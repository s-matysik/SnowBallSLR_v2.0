# Version 2 validation: experiments and data

All CSV files are in `data/`, one row per simulated run or evaluation, UTF-8, comma-separated.
Simulated reviews come from `validation_generator.py` (temporally acyclic citation graphs with
120 relevant records, topic homophily, partial provider coverage and a share of relevant records
unreachable by citation). The grid is the version-1 stopping benchmark: regimes dense, sparse and
diffuse x graph seeds 0-5 x seed-set sizes 5, 10, 20 x 5 draws = 270 reviews.

## Within-iteration stopping (pillar B)

`python validation/validation_queue_stopping.py data/queue_stopping_benchmark.csv`
(`--alpha 0.01 --variants queue,review` for the sensitivity file). Each review runs through the
library five times; the ranking uses citation structure only (the generator's text encodes
relevance and is replaced by one neutral string), and the test is checked after every five
decisions.

`queue_stopping_benchmark.csv`, `queue_stopping_alpha001.csv`

| column | meaning |
|---|---|
| alpha | significance level of the within-iteration test |
| regime, graph_seed, seed_size, draw | the simulated review (pairing key) |
| variant | `full` (every candidate screened, version 1), `queue`, `review`, `queue_random`, `review_random` (random screening order, control) |
| n_gold | relevant records in the graph (120) |
| iterations | iterations completed |
| stopped_by | stopping rule that ended the review (`exhaustion`, `marginal_yield`, `max_iterations`) |
| screened | records screened over the whole review |
| found | relevant records included |
| recall | found / n_gold |
| queues_cut | iterations whose queue was cut short by the rule |
| records_left_unscreened | candidates left unscreened at those cuts (some resurface later) |
| cuts_below_target | cuts made while recall, in the scope tested, was below the 0.95 target |

`queue_stopping_paired_summary.csv` holds the paired summary reported in the article. Savings are over 269
reviews: in one (diffuse, graph 5, 5 seeds, draw 3) the seeds have no citation links, so every variant
screens 0 records and the saving is undefined; recall figures use all 270.

## Cross-method recall estimation (pillar A)

Design and criterion fixed before the run in `PREREGISTRATION_pillar_A.md`
(commit d8752f9). `python validation/validation_crossmethod.py data/crossmethod_coverage.csv`.

`crossmethod_coverage.csv`: one row per review x database recall q x dependence rho x chase depth.

| column | meaning |
|---|---|
| regime, graph_seed, seed_size, draw | the simulated review |
| q | probability that the database search includes a relevant record |
| rho | weight of the latent prominence shared with citation (dependence between arms) |
| depth, at_exhaustion | citation-chase iterations completed; whether the chase was exhausted |
| truth | relevant records other than seeds |
| n_db, n_chase, m, observed | arm sizes, overlap, union |
| chapman_* / chao1_* | estimable, N-hat, interval, relative bias (N-hat - truth) / truth, interval covers truth |

`crossmethod_summary.csv` holds the summary by rho, q, regime and depth.

## Result in one line each

- Pillar B, alpha 0.05, scope review: median 19.2% less screening, mean recall loss 0.42 points,
  11.4% of cuts below target; alpha 0.01: 13.1%, 0.29 points, 5.2%.
- Pillar A, rho 0.3, chase to exhaustion: Chapman coverage 95.6% (809 of 810 estimable), median
  relative bias +0.3%: GO.

## Live-data replay (version-1 reviews)

`live_queue_replay.csv`: the within-iteration rule (target 0.95) replayed on iteration 1 of the three version-1 reviews with their
recorded ranking and screening decisions. queue_size counts every candidate, screened_in_rank_order those decided (mid and large were
budget-limited, so their tail is unseen); oracle_* is the screening an oracle stopping at exactly 95% of the screened inclusions needs.

`live_crossmethod_adverse_records.csv`: the adverse review's Scopus export (260 records, the source of all 15 seeds), one row per record:
Scopus EID, DOI, scores of the version-1 screening models (claude-haiku-4-5 gate >= 5, then claude-opus-4-8; claude-sonnet-5 could not be
run, so the decision rule is the mean of the two available models >= 7, applied identically to the citation arm), whether the record is
among the citation-search inclusions, and the chase iteration in which the crawl reached it. Abstracts are not redistributed.
On version-1 records scored by all three models, the two-model rule agrees with the recorded decision for 93.2% (adverse).
`live_crossmethod_adverse_summary.csv`: the Chapman result; overlap m = 0, so the library refuses the estimate.
Scopus retrieval for the three queries (Scopus Search API, 17 November 2026) is in scopus_database_search.json (metadata only).

