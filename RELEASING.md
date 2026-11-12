# Releasing

Releases are published to PyPI by `.github/workflows/publish.yml` using Trusted
Publishing, so no API token exists to leak.

## One-time setup on PyPI

On <https://pypi.org/manage/account/publishing/>, add a *pending publisher*:

| field | value |
|---|---|
| PyPI project name | `snowballslr` |
| Owner | `s-matysik` |
| Repository name | `SnowBallSLR_v2.0` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

## Each release

1. Set the version in `snowballslr/_version.py` (the only place it is written) and in
   `CITATION.cff`, and add the entry to `CHANGELOG.md`.
2. Push an annotated tag `v<version>`. The workflow refuses a tag that does not match the
   package version, builds, checks the wheel imports without its CLI dependency, and
   publishes.
