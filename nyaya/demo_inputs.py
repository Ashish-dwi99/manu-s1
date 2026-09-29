"""Inputs for the demo run: every decision the demo shows, built from real files where they exist.

  uv run --with pyyaml python -m nyaya.demo_inputs   ->  data/demo/inputs.json

1. The owner's CBI case file (real): for each order, what kind of order it is, whether the next order on file is
   on the date it fixed, how each accused named in it appeared, and (once) the special-court statute.
2. Four cheque-dishonour complaints (samples, marked as such): the Act's answer is computed by the calculator.
3. Held-out High Court orders (real, never trained on): every final order in the test split, so the number of
   records where the court database's outcome differs from the order text is counted over all of them.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

from nyaya import calculators as C
from nyaya.assemble import map_disposal, split_of
from nyaya.items import ROOT, bank

B = bank()
OUT = os.path.join(ROOT, "data", "demo")


def q(bid: str, note: str = "") -> dict:
    e = B[bid]
    return {"bank_id": bid, "type": "choice", "instructions": e["question"] + (f" {note}" if note else ""),
            "criteria": dict(e["labels"])}


def cbi() -> tuple[list[dict], list[dict]]:
    rows = json.load(open(os.path.join(ROOT, "data", "real", "cbi-315-2019", "orders.json")))
    rows = sorted([r for r in rows if r["chars"] > 200 and re.match(r"\d{4}-\d{2}-\d{2}", r["file"]) and "order on charge" not in r["file"]],
                  key=lambda r: r["file"])
    orders, decisions = [], []
    for i, r in enumerate(rows):
        text = re.sub(r"[ \t]+", " ", r["text"]).strip()
        d = r["file"][:10]
        fixed = re.search(r"put up (?:on|for [^.]{0,80}? on)\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", text, re.I | re.S)
        pws = sorted({int(x) for x in re.findall(r"\bPW-?\s?(\d{1,3})\b", text)})
        orders.append({"date": d, "file": r["file"], "text": text[:6000], "pages": r["pages"],
                       "next_fixed": (f"{int(fixed.group(3)):04d}-{int(fixed.group(2)):02d}-{int(fixed.group(1)):02d}" if fixed else None),
                       "witnesses_mentioned": pws})
        decisions.append({"group": "cbi", "order": d, "kind": "order_kind", "state": text[:6000], "question": q("ORD.TYP.01")})
        if i + 1 < len(rows):
            nxt = date.fromisoformat(rows[i + 1]["file"][:10])
            decisions.append({"group": "cbi", "order": d, "kind": "next_date", "state": f"{text[:6000]}\n\nNext date recorded in the case database: {nxt.strftime('%d.%m.%Y')}.",
                              "question": q("ORD.NXT.01"), "next_on_file": nxt.isoformat()})
        for tag in sorted(set(re.findall(r"\bA-(\d)\b", text)), key=int):
            m = re.search(rf"A-{tag}\s+([A-Z][A-Za-z\. ]{{3,40}}?)(?:\s+(?:is|are|in|\(|and|has|have|,|\.))", text)
            name = m.group(1).strip() if m else ""
            decisions.append({"group": "cbi", "order": d, "kind": "appearance", "accused": f"A-{tag}", "name": name,
                              "state": text[:6000], "question": q("SRV.APR.01", f"Party asked about: A-{tag} {name}.".replace("  ", " "))})
        if i == 0:
            decisions.append({"group": "cbi", "order": d, "kind": "special_court", "state": text[:1500], "question": q("REG.SPL.01")})
    return orders, decisions


def ni138_samples() -> list[dict]:
    """Four sample complaints. Dates chosen to tell four different stories; the Act's answer is computed."""
    stories = [
        ("On time", "Shree Balaji Traders", "Ramesh Yadav", date(2025, 1, 6), date(2025, 2, 20), date(2025, 2, 24), date(2025, 3, 3), date(2025, 4, 1), False, True),
        ("Filed too early", "Kaveri Agro Industries", "Irfan Qureshi", date(2025, 5, 2), date(2025, 5, 20), date(2025, 5, 22), date(2025, 5, 30), date(2025, 6, 10), False, True),
        ("Late, with a condonation application", "Malabar Spices Co.", "Mary Varghese", date(2024, 8, 12), date(2024, 9, 5), date(2024, 9, 9), date(2024, 9, 16), date(2024, 11, 18), True, True),
        ("The record is silent", "Deccan Hardware Stores", "Sukhwinder Gill", date(2025, 7, 1), date(2025, 7, 25), date(2025, 7, 28), None, date(2025, 9, 15), False, False),
    ]
    out = []
    for title, payee, drawer, cheque, presented, notice_sent, received, filed, condone, tracking in stories:
        validity = C.ni138_validity(cheque)
        memo = presented + timedelta(days=2)
        notice_w = C.ni138_notice(memo)
        text = (f"SAMPLE COMPLAINT (for demonstration)\nComplaint under Section 138 read with Section 142 of the Negotiable Instruments Act, 1881\n"
                f"before the Metropolitan Magistrate (NI Act), Saket, New Delhi.\nComplainant: {payee}. Accused: {drawer}.\n"
                f"Cheque No. 482113 for Rs. 3,40,000 dated {cheque.strftime('%d.%m.%Y')}, presented on {presented.strftime('%d.%m.%Y')}, "
                f"returned unpaid 'Funds Insufficient' by memo dated {memo.strftime('%d.%m.%Y')}.\n"
                f"Demand notice sent by registered post on {notice_sent.strftime('%d.%m.%Y')}.\n")
        calc = [f"Cheque validity: three months from {C.fmt(cheque)}; last day {C.fmt(validity.last_day)}.",
                f"Presented on {C.fmt(presented)}: {abs(C.signed_days(presented, validity.last_day))} day(s) {'before' if presented <= validity.last_day else 'after'} the last day.",
                notice_w.render(notice_sent, "notice issued")]
        if received:
            pay = C.ni138_payment(received)
            arises = C.ni138_cause_of_action(pay)
            comp = C.ni138_complaint(arises)
            text += f"The accused received the notice on {received.strftime('%d.%m.%Y')} (postal tracking report annexed) and did not pay.\n"
            calc += [pay.render(), f"Cause of action arose on {C.fmt(arises)} (the day after the payment period ended).", comp.render(filed, "complaint presented")]
            if filed < arises:
                calc.append(f"The complaint was presented {(arises - filed).days} day(s) before the cause of action arose.")
                act = "premature"
            elif filed <= comp.last_day:
                act = "in_time"
            else:
                act = "late_condonation_sought" if condone else "late"
        else:
            text += "The complaint says the accused received the notice but gives no date, and no tracking report is annexed.\n"
            calc.append("Date of receipt of notice: not in the record.")
            act = "cannot_tell"
        text += f"Complaint presented on {filed.strftime('%d.%m.%Y')}.\n"
        if condone:
            text += "An application for condonation of delay under the proviso to Section 142(1)(b) is filed with the complaint.\n"
        state = text + "\n[computed by the court calculator]\n" + "\n".join(f"- {x}" for x in calc)
        for bid, kind, expected in (("FCR.NI.01", "validity", "within_validity" if presented <= validity.last_day else "after_validity"),
                                    ("FCR.NI.02", "notice", "in_time" if notice_sent <= notice_w.last_day else "late"),
                                    ("FCR.NI.03", "complaint", act)):
            out.append({"group": "ni138", "story": title, "kind": kind, "state": state, "question": q(bid), "expected": expected})
    return out