## Live data: adverse review, iteration 2

`live_iter2_adverse_records.csv`: ranks 1-10,000 of the adverse review's iteration-2 queue (31,486 candidates, version-1 ranking):
work key, rank, DOI, claude-haiku-4-5 and claude-opus-4-8 scores, the two-model decision (mean >= 7 after the haiku gate >= 5) and
whether the record is one of the 56 database (Scopus export) inclusions. `live_iter2_adverse_trajectory.csv`: the Chapman estimate
(database arm 56 inclusions; citation arm iteration 1 plus iteration-2 inclusions screened so far) after 0, 1,000, 2,500, 5,000,
7,500 and 10,000 iteration-2 records. Supplementary material, Section S5.

## SYNERGY+ reviews on their Scopus citation graph

`synergy_scopus_benchmark.csv`: one row per review x draw x variant (28 SYNERGY+ reviews, five draws of five included seeds,
variants full / review_0.05 / review_0.01). Truth = the review authors' own inclusions; candidates the review never screened count
as excluded. n_target = inclusions other than seeds; reachable = inclusions reachable from the seeds through citation links among
inclusions; recall = found / n_target; recall_of_reachable = found / reachable; records_left_unscreened and cuts_below_target as in the
simulation benchmark. `synergy_scopus_summary.csv`: Table S7. `synergy_scopus_per_review.csv`: per-review means (Fig. S2a), with
edges_within (citation links between inclusions) and linked (inclusions linked to at least one other). The Scopus graphs are not
redistributed; validation/synergy_scopus_crawl.py rebuilds them (Scopus API key required). Supplementary material, Section S6.

## SYNERGY+: cross-method estimate and screening models

`synergy_database_searches.json`: for 28 SYNERGY+ reviews, the Scopus query built from the review title and eligibility criteria
(rule in the file), the hit count and the included studies it retrieves. `synergy_crossmethod.csv`: one row per review x draw (seeds
from the database arm): arm sizes, overlap m, observed, truth (inclusions other than seeds), Chapman N-hat and interval, coverage,
relative bias, estimated and true recall of the search. Supplementary material, Section S7.

`synergy_screening_scores.csv`: 1,101 records from six reviews (all inclusions with a Scopus abstract plus 150 random
exclusions each): DOI, the authors' final decision and the 0-10 score of each of 11 models from Anthropic, OpenAI, Google, DeepSeek and xAI (validation/screen_prompt.txt,
validation/screen_vendor.py; analysis validation/compare_vendors.py). `synergy_screening_per_review.csv`, `_paired_differences.csv`
(bootstrap, Holm-adjusted) and `_kappa.csv` support Table S9 and Fig. S4. `synergy_screening_metrics.csv`: AUC, sensitivity, specificity and WSS pooled (review = all)
and per review. Section S8.

## Additions in 2.0.3

- `data/synergy_label_mapping.csv`: for each of the 28 SYNERGY+ reviews, the author-labelled inclusions
  (`label_included = 1` in the SYNERGY+ 3.1 label files), those with a DOI, distinct DOIs, those mapped to
  Scopus by the crawl, and the non-seed reference set used in S6. Totals: 1,522 labelled, 1,489 with a DOI,
  1,435 mapped; the crawl's identifier files held 1,476 distinct DOIs and the step from 1,489 to 1,476 is not
  reconstructible from the retained files.
- `validation/reproduce_screening_tables.py`: recomputes the pooled metrics and the paired differences of
  supplement S8 from `data/synergy_screening_scores.csv` (agreement with the released metrics to 5e-5, the
  rounding of the CSV). `data/synergy_screening_metrics.csv` has 12 rows: 11 models and the mean of their scores;
  per-review values are in `data/synergy_screening_per_review.csv`. Not every CSV has one row per simulated run.
- Holm adjustment: over the 27 distinct pairs formed by the three reference models with the other eight models
  and with each other; a bootstrap p of zero is floored at 1/2000.

## Additions in 2.0.4

- `data/queue_stopping_check_every1.csv` (270 rows, same columns as `queue_stopping_benchmark.csv`, variant `review`,
  alpha 0.05) and `data/synergy_scopus_check_every1.csv` (280 rows, same columns as `synergy_scopus_benchmark.csv`,
  variants `review_0.05` and `review_0.01`): the review scope with the rule evaluated after every decision. Full
  screening is the same run as in the N = 5 files, so savings are paired against it.
  Reproduce with `--check-every 1` (`--variants review` for the simulation, `--variants review_0.05,review_0.01` for
  the published reviews).
