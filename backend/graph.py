"""Unified typed evidence graph + programmatic metrics (no LLM involvement).

Every edge carries: etype, source (FIR | CDR | TXN), evidence (list of record ids), plus aggregates.
Person projection weight  w = calls + 3*transfers + 2*fir_relations   (documented, deterministic).
"""
import math
from collections import defaultdict
import networkx as nx
import pandas as pd

W_CALL, W_TXN, W_FIR = 1, 3, 2


def _ts(x):
    return None if x is None else pd.Timestamp(x)


def build_graph(A, start=None, end=None):
    key = (str(start), str(end))
    if key in A._graphs:
        return A._graphs[key]
    start, end = _ts(start), _ts(end)
    G = nx.MultiGraph()
    ents = A.entities
    for eid, e in ents.items():
        G.add_node(eid, type="person", label=e["name"], role=e["role"], aliases=e["aliases"], phones=e["phones"])

    def ok(ts):
        return (start is None or ts >= start) and (end is None or ts <= end)

    # --- calls (aggregated per pair) -------------------------------------------------
    agg = defaultdict(lambda: dict(ids=[], sec=0, first=None, last=None))
    for r in A.cdr.itertuples():
        if not ok(r.ts):
            continue
        a = r.caller_ent or f"ph:{r.caller}"
        b = r.receiver_ent or f"ph:{r.receiver}"
        if a == b:
            continue
        k = tuple(sorted((a, b)))
        d = agg[k]
        d["ids"].append(r.call_id)
        d["sec"] += int(r.duration_sec)
        d["first"] = r.ts if d["first"] is None or r.ts < d["first"] else d["first"]
        d["last"] = r.ts if d["last"] is None or r.ts > d["last"] else d["last"]
    for (a, b), d in agg.items():
        for n in (a, b):
            if n.startswith("ph:") and n not in G:
                G.add_node(n, type="phone", label=n[3:], status="unidentified")
        G.add_edge(a, b, etype="call", source="CDR", evidence=d["ids"], count=len(d["ids"]), seconds=d["sec"],
                   first=str(d["first"]), last=str(d["last"]), label=f"{len(d['ids'])} calls")

    # --- transfers (aggregated per directed pair) -------------------------------------
    tagg = defaultdict(lambda: dict(ids=[], amt=0, first=None, last=None))
    for r in A.tx.itertuples():
        if not ok(r.ts) or r.sender_ent == r.receiver_ent:
            continue
        d = tagg[(r.sender_ent, r.receiver_ent)]
        d["ids"].append(r.txn_id)
        d["amt"] += int(r.amount_inr)
        d["first"] = r.ts if d["first"] is None or r.ts < d["first"] else d["first"]
        d["last"] = r.ts if d["last"] is None or r.ts > d["last"] else d["last"]
    for (s, t), d in tagg.items():
        G.add_edge(s, t, etype="transfer", source="TXN", evidence=d["ids"], count=len(d["ids"]), amount=d["amt"],
                   src=s, dst=t, first=str(d["first"]), last=str(d["last"]), label=f"₹{d['amt']:,}")

    # --- FIR-derived edges -------------------------------------------------------------
    R = A.R
    fir_rel = defaultdict(lambda: dict(ids=[], rel=set()))
    for e in A.extracted:
        if not ok(pd.Timestamp(e["date"])):
            continue
        for rel in e["relations"]:
            a = R.mention_entity.get(f"{e['fir_id']}#{rel['a']}")
            b = R.mention_entity.get(f"{e['fir_id']}#{rel['b']}")
            if a and b and a != b:
                d = fir_rel[tuple(sorted((a, b)))]
                d["ids"].append(e["fir_id"])
                d["rel"].add(rel["relation"])
        for m in e["mentions"]:
            eid = R.mention_entity.get(f"{e['fir_id']}#{m['idx']}")
            if not eid:
                continue
            if m.get("org"):
                n = f"org:{m['org']}"
                G.add_node(n, type="org", label=m["org"])
                _once(G, eid, n, "works_with", "FIR", e["fir_id"], "operates through")
            if m.get("plate"):
                n = f"veh:{m['plate']}"
                G.add_node(n, type="vehicle", label=f"{m['plate']}" + (f" ({m['vehicle_desc']})" if m.get("vehicle_desc") else ""))
                _once(G, eid, n, "uses_vehicle", "FIR", e["fir_id"], "vehicle")
            if m.get("location") and m["role"] != "victim":
                n = f"loc:{m['location']}"
                G.add_node(n, type="location", label=m["location"])
                _once(G, eid, n, "frequents", "FIR", e["fir_id"], "frequents")
    for (a, b), d in fir_rel.items():
        G.add_edge(a, b, etype="associate", source="FIR", evidence=sorted(set(d["ids"])), count=len(set(d["ids"])),
                   relation=", ".join(sorted(d["rel"])), label=", ".join(sorted(d["rel"])))

    # --- phones: owner link (stated/inferred) and shared phones ------------------------
    for ph, eid in R.phone_owner.items():
        if eid not in ents:
            continue
        info = R.entities[eid]["phone_evidence"].get(ph, {})
        n = f"ph:{ph}"
        G.add_node(n, type="phone", label=ph, status="identified")
        G.add_edge(eid, n, etype="uses_phone", source="FIR", evidence=[info.get("fir")], confidence=info.get("confidence"),
                   rule=info.get("rule"), label="uses")
    for ph, uses in R.shared_phones.items():
        n = f"ph:{ph}"
        G.add_node(n, type="phone", label=ph, status="shared")
        for u in uses:
            if u["entity"]:
                G.add_edge(u["entity"], n, etype="reported_use", source="FIR", evidence=[u["fir_id"]], label="reported use (shared)")
    A._graphs[key] = G
    return G


