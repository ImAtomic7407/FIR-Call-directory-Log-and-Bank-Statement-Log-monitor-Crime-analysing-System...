"""HTTP surface for the map view, police stations, live FIRs and cross-station notifications.

Everything the map shows is computed from the same Analysis the graph uses; this module only filters, aggregates
and shapes it. Station identity is a plain `station` parameter (id or name): this is a prototype with no auth.
"""
import asyncio
import json
from collections import Counter, defaultdict
from datetime import timedelta

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import geo
import live

router = APIRouter()
S = None  # shared state dict, set by attach()


def attach(app, state):
    global S
    S = state
    app.include_router(router)


def _snap():
    return dict(S)


def _csv(x):
    return [v.strip() for v in x.split(",") if v.strip()] if x else []


def _station_filter(station, district, state):
    """Resolve station / district / state params to a set of station ids (None = no restriction)."""
    allowed = None
    if station:
        ids = {geo.station_id(s) for s in _csv(station)}
        if None in ids:
            bad = [s for s in _csv(station) if not geo.station_id(s)]
            raise HTTPException(400, f"unknown station: {bad}")
        allowed = ids
    for key, vals in (("district", _csv(district)), ("state", _csv(state))):
        if vals:
            m = {s["id"] for s in geo.STATIONS.values() if s[key].lower() in {v.lower() for v in vals}}
            allowed = m if allowed is None else allowed & m
    return allowed


def _area_filter(area):
    ids = set()
    for a in _csv(area):
        aid = a if a in geo.AREAS else geo.area_id(a)
        if not aid:
            raise HTTPException(400, f"unknown area: {a}")
        ids.add(aid)
    return ids or None


def _in_dates(d, start, end):
    d = str(d)[:10]
    return (not start or d >= start) and (not end or d <= end)


def _name(sid):
    return geo.STATIONS[sid]["name"] if sid in geo.STATIONS else sid


# ---------------------------------------------------------------- geography
@router.get("/geo/meta")
def geo_meta():
    return geo.meta()


@router.get("/map/filters")
def map_filters():
    s = _snap()
    A = s["A"]
    dates = [f["date"] for f in A.firs] + [str(A.t_min)[:10], str(A.t_max)[:10]]
    return dict(stations=[dict(id=x["id"], name=x["name"], district=x["district"], state=x["state"]) for x in geo.STATIONS.values()],
                districts=sorted({x["district"] for x in geo.STATIONS.values()}), states=sorted({x["state"] for x in geo.STATIONS.values()}),
                areas=[dict(id=a["id"], name=a["name"], station=a["station"]) for a in geo.AREAS.values()],
                alert_types=sorted({a["type"] for a in s["alerts"]}), severities=sorted({a["severity"] for a in s["alerts"]}),
                layers=["firs", "towers", "entities", "alerts"], sources=["base", "live"],
                date_range=[min(dates), max(dates)], risk_range=[0, 100])


def _alert_row(s, a):
    g = s["geo"]["alerts"][a["id"]]
    return dict(a, geo=dict(g, stations=[dict(st, name=_name(st["station"])) for st in g["stations"]]))


def _tower_stats(s, start, end):
    A, risk = s["A"], s["risk"]
    c = A.cdr
    if start:
        c = c[c.ts >= pd.Timestamp(start)]
    if end:
        c = c[c.ts < pd.Timestamp(end) + timedelta(days=1)]
    out = {}
    for tower, g in c.groupby("tower_location"):
        aid = geo.area_id(tower)
        if not aid:
            continue
        people = Counter(e for e in g.caller_ent if e)
        ppl = [dict(id=e, name=A.name(e), calls=n, risk=risk.get(e, {}).get("score")) for e, n in people.most_common(5)]
        out[aid] = dict(calls=int(len(g)), phones=int(g.caller.nunique()), people=len(people), tower_ids=sorted(g.tower_id.unique()),
                        high_risk_people=sum(1 for e in people if risk.get(e, {}).get("score", 0) >= 60), top_people=ppl,
                        night_calls=int(((g.ts.dt.hour >= 22) | (g.ts.dt.hour < 5)).sum()))
    return out


