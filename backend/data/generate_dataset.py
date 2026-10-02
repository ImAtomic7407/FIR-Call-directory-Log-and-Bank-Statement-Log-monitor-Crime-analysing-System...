#!/usr/bin/env python3
"""Synthetic dataset generator for the XEST criminal-network demo.

Outputs (next to this file):
  fir.json           ~49 unstructured FIR paragraphs
  cdr.csv            call detail records (phone numbers, not names)
  transactions.csv   bank transfers (names as written, with alias variance)
  truth.json         GROUND TRUTH for testing only - the app must never read it

Planted traps: alias chains, shared burner phone, burst calling, circular and
layered transfers, a hidden small group, a sudden cross-group bridge, and a
same-tower/same-time meeting. Deterministic: same SEED -> same files.
Stdlib only.
"""
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
OUT = Path(__file__).parent
R = random.Random(SEED)

START = datetime(2026, 7, 1)
END = datetime(2026, 9, 14)
BRIDGE_DATE = datetime(2026, 8, 26)  # first G2<->G4 contact ever
MEET_DAY = datetime(2026, 8, 25)

TOWERS = {
    "T-01": "Sadar Bazaar", "T-02": "Karol Bagh", "T-03": "Nehru Place",
    "T-04": "Lajpat Nagar", "T-05": "Seelampur", "T-06": "Okhla Phase 2",
    "T-07": "Mundka Industrial Area", "T-08": "Janakpuri", "T-09": "Rohini Sector 9",
    "T-10": "Gurugram Sector 29", "T-11": "Noida Sector 62", "T-12": "Anand Vihar ISBT",
    "T-13": "Azadpur Mandi", "T-14": "Dwarka Sector 10",
}
BG_TOWERS = [t for t in TOWERS if t != "T-12"]  # T-12 is reserved for the meeting
STATIONS = ["Sadar Bazaar PS", "Karol Bagh PS", "Seelampur PS", "Okhla PS", "Mundka PS",
            "Anand Vihar PS", "Sector 29 PS Gurugram", "Sector 62 PS Noida", "Dwarka PS",
            "Azadpur PS"]
GROUP_LABEL = {
    "G1": "Rathore smuggling syndicate", "G2": "Hawala & finance network",
    "G3": "Vehicle theft ring", "G4": "Cyber-fraud call centre",
    "G5": "Extortion gang (hidden)",
}

