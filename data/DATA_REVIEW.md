# Data review: the real case file against the public High Court data (2026-09-29)

## What we compared

| | Real case file (the owner's) | Public High Court data (AWS open data, CC-BY-4.0, Dattam Labs) |
|---|---|---|
| Source | CBI v. M/s Revati Cement, CC 315/2019, Special Judge (PC Act), Rouse Avenue, New Delhi | 25 High Courts, ~17.8M orders and judgments, metadata parquet + PDFs, daily updates |
| Court level | Trial court (district / special court) | High Courts only |
| Shape | **152 daily orders of one case, 2019-2026**, a full order sheet history | **One order per case** in the metadata (median 1 per CNR); mostly final judgments and orders |
| Length | median 2,024 characters, 2 pages | median 3,288 characters, 4 pages (p90 12,696) |
| Text | typed, text layer present (1 of 152 without) | typed, text layer present in every sampled PDF |
| Language | English | English in all 24 sampled PDFs (Karnataka, Madras, Jammu & Kashmir) |
| "Present:" appearance block | 146 / 152 | 0 / 24 |
| Next date fixed in the order | most orders | 0 / 24 |
| Witness examination | 79 / 152 | 2 / 24 |
| Final-disposal language | frequent (in recitals and in the charge order) | 22 / 24 |
| Structured labels | none (but the sequence itself labels next dates, gaps and stages) | `disposal_nature` **100% filled** for Karnataka, Madras and J&K; **empty for all 50,462 Delhi rows**; `description` is only the first ~290 characters, so text must come from the PDFs |

## What this means

1. **The public data is High Court final orders, not trial-court order sheets.** The families that live in a
   trial court's daily orders (service and appearance `SRV`, hearing readiness and adjournments `HRG`, trial
   stage `PLD.STG.02`, accused production, witness summons) have almost no training signal in it.
   These families are where the adjournment problem sits, and where the real case file is rich.
2. **It is strong for what High Courts produce:** how a case was disposed of (`ORD.OUT.01`, with a free label for
   most courts), what kind of order it is, interim orders and costs, the remedy brought (`APL.TYP.01`), statutes
   and precedents cited (`RSR.*`), which criminal code applies (`CRM.CODE.*`), and cheque-dishonour quashing
   petitions and their timelines.
3. **Disposal labels need a mapping.** Each court writes its own vocabulary ("Disposed Off", "DISPOSED OF",
   "ORDERED", "GRANTED", "CLOSED", "MODIFIED", "Dismissal for Non Compliance of Office Objections"). Mapped to our
   labels where the meaning is unambiguous; "ORDERED", "GRANTED", "CLOSED" and "MODIFIED" are not, and are
   labelled from the text instead.
4. **Language is not the problem at High Court level** (all English). It will be at district level in the Hindi
   belt and the south, which is also where this dataset has nothing.
5. **The owner's case file is the right shape for the district families but is one case.** It is held out
   entirely as a real-world evaluation (split by case, never trained on). Its sequence gives rule labels for
   free: the next date an order fixes against the date of the next order on file (a gap means a missing order
   or an unrecorded adjournment), the code applicable by offence and registration dates, the special-court statute.

## What we need to close the gap

Trial-court order sheets at scale, in several states and languages. In order of preference:

1. **Case folders collected with consent**, from advocates (Manu users) and legal-services authorities, like this
   one. Each case is 50-200 orders; 200 case folders is 10,000-40,000 order sheets, enough for the district
   families. This is a data-partnership ask, not an engineering one.
2. **An official data request** to the eCourts Committee or a High Court's IT/AI committee for anonymised district
   order sheets for research, which the Supreme Court's proposed AI regulations (CoRE-AI) are meant to enable.
3. **District court websites that publish orders publicly** (Delhi's do). Public documents, but bulk collection
   needs a decision on terms of use and rate limits before any crawler is written. The owner's call.

Not an option: automated scraping of the eCourts case-status service (captcha-protected; its terms do not
permit bulk collection).

## Decision for v0

Train on what is real and labelled today, and measure the rest honestly:

- **High Court orders** (Karnataka, Madras, J&K and other courts whose `disposal_nature` is filled), text from the
  PDFs, split by CNR: disposal nature from metadata; order kind, interim orders, costs, remedy, statute cited,
  code applicable from open-weight teacher questions solved twice (kept only when both agree).
- **Rule programs over the calculators** for every date and threshold decision (limitation, cheque dishonour,
  abatement, written-statement periods, arbitration and consumer limitation, execution, mutual-consent period,
  caveat, section 80 notice): labels computed exactly.
- **The real case file:** evaluation only, including zero-shot on the district families v0 has no data for.
  The gap shows up as a number, not a guess.
