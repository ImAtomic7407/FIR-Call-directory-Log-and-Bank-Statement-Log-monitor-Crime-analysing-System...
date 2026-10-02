from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from analysis import Analysis
from graph import build_graph, compute_metrics
from patterns import run_all
from risk import risk_scores

app = FastAPI(title="Criminal Network Analysis")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
S = {}


def boot():
    # live FIRs filed at runtime (persisted in cache/live_state.json) are part of the dataset
    S.update(live.build(live.LIVE_FIRS))


import live
import geoapi
boot()
geoapi.attach(app, S)


@app.get("/health")
def health():
    A = S["A"]
    return dict(status="ok", firs=len(A.firs), calls=len(A.cdr), transactions=len(A.tx), entities=len(A.entities),
                alerts=len(S["alerts"]), period=[str(A.t_min), str(A.t_max)])


@app.post("/analyze")
def analyze():
    boot()
    return health()


def _node(G, M, R, n, d):
    m = M["metrics"].get(n, {})
    out = dict(id=n, label=d.get("label"), type=d["type"], role=d.get("role"), status=d.get("status"),
               community=m.get("community"), score=m.get("score"), risk=(R.get(n) or {}).get("score"))
    return out


@app.get("/graph")
def graph(start: str | None = None, end: str | None = None,
          types: str = "person,phone,vehicle,org,location", etypes: str = "call,transfer,associate,uses_phone,reported_use,uses_vehicle,works_with,frequents",
          community: int | None = None, min_risk: int = 0):
    A = S["A"]
    G = build_graph(A, start, end)
    M = compute_metrics(A, G) if (start or end) else S["M"]
    tset, eset = set(types.split(",")), set(etypes.split(","))
    risk = S["risk"]
    keep = {n for n, d in G.nodes(data=True) if d["type"] in tset}
    if community:
        keep = {n for n in keep if G.nodes[n]["type"] != "person" or M["metrics"].get(n, {}).get("community") == community}
    if min_risk:
        keep = {n for n in keep if G.nodes[n]["type"] != "person" or risk.get(n, {}).get("score", 0) >= min_risk}
    edges = []
    for i, (a, b, k, d) in enumerate(G.edges(keys=True, data=True)):
        if d["etype"] in eset and a in keep and b in keep:
            e = {x: v for x, v in d.items() if x not in ("src", "dst", "source")}
            e.update(id=f"{d['etype']}:{a}:{b}:{k}", source=d.get("src", a), target=d.get("dst", b), evidence_source=d.get("source"))
            edges.append(e)
    used = {e["source"] for e in edges} | {e["target"] for e in edges}
    nodes = [_node(G, M, risk, n, G.nodes[n]) for n in keep if n in used or G.nodes[n]["type"] == "person" and M["metrics"].get(n)]
    return dict(nodes=nodes, edges=edges, communities=M["communities"], period=[str(A.t_min), str(A.t_max)])


@app.get("/metrics")
def metrics():
    M, A = S["M"], S["A"]
    return dict(top5=M["top5"], communities=[dict(c, lead_name=A.name(c["lead"]), member_names=[A.name(m) for m in c["members"]]) for c in M["communities"]],
                method="degree, betweenness, closeness, PageRank via NetworkX on person-person graph; weight = calls + 3*transfers + 2*FIR links; composite = 0.35*betw + 0.25*deg + 0.20*PR + 0.20*close (each / max)",
                all={k: v for k, v in M["metrics"].items()})


@app.get("/alerts")
def alerts(type: str | None = None):
    return [a for a in S["alerts"] if not type or a["type"] == type]


@app.get("/entities")
def entities(q: str | None = None):
    A = S["A"]
    res = []
    for e in A.entities.values():
        hay = " ".join([e["name"], *e["aliases"], *e["phones"]]).lower()
        if not q or q.lower() in hay:
            res.append(dict(id=e["id"], name=e["name"], aliases=e["aliases"], role=e["role"], risk=S["risk"][e["id"]]["score"],
                            community=S["M"]["metrics"].get(e["id"], {}).get("community")))
    return sorted(res, key=lambda x: -x["risk"])


def _connections(G, eid):
    out = {}
    for _, b, d in G.edges(eid, data=True):
        if G.nodes[b]["type"] != "person":
            continue
        o = out.setdefault(b, dict(id=b, name=G.nodes[b]["label"], calls=0, transfers=0, amount=0, fir=[]))
        if d["etype"] == "call": o["calls"] += d["count"]
        elif d["etype"] == "transfer": o["transfers"] += d["count"]; o["amount"] += d["amount"]
        elif d["etype"] == "associate": o["fir"] += d["evidence"]; o["relation"] = d.get("relation")
    return sorted(out.values(), key=lambda o: -(o["calls"] + 3 * o["transfers"] + 2 * len(o["fir"])))


