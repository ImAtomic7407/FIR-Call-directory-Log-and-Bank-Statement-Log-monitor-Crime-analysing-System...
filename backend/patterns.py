"""Five rule-based suspicious-pattern detectors. Pure Python/pandas/NetworkX; every alert lists its evidence ids.

Alert: {id, type, severity, title, summary, entities[], evidence{calls,txns,firs}, time{start,end}, details}
"""
from collections import defaultdict, Counter
from itertools import combinations
import networkx as nx
import pandas as pd
from graph import build_graph, compute_metrics

BURST_WINDOW_MIN, BURST_MIN_CALLS = 30, 10
CYCLE_MIN_AMOUNT, CYCLE_MAX_DAYS, CYCLE_AMT_TOL = 25_000, 7, 0.25
COLOC_WINDOW_MIN, COLOC_MIN_PEOPLE = 30, 3
BASELINE_FRAC = 0.65


def _rupees(x):
    return f"₹{int(x):,}"


def _alert(type_, severity, title, summary, entities, calls=(), txns=(), firs=(), start=None, end=None, **details):
    return dict(type=type_, severity=severity, title=title, summary=summary, entities=sorted(set(e for e in entities if e)),
                evidence=dict(calls=list(calls), txns=list(txns), firs=sorted(set(firs))),
                time=dict(start=str(start) if start is not None else None, end=str(end) if end is not None else None), details=details)


# 1 ---------------------------------------------------------------------------------
def burst_calling(A):
    out = []
    cdr = A.cdr.sort_values("ts")
    for phone, g in cdr.groupby("caller"):
        ts, ids = list(g.ts), list(g.call_id)
        n, i, episodes = len(ts), 0, []
        for i in range(n):
            j = i
            while j + 1 < n and (ts[j + 1] - ts[i]).total_seconds() <= BURST_WINDOW_MIN * 60:
                j += 1
            if j - i + 1 >= BURST_MIN_CALLS:
                if episodes and i <= episodes[-1][1]:
                    episodes[-1][1] = max(episodes[-1][1], j)
                else:
                    episodes.append([i, j])
        days = max((ts[-1] - ts[0]).days, 1) if n else 1
        for a, b in episodes:
            sub = g.iloc[a:b + 1]
            owner = A.R.phone_owner.get(phone)
            base = round(n / 75, 1)
            recv = sub.receiver.nunique()
            out.append(_alert("burst_calling", "high" if b - a + 1 >= 15 else "medium",
                              f"Sudden burst of calls from {A.name(owner) if owner else phone}",
                              f"{b - a + 1} outgoing calls from {phone} within {int((ts[b] - ts[a]).total_seconds() // 60)} minutes "
                              f"({ts[a]:%d %b %H:%M}–{ts[b]:%H:%M}) to {recv} distinct numbers; this phone's average is ~{base}/day.",
                              [owner] + [A.R.phone_owner.get(r) for r in sub.receiver], calls=ids[a:b + 1], start=ts[a], end=ts[b],
                              phone=phone, call_count=b - a + 1, distinct_receivers=int(recv), towers=sorted(set(sub.tower_id))))
    return out


# 2 ---------------------------------------------------------------------------------
def circular_transfers(A):
    tx = A.tx[(A.tx.amount_inr >= CYCLE_MIN_AMOUNT) & (A.tx.sender_ent != A.tx.receiver_ent)].sort_values("ts")
    D = nx.DiGraph()
    by_edge = defaultdict(list)
    for r in tx.itertuples():
        D.add_edge(r.sender_ent, r.receiver_ent)
        by_edge[(r.sender_ent, r.receiver_ent)].append(r)
    out, seen = [], set()
    for cyc in nx.simple_cycles(D, length_bound=5):
        if len(cyc) < 3:
            continue
        k = len(cyc)
        best = None
        for rot in range(k):  # try each node as the origin of the money
            order = cyc[rot:] + cyc[:rot]
            edges = [(order[i], order[(i + 1) % k]) for i in range(k)]
            chain = _chain(by_edge, edges, 0, None, None, [])
            if chain and (best is None or chain[-1].ts - chain[0].ts < best[-1].ts - best[0].ts):
                best = chain
        if not best:
            continue
        ids = tuple(sorted(t.txn_id for t in best))
        if ids in seen:
            continue
        seen.add(ids)
        names = [A.name(best[0].sender_ent)] + [A.name(t.receiver_ent) for t in best]
        amt0, amtn = best[0].amount_inr, best[-1].amount_inr
        out.append(_alert("circular_transfer", "high",
                          f"{k}-hop circular money flow",
                          f"{' → '.join(names)}: {_rupees(amt0)} left the origin and {_rupees(amtn)} came back within "
                          f"{(best[-1].ts - best[0].ts).days or 1} day(s) after passing through {k - 1} intermediaries "
                          f"(~{(1 - amtn / amt0) * 100:.1f}% skimmed). Money going in a circle like this is a common way to hide its origin.",
                          [t.sender_ent for t in best], txns=[t.txn_id for t in best], start=best[0].ts, end=best[-1].ts,
                          hops=k, origin_amount=int(amt0), return_amount=int(amtn)))
    return out


