"""Rules-first entity resolution with evidence + confidence. Never merges blindly.

Rules (in priority order):
  R1 exact_full_name        identical full names are one person (different full names NEVER merge)
  R2 alias+phone            nickname declared elsewhere for that person AND the phone matches
  R3 phone_match            phone owned by exactly one person; nickname/initial compatible
  R4 unique_alias           nickname declared as alias of exactly one person
  R5 initial_surname        'B. Rathore' -> exactly one 'B* Rathore'; +org corroboration raises confidence
Phones attributed to >=2 distinct full names are SHARED: they are reported, never used to merge.
Single-token names matching several first names (e.g. 'Ojas') are left unresolved + flagged.
"""
import re
from collections import defaultdict


def _norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


class Cluster:
    def __init__(self, key, name):
        self.key, self.name = key, name
        self.aliases = defaultdict(list)     # alias(lower) -> [fir ids]
        self.alias_disp = {}
        self.phones = {}                     # phone -> {fir, rule, confidence}
        self.orgs, self.plates = set(), set()
        self.roles = set()
        self.mentions = []                   # (mid, rule, conf)
        self.locations = set()

    @property
    def first(self):
        return self.name.split()[0].lower()

    @property
    def last(self):
        return self.name.split()[-1].lower()


class Resolution:
    def __init__(self):
        self.clusters = {}
        self.eid = {}            # cluster key -> entity id
        self.mention_entity = {}  # mid -> entity id | None
        self.links = []          # evidence for each mention->entity decision
        self.unresolved = []
        self.shared_phones = {}  # phone -> [{entity, surface, fir}]
        self.phone_owner = {}    # phone -> entity id
        self.mentions = {}       # mid -> mention dict (+fir)

    # ---------------------------------------------------------------- lookups
    def entity_name(self, eid):
        return self.entities[eid]["name"]

    def lookup_name(self, name):
        """Resolve a name string (as written in transactions) to an entity id, or None."""
        s = _norm(name)
        toks = s.split()
        if len(toks) >= 2 and not re.match(r"^[a-z]\.$", toks[0]):
            c = self.clusters.get(s)
            return self.eid[c.key] if c else None
        if len(toks) == 2:  # initial form
            ini, sur = toks[0][0], toks[1]
            cs = [c for c in self.clusters.values() if c.first[0] == ini and c.last == sur]
            return self.eid[cs[0].key] if len(cs) == 1 else None
        cs = [c for c in self.clusters.values() if s in c.aliases]
        return self.eid[cs[0].key] if len(cs) == 1 else None


def resolve(extracted):
    R = Resolution()
    C = R.clusters
    ments = []
    for e in extracted:
        for m in e["mentions"]:
            m = dict(m, fir_id=e["fir_id"], mid=f"{e['fir_id']}#{m['idx']}")
            ments.append(m)
            R.mentions[m["mid"]] = m

    def add_link(m, key, rule, conf, note=""):
        c = C[key]
        c.mentions.append((m["mid"], rule, conf))
        c.roles.add(m["role"])
        if m.get("org"):
            c.orgs.add(m["org"])
        if m.get("plate"):
            c.plates.add(m["plate"])
        if m.get("location") and m["role"] != "victim":
            c.locations.add(m["location"])
        R.mention_entity[m["mid"]] = key
        R.links.append(dict(mention=m["mid"], fir_id=m["fir_id"], surface=m["surface"], entity_key=key,
                            rule=rule, confidence=conf, evidence=m["evidence"], note=note))

    # ---- R1: full-name clusters
    for m in ments:
        if m["kind"] == "full":
            k = _norm(m["surface"])
            C.setdefault(k, Cluster(k, m["surface"]))
            add_link(m, k, "exact_full_name", 1.0)
            if m.get("alias"):
                C[k].aliases[m["alias"].lower()].append(m["fir_id"])
                C[k].alias_disp[m["alias"].lower()] = m["alias"]

    # ---- phone ownership from full-name mentions
    phone_full = defaultdict(set)
    for m in ments:
        if m["kind"] == "full" and m.get("phone"):
            phone_full[m["phone"]].add(_norm(m["surface"]))
    shared = {p for p, ks in phone_full.items() if len(ks) >= 2}
    owner = {p: next(iter(ks)) for p, ks in phone_full.items() if len(ks) == 1}
    for m in ments:
        if m["kind"] == "full" and m.get("phone") and m["phone"] in owner:
            C[_norm(m["surface"])].phones.setdefault(m["phone"], dict(fir=m["fir_id"], rule="stated_in_fir", confidence=1.0))

    # ---- iterate over non-full mentions
    pending = [m for m in ments if m["kind"] != "full"]
    for _ in range(6):
        changed = False
        for m in list(pending):
            res = _try(m, C, owner, shared)
            if res:
                key, rule, conf, note = res
                add_link(m, key, rule, conf, note)
                ph = m.get("phone")
                if ph and ph not in shared and ph not in owner:
                    owner[ph] = key
                    C[key].phones[ph] = dict(fir=m["fir_id"], rule=rule, confidence=conf)
                elif ph and ph in owner and owner[ph] == key:
                    C[key].phones.setdefault(ph, dict(fir=m["fir_id"], rule=rule, confidence=conf))
                if m["kind"] in ("single", "initial") and m["surface"].lower() not in C[key].aliases:
                    C[key].aliases[m["surface"].lower()].append(m["fir_id"])
                    C[key].alias_disp[m["surface"].lower()] = m["surface"]
                pending.remove(m)
                changed = True
        if not changed:
            break

    # ---- leftovers: group by (non-shared) phone into 'unnamed' entities; else flag as unresolved
    byphone = defaultdict(list)
    for m in pending:
        ph = m.get("phone")
        if ph and ph not in shared:
            byphone[ph].append(m)
    for ph, ms in byphone.items():
        k = f"~{ms[0]['surface'].lower()}@{ph}"
        C[k] = Cluster(k, ms[0]["surface"])
        for m in ms:
            add_link(m, k, "phone_only_new_identity", 0.6, "no full name known; grouped by phone")
            pending.remove(m)
        C[k].phones[ph] = dict(fir=ms[0]["fir_id"], rule="phone_only_new_identity", confidence=0.6)
        owner[ph] = k
        C[k].aliases[ms[0]["surface"].lower()].append(ms[0]["fir_id"])
        C[k].alias_disp[ms[0]["surface"].lower()] = ms[0]["surface"]

    # ---- entity ids
    for i, k in enumerate(sorted(C, key=lambda x: (x.startswith("~"), C[x].name.lower())), 1):
        R.eid[k] = f"E{i:03d}"
    R.mention_entity = {mid: R.eid[k] for mid, k in R.mention_entity.items()}
    R.phone_owner = {p: R.eid[k] for p, k in owner.items()}

    # ---- unresolved + context hints (still NOT merged)
    fir_map = defaultdict(list)
    for m in ments:
        fir_map[m["fir_id"]].append(m)
    for m in pending:
        cands = _name_candidates(m, C)
        hint = None
        peers = {R.mention_entity.get(x["mid"]) for x in fir_map[m["fir_id"]] if x["mid"] != m["mid"]} - {None}
        scored = []
        for c in cands:
            e = R.eid[c.key]
            # corroboration: candidate has a FIR relation with someone else named in this FIR
            rel = _co_listed(e, peers, R, extracted)
            scored.append((rel, e))
        top = [e for r, e in scored if r]
        if len(top) == 1 and len(cands) > 1:
            hint = top[0]
        R.unresolved.append(dict(mid=m["mid"], fir_id=m["fir_id"], surface=m["surface"],
                                 candidates=[R.eid[c.key] for c in cands], leading_candidate=hint,
                                 reason="ambiguous: matches several people" if len(cands) > 1 else "no safe match",
                                 evidence=m["evidence"]))

    # ---- shared phone report
    for p in shared:
        R.shared_phones[p] = []
    for m in ments:
        ph = m.get("phone")
        if ph in shared:
            k = R.mention_entity.get(m["mid"])
            R.shared_phones[ph].append(dict(entity=k, surface=m["surface"], fir_id=m["fir_id"], evidence=m["evidence"]))

    _finalize(R, C, ments)
    return R


