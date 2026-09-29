"""Validate the question bank: structure, unique ids and names, cannot_tell on every choice, tiers, and the
EXCLUDED.md rule (no entry may ask for risk scoring, credibility, merits, outcome or sentence).

  uv run --with pyyaml python tools/validate_bank.py
"""
import glob
import os
import re
import sys
from collections import Counter

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES, TIERS = {"choice", "score"}, {"court_admin", "research", "restricted"}
SOURCES = {"cis", "rule", "teacher", "gold"}
FORBIDDEN = re.compile(r"\b(grant bail|flight risk|reoffend|recidiv|credib|believab|guilt|likely outcome|predict(ed)? outcome|"
                       r"sentence to impose|quantum|should be (allowed|granted|dismissed))\b", re.I)


def load() -> list[dict]:
    entries = []
    for path in sorted(glob.glob(os.path.join(ROOT, "bank", "*.yaml"))):
        for e in yaml.safe_load(open(path)) or []:
            e["_file"] = os.path.basename(path)
            entries.append(e)
    return entries


def check(e: dict) -> list[str]:
    errs = []
    for k in ("id", "name", "type", "question", "labels", "inputs", "labels_from", "evidence", "tier"):
        if k not in e:
            errs.append(f"missing {k}")
    if errs:
        return errs
    if e["type"] not in TYPES:
        errs.append(f"type {e['type']}")
    if e["tier"] not in TIERS:
        errs.append(f"tier {e['tier']}")
    if not set(e["labels_from"]) <= SOURCES:
        errs.append(f"labels_from {e['labels_from']}")
    if e["type"] == "choice":
        if not isinstance(e["labels"], dict) or "cannot_tell" not in e["labels"]:
            errs.append("choice without cannot_tell")
        elif len(e["labels"]) < 3:
            errs.append("choice with fewer than three labels")
        elif any(not str(v).strip() for v in e["labels"].values()):
            errs.append("empty label description")
    else:
        if not isinstance(e["labels"], list) or len(e["labels"]) < 2:
            errs.append("score needs an ordered list of at least two levels")
    if e["evidence"] not in ("required", "optional"):
        errs.append(f"evidence {e['evidence']}")
    if not re.fullmatch(r"[A-Z]{2,4}\.[A-Z0-9]{2,5}\.\d{2}", e["id"]):
        errs.append(f"id format {e['id']}")
    text = " ".join([e["question"], e["name"], *[str(v) for v in (e["labels"].values() if isinstance(e["labels"], dict) else e["labels"])]])
    if FORBIDDEN.search(text):
        errs.append(f"matches EXCLUDED.md: {FORBIDDEN.search(text).group(0)!r}")
    if e["tier"] == "restricted" and "gold" in e["labels_from"] and "rule" not in e["labels_from"]:
        errs.append("restricted entries are rule-computed")
    return errs


def main() -> int:
    entries = load()
    bad = 0
    for e in entries:
        for err in check(e):
            bad += 1
            print(f"{e.get('_file')}: {e.get('id')}: {err}")
    for field in ("id", "name"):
        for value, n in Counter(e.get(field) for e in entries).items():
            if n > 1:
                bad += 1
                print(f"duplicate {field}: {value}")
    fam = Counter(e["id"].split(".")[0] for e in entries)
    print(f"{len(entries)} entries, {bad} problems | families {dict(sorted(fam.items()))}")
    print(f"tiers {dict(Counter(e['tier'] for e in entries))} | verify-flagged {sum(bool(e.get('verify')) for e in entries)}"
          f" | calculator-backed {sum(bool(e.get('calculator')) for e in entries)}"
          f" | label sources {dict(Counter(s for e in entries for s in e['labels_from']))}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
