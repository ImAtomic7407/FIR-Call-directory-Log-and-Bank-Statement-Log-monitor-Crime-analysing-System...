"""Load CDR + transactions and attach resolved entity ids (phones -> people, accounts -> people)."""
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd

DATA = Path(__file__).parent / "data"


def load_raw():
    cdr = pd.read_csv(DATA / "cdr.csv", dtype={"caller": str, "receiver": str})
    cdr["ts"] = pd.to_datetime(cdr["timestamp"])
    tx = pd.read_csv(DATA / "transactions.csv", dtype={"sender_account": str, "receiver_account": str})
    tx["ts"] = pd.to_datetime(tx["date"] + " " + tx["time"])
    return cdr, tx


def attach_entities(R, cdr, tx):
    """Adds caller_ent/receiver_ent (None = unidentified phone) and sender_ent/receiver_ent to tx.
    Returns (cdr, tx, extra_entities, account_owner, account_conflicts)."""
    cdr = cdr.copy()
    cdr["caller_ent"] = cdr["caller"].map(R.phone_owner)
    cdr["receiver_ent"] = cdr["receiver"].map(R.phone_owner)
    for c in ("caller_ent", "receiver_ent"):
        cdr[c] = cdr[c].astype(object).where(cdr[c].notna(), None)

    # accounts -> entity: stable account numbers tie together name variants (Bhuvan Rathore / Bunty / B. Rathore)
    names_by_acct = defaultdict(Counter)
    for side in ("sender", "receiver"):
        for n, a in zip(tx[side], tx[f"{side}_account"]):
            names_by_acct[a][n] += 1
    acct_owner, conflicts, extra = {}, {}, {}
    for a, names in names_by_acct.items():
        votes = Counter()
        for n, c in names.items():
            e = R.lookup_name(n)
            if e:
                votes[e] += c
        if len(votes) > 1:
            conflicts[a] = dict(votes)
        if votes:
            acct_owner[a] = votes.most_common(1)[0][0]
        else:
            # nobody in the FIRs matches this account holder: keep as a bank-only identity
            best = max(names, key=lambda n: (len(n.split()), names[n]))
            eid = f"X{len(extra) + 1:03d}"
            extra[eid] = dict(id=eid, type="person", name=best, aliases=sorted(set(names) - {best}), phones=[], phone_evidence={},
                              orgs=[], plates=[], locations=[], role="mentioned", firs=[], links=[], confidence=0.5,
                              source="transactions")
            acct_owner[a] = eid
    tx = tx.copy()
    tx["sender_ent"] = tx["sender_account"].map(acct_owner)
    tx["receiver_ent"] = tx["receiver_account"].map(acct_owner)
    accounts_of = defaultdict(set)
    for a, e in acct_owner.items():
        accounts_of[e].add(a)
    return cdr, tx, extra, accounts_of, conflicts
