"""Within-iteration stopping on the ranked candidate queue.

Every iteration produces a queue of candidates ranked by predicted relevance. The
reviewer screens it from the top. This module answers, at any point, whether the
rest of the queue may be left unscreened: it tests the null hypothesis that recall
*within the queue* is below a target, using the ranked quasi-sampling criterion of
Callaghan and Mueller-Hansen (2020, Systematic Reviews 9:273, doi:10.1186/s13643-020-01521-4).

For every split point i of the screened prefix, the last ``n = n_seen - i`` screened
records are treated as if they were a random sample from the ``N = n_queue - i``
records that were unseen at i. With ``rho_al`` relevant records found before i and
``k`` after it, the smallest number of relevant records remaining at i that is
compatible with recall below the target is

    K_tar = floor((rho_al + k) / target - rho_al + 1)

and the p-value is ``P(X <= k)`` for ``X ~ Hypergeometric(N, K_tar, n)``. The minimum
over all split points is compared with ``alpha``. Because the queue is ranked, the
screened records are at least as rich in relevant records as a random sample of the
remainder would be, which is what makes the criterion conservative; if the ranking is
no better than random it reduces to a sampling test taken at its best split, so the
benchmark checks the guarantee under random order as well.

Two scopes are offered. ``queue`` applies the test to the current queue alone.
``review`` pools the review so far: records screened in earlier iterations precede the
current queue in the screening order, and candidates left unscreened earlier are still
part of the unseen population, so the target is recall over every record identified so
far. Pooling matters because the criterion needs roughly 1/(1 - target) relevant records
before it can save anything (19 at a 95% target), which a single snowballing queue often
does not contain. As in the reference implementation, the start of the current queue is
itself a split point.

The test concerns recall over identified records. A relevant record left unscreened is not expanded, so
its own references and citations are not followed; the effect on the review as a
whole is measured by ``validation/validation_queue_stopping.py``, not guaranteed here.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import hypergeom

__all__ = ["CITATION", "QueueTest", "queue_test"]

CITATION = "Callaghan and Mueller-Hansen (2020), doi:10.1186/s13643-020-01521-4"


@dataclass(frozen=True, slots=True)
class QueueTest:
    n_queue: int
    n_screened: int
    n_relevant: int
    target: float
    alpha: float
    p_min: float
    split_at: int | None
    stop: bool

    @property
    def n_remaining(self) -> int:
        return self.n_queue - self.n_screened

    def rationale(self) -> str:
        if self.n_screened == 0:
            return "Nothing screened in this iteration yet."
        if self.n_remaining == 0:
            return "The whole queue has been screened."
        if self.stop:
            return (
                f"H0 'recall within this iteration's queue is below {self.target:.0%}' rejected "
                f"(p = {self.p_min:.3g} < {self.alpha}); the remaining {self.n_remaining} "
                f"of {self.n_queue} candidates may be left unscreened."
            )
        return (
            f"H0 'recall within this iteration's queue is below {self.target:.0%}' not rejected "
            f"(p = {self.p_min:.3g}, needs < {self.alpha}); keep screening."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": "ranked_quasi_sampling",
            "reference": CITATION,
            "n_queue": self.n_queue,
            "n_screened": self.n_screened,
            "n_relevant": self.n_relevant,
            "n_remaining": self.n_remaining,
            "target": self.target,
            "alpha": self.alpha,
            "p_min": None if math.isnan(self.p_min) else round(self.p_min, 6),
            "split_at": self.split_at,
            "stop": self.stop,
            "rationale": self.rationale(),
        }


def queue_test(
    relevant: Sequence[bool],
    n_queue: int,
    *,
    target: float = 0.95,
    alpha: float = 0.05,
    prior_relevant: int = 0,
    prior_unseen: int = 0,
) -> QueueTest:
    """Test a screened prefix of a ranked queue.

    ``relevant`` holds the decisions for the first ``len(relevant)`` records of the
    queue, in rank order (True = include). ``n_queue`` is the full queue length.
    ``prior_relevant`` and ``prior_unseen`` pool earlier iterations (scope ``review``):
    relevant records found before this queue, and candidates still unscreened from
    earlier queues. Both are zero for scope ``queue``.
    """
    if not 0 < target < 1:
        raise ValueError("target must lie strictly between 0 and 1")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie strictly between 0 and 1")
    n_seen = len(relevant)
    if n_seen > n_queue:
        raise ValueError(f"{n_seen} decisions for a queue of {n_queue}")
    rho = int(sum(bool(x) for x in relevant))
    if prior_relevant < 0 or prior_unseen < 0:
        raise ValueError("prior counts must be non-negative")
    if n_seen == n_queue and prior_unseen == 0:
        # Nothing is left to skip; recall within the queue is 1 by construction.
        return QueueTest(n_queue, n_seen, rho, target, alpha, 0.0, None, n_seen > 0)
    if n_seen < 1:
        return QueueTest(n_queue, n_seen, rho, target, alpha, float("nan"), None, False)

    cum = np.concatenate([[0], np.cumsum(np.asarray(relevant, dtype=np.int64))])
    i = np.arange(0, n_seen)                 # split points within this queue
    rho_al = prior_relevant + cum[i]         # relevant found before the split
    k = rho - cum[i]                         # relevant in the quasi-sample
    n = n_seen - i                           # quasi-sample size
    big_n = n_queue - i + prior_unseen       # records unseen at the split
    k_tar = np.floor((prior_relevant + rho) / target - rho_al + 1).astype(np.int64)
    p = np.ones_like(i, dtype=float)
    # More relevant records than unseen ones cannot remain: H0 is impossible there.
    impossible = k_tar > big_n
    p[impossible] = 0.0
    ok = ~impossible
    p[ok] = hypergeom.cdf(k[ok], big_n[ok], k_tar[ok], n[ok])
    j = int(np.argmin(p))
    p_min = float(p[j])
    return QueueTest(n_queue, n_seen, rho, target, alpha, p_min, int(i[j]), p_min < alpha)