@router.get("/map/stations")
def map_stations(start: str | None = None, end: str | None = None, station: str | None = None,
                 district: str | None = None, state: str | None = None):
    """One row per station: location, jurisdiction polygon and live counters (for markers and the station panel)."""
    s = _snap()
    A, risk = s["A"], s["risk"]
    allowed = _station_filter(station, district, state)
    firs_by = defaultdict(list)
    for f in A.firs:
        if _in_dates(f["date"], start, end):
            firs_by[geo.station_id(f["station"])].append(f)
    alerts_by = defaultdict(list)
    for a in s["alerts"]:
        for st in s["geo"]["alerts"][a["id"]]["stations"]:
            if st["routed"]:
                alerts_by[st["station"]].append(a)
    unread = Counter(n["to_station"] for n in live.NOTES if n["status"] == "new")
    towers = _tower_stats(s, start, end)
    out = []
    for sid, st in geo.STATIONS.items():
        if allowed is not None and sid not in allowed:
            continue
        people = {e for f in firs_by[sid] for e, ent in A.entities.items() if f["fir_id"] in ent.get("firs", [])}
        out.append(dict(st, firs=len(firs_by[sid]), live_firs=sum(1 for f in firs_by[sid] if f.get("source") == "live"),
                        alerts=len(alerts_by[sid]), high_alerts=sum(1 for a in alerts_by[sid] if a["severity"] == "high"),
                        cross_station_alerts=sum(1 for a in alerts_by[sid] if s["geo"]["alerts"][a["id"]]["cross_station"]),
                        people=len(people), high_risk_people=sum(1 for e in people if risk.get(e, {}).get("score", 0) >= 60),
                        calls=sum(towers.get(a, {}).get("calls", 0) for a in st["areas"]), unread_notifications=unread.get(sid, 0)))
    return out


@router.get("/map/features")
def map_features(layers: str = "firs,towers,entities,alerts", station: str | None = None, district: str | None = None,
                 state: str | None = None, area: str | None = None, start: str | None = None, end: str | None = None,
                 min_risk: int = 0, severity: str | None = None, alert_type: str | None = None, q: str | None = None,
                 source: str | None = None, cross_station: bool = False):
    """Map markers for the chosen layers, all sharing one filter set. Each feature: {kind, id, lat, lon, ...props}."""
    s = _snap()
    A, risk, M = s["A"], s["risk"], s["M"]["metrics"]
    L = set(_csv(layers))
    allowed = _station_filter(station, district, state)
    areas = _area_filter(area)
    ql = (q or "").lower().strip()
    sev, atype = set(_csv(severity)), set(_csv(alert_type))
    feats = []

    def st_ok(sids):
        return allowed is None or bool(set(sids) & allowed)

    if "firs" in L:
        for f in A.firs:
            g = s["geo"]["firs"][f["fir_id"]]
            if not (st_ok([g["station"]]) and _in_dates(f["date"], start, end)):
                continue
            if areas and not (areas & set(g["areas"])):
                continue
            if source and f.get("source", "base") != source:
                continue
            ppl = [dict(id=e["id"], name=e["name"], risk=risk.get(e["id"], {}).get("score")) for e in A.entities.values() if f["fir_id"] in e.get("firs", [])]
            if min_risk and not any((p["risk"] or 0) >= min_risk for p in ppl):
                continue
            if ql and ql not in f["text"].lower() and ql not in f["fir_id"].lower() and not any(ql in p["name"].lower() for p in ppl):
                continue
            feats.append(dict(kind="fir", id=f["fir_id"], lat=g["lat"], lon=g["lon"], date=f["date"], station=g["station"], station_name=f["station"],
                              area=g["area"], areas=g["areas"], located_by=g["located_by"], source=f.get("source", "base"),
                              snippet=f["text"][:160], people=ppl, max_risk=max((p["risk"] or 0 for p in ppl), default=0)))

    if "towers" in L:
        stats = _tower_stats(s, start, end)
        for aid, a in geo.AREAS.items():
            if not st_ok([a["station"]]) or (areas and aid not in areas):
                continue
            t = stats.get(aid, dict(calls=0, phones=0, people=0, tower_ids=[], high_risk_people=0, top_people=[], night_calls=0))
            if min_risk and not any((p["risk"] or 0) >= min_risk for p in t["top_people"]):
                continue
            if ql and ql not in a["name"].lower() and not any(ql in p["name"].lower() for p in t["top_people"]):
                continue
            feats.append(dict(kind="tower", id=aid, name=a["name"], lat=a["lat"], lon=a["lon"], station=a["station"], station_name=_name(a["station"]), **t))

    if "entities" in L:
        for eid, e in A.entities.items():
            g = s["geo"]["entities"].get(eid)
            if not g:
                continue
            at = (g["last_seen"] or {}).get("area") or g["home_area"]
            if not at:
                continue
            r = risk.get(eid, {}).get("score", 0)
            sids = set(g["stations"]) | {geo.station_of_area(at)}
            if not st_ok(sids) or r < min_risk or (areas and not (areas & ({at, g["home_area"]} | set(g["towers"])))):
                continue
            if g["last_seen"] and not _in_dates(g["last_seen"]["ts"], start, end):
                continue
            if ql and ql not in e["name"].lower() and not any(ql in x.lower() for x in e.get("aliases", [])) and not any(ql in p for p in e.get("phones", [])):
                continue
            dj, dl = live._jitter(eid, 0.008)
            base = geo.AREAS[at]
            feats.append(dict(kind="entity", id=eid, name=e["name"], lat=round(base["lat"] + dj, 5), lon=round(base["lon"] + dl, 5), role=e.get("role"),
                              risk=r, risk_level=risk.get(eid, {}).get("level"), community=M.get(eid, {}).get("community"),
                              area=at, home_area=g["home_area"], last_seen=g["last_seen"], stations=g["stations"],
                              multi_station=len(g["stations"]) > 1, firs=e.get("firs", []), alerts=risk.get(eid, {}).get("alerts", [])))

    if "alerts" in L:
        for a in s["alerts"]:
            g = s["geo"]["alerts"][a["id"]]
            if g["lat"] is None or not st_ok([x["station"] for x in g["stations"]]):
                continue
            if (sev and a["severity"] not in sev) or (atype and a["type"] not in atype) or (cross_station and not g["cross_station"]):
                continue
            if areas and not (areas & set(g["areas"])):
                continue
            t0 = a["time"]["start"]
            if t0 and not _in_dates(t0, start, end):
                continue
            if ql and ql not in a["title"].lower() and not any(ql in A.name(e).lower() for e in a["entities"]):
                continue
            feats.append(dict(kind="alert", id=a["id"], lat=g["lat"], lon=g["lon"], type=a["type"], severity=a["severity"], title=a["title"],
                              summary=a["summary"], time=a["time"], cross_station=g["cross_station"], areas=list(g["areas"]),
                              stations=[dict(x, name=_name(x["station"])) for x in g["stations"]],
                              entities=[dict(id=e, name=A.name(e)) for e in a["entities"]]))

    counts = Counter(f["kind"] for f in feats)
    return dict(count=len(feats), by_kind=dict(counts), features=feats)