def hc_orders() -> list[dict]:
    out = []
    for line in open(os.path.join(ROOT, "data", "hc", "teacher.jsonl")):
        r = json.loads(line)
        if r["pool"] != "disposal" or r["key"].endswith(":cite") or split_of(r["cnr"]) != "test":
            continue
        mapped = map_disposal(r.get("disposal_raw", ""))
        if not mapped:
            continue
        for bid, kind in (("ORD.TYP.01", "order_kind"), ("ORD.OUT.01", "outcome"), ("ORD.INT.01", "interim"), ("ORD.COS.01", "costs")):
            out.append({"group": "hc", "key": r["key"], "court": r.get("court"), "case_type": r.get("case_type"),
                        "database_outcome": r.get("disposal_raw"), "database_label": mapped, "kind": kind,
                        "state": r["state"], "question": q(bid)})
    return out


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    orders, cbi_dec = cbi()
    inputs = {"cbi_orders": orders, "decisions": cbi_dec + ni138_samples() + hc_orders()}
    json.dump(inputs, open(os.path.join(OUT, "inputs.json"), "w"), ensure_ascii=False)
    from collections import Counter
    print(len(orders), "CBI orders;", Counter((d["group"], d["kind"]) for d in inputs["decisions"]))


if __name__ == "__main__":
    main()
