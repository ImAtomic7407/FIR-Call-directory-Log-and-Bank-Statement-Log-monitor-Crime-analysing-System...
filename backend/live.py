"""Live layer: file a new FIR -> re-run the pipeline -> work out which police stations need to know -> push it.

Nothing here is decided by the LLM. Routing is plain rules over computed facts:
  cross_station_link  a person in the new FIR already appears in FIRs of other stations
  new_alert           the new data triggered a detector alert; every station the alert touches is told
  jurisdiction_notice the FIR text refers to an area that belongs to another station
  (manual)            request_assistance / share_intel / bolo sent by an officer via dispatch()
"""
import asyncio
import json
import os
import re
import threading
import zlib
from collections import Counter
from datetime import datetime
from pathlib import Path

import geo
from analysis import Analysis, CACHE
from extract import PH, PLATE, name_kind, norm_phone
from graph import build_graph, compute_metrics
from patterns import run_all
from risk import risk_scores

TOWER_SHARE = 0.25  # min share of an alert's calls for a tower area to count as routing evidence
LOCK = threading.RLock()
STATE_FILE = Path(os.getenv("LIVE_STATE_FILE") or CACHE / "live_state.json")
LIVE_FIRS: list = []
CUSTOM: list = []  # alerts raised by hand by an officer (type officer_flag)
NOTES: list = []
_seq = {"note": 0, "demo": 0}


# ------------------------------------------------------------------ persistence
def load():
    if STATE_FILE.exists():
        try:
            d = json.loads(STATE_FILE.read_text())
            LIVE_FIRS[:] = d.get("firs", [])
            NOTES[:] = d.get("notifications", [])
            CUSTOM[:] = d.get("custom_alerts", [])
            _seq.update(d.get("seq", {}))
        except Exception:
            pass


def save():
    CACHE.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(dict(firs=LIVE_FIRS, notifications=NOTES, custom_alerts=CUSTOM, seq=_seq), ensure_ascii=False, indent=1))


def reset():
    with LOCK:
        LIVE_FIRS.clear(); NOTES.clear(); CUSTOM.clear(); _seq.update(note=0, demo=0, custom=0)
        if STATE_FILE.exists():
            STATE_FILE.unlink()


# ------------------------------------------------------------------ event broker (SSE)
class Broker:
    """In-process pub/sub. publish() is callable from any thread; subscribers are asyncio queues."""

    def __init__(self):
        self.subs = []       # (station_id|None, loop, queue)
        self.ring = []       # recent events for reconnect replay
        self.seq = 0
        self.lock = threading.Lock()

    def publish(self, event, data, station=None):
        """station=None -> everybody; otherwise only that station (and observers who did not pick a station)."""
        with self.lock:
            self.seq += 1
            ev = dict(seq=self.seq, event=event, station=station, ts=datetime.now().isoformat(timespec="seconds"), data=data)
            self.ring.append(ev)
            del self.ring[:-500]
            subs = list(self.subs)
        for st, loop, q in subs:
            if self._wants(st, ev):
                try:
                    loop.call_soon_threadsafe(q.put_nowait, ev)
                except RuntimeError:
                    pass
        return ev

    @staticmethod
    def _wants(sub_station, ev):
        return sub_station is None or ev["station"] is None or ev["station"] == sub_station

    def subscribe(self, station, loop):
        q = asyncio.Queue()
        with self.lock:
            self.subs.append((station, loop, q))
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.subs = [s for s in self.subs if s[2] is not q]

    def replay(self, station, since):
        with self.lock:
            return [e for e in self.ring if e["seq"] > since and self._wants(station, e)]


BUS = Broker()


# ------------------------------------------------------------------ pipeline
def build(live_firs, known=None):
    if live_firs and known is None:
        known = Analysis().entities  # live free-text FIRs are matched against people from the base data
    A = Analysis(live_firs=live_firs, known=known)
    G = build_graph(A)
    M = compute_metrics(A, G)
    alerts = run_all(A)
    risk = risk_scores(A, M["metrics"], alerts)
    # officer flags come after scoring: a hand-raised alert must not change anyone's computed risk
    alerts = alerts + [dict(c, entities=[e for e in c["entities"] if e in A.entities]) for c in CUSTOM]
    return dict(A=A, G=G, M=M, alerts=alerts, risk=risk, geo=geo_index(A, alerts))