@router.get("/map/heat")
def map_heat(metric: str = "calls", start: str | None = None, end: str | None = None, station: str | None = None,
             district: str | None = None, state: str | None = None):
    """Weighted points for a heat layer. metric: calls | night_calls | firs | alerts | risk."""
    s = _snap()
    allowed = _station_filter(station, district, state)
    pts = []
    if metric in ("calls", "night_calls", "risk"):
        for aid, t in _tower_stats(s, start, end).items():
            a = geo.AREAS[aid]
            if allowed is not None and a["station"] not in allowed:
                continue
            w = {"calls": t["calls"], "night_calls": t["night_calls"], "risk": t["high_risk_people"]}[metric]
            pts.append(dict(lat=a["lat"], lon=a["lon"], weight=w, area=aid))
    elif metric == "firs":
        for f in s["A"].firs:
            g = s["geo"]["firs"][f["fir_id"]]
            if (allowed is None or g["station"] in allowed) and _in_dates(f["date"], start, end):
                pts.append(dict(lat=g["lat"], lon=g["lon"], weight=1, area=g["area"]))
    elif metric == "alerts":
        for a in s["alerts"]:
            g = s["geo"]["alerts"][a["id"]]
            if g["lat"] is not None and (allowed is None or any(x["station"] in allowed for x in g["stations"])):
                pts.append(dict(lat=g["lat"], lon=g["lon"], weight=3 if a["severity"] == "high" else 1, area=None))
    else:
        raise HTTPException(400, "metric must be calls, night_calls, firs, alerts or risk")
    mx = max((p["weight"] for p in pts), default=1) or 1
    return dict(metric=metric, max=mx, points=[dict(p, intensity=round(p["weight"] / mx, 3)) for p in pts])