# id, canonical, nick, group, role, home tower, org, has vehicle
CORE = [
    ("P01", "Bhuvan Rathore", "Bunty", "G1", "leader", "T-07", "Rathore Logistics", True),
    ("P02", "Ojas Dwivedi", "Oju", "G1", "lieutenant", "T-07", None, False),
    ("P03", "Yashvir Shekhawat", "Yashu", "G1", "courier", "T-01", "Rathore Logistics", True),
    ("P04", "Hemant Mittal", "Hemu", "G1", "member", "T-01", None, False),
    ("P05", "Kuldeep Khatri", "Kuldi", "G1", "financier", "T-09", None, False),
    ("P06", "Tushar Rawal", "Tushi", "G1", "member", "T-09", None, False),
    ("P07", "Chirag Bhadana", "Chiku", "G1", "courier", "T-13", "Rathore Logistics", True),
    ("P08", "Omkar Lohia", "Ommi", "G1", "member", "T-13", None, False),
    ("P09", "Devansh Baisla", "Devu", "G1", "member", "T-07", None, False),
    ("P10", "Nirmal Kashyap", "Nimmu", "G1", "member", "T-01", None, False),
    ("P11", "Jatin Singhal", "Jatinbhai", "G2", "leader", "T-02", "Singhal Traders", True),
    ("P12", "Prakhar Lodha", "Prakhu", "G2", "member", "T-02", "Singhal Traders", False),
    ("P13", "Shailesh Parikh", "Shellu", "G2", "member", "T-08", None, False),
    ("P14", "Bhupesh Mangla", "Bhupi", "G2", "member", "T-08", None, False),
    ("P15", "Ritesh Garg", "Ritz", "G2", "member", "T-02", None, False),
    ("P16", "Mayank Mathur", "Mayu", "G2", "member", "T-08", None, False),
    ("P17", "Kamlesh Ahuja", "Kammo", "G2", "member", "T-02", None, False),
    ("P18", "Vipul Bhasin", "Vippy", "G2", "member", "T-08", None, False),
    ("P19", "Zubair Pathan", "Zubi", "G3", "leader", "T-05", "Pathan Auto Parts", True),
    ("P20", "Nadeem Shaikh", "Nadu", "G3", "member", "T-05", "Pathan Auto Parts", False),
    ("P21", "Arshad Mirza", "Ashu", "G3", "member", "T-06", None, True),
    ("P22", "Tabrez Haider", "Tabbu", "G3", "member", "T-06", None, False),
    ("P23", "Faizan Khatri", "Faizu", "G3", "member", "T-05", None, True),
    ("P24", "Sohail Rizvi", "Sohu", "G3", "member", "T-06", None, False),
    ("P25", "Wasim Farooqui", "Wasu", "G3", "member", "T-05", None, False),
    ("P26", "Danish Usmani", "Danny", "G3", "member", "T-06", None, False),
    ("P27", "Ishaan Talwar", "Ishu", "G4", "leader", "T-10", "QuickConnect BPO", False),
    ("P28", "Pranav Sahni", "Pranu", "G4", "member", "T-10", "QuickConnect BPO", False),
    ("P29", "Siddhant Grover", "Siddy", "G4", "member", "T-11", "QuickConnect BPO", False),
    ("P30", "Lakshay Kohli", "Lucky", "G4", "mule", "T-11", None, False),
    ("P31", "Parth Wadhwa", "Paru", "G4", "mule", "T-10", None, False),
    ("P32", "Dhruv Bedi", "Dhruvy", "G4", "mule", "T-11", None, False),
    ("P33", "Ritika Suri", "Riti", "G4", "member", "T-10", "QuickConnect BPO", False),
    ("P34", "Tanvi Mehra", "Tanu", "G4", "member", "T-11", "QuickConnect BPO", False),
    ("P35", "Manjeet Sandhu", "Mannu", "G5", "leader", "T-14", None, True),
    ("P36", "Baljeet Sandhu", "Bally", "G5", "member", "T-14", None, False),
    ("P37", "Kulwant Brar", "Wantu", "G5", "member", "T-14", None, False),
    ("P38", "Sukhdev Grewal", "Sukhi", "G5", "member", "T-09", None, False),
]
# decoys / civilians (not part of any network)
NOISE = [
    ("N01", "Bhuvan Lohia", "Bhuvan", None, "decoy (shopkeeper, shares first name with Bhuvan Rathore)", "T-05"),
    ("N02", "Ojas Kashyap", "Ojas", None, "decoy (bank clerk, shares first name with Ojas Dwivedi)", "T-03"),
    ("N04", "Kamla Negi", "Kamla", None, "victim", "T-03"),
    ("N05", "Gopal Nair", "Gopal", None, "victim", "T-04"),
]
BURNER = "9899077700"  # one SIM attributed to three different people
BANKS = ["SBI", "HDFC", "ICICI", "PNB", "AXIS", "BOB"]
VEH_KINDS = ["white Innova", "black Scorpio", "silver Swift", "grey Bolero", "red Pulsar bike",
             "blue Eicher truck", "white Creta"]
RELS = ["associate", "business partner", "cousin", "driver", "trusted aide", "financier"]


# --------------------------------------------------------------------------- people
used_phones = {BURNER}


def new_phone():
    while True:
        ph = R.choice(["98", "99", "97", "88", "70"]) + "".join(str(R.randrange(10)) for _ in range(8))
        if ph not in used_phones:
            used_phones.add(ph)
            return ph


def plate():
    return f"DL{R.randrange(1, 10)}C{R.choice('ABCDEFGH')}{R.choice('KLMNPRST')}{R.randrange(1000, 9999)}"


persons = {}
for i, (pid, canon, nick, grp, role, home, org, has_v) in enumerate(CORE):
    last = canon.split()[-1]
    persons[pid] = dict(
        id=pid, canonical=canon, nick=nick, initial=f"{canon[0]}. {last}", group=grp, role=role,
        home=home, org=org, phones=[new_phone()], vehicle=None,
        explicit_alias=(i % 2 == 0 or pid == "P01"),  # alias stated outright in the FIR?
    )
    if has_v:
        persons[pid]["vehicle"] = dict(plate=plate(), desc=R.choice(VEH_KINDS))
