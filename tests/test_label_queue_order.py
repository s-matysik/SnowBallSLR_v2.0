"""The within-iteration test saved by Run.label equals the one shown before labelling."""

import json
from pathlib import Path

import pytest

from snowballslr.config import Config
from snowballslr.core.run import Run
from snowballslr.report.prisma import build_counts
from snowballslr.simulation.oracle import Oracle

FX = Path(__file__).parent / "fixtures"


@pytest.fixture
def setup(tmp_path):
    graph = json.loads((FX / "mini_graph.json").read_text())
    oracle = Oracle.from_file(FX / "mini_gold.csv")
    cfg = Config.model_validate(
        {"stopping": {"within_iteration": {"target": 0.95, "alpha": 0.05, "scope": "review"}}}
    )
    run = Run.init(tmp_path / "r", sorted(oracle.included)[:3], cfg, offline_graph=graph)
    return run, oracle


def _decide(run, oracle, k):
    order = [w.key for w in run.step()]
    return order, {key: ("include" if key in oracle.included else "exclude") for key in order[:k]}


def test_saved_result_equals_preview_in_the_first_iteration(setup):
    run, oracle = setup
    order, dec = _decide(run, oracle, 49)
    assert len(order) > len(dec) and any(v == "include" for v in dec.values())
    preview = run.queue_test(dec)
    run.label(dec)
    saved = run.state.queue_tests[-1]
    for field in ("prior_relevant", "prior_unseen", "p_min", "stop", "n_remaining"):
        assert saved[field] == preview[field], field
    # No earlier iteration exists, so nothing can count as an earlier inclusion.
    assert saved["prior_relevant"] == 0


def test_prior_relevant_counts_only_earlier_iterations(setup):
    run, oracle = setup
    _order, dec = _decide(run, oracle, 10**6)
    run.label(dec)
    if run.stopped:
        pytest.skip("fixture review ended after one iteration")
    earlier = len([k for k in run.state.included_keys if k not in set(run.state.seeds)])
    _order2, dec2 = _decide_next(run, oracle)
    preview = run.queue_test(dec2)
    run.label(dec2)
    saved = run.state.queue_tests[-1] if run.state.queue_tests else None
    if preview is not None and preview["n_remaining"] > 0:
        assert saved["prior_relevant"] == preview["prior_relevant"] == earlier


def _decide_next(run, oracle):
    order = list(run.state.pending) or [w.key for w in run.step()]
    k = max(1, len(order) // 2)
    return order, {key: ("include" if key in oracle.included else "exclude") for key in order[:k]}


def test_prisma_separates_rule_stop_from_reviewer_ending_the_iteration(setup):
    run, oracle = setup
    order, dec = _decide(run, oracle, 1)
    preview = run.queue_test(dec)
    assert preview["stop"] is False
    run.label(dec)
    counts = build_counts(run.state).to_dict()
    assert "records_not_screened_within_iteration_stop" not in counts
    assert counts["records_not_screened_other"] == len(order) - 1


def test_prisma_reports_rule_stop_when_the_test_is_met(setup):
    run, oracle = setup
    order, dec = _decide(run, oracle, 49)
    assert run.queue_test(dec)["stop"] is False  # review scope, first iteration: not yet met
    # Include every record with the oracle label first, so the prefix is all relevant.
    inc_first = sorted(order, key=lambda k: k not in oracle.included)
    run.state.pending = inc_first
    dec2 = {key: ("include" if key in oracle.included else "exclude") for key in inc_first[:40]}
    pre = run.queue_test(dec2)
    run.label(dec2)
    counts = build_counts(run.state).to_dict()
    if pre["stop"]:
        assert counts["records_not_screened_within_iteration_stop"] == len(order) - 40
        assert "records_not_screened_other" not in counts
    else:
        assert counts["records_not_screened_other"] == len(order) - 40
