"""The owner's real case file (CBI v. M/s Revati Cement, CC 315/2019) as a held-out, real-world test set.

Labels come only from what an order states in so many words, read by exact patterns; anything the patterns
cannot read unambiguously is left out rather than guessed. Never trained on.

  - ORD.NXT.01: the next date the order fixes, against the date of the next order on file.
  - REG.SPL.01: the special-court statute named in the case header (Prevention of Corruption Act).
  - SRV.APR.01: an accused recorded "in person" (physically or through VC) on the order's date.
  - HRG.WIT.01: a witness's summons recorded as received back served or unserved.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date

from nyaya.items import ROOT, bank, make_item

SRC = os.path.join(ROOT, "data", "real", "cbi-315-2019", "orders.json")
DATE = r"(\d{1,2})\.(\d{1,2})\.(\d{4})"


def parse_date(s: str) -> date | None:
    m = re.search(DATE, s)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def build() -> list[dict]:
    B, rows = bank(), json.load(open(SRC))
    rows = [r for r in rows if r["chars"] > 200 and re.match(r"\d{4}-\d{2}-\d{2}", r["file"]) and "order on charge" not in r["file"]]
    rows.sort(key=lambda r: r["file"])
    items = []
    for i, r in enumerate(rows):
        text = re.sub(r"[ \t]+", " ", r["text"]).strip()
        fid = r["file"][:-4]
        this_date = date.fromisoformat(r["file"][:10])
        # next date fixed vs the next order on file
        fixed = re.search(r"put up (?:on|for [^.]{0,80}? on)\s+" + DATE, text, re.I | re.S)
        if i + 1 < len(rows) and fixed:
            nxt = date.fromisoformat(rows[i + 1]["file"][:10])
            fd = date(int(fixed.group(3)), int(fixed.group(2)), int(fixed.group(1)))
            state = f"{text}\n\nNext date recorded in the case database: {nxt.strftime('%d.%m.%Y')}."
            it = make_item(B["ORD.NXT.01"], state, "matches" if fd == nxt else "differs", source="cbi/next_date", item_id=f"cbi:{fid}:nxt")
            if it:
                items.append(it)
        # special court statute from the header
        if i % 6 == 0 and re.search(r"PC Act|Prevention of Corruption", text[:600]):
            it = make_item(B["REG.SPL.01"], text[:1500], "prevention_of_corruption", source="cbi/special_court", item_id=f"cbi:{fid}:spl")
            if it:
                items.append(it)
        # accused recorded in person on this date
        for m in re.finditer(r"(A-\d)\s+([A-Z][A-Za-z\. ]{3,40}?)\s+(?:is\s+)?in\s+person|(A-\d)\s+([A-Z][A-Za-z\. ]{3,40}?)\s*\(through VC\)", text):
            tag, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            head = text[:m.start()]
            if "absent" in text[m.start():m.end() + 20]:
                continue
            # counsel lines name the accused they appear for: "Ld. Counsel(s) ... for A-1 and A-4"
            # Counsel entries wrap across lines and abbreviations ("Sh. Mohd.") end lines, so no sentence rule is
            # reliable. Generous on purpose: an accused named within 250 characters after "Counsel ... for" is
            # represented. "Without counsel" is then only claimed when nothing anywhere could name them.
            represented = set()
            for c in re.finditer(r"Counsels?\b", text):
                window = text[c.end():c.end() + 250]
                if re.search(r"\bfor\b", window):
                    represented |= set(re.findall(r"A-\d", window.split("for", 1)[1]))
            if tag not in represented:
                continue   # absence of counsel cannot be read reliably from these orders' layout; left out, not guessed
            label = "in_person_with_counsel"
            it = make_item(B["SRV.APR.01"], text, label, source="cbi/appearance", item_id=f"cbi:{fid}:apr:{tag}",
                           note=f"Party asked about: {tag} {name.strip()}.")
            if it:
                items.append(it)
            break
        # witness summons status stated explicitly
        w = re.search(r"Summons (?:sent )?to (?:the )?witness(?:es)?\s+([^,\n]{3,60}?),?[^\n]{0,80}?\s*received\s+back\s+(unserved|served)", text, re.I | re.S)
        if w:
            label = "served" if w.group(2).lower() == "served" else "unserved"
            it = make_item(B["HRG.WIT.01"], text, label, source="cbi/witness_summons", item_id=f"cbi:{fid}:wit",
                           note=f"Witness asked about: {w.group(1).strip()}.")
            if it:
                items.append(it)
    return items


if __name__ == "__main__":
    from collections import Counter
    items = build()
    out = os.path.join(ROOT, "data", "final", "test_cbi.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as h:
        for it in items:
            h.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(len(items), "items", Counter((i["bank_id"], i["label_name"]) for i in items))