@router.get("/map/links")
def map_links(min_risk: int = 0, station: str | None = None):
    """Station-to-station connections: people who show up in FIRs of both stations, and alerts that span both."""
    s = _snap()
    A, risk = s["A"], s["risk"]
    allowed = _station_filter(station, None, None)
    pair = defaultdict(lambda: dict(entities=[], alerts=[]))
    for eid, e in A.entities.items():
        sts = sorted({geo.station_id(A.fir_by_id[f]["station"]) for f in e.get("firs", []) if f in A.fir_by_id} - {None})
        r = risk.get(eid, {}).get("score", 0)
        if len(sts) < 2 or r < min_risk:
            continue
        for i in range(len(sts)):
            for j in range(i + 1, len(sts)):
                pair[(sts[i], sts[j])]["entities"].append(dict(id=eid, name=e["name"], risk=r))
    for a in s["alerts"]:
        sts = sorted(x["station"] for x in s["geo"]["alerts"][a["id"]]["stations"])
        for i in range(len(sts)):
            for j in range(i + 1, len(sts)):
                pair[(sts[i], sts[j])]["alerts"].append(a["id"])
    out = []
    for (a, b), v in pair.items():
        if allowed is not None and not ({a, b} & allowed):
            continue
        sa, sb = geo.STATIONS[a], geo.STATIONS[b]
        out.append(dict(a=a, b=b, a_name=sa["name"], b_name=sb["name"], a_pos=[sa["lat"], sa["lon"]], b_pos=[sb["lat"], sb["lon"]],
                        weight=len(v["entities"]) + len(v["alerts"]), entities=v["entities"], alerts=v["alerts"]))
    return sorted(out, key=lambda x: -x["weight"])


# ---------------------------------------------------------------- stations
@router.get("/stations")
def stations():
    return [{k: v for k, v in st.items() if k != "jurisdiction"} for st in geo.STATIONS.values()]


@router.get("/stations/{sid}")
def station_detail(sid: str):
    sid_ = geo.station_id(sid)
    if not sid_:
        raise HTTPException(404, "unknown station")
    s = _snap()
    A, risk = s["A"], s["risk"]
    row = next(r for r in map_stations(station=sid_))
    firs = [f for f in A.firs if geo.station_id(f["station"]) == sid_]
    people = {e["id"]: e for e in A.entities.values() if set(e.get("firs", [])) & {f["fir_id"] for f in firs}}
    top = sorted(people.values(), key=lambda e: -risk.get(e["id"], {}).get("score", 0))[:8]
    return dict(row, recent_firs=[dict(f, geo=s["geo"]["firs"][f["fir_id"]]) for f in sorted(firs, key=lambda f: f["date"], reverse=True)[:10]],
                alerts=[_alert_row(s, a) for a in s["alerts"] if any(x["station"] == sid_ and x["routed"] for x in s["geo"]["alerts"][a["id"]]["stations"])],
                top_people=[dict(id=e["id"], name=e["name"], risk=risk[e["id"]]["score"], level=risk[e["id"]]["level"],
                                 other_stations=[_name(x) for x in s["geo"]["entities"][e["id"]]["stations"] if x != sid_]) for e in top],
                links=map_links(station=sid_),
                inbox=dict(new=len(live.inbox(s, sid_, "new")), total=len(live.inbox(s, sid_))),
                sent=len(live.inbox(s, sid_, direction="out")))


@router.get("/alerts/geo")
def alerts_geo(station: str | None = None, type: str | None = None, severity: str | None = None, cross_station: bool = False):
    """Alerts with their station routing (which stations each concerns, and why)."""
    s = _snap()
    allowed = _station_filter(station, None, None)
    rows = []
    for a in s["alerts"]:
        g = s["geo"]["alerts"][a["id"]]
        if allowed is not None and not any(x["station"] in allowed for x in g["stations"]):
            continue
        if (type and a["type"] != type) or (severity and a["severity"] != severity) or (cross_station and not g["cross_station"]):
            continue
        rows.append(_alert_row(s, a))
    return rows


# ---------------------------------------------------------------- FIRs
class FirIn(BaseModel):
    station: str
    text: str
    date: str | None = None
    reporter: str | None = None


@router.get("/firs")
def list_firs(station: str | None = None, district: str | None = None, state: str | None = None, area: str | None = None,
              start: str | None = None, end: str | None = None, q: str | None = None, source: str | None = None, limit: int = Query(200, le=1000)):
    s = _snap()
    allowed = _station_filter(station, district, state)
    areas = _area_filter(area)
    ql = (q or "").lower().strip()
    rows = []
    for f in sorted(s["A"].firs, key=lambda f: (f["date"], f["fir_id"]), reverse=True):
        g = s["geo"]["firs"][f["fir_id"]]
        if allowed is not None and g["station"] not in allowed:
            continue
        if (areas and not (areas & set(g["areas"]))) or not _in_dates(f["date"], start, end):
            continue
        if source and f.get("source", "base") != source:
            continue
        if ql and ql not in f["text"].lower() and ql not in f["fir_id"].lower():
            continue
        rows.append(dict(f, source=f.get("source", "base"), geo=g))
    return rows[:limit]


@router.post("/firs")
def create_fir(body: FirIn):
    """File a FIR at a station. Re-runs the analysis, notifies the stations that need to know, and pushes live events."""
    try:
        return live.file_fir(S, body.station, body.text, body.date, body.reporter)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- notifications
