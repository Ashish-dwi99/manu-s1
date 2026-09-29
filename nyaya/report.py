"""Before/after report per test set and per decision type, next to the majority-answer baseline.

  python -m nyaya.report   (reads data/final/results.json and the test files)

A skewed decision (most orders impose no costs) can score high by always giving the common answer; the majority
column is the floor every number has to be read against.
"""
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL = os.path.join(ROOT, "data", "final")


def majority(path: str) -> dict[str, tuple[int, float]]:
    by = defaultdict(Counter)
    for line in open(path):
        r = json.loads(line)
        by[r.get("bank_id", r["source"])][r["expected"]] += 1
    out = {k: (sum(c.values()), c.most_common(1)[0][1] / sum(c.values())) for k, c in by.items()}
    allc = sum(n for n, _ in out.values())
    out["ALL"] = (allc, sum(n * m for n, m in out.values()) / allc)
    return out


def main() -> None:
    import sys
    global FINAL
    if len(sys.argv) > 1:
        FINAL = os.path.join(ROOT, "data", sys.argv[1])
    res = json.load(open(os.path.join(FINAL, "results.json")))
    print(f"base: {res['base']}  (dev: {json.dumps(res['bases'])})  temperature {res.get('temperature')}  "
          f"training {res.get('train_minutes')} min\n")
    for split in ("test_rules", "test_hc", "test_cbi"):
        maj = majority(os.path.join(FINAL, f"{split}.jsonl"))
        before, after = res["base_tests"][split], res["after_tests"][split]
        print(f"== {split}")
        print(f"   {'decision':14s} {'n':>5s} {'majority':>9s} {'base':>7s} {'nyaya':>7s} {'ece base':>9s} {'ece nyaya':>10s}")
        for k in sorted(after, key=lambda x: (x != "ALL", x)):
            n, m = maj.get(k, (after[k]["n"], float("nan")))
            b = before.get(k, {})
            print(f"   {k:14s} {after[k]['n']:5d} {m:9.1%} {b.get('acc', float('nan')):7.1%} {after[k]['acc']:7.1%} "
                  f"{b.get('ece', float('nan')):9.3f} {after[k]['ece']:10.3f}")
        print()


if __name__ == "__main__":
    main()
