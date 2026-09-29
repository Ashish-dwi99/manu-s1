"""Bank entry + state + label -> a JevK5 training/eval item (the format JevK5's lora.py and runtime read).

Choice labels are renamed to neutral keys (a, b, c, ...) as JevK5's own build_train.py does, so the model learns
from the option text, never from a key's name. Entries with more than 16 options are served in passes and are not
trained in v0.
"""
from __future__ import annotations

import glob
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS = "abcdefghijklmnop"


def bank() -> dict[str, dict]:
    return {e["id"]: e for p in sorted(glob.glob(os.path.join(ROOT, "bank", "*.yaml"))) for e in yaml.safe_load(open(p))}


def make_item(entry: dict, state: str, label: str, *, source: str, item_id: str, note: str = "") -> dict | None:
    labels = entry["labels"]
    if entry["type"] != "choice" or len(labels) > 16 or label not in labels:
        return None
    rename = dict(zip(labels, KEYS))
    instructions = entry["question"] + (f" {note}" if note else "")
    return {"id": item_id, "source": source, "bank_id": entry["id"], "state": state,
            "question": {"type": "choice", "instructions": instructions,
                         "criteria": {rename[k]: v for k, v in labels.items()}},
            "expected": rename[label], "label_name": label}
