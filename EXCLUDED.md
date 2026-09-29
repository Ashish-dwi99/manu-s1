# What Nyaya-S1 will not decide

Not at any tier, not on request, not as a research preview. Each line is a decision the model is never trained on,
and the question bank validator refuses an entry whose name or question matches it.

| never | why |
|---|---|
| Whether to grant bail, anticipatory bail or parole; flight risk; likelihood of reoffending | Risk scoring about a person. Prohibited by the Supreme Court's proposed AI regulations (July 2026: "risk scoring", including bail eligibility evaluation, flight risk, recidivism). It is also where historical bias in the record becomes a machine's judgment about a human. |
| Credibility of a party or a witness; whether evidence is believable | Prohibited (credibility determinations). Appreciation of evidence is the judge's alone. |
| Guilt, liability, the merits of a claim, the likely outcome of a case or appeal | Adjudication. The Kerala High Court policy confines AI to administrative, research and translation work; outcome prediction also invites forum shopping and pressure on litigants. |
| Sentence, quantum of damages, compensation or maintenance amounts | Adjudication. |
| Whether a judge, advocate or party is "good", "fast", "lenient" or "favourable" | Profiling people who appear before or sit in court. |
| Anything keyed on caste, religion, gender, region, or a party's name | Protected attributes. Every release must pass the counterfactual swap test (`eval/FAIRNESS.md`): changing these in the state must not change any answer. |

Statutory arithmetic that touches liberty (custody period against the Section 479 BNSS thresholds, the Section
187 BNSS investigation periods) exists only at tier `restricted`: a calculation for prison administrations and
legal-services authorities to act on, never an assessment, never deployed inside a court.
