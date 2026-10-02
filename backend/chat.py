"""Hybrid investigator chatbot.

  question --(LLM or regex fallback)--> {tool, args} --(Python/NetworkX/pandas)--> facts + evidence ids
           --(LLM explains, or deterministic template)--> answer, validated against the evidence.

The LLM never computes: it picks a tool and phrases the result. Answers citing an id/number that is not in the
tool output are rejected and replaced by the deterministic answer.
"""
import json, re
from collections import defaultdict
import networkx as nx
import pandas as pd

import llm
from graph import person_projection

SESSIONS = defaultdict(lambda: dict(last=[], history=[]))
ID_RX = re.compile(r"\b(FIR-\d{3}|C\d{4}|T\d{4}|ALR-\d{2})\b")

TOOLS_DOC = """Tools (choose exactly one):
- top_central   {n:int}                      key persons ranked by overall importance in the network
- entity_profile{entity:str}                 who is X: aliases, phones, FIRs, risk
- neighbors     {entity:str, hops:1|2}       who is connected to X
- transactions  {entity?:str, entity2?:str, group?:int, min_amount?:int, max_amount?:int, start?:YYYY-MM-DD, end?:YYYY-MM-DD}
- shortest_path {entity:str, entity2:str}    how are A and B connected
- calls         {entity?:str, entity2?:str, start?, end?}
- alerts        {type?: burst_calling|circular_transfer|layering|shared_phone|shared_vehicle|sudden_contact|co_location, entity?:str}
- risk          {entity?:str}
- communities   {}
- clarify       {message:str}                if the question is ambiguous or unrelated to the case data"""


# ---------------------------------------------------------------- entity lookup
def _index(A):
    if getattr(A, "_idx", None):
        return A._idx
    forms, firsts = {}, defaultdict(set)
    for e in A.entities.values():
        forms[e["name"].lower()] = e["id"]
        for a in e["aliases"]:
            forms.setdefault(a.lower(), e["id"])
        for t in e["name"].lower().split():
            if len(t) > 2:
                firsts[t].add(e["id"])
    A._idx = (forms, firsts)
    return A._idx


def find_entities(A, text):
    """-> (found [eid], ambiguous [(token,[eid])], phones_unknown [str])"""
    forms, tokens = _index(A)
    t = " " + re.sub(r"[^\w\s\.\+]", " ", text.lower()) + " "
    found, amb, unk = [], [], []
    for ph in re.findall(r"(?:\+91[ -]?)?(\d{5}[ -]?\d{5})", text):
        p = re.sub(r"\D", "", ph)[-10:]
        e = A.R.phone_owner.get(p)
        if e and e not in found:
            found.append(e)
        elif not e:
            unk.append(p)
    spans = []
    for f in sorted(forms, key=len, reverse=True):  # longest first
        for m in re.finditer(r"(?<![\w])" + re.escape(f) + r"(?![\w])", t):
            if not any(s <= m.start() < e_ or s < m.end() <= e_ for s, e_ in spans):
                spans.append((m.start(), m.end()))
                if forms[f] not in found:
                    found.append(forms[f])
    for tok in re.findall(r"[a-z]{3,}", t):
        if tok in tokens and not any(s <= t.find(tok) < e_ for s, e_ in spans):
            c = tokens[tok]
            if len(c) == 1 and next(iter(c)) not in found:
                found.append(next(iter(c)))
            elif len(c) > 1 and not (set(c) & set(found)):
                amb.append((tok, sorted(c)))
    return found, amb, unk


def _resolve_arg(A, val, memory):
    """Entity argument (name string / pronoun / id) -> eid or ('ambiguous', [...])."""
    if not val:
        return None
    if val in A.entities:
        return val
    v = str(val).strip()
    if v.lower() in ("him", "her", "he", "she", "they", "them", "his", "that person", "same person", "uska", "unka", "usne"):
        return memory["last"][0] if memory["last"] else None
    f, amb, _ = find_entities(A, v)
    if f:
        return f[0]
    if amb:
        return ("ambiguous", amb[0][1], amb[0][0])
    return None


# ---------------------------------------------------------------- tools
def _fmt_amt(x):
    return f"₹{int(x):,}"


