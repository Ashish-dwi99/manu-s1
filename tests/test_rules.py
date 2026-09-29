"""Every generated label must be one the bank entry allows, every generator must produce every non-degenerate
label, and the label must follow from the calculator facts in the state (spot-checked per family)."""
import re
from collections import Counter

import yaml
import glob
import os

from nyaya import rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = {e["id"]: e for p in glob.glob(os.path.join(ROOT, "bank", "*.yaml")) for e in yaml.safe_load(open(p))}


def test_labels_are_bank_labels_and_all_are_reached():
    for bank_id in rules.GENERATORS:
        entry = BANK[bank_id]
        assert not entry.get("verify"), f"{bank_id} is flagged verify and must not be generated"
        got = Counter(label for _, label in rules.generate(bank_id, 600, seed=1))
        allowed = set(entry["labels"])
        assert set(got) <= allowed, (bank_id, set(got) - allowed)
        unreachable = {"right_survives_against_others", "partly_matches", "set_ex_parte", "not_appeared_after_service"}
        missing = allowed - set(got) - unreachable
        assert not missing, (bank_id, missing, got)


def test_generation_is_deterministic():
    assert rules.generate("FCR.NI.03", 20, seed=7) == rules.generate("FCR.NI.03", 20, seed=7)


def test_ni138_complaint_label_matches_calculator():
    for state, label in rules.generate("FCR.NI.03", 300, seed=3):
        if label in ("in_time", "late", "late_condonation_sought"):
            m = re.search(r"Complaint presented on \S+: (on the last day|(\d+) day\(s\) (after|before) the last day)", state)
            after = bool(m and m.group(3) == "after")
            assert after == (label != "in_time"), state


def test_names_never_decide():
    # the same facts with other names give the same label: generators draw names from rng but labels depend only
    # on dates and flags, so swapping the name lists must not move the label distribution
    a = Counter(l for _, l in rules.generate("PLD.WS.01", 800, seed=11))
    saved = rules.FIRST[:]
    try:
        rules.FIRST.reverse()
        b = Counter(l for _, l in rules.generate("PLD.WS.01", 800, seed=11))
    finally:
        rules.FIRST[:] = saved
    assert a == b
