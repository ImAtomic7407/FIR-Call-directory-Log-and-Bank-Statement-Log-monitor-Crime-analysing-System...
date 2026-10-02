"""AI control of the map view.

  text --(LLM, or keyword rules when it is offline)--> a few small commands --(validated here)--> resolved commands
         the frontend simply executes: fly, filters, layers, heat, camera, tour, highlight, fit, select.

Like the chatbot, the LLM only chooses; Python resolves every name to a real station / area / person / alert id with
real coordinates, and anything it cannot resolve is dropped. Questions about the case records are handed to the chatbot
and the answer's people / alerts / FIRs are turned into map commands, so the map follows the conversation.
"""
import re

import geo
import llm
import chat as chatmod

LAYERS = ["firs", "towers", "entities", "alerts", "links", "zones", "heat", "buildings"]
HEAT = ["calls", "night_calls", "firs", "alerts", "risk"]
ALERT_TYPES = ["burst_calling", "circular_transfer", "layering", "shared_phone", "shared_vehicle", "sudden_contact", "co_location"]
FILTER_KEYS = {"station", "district", "state", "area", "min_risk", "start", "end", "alert_type", "severity", "cross_station", "q", "source"}

MAP_WORDS = re.compile(r"\b(map|fly|zoom|pan|tilt|3d|2d|top[- ]?down|bird|orbit|rotate|spin|heat\w*|layer|station|thana|jurisdiction|area|tour|patrol|"
                       r"go to|take me|jump to|focus|centre|center|reset view|filter|only|hide|show me|where|kahan|dikhao|le chalo|nearby|region|zone|"
                       r"cross[- ]station|live fir)\b", re.I)

TOOLS_DOC = """Commands (return a list, usually 1-3):
 {"op":"fly","target":"<station, area, person, ALR-xx or FIR-xxx>"}
 {"op":"filter","set":{"station":"<name>","district":"..","state":"Delhi|Uttar Pradesh|Haryana","area":"..","min_risk":0-100,"alert_type":"%s","severity":"high|medium|low","cross_station":true,"source":"base|live","q":"text","start":"YYYY-MM-DD","end":"YYYY-MM-DD"}}
 {"op":"filter","reset":true}
 {"op":"layers","show":[..],"hide":[..]}      layers: %s
 {"op":"heat","metric":"%s|off"}
 {"op":"camera","mode":"3d|top|orbit|stop"}
 {"op":"tour","what":"high_alerts|cross_station|stations"}
Set "ask_records":true (and no commands) if the user asks about people, calls, money or connections rather than the map.""" % (
    "|".join(ALERT_TYPES), ",".join(LAYERS), "|".join(HEAT))


# ---------------------------------------------------------------- resolving names
def _entity_pos(S, eid):
    g = S["geo"]["entities"].get(eid)
    if not g:
        return None
    at = (g["last_seen"] or {}).get("area") or g["home_area"]
    return (geo.AREAS[at]["lat"], geo.AREAS[at]["lon"]) if at in geo.AREAS else None


def resolve(S, text):
    """Free text -> {kind, id, name, lat, lon} or None. Station, area, FIR, alert, person (in that order of specificity)."""
    t = (text or "").strip()
    if not t:
        return None
    m = re.search(r"\bALR-\d{2}\b", t, re.I)
    if m:
        gid = m.group(0).upper()
        g = S["geo"]["alerts"].get(gid)
        if g and g["lat"] is not None:
            return dict(kind="alert", id=gid, name=gid, lat=g["lat"], lon=g["lon"])
    m = re.search(r"\bFIR-\d{3}\b", t, re.I)
    if m:
        fid = m.group(0).upper()
        g = S["geo"]["firs"].get(fid)
        if g:
            return dict(kind="fir", id=fid, name=fid, lat=g["lat"], lon=g["lon"])
    sid = geo.station_id(t)
    if sid:
        st = geo.STATIONS[sid]
        return dict(kind="station", id=sid, name=st["name"], lat=st["lat"], lon=st["lon"])
    aid = geo.area_id(t)
    if aid:
        a = geo.AREAS[aid]
        return dict(kind="area", id=aid, name=a["name"], lat=a["lat"], lon=a["lon"])
    A = S["A"]
    found, _, _ = chatmod.find_entities(A, t)
    for e in found:
        p = _entity_pos(S, e)
        if p:
            return dict(kind="entity", id=e, name=A.name(e), lat=p[0], lon=p[1])
    return None