def _res(tool, args, facts, answer, calls=(), txns=(), firs=(), alerts=(), nodes=(), etypes=None):
    return dict(tool=tool, args=args, facts=facts, answer=answer,
                evidence=dict(calls=list(calls), txns=list(txns), firs=sorted(set(firs)), alerts=list(alerts)),
                highlight=dict(nodes=sorted(set(nodes)), etypes=etypes))


def t_top_central(S, n=5, **_):
    A, M = S["A"], S["M"]
    n = max(1, min(int(n or 5), 10))
    top = M["top5"] if n <= 5 else None
    if top is None:
        order = sorted(M["metrics"], key=lambda x: -M["metrics"][x]["score"])[:n]
        top = [dict(id=i, name=A.name(i), score=M["metrics"][i]["score"], reasons=[]) for i in order]
    facts = [dict(rank=i + 1, id=t["id"], name=t["name"], composite=t["score"], reasons=t.get("reasons", [])) for i, t in enumerate(top[:n])]
    ans = f"Top {len(facts)} key persons (ranked by how many people they connect, how much they link separate groups, and how much calls, money and FIRs flow through them):\n"
    for f in facts:
        ans += f"{f['rank']}. {f['name']} (score {f['composite']}) — " + "; ".join(f["reasons"][:3]) + "\n"
    return _res("top_central", {"n": n}, facts, ans.strip(), nodes=[f["id"] for f in facts])


def t_entity_profile(S, entity=None, **_):
    A, M, R = S["A"], S["M"], S["risk"]
    e = A.entities[entity]
    m = M["metrics"].get(entity) or {}
    al = [a for a in S["alerts"] if entity in a["entities"]]
    facts = dict(id=entity, name=e["name"], aliases=e["aliases"], role=e["role"], phones=e["phones"], accounts=e["accounts"],
                 organisations=e["orgs"], vehicles=e["plates"], locations=e["locations"], firs=e["firs"],
                 community=m.get("community"), risk=R[entity]["score"], risk_level=R[entity]["level"],
                 resolution_confidence=e["confidence"], alerts=[(a["id"], a["title"]) for a in al])
    ans = (f"{e['name']}" + (f" (also known as {', '.join(e['aliases'])})" if e["aliases"] else "") + f" — role: {e['role']}, group {m.get('community')}. "
           f"Phones: {', '.join(e['phones']) or 'none identified'}. " + (f"Organisation: {', '.join(e['orgs'])}. " if e["orgs"] else "")
           + (f"Vehicle: {', '.join(e['plates'])}. " if e["plates"] else "") + f"Appears in {', '.join(e['firs']) or 'no FIRs'}. "
           f"Risk score {R[entity]['score']}/100 ({R[entity]['level']}). " + (f"Involved in alerts: {', '.join(a['id'] for a in al)}." if al else "No alerts."))
    return _res("entity_profile", {"entity": entity}, facts, ans, firs=e["firs"], alerts=[a["id"] for a in al], nodes=[entity])


def _pair_edges(G, a, b):
    out = dict(calls=[], txns=[], firs=[], amount=0, rel=set())
    if G.has_edge(a, b):
        for d in G[a][b].values():
            if d["etype"] == "call": out["calls"] += d["evidence"]
            elif d["etype"] == "transfer": out["txns"] += d["evidence"]; out["amount"] += d["amount"]
            elif d["etype"] == "associate": out["firs"] += d["evidence"]; out["rel"].add(d.get("relation"))
    return out


def t_neighbors(S, entity=None, hops=1, **_):
    A, G = S["A"], S["G"]
    P = person_projection(G)
    if entity not in P:
        return _res("neighbors", {"entity": entity}, [], f"{A.name(entity)} has no recorded contacts.", nodes=[entity])
    hops = 2 if str(hops) == "2" else 1
    ego = nx.single_source_shortest_path_length(P, entity, cutoff=hops)
    rows, calls, txns, firs = [], [], [], []
    for n, dist in sorted(ego.items(), key=lambda kv: (kv[1], -P[entity][kv[0]]["weight"] if kv[1] == 1 else 0)):
        if n == entity:
            continue
        r = dict(id=n, name=A.name(n), hops=dist)
        if dist == 1:
            pe = _pair_edges(G, entity, n)
            r.update(calls=len(pe["calls"]), transfers=len(pe["txns"]), amount=pe["amount"], fir_links=pe["firs"], relation=", ".join(sorted(x for x in pe["rel"] if x)))
            calls += pe["calls"][:3]; txns += pe["txns"][:3]; firs += pe["firs"]
        rows.append(r)
    d1 = [r for r in rows if r["hops"] == 1]
    ans = f"{A.name(entity)} has {len(d1)} direct contacts: " + "; ".join(
        f"{r['name']} ({r['calls']} calls, {r['transfers']} transfers" + (f" {_fmt_amt(r['amount'])}" if r["amount"] else "") + (f", FIR {','.join(r['fir_links'])}" if r["fir_links"] else "") + ")" for r in d1[:10])
    if hops == 2:
        ans += f". Within 2 hops: {len(rows) - len(d1)} more people."
    return _res("neighbors", {"entity": entity, "hops": hops}, rows[:25], ans, calls=calls, txns=txns, firs=firs, nodes=[entity] + [r["id"] for r in rows])


