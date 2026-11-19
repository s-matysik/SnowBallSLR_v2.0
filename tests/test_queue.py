"""Within-iteration (ranked queue) stopping: the test itself, and its use in a run."""

import json
import math

import pytest

from snowballslr import Config
from snowballslr.core.run import Run
from snowballslr.report.prisma import build_counts
from snowballslr.stopping.queue import queue_test

V1_DEFAULT_CONFIG_HASH = "sha256:eb9d8772780da480fabaf8a765aa17c5686906735136a9b12fbedcd67b905ff5"


def _hyper_cdf(k, big_n, big_k, n):
    tot = math.comb(big_n, n)
    return sum(math.comb(big_k, x) * math.comb(big_n - big_k, n - x) for x in range(0, k + 1)) / tot


def _p_min_by_hand(labels, n_queue, target):
    best = 1.0
    rho = sum(labels)
    for i in range(0, len(labels)):
        rho_al = sum(labels[:i])
        k, n, big_n = rho - rho_al, len(labels) - i, n_queue - i
        k_tar = math.floor(rho / target - rho_al + 1)
        p = 0.0 if k_tar > big_n else _hyper_cdf(k, big_n, k_tar, n)
        best = min(best, p)
    return best


@pytest.mark.parametrize("labels,n_queue", [
    ([True] * 8 + [False] * 30, 60),
    ([True, False] * 6 + [False] * 40, 90),
    ([False] * 25, 40),
    ([True] * 3 + [False] * 50 + [True] + [False] * 20, 80),
])
def test_p_min_matches_the_formula_of_callaghan_and_mueller_hansen(labels, n_queue):
    t = queue_test(labels, n_queue, target=0.95, alpha=0.05)
    assert t.p_min == pytest.approx(_p_min_by_hand(labels, n_queue, 0.95), rel=1e-9, abs=1e-12)
    assert t.stop == (t.p_min < 0.05)


def test_a_rich_head_and_a_long_empty_tail_allows_stopping():
    t = queue_test([True] * 60 + [False] * 200, 400)
    assert t.stop and t.n_remaining == 140
    assert "rejected" in t.rationale()


def test_few_relevant_records_need_almost_the_whole_queue():
    # Below 1/(1 - target) relevant records K_tar is 1, so ~95% of the rest must be seen.
    assert not queue_test([True] * 12 + [False] * 120, 400).stop


def test_pooling_earlier_iterations_lets_a_thin_queue_stop():
    thin = [True] * 4 + [False] * 120
    assert not queue_test(thin, 200).stop
    assert queue_test(thin, 200, prior_relevant=300).stop
    # Unscreened leftovers of earlier queues enlarge the unseen population.
    assert queue_test(thin, 200, prior_relevant=300, prior_unseen=4000).p_min > \
        queue_test(thin, 200, prior_relevant=300).p_min


@pytest.mark.parametrize("labels,n_queue,prior", [
    ([True] * 5 + [False] * 60, 150, 40), ([False, True] * 10 + [False] * 30, 90, 120)])
def test_pooled_p_min_matches_the_formula(labels, n_queue, prior):
    best = 1.0
    rho = sum(labels)
    for i in range(0, len(labels)):
        rho_al = prior + sum(labels[:i])
        k, n, big_n = rho - sum(labels[:i]), len(labels) - i, n_queue - i
        k_tar = math.floor((prior + rho) / 0.95 - rho_al + 1)
        best = min(best, 0.0 if k_tar > big_n else _hyper_cdf(k, big_n, k_tar, n))
    assert queue_test(labels, n_queue, prior_relevant=prior).p_min == pytest.approx(best, rel=1e-9, abs=1e-12)


def test_an_empty_queue_cannot_be_cut_short_cheaply():
    # With no relevant record seen, 95% recall is only supported by screening ~95%.
    assert not queue_test([False] * 80, 100).stop
    assert queue_test([False] * 96, 100).stop


def test_whole_queue_and_tiny_prefixes():
    assert queue_test([False, True, False], 3).stop
    assert not queue_test([True], 50).stop
    assert not queue_test([], 50).stop
    with pytest.raises(ValueError):
        queue_test([True] * 4, 3)
    with pytest.raises(ValueError):
        queue_test([True], 3, target=1.0)


def test_default_configuration_keeps_the_version_1_hash():
    assert Config().config_hash == V1_DEFAULT_CONFIG_HASH
    on = Config.model_validate({"stopping": {"within_iteration": {}}})
    assert on.config_hash != V1_DEFAULT_CONFIG_HASH
    assert on.stopping.within_iteration.target == 0.95


def _run(tmp_path, graph, oracle, rule=True):
    cfg = Config.model_validate({"stopping": {"within_iteration": {}}} if rule else {})
    return Run.init(tmp_path / "r", sorted(oracle.included)[:3], cfg, offline_graph=graph)


def test_run_records_the_test_and_prisma_counts_the_skipped(tmp_path, graph, oracle):
    run = _run(tmp_path, graph, oracle)
    cands = run.step()
    k = len(cands) // 2
    head = {w.key: oracle.decide(w.key) for w in cands[:k]}
    res = run.queue_test(head)
    assert res["n_screened"] == k and res["n_remaining"] == len(cands) - k
    run.label(head)
    assert len(run.state.queue_tests) == 1
    qt = run.state.queue_tests[0]
    assert qt["iteration"] == 1 and len(qt["left_unscreened"]) == len(cands) - k
    counts = build_counts(run.state).to_dict()
    # The skipped records are reported under the reason that applies: a met criterion,
    # or the reviewer ending the iteration while the criterion was not yet met.
    field = ("records_not_screened_within_iteration_stop" if qt["stop"]
             else "records_not_screened_other")
    assert counts[field] == len(cands) - k
    assert (len(counts) and sum(counts.get(f, 0) for f in (
        "records_not_screened_within_iteration_stop", "records_not_screened_other"))) == len(cands) - k
    saved = json.loads((tmp_path / "r" / "state.json").read_text())
    assert saved["queue_tests"][0]["n_queue"] == len(cands)


def test_out_of_order_screening_is_not_accepted(tmp_path, graph, oracle):
    run = _run(tmp_path, graph, oracle)
    cands = run.step()
    skip_first = {w.key: oracle.decide(w.key) for w in cands[1:6]}
    res = run.queue_test(skip_first)
    assert res["stop"] is False and "out of rank order" in res["rationale"]


def test_runs_without_the_rule_are_unchanged(tmp_path, graph, oracle):
    run = _run(tmp_path, graph, oracle, rule=False)
    cands = run.step()
    assert run.queue_test({w.key: "exclude" for w in cands}) is None
    run.label({w.key: oracle.decide(w.key) for w in cands})
    saved = json.loads((tmp_path / "r" / "state.json").read_text())
    assert "queue_tests" not in saved
    assert "records_not_screened_within_iteration_stop" not in build_counts(run.state).to_dict()