def _chain(by_edge, edges, i, prev, first, acc):
    if i == len(edges):
        return acc
    for t in by_edge[edges[i]]:
        if prev is not None and not (t.ts >= prev.ts and (t.ts - first.ts).days <= CYCLE_MAX_DAYS):
            continue
        if first is not None and abs(t.amount_inr - first.amount_inr) > CYCLE_AMT_TOL * first.amount_inr:
            continue
        r = _chain(by_edge, edges, i + 1, t, first or t, acc + [t])
        if r:
            return r
    return None


def layering(A):
    """One account splits money to >=3 accounts in a short time; they forward to a common receiver."""
    out = []
    tx = A.tx[A.tx.sender_ent != A.tx.receiver_ent].sort_values("ts")
    for s, g in tx[tx.amount_inr >= 50_000].groupby("sender_ent"):
        rows = list(g.itertuples())
        for i, r0 in enumerate(rows):
            win = [r for r in rows[i:] if (r.ts - r0.ts).total_seconds() <= 72 * 3600 and abs(r.amount_inr - r0.amount_inr) <= 0.2 * r0.amount_inr]
            recvs = {r.receiver_ent for r in win}
            if len(recvs) < 3:
                continue
            fwd = tx[(tx.sender_ent.isin(recvs)) & (tx.ts >= r0.ts) & ((tx.ts - r0.ts).dt.days <= 10)]
            tgt = Counter(fwd.receiver_ent)
            for t, c in tgt.items():
                got = set(fwd[fwd.receiver_ent == t].sender_ent) & recvs
                if t != s and len(got) >= 3:
                    f = fwd[(fwd.receiver_ent == t) & (fwd.sender_ent.isin(got))]
                    ids = [r.txn_id for r in win if r.receiver_ent in got] + list(f.txn_id)
                    out.append(_alert("layering", "high", f"Layered transfers via {len(got)} intermediaries",
                                      f"{A.name(s)} split {_rupees(sum(r.amount_inr for r in win if r.receiver_ent in got))} across {len(got)} accounts "
                                      f"({', '.join(A.name(x) for x in sorted(got))}) within 72h; they forwarded {_rupees(f.amount_inr.sum())} to {A.name(t)}.",
                                      [s, t, *got], txns=ids, start=r0.ts, end=f.ts.max(), source=s, target=t, intermediaries=sorted(got)))
                    return _dedupe(out)
    return _dedupe(out)


def _dedupe(alerts):
    seen, res = set(), []
    for a in alerts:
        k = tuple(sorted(a["evidence"]["txns"]))
        if k not in seen:
            seen.add(k)
            res.append(a)
    return res


# 3 ---------------------------------------------------------------------------------
def shared_identity(A):
    out = []
    R = A.R
    for ph, uses in R.shared_phones.items():
        ents = {u["entity"] for u in uses if u["entity"]}
        calls = A.cdr[(A.cdr.caller == ph) | (A.cdr.receiver == ph)]
        who = sorted({(u["surface"], u["fir_id"]) for u in uses})
        out.append(_alert("shared_phone", "high" if len(ents) >= 3 else "medium", f"One phone linked to {len(ents)} different identities",
                          f"Phone {ph} is attributed to {', '.join(A.name(e) for e in sorted(ents))} in "
                          f"{', '.join(sorted({u['fir_id'] for u in uses}))}. The identities were deliberately NOT merged: "
                          f"likely a shared or throwaway SIM card. {len(calls)} call records involve this number.",
                          ents, calls=list(calls.call_id), firs=[u["fir_id"] for u in uses], phone=ph, attributions=[dict(name=n, fir_id=f) for n, f in who]))
    return out


def shared_vehicle(A, comm_of):
    out, byplate = [], defaultdict(set)
    for e in A.entities.values():
        for p in e["plates"]:
            byplate[p].add(e["id"])
    for plate, ents in byplate.items():
        groups = {comm_of.get(e) for e in ents if e in comm_of}
        if len(ents) >= 2 and len(groups) >= 2:
            firs = [l["fir_id"] for e in ents for l in A.entities[e]["links"] if A.R.mentions[l["mention"]].get("plate") == plate]
            out.append(_alert("shared_vehicle", "medium", f"Vehicle {plate} used by people in different groups",
                              f"Vehicle {plate} is linked to {', '.join(A.name(e) for e in sorted(ents))}, who belong to different communities "
                              f"({', '.join('C' + str(g) for g in sorted(groups))}).", ents, firs=firs, plate=plate))
    return out