def _station_from_text(t):
    """A station named anywhere in the sentence ('okhla', 'sector 62', 'karol bagh ps')."""
    for sid, st in geo.STATIONS.items():
        if re.search(rf"\b{re.escape(st['short'].lower())}\b", t):
            return sid
    return None


def _norm_filters(S, raw):
    """Keep only filters that name something real."""
    out = {}
    for k, v in (raw or {}).items():
        if k not in FILTER_KEYS or v in (None, ""):
            continue
        if k == "station":
            sid = geo.station_id(str(v)) or _station_from_text(str(v).lower())
            if sid:
                out[k] = sid
        elif k == "area":
            aid = geo.area_id(str(v))
            if aid:
                out[k] = aid
        elif k == "district":
            d = next((d for d in {s["district"] for s in geo.STATIONS.values()} if d.lower() == str(v).lower()), None)
            if d:
                out[k] = d
        elif k == "state":
            s = next((s for s in {x["state"] for x in geo.STATIONS.values()} if s.lower() == str(v).lower()), None)
            if s:
                out[k] = s
        elif k == "min_risk":
            try:
                out[k] = max(0, min(100, int(v)))
            except (TypeError, ValueError):
                pass
        elif k == "alert_type":
            if str(v) in ALERT_TYPES:
                out[k] = str(v)
        elif k == "severity":
            if str(v).lower() in ("high", "medium", "low"):
                out[k] = str(v).lower()
        elif k == "source":
            if str(v) in ("base", "live"):
                out[k] = str(v)
        elif k == "cross_station":
            out[k] = bool(v) and str(v).lower() != "false"
        elif k in ("start", "end"):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)):
                out[k] = str(v)
        elif k == "q":
            out[k] = str(v)[:60]
    return out


def _tour(S, what):
    stops = []
    if what == "stations":
        order = sorted(geo.STATIONS.values(), key=lambda s: -s["lat"])
        stops = [dict(kind="station", id=s["id"], label=s["name"], lat=s["lat"], lon=s["lon"]) for s in order]
    else:
        for a in S["alerts"]:
            g = S["geo"]["alerts"][a["id"]]
            if g["lat"] is None:
                continue
            if what == "cross_station" and not g["cross_station"]:
                continue
            if what == "high_alerts" and a["severity"] != "high":
                continue
            stops.append(dict(kind="alert", id=a["id"], label=a["title"], lat=g["lat"], lon=g["lon"]))
    return dict(op="tour", what=what, stops=stops[:14], dwell_ms=4500) if stops else None


def validate(S, cmds):
    out = []
    for c in cmds or []:
        if not isinstance(c, dict):
            continue
        op = c.get("op")
        if op == "fly":
            r = resolve(S, str(c.get("target", "")))
            if r:
                out.append(dict(op="fly", target=r, zoom=c.get("zoom") if isinstance(c.get("zoom"), (int, float)) else None))
        elif op == "filter":
            if c.get("reset"):
                out.append(dict(op="filter", reset=True))
            else:
                s = _norm_filters(S, c.get("set"))
                if s:
                    out.append(dict(op="filter", set=s))
        elif op == "layers":
            show = [x for x in c.get("show") or [] if x in LAYERS]
            hide = [x for x in c.get("hide") or [] if x in LAYERS]
            if show or hide:
                out.append(dict(op="layers", show=show, hide=hide))
        elif op == "heat":
            if c.get("metric") in HEAT + ["off"]:
                out.append(dict(op="heat", metric=c["metric"]))
        elif op == "camera":
            if c.get("mode") in ("3d", "top", "orbit", "stop"):
                out.append(dict(op="camera", mode=c["mode"]))
        elif op == "tour":
            if c.get("what") in ("high_alerts", "cross_station", "stations"):
                t = _tour(S, c["what"])
                if t:
                    out.append(t)
        elif op in ("highlight", "fit", "select"):
            out.append(c)
    return out