def _name_candidates(m, C):
    s = m["surface"].lower()
    if m["kind"] == "initial":
        toks = s.split()
        return [c for c in C.values() if not c.key.startswith("~") and c.first[0] == toks[0][0] and c.last == toks[-1]]
    byalias = [c for c in C.values() if s in c.aliases]
    if byalias:
        return byalias
    return [c for c in C.values() if not c.key.startswith("~") and c.first == s]


def _try(m, C, owner, shared):
    s, ph = m["surface"].lower(), m.get("phone")
    # phone-based (R2/R3)
    if ph and ph not in shared and ph in owner:
        c = C[owner[ph]]
        if m["kind"] == "initial":
            toks = s.split()
            if c.first[0] == toks[0][0] and c.last == toks[-1]:
                return c.key, "phone_match", 0.9, f"phone {ph} belongs to {c.name}; initial+surname compatible"
            return None
        if s in c.aliases:
            return c.key, "alias+phone", 0.95, f"'{m['surface']}' is a declared alias of {c.name} and phone {ph} matches"
        if c.aliases and not any(a for a in c.aliases if a == s):
            return None  # nickname conflicts with a declared one -> do not merge
        return c.key, "phone_match", 0.85, f"phone {ph} belongs to {c.name}; nickname '{m['surface']}' not independently declared"
    # name-based (R4/R5)
    cands = _name_candidates(m, C)
    if m["kind"] == "initial" and len(cands) == 1:
        c = cands[0]
        corro = bool(m.get("org") and m["org"] in c.orgs)
        return c.key, "initial_surname", 0.9 if corro else 0.75, ("org matches" if corro else "unique initial+surname")
    if m["kind"] == "single" and len(cands) == 1 and s in cands[0].aliases:
        return cands[0].key, "unique_alias", 0.85, f"'{m['surface']}' declared as alias of {cands[0].name} only"
    return None


def _co_listed(eid, peers, R, extracted):
    """True if candidate entity shares a FIR relation with any peer in the same FIR (any FIR)."""
    for e in extracted:
        ids = {R.mention_entity.get(f"{e['fir_id']}#{i}") for i in range(len(e["mentions"]))}
        if eid in ids and ids & peers:
            return True
    return False


def _finalize(R, C, ments):
    ents = {}
    byk = defaultdict(list)
    for l in R.links:
        byk[l["entity_key"]].append(l)
    for k, c in C.items():
        eid = R.eid[k]
        links = byk[k]
        firs = sorted({l["fir_id"] for l in links})
        roles = c.roles
        role = "victim" if roles == {"victim"} else ("suspect" if "suspect" in roles else ("associate" if "associate" in roles else "mentioned"))
        ents[eid] = dict(
            id=eid, type="person", name=c.name,
            aliases=sorted(c.alias_disp[a] for a in c.aliases),
            phones=sorted(c.phones), phone_evidence=c.phones,
            orgs=sorted(c.orgs), plates=sorted(c.plates), locations=sorted(c.locations),
            role=role, firs=firs, links=links,
            confidence=round(min([l["confidence"] for l in links] or [1.0]), 2),
        )
    R.entities = ents