for pid, canon, nick, grp, role, home in NOISE:
    last = canon.split()[-1]
    persons[pid] = dict(id=pid, canonical=canon, nick=nick, initial=f"{canon[0]}. {last}", group=None,
                        role=role, home=home, org=None, phones=[new_phone()], vehicle=None,
                        explicit_alias=False)
# hand-tuned traps
persons["P01"]["phones"].append(new_phone())          # Bunty's second phone
persons["P01"]["vehicle"] = dict(plate="DL3CAB1234", desc="white Innova")
persons["P19"]["vehicle"] = dict(plate="DL3CAB1234", desc="white Innova")  # same car, two groups
persons["P27"]["phones"].append(new_phone())          # call-centre burst phone
persons["P36"]["org"] = None
unknown_phones = [new_phone() for _ in range(12)]    # victims / customers with no identity

acct = {pid: f"{R.choice(BANKS)}-{R.randrange(10**9, 10**10)}" for pid in persons}
core_ids = [c[0] for c in CORE]


def members(g):
    return [persons[c[0]] for c in CORE if c[3] == g]


# --------------------------------------------------------------------------- FIR
fir_raw = []  # dict(date, station, text, mentions)


def form(p, kind):
    return {"full": p["canonical"], "nick": p["nick"], "init": p["initial"],
            "first": p["canonical"].split()[0]}[kind]


def fmt_phone(ph):
    s = R.choice(["plain", "plain", "plus91", "dash", "space"])
    return {"plain": ph, "plus91": f"+91 {ph}", "dash": f"{ph[:5]}-{ph[5:]}",
            "space": f"{ph[:5]} {ph[5:]}"}[s]


def rand_date(a=datetime(2026, 7, 3), b=datetime(2026, 9, 12)):
    return a + timedelta(days=R.randrange((b - a).days))


def veh_clause(p):
    v = p["vehicle"]
    return f" The suspect was travelling in a {v['desc']} ({v['plate']})." if v else ""


relations = []


def add_fir(date, station, text, mentions):
    fir_raw.append(dict(date=date, station=station, text=text, mentions=mentions))


def intro_fir(p, q):
    rel = "brother" if {p["id"], q["id"]} == {"P35", "P36"} else R.choice(RELS)
    d = rand_date()
    loc = TOWERS[p["home"]]
    pf = form(p, "full")
    alias = f" (alias {p['nick']})" if p["explicit_alias"] else ""
    qkind = R.choices(["nick", "init", "full"], weights=[6, 2.5, 1.5])[0]
    qs, qph = form(q, qkind), fmt_phone(q["phones"][0])
    ph = fmt_phone(p["phones"][0])
    org = f" {pf} is said to operate through {p['org']}." if p["org"] else ""
    ments = [dict(surface=pf, person_id=p["id"]), dict(surface=qs, person_id=q["id"])]
    if p["explicit_alias"]:
        ments.append(dict(surface=p["nick"], person_id=p["id"]))
    relations.append(dict(a=p["id"], b=q["id"], relation=rel, source="fir_intro"))
    t = R.randrange(4)
    if t == 0:
        text = (f"On {d:%d %B %Y}, acting on a tip-off, officers of {R.choice(STATIONS)} apprehended "
                f"{pf}{alias} near {loc}. A mobile phone ({ph}) was recovered from the accused.{veh_clause(p)} "
                f"During questioning the accused named {qs} (mobile {qph}) as a {rel}.{org}")
    elif t == 1:
        text = (f"A complaint registered at {R.choice(STATIONS)} alleges that {pf}{alias} is involved in "
                f"unlawful dealings around {loc}. The number {ph} is reportedly used for these dealings."
                f"{veh_clause(p)}{org} {qs} (mobile {qph}) is described as a {rel} of the suspect.")
    elif t == 2:
        text = (f"An informant told {R.choice(STATIONS)} that {pf}{alias} regularly visits {loc} and can be "
                f"reached on {ph}. The suspect was seen with {qs} ({qph}), described as a {rel}.{veh_clause(p)}{org}")
    else:
        text = (f"A search at the residence of {pf}{alias} near {loc} yielded a diary listing {ph} against "
                f"the name {form(p, 'nick')}. The diary also lists {qs} at {qph}, noted as a {rel}.{veh_clause(p)}{org}")
        ments.append(dict(surface=form(p, "nick"), person_id=p["id"]))
    add_fir(d, R.choice(STATIONS), text, ments)


