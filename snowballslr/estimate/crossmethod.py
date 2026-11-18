"""Cross-method recall: the database search and citation searching as two capture arms.

Version 1 estimated recall from two bibliographic providers queried by the same crawl.
Those arms are nested or strongly dependent: in simulation their nominal 95% interval
never contained the truth. Version 2 adds the design that the version-1 analysis pointed
to: one arm is the set of studies the review *included from its database search*, the
other the studies *included through citation searching*. The two come from different
discovery processes, and records only the database found are counted even though the
crawl never saw them.

Validation (validation/validation_crossmethod.py, pre-registered in
validation/PREREGISTRATION_pillar_A.md): over 810 simulated reviews with moderate
dependence between the arms, the Chapman interval contained the true population in
95.6% of reviews and the median relative bias was +0.3%. On real reviews with known inclusions
(validation/validation_synergy_crossmethod.py; 21 SYNERGY+ reviews, Scopus) the median bias was
-3.9% but the interval covered the truth in only 62% of estimates: both methods favour
well-connected studies, so the population, and hence the share still missing, is underestimated.
Treat the recall as optimistic and the estimated number of missing studies as a minimum.

Seeds normally come from the database search, so they belong to the database arm and
cannot be "found" by citation searching. They are therefore removed from both arms
and from the population: the estimate concerns relevant records other than the seeds.

Records are matched by DOI. A record without a DOI cannot be matched; it is counted in
its own arm as unshared, which inflates the estimate and so understates recall rather
than overstating it.
"""
from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from typing import Any

from ..types import Decision
from .capture_recapture import chapman
from .membership import MembershipSet, normalize_doi

__all__ = ["cross_method_estimate", "parse_doi_list"]

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>,;]+", re.I)


def parse_doi_list(text: str, *, doi_column: str = "DOI") -> tuple[set[str], int]:
    """DOIs from a CSV export (``doi_column``), an RIS file (DO tags) or plain lines.

    Returns the normalised DOIs and the number of records that carried none.
    """
    head = text.lstrip("\ufeff")[:4000]
    if re.search(r"(?m)^TY  - ", head):
        recs = re.split(r"(?m)^ER  -.*$", text)
        dois, missing = set(), 0
        for r in recs:
            if not r.strip():
                continue
            m = re.search(r"(?m)^DO  - (.+)$", r)
            d = normalize_doi(m.group(1).strip()) if m else None
            if d:
                dois.add(d)
            missing += d is None
        return dois, missing
    first = head.splitlines()[0] if head.splitlines() else ""
    if doi_column in [c.strip().strip('"') for c in re.split(r"[,;\t]", first)]:
        delim = max(",;\t", key=first.count) if any(d in first for d in ",;\t") else ","
        rows = list(csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=delim))
        dois = {d for d in (normalize_doi(r.get(doi_column)) for r in rows) if d}
        return dois, sum(1 for r in rows if not normalize_doi(r.get(doi_column)))
    dois, missing = set(), 0
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _DOI_RE.search(line)
        d = normalize_doi(m.group(0).rstrip(".")) if m else None
        if d:
            dois.add(d)
        missing += d is None
    return dois, missing


def cross_method_estimate(
    state: Any, database: MembershipSet | Iterable[str], *, database_without_doi: int = 0
) -> dict[str, Any]:
    """Chapman estimate over (database-included, citation-included), seeds removed."""
    if not isinstance(database, MembershipSet):
        database = MembershipSet.from_dois("database", database)
        n_db_missing = database_without_doi
    else:
        n_db_missing = database.n_without_doi + database_without_doi
    seeds = set(state.seeds)
    seed_dois = {d for d in (normalize_doi(state.works[k].doi) for k in seeds if k in state.works) if d}
    chase, chase_missing = set(), 0
    for key, value in state.decisions.items():
        if value != Decision.INCLUDE or key in seeds:
            continue
        d = normalize_doi(state.works[key].doi) if key in state.works else None
        if d is None:
            chase_missing += 1
        elif d not in seed_dois:
            chase.add(d)
    db = set(database.dois) - seed_dois
    m = len(db & chase)
    n1 = len(db) + n_db_missing
    n2 = len(chase) + chase_missing
    observed = n1 + n2 - m
    est = chapman(n1, n2, m, n_observed=observed)
    # Chapman's own calibration warning was measured on version-1 provider arms; the
    # cross-method design has its own validation, reported in the result instead.
    warnings = [w for w in est.warnings if "not calibrated" not in w]
    not_in_db = len(seed_dois - set(database.dois))
    if not_in_db:
        warnings.append(
            f"{not_in_db} seed(s) are not in the database set; the design assumes seeds "
            "come from the database search, so check that the file lists its included studies")
    if n_db_missing or chase_missing:
        warnings.append(
            f"{n_db_missing + chase_missing} record(s) without a DOI were counted as unshared; "
            "this lowers the recall estimate")
    out: dict[str, Any] = {
        "method": "cross_method_chapman",
        "estimable": bool(est.estimable and est.n_hat),
        "n_database": n1, "n_citation": n2, "m": m, "n_observed": observed,
        "seeds_removed": len(seeds),
        "reason": est.reason, "warnings": warnings,
    }
    if out["estimable"]:
        lo, hi = est.n_hat_ci
        out.update(
            n_hat=round(est.n_hat, 1), n_hat_ci=[round(lo, 1), round(hi, 1)],
            recall_combined=round(observed / est.n_hat, 4),
            recall_combined_ci=[round(observed / hi, 4), round(min(1.0, observed / lo), 4)],
            recall_citation_only=round(n2 / est.n_hat, 4),
            recall_database_only=round(n1 / est.n_hat, 4),
            validated=("simulation: interval coverage 95.6%, median bias +0.3% (810 reviews); real reviews with known "
                       "inclusions: coverage 62%, median bias -3.9% (77 estimates, "
                       "21 SYNERGY+ reviews) - recall tends to be overestimated"),
        )
    return out
