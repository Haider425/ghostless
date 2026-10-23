# Resume models: results

Each stage of `docs/resume-model-plan.md` is measured on the **held-out** set
with `ghostless evaluate-resume`, and recorded here. The raw numbers for the
latest run of each system are in `eval/resume/results/`.

## The labels: Claude-labelled, provisional

No person has labelled the set yet. Until someone does, the answer key is
built from two independent Claude passes over the 99 held-out pairs:

1. **Pre-labels** (`eval/resume/prelabels.jsonl`), with a reason each.
2. **A blind second pass** (`eval/resume/second_labels.jsonl`) by a separate
   agent that saw only the rubric in `eval/resume/README.md`, the resume and
   the posting: never the pre-labels.

| | |
|---|---|
| Pairs compared | 99 |
| Agree | 81 (82%), Cohen's kappa 0.68 |
| Second pass said strong / okay / weak | pre-label agreed 6 of 8 / 29 of 34 / 46 of 57 |

Where the two agree (81 pairs: 6 strong, 29 okay, 46 weak), that label is the
answer. The 18 where they disagree are **left out of the scores**, and shown
below counted each way. A person's label always takes the place of both
(`evalset.answer_key`), and so, later, can users' feedback
(`tracker/resume/feedback.py`).

Most disagreements are about eligibility abroad (an EU work permit, a
language) or how far a specialty stretches. Examples:

| Pair | Pre-label | Second pass |
|---|---|---|
| iOS new grad (Montreal) × new grad mobile role in Milan | okay: Milan is the one mismatch | weak: needs a permit to work in the EU |
| Backend developer, 3 years × test-infrastructure role, remote in Canada | strong | okay: test automation, not backend product work |
| Backend developer, 3 years × senior data-platform reliability (Toronto) | okay: a different specialty | weak: covers little of Java, Kafka, Spark, Snowflake |
| Senior frontend, remote in the US × frontend role on site in Costa Mesa with clearance | weak: a step down and not remote | okay: on site and clearance, but a fit on skills |
| NLP new grad (Vancouver) × graduate AI program in Cairo | okay: Cairo is the one mismatch | weak: on site and needs Arabic |

## Stage 1 baseline: today's matcher (2026-10-23)

`ghostless evaluate-resume` (held-out set, offline, from the posting snapshots).
Each person's judged postings are ranked by today's score (`match.score_job`).

| Measure | Result | Notes |
|---|---|---|
| **NDCG@10** (strong 2, okay 1, weak 0) | **0.849** | over the 11 people with at least one strong or okay posting |
| **Precision@3** (strong or okay) | **0.758** | @3 rather than @10: people have 2 to 8 judged postings |
| Fit score: Spearman with the labels | 0.511 | |
| Fit score: accuracy / weighted kappa | 0.667 / 0.484 | after mapping scores with cut-offs chosen on the tuning split: okay at 41; no cut-off for strong did better than never saying strong |
| **Words to add: precision** | **0.042** | 37 of 888 suggestions judged fair to add (second pass only) |
| Speed, p95 | analyse 8 ms; score one posting 62 ms | this laptop, one thread |

With the 18 disputed pairs counted rather than left out:

| Disputed pairs counted as | NDCG@10 | P@3 | Spearman | Weighted kappa |
|---|---|---|---|---|
| left out (the baseline) | 0.849 | 0.758 | 0.511 | 0.484 |
| the pre-label | 0.870 | 0.744 | 0.481 | 0.451 |
| the second pass | 0.810 | 0.727 | 0.443 | 0.372 |

**What it says:**

- **Ranking is reasonable** among postings already shortlisted for a person: a
  good fit usually comes first. This doesn't yet measure ranking over the
  whole pool, where most postings are unjudged.
- **The fit score separates weak from the rest, but not strong from okay.**
  On the tuning split, no score cut-off for "strong" agreed with the labels
  better than never saying strong.
- **"Words to add" is mostly noise:** 96% of suggestions were judged not fair,
  typically generic words from the posting ("development", "program",
  "e.g.") or company names. Stage 2's target.
- **Not measured yet:** resume quality (no quality ratings), and the harmful
  count as the plan defines it (judged "not fair" covers both "not a real
  requirement" and "the person doesn't have it").
- **Small and provisional:** 81 pairs, 6 of them strong. Differences of a few
  points between systems won't mean much until the set grows or a person
  labels it.