# ---------------------------------------------------------------- rules (offline fallback)
def rule_commands(S, text):
    t = text.lower()
    cmds = []
    if re.search(r"\b(reset|clear|saaf|sab dikhao|everything)\b.*\b(filter|view|map)?|\bshow all\b", t) and re.search(r"\b(reset|clear|saaf|show all)\b", t):
        cmds.append(dict(op="filter", reset=True))
    if re.search(r"\btour|patrol|walk me through|one by one|sab alerts\b", t):
        what = "cross_station" if re.search(r"cross|between stations", t) else "stations" if re.search(r"station|thana", t) and not re.search(r"alert", t) else "high_alerts"
        cmds.append(dict(op="tour", what=what))
    if re.search(r"\b(orbit|rotate|spin|ghumao|revolve)\b", t):
        cmds.append(dict(op="camera", mode="orbit"))
    elif re.search(r"\b(stop (rotat|orbit|spin)\w*)\b", t):
        cmds.append(dict(op="camera", mode="stop"))
    elif re.search(r"\b(3d|tilt|perspective|angle)\b", t):
        cmds.append(dict(op="camera", mode="3d"))
    elif re.search(r"\b(top[- ]?down|2d|flat|bird'?s?[- ]?eye|overhead)\b", t):
        cmds.append(dict(op="camera", mode="top"))
    if re.search(r"\bheat", t):
        metric = ("night_calls" if re.search(r"night|raat", t) else "firs" if re.search(r"\bfirs?\b|complaint", t) else "alerts" if re.search(r"alert", t)
                  else "risk" if re.search(r"risk|danger", t) else "calls")
        cmds.append(dict(op="heat", metric="off" if re.search(r"\b(off|hide|remove|band)\b", t) else metric))
    lay = dict(firs=r"\bfirs?\b", towers=r"tower", entities=r"people|persons|suspects", alerts=r"alerts?", links=r"links?|connections?|arcs?|lines?",
               zones=r"zones?|jurisdictions?|boundar\w+|areas?", buildings=r"buildings?")
    if re.search(r"\b(hide|remove|turn off|band)\b", t):
        hide = [k for k, rx in lay.items() if re.search(rx, t)]
        if hide and not re.search(r"heat", t):
            cmds.append(dict(op="layers", hide=hide, show=[]))
    elif re.search(r"\b(show|turn on|enable|add)\b", t) and re.search(r"\blayers?\b|towers?|links?|arcs?|zones?|buildings?", t):
        show = [k for k, rx in lay.items() if re.search(rx, t)]
        if show:
            cmds.append(dict(op="layers", show=show, hide=[]))
    f = {}
    if re.search(r"high[- ]?risk|khatarnak|dangerous", t):
        f["min_risk"] = 60
    if re.search(r"cross[- ]station|multiple stations|more than one station|alag alag thane", t):
        f["cross_station"] = True
    if re.search(r"\blive (firs?|records?)|new firs?|just filed\b", t):
        f["source"] = "live"
    sv = re.search(r"\b(high|medium|low)[- ]severity|severity (high|medium|low)", t)
    if sv:
        f["severity"] = sv.group(1) or sv.group(2)
    for ty in ALERT_TYPES:
        if ty.replace("_", " ") in t or ty.split("_")[0] in t and ty in ("burst_calling", "co_location"):
            f["alert_type"] = ty
    st = re.search(r"(delhi|uttar pradesh|haryana)", t)
    if st and re.search(r"\b(only|in|within|filter)\b", t):
        f["state"] = st.group(1)
    mo = re.search(r"\b(july|august|september)\b", t)
    if mo:
        n = {"july": 7, "august": 8, "september": 9}[mo.group(1)]
        f["start"], f["end"] = f"2026-{n:02d}-01", f"2026-{n:02d}-{31 if n != 9 else 30}"
    if re.search(r"\b(only|filter|just)\b", t):
        sid = _station_from_text(t)
        if sid:
            f["station"] = sid
    if f:
        cmds.append(dict(op="filter", set=f))
    if not any(c["op"] in ("tour",) for c in cmds):
        tgt = resolve(S, text)
        if tgt and (re.search(r"\b(fly|zoom|go to|take me|jump|focus|show|where|kahan|dikhao|le chalo|centre|center|map|locate|find)\b", t) or not cmds):
            cmds.insert(0, dict(op="fly", target=tgt["id"] if tgt["kind"] in ("station", "area", "alert", "fir") else tgt["name"]))
    return cmds


