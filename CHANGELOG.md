# Changelog

All notable changes since the version described in SoftwareX 36 (2026) 103116.

## [Unreleased] - 2.0.0

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

### Removed
- `rapidfuzz` as a runtime dependency (kept in the `dev` extra as a test reference).
