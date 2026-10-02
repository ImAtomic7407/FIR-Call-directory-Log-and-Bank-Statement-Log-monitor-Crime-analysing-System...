"""Deterministic (rules-first) entity extraction from FIR text.

Output per FIR is a dict:
  {fir_id, date, station, mentions: [...], relations: [...], events: [...]}
Each mention: {idx, surface, kind(full|initial|single), phone, alias, role, org,
               plate, vehicle_desc, location, evidence}
`relations` link mention indexes: {a, b, relation}.

An LLM extractor (llm.py) can return the same schema; this module is the offline
fallback and the source of truth for phone / plate normalisation.
"""
import re

PH = r"(?:\+91[ -]?)?\d{5}[ -]?\d{5}"
NAME = r"[A-Z][a-z]+(?: [A-Z][a-z]+)?|[A-Z]\. [A-Z][a-z]+"
ALIAS = r"(?: \(alias (?P<alias>[A-Z][a-z]+)\))?"
PLATE = r"[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}"


def norm_phone(s):
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else None


def name_kind(s):
    toks = s.split()
    if len(toks) == 1:
        return "single"
    return "initial" if re.match(r"^[A-Z]\.$", toks[0]) else "full"


class _Ctx:
    def __init__(self, fir):
        self.fir = fir
        self.mentions = []
        self.relations = []
        self.events = []

    def add(self, surface, evidence, **kw):
        # reuse an existing mention for the same surface+phone inside one FIR
        for m in self.mentions:
            if m["surface"] == surface and (m.get("phone") == kw.get("phone") or not kw.get("phone") or not m.get("phone")):
                for k, v in kw.items():
                    if v and not m.get(k):
                        m[k] = v
                return m["idx"]
        m = dict(idx=len(self.mentions), surface=surface, kind=name_kind(surface), phone=None, alias=None,
                 role="mentioned", org=None, plate=None, vehicle_desc=None, location=None, evidence=evidence)
        m.update({k: v for k, v in kw.items() if v})
        self.mentions.append(m)
        return m["idx"]

    def rel(self, a, b, label):
        self.relations.append(dict(a=a, b=b, relation=label))


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[a-z0-9\)])\.\s+(?=[A-Z])", text) if s.strip()]


# primary-subject templates ----------------------------------------------------------
PRIMARY = [
    re.compile(rf"alleges that (?P<n>{NAME}){ALIAS} is involved in unlawful dealings around (?P<loc>[^.]+?)\. The number (?P<ph>{PH}) is reportedly used"),
    re.compile(rf"that (?P<n>{NAME}){ALIAS} regularly visits (?P<loc>.+?) and can be reached on (?P<ph>{PH})"),
    re.compile(rf"apprehended (?P<n>{NAME}){ALIAS} near (?P<loc>[^.]+?)\. A mobile phone \((?P<ph>{PH})\) was recovered"),
    re.compile(rf"residence of (?P<n>{NAME}){ALIAS} near (?P<loc>.+?) yielded a diary listing (?P<ph>{PH}) against the name (?P<diary>[A-Z][a-z]+)"),
]
SECONDARY = [
    (re.compile(rf"(?P<n>{NAME}) \((?:mobile )?(?P<ph>{PH})\) is described as an? (?P<rel>[a-z ]+?) of the suspect"), "assoc"),
    (re.compile(rf"suspect was seen with (?P<n>{NAME}) \((?P<ph>{PH})\), described as an? (?P<rel>[a-z ]+?)\."), "assoc"),
    (re.compile(rf"accused named (?P<n>{NAME}) \(mobile (?P<ph>{PH})\) as an? (?P<rel>[a-z ]+?)\."), "assoc"),
    (re.compile(rf"also lists (?P<n>{NAME}) at (?P<ph>{PH}), noted as an? (?P<rel>[a-z ]+?)\."), "assoc"),
]
ORG = re.compile(rf"(?P<n>{NAME}) is said to operate through (?P<org>[^.]+)\.")
VEH = re.compile(rf"travelling in an? (?P<desc>[^()]+?) \((?P<plate>{PLATE})\)")


