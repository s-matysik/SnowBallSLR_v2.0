# Changelog

All notable changes since the version described in SoftwareX 36 (2026) 103116.

## [2.0.3] - 2026-11-19

### Changed
- Wording of the cross-method estimate (library docstring, README, application hint): on real reviews recall tended to be
  overestimated and the missing count underestimated; these are observed tendencies, not bounds.
- `CITATION.cff` repository-code points to this repository.

### Added
- `data/synergy_label_mapping.csv` (per-review label and mapping counts), `data/synergy_screening_paired_differences.csv`
  (27 distinct pairs, Holm-adjusted), `validation/reproduce_screening_tables.py` (recomputes the S8 tables from the released scores).
- The 11-model screening comparison, the real-data cross-method study and the SYNERGY+ benchmark (data and scripts).

## [2.0.2] - 2026-11-19

### Fixed
- The within-iteration test saved with a labelled batch (`state.queue_tests`, PRISMA counts) is now
  evaluated on the batch being submitted, before the decisions are written to the state. Evaluated
  afterwards, the review scope counted the queue's own inclusions as earlier-iteration inclusions
  (`prior_relevant`), so the saved result could differ from the one shown to the reviewer
  (worked case on the offline fixture: preview p = 0.235, not met; saved p = 0.041, met). The
  published benchmarks decide stops through `Run.queue_test` before labelling and are unaffected:
  the 420 SYNERGY+ runs and both simulation grids (270 reviews at alpha 0.05 and 0.01) were rerun
  with this version and reproduce every recorded count exactly.
- PRISMA now separates records left unscreened because the criterion was met
  (`records_not_screened_within_iteration_stop`) from records left unscreened because the reviewer
  ended the iteration with the criterion not met (`records_not_screened_other`).

### Documentation
- Supplement corrections: two cells of Table S4 and four of Table S2 were mis-rounded; the iteration-1
  citation arm of the adverse review is 177 distinct records (two inclusion keys were duplicates merged
  by identity resolution), so Table S6 was recomputed.

## [2.0.0] - 2026-11-17

### Added
- Repository imported from s-matysik/SnowBallSLR at tag v1.0.5 (commit 065bac5).
- README section restoring the command-line and Python snippets altered by typesetting in the
  published v1 article.
- `snowballslr.identity.jaro`: pure-Python Jaro-Winkler, bit-equal to rapidfuzz's reference
  implementation on 240,000 comparisons of real titles (`validation/jaro_equality.json`).

- `snowballslr.providers.transport`: provider HTTP clients are built through one function, and a
  browser transport carries requests over synchronous `XMLHttpRequest` in a Web Worker, dropping
  the request headers browsers forbid script to set.
- `snowballslr/_version.py` as the single source of the version, read by the build backend and by
  the run manifest (v1 kept a second copy in `core/run.py`).
- Publishing to PyPI through Trusted Publishing (`.github/workflows/publish.yml`, `RELEASING.md`).

- OpenAlex API key support through the `OPENALEX_API_KEY` environment variable. The key is sent
  as a query parameter on the wire only (`BaseProvider.secret_params`): it is excluded from cache
  keys, cache entries, `config.yaml`, the configuration hash and every error message, so a run
  directory can be shared without it. Measured on 12 November 2026: without a key OpenAlex now
  answers the first page of a query but returns HTTP 401 for any cursor page ("Paging past the first
  page with cursor= needs a free API key"), so in v1 the forward chase of any seed cited more than
  200 times fails.

- `snowballslr.web.Session`: JSON-in/JSON-out session API used by the browser app, so the app holds
  no review logic of its own; `pack` makes a deterministic run archive and `verify_archive` replays
  a received archive from its own cache without network access.
- Browser-CLI parity check (`validation/parity/`, CI job `browser-parity`): a complete review run
  through CPython 3.12 and through Pyodide 0.28.3 (Python 3.13, WebAssembly) yields identical artifact
  hashes, per-iteration records, candidate order, recall estimate and stop rule, and each runtime
  verifies the other's archive.

- Browser app (`docs/app/index.html`, published at https://s-matysik.github.io/SnowBallSLR_v2.0/app/):
  the library itself, in Pyodide in a Web Worker, with three modes: a new review (seeds, screening
  with keyboard shortcuts, stopping-rule table, PRISMA diagram, report and run.zip downloads),
  continuing a review from a run.zip made here or on the command line, and verifying a received
  run.zip with no network access, for reviewers and editors. Reviews autosave in the browser
  (IndexedDB). An offline demo runs on a frozen citation graph. `docs/build_app.py` builds the
  wheel from the same commit into the site.
- End-to-end browser test (`validation/browser/`, CI job `browser-e2e`) in Chromium, followed by
  command-line verification of the archives the browser produced.

- Within-iteration stopping (`stopping.within_iteration`, `snowballslr.stopping.queue`): ranked
  quasi-sampling test of Callaghan and Mueller-Hansen (2020) on the screened top of each iteration's
  ranked queue, scope `review` (default; pools earlier iterations) or `queue`. `Run.queue_test`,
  `Session.queue_test`, a live indicator in the browser app, the test recorded in `state.json`
  (`queue_tests`, only when used) and a PRISMA box for records left unscreened. Paired benchmark on
  270 simulated reviews: `validation/validation_queue_stopping.py`, `data/queue_stopping_benchmark.csv`
  (alpha 0.05) and `data/queue_stopping_alpha001.csv` (alpha 0.01).
- Cross-method recall (`snowballslr.estimate.crossmethod`, `snowballslr estimate --database`,
  `Session.cross_method`): Chapman over the studies included from the database search and those
  included through citation searching, seeds removed, DOI matching with unmatched records counted
  against recall. Pre-registered go/no-go study (`validation/PREREGISTRATION_pillar_A.md`,
  `validation/validation_crossmethod.py`, `data/crossmethod_coverage.csv`): GO.
- `MIGRATION.md`, `validation/README_v2.md` (experiments and CSV data dictionary).

### Changed
- The test-suite network guard blocks httpx's socket transport rather than `Client.get`, so
  in-memory transports can be tested; real requests from tests still fail (INV-4).
- Deduplication and GROBID reference matching use the pure-Python Jaro-Winkler unconditionally.
  The compiled rapidfuzz wheel fuses the Winkler step into a fused multiply-add on arm64, so its
  scores differ from the reference in the last bit on 358 of those 240,000 comparisons and can differ
  between machines. Scores are written to `audit.jsonl`, so this mattered for byte-identical audit
  logs across platforms; it did not affect `run.json`, which does not hash the audit log, and a
  merge decision changes only when a score lies within one unit in the last place of the threshold.
  The pure implementation is also what makes the library importable in Pyodide.

- `validation_generator.generate_graph` also returns each work's latent prominence (`latent`); the
  random sequence is unchanged, so every published benchmark figure is reproduced as before.

### Removed
- `rapidfuzz` as a runtime dependency (kept in the `dev` extra as a test reference).## 2.0.1

### Changed

- Cross-method recall: the result's `validated` field and the documentation now report the real-data
  study (`validation/validation_synergy_crossmethod.py`, 21 SYNERGY+ reviews with Scopus searches and citation
  graphs): median bias -3.9%, interval coverage 62%. The estimate is optimistic on real data.
- Real-data benchmark of the within-iteration rule on 28 SYNERGY+ reviews (`validation/validation_synergy_scopus.py`).


