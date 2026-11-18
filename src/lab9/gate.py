"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def _ratchet_check(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    problems = []

    def compare(current: dict, previous: dict, label: str, *, is_slice: bool = False) -> None:
        if previous.get("blocking") and not current.get("blocking"):
            problems.append(f"{label}: blocking removed")
        for field in ("kind", "grader", "level") if not is_slice else ():
            if field in previous and current.get(field) != previous[field]:
                problems.append(f"{label}: {field} changed")
        new_threshold = current if is_slice else current.get("threshold", {})
        old_threshold = previous if is_slice else previous.get("threshold", {})
        for key in ("min", "max", "max_increase"):
            if key not in old_threshold:
                continue
            old, new = old_threshold[key], new_threshold.get(key)
            if (not isinstance(new, (int, float)) or not math.isfinite(new)
                    or (key == "min" and new < old)
                    or (key != "min" and new > old)):
                problems.append(f"{label}: {key} removed or loosened")
        if old_threshold.get("no_significant_drop") and not new_threshold.get("no_significant_drop"):
            problems.append(f"{label}: no_significant_drop removed")

    for collection, key_fn in (
        ("metrics", lambda entry: entry["id"]),
        ("slices", lambda entry: (entry["name"], entry["metric"])),
    ):
        current_entries = spec.get(collection, [])
        current = {key_fn(entry): entry for entry in current_entries}
        if len(current) != len(current_entries):
            problems.append(f"duplicate {collection} entries")
        for previous in base_spec.get(collection, []):
            key = key_fn(previous)
            label = f"{collection}:{key}"
            if key not in current:
                problems.append(f"{label} removed")
            else:
                compare(current[key], previous, label, is_slice=collection == "slices")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems = []
    graded = [m["id"] for m in spec["metrics"]
              if m["id"] in GRADERS or m.get("grader") == "code"]
    keys_by_report = []
    slices_by_report = []
    for name, report in (("PR", pr), ("baseline", base)):
        manifest = report.get("manifest", {})
        rows = report.get("rows", [])
        metrics = report.get("metrics", {})
        seeds = manifest.get("seeds", [])
        item_count = manifest.get("items")
        if not isinstance(rows, list) or not isinstance(metrics, dict) or not isinstance(seeds, list):
            problems.append(f"{name}: invalid report structure")
            keys_by_report.append(set())
            slices_by_report.append({})
            continue
        if (type(item_count) is not int or item_count <= 0 or not seeds
                or any(type(seed) is not int for seed in seeds) or len(seeds) != len(set(seeds))):
            problems.append(f"{name}: invalid manifest item count or seeds")
        elif len(rows) != item_count * len(seeds):
            problems.append(f"{name}: row count does not match manifest")
        if report.get("evaluator_failures") != []:
            problems.append(f"{name}: evaluator failures or missing evaluator_failures")
        for metric, value in metrics.items():
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                problems.append(f"{name}: metric {metric} is not a finite number")
        for metric in spec["metrics"]:
            value = metrics.get(metric["id"])
            if metric.get("blocking") and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                problems.append(f"{name}: blocking metric {metric['id']} missing or invalid")

        keys = set()
        item_slices = {}
        valid_rows = True
        for row in rows:
            if not isinstance(row, dict):
                problems.append(f"{name}: invalid row")
                valid_rows = False
                continue
            item, seed, slices = row.get("item_id"), row.get("seed"), row.get("slices", [])
            if not isinstance(item, str) or not item or type(seed) is not int:
                problems.append(f"{name}: invalid item or seed")
                valid_rows = False
                continue
            key = (item, seed)
            if key in keys:
                problems.append(f"{name}: duplicate row {key}")
            keys.add(key)
            if not isinstance(slices, list) or any(not isinstance(tag, str) for tag in slices):
                problems.append(f"{name}: invalid slices for {item}")
                valid_rows = False
                continue
            tags = frozenset(slices)
            if item in item_slices and item_slices[item] != tags:
                problems.append(f"{name}: inconsistent slice tags for {item}")
            item_slices[item] = tags
            for metric in graded:
                if type(row.get(metric)) is not bool:
                    problems.append(f"{name}: {key} has missing or invalid {metric}")
                    valid_rows = False
        if type(item_count) is int and isinstance(seeds, list) and all(type(s) is int for s in seeds):
            expected_keys = {(item, seed) for item in item_slices for seed in seeds}
            if len(item_slices) != item_count or keys != expected_keys:
                problems.append(f"{name}: rows do not cover every item and manifest seed")
        keys_by_report.append(keys)
        slices_by_report.append(item_slices)

        # A report's summary must describe its own row-level evidence.
        if valid_rows and rows:
            for metric in graded:
                values = [row[metric] for row in rows]
                expected = sum(values) if metric in ("secret_leak", "approval_bypass") else round(sum(values) / len(values), 4)
                actual = metrics.get(metric)
                if not isinstance(actual, (int, float)) or not math.isfinite(actual) or abs(actual - expected) > 1e-9:
                    problems.append(f"{name}: metric {metric} disagrees with rows")
            if all(type(row.get("pass_rate")) is bool and isinstance(row.get("cost"), (int, float))
                   and math.isfinite(row["cost"]) for row in rows):
                recalculated = aggregate(rows, graded, k_values=spec.get("pass_k", []))
                for metric in ("pass_5", "cost_per_success", *(
                        f"{kind}_{k}" for k in spec.get("pass_k", []) for kind in ("pass_at", "pass_hat"))):
                    if metric in metrics and metrics[metric] != recalculated.get(metric):
                        problems.append(f"{name}: metric {metric} disagrees with rows")

    if keys_by_report[0] != keys_by_report[1]:
        problems.append("PR and baseline have different (item, seed) pairs")
    if slices_by_report[0] != slices_by_report[1]:
        problems.append("PR and baseline have different item slice tags")
    if base_spec is not None:
        if (pr.get("manifest", {}).get("eval_set_sha") == base.get("manifest", {}).get("eval_set_sha")
                and spec.get("eval_set_version") != base_spec.get("eval_set_version")):
            problems.append("eval-set version changed without changing the eval-set SHA")
        problems.extend(_ratchet_check(spec, base_spec))
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for entry in spec.get("slices", []):
        name, metric = entry["name"], entry["metric"]
        identifier = f"slice:{name}/{metric}"
        values, baseline = per_item(pr, metric, name), per_item(base, metric, name)
        verdict, note = "ok", ""
        if not values or set(values) != set(baseline):
            verdict, value = "missing", None
        else:
            value = sum(values.values()) / len(values)
            if "min" in entry and value < entry["min"]:
                verdict = "fail"
            if entry.get("no_significant_drop"):
                keys = sorted(values)
                if len(keys) == 1:
                    d = values[keys[0]] - baseline[keys[0]]
                    lo = hi = d
                else:
                    d, lo, hi = stats.paired_bootstrap(
                        [values[k] for k in keys], [baseline[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                        confidence=bs.get("confidence", 0.95),
                    )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and entry.get("blocking"):
            blocked.append(identifier)
        label = "ok" if verdict == "ok" else ("BLOCK" if entry.get("blocking") else "warn")
        lines.append(f"  {identifier:<32} {value!s:<8} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    pr_sha = pr.get("manifest", {}).get("eval_set_sha")
    base_sha = base.get("manifest", {}).get("eval_set_sha")
    if not isinstance(pr_sha, str) or not pr_sha or pr_sha != base_sha:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
