"""Pipeline: FIR text -> mentions -> resolved entities; CDR/transactions -> entity-attached tables."""
import json
from pathlib import Path
from extract import extract_all
from resolve import resolve
from ingest import DATA, load_raw, attach_entities

CACHE = Path(__file__).parent / "cache"


class Analysis:
    def __init__(self, extractor=None, live_firs=None, known=None):
        """live_firs: FIRs filed at runtime (same schema as fir.json). known: previous entities, used so
        free-text live FIRs can be matched to people already in the system (live.loose_augment)."""
        self.base_firs = json.load(open(DATA / "fir.json"))
        self.live_firs = list(live_firs or [])
        self.firs = self.base_firs + self.live_firs
        self.fir_by_id = {f["fir_id"]: f for f in self.firs}
        # extractor can be swapped for the LLM one (llm.py); default = deterministic rules
        self.extracted = (extractor or extract_all)(self.firs)
        if self.live_firs:
            from live import loose_augment
            live_ids = {f["fir_id"] for f in self.live_firs}
            for ex in self.extracted:
                if ex["fir_id"] in live_ids:
                    loose_augment(ex, known or {})
        self.R = resolve(self.extracted)
        cdr, tx = load_raw()
        self.cdr, self.tx, extra, self.accounts_of, self.account_conflicts = attach_entities(self.R, cdr, tx)
        self.entities = {**self.R.entities, **extra}
        for eid, e in self.entities.items():
            e["accounts"] = sorted(self.accounts_of.get(eid, []))
        self.t_min = min(self.cdr.ts.min(), self.tx.ts.min())
        self.t_max = max(self.cdr.ts.max(), self.tx.ts.max())
        self._graphs = {}

    def name(self, eid):
        e = self.entities.get(eid)
        return e["name"] if e else eid
