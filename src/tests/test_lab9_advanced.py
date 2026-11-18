"""M5-M7 self-check (Advanced/Expert). Run: python -m pytest -q -m student -o addopts= -k advanced
Public vectors only; the instructor grades with hidden ones."""
import copy
import math

import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def stats():
    from lab9 import stats

    return stats


@pytest.mark.parametrize("n,c,k,want", [(5, 5, 5, 1.0), (5, 0, 1, 0.0), (5, 2, 1, 0.4), (10, 3, 3, 1 - 35 / 120)])
def test_pass_at_k(stats, n, c, k, want):
    assert math.isclose(stats.pass_at_k(n, c, k), want, abs_tol=1e-9)


@pytest.mark.parametrize("n,c,k,want", [(5, 5, 5, 1.0), (5, 4, 5, 0.0), (5, 4, 3, 0.4), (10, 8, 2, 28 / 45)])
def test_pass_hat_k(stats, n, c, k, want):
    assert math.isclose(stats.pass_hat_k(n, c, k), want, abs_tol=1e-9)


def test_pass_k_rejects_bad_args(stats):
    for args in [(5, 6, 1), (5, 2, 0), (3, 1, 4), (0, 0, 0), (5, -1, 1), (5, 2, -1),
                 (5, 2.5, 1), (5, 2, True)]:
        with pytest.raises(ValueError):
            stats.pass_at_k(*args)
        with pytest.raises(ValueError):
            stats.pass_hat_k(*args)


def _report(rows, metrics, items=4, seeds=(1, 2)):
    return {"manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)},
            "rows": rows, "metrics": metrics, "evaluator_failures": []}


ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["denial"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2", "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                                               "threshold": {"min": 0.8}}]}


def test_integrity_flags_nan_and_dropped_rows():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    assert gate.integrity_check(base, base, SPEC) == []
    nan = _report(copy.deepcopy(ROWS), {"pass_rate": float("nan")})
    assert gate.integrity_check(nan, base, SPEC)
    dropped = _report(copy.deepcopy(ROWS[:-1]), {"pass_rate": 1.0})
    assert gate.integrity_check(dropped, base, SPEC)


def test_integrity_flags_loosened_spec():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    loose = copy.deepcopy(SPEC)
    loose["metrics"][0]["threshold"]["min"] = 0.5
    assert gate.integrity_check(base, base, loose, SPEC)
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_slice_check_blocks_a_slice_below_floor():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    rows = copy.deepcopy(ROWS)
    for r in rows:
        if "denial" in r["slices"] and r["seed"] == 1:
            r["pass_rate"] = False
    spec = dict(SPEC, slices=[{"name": "denial", "metric": "pass_rate", "min": 0.9, "blocking": True}])
    blocked, _ = gate.slice_check(_report(rows, {"pass_rate": 0.75}), base, spec)
    assert blocked == ["slice:denial/pass_rate"]


def test_integrity_rejects_duplicate_rows_and_evaluator_failures():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    duplicate = copy.deepcopy(base)
    duplicate["rows"][0] = copy.deepcopy(duplicate["rows"][1])
    assert gate.integrity_check(duplicate, base, SPEC)
    crashed = copy.deepcopy(base)
    crashed["evaluator_failures"] = ["E-001:grader:error"]
    assert gate.integrity_check(crashed, base, SPEC)


def test_integrity_rejects_slice_relabel_and_forged_metrics():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    relabelled = copy.deepcopy(base)
    for row in relabelled["rows"]:
        if row["item_id"] == "E-000":
            row["slices"] = []
    assert gate.integrity_check(relabelled, base, SPEC)
    forged = copy.deepcopy(base)
    forged["rows"][0]["pass_rate"] = False
    assert gate.integrity_check(forged, base, SPEC)


def test_ratchet_rejects_removed_slice_and_regression_check():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    original = copy.deepcopy(SPEC)
    original["metrics"][0]["threshold"]["no_significant_drop"] = True
    original["slices"] = [{"name": "denial", "metric": "pass_rate", "min": 0.9,
                           "no_significant_drop": True, "blocking": True}]
    loose = copy.deepcopy(original)
    del loose["metrics"][0]["threshold"]["no_significant_drop"]
    loose["slices"] = []
    assert gate.integrity_check(base, base, loose, original)
    changed_version = copy.deepcopy(original)
    changed_version["eval_set_version"] = "v3"
    assert gate.integrity_check(base, base, changed_version, original)


def test_slice_check_rejects_missing_slice():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    spec = dict(SPEC, slices=[{"name": "missing", "metric": "pass_rate", "min": 0.9, "blocking": True}])
    blocked, _ = gate.slice_check(base, base, spec)
    assert blocked == ["slice:missing/pass_rate"]


def test_ci_check_accepts_derived_pass_hat_without_a_grader():
    from lab9 import ci_check

    report = {"shape": "swarm", "manifest": {"eval_set_sha": "x"},
              "metrics": {"pass_hat_5": 1.0, "reply_amount_matches_ledger": 1.0}}
    spec = {"pass_k": [5], "metrics": [
        {"id": "pass_hat_5", "kind": "capability", "blocking": True},
        {"id": "reply_amount_matches_ledger", "kind": "capability", "blocking": True},
    ]}
    assert ci_check.check(report, report, spec) == []