@app.get("/entity/{eid}")
def entity(eid: str):
    A, G, M = S["A"], S["G"], S["M"]
    e = A.entities.get(eid)
    if not e:
        raise HTTPException(404, "unknown entity")
    firs = [dict(fir_id=f, date=A.fir_by_id[f]["date"], station=A.fir_by_id[f]["station"], text=A.fir_by_id[f]["text"]) for f in e["firs"]]
    return dict(id=eid, name=e["name"], aliases=e["aliases"], role=e["role"], phones=[dict(number=p, **e["phone_evidence"][p]) for p in e["phones"]],
                accounts=e["accounts"], orgs=e["orgs"], vehicles=e["plates"], locations=e["locations"], firs=firs,
                resolution=dict(confidence=e["confidence"], links=[{k: l[k] for k in ("fir_id", "surface", "rule", "confidence", "note")} for l in e["links"]]),
                metrics=M["metrics"].get(eid), risk=S["risk"][eid], alerts=[a for a in S["alerts"] if eid in a["entities"]],
                connections=_connections(G, eid)[:12])


@app.get("/resolution")
def resolution():
    R, A = S["A"].R, S["A"]
    merged = [dict(id=e["id"], name=e["name"], aliases=e["aliases"], confidence=e["confidence"], mentions=len(e["links"]))
              for e in A.entities.values() if len(e["aliases"]) or len(e["links"]) > 1]
    return dict(entities=len(A.entities), merged=merged,
                unresolved=[dict(u, candidate_names=[A.name(c) for c in u["candidates"]], leading_name=A.name(u["leading_candidate"]) if u["leading_candidate"] else None) for u in R.unresolved],
                shared_phones={p: [dict(u, name=A.name(u["entity"]) if u["entity"] else None) for u in v] for p, v in R.shared_phones.items()},
                account_conflicts=A.account_conflicts)


@app.get("/timeline/{eid}")
def timeline(eid: str):
    A = S["A"]
    if eid not in A.entities:
        raise HTTPException(404)
    ev = []
    phones = set(A.entities[eid]["phones"])
    for r in A.cdr[(A.cdr.caller_ent == eid) | (A.cdr.receiver_ent == eid)].itertuples():
        other = r.receiver_ent if r.caller_ent == eid else r.caller_ent
        ev.append(dict(ts=str(r.ts), kind="call", id=r.call_id, text=f"{'Called' if r.caller_ent == eid else 'Called by'} {A.name(other) if other else (r.receiver if r.caller_ent == eid else r.caller)} ({r.duration_sec}s, {r.tower_location})"))
    for r in A.tx[(A.tx.sender_ent == eid) | (A.tx.receiver_ent == eid)].itertuples():
        out = r.sender_ent == eid
        ev.append(dict(ts=str(r.ts), kind="transfer", id=r.txn_id, text=f"{'Sent' if out else 'Received'} ₹{int(r.amount_inr):,} {'to' if out else 'from'} {A.name(r.receiver_ent if out else r.sender_ent)} ({r.mode})"))
    for f in A.entities[eid]["firs"]:
        ev.append(dict(ts=A.fir_by_id[f]["date"], kind="fir", id=f, text=f"Named in {f} ({A.fir_by_id[f]['station']})"))
    for a in S["alerts"]:
        if eid in a["entities"] and a["time"]["start"]:
            ev.append(dict(ts=a["time"]["start"], kind="alert", id=a["id"], text=a["title"]))
    return sorted(ev, key=lambda x: x["ts"])


@app.get("/record/{rid}")
def record(rid: str):
    """Look up any cited id (FIR-xxx / Cxxxx / Txxxx) so the UI can show evidence."""
    A = S["A"]
    if rid.startswith("FIR-") and rid in A.fir_by_id:
        return dict(kind="fir", **A.fir_by_id[rid])
    if rid.startswith("C"):
        r = A.cdr[A.cdr.call_id == rid]
        if len(r):
            r = r.iloc[0]
            return dict(kind="call", id=rid, caller=r.caller, caller_name=A.name(r.caller_ent) if r.caller_ent else None, receiver=r.receiver,
                        receiver_name=A.name(r.receiver_ent) if r.receiver_ent else None, timestamp=r.timestamp, duration_sec=int(r.duration_sec), tower=f"{r.tower_id} {r.tower_location}")
    if rid.startswith("T"):
        r = A.tx[A.tx.txn_id == rid]
        if len(r):
            r = r.iloc[0]
            return dict(kind="transfer", id=rid, sender=A.name(r.sender_ent), receiver=A.name(r.receiver_ent), amount_inr=int(r.amount_inr), when=f"{r.date} {r.time}", mode=r["mode"],
                        sender_account=r.sender_account, receiver_account=r.receiver_account, names_as_written=[r.sender, r.receiver])
    raise HTTPException(404, "record not found")


# ---------------------------------------------------------------- chatbot
from pydantic import BaseModel
import chat as chatmod
import llm as llmmod


class ChatIn(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/chat")
def chat(body: ChatIn):
    return chatmod.handle(S, body.session_id, body.message)


@app.get("/llm/status")
def llm_status():
    return llmmod.status()


from fastapi.responses import Response
import report as reportmod


@app.get("/report.pdf")
def report_all():
    return Response(reportmod.build_pdf(S), media_type="application/pdf")


@app.get("/report/{eid}.pdf")
def report_entity(eid: str):
    if eid not in S["A"].entities:
        raise HTTPException(404, "unknown entity")
    return Response(reportmod.build_pdf(S, eid), media_type="application/pdf")