# ---------------------------------------------------------------- from a chat answer to the map
def commands_from_chat(S, res):
    """The chatbot's highlight / evidence turned into map commands, so the map follows the conversation."""
    pts, ids = [], []
    for n in (res.get("highlight") or {}).get("nodes") or []:
        if re.fullmatch(r"E\d+", str(n)):
            p = _entity_pos(S, n)
            if p:
                pts.append(p); ids.append(n)
    for aid in (res.get("evidence") or {}).get("alerts", []):
        g = S["geo"]["alerts"].get(aid)
        if g and g["lat"] is not None:
            pts.append((g["lat"], g["lon"])); ids.append(aid)
    if not pts:
        for fid in (res.get("evidence") or {}).get("firs", [])[:6]:
            g = S["geo"]["firs"].get(fid)
            if g:
                pts.append((g["lat"], g["lon"])); ids.append(fid)
    if not pts:
        return []
    out = [dict(op="highlight", ids=ids[:20]), dict(op="fit", points=[list(p) for p in pts[:20]])]
    return out


# ---------------------------------------------------------------- entry point
def ask(S, sid, text):
    via, cmds, ask_records = "rules", None, None
    if llm.enabled():
        sysmsg = ("You control a 3D crime map for a police analyst. Turn the user's request (English/Hindi/Hinglish) into map commands. "
                  "Reply with JSON only: {\"commands\":[...],\"ask_records\":false}.\n" + TOOLS_DOC +
                  "\nStations: " + ", ".join(s["short"] for s in geo.STATIONS.values()) +
                  "\nAreas: " + ", ".join(a["name"] for a in geo.AREAS.values()))
        out = llm.complete_json([dict(role="system", content=sysmsg), dict(role="user", content=text)], max_tokens=260)
        if isinstance(out, dict):
            ask_records = bool(out.get("ask_records"))
            cmds = validate(S, out.get("commands"))
            # small models invent filters the user never asked for: only keep a filter key if the text backs it up
            said = {k for c in validate(S, rule_commands(S, text)) if c["op"] == "filter" for k in c.get("set", {})}
            for c in list(cmds or []):
                if c["op"] == "filter" and c.get("set"):
                    c["set"] = {k: v for k, v in c["set"].items() if k in said or k in ("station", "district", "area", "state")}
                    if not c["set"]:
                        cmds.remove(c)
            if cmds or ask_records:
                via = "llm"
                if cmds and not ask_records:  # small models drop qualifiers ("high risk"): keep the rule-based filters it missed
                    have = {k for c in cmds if c["op"] == "filter" for k in c.get("set", {})}
                    for c in validate(S, rule_commands(S, text)):
                        if c["op"] == "filter" and c.get("set") and not set(c["set"]) <= have:
                            cmds.append(dict(op="filter", set={k: v for k, v in c["set"].items() if k not in have}))
    if via != "llm":
        cmds = validate(S, rule_commands(S, text))
        ask_records = not cmds and not MAP_WORDS.search(text)
        if not cmds and not ask_records:
            ask_records = True  # nothing recognised as a map instruction: let the chatbot try
    answer, chat_res = None, None
    if ask_records or not cmds:
        chat_res = chatmod.handle(S, sid, text)
        answer = chat_res["answer"]
        cmds = (cmds or []) + commands_from_chat(S, chat_res)
    else:
        answer = describe(cmds)
    return dict(answer=answer, commands=cmds, router=via, chat=chat_res)


def describe(cmds):
    bits = []
    for c in cmds:
        op = c["op"]
        if op == "fly":
            bits.append(f"Flying to {c['target']['name']}")
        elif op == "filter":
            bits.append("Cleared the map filters" if c.get("reset") else "Filtering: " + ", ".join(f"{k.replace('_', ' ')} = {v}" for k, v in c["set"].items()))
        elif op == "layers":
            bits.append((("Showing " + ", ".join(c["show"])) if c["show"] else "") + ((" Hiding " + ", ".join(c["hide"])) if c["hide"] else ""))
        elif op == "heat":
            bits.append("Heat layer off" if c["metric"] == "off" else f"Heat layer: {c['metric'].replace('_', ' ')}")
        elif op == "camera":
            bits.append({"3d": "Tilted into 3D", "top": "Top-down view", "orbit": "Slowly rotating", "stop": "Stopped rotating"}[c["mode"]])
        elif op == "tour":
            bits.append(f"Touring {len(c['stops'])} stops")
    return ". ".join(b.strip() for b in bits if b.strip()) + "." if bits else "Done."
