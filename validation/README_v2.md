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

`queue_stopping_paired_summary.csv` holds the paired summary reported in the article.

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

- Pillar B, alpha 0.05, scope review: median 19.3% less screening, mean recall loss 0.42 points,
  11.4% of cuts below target; alpha 0.01: 13.2%, 0.29 points, 5.2%.
- Pillar A, rho 0.3, chase to exhaustion: Chapman coverage 95.6% (809 of 810 estimable), median
  relative bias +0.3%: GO.
