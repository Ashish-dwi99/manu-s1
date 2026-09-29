"""Assemble Nyaya-S1 v0's train / dev / test files in JevK5's item format.

  uv run --with pyyaml python -m nyaya.assemble --teacher data/hc/teacher.jsonl

Sources:
  - rules:   the calculator-labelled generators (nyaya/rules.py); separate seeds for train, dev and test.
  - hc:      High Court orders labelled by the teacher (both passes agree) or, for how a case was disposed of,
             by the court's own metadata where its wording maps to one label unambiguously (cis). Split by CNR.
  - replay:  general decisions from the earlier Plumb fine-tune mix (non-Tura sources), so the base keeps its
             general strength.
Test sets never enter training: test_rules, test_hc (held-out CNRs) and test_cbi (the owner's real case file).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import Counter, defaultdict

from nyaya import rules
from nyaya.items import ROOT, bank, make_item

OUT = os.path.join(ROOT, "data", "final")
REPLAY = os.path.expanduser("~/Desktop/tura-s1-data/general/jevk5/train.jsonl")
PARTY_NOTE = {"SRV.APR.01": "Party asked about: the respondent (respondent No. 1 where there are several)."}
PER_LABEL_CAP = 1200


def map_disposal(raw: str) -> str | None:
    r = " ".join(raw.lower().replace("off", "of").split())
    if not r:
        return None
    if "prosecution" in r or "default" in r or "non compliance" in r or "non-compliance" in r:
        return "dismissed_for_default"
    if "withdrawn" in r:
        return "dismissed_as_withdrawn"
    if "infructuous" in r or "infractuous" in r:
        return "infructuous"
    if "abated" in r:
        return "abated"
    if "partly" in r:
        return "partly_allowed"
    if r.startswith("allowed") or r == "allowed and remanded":
        return "allowed"
    if r == "dismissed":
        return "dismissed_on_merits"
    if r.startswith("transfer"):
        return "transferred"
    if "compromise" in r or "settled" in r:
        return "compromised_or_settled"
    if "acquit" in r:
        return "acquitted"
    if "convict" in r:
        return "convicted"
    if "compounded" in r:
        return "compounded"
    return None   # disposed, ordered, granted, closed, modified, rejected, dropped, delay condoned: read from the text


def split_of(cnr: str) -> str:
    h = int(hashlib.sha256(cnr.encode()).hexdigest()[:8], 16) % 100
    return "train" if h < 85 else "dev" if h < 90 else "test"


def hc_items(path: str, B: dict) -> tuple[dict[str, list], Counter]:
    out, stats = defaultdict(list), Counter()
    for line in open(path):
        r = json.loads(line)
        split = split_of(r["cnr"])
        a, b = r["a"], r["b"]
        agreed = {q: a[q] for q in r["qids"] if q in a and a.get(q) == b.get(q)}
        stats["prompts"] += 1
        for q in r["qids"]:
            stats[f"{q}:asked"] += 1
            if q in agreed:
                stats[f"{q}:agreed"] += 1
        not_final = agreed.get("ORD.TYP.01") not in (None, "final_disposal")
        for q, label in agreed.items():
            if q == "ORD.OUT.01":
                continue
            it = make_item(B[q], r["state"], label, source=f"hc/{q}", item_id=f"{r['key']}:{q}", note=PARTY_NOTE.get(q, ""))
            if it:
                out[split].append(it)
        if "ORD.OUT.01" in r["qids"] and not not_final:
            mapped = map_disposal(r.get("disposal_raw", ""))
            label, src = (mapped, "cis") if mapped else (agreed.get("ORD.OUT.01"), "teacher")
            if mapped and agreed.get("ORD.OUT.01"):
                stats["ORD.OUT.01:cis_teacher_" + ("agree" if agreed["ORD.OUT.01"] == mapped else "disagree")] += 1
            if label:
                it = make_item(B["ORD.OUT.01"], r["state"], label, source=f"hc/ORD.OUT.01/{src}", item_id=f"{r['key']}:out")
                if it:
                    out[split].append(it)
    return out, stats


def cap(items: list[dict], rng: random.Random, limit: int = PER_LABEL_CAP) -> list[dict]:
    by = defaultdict(list)
    for it in items:
        by[(it["bank_id"], it["label_name"])].append(it)
    kept = []
    for v in by.values():
        rng.shuffle(v)
        kept += v[:limit]
    return kept


def write(name: str, rows: list[dict]) -> None:
    with open(os.path.join(OUT, name), "w") as h:
        for r in rows:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--rules_train", type=int, default=700)
    ap.add_argument("--replay", type=int, default=3000)
    ap.add_argument("--cap", type=int, default=PER_LABEL_CAP)
    a = ap.parse_args()
    B, rng = bank(), random.Random(11)
    os.makedirs(OUT, exist_ok=True)

    rule = {"train": [], "dev": [], "test": []}
    for bid in rules.GENERATORS:
        for split, n, seed in (("train", a.rules_train, 1), ("dev", 50, 2), ("test", 100, 3)):
            for j, (state, label) in enumerate(rules.generate(bid, n, seed)):
                it = make_item(B[bid], state, label, source=f"rules/{bid}", item_id=f"rule:{bid}:{split}:{j}",
                               note=("" if bid != "HRG.ADJ.01" else "Answer for the party named at the end of the record."))
                if it:
                    rule[split].append(it)

    hc, stats = hc_items(a.teacher, B)
    replay = [json.loads(l) for l in open(REPLAY)]
    replay = [r for r in replay if not r["source"].startswith("tura")]
    replay = rng.sample(replay, min(a.replay, len(replay)))

    train = cap(hc["train"], rng, a.cap) + rule["train"] + replay
    rng.shuffle(train)
    dev = hc["dev"] + rule["dev"]
    write("train.jsonl", train)
    write("dev.jsonl", dev)
    write("test_rules.jsonl", rule["test"])
    write("test_hc.jsonl", hc["test"])
    summary = {"train": len(train), "dev": len(dev), "test_rules": len(rule["test"]), "test_hc": len(hc["test"]),
               "train_by_source": Counter(r["source"].split("/")[0] + "/" + r.get("bank_id", r["source"]) for r in train).most_common(),
               "teacher": dict(stats)}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "train_by_source"}, indent=1))


if __name__ == "__main__":
    main()