# 4 ---------------------------------------------------------------------------------
def sudden_contact(A, frac=BASELINE_FRAC):
    cut = A.t_min + (A.t_max - A.t_min) * frac
    G0 = build_graph(A, end=cut)
    M0 = compute_metrics(A, G0)
    cid = {n: m["community"] for n, m in M0["metrics"].items()}
    size = Counter(cid.values())
    lead = {c["id"]: " & ".join(A.name(x) for x in c["top"][:2]) for c in M0["communities"]}
    pre_pairs = set()
    for a, b, d in G0.edges(data=True):
        if d["etype"] in ("call", "transfer", "associate") and a in cid and b in cid and cid[a] != cid[b]:
            pre_pairs.add(frozenset((cid[a], cid[b])))
    post = defaultdict(lambda: dict(calls=[], txns=[], ents=set(), first=None, amt=0, last=None))
    for r in A.cdr[A.cdr.ts > cut].itertuples():
        a, b = r.caller_ent, r.receiver_ent
        if a in cid and b in cid and cid[a] != cid[b] and size[cid[a]] >= 3 and size[cid[b]] >= 3:
            p = post[frozenset((cid[a], cid[b]))]
            p["calls"].append(r.call_id); p["ents"] |= {a, b}
            p["first"] = r.ts if p["first"] is None or r.ts < p["first"] else p["first"]
            p["last"] = r.ts if p["last"] is None or r.ts > p["last"] else p["last"]
    for r in A.tx[A.tx.ts > cut].itertuples():
        a, b = r.sender_ent, r.receiver_ent
        if a in cid and b in cid and cid[a] != cid[b] and size[cid[a]] >= 3 and size[cid[b]] >= 3:
            p = post[frozenset((cid[a], cid[b]))]
            p["txns"].append(r.txn_id); p["ents"] |= {a, b}; p["amt"] += int(r.amount_inr)
            p["first"] = r.ts if p["first"] is None or r.ts < p["first"] else p["first"]
            p["last"] = r.ts if p["last"] is None or r.ts > p["last"] else p["last"]
    out = []
    for pair, p in post.items():
        if pair in pre_pairs or len(p["calls"]) + len(p["txns"]) < 3:
            continue
        c1, c2 = sorted(pair)
        out.append(_alert("sudden_contact", "high", f"Previously separate groups suddenly in contact",
                          f"The group around {lead[c1]} and the group around {lead[c2]} had no direct calls or money transfers before "
                          f"{cut:%d %b %Y}. First contact {p['first']:%d %b %H:%M}; since then {len(p['calls'])} calls and {len(p['txns'])} transfers "
                          f"({_rupees(p['amt'])}) between {len(p['ents'])} people.",
                          p["ents"], calls=p["calls"], txns=p["txns"], start=p["first"], end=p["last"],
                          baseline_cutoff=str(cut), communities=[c1, c2]))
    return out


# 5 ---------------------------------------------------------------------------------
def colocation(A, comm_of):
    out = []
    c = A.cdr[A.cdr.caller_ent.notna()].copy()
    home = c.groupby("caller_ent").tower_id.agg(lambda s: s.value_counts().idxmax())
    c["away"] = c.apply(lambda r: home[r.caller_ent] != r.tower_id, axis=1)
    for tower, g in c.groupby("tower_id"):
        g = g.sort_values("ts")
        rows = list(g.itertuples())
        used = -1
        for i, r0 in enumerate(rows):
            if i <= used:
                continue
            win = [r for r in rows[i:] if (r.ts - r0.ts).total_seconds() <= COLOC_WINDOW_MIN * 60]
            people = {r.caller_ent for r in win}
            away = {r.caller_ent for r in win if r.away}
            comms = {comm_of.get(p) for p in away}
            if len(away) >= COLOC_MIN_PEOPLE and len(comms) >= 2:
                used = i + len(win) - 1
                fir = [e["fir_id"] for e in A.extracted for ev in e["events"] if ev["kind"] == "meeting"
                       and tower and A.cdr[A.cdr.tower_id == tower].tower_location.iloc[0].split()[0] in ev["location"]]
                corro = " Corroborated by " + ", ".join(fir) + " (informant report of a meeting at this place)." if fir else ""
                out.append(_alert("co_location", "high" if fir else "medium",
                                  f"Possible meeting: {len(away)} people at {win[0].tower_location}",
                                  f"{len(away)} people ({', '.join(A.name(p) for p in sorted(away))}) made calls "
                                  f"from tower {tower} ({win[0].tower_location}) between {win[0].ts:%H:%M} and {win[-1].ts:%H:%M} on {win[0].ts:%d %b}, "
                                  f"all away from their usual towers.{corro}",
                                  away, calls=[r.call_id for r in win if r.caller_ent in away], firs=fir, start=win[0].ts, end=win[-1].ts,
                                  tower=tower, location=win[0].tower_location))
    return out


def run_all(A):
    G = build_graph(A)
    M = compute_metrics(A, G)
    comm_of = {n: m["community"] for n, m in M["metrics"].items()}
    alerts = []
    alerts += burst_calling(A)
    alerts += circular_transfers(A)
    alerts += layering(A)
    alerts += shared_identity(A)
    alerts += shared_vehicle(A, comm_of)
    alerts += sudden_contact(A)
    alerts += colocation(A, comm_of)
    order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: (order[a["severity"]], a["time"]["start"] or ""))
    for i, a in enumerate(alerts, 1):
        a["id"] = f"ALR-{i:02d}"
    return alerts