def t_transactions(S, entity=None, entity2=None, group=None, min_amount=None, max_amount=None, start=None, end=None, **_):
    A, M = S["A"], S["M"]
    df = A.tx.copy()
    desc = []
    members = None
    if group:
        c = next((c for c in M["communities"] if c["id"] == int(group)), None)
        if not c:
            return _res("transactions", {"group": group}, [], f"There is no group {group}; there are {len(M['communities'])} groups.")
        members = set(c["members"])
        df = df[df.sender_ent.isin(members) & df.receiver_ent.isin(members)]
        desc.append(f"between members of Group {c['id']} (led by {A.name(c['lead'])})")
    if entity and entity2:
        df = df[((df.sender_ent == entity) & (df.receiver_ent == entity2)) | ((df.sender_ent == entity2) & (df.receiver_ent == entity))]
        desc.append(f"between {A.name(entity)} and {A.name(entity2)}")
    elif entity:
        df = df[(df.sender_ent == entity) | (df.receiver_ent == entity)]
        desc.append(f"involving {A.name(entity)}")
    if min_amount: df = df[df.amount_inr > float(min_amount)]; desc.append(f"above {_fmt_amt(min_amount)}")
    if max_amount: df = df[df.amount_inr < float(max_amount)]; desc.append(f"below {_fmt_amt(max_amount)}")
    if start: df = df[df.ts >= pd.Timestamp(start)]; desc.append(f"from {start}")
    if end: df = df[df.ts <= pd.Timestamp(end) + pd.Timedelta(days=1)]; desc.append(f"until {end}")
    df = df.sort_values("ts")
    rows = [dict(txn_id=r.txn_id, when=f"{r.date} {r.time}", sender=A.name(r.sender_ent), receiver=A.name(r.receiver_ent), amount=int(r.amount_inr),
                 mode=r.mode, names_as_written=[r.sender, r.receiver]) for r in df.itertuples()]
    nodes = set(df.sender_ent) | set(df.receiver_ent)
    if not rows:
        return _res("transactions", {"entity": entity, "group": group}, [], f"No transactions found {' '.join(desc)}.", nodes=[x for x in (entity, entity2) if x])
    ans = f"{len(rows)} transaction(s) {' '.join(desc)}, total {_fmt_amt(sum(r['amount'] for r in rows))}:\n" + "\n".join(
        f"- {r['txn_id']}: {r['sender']} → {r['receiver']} {_fmt_amt(r['amount'])} on {r['when']} ({r['mode']})" for r in rows[:15])
    if len(rows) > 15:
        ans += f"\n…and {len(rows) - 15} more."
    return _res("transactions", dict(entity=entity, entity2=entity2, group=group, min_amount=min_amount, start=start, end=end), rows[:40], ans,
                txns=[r["txn_id"] for r in rows], nodes=nodes, etypes=["transfer"])


