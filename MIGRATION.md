# Migrating from version 1 (1.0.x) to version 2

Nothing in a version-1 workflow has to change.

- **Configurations.** Every version-1 `config.yaml` loads unchanged and keeps its configuration
  hash: fields added in version 2 are left out of the hash while unset
  (`tests/test_queue.py::test_default_configuration_keeps_the_version_1_hash`). Two archived
  runs written by 1.0.0 (`run_adverse`, `run_narrow` in the v1 repository) do not reproduce
  their recorded hash under 1.0.5 either; that predates version 2.
- **Run directories.** Version 2 reads version-1 run directories. `state.json` gains a
  `queue_tests` key and `prisma.json` a `records_not_screened_within_iteration_stop` count only
  in runs that use the within-iteration rule.
- **Dependencies.** `rapidfuzz` is no longer required; deduplication uses a pure-Python
  Jaro-Winkler that is bit-equal to rapidfuzz's reference implementation. `typer` is needed by
  the command line only.
- **OpenAlex.** Without an API key OpenAlex now refuses cursor paging, so forward chasing of a
  seed cited more than 200 times fails. Set `OPENALEX_API_KEY` (free at
  openalex.org/settings/api). The key is sent on the wire only and never stored in a run.
- **New, opt-in.** `stopping.within_iteration` and `snowballslr estimate --database`; see the
  README section "What is new in version 2".