for g in GROUP_LABEL:
    ms = members(g)
    for i, p in enumerate(ms):
        intro_fir(p, ms[(i + 1) % len(ms)])  # everyone is the 'associate' of someone -> nick+phone evidence

P = persons
# alias chain for Bhuvan: Bunty <-> phone2 <-> B. Rathore <-> Rathore Logistics
add_fir(datetime(2026, 8, 6), "Mundka PS",
        f"Bunty was seen with Ojas near the market in Mundka, loading cartons into a vehicle at night. "
        f"Bunty uses the number {fmt_phone(P['P01']['phones'][1])}.",
        [dict(surface="Bunty", person_id="P01"),
         dict(surface="Ojas", person_id="P02", ambiguous=True, candidates=["P02", "N02"])])
add_fir(datetime(2026, 8, 19), "Mundka PS",
        f"A notice was served on B. Rathore of Rathore Logistics, contact {fmt_phone(P['P01']['phones'][1])}, "
        f"regarding unexplained cash deposits and unregistered consignments.",
        [dict(surface="B. Rathore", person_id="P01")])
# the meeting
add_fir(datetime(2026, 8, 27), "Anand Vihar PS",
        "An informant reported that on the evening of 25 August around 7 PM, Bunty, Jatinbhai, Zubi and "
        "I. Talwar were seen together in a white Innova near Anand Vihar ISBT. The four spoke for about "
        "thirty minutes before dispersing in different directions.",
        [dict(surface="Bunty", person_id="P01"), dict(surface="Jatinbhai", person_id="P11"),
         dict(surface="Zubi", person_id="P19"), dict(surface="I. Talwar", person_id="P27")])
# the burner SIM attributed to three different people
add_fir(datetime(2026, 7, 20), "Azadpur PS",
        f"Mobile {BURNER} was recovered from the accused known as Ommi, real name Omkar Lohia, at Azadpur Mandi. "
        f"He claimed the SIM was bought from a street dealer.",
        [dict(surface="Ommi", person_id="P08"), dict(surface="Omkar Lohia", person_id="P08")])
add_fir(datetime(2026, 8, 9), "Okhla PS",
        f"In his statement, Arshad Mirza said SIM number {BURNER} was handed to him by a dealer at Okhla and "
        f"that he uses it for calls about stolen vehicles.",
        [dict(surface="Arshad Mirza", person_id="P21")])
add_fir(datetime(2026, 9, 1), "Sector 62 PS Noida",
        f"A victim complained that a caller who called himself Siddy used {BURNER} to demand an OTP and "
        f"then withdrew money from the victim's account.",
        [dict(surface="Siddy", person_id="P29")])
# decoys with shared first names
add_fir(datetime(2026, 8, 2), "Seelampur PS",
        f"Complainant Bhuvan Lohia, a shopkeeper in Seelampur (mobile {fmt_phone(P['N01']['phones'][0])}), "
        f"reported that his scooter was stolen from outside his shop on the previous night.",
        [dict(surface="Bhuvan Lohia", person_id="N01")])
add_fir(datetime(2026, 8, 11), "Nehru Place PS",
        f"Ojas Kashyap, a bank clerk (mobile {fmt_phone(P['N02']['phones'][0])}), reported repeated "
        f"suspicious calls from an unknown number asking for his card details.",
        [dict(surface="Ojas Kashyap", person_id="N02")])
# shared vehicle across two groups
add_fir(datetime(2026, 8, 14), "Seelampur PS",
        "A white Innova (DL3CAB1234) registered to Rathore Logistics was seen inside the Pathan Auto Parts "
        "yard in Seelampur with Zubi present.",
        [dict(surface="Zubi", person_id="P19")])