def extract_fir(fir):
    text, fid = fir["text"], fir["fir_id"]
    c = _Ctx(fir)
    primary = None

    for rx in PRIMARY:
        m = rx.search(text)
        if m:
            g = m.groupdict()
            alias = g.get("alias") or g.get("diary")
            ev = m.group(0)
            primary = c.add(g["n"], ev, phone=norm_phone(g["ph"]), alias=alias, role="suspect", location=g["loc"].strip())
            break

    for rx, _ in SECONDARY:
        for m in rx.finditer(text):
            g = m.groupdict()
            i = c.add(g["n"], m.group(0), phone=norm_phone(g["ph"]), role="associate")
            if primary is not None:
                c.rel(primary, i, g["rel"].strip())

    for m in ORG.finditer(text):
        for mm in c.mentions:
            if mm["surface"] == m.group("n"):
                mm["org"] = m.group("org").strip()
    vm = VEH.search(text)
    if vm and primary is not None:
        c.mentions[primary]["plate"] = vm.group("plate")
        c.mentions[primary]["vehicle_desc"] = vm.group("desc")

    # ---- one-off report styles -----------------------------------------------------
    m = re.search(rf"Mobile (?P<ph>{PH}) was recovered from the accused known as (?P<nick>[A-Z][a-z]+), real name (?P<n>{NAME})", text)
    if m:
        c.add(m["n"], m.group(0), phone=norm_phone(m["ph"]), alias=m["nick"], role="suspect", shared_hint=True)
    m = re.search(rf"statement, (?P<n>{NAME}) said SIM number (?P<ph>{PH})", text)
    if m:
        c.add(m["n"], m.group(0), phone=norm_phone(m["ph"]), role="suspect", shared_hint=True)
    m = re.search(rf"Complainant (?P<n>{NAME}), an? (?P<job>[a-z ]+?) in (?P<loc>[A-Za-z ]+?) \(mobile (?P<ph>{PH})\)", text)
    if m:
        c.add(m["n"], m.group(0), phone=norm_phone(m["ph"]), role="victim", location=m["loc"])
    m = re.match(rf"(?P<n>{NAME}), an? (?P<job>[a-z ]+?) \(mobile (?P<ph>{PH})\), reported", text)
    if m:
        c.add(m["n"], m.group(0), phone=norm_phone(m["ph"]), role="victim")
    m = re.match(rf"(?P<n>{NAME}) \(mobile (?P<ph>{PH})\) (?:complained|reported)", text)
    if m:
        c.add(m["n"], m.group(0), phone=norm_phone(m["ph"]), role="victim")
        k = re.search(rf"caller number (?P<ph>{PH}) was traced to (?P<org>[^ ]+ [^ ]+ ?[A-Z]*)? and the caller introduced himself as (?P<nick>[A-Z][a-z]+)", text)
        if k:
            org = re.search(r"traced to ([A-Za-z ]+?) and", text)
            c.add(k["nick"], k.group(0), phone=norm_phone(k["ph"]), role="suspect", org=org.group(1) if org else None)
        k = re.search(r"a woman named (?P<nick>[A-Z][a-z]+) from (?P<org>[A-Za-z ]+?) called", text)
        if k:
            c.add(k["nick"], k.group(0), role="suspect", org=k["org"])
    m = re.match(rf"(?P<nick>[A-Z][a-z]+) was seen with (?P<other>[A-Z][a-z]+) near .*?\. (?P=nick) uses the number (?P<ph>{PH})", text)
    if m:
        a = c.add(m["nick"], m.group(0), phone=norm_phone(m["ph"]), role="suspect")
        b = c.add(m["other"], m.group(0), role="mentioned")
        c.rel(a, b, "seen with")
    m = re.search(rf"registered to (?P<org>[A-Za-z ]+?) was seen inside the .*? yard in (?P<loc>[A-Za-z ]+?) with (?P<nick>[A-Z][a-z]+) present", text)
    if m:
        pl = re.search(PLATE, text)
        i = c.add(m["nick"], m.group(0), role="mentioned", plate=pl.group(0) if pl else None, org=None, location=m["loc"])
        c.events.append(dict(kind="vehicle_sighting", plate=pl.group(0), org=m["org"], person=i))
    m = re.search(rf"served on (?P<n>{NAME}) of (?P<org>[A-Za-z ]+?), contact (?P<ph>{PH})", text)
    if m:
        c.add(m["n"], m.group(0), phone=norm_phone(m["ph"]), org=m["org"], role="suspect")
    m = re.search(r"caller who called himself (?P<nick>[A-Z][a-z]+) used (?P<ph>\d{10})", text)
    if m:
        c.add(m["nick"], m.group(0), phone=m["ph"], role="suspect")
    m = re.search(r"around (?P<t>\d+ [AP]M), (?P<names>.+?) were seen together in an? (?P<v>[A-Za-z ]+?) near (?P<loc>[A-Za-z ]+?)\.", text)
    if m:
        parts = [p.strip() for p in re.split(r",\s*|\s+and\s+", m["names"]) if p.strip()]
        idxs = [c.add(p, m.group(0), role="suspect", location=m["loc"]) for p in parts]
        c.events.append(dict(kind="meeting", location=m["loc"], time=m["t"], people=idxs,
                             when=re.search(r"evening of (\d+ [A-Za-z]+)", text).group(1) if re.search(r"evening of (\d+ [A-Za-z]+)", text) else None))
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                c.rel(idxs[i], idxs[j], "seen together")

    return dict(fir_id=fid, date=fir["date"], station=fir["station"], text=text,
                mentions=c.mentions, relations=c.relations, events=c.events)


def extract_all(firs):
    return [extract_fir(f) for f in firs]
