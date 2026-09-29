"""Nyaya-S1 v1 data: v0's files plus the two fixes the real case asked for.

  uv run --with pyyaml python -m nyaya.assemble_v1 --teacher_apr data/hc/teacher_apr.jsonl

  - REG.SPL.01 (special-court statute): a rule generator (section headers in the forms courts write them -> statute).
  - SRV.APR.01 (appearance): relabelled by the teacher with mutually exclusive labels (both passes agree); the old,
    ambiguous items are removed from every split.
  - Replay: 5,000 items of v0's training set, so continuing from v0 does not forget what it learned.
Splits follow v0 (by CNR); the owner's real case stays test only.
"""
from __future__ import annotations

import argparse
import json
import os
import random

from nyaya import rules
from nyaya.assemble import cap, split_of
from nyaya.items import ROOT, bank, make_item

V0, OUT = os.path.join(ROOT, "data", "final"), os.path.join(ROOT, "data", "final_v1")
NOTE = "Party asked about: the respondent (respondent No. 1 where there are several)."


def read(path: str) -> list[dict]:
    return [json.loads(l) for l in open(path)]


def write(name: str, rows: list[dict]) -> None:
    with open(os.path.join(OUT, name), "w") as h:
        for r in rows:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher_apr", required=True)
    ap.add_argument("--replay", type=int, default=5000)
    a = ap.parse_args()
    B, rng = bank(), random.Random(21)
    os.makedirs(OUT, exist_ok=True)

    spl = {split: [make_item(B[bid], s, l, source=f"rules/{bid}", item_id=f"rule:{bid}:{split}:{j}")
                   for bid, k in (("REG.SPL.01", 1), ("SRV.APR.01", 1.2))
                   for j, (s, l) in enumerate(rules.generate(bid, int(n * k), seed))]
           for split, n, seed in (("train", 500, 1), ("dev", 50, 2), ("test", 100, 3))}

    apr = {"train": [], "dev": [], "test": []}
    agree = asked = 0
    for line in open(a.teacher_apr):
        r = json.loads(line)
        asked += 1
        x, y = r["a"].get("SRV.APR.01"), r["b"].get("SRV.APR.01")
        if x and x == y:
            agree += 1
            it = make_item(B["SRV.APR.01"], r["state"], x, source="hc/SRV.APR.01", item_id=f"{r['key']}:apr", note=NOTE)
            if it:
                apr[split_of(r["cnr"])].append(it)

    old = lambda rows: [r for r in rows if r.get("bank_id") != "SRV.APR.01"]   # noqa: E731
    v0_train = old(read(os.path.join(V0, "train.jsonl")))
    train = spl["train"] + cap(apr["train"], rng, 700) + rng.sample(v0_train, min(a.replay, len(v0_train)))
    rng.shuffle(train)
    dev = old(read(os.path.join(V0, "dev.jsonl"))) + apr["dev"] + spl["dev"]
    write("train.jsonl", train)
    write("dev.jsonl", dev)
    write("test_rules.jsonl", read(os.path.join(V0, "test_rules.jsonl")) + spl["test"])
    write("test_hc.jsonl", old(read(os.path.join(V0, "test_hc.jsonl"))) + apr["test"])
    write("test_cbi.jsonl", read(os.path.join(V0, "test_cbi.jsonl")))
    from collections import Counter
    summary = {"train": len(train), "dev": len(dev), "apr_agreement": f"{agree}/{asked}",
               "apr_labels": Counter(i["label_name"] for s in apr.values() for i in s),
               "rule_labels": Counter(f'{i["bank_id"]}:{i["label_name"]}' for i in spl["train"])}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=dict)
    print(json.dumps(summary, indent=1, default=dict))


if __name__ == "__main__":
    main()