# victims tied to the call-centre burst phone
add_fir(datetime(2026, 9, 2), "Nehru Place PS",
        f"Kamla Negi (mobile {fmt_phone(P['N04']['phones'][0])}) complained that on 30 August she lost "
        f"Rs 1,20,000 after a caller posing as a bank manager phoned her. The caller number {fmt_phone(P['P27']['phones'][1])} "
        f"was traced to QuickConnect BPO and the caller introduced himself as Ishu.",
        [dict(surface="Kamla Negi", person_id="N04"), dict(surface="Ishu", person_id="P27")])
add_fir(datetime(2026, 9, 3), "Lajpat Nagar PS",
        f"Gopal Nair (mobile {fmt_phone(P['N05']['phones'][0])}) reported that a woman named Riti from "
        f"QuickConnect BPO called him on 30 August and persuaded him to share an OTP.",
        [dict(surface="Gopal Nair", person_id="N05"), dict(surface="Riti", person_id="P33")])

fir_raw.sort(key=lambda f: (f["date"], f["station"]))
firs, fir_truth = [], {}
for i, f in enumerate(fir_raw, 1):
    fid = f"FIR-{i:03d}"
    firs.append(dict(fir_id=fid, date=f["date"].strftime("%Y-%m-%d"), station=f["station"], text=f["text"]))
    fir_truth[fid] = f["mentions"]


# --------------------------------------------------------------------------- CDR
HOUR_W = [1, 1, 1, 1, 1, 2, 4, 6, 8, 9, 9, 9, 8, 8, 9, 9, 9, 9, 9, 8, 6, 4, 3, 2]
NIGHT_W = [5, 4, 3, 2, 1, 1, 1, 2, 3, 4, 4, 5, 5, 5, 5, 6, 6, 7, 8, 9, 10, 10, 9, 7]
calls = []


def rand_ts(a=START, b=END, night=False):
    day = R.randrange((b - a).days)
    h = R.choices(range(24), weights=NIGHT_W if night else HOUR_W)[0]
    return a + timedelta(days=day, hours=h, minutes=R.randrange(60), seconds=R.randrange(60))


def rand_dur():
    return int(min(1500, max(8, R.lognormvariate(4.6, 0.8))))


def bg_tower(p):
    return p["home"] if R.random() < 0.65 else R.choice(BG_TOWERS)


def call(a_ph, b_ph, ts, dur, tower, tag=None):
    calls.append(dict(caller=a_ph, receiver=b_ph, ts=ts, dur=dur, tower=tower, tag=tag))


def group_edges(ms):
    E = set()
    for i, m in enumerate(ms[1:], 1):
        if R.random() < 0.6:
            E.add((ms[0]["id"], m["id"]))
        for o in R.sample([x for x in ms if x is not m], 2):
            E.add(tuple(sorted((m["id"], o["id"]))))
    E.add((ms[0]["id"], ms[1]["id"]))
    return [(P[a], P[b]) for a, b in sorted(E)]


INTRA = {"G1": 95, "G2": 55, "G3": 50, "G4": 40, "G5": 22}
g_edges = {g: group_edges(members(g)) for g in GROUP_LABEL}
for g, n in INTRA.items():
    for _ in range(n):
        a, b = R.choice(g_edges[g])
        if R.random() < 0.5:
            a, b = b, a
        call(a["phones"][0], b["phones"][0], rand_ts(night=g in ("G1", "G5")), rand_dur(), bg_tower(a))
for _ in range(6):  # Bunty's second phone also used normally
    b = P[R.choice(["P02", "P03", "P04"])]
    call(P["P01"]["phones"][1], b["phones"][0], rand_ts(night=True), rand_dur(), bg_tower(P["P01"]))

for a, b, n in [("P01", "P11", 14), ("P01", "P19", 10), ("P11", "P19", 6), ("P05", "P14", 5),
                ("P22", "P07", 4), ("P38", "P08", 2)]:
    for _ in range(n):
        x, y = (P[a], P[b]) if R.random() < 0.5 else (P[b], P[a])
        call(x["phones"][0], y["phones"][0], rand_ts(), rand_dur(), bg_tower(x))