class DispatchIn(BaseModel):
    from_station: str
    to_stations: list[str]
    kind: str = "share_intel"        # request_assistance | share_intel | bolo
    title: str
    body: str = ""
    severity: str = "medium"         # low | medium | high
    refs: dict | None = None         # e.g. {"fir_id": "FIR-007", "entities": [{"id": "E038", "name": "..."}], "alert_id": "A-03"}


class AckIn(BaseModel):
    station: str


class RespondIn(BaseModel):
    station: str
    text: str


@router.get("/notifications")
def notifications(station: str | None = None, status: str | None = None, direction: str = "in", kind: str | None = None,
                  from_station: str | None = None, limit: int = Query(100, le=500)):
    """A station's inbox (direction=in) or outbox (direction=out). No station = everything (command-centre view)."""
    if station and not geo.station_id(station):
        raise HTTPException(400, "unknown station")
    return live.inbox(_snap(), station, status, from_station, kind, limit, direction)


@router.post("/notifications")
def send_notification(body: DispatchIn):
    try:
        return live.dispatch(_snap(), body.from_station, body.to_stations, body.kind, body.title, body.body, body.severity, body.refs)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/notifications/{nid}/ack")
def ack_notification(nid: str, body: AckIn):
    try:
        return live.ack(_snap(), nid, body.station)
    except KeyError:
        raise HTTPException(404, "no such notification")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/notifications/{nid}/respond")
def respond_notification(nid: str, body: RespondIn):
    try:
        return live.respond(_snap(), nid, body.station, body.text)
    except KeyError:
        raise HTTPException(404, "no such notification")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/stream")
async def stream(request: Request, station: str | None = None, since: int = 0):
    """Server-Sent Events. With ?station= you get public events plus that station's notifications; without it, everything.
    Events: fir.created, graph.updated, notification, notification.ack. Reconnect with ?since=<last id> to replay missed ones."""
    sid = geo.station_id(station) if station else None
    if station and not sid:
        raise HTTPException(400, "unknown station")
    q = live.BUS.subscribe(sid, asyncio.get_running_loop())

    def fmt(ev):
        return f"id: {ev['seq']}\nevent: {ev['event']}\ndata: {json.dumps(dict(ev['data'], _ts=ev['ts'], _station=ev['station']), default=str)}\n\n"

    async def gen():
        try:
            yield f"retry: 2000\nevent: hello\ndata: {json.dumps(dict(station=sid, seq=live.BUS.seq))}\n\n"
            for ev in live.BUS.replay(sid, since):
                yield fmt(ev)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), 15)
                    yield fmt(ev)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            live.BUS.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- demo helpers
@router.get("/demo/next")
def demo_next():
    """Preview the FIR the demo button would file next (built from the data: a known high-risk person, a different station)."""
    return live.next_demo(_snap())


@router.post("/demo/fire")
def demo_fire():
    raise HTTPException(410, "demo FIRs are switched off")


@router.post("/demo/reset")
def demo_reset(request: Request):
    """Drop every live FIR and notification and rebuild from the base data."""
    live.reset()
    S.update(live.build([]))
    live.BUS.publish("graph.updated", dict(firs=len(S["A"].firs), entities=len(S["A"].entities), alerts=len(S["alerts"]), cause="reset"))
    return dict(status="reset", firs=len(S["A"].firs))


# ---------------------------------------------------------------- AI map control
class CustomAlertIn(BaseModel):
    station: str
    title: str
    note: str = ""
    severity: str = "medium"
    entities: list[str] = []
    firs: list[str] = []
    to_stations: list[str] = []


@router.post("/alerts/custom")
def raise_custom_alert(body: CustomAlertIn):
    try:
        a = live.raise_alert(S, body.station, body.title, body.note, body.severity, body.entities, body.firs, body.to_stations)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _alert_row(_snap(), a)


@router.delete("/alerts/custom/{aid}")
def withdraw_custom_alert(aid: str, station: str):
    try:
        live.withdraw_alert(S, aid, station)
    except KeyError:
        raise HTTPException(404, f"no custom alert {aid}")
    except ValueError as e:
        raise HTTPException(403, str(e))
    return dict(ok=True)


class MapAskIn(BaseModel):
    message: str
    session_id: str = "map"


@router.post("/map/ask")
def map_ask(body: MapAskIn):
    """Natural language -> validated map commands (fly, filter, layers, heat, camera, tour, highlight, fit).
    Questions about the case records go to the chatbot and its answer is turned into highlight/fit commands."""
    import mapai
    return mapai.ask(_snap(), body.session_id, body.message)
