# Question bank schema (v0)

Every decision Nyaya-S1 makes is one entry in `bank/*.yaml`. The bank is the spec the whole pipeline reads:
data generation asks these questions, the calculators compute what they need, evaluation scores them, and the
deployment gate reads `tier`. A decision that is not in the bank does not exist.

```yaml
- id: FIL.LIM.01                 # FAMILY.GROUP.NN, unique, never reused once a model has shipped with it
  name: suit_limitation           # snake_case, unique
  type: choice                    # choice | score   (see "Why almost everything is a choice")
  question: >                     # the instruction the model reads, in English (states may be in any language)
    Is this suit within limitation on the dates the record gives?
  labels:                         # label -> one-line description the model reads as the option text
    in_time: ...
    time_barred: ...
    cannot_tell: ...              # REQUIRED on every entry
  inputs: [plaint, cause_of_action_date]   # what must be in the state (documents, extracted facts, calculator output)
  calculator: limitation          # optional: the legal-date / threshold engine this decision leans on (calculators/SPEC.md)
  law: ["Limitation Act 1963 s.3", "Schedule, art. 113"]   # the provisions the answer is decided against
  labels_from: [rule, teacher, gold]       # where training/eval labels come from (below)
  evidence: required              # required | optional: the answer must point at a paragraph/page of the state
  tier: court_admin               # court_admin | research | restricted  (below)
  verify: true                    # optional: a statutory detail here must be confirmed by counsel before labelling
  notes: ...                      # optional
```

## Types

- `choice`: one label from a closed set, calibrated probabilities over all of them.
- `score`: ordered levels (0..n), probability over levels. Used for degrees (legibility, readiness).

### Why almost everything is a choice

A court decision about a record has three honest answers, not two: yes, no, and *the record does not say*.
Every entry carries `cannot_tell`, and it is a trained, first-class answer: missing service reports, an
unreadable scan, a date that is not in the file. A model that is forced to pick yes or no on a file that does
not answer the question is a model that makes things up. The deployment gate sends `cannot_tell` and every
answer below its type's certified threshold to a person.

## Where labels come from (`labels_from`)

| source | what it is | scale |
|---|---|---|
| `cis` | the court's own structured record (eCourts CIS / NJDG fields: case type, stage, purpose, next date, disposal nature, acts and sections, filing/registration/decision dates) aligned with the text of the orders and filings it belongs to | millions, every language |
| `rule` | a deterministic program over extracted facts and the calculators (limitation, thresholds, statutory tables) | unlimited, exact |
| `teacher` | questions over real public documents written by open-weight teacher models, each solved twice, kept only when both agree | tens of thousands |
| `gold` | practising advocates, registry officers, retired judicial officers | ~3,000, **evaluation only** |

`gold` never enters training. Splits are by case (CNR), never by document, so no case is on both sides.

## Tiers (`tier`) and the deployment gate

| tier | may run in a court's system | basis |
|---|---|---|
| `court_admin` | yes | case management, registry scrutiny, cause lists, scheduling: the administrative uses the Supreme Court's proposed AI regulations (July 2026) and the Kerala High Court policy permit |
| `research` | yes, as research only | legal research assistance; output is a lead, verified by a person |
| `restricted` | **no** | statutory arithmetic that touches liberty (custody periods, default-bail timelines). Offered only to prison administrations and legal-services authorities as a computation aid, never as an assessment, never inside a court. |

What is not built at any tier is in `EXCLUDED.md`.

## Evidence

`evidence: required` means the model must also answer "which paragraph or page supports this?", a second
choice over the state's own numbered paragraphs. An answer without a valid pointer is treated as `cannot_tell`.
The pointer can only name a paragraph that exists, so the model cannot cite a source that is not in the file.
