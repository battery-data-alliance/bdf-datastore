"""Collect CI validation metrics for bdf-datastore.

Runs structure and quality validation, times them, and produces:
- A structured JSON metrics report
- A GitHub Actions job summary (when GITHUB_STEP_SUMMARY is set)
- Alert messages for threshold violations (exits non-zero if any alerts)

Usage:
    python scripts/collect_metrics.py [repo-root] [--json-output FILE]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, TypeVar

# Allow importing sibling scripts when run directly
sys.path.insert(0, str(Path(__file__).parent))

from validate_structure import validate as validate_structure
from validate_quality import validate_quality

T = TypeVar("T")

NON_CONTRIBUTOR_DIRS = {"scripts", ".github"}

# Alert thresholds
MAX_STRUCTURE_ERRORS = 0
MAX_QUALITY_ERRORS = 0
MIN_CONSISTENCY_SCORE = 1.0  # 100% — every cell must pass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class MetricsReport:
    timestamp: str
    cell_counts: dict[str, Any]
    consistency_score: float
    structure_errors: int
    structure_warnings: int
    quality_errors: int
    quality_warnings: int
    runtime_total_seconds: float
    runtime_structure_seconds: float
    runtime_quality_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def run_with_timing(fn: Callable[[], T]) -> tuple[T, float]:
    """Run *fn* and return (result, elapsed_seconds)."""
    start = time.monotonic()
    result = fn()
    elapsed = time.monotonic() - start
    return result, elapsed


def collect_cell_counts(root: Path) -> dict[str, Any]:
    """Count cells and battery.json coverage across all contributors."""
    total = 0
    with_battery_json = 0
    by_contributor: dict[str, int] = {}

    contributor_dirs = [
        p for p in sorted(root.iterdir())
        if p.is_dir() and not p.name.startswith(".") and p.name not in NON_CONTRIBUTOR_DIRS
    ]

    for contrib_dir in contributor_dirs:
        cell_dirs = [p for p in sorted(contrib_dir.iterdir()) if p.is_dir()]
        count = len(cell_dirs)
        by_contributor[contrib_dir.name] = count
        total += count
        for cell_dir in cell_dirs:
            if (cell_dir / "battery.json").exists():
                with_battery_json += 1

    coverage = with_battery_json / total if total > 0 else 1.0
    return {
        "total": total,
        "by_contributor": by_contributor,
        "with_battery_json": with_battery_json,
        "battery_json_coverage": coverage,
    }


def compute_consistency_score(root: Path) -> float:
    """Fraction of cells that pass both structure and quality validation.

    A cell has an error if it is mentioned in the error output of either
    validate_structure or validate_quality.  We approximate this by checking
    whether the total errors affect any individual cells: if there are N cells
    and E errors spread across M cells, we return (N - M) / N.

    In practice we use a simpler heuristic: any non-zero error count means at
    least one cell failed.  To produce a meaningful fractional score we count
    per-cell errors from the structure validator (which emits one error per
    failing cell).
    """
    counts = collect_cell_counts(root)
    total = counts["total"]
    if total == 0:
        return 1.0

    struct_errors, _ = validate_structure(root)
    qual_errors, _ = validate_quality(root)

    # Each error in structure validation maps to one cell (one error per cell).
    # Quality errors may be cross-cell; count unique cell paths mentioned.
    failing_cells: set[str] = set()

    for err in struct_errors:
        # Errors are formatted as "Missing battery.json: SINTEF/cell-a" etc.
        # Extract the first path-like token (contributor/cell prefix).
        parts = err.split()
        for part in parts:
            if "/" in part:
                cell_path = "/".join(part.split("/")[:2])
                failing_cells.add(cell_path)
                break
        else:
            # Couldn't identify the cell — count as one failing cell
            failing_cells.add(f"__unknown_struct_{len(failing_cells)}")

    for err in qual_errors:
        parts = err.split()
        for part in parts:
            if "/" in part:
                cell_path = "/".join(part.split("/")[:2])
                failing_cells.add(cell_path)
                break
        else:
            failing_cells.add(f"__unknown_qual_{len(failing_cells)}")

    passing = max(0, total - len(failing_cells))
    return passing / total


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_metrics_report(root: Path) -> MetricsReport:
    """Run all validations and assemble a MetricsReport."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    (struct_result, struct_time) = run_with_timing(lambda: validate_structure(root))
    struct_errors, struct_warnings = struct_result

    (qual_result, qual_time) = run_with_timing(lambda: validate_quality(root))
    qual_errors, qual_warnings = qual_result

    cell_counts = collect_cell_counts(root)
    consistency_score = compute_consistency_score(root)
    total_time = struct_time + qual_time

    return MetricsReport(
        timestamp=timestamp,
        cell_counts=cell_counts,
        consistency_score=consistency_score,
        structure_errors=len(struct_errors),
        structure_warnings=len(struct_warnings),
        quality_errors=len(qual_errors),
        quality_warnings=len(qual_warnings),
        runtime_total_seconds=round(total_time, 3),
        runtime_structure_seconds=round(struct_time, 3),
        runtime_quality_seconds=round(qual_time, 3),
    )


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def format_job_summary(report: MetricsReport) -> str:
    """Render a GitHub Actions job summary in Markdown."""
    score_pct = f"{report.consistency_score * 100:.1f}%"
    coverage_pct = f"{report.cell_counts['battery_json_coverage'] * 100:.1f}%"
    status = "PASS" if (report.structure_errors == 0 and report.quality_errors == 0) else "FAIL"
    status_icon = "" if status == "PASS" else ""

    by_contributor_rows = "\n".join(
        f"| {contrib} | {count} |"
        for contrib, count in sorted(report.cell_counts["by_contributor"].items())
    )

    lines = [
        f"## {status_icon} Data Quality Report — {status}",
        "",
        f"> Generated: {report.timestamp}",
        "",
        "### Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total cells | {report.cell_counts['total']} |",
        f"| `battery.json` coverage | {coverage_pct} |",
        f"| Consistency score | {score_pct} |",
        f"| Structure errors | {report.structure_errors} |",
        f"| Structure warnings | {report.structure_warnings} |",
        f"| Quality errors | {report.quality_errors} |",
        f"| Quality warnings | {report.quality_warnings} |",
        f"| Validation runtime | {report.runtime_total_seconds:.3f}s |",
        "",
        "### Cells by contributor",
        "",
        "| Contributor | Cells |",
        "|-------------|-------|",
        by_contributor_rows,
        "",
        "### Runtime breakdown",
        "",
        "| Phase | Seconds |",
        "|-------|---------|",
        f"| Structure validation | {report.runtime_structure_seconds:.3f}s |",
        f"| Quality validation | {report.runtime_quality_seconds:.3f}s |",
        f"| **Total** | **{report.runtime_total_seconds:.3f}s** |",
    ]
    return "\n".join(lines)


