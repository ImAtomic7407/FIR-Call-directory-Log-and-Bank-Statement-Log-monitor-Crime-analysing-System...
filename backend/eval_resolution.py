"""Score entity resolution against truth.json (testing only; the app never imports this)."""
import json, itertools
from extract import extract_all
from resolve import resolve

firs = json.load(open("data/fir.json"))
truth = json.load(open("data/truth.json"))
R = resolve(extract_all(firs))
gold = {}
for fid, ms in truth["fir_mentions"].items():
    for x in ms:
        gold[(fid, x["surface"])] = x["person_id"]
pred = {}
for mid, eid in R.mention_entity.items():
    fid, idx = mid.split("#")
    surf = R.mentions[mid]["surface"]
    if (fid, surf) in gold:
        pred[(fid, surf)] = eid
keys = [k for k in gold if k in R.mentions_by_key] if False else [k for k in gold if any(R.mentions[m]["fir_id"] == k[0] and R.mentions[m]["surface"] == k[1] for m in R.mentions)]
tp = fp = fn = 0
wrong = []
for a, b in itertools.combinations(keys, 2):
    g = gold[a] == gold[b]
    p = a in pred and b in pred and pred[a] == pred[b]
    if g and p: tp += 1
    elif p and not g: fp += 1; wrong.append(("FALSE MERGE", a, b))
    elif g and not p: fn += 1; wrong.append(("MISSED", a, b))
print(f"pairs: TP={tp} FP={fp} FN={fn}  precision={tp/(tp+fp or 1):.3f} recall={tp/(tp+fn or 1):.3f}")
for w in wrong[:25]: print(w)
print("unresolved:", [(u['fir_id'], u['surface'], u['candidates'], u['leading_candidate']) for u in R.unresolved])
print("shared phones:", {p: [(x['surface'], x['fir_id']) for x in v] for p, v in R.shared_phones.items()})
print("entities:", len(R.entities), "(truth persons+noise:", len(truth['persons']) + 4, ")")
