---
license: apache-2.0
base_model: AshishDwi99/tura-s1-4b
language:
- en
tags:
- decision-model
- system-one
- legal
- india
- courts
- jevk5
- typed-decisions
pipeline_tag: text-classification
---

# Manu-S1

A one-pass decision model for the procedural work of Indian courts. Give it a record (an order sheet, a complaint,
a judgment) and a typed question from its question bank; it returns a probability for every answer, including a
trained "cannot tell", in one forward pass with no generated text.

It is a research model. It checks procedure (dates, filings, appearances, records) and never the merits of a case.
It must be evaluated against answers labelled by practising advocates before any court relies on it.

## What it answers

| Family | Examples |
|---|---|
| Deadlines and limitation (with the court calculator) | cheque-dishonour complaints under s.138 NI Act (presentation, notice, complaint timing), suit limitation, s.34 Arbitration Act challenges, consumer complaints, execution petitions, written-statement periods, s.80 CPC notice, caveats, abatement, mutual-consent waiting period |
| Orders | what kind of order it is, how the case was disposed of, interim orders, costs |
| Appearance | whether a party came in person or only through counsel |
| Routing | the special court a criminal case belongs to (PC Act, NDPS, POCSO, SC/ST (PoA), PMLA, UAPA); old or new penal code by offence date |
| Research | how a later judgment treats a precedent (research use only) |

Date arithmetic is done by code, not by the model: the calculator's facts are placed in the record, and the model
decides which answer the record supports. The question bank, calculator and pipeline are in the project repository.

## What it will never do

It is never trained to decide bail, flight risk, reoffending, credibility, guilt, liability, outcomes, sentences
or amounts, or anything keyed on caste, religion, gender, region or a party's name. The Supreme Court's proposed
regulations on AI in courts (July 2026) prohibit risk scoring, including bail eligibility evaluation.

## Results

Measured with JevK5's evaluation at temperature 1, test sets split by case and never trained on.

| Test set | Majority answer | Before (Tura-S1-4B) | Manu-S1 |
|---|---|---|---|
| Rule families, 1,620 generated records (16 families) | 39.3% | 97.0%* | 99.5% |
| High Court orders, held-out cases, 2,346 | 72.3% | 86.9% | 91.8% |
| A real CBI special-court trial file, special-court statute (24) | 100% | 12.5% | 100% |
| Same file, "came in person" where the order records it (90) | | | 80 of 90 |

\* After the first court-procedure round (v0); the original base scored 76.9% on the 14 families it shared.

Rule-family records are generated, so read those numbers as "reads the calculator's facts correctly", not as
accuracy on a registry's files. Distinguishing an accused in person *with* counsel from *without* counsel remains
unreliable (47% on the real file, where the reference labels are themselves uncertain).

Speed on one NVIDIA L40S, JevK5 runtime, one decision at a time on records of up to a few thousand tokens: median
64 ms, p95 194 ms (1,972 decisions in 197 s).

## Training

Two LoRA rounds (rank 16, lr 2e-5, one epoch each) with JevK5's `training/lora.py`, merged:

- 6,700 orders from 24 High Courts (public AWS dataset, CC-BY-4.0): how the case was disposed of from the court's own
  metadata where its wording is unambiguous; order kind, interim orders, costs, appearance and precedent treatment
  from gpt-oss-120b answering each question twice with shuffled options, kept only when both answers agree.
- Rule programs: record excerpts whose answers are computed by the court calculator (16 families).
- Replay of general decision data so the base keeps its general skill.

The base, Tura-S1-4B, was chosen over Plumb-4B on the development set (83.9% vs 80.9%). One temperature (1.26) is
fitted on the development set and stored in `jevk5_config.json`.

## Run it

```bash
pip install git+https://github.com/allebee/jevk5
jevk5-serve --model sankhya-ai-labs/manu-s1-4b --port 8090   # TypeSafe-style POST /v1/systemone
```

About 9 GB in bf16. English records only; up to 16 options per pass.

## Limitations

- English only; trained on High Court orders and generated trial-court records, evaluated on one real trial file.
- No evidence pointer yet: the answer does not name the paragraph it relied on.
- Twenty decision types in the question bank await review by counsel and are not trained.
- Dates must be extracted from documents before the calculator can use them; extraction is not part of this model.

## Licence

Apache-2.0. See `NOTICE` (and `NOTICE-plumb`, `NOTICE-jevk5`) for the weights, code and data this builds on,
including the CC-BY-4.0 attribution for the Indian High Court Judgments dataset (Dattam Labs).
