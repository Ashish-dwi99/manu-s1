# Nyaya-S1 v0 results (2026-09-29)

**Model.** Tura-S1-4B (Plumb-4B + our Tura/general/tool-calling LoRA), chosen over Plumb-4B on the Nyaya dev set
(83.9% vs 80.9%, NLL 0.48 vs 0.85), plus one LoRA (rank 16, one epoch, lr 2e-5) on 17,401 Indian court questions,
merged. Temperature 1.22 fitted on dev. Training 31.7 minutes on one H100.

- Adapter: Kaggle `moriarty9/nyaya-s1-v0` (checkpoints every 300 steps in `moriarty9/nyaya-s1-v0-ckpt`)
- Merged model: Modal volume `tura-s1-jevk5-runs:/nyaya-s1-v0` (with `jevk5_config.json`); serves with `jevk5-serve`
- Raw results: `data/final/results.json`; per-item real-case predictions: `data/final/cbi_predictions.json`

**Training data (17,514 before length filtering).** 8,514 High Court questions from 6,700 orders of 24 High Courts
(public AWS dataset, CC-BY-4.0): outcome from the court's own metadata where unambiguous (86% agreement with the
teacher on overlap), everything else from gpt-oss-120b answering twice with shuffled options, kept only when both
agree (77-94% per question); 7,000 calculator-labelled rule questions (14 families); 2,000 general replay.

## Scores (JevK5 evaluate, T=1)

| test set | majority floor | before (Tura-S1) | Nyaya-S1 v0 | ECE before → after |
|---|---|---|---|---|
| Rule families, 1,400 | 40.7% | 76.9% | **99.9%** | 0.115 → 0.003 |
| High Court orders, held-out cases, 2,351 | 72.4% | 86.9% | **91.7%** | 0.068 → 0.043 |
| Owner's real CBI case, 171 | 91.2% | 63.7% | 62.6% | 0.289 → 0.307 |

High Court, per decision: interim orders 85.0 → 92.7, appearance 79.4 → 90.6, precedent treatment 76.7 → 86.1,
order kind 85.2 → 89.1, costs 95.2 → 97.8 (majority 91.7), outcome 82.3 → 82.7 (flat; majority 16.7).

Rule families: the base failed counting adjournments (18%) and the mutual-consent waiting period (27%); v0 is at
99-100% on every family. These are generated records; they show the model reads the calculator's facts and the
record's conditions correctly, not how it does on a real registry's files.

## What the real case showed

- **Next date fixed vs the next order on file: 93.6%** (majority 68.1%), on district orders it never trained on.
- **Appearance of an accused: 59.6% strict, 99/99 when either true answer counts.** The label set was ambiguous:
  when an accused attends and counsel also appears, "in person" and "through an advocate" are both true. The
  model chose "through an advocate" on 40 such orders. Fixed in the bank for v1 (mutually exclusive labels).
- **Special-court statute: 12.5%.** A real failure: 21 of 24 times it said no special statute applies to a case
  under "Sec. 13(2) r/w 13(1)(d) of PC Act, 1988". This decision had no training data in v0.

## v1, in order

1. A rule generator for `REG.SPL.01` (sections and their abbreviations -> special statute: PC Act, NDPS, POCSO,
   SC/ST (PoA), PMLA, UAPA) and `CRM.SCH.*` once the schedule tables are checked by counsel.
2. Re-label appearance with the split labels (teacher, both passes agree).
3. Trial-court order sheets at scale (`data/DATA_REVIEW.md`): the district families are where the model is weakest
   and the real work is.
4. Counsel review of the 20 `verify`-flagged decisions, then train them.
5. A gold set from practising advocates; conformal thresholds per decision; the evidence-pointer head.

Spend for v0 on Modal: about $8 (collection ~$0.3, teacher labelling ~$3.7 including one failed start, training and
evaluation ~$3.6, diagnosis ~$0.2).

# v1 (2026-09-29): the two real-case fixes

Continued from v0 on 7,125 questions: a rule generator for the special-court statute (headers in the forms courts
write them), a trial-court appearance generator ("Present:" blocks, counsel entries wrapped across lines), the
High Court appearance questions relabelled with the split labels (gpt-oss-120b, both passes agree, 2,236/2,500),
and 5,000 replayed from v0. Adapter: Kaggle `moriarty9/nyaya-s1-v1`; merged: `tura-s1-jevk5-runs:/nyaya-s1-v1`.

| test set | v0 | v1 |
|---|---|---|
| Rule families (1,620, incl. special court and appearance) | 97.0% | **99.5%** |
| High Court held-out cases (2,346) | 90.6% | **91.8%** |
| Real CBI case (169) | 51.5% | **68.0%** |
| - special-court statute (24) | 12.5% | **100%** |
| - "came in person", on orders that record it (90) | | **80 of 90** |
| - in person with vs without counsel (97, pattern labels) | 40.2% | 47.4% (labels themselves uncertain) |

# Demo (released as Manu-S1)

`demo/`: `manu_case_desk.html` (interactive page, also `#film`), `manu_s1_demo.mp4` (2 min 14 s, narrated),
built from one live run of v1 on an NVIDIA L40S: 1,972 decisions in 197 s, median 64 ms, p95 194 ms.
Rebuild: `modal run modal/demo_run.py`, `python3 demo/build_page.py`, `.venv/bin/python demo/record_film.py`.
Batched evaluation (JevK5's training evaluate path) was slower than one-at-a-time here and is not reported as speed.