def _once(G, a, b, etype, source, fir, label):
    if G.has_edge(a, b):
        for k, d in G[a][b].items():
            if d.get("etype") == etype:
                if fir not in d["evidence"]:
                    d["evidence"].append(fir)
                return
    G.add_edge(a, b, etype=etype, source=source, evidence=[fir], label=label)


def person_projection(G):
    """Weighted undirected person-person graph used for all centrality / community maths."""
    P = nx.Graph()
    P.add_nodes_from(n for n, d in G.nodes(data=True) if d["type"] == "person")
    for a, b, d in G.edges(data=True):
        if a not in P or b not in P:
            continue
        w = {"call": W_CALL * d.get("count", 1), "transfer": W_TXN * d.get("count", 1), "associate": W_FIR * d.get("count", 1)}.get(d["etype"])
        if not w:
            continue
        if P.has_edge(a, b):
            P[a][b]["weight"] += w
            P[a][b]["types"].add(d["etype"])
        else:
            P.add_edge(a, b, weight=w, types={d["etype"]})
    for a, b, d in P.edges(data=True):
        d["dist"] = 1.0 / d["weight"]
    P.remove_nodes_from([n for n in list(P) if P.degree(n) == 0])
    return P


def compute_metrics(A, G):
    P = person_projection(G)
    if len(P) == 0:
        return dict(P=P, metrics={}, communities=[], top5=[])
    deg = nx.degree_centrality(P)
    btw = nx.betweenness_centrality(P, weight="dist", normalized=True)
    clo = nx.closeness_centrality(P, distance="dist", wf_improved=True)
    pr = nx.pagerank(P, weight="weight")
    strength = dict(P.degree(weight="weight"))

    # Louvain is seed-sensitive: run 20 seeds and keep the highest-modularity partition (deterministic)
    comms = max((nx.community.louvain_communities(P, weight="weight", seed=s) for s in range(20)),
                key=lambda c: nx.community.modularity(P, c, weight="weight"))
    comms = sorted([sorted(c) for c in comms], key=lambda c: (-len(c), c[0]))
    cid = {}
    for i, c in enumerate(comms, 1):
        for n in c:
            cid[n] = i

    mx = lambda d: (max(d.values()) or 1)
    comp = {}
    for n in P:
        comp[n] = (0.35 * btw[n] / mx(btw) + 0.25 * deg[n] / mx(deg) + 0.20 * pr[n] / mx(pr) + 0.20 * clo[n] / mx(clo))
    metrics = {}
    ranks = {}
    for name, d in (("degree", deg), ("betweenness", btw), ("closeness", clo), ("pagerank", pr), ("strength", strength)):
        for r, n in enumerate(sorted(d, key=lambda x: -d[x]), 1):
            ranks.setdefault(n, {})[name] = r
    for n in P:
        nb_comm = {cid[m] for m in P[n] if cid.get(m) != cid[n]}
        metrics[n] = dict(degree=round(deg[n], 4), betweenness=round(btw[n], 4), closeness=round(clo[n], 4),
                          pagerank=round(pr[n], 4), strength=int(strength[n]), score=round(comp[n], 4),
                          community=cid[n], cross_community_links=len(nb_comm), ranks=ranks[n],
                          neighbors=P.degree(n))

    # community summaries
    communities = []
    for i, c in enumerate(comms, 1):
        lead = max(c, key=lambda n: comp.get(n, 0))
        sub = P.subgraph(c)
        top3 = sorted(c, key=lambda n: -comp.get(n, 0))[:3]
        communities.append(dict(id=i, size=len(c), members=c, lead=lead, top=top3, label=f"Group {i} — led by {A.name(lead)}",
                                internal_edges=sub.number_of_edges(), density=round(nx.density(sub), 3) if len(c) > 1 else 0))

    # top 5 + programmatic reasons
    n_total = len(P)
    top = sorted(P, key=lambda n: -comp[n])[:5]
    top5 = []
    for n in top:
        m = metrics[n]
        edges = [(b, d) for _, b, d in G.edges(n, data=True)]
        calls = sum(d.get("count", 0) for _, d in edges if d["etype"] == "call")
        txns = sum(d.get("count", 0) for _, d in edges if d["etype"] == "transfer")
        amt = sum(d.get("amount", 0) for _, d in edges if d["etype"] == "transfer")
        reasons = []
        best = sorted(m["ranks"].items(), key=lambda kv: kv[1])[:3]
        label = {"degree": "has the most direct contacts", "betweenness": "is the link between otherwise separate people",
                 "closeness": "can reach everyone else the fastest", "pagerank": "is connected to other well-connected people",
                 "strength": "has the most calls, money and FIR links overall"}
        for k, r in best:
            reasons.append(f"#{r} of {n_total} people — {label[k]}")
        if m["cross_community_links"]:
            reasons.append(f"Connects to {m['cross_community_links']} other group{'' if m['cross_community_links'] == 1 else 's'}")
        reasons.append(f"{m['neighbors']} direct contacts; {calls} calls and {txns} transfers (₹{amt:,}) in the selected period")
        top5.append(dict(id=n, name=A.name(n), score=m["score"], community=m["community"], reasons=reasons, metrics=m))
    return dict(P=P, metrics=metrics, communities=communities, top5=top5)