def check_alert_thresholds(report: MetricsReport) -> list[str]:
    """Return a list of alert messages for any threshold violations."""
    alerts: list[str] = []

    if report.structure_errors > MAX_STRUCTURE_ERRORS:
        alerts.append(
            f"ALERT: {report.structure_errors} structure error(s) detected "
            f"(threshold: {MAX_STRUCTURE_ERRORS}). "
            "Check battery.json files and raw/processed file parity."
        )

    if report.quality_errors > MAX_QUALITY_ERRORS:
        alerts.append(
            f"ALERT: {report.quality_errors} quality error(s) detected "
            f"(threshold: {MAX_QUALITY_ERRORS}). "
            "Check spec values and cross-cell consistency."
        )

    if report.consistency_score < MIN_CONSISTENCY_SCORE:
        score_pct = f"{report.consistency_score * 100:.1f}%"
        threshold_pct = f"{MIN_CONSISTENCY_SCORE * 100:.1f}%"
        alerts.append(
            f"ALERT: Consistency score {score_pct} is below threshold {threshold_pct}. "
            "One or more cells have validation errors."
        )

    return alerts


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect and report CI validation metrics for bdf-datastore."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--json-output",
        metavar="FILE",
        help="Write JSON metrics to FILE.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = build_metrics_report(root)

    # Write job summary if running in GitHub Actions
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(format_job_summary(report))
            f.write("\n")

    # Always print summary to stdout
    print(format_job_summary(report))

    # Write JSON metrics file if requested
    if args.json_output:
        with open(args.json_output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\nMetrics written to {args.json_output}", file=sys.stderr)

    # Check thresholds and emit alerts
    alerts = check_alert_thresholds(report)
    if alerts:
        print("\n--- ALERTS ---", file=sys.stderr)
        for alert in alerts:
            print(f"  {alert}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
