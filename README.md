# Manu-S1

Released as **Manu-S1**; the code and training runs use the working name Nyaya-S1 (`nyaya/`, `nyaya-s1-*`).

A System 1 model for the procedural work of Indian courts: millions of small, checkable decisions (is service
complete, is this filing in time, what did this order do, is this case over in substance but still pending) made
in milliseconds, on the court's own hardware, each answer a calibrated probability with an honest "cannot tell".

It never decides a case. Judges keep every merits decision; the model takes the procedure off their desks and the
registry's. What it will never do is written down in `EXCLUDED.md` and enforced by the bank validator.

## Layout

| path | what |
|---|---|
| `bank/` | the question bank: every decision the model makes, its labels, the statute it is decided against, where its labels come from, and whether a court may deploy it (`bank/SCHEMA.md`) |
| `EXCLUDED.md` | what is never built (risk scoring, credibility, merits, outcomes, sentences, profiling) |
| `nyaya/calculators.py` | the court calculator: exact legal date arithmetic the model is handed as facts |
| `nyaya/rules.py` | rule programs: record excerpts labelled by the calculator, never by a model |
| `nyaya/cbi_eval.py` | the owner's real case file as a held-out test (labels read by exact patterns, never trained on) |
| `nyaya/assemble.py` | train / dev / test assembly in JevK5's item format, split by case (CNR) |
| `modal/collect.py` | High Court orders from the public AWS dataset (CC-BY-4.0) |
| `modal/teach.py` | teacher labels: open-weight gpt-oss-120b on Modal, every question answered twice, kept only when both agree |
| `modal/train.py` | base selection on dev, JevK5 LoRA training with checkpoints, temperature, before/after on every test set |
| `data/DATA_REVIEW.md` | how the public data differs from a real case file, and what that means |
| `tools/validate_bank.py`, `tests/` | the bank validator; calculator and rule-program tests |

## Rules we hold ourselves to

- **No Claude output is ever a training label or example.** Labels come from courts' own records, deterministic
  rule programs, and open-weight teachers run on our own compute. No hosted API credits are used for data.
- **Nothing flagged `verify` in the bank is trained** until counsel confirms the statutory detail.
- **Splits are by case.** No case is on both sides of train and test. The owner's real case file is test only.
- **The base is chosen on dev, never on a test set.** Plumb-4B (JevK5 v0.2 + LoRA, #2 on JevBench) and our
  Tura-S1 fine-tune of it are both scored on the Nyaya dev set; the better one is trained.

## Status (v0 trained, 2026-09-29)

- **Nyaya-S1 v0 is trained** (see `RESULTS.md`): High Court held-out cases 86.9% -> 91.7% (majority 72.4%),
  rule families 76.9% -> 99.9%, real CBI case flat at 62.6% (one ambiguous label set, one decision with no data).
- Adapter on Kaggle `moriarty9/nyaya-s1-v0`; merged model on Modal volume `tura-s1-jevk5-runs:/nyaya-s1-v0`.
- Bank v0: 106 decision types across 14 families; 20 flagged for counsel review; validator clean.
- Known gaps: trial-court order sheets at scale (see `data/DATA_REVIEW.md`), Indian languages, the evidence
  pointer head, conformal thresholds per decision type. The v1 list is at the end of `RESULTS.md`.