# sudden bridge: G4 has NEVER contacted G2 before 26 Aug
for a, b, n in [("P27", "P11", 9), ("P28", "P12", 6), ("P29", "P13", 4)]:
    for _ in range(n):
        x, y = (P[a], P[b]) if R.random() < 0.5 else (P[b], P[a])
        call(x["phones"][0], y["phones"][0], rand_ts(BRIDGE_DATE, END), rand_dur(), bg_tower(x), "bridge")
# burst 1: Bunty's second phone, 16 short calls in ~18 minutes at night
t0 = datetime(2026, 8, 14, 23, 5, 10)
targets = [P[i] for i in ["P02", "P03", "P04", "P05", "P06", "P07"]]
for k in range(16):
    call(P["P01"]["phones"][1], targets[k % 6]["phones"][0], t0 + timedelta(seconds=k * 68 + R.randrange(30)),
         R.randrange(4, 26), "T-07", "burst_P01")
# burst 2: call-centre boss dials victims, 25 calls in ~32 minutes
victims = [P["N04"]["phones"][0], P["N05"]["phones"][0]] + unknown_phones[:8]
t0 = datetime(2026, 8, 30, 14, 10, 0)
for k in range(25):
    call(P["P27"]["phones"][1], victims[k % len(victims)], t0 + timedelta(seconds=k * 75 + R.randrange(40)),
         R.randrange(20, 180), "T-10", "burst_P27")
# meeting: four leaders on tower T-12 within 25 minutes
for pid, other, minute in [("P01", "P03", 5), ("P11", "P12", 12), ("P19", "P20", 20), ("P27", "P28", 27)]:
    call(P[pid]["phones"][0], P[other]["phones"][0], MEET_DAY + timedelta(hours=19, minutes=minute),
         R.randrange(25, 70), "T-12", "coloc")
# ordinary victim / customer traffic
for _ in range(30):
    m = R.choice(members("G4"))
    call(m["phones"][0], R.choice(victims + unknown_phones), rand_ts(), R.randrange(60, 600), bg_tower(m))
for _ in range(40):
    m = P[R.choice(core_ids)]
    u = R.choice(unknown_phones)
    a, b = (m["phones"][0], u) if R.random() < 0.5 else (u, m["phones"][0])
    call(a, b, rand_ts(), rand_dur(), bg_tower(m))
call(unknown_phones[0], P["N02"]["phones"][0], datetime(2026, 8, 10, 11, 20), 33, "T-03")
call(unknown_phones[0], P["N02"]["phones"][0], datetime(2026, 8, 10, 15, 2), 41, "T-03")

calls.sort(key=lambda c: c["ts"])
for i, c in enumerate(calls, 1):
    c["id"] = f"C{i:04d}"

# --------------------------------------------------------------------------- transactions
txns = []


def nm(p):
    return R.choices([p["canonical"], p["nick"], p["initial"]], weights=[65, 25, 10])[0]


def tx(s, r, amt, day, mode=None, tag=None, note=""):
    ts = day + timedelta(hours=R.randrange(8, 21), minutes=R.randrange(60))
    txns.append(dict(s=P[s], r=P[r], amt=amt, ts=ts, mode=mode or R.choice(["UPI", "IMPS", "NEFT"]),
                     tag=tag, note=note))


def rdate():
    return datetime(2026, 7, 1) + timedelta(days=R.randrange(75))


# G1 internal: seven large ones (demo query: > Rs 50,000 between Group 1 members)
for s, r, a, d in [("P05", "P01", 150000, (7, 22)), ("P01", "P02", 85000, (8, 3)), ("P01", "P03", 60000, (8, 9)),
                   ("P05", "P07", 72000, (8, 16)), ("P08", "P05", 55000, (8, 28)), ("P02", "P05", 98000, (9, 4)),
                   ("P01", "P09", 52000, (9, 8))]:
    tx(s, r, a, datetime(2026, *d), tag="g1_big")
for _ in range(8):
    a, b = R.choice(g_edges["G1"])
    tx(a["id"], b["id"], R.choice([5000, 8000, 12000, 20000, 25000, 40000]), rdate())