def t_shortest_path(S, entity=None, entity2=None, **_):
    A, G = S["A"], S["G"]
    P = person_projection(G)
    if entity not in P or entity2 not in P:
        return _res("shortest_path", {}, [], "One of these people has no recorded connections, so no path exists.", nodes=[entity, entity2])
    try:
        path = nx.shortest_path(P, entity, entity2)
    except nx.NetworkXNoPath:
        return _res("shortest_path", {"a": entity, "b": entity2}, [], f"No connection found between {A.name(entity)} and {A.name(entity2)} in the data.", nodes=[entity, entity2])
    hops, calls, txns, firs = [], [], [], []
    for u, v in zip(path, path[1:]):
        pe = _pair_edges(G, u, v)
        hops.append(dict(a=A.name(u), b=A.name(v), calls=len(pe["calls"]), transfers=len(pe["txns"]), amount=pe["amount"], firs=pe["firs"]))
        calls += pe["calls"][:2]; txns += pe["txns"][:2]; firs += pe["firs"]
    ans = f"Shortest connection ({len(path) - 1} hop{'s' if len(path) > 2 else ''}): " + " → ".join(A.name(p) for p in path) + ". " + " ".join(
        f"[{h['a']}–{h['b']}: {h['calls']} calls, {h['transfers']} transfers" + (f" {_fmt_amt(h['amount'])}" if h["amount"] else "") + (f", {', '.join(h['firs'])}" if h["firs"] else "") + "]" for h in hops)
    return _res("shortest_path", {"a": entity, "b": entity2}, hops, ans, calls=calls, txns=txns, firs=firs, nodes=path, etypes=["call", "transfer", "associate"])


def t_calls(S, entity=None, entity2=None, start=None, end=None, **_):
    A = S["A"]
    df = A.cdr
    if entity and entity2:
        df = df[((df.caller_ent == entity) & (df.receiver_ent == entity2)) | ((df.caller_ent == entity2) & (df.receiver_ent == entity))]
    elif entity:
        df = df[(df.caller_ent == entity) | (df.receiver_ent == entity)]
    if start: df = df[df.ts >= pd.Timestamp(start)]
    if end: df = df[df.ts <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    rows = [dict(call_id=r.call_id, when=r.timestamp, caller=A.name(r.caller_ent) if r.caller_ent else r.caller, receiver=A.name(r.receiver_ent) if r.receiver_ent else r.receiver,
                 duration_sec=int(r.duration_sec), tower=r.tower_location) for r in df.itertuples()]
    nodes = {e for e in (set(df.caller_ent) | set(df.receiver_ent)) if e}
    ans = f"{len(rows)} call record(s)" + (f" involving {A.name(entity)}" if entity else "") + (f" and {A.name(entity2)}" if entity2 else "") + ". " + "; ".join(
        f"{r['call_id']} {r['caller']}→{r['receiver']} {r['when']} ({r['duration_sec']}s)" for r in rows[:8]) + ("…" if len(rows) > 8 else "")
    return _res("calls", dict(entity=entity, entity2=entity2), rows[:40], ans, calls=[r["call_id"] for r in rows], nodes=nodes, etypes=["call"])


def t_alerts(S, type=None, entity=None, **_):
    A = S["A"]
    al = [a for a in S["alerts"] if (not type or a["type"] == type) and (not entity or entity in a["entities"])]
    facts = [dict(id=a["id"], type=a["type"], severity=a["severity"], title=a["title"], summary=a["summary"]) for a in al]
    ans = f"{len(al)} alert(s):\n" + "\n".join(f"- {a['id']} [{a['severity']}] {a['title']}: {a['summary']}" for a in al)
    ev = defaultdict(list)
    for a in al:
        for k in ("calls", "txns", "firs"):
            ev[k] += a["evidence"][k]
    nodes = {e for a in al for e in a["entities"]}
    return _res("alerts", dict(type=type, entity=entity), facts, ans, calls=ev["calls"][:30], txns=ev["txns"], firs=ev["firs"], alerts=[a["id"] for a in al], nodes=nodes)


def t_risk(S, entity=None, **_):
    A, R = S["A"], S["risk"]
    if entity:
        r = R[entity]
        ans = f"{A.name(entity)} risk score {r['score']}/100 ({r['level']}): importance in the network {r['breakdown']['centrality']}/40, alert involvement {r['breakdown']['alert_involvement']} ({', '.join(r['alerts']) or 'none'}), money moved {r['breakdown']['money_volume']}/20."
        return _res("risk", {"entity": entity}, dict(r, name=A.name(entity)), ans, alerts=r["alerts"], nodes=[entity])
    top = sorted(R, key=lambda e: -R[e]["score"])[:5]
    facts = [dict(id=e, name=A.name(e), score=R[e]["score"], level=R[e]["level"]) for e in top]
    return _res("risk", {}, facts, "Highest risk: " + "; ".join(f"{f['name']} {f['score']}/100" for f in facts), nodes=top)


def t_communities(S, **_):
    A, M = S["A"], S["M"]
    facts = [dict(group=c["id"], size=c["size"], led_by=A.name(c["lead"]), members=[A.name(m) for m in c["members"]]) for c in M["communities"]]
    ans = f"{len(facts)} groups detected (people who interact mostly with each other): " + "; ".join(f"Group {f['group']} ({f['size']} people, led by {f['led_by']})" for f in facts)
    return _res("communities", {}, facts, ans, nodes=[m for c in M["communities"] for m in c["members"]])


TOOLS = dict(top_central=t_top_central, entity_profile=t_entity_profile, neighbors=t_neighbors, transactions=t_transactions,
             shortest_path=t_shortest_path, calls=t_calls, alerts=t_alerts, risk=t_risk, communities=t_communities)
ENT_ARGS = ("entity", "entity2")


# ---------------------------------------------------------------- routing
def parse_amount(text):
    t = text.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|crore|k\b|thousand)", t)
    if m:
        mult = dict(lakh=1e5, lac=1e5, crore=1e7, k=1e3, thousand=1e3)[m.group(2)]
        return int(float(m.group(1)) * mult)
    m = re.search(r"(?:₹|rs\.?|inr)\s*(\d{4,})|(\d{4,})", t)
    return int(m.group(1) or m.group(2)) if m else None


