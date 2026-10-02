"""Explainable 0-100 risk score: every point comes from a computed fact."""


def risk_scores(A, metrics, alerts):
    inv = {}
    for a in alerts:
        for e in a["entities"]:
            inv.setdefault(e, []).append(a["id"])
    amt = {}
    for r in A.tx.itertuples():
        amt[r.sender_ent] = amt.get(r.sender_ent, 0) + int(r.amount_inr)
        amt[r.receiver_ent] = amt.get(r.receiver_ent, 0) + int(r.amount_inr)
    top = max((m["score"] for m in metrics.values()), default=1) or 1
    out = {}
    for eid in A.entities:
        m = metrics.get(eid)
        cen = round(40 * (m["score"] / top)) if m else 0
        al = inv.get(eid, [])
        alr = min(40, 10 * len(al))
        vol = min(20, round(20 * amt.get(eid, 0) / 2_000_000))
        total = cen + alr + vol
        out[eid] = dict(score=total, level="high" if total >= 60 else "medium" if total >= 30 else "low",
                        breakdown=dict(centrality=cen, alert_involvement=alr, money_volume=vol), alerts=al)
    return out