# laundering G1 -> G2 and G3 -> G2
for s, r, a in [("P01", "P11", 250000), ("P01", "P11", 180000), ("P01", "P11", 300000), ("P01", "P11", 220000),
                ("P05", "P11", 140000), ("P05", "P11", 160000), ("P05", "P12", 90000),
                ("P19", "P11", 120000), ("P19", "P11", 135000), ("P19", "P12", 75000), ("P19", "P12", 80000),
                ("P25", "P15", 45000)]:
    tx(s, r, a, rdate(), mode="Cash Deposit" if s in ("P01", "P05") else None)
# G2 internal noise (cycles added separately)
for _ in range(18):
    a, b = R.choice(g_edges["G2"])
    tx(a["id"], b["id"], R.randrange(10, 90) * 1000, rdate())
for g, n in [("G3", 12), ("G4", 12)]:
    for _ in range(n):
        a, b = R.choice(g_edges[g])
        tx(a["id"], b["id"], R.randrange(8, 45) * 1000, rdate())
# hidden extortion gang: collections flow up to the Sandhu brothers
for s, r, a in [("P37", "P35", 35000), ("P37", "P35", 42000), ("P38", "P36", 28000),
                ("P38", "P35", 60000), ("P36", "P35", 50000), ("P37", "P36", 22000)]:
    tx(s, r, a, rdate(), mode="Cash Deposit")
# circular #1: 3-hop inside G2, three consecutive days, amounts barely shrink
for s, r, a, d in [("P11", "P13", 95000, 10), ("P13", "P16", 92000, 11), ("P16", "P11", 89500, 12)]:
    tx(s, r, a, datetime(2026, 8, d), tag="cycle3")
# circular #2: 4-hop across G1 -> G2 -> G3 -> G1
for s, r, a, d in [("P05", "P14", 320000, 18), ("P14", "P22", 310000, 19), ("P22", "P07", 300000, 20),
                   ("P07", "P05", 295000, 21)]:
    tx(s, r, a, datetime(2026, 8, d), tag="cycle4")
# layering: call-centre boss splits Rs 4.8L across mules, mules forward to Jatin
for m, d in [("P30", 31), ("P31", 31), ("P32", 31)]:
    tx("P27", m, 160000, datetime(2026, 8, d), tag="layer")
for m, d in [("P30", (9, 1)), ("P31", (9, 1)), ("P32", (9, 2))]:
    tx(m, "P11", 155000, datetime(2026, *d), tag="layer")
# bridge money: first G4 <-> G2 transfers happen only after the meeting
tx("P27", "P11", 200000, datetime(2026, 8, 29), tag="bridge")
tx("P11", "P27", 40000, datetime(2026, 9, 6), tag="bridge")
# a little background noise
for _ in range(14):
    s, r = R.sample(core_ids, 2)
    if P[s]["group"] == P[r]["group"] or {P[s]["group"], P[r]["group"]} in ({"G2", "G4"}, {"G4", "G1"}, {"G4", "G3"}, {"G4", "G5"}):
        continue
    tx(s, r, R.randrange(5, 60) * 100, rdate())

txns.sort(key=lambda t: t["ts"])
for i, t in enumerate(txns, 1):
    t["id"] = f"T{i:04d}"

# --------------------------------------------------------------------------- write
with open(OUT / "fir.json", "w") as f:
    json.dump(firs, f, indent=2, ensure_ascii=False)

with open(OUT / "cdr.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["call_id", "caller", "receiver", "timestamp", "duration_sec", "tower_id", "tower_location"])
    for c in calls:
        w.writerow([c["id"], c["caller"], c["receiver"], c["ts"].strftime("%Y-%m-%d %H:%M:%S"), c["dur"],
                    c["tower"], TOWERS[c["tower"]]])

with open(OUT / "transactions.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["txn_id", "sender", "receiver", "sender_account", "receiver_account", "amount_inr", "date",
                "time", "mode"])
    for t in txns:
        w.writerow([t["id"], nm(t["s"]), nm(t["r"]), acct[t["s"]["id"]], acct[t["r"]["id"]], t["amt"],
                    t["ts"].strftime("%Y-%m-%d"), t["ts"].strftime("%H:%M"), t["mode"]])


def ids(items, tag):
    return [x["id"] for x in items if x["tag"] == tag]