def rule_route(A, text, memory):
    """Regex/keyword fallback router (also used to double-check the LLM)."""
    t = text.lower()
    found, amb, unk = find_entities(A, text)
    if memory["last"] and re.search(r"\b(him|her|his|he|she|they|them|uska|unka|usne|us)\b", t) and (not found or len(found) == 1 and memory["last"][0] != found[0]):
        found = memory["last"][:1] + found
    g = re.search(r"(?:group|community|gang)\s*#?(\d+)", t)
    amt = parse_amount(re.sub(r"(?:group|community)\s*\d+", "", t)) if re.search(r"above|over|more than|greater|zyada|se upar|below|under|less|>|<", t) else None
    args = {}
    if re.fullmatch(r"\s*(hi+|hello+|hey+|namaste|namaskar|hola|good (morning|evening|afternoon))\s*[!.?]*\s*", t):
        return "clarify", {"message": "Hello. Ask me about people, calls, money, connections, risk or alerts. For example: 'Show the alerts', 'Who is Bunty?', 'Top 5 key persons'."}
    if re.search(r"top|key (person|player)|kingpin|most (important|central|connected)|leader|sabse (important|khatarnak|bada)|rank", t) and not found:
        n = re.search(r"top\s*(\d+)", t)
        return "top_central", {"n": int(n.group(1)) if n else 5}
    if re.search(r"\b(alert|suspicious|pattern|anomal|burst|circular|layering|co-?locat|meeting|burner|shared)\w*", t):
        ty = next((k for k, rx in dict(burst_calling="burst", circular_transfer="circular|cycle|round", layering="layer", shared_phone="burner|shared phone|one phone|same phone",
                                       sudden_contact="sudden|bridge|previously separate", co_location="co-?locat|meeting|same tower").items() if re.search(rx, t)), None)
        return "alerts", {"type": ty, **({"entity": found[0]} if found else {})}
    if re.search(r"\b(transaction|transfer|payment|money|paisa|paise|len-?den|lenden|hawala|cash|fund)\w*", t):
        a = {}
        if g: a["group"] = int(g.group(1))
        if amt and re.search(r"below|under|less|<", t): a["max_amount"] = amt
        elif amt: a["min_amount"] = amt
        if found: a["entity"] = found[0]
        if len(found) > 1: a["entity2"] = found[1]
        return "transactions", a
    if len(found) >= 2 and re.search(r"connect|link|path|related|relation|how|kaise|sambandh|chain", t):
        return "shortest_path", {"entity": found[0], "entity2": found[1]}
    if re.search(r"\bcall(s|ed|ing)?\b|phone record|cdr|dial", t) and found:
        return "calls", {"entity": found[0], **({"entity2": found[1]} if len(found) > 1 else {})}
    if len(found) >= 2 and re.search(r"between", t):
        return "shortest_path", {"entity": found[0], "entity2": found[1]}
    if re.search(r"\brisk|danger|threat|khatarnak", t):
        return "risk", {"entity": found[0]} if found else {}
    if re.search(r"communit|groups?\b|gangs?\b|clusters?|network structure", t) and not found:
        return "communities", {}
    if found and re.search(r"contact|connect|associate|know|linked|neighbo|who (is|are) .* (with|around)|sath|saathi|network|people around|kis kis", t):
        return "neighbors", {"entity": found[0], "hops": 2 if re.search(r"2 hop|two hop|second|indirect|friends of", t) else 1}
    if found and re.search(r"who is|who's|tell me about|profile|details|about|info|kaun|bare mein|batao|show", t):
        return "entity_profile", {"entity": found[0]}
    if found:
        return "entity_profile", {"entity": found[0]}
    if amb:
        return "clarify", {"message": f"'{amb[0][0].title()}' could mean " + " or ".join(A.name(e) for e in amb[0][1]) + ". Which one do you mean?"}
    return "clarify", {"message": "I can answer about people, calls, transactions, connections, key persons, risk and alerts in this case. Try: 'Top 5 key persons', 'Who is Bunty?', 'Transactions above ₹50,000 in Group 1', 'How is Zubair connected to Ishaan?'."}