def _strip_stations(text):
    for st in sorted(geo.STATIONS.values(), key=lambda s: -len(s["name"])):
        for v in {st["name"], st["short"] + " PS", st["short"] + " Police Station"}:
            text = re.sub(re.escape(v), " ", text, flags=re.I)
    return text


def _jitter(key, span=0.006):
    h = zlib.crc32(str(key).encode())  # stable across restarts (str hash() is salted per process)
    return ((h % 1000) / 1000 - 0.5) * span, (((h // 1000) % 1000) / 1000 - 0.5) * span


def fir_geo(A, ex_by_id, f):
    sid = geo.station_id(f["station"])
    body = _strip_stations(f["text"])
    mentioned = geo.areas_in(body)
    for m in ex_by_id.get(f["fir_id"], {}).get("mentions", []):  # extractor locations first: they are the actual subject location
        a = geo.area_id(m.get("location"))
        if a and a not in mentioned:
            mentioned.insert(0, a)
    primary = mentioned[0] if mentioned else None
    if primary:
        base = geo.AREAS[primary]
    else:
        base = geo.STATIONS[sid] if sid else dict(lat=28.6, lon=77.15)
    dj, dl = _jitter(f["fir_id"])
    return dict(station=sid, area=primary, areas=mentioned, lat=round(base["lat"] + dj, 5), lon=round(base["lon"] + dl, 5),
                located_by="text" if primary else "station")


def alert_stations(A, a):
    """Which stations an alert concerns, and why. Pure facts: where its evidence FIRs were filed, where its calls were made,
    and which stations already hold FIRs on the people involved.
    routed = the station gets notified: evidence is in its area, or it holds FIRs on >=2 of the alert's people
    (>=1 when the alert only has one or two people). Other stations with a single matching person are covered by the
    per-person cross_station_link notice instead, so a 7-person alert does not page every station."""
    why = {}

    def row(sid):
        return why.setdefault(sid, dict(station=sid, evidence=0, reasons=[], people={}))

    for fid in a["evidence"]["firs"]:
        f = A.fir_by_id.get(fid)
        sid = geo.station_id(f["station"]) if f else None
        if sid:
            r = row(sid)
            r["evidence"] += 3
            r["reasons"].append(f"{fid} was filed here")
    calls = a["evidence"]["calls"]
    if calls:
        by_tower = Counter(A.cdr[A.cdr.call_id.isin(calls)].tower_location)
        total = sum(by_tower.values()) or 1
        for tower, n in by_tower.items():
            aid = geo.area_id(tower)
            if aid:
                r = row(geo.station_of_area(aid))
                if n / total >= TOWER_SHARE:  # a phone seen in 12 areas is not evidence about each of them
                    r["evidence"] += 2
                r["reasons"].append(f"{n} of the alert's {total} calls were made from {tower}")
    for eid in a["entities"]:
        for fid in (A.entities.get(eid) or {}).get("firs", []):
            f = A.fir_by_id.get(fid)
            sid = geo.station_id(f["station"]) if f else None
            if sid:
                row(sid)["people"].setdefault(eid, []).append(fid)
    need = min(2, max(len(a["entities"]), 1))
    out = []
    for sid, r in why.items():
        for eid, fl in r.pop("people").items():
            r["reasons"].append(f"{A.name(eid)} is named in {', '.join(fl)} here")
            r["evidence"] += 0
            r.setdefault("n_people", 0)
            r["n_people"] += 1
        r["routed"] = r["evidence"] > 0 or r.get("n_people", 0) >= need
        r["weight"] = r.pop("evidence") + r.get("n_people", 0)
        out.append(r)
    return sorted(out, key=lambda d: -d["weight"])


def alert_areas(A, a):
    c = Counter()
    if a["evidence"]["calls"]:
        for tower, n in Counter(A.cdr[A.cdr.call_id.isin(a["evidence"]["calls"])].tower_location).items():
            aid = geo.area_id(tower)
            if aid:
                c[aid] += n
    return c


def _custom_route(A, a, st, lat, lon):
    """The raising station and the stations it was sent to always get the alert; place it on the map at the
    people's home areas if known, else at the raising station."""
    d = a["details"]
    by = {r["station"]: r for r in st}
    for sid, why in [(d["raised_by"], "raised here by hand"), *[(t, f"sent here by {geo.STATIONS[d['raised_by']]['name']}") for t in d["to_stations"]]]:
        r = by.get(sid) or by.setdefault(sid, dict(station=sid, reasons=[], weight=0))
        r["reasons"].insert(0, why); r["routed"] = True; r["weight"] += 5
    if lat is None:
        pts = [geo.AREAS[h] for e in a["entities"] if (h := _home(A, e)) in geo.AREAS]
        if pts:
            lat, lon = sum(p["lat"] for p in pts) / len(pts), sum(p["lon"] for p in pts) / len(pts)
        else:
            s0 = geo.STATIONS[d["raised_by"]]; lat, lon = s0["lat"], s0["lon"]
    return sorted(by.values(), key=lambda r: -r["weight"]), lat, lon


def _home(A, eid):
    c = A.cdr[A.cdr.caller_ent == eid].tower_location
    if len(c):
        return geo.area_id(Counter(c).most_common(1)[0][0])
    return None


def sig(A, a):
    """Alert identity that survives re-numbering: type + people (by name) + start time."""
    return f'{a["type"]}|{",".join(sorted(A.name(e) for e in a["entities"]))}|{a["time"]["start"]}'


def geo_index(A, alerts):
    ex_by_id = {x["fir_id"]: x for x in A.extracted}
    firs = {f["fir_id"]: fir_geo(A, ex_by_id, f) for f in A.firs}
    al = {}
    for a in alerts:
        st = alert_stations(A, a)
        ar = alert_areas(A, a)
        if ar:
            tot = sum(ar.values())
            lat = sum(geo.AREAS[k]["lat"] * v for k, v in ar.items()) / tot
            lon = sum(geo.AREAS[k]["lon"] * v for k, v in ar.items()) / tot
        elif st:
            s0 = geo.STATIONS[st[0]["station"]]
            lat, lon = s0["lat"], s0["lon"]
        else:
            lat = lon = None
        if a.get("custom"):
            st, lat, lon = _custom_route(A, a, st, lat, lon)
        al[a["id"]] = dict(sig=sig(A, a), stations=st, areas=dict(ar), lat=lat and round(lat, 5), lon=lon and round(lon, 5),
                           cross_station=len(st) > 1)
    ent = {}
    caller = A.cdr[A.cdr.caller_ent.notna()].sort_values("ts")
    for eid, g in caller.groupby("caller_ent"):
        towers = Counter(geo.area_id(t) for t in g.tower_location)
        last = g.iloc[-1]
        ent[eid] = dict(last_seen=dict(area=geo.area_id(last.tower_location), ts=str(last.ts)),
                        home_area=towers.most_common(1)[0][0], towers=dict(towers))
    for eid, e in A.entities.items():
        d = ent.setdefault(eid, dict(last_seen=None, home_area=None, towers={}))
        d["stations"] = sorted({geo.station_id(A.fir_by_id[f]["station"]) for f in e.get("firs", []) if f in A.fir_by_id} - {None})
        d["fir_areas"] = sorted({a for f in e.get("firs", []) for a in firs.get(f, {}).get("areas", [])})
        if d["home_area"] is None and d["fir_areas"]:
            d["home_area"] = d["fir_areas"][0]
    return dict(firs=firs, alerts=al, entities=ent)


# ------------------------------------------------------------------ free-text FIR support
SUSPECT_WORDS = re.compile(r"accused|suspect|arrested|apprehended|detained|absconding|wanted", re.I)
NEW_PERSON = re.compile(rf"(?P<kw>accused|suspect|named|complainant|victim|arrested|apprehended|detained)\s+(?P<n>[A-Z][a-z]+ [A-Z][a-z]+)")


def loose_augment(ex, known):
    """Template extraction only understands the synthetic phrasing. For FIRs typed in by officers we also
    (1) recognise people already in the system by full name or by phone/plate, and (2) pick up 'accused <Full Name> ... <phone>'.
    Everything it adds is a normal mention, so the usual resolution rules and evidence trail apply."""
    text = ex["text"]
    ms = ex["mentions"]
    have = {m["surface"].lower() for m in ms}
    phones_in = {norm_phone(p) for p in re.findall(PH, text)} - {None}
    plates_in = set(re.findall(PLATE, text))
    sents = re.split(r"(?<=[.!?])\s+", text)

    def sentence(pos_text):
        return next((s for s in sents if pos_text.lower() in s.lower()), text[:160])

    def add(surface, ev, **kw):
        m = dict(idx=len(ms), surface=surface, kind=name_kind(surface), phone=None, alias=None, role="mentioned", org=None,
                 plate=None, vehicle_desc=None, location=None, evidence=ev)
        m.update({k: v for k, v in kw.items() if v})
        ms.append(m)
        have.add(surface.lower())

    for e in known.values():
        nm = e.get("name", "")
        if not nm or len(nm.split()) < 2 or e.get("type") != "person":
            continue
        by_name = re.search(rf"\b{re.escape(nm)}\b", text, re.I)
        ph = [p for p in e.get("phones", []) if p in phones_in]
        pl = [p for p in e.get("plates", []) if p in plates_in]
        if not (by_name or ph):
            continue
        if nm.lower() in have:
            continue
        role = "suspect" if SUSPECT_WORDS.search(sentence(by_name.group(0) if by_name else ph[0])) else "mentioned"
        add(nm, sentence(by_name.group(0) if by_name else ph[0]), phone=ph[0] if ph else None, plate=pl[0] if pl else None, role=role)

    for m in NEW_PERSON.finditer(text):
        nm = m["n"]
        if nm.lower() in have:
            continue
        p = re.search(PH, text[m.end():m.end() + 160])  # the number may sit in the next sentence ("A mobile phone (...) was recovered")
        role = "victim" if m["kw"].lower() in ("complainant", "victim") else "suspect"
        add(nm, m.group(0), phone=norm_phone(p.group(0)) if p else None, role=role)
    return ex


# ------------------------------------------------------------------ notifications
def _public(n, S):
    A = S["A"]
    cur = None
    if n["refs"].get("alert_sig"):
        cur = next((aid for aid, g in S["geo"]["alerts"].items() if g["sig"] == n["refs"]["alert_sig"]), None)
    fn = lambda x: geo.STATIONS[x]["name"] if x in geo.STATIONS else x
    return dict(n, from_name=fn(n["from_station"]), to_name=fn(n["to_station"]),
                refs=dict(n["refs"], alert_id=cur or n["refs"].get("alert_id")))


def _note(kind, severity, frm, to, title, body, refs=None, reply_to=None):
    _seq["note"] += 1
    n = dict(id=f'N-{_seq["note"]:04d}', ts=datetime.now().isoformat(timespec="seconds"), kind=kind, severity=severity,
             from_station=frm, to_station=to, title=title, body=body, refs=refs or {}, status="new", ack_at=None,
             reply_to=reply_to, responses=[])
    NOTES.append(n)
    return n


def _push(n, S):
    BUS.publish("notification", _public(n, S), station=n["to_station"])


def _ents(A, eids):
    return [dict(id=e, name=A.name(e)) for e in eids]


def file_fir(S, station, text, date=None, reporter=None):
    """Add a FIR, rebuild everything, route notifications, push events. Raises ValueError on bad input."""
    sid = geo.station_id(station)
    if not sid:
        raise ValueError(f"unknown police station: {station!r}")
    if not text or len(text.strip()) < 20:
        raise ValueError("FIR text is too short")
    with LOCK:
        old = S
        old_sigs = {g["sig"] for g in old["geo"]["alerts"].values()}
        old_names = {e["name"] for e in old["A"].entities.values()}
        old_risk = {old["A"].name(k): v["score"] for k, v in old["risk"].items()}
        nums = [int(m.group(1)) for f in old["A"].firs if (m := re.match(r"FIR-(\d+)$", f["fir_id"]))]
        fid = f"FIR-{max(nums, default=0) + 1:03d}"
        fir = dict(fir_id=fid, date=date or datetime.now().strftime("%Y-%m-%d"), station=geo.STATIONS[sid]["name"], text=text.strip(),
                   source="live", filed_at=datetime.now().isoformat(timespec="seconds"), reporter=reporter)
        LIVE_FIRS.append(fir)
        try:
            new = build(LIVE_FIRS, known=old["A"].entities)
        except Exception:
            LIVE_FIRS.pop()
            raise
        S.update(new)
        A = new["A"]
        fg = new["geo"]["firs"][fid]
        stn = geo.STATIONS[sid]
        people = [e for e in A.entities.values() if fid in e.get("firs", [])]
        notes, seen = [], set()

        def send(kind, severity, to, title, body, refs):
            if (to, kind, title) in seen:
                return
            seen.add((to, kind, title))
            notes.append(_note(kind, severity, sid, to, title, body, refs))

        # 1. people who already appear in other stations' FIRs
        ent_view = []
        for e in people:
            others = [f for f in e["firs"] if f != fid]
            ost = {}
            for f in others:
                s2 = geo.station_id(A.fir_by_id[f]["station"])
                if s2:
                    ost.setdefault(s2, []).append(f)
            r = new["risk"].get(e["id"], {})
            ent_view.append(dict(id=e["id"], name=e["name"], role=e.get("role"), is_new=e["name"] not in old_names,
                                 risk=r.get("score"), risk_level=r.get("level"), prev_risk=old_risk.get(e["name"]),
                                 other_firs=others, other_stations=sorted(ost)))
            for s2, fl in ost.items():
                if s2 == sid:
                    continue
                send("cross_station_link", r.get("level") if r.get("level") in ("high", "medium") else "low", s2,
                     f"{e['name']} (in your {', '.join(fl)}) is named in new {fid} at {stn['short']}",
                     f"{stn['name']} just registered {fid} naming {e['name']}. Your station already holds {', '.join(fl)} on the same person. "
                     f"Risk score is now {r.get('score')}/100. Consider coordinating before either station acts.",
                     dict(fir_id=fid, entities=_ents(A, [e["id"]]), other_firs=fl))

        # 2. alerts that did not exist before
        new_alerts = []
        for a in new["alerts"]:
            g = new["geo"]["alerts"][a["id"]]
            if g["sig"] in old_sigs:
                continue
            new_alerts.append(dict(a, geo=g))
            targets = {sid} | {s["station"] for s in g["stations"] if s["routed"]}
            for t in targets:
                send("new_alert", a["severity"], t, f"New alert: {a['title']}",
                     f"{a['summary']} Triggered after {fid} was filed at {stn['short']}. "
                     + ("This alert spans several stations: " + ", ".join(geo.STATIONS[x]["short"] for x in sorted(targets)) + "." if len(targets) > 1 else ""),
                     dict(fir_id=fid, alert_id=a["id"], alert_sig=g["sig"], entities=_ents(A, a["entities"])))

        # 3. the FIR talks about places that belong to another station
        for aid in fg["areas"]:
            owner = geo.station_of_area(aid)
            if owner and owner != sid:
                who = ", ".join(e["name"] for e in people) or "unnamed parties"
                send("jurisdiction_notice", "low", owner, f"{fid} from {stn['short']} concerns {geo.AREAS[aid]['name']} (your area)",
                     f"{stn['name']} registered {fid} which refers to {geo.AREAS[aid]['name']}, inside your jurisdiction. People involved: {who}.",
                     dict(fir_id=fid, area=aid, entities=_ents(A, [e["id"] for e in people])))

        save()
        for n in notes:
            _push(n, S)
        new_names = [e["name"] for e in ent_view if e["is_new"]]
        result = dict(fir=dict(fir, geo=fg), entities=ent_view, new_alerts=new_alerts, notifications=[_public(n, S) for n in notes],
                      summary=f"{fid} filed at {stn['name']}: {len(people)} people recognised ({len(new_names)} new), "
                              f"{len(new_alerts)} new alert(s), {len(notes)} station notification(s).")
        BUS.publish("fir.created", dict(fir=dict(fir, geo=fg), entities=ent_view, summary=result["summary"]))
        BUS.publish("graph.updated", dict(firs=len(A.firs), entities=len(A.entities), alerts=len(new["alerts"]), cause=fid))
        return result


def dispatch(S, frm, to_list, kind, title, body, severity="medium", refs=None):
    """An officer sends something to other stations by hand: request_assistance | share_intel | bolo."""
    f = geo.station_id(frm)
    if not f:
        raise ValueError(f"unknown sender station: {frm!r}")
    if kind not in ("request_assistance", "share_intel", "bolo"):
        raise ValueError("kind must be request_assistance, share_intel or bolo")
    targets = []
    for t in to_list:
        s = geo.station_id(t)
        if not s:
            raise ValueError(f"unknown station: {t!r}")
        if s != f and s not in targets:
            targets.append(s)
    if not targets:
        raise ValueError("pick at least one other station")
    with LOCK:
        out = [_note(kind, severity, f, t, title, body, refs or {}) for t in targets]
        save()
    for n in out:
        _push(n, S)
    return [_public(n, S) for n in out]


def ack(S, nid, station):
    s = geo.station_id(station)
    with LOCK:
        n = next((x for x in NOTES if x["id"] == nid), None)
        if not n:
            raise KeyError(nid)
        if s and s != n["to_station"]:
            raise ValueError("only the receiving station can acknowledge")
        n["status"], n["ack_at"] = "ack", datetime.now().isoformat(timespec="seconds")
        save()
    BUS.publish("notification.ack", dict(id=nid, ack_at=n["ack_at"]), station=n["from_station"])
    return _public(n, S)


def respond(S, nid, station, text):
    s = geo.station_id(station)
    with LOCK:
        n = next((x for x in NOTES if x["id"] == nid), None)
        if not n:
            raise KeyError(nid)
        if s != n["to_station"]:
            raise ValueError("only the receiving station can reply")
        n["status"], n["ack_at"] = "ack", n["ack_at"] or datetime.now().isoformat(timespec="seconds")
        n["responses"].append(dict(ts=datetime.now().isoformat(timespec="seconds"), text=text))
        r = _note("reply", n["severity"], s, n["from_station"], f"Re: {n['title']}", text, n["refs"], reply_to=nid)
        save()
    _push(r, S)
    return _public(r, S)


def inbox(S, station=None, status=None, frm=None, kind=None, limit=100, direction="in"):
    s = geo.station_id(station) if station else None
    key = "to_station" if direction == "in" else "from_station"
    rows = [n for n in reversed(NOTES) if (not s or n[key] == s) and (not status or n["status"] == status)
            and (not frm or n["from_station"] == geo.station_id(frm)) and (not kind or n["kind"] == kind)]
    return [_public(n, S) for n in rows[:limit]]


# ------------------------------------------------------------------ demo scenarios (generated from the data, never hard-coded)
def next_demo(S):
    """Pick a high-risk person who already has a FIR at one station, and write a new FIR about them at a different station.
    Alternates between template phrasing and free prose so both extraction paths get exercised."""
    A, risk = S["A"], S["risk"]
    ranked = sorted((e for e in A.entities.values() if e.get("firs") and e.get("phones") and e.get("type") == "person"),
                    key=lambda e: -risk.get(e["id"], {}).get("score", 0))
    if not ranked:
        raise ValueError("no suitable entity for a demo FIR")
    i = _seq["demo"]
    _seq["demo"] += 1
    e = ranked[i % min(len(ranked), 8)]
    have = {geo.station_id(A.fir_by_id[f]["station"]) for f in e["firs"]}
    cands = [s for s in geo.STATIONS if s not in have]
    st = geo.STATIONS[cands[(i * 5 + 3) % len(cands)]]
    gi = S["geo"]["entities"].get(e["id"], {})
    area = geo.AREAS.get(gi.get("home_area")) or (geo.AREAS[st["areas"][0]] if st["areas"] else None)
    area_name = area["name"] if area else st["short"]
    ph = e["phones"][0]
    ph_fmt = f"{ph[:5]} {ph[5:]}"
    if i % 2 == 0:
        text = (f"An informant told {st['name']} that {e['name']} regularly visits {area_name} and can be reached on {ph_fmt}. "
                f"The suspect was seen collecting cash from traders late at night.")
    else:
        text = (f"During a naka check near {st['short']}, officers detained a driver who named {e['name']} as the person directing the movement "
                f"of goods to {area_name}. The contact number given was {ph_fmt}. Inquiry is continuing.")
    return dict(station=st["id"], station_name=st["name"], text=text, about=dict(id=e["id"], name=e["name"]), area=area_name)


load()


# ------------------------------------------------------------------ officer-raised alerts
SEVERITIES = ("high", "medium", "low")


def raise_alert(S, station, title, note, severity="medium", entities=(), firs=(), to_list=()):
    """An officer flags something by hand. It joins the alert list (type officer_flag), shows on the map,
    and the chosen stations get it in their inbox."""
    sid = geo.station_id(station)
    if not sid:
        raise ValueError(f"unknown station: {station!r}")
    title = (title or "").strip()
    if not title:
        raise ValueError("give the alert a title")
    if severity not in SEVERITIES:
        raise ValueError("severity must be high, medium or low")
    A = S["A"]
    bad = [e for e in entities if e not in A.entities] + [f for f in firs if f not in A.fir_by_id]
    if bad:
        raise ValueError(f"not found: {', '.join(bad)}")
    if not entities and not firs:
        raise ValueError("pick at least one person or FIR")
    targets = []
    for t in to_list:
        x = geo.station_id(t)
        if not x:
            raise ValueError(f"unknown station: {t!r}")
        if x != sid and x not in targets:
            targets.append(x)
    with LOCK:
        _seq["custom"] = _seq.get("custom", 0) + 1
        now = datetime.now().isoformat(timespec="seconds")
        a = dict(id=f'CUS-{_seq["custom"]:02d}', type="officer_flag", severity=severity, title=title,
                 summary=(note or "").strip() or f"Raised by hand by {geo.STATIONS[sid]['name']}.",
                 entities=list(dict.fromkeys(entities)), evidence=dict(calls=[], txns=[], firs=list(dict.fromkeys(firs))),
                 time=dict(start=now, end=None), custom=True,
                 details=dict(raised_by=sid, raised_by_name=geo.STATIONS[sid]["name"], raised_at=now, to_stations=targets))
        CUSTOM.append(a)
        try:
            S.update(build(LIVE_FIRS, known=A.entities if LIVE_FIRS else None))
        except Exception:
            CUSTOM.pop()
            raise
        notes = [_note("new_alert", severity, sid, t, f"Officer alert: {title}", a["summary"], dict(alert_id=a["id"])) for t in targets]
        save()
    for n in notes:
        _push(n, S)
    BUS.publish("graph.updated", dict(alerts=len(S["alerts"]), cause="custom_alert"))
    return a


def withdraw_alert(S, aid, station):
    with LOCK:
        a = next((c for c in CUSTOM if c["id"] == aid), None)
        if not a:
            raise KeyError(aid)
        if geo.station_id(station) != a["details"]["raised_by"]:
            raise ValueError("only the station that raised this alert can withdraw it")
        CUSTOM.remove(a)
        S.update(build(LIVE_FIRS, known=S["A"].entities if LIVE_FIRS else None))
        save()
    BUS.publish("graph.updated", dict(alerts=len(S["alerts"]), cause="custom_alert_withdrawn"))