truth = dict(
    note="GROUND TRUTH FOR TESTING ONLY. The application must not read this file.",
    groups=GROUP_LABEL,
    persons={p["id"]: dict(canonical=p["canonical"], aliases=[p["nick"], p["initial"]], group=p["group"],
                           role=p["role"], phones=p["phones"], org=p["org"], vehicle=p["vehicle"],
                           account=acct[p["id"]], alias_stated_explicitly=p["explicit_alias"])
             for p in persons.values()},
    unresolved_phones=unknown_phones,
    fir_mentions=fir_truth,
    relations=relations,
    patterns=dict(
        burst_calling=[
            dict(person="P01", phone=P["P01"]["phones"][1], call_ids=ids(calls, "burst_P01"), date="2026-08-14"),
            dict(person="P27", phone=P["P27"]["phones"][1], call_ids=ids(calls, "burst_P27"), date="2026-08-30")],
        circular_transfers=[
            dict(kind="3-hop", persons=["P11", "P13", "P16"], txn_ids=ids(txns, "cycle3")),
            dict(kind="4-hop", persons=["P05", "P14", "P22", "P07"], txn_ids=ids(txns, "cycle4"))],
        layering=dict(source="P27", mules=["P30", "P31", "P32"], sink="P11", txn_ids=ids(txns, "layer")),
        shared_phone=dict(phone=BURNER, persons=["P08", "P21", "P29"], note="different people - do NOT merge"),
        shared_vehicle=dict(plate="DL3CAB1234", persons=["P01", "P19"]),
        bridge=dict(groups=["G2", "G4"], first_contact="2026-08-26",
                    call_ids=ids(calls, "bridge"), txn_ids=ids(txns, "bridge")),
        colocation=dict(tower="T-12", date="2026-08-25", window="19:00-19:30",
                        persons=["P01", "P11", "P19", "P27"], call_ids=ids(calls, "coloc")),
        g1_transfers_over_50k=ids(txns, "g1_big"),
    ),
    resolution_traps=dict(
        merge=[["P01: Bhuvan Rathore / Bunty / B. Rathore (linked by phone2 + Rathore Logistics)"]],
        do_not_merge=["Bhuvan Lohia (N01) vs Bhuvan Rathore (P01)", "Ojas Kashyap (N02) vs Ojas Dwivedi (P02)",
                      f"{BURNER} is shared by P08/P21/P29 but they are three people"],
        ambiguous_mentions=[m for ms in fir_truth.values() for m in ms if m.get("ambiguous")],
    ),
)
with open(OUT / "truth.json", "w") as f:
    json.dump(truth, f, indent=2, ensure_ascii=False)

# --------------------------------------------------------------------------- self-check
assert 30 <= len(firs) <= 50, len(firs)
digits = "".join(c for c in " ".join(x["text"] for x in firs) if c.isdigit())
for pid in core_ids:
    assert persons[pid]["phones"][0] in digits, f"{pid} phone missing from FIRs"
b = [c for c in calls if c["tag"] == "burst_P01"]
assert len(b) == 16 and (max(c["ts"] for c in b) - min(c["ts"] for c in b)).seconds < 25 * 60
g_of = {p["phones"][i]: p["group"] for p in persons.values() for i in range(len(p["phones"]))}
early = [c for c in calls if {g_of.get(c["caller"]), g_of.get(c["receiver"])} == {"G2", "G4"} and c["ts"] < BRIDGE_DATE]
assert not early, "G2<->G4 contact before the bridge date"
early_t = [t for t in txns if {t["s"]["group"], t["r"]["group"]} == {"G2", "G4"} and t["ts"] < BRIDGE_DATE]
assert not early_t, "G2<->G4 money before the bridge date"
big = [t for t in txns if t["s"]["group"] == "G1" == t["r"]["group"] and t["amt"] > 50000]
assert len(big) >= 6

print(f"FIR paragraphs : {len(firs)}")
print(f"CDR records    : {len(calls)}")
print(f"Transactions   : {len(txns)}")
print(f"Core persons   : {len(CORE)}  (+{len(NOISE)} decoys/victims, {len(unknown_phones)} unidentified phones)")
print(f"G1 transfers > Rs 50,000 between members: {len(big)}")
print("Self-check passed. Files written to", OUT)