def llm_route(A, text, memory):
    names = "; ".join(f"{e['name']}" + (f" (aka {', '.join(e['aliases'])})" if e["aliases"] else "") for e in A.entities.values())
    last = ", ".join(A.name(e) for e in memory["last"]) or "none"
    sys = ("You are the intent router of a police investigation assistant. Convert the user's question (English, Hindi or Hinglish) into ONE tool call. "
           "Reply with JSON only: {\"tool\": ..., \"args\": {...}}. Use person names exactly as the user wrote them (the system resolves aliases). "
           "If the user says he/she/him/her/unka, use the most recent person: " + last + ". Amounts are in rupees as integers. 'Group N' -> group:N.\n" + TOOLS_DOC +
           "\nKnown people: " + names)
    out = llm.complete_json([dict(role="system", content=sys), dict(role="user", content=text)], max_tokens=200)
    if out and out.get("tool") in {*TOOLS, "clarify"}:
        return out["tool"], out.get("args") or {}
    return None


def explain(text, result, lang_hint=""):
    """LLM phrases the already-computed result. Returns validated text or None."""
    facts = json.dumps(dict(tool=result["tool"], facts=result["facts"], evidence=result["evidence"]), ensure_ascii=False, default=str)[:6000]
    sys = ("You are an investigator's assistant. Answer the question using ONLY the FACTS provided; they were computed by software. "
           "Do not add people, numbers, dates or ids that are not in FACTS. Cite evidence ids that appear in FACTS (like FIR-007, C0123, T0045, ALR-02) in square brackets next to a claim, only if FACTS contain such ids. Never write placeholder ids. Use plain words, no jargon. Refer to people by name or as 'they'; never use he/she/his/her. "
           "Be concise (max 120 words). If the user wrote Hinglish/Hindi, answer in the same style. If FACTS are empty, say no matching record exists.")
    out = llm.complete([dict(role="system", content=sys), dict(role="user", content=f"QUESTION: {text}\nFACTS: {facts}")], max_tokens=350)
    if not out:
        return None
    allowed = set(result["evidence"]["firs"]) | set(result["evidence"]["calls"]) | set(result["evidence"]["txns"]) | set(result["evidence"]["alerts"]) | set(ID_RX.findall(facts))
    if re.search(r"(?i)\b(he|she|his|her|him|hers)\b", out) or re.search(r"(?i)\b(FIR|ALR)-x+|\b[CT]x+\b|\[[^\]]*x{3}[^\]]*\]", out) or any(i not in allowed for i in ID_RX.findall(out)):
        return None
    flat = facts.replace(",", "")
    for num in re.findall(r"\d[\d,]{3,}", out):
        if num.replace(",", "") not in flat:
            return None
    return out


# ---------------------------------------------------------------- entry point
def handle(S, sid, text):
    A = S["A"]
    mem = SESSIONS[sid]
    route, via = None, "rules"
    if llm.enabled():
        route = llm_route(A, text, mem)
        via = "llm" if route else "rules (llm unavailable)"
        if route and route[0] == "clarify":
            route, via = None, "rules (llm could not route)"
    if not route:
        route = rule_route(A, text, mem)
    tool, args = route
    # the LLM must not silently pick one of several people the user's wording could mean
    if via == "llm":
        _, amb, _ = find_entities(A, text)
        for k in ENT_ARGS:
            v = args.get(k)
            if amb and isinstance(v, str) and v.lower() not in text.lower() and not v.startswith(("E", "X")) and not re.search(r"\b(he|she|him|her|his)\b", text.lower()):
                if any(A.name(e).lower() == v.lower() for _, es in amb for e in es):
                    args[k] = amb[0][0]

    if via == "llm" and any(isinstance(args.get(k), str) and not find_entities(A, args[k])[0] and not find_entities(A, args[k])[1]
                            and not args[k].startswith(("E", "X")) and not re.search(r"\b(he|she|him|her|his|they)\b", args[k].lower()) for k in ENT_ARGS):
        tool, args = rule_route(A, text, mem); via = "rules (llm named an unknown person)"
    # the LLM sometimes drops the person in a follow-up ("his calls"): take it from the rules router, which reads pronouns from memory
    if via == "llm" and not args.get("entity"):
        rt, ra = rule_route(A, text, mem)
        if rt == tool and ra.get("entity"):
            args["entity"] = ra["entity"]
            if ra.get("entity2") and not args.get("entity2"): args["entity2"] = ra["entity2"]
    # resolve entity args
    for k in ENT_ARGS:
        if args.get(k):
            r = _resolve_arg(A, args[k], mem)
            if isinstance(r, tuple):
                return _finish(mem, text, dict(tool="clarify", args=args, facts=[], answer=f"'{r[2].title()}' could mean " + " or ".join(A.name(e) for e in r[1]) + ". Which one do you mean?",
                               evidence=dict(calls=[], txns=[], firs=[], alerts=[]), highlight=dict(nodes=r[1], etypes=None)), via)
            if r is None:
                f, amb, _ = find_entities(A, str(args[k]))
                if not f:
                    return _finish(mem, text, dict(tool="clarify", args=args, facts=[], answer=f"I couldn't find anyone matching '{args[k]}' in the case data.",
                                   evidence=dict(calls=[], txns=[], firs=[], alerts=[]), highlight=dict(nodes=[], etypes=None)), via)
            args[k] = r
    if tool == "clarify":
        return _finish(mem, text, dict(tool="clarify", args=args, facts=[], answer=args.get("message", "Could you rephrase?"),
                       evidence=dict(calls=[], txns=[], firs=[], alerts=[]), highlight=dict(nodes=[], etypes=None)), via)
    if tool in ("entity_profile", "neighbors") and not args.get("entity"):
        return _finish(mem, text, dict(tool="clarify", args=args, facts=[], answer="Which person do you mean?",
                       evidence=dict(calls=[], txns=[], firs=[], alerts=[]), highlight=dict(nodes=[], etypes=None)), via)
    if tool == "shortest_path" and not (args.get("entity") and args.get("entity2")):
        return _finish(mem, text, dict(tool="clarify", args=args, facts=[], answer="Please name the two people to connect.",
                       evidence=dict(calls=[], txns=[], firs=[], alerts=[]), highlight=dict(nodes=[], etypes=None)), via)
    try:
        res = TOOLS[tool](S, **args)
    except Exception as e:  # never crash the demo
        res = dict(tool=tool, args=args, facts=[], answer=f"Could not compute that ({type(e).__name__}). Try rephrasing.",
                   evidence=dict(calls=[], txns=[], firs=[], alerts=[]), highlight=dict(nodes=[], etypes=None))
    nice = explain(text, res) if llm.enabled() else None
    res["answer_source"] = "llm (validated against evidence)" if nice else "deterministic template"
    if nice:
        res["answer_llm"] = nice
        res["answer_template"] = res["answer"]
        res["answer"] = nice
    return _finish(mem, text, res, via)


def _finish(mem, text, res, via):
    ents = [n for n in res["highlight"]["nodes"] if n and not str(n).startswith("ph:")]
    focus = [res["args"].get(k) for k in ENT_ARGS if isinstance(res["args"].get(k), str) and res["args"].get(k).startswith(("E", "X"))]
    if focus:
        mem["last"] = focus + [e for e in mem["last"] if e not in focus]
    mem["last"] = mem["last"][:4]
    mem["history"].append(dict(q=text, tool=res["tool"]))
    res["router"] = via
    res["trace"] = dict(tool=res["tool"], args=res["args"], router=via)
    res.setdefault("answer_source", "deterministic template")
    return res
