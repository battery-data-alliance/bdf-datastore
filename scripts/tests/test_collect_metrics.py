"""Tests for scripts/collect_metrics.py."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from collect_metrics import (
    MetricsReport,
    collect_cell_counts,
    compute_consistency_score,
    run_with_timing,
    build_metrics_report,
    format_job_summary,
    check_alert_thresholds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_repo(
    base: Path,
    contributors: dict[str, list[str]] | None = None,
    *,
    battery_json_spec: dict | None = None,
    skip_battery_json: set[tuple[str, str]] | None = None,
) -> Path:
    """Build a minimal fake repo for testing."""
    if contributors is None:
        contributors = {"SINTEF": ["cell-a", "cell-b"], "Microsoft": ["cell-c"]}
    if battery_json_spec is None:
        battery_json_spec = {
            "manufacturer": "acme",
            "model": "x100",
            "batch": "2024",
            "chemistry": "li-ion",
            "form_factor": "pouch",
            "nominal_voltage_v": 3.7,
            "rated_capacity_ah": 2.0,
            "rated_energy_wh": 7.4,
        }
    if skip_battery_json is None:
        skip_battery_json = set()

    for contributor, cells in contributors.items():
        for cell in cells:
            cell_dir = base / contributor / cell
            cell_dir.mkdir(parents=True, exist_ok=True)
            if (contributor, cell) not in skip_battery_json:
                battery_data = {"spec": battery_json_spec}
                (cell_dir / "battery.json").write_text(json.dumps(battery_data))
    return base


# ---------------------------------------------------------------------------
# collect_cell_counts
# ---------------------------------------------------------------------------


def test_collect_cell_counts_basic(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"], "Microsoft": ["c"]})
    counts = collect_cell_counts(tmp_path)
    assert counts["total"] == 3
    assert counts["by_contributor"]["SINTEF"] == 2
    assert counts["by_contributor"]["Microsoft"] == 1


def test_collect_cell_counts_ignores_non_contributor_dirs(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a"]})
    # scripts and .github should be ignored
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".github").mkdir()
    counts = collect_cell_counts(tmp_path)
    assert counts["total"] == 1


def test_collect_cell_counts_battery_json_coverage(tmp_path):
    make_repo(
        tmp_path,
        {"SINTEF": ["a", "b", "c"]},
        skip_battery_json={("SINTEF", "b")},
    )
    counts = collect_cell_counts(tmp_path)
    assert counts["total"] == 3
    assert counts["with_battery_json"] == 2
    assert counts["battery_json_coverage"] == pytest.approx(2 / 3)


def test_collect_cell_counts_all_have_battery_json(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]})
    counts = collect_cell_counts(tmp_path)
    assert counts["battery_json_coverage"] == 1.0


# ---------------------------------------------------------------------------
# compute_consistency_score
# ---------------------------------------------------------------------------


def test_consistency_score_no_errors(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]})
    score = compute_consistency_score(tmp_path)
    assert score == 1.0


def test_consistency_score_with_errors(tmp_path):
    # 3 cells, one has a bad battery.json (will fail structure check)
    make_repo(tmp_path, {"SINTEF": ["a", "b", "c"]})
    # Corrupt one battery.json
    (tmp_path / "SINTEF" / "b" / "battery.json").write_text("not json{{{")
    score = compute_consistency_score(tmp_path)
    # 1 of 3 cells has errors → score < 1.0
    assert score < 1.0


def test_consistency_score_returns_float(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a"]})
    score = compute_consistency_score(tmp_path)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# run_with_timing
# ---------------------------------------------------------------------------


def test_run_with_timing_returns_result_and_duration():
    result, duration = run_with_timing(lambda: 42)
    assert result == 42
    assert duration >= 0.0


def test_run_with_timing_measures_time():
    def slow():
        time.sleep(0.05)
        return "done"

    _, duration = run_with_timing(slow)
    assert duration >= 0.04


def test_run_with_timing_propagates_exceptions():
    with pytest.raises(ValueError, match="boom"):
        run_with_timing(lambda: (_ for _ in ()).throw(ValueError("boom")))


# ---------------------------------------------------------------------------
# build_metrics_report
# ---------------------------------------------------------------------------


def test_build_metrics_report_structure(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]})
    report = build_metrics_report(tmp_path)

    assert isinstance(report, MetricsReport)
    assert report.timestamp  # non-empty ISO string
    assert report.cell_counts["total"] == 2
    assert 0.0 <= report.consistency_score <= 1.0
    assert report.structure_errors >= 0
    assert report.structure_warnings >= 0
    assert report.quality_errors >= 0
    assert report.quality_warnings >= 0
    assert report.runtime_total_seconds >= 0
    assert report.runtime_structure_seconds >= 0
    assert report.runtime_quality_seconds >= 0


def test_build_metrics_report_clean_repo(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"], "Microsoft": ["c"]})
    report = build_metrics_report(tmp_path)

    assert report.structure_errors == 0
    assert report.quality_errors == 0
    assert report.consistency_score == 1.0
    assert report.cell_counts["total"] == 3


def test_build_metrics_report_detects_errors(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]}, skip_battery_json={("SINTEF", "a")})
    report = build_metrics_report(tmp_path)
    assert report.structure_errors > 0
    assert report.consistency_score < 1.0


def test_build_metrics_report_serializable(tmp_path):
    make_repo(tmp_path)
    report = build_metrics_report(tmp_path)
    data = report.to_dict()
    # Must be JSON-serializable
    serialized = json.dumps(data)
    parsed = json.loads(serialized)
    assert parsed["cell_counts"]["total"] == data["cell_counts"]["total"]


# ---------------------------------------------------------------------------
# format_job_summary
# ---------------------------------------------------------------------------


def test_format_job_summary_contains_key_fields(tmp_path):
    make_repo(tmp_path)
    report = build_metrics_report(tmp_path)
    summary = format_job_summary(report)

    assert "consistency_score" in summary.lower() or "consistency" in summary.lower()
    assert str(report.cell_counts["total"]) in summary


def test_format_job_summary_returns_markdown(tmp_path):
    make_repo(tmp_path)
    report = build_metrics_report(tmp_path)
    summary = format_job_summary(report)
    # Should have markdown headers or table syntax
    assert "#" in summary or "|" in summary


def test_format_job_summary_flags_errors(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a"]}, skip_battery_json={("SINTEF", "a")})
    report = build_metrics_report(tmp_path)
    summary = format_job_summary(report)
    assert "error" in summary.lower() or "fail" in summary.lower()


# ---------------------------------------------------------------------------
# check_alert_thresholds
# ---------------------------------------------------------------------------


def test_no_alerts_for_clean_repo(tmp_path):
    make_repo(tmp_path)
    report = build_metrics_report(tmp_path)
    alerts = check_alert_thresholds(report)
    assert alerts == []


def test_alert_on_structure_errors(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a"]}, skip_battery_json={("SINTEF", "a")})
    report = build_metrics_report(tmp_path)
    alerts = check_alert_thresholds(report)
    assert any("structure" in a.lower() or "battery.json" in a.lower() for a in alerts)


def test_alert_on_quality_errors(tmp_path):
    # Create a cell with an invalid voltage to trigger quality error
    cell_dir = tmp_path / "SINTEF" / "bad-cell"
    cell_dir.mkdir(parents=True)
    bad_spec = {
        "manufacturer": "x",
        "model": "y",
        "batch": "z",
        "nominal_voltage_v": 99.9,  # way out of range
    }
    (cell_dir / "battery.json").write_text(json.dumps({"spec": bad_spec}))
    report = build_metrics_report(tmp_path)
    alerts = check_alert_thresholds(report)
    assert any("quality" in a.lower() or "error" in a.lower() for a in alerts)


def test_alert_on_low_consistency_score(tmp_path):
    # 2 cells, 2 missing battery.json → consistency score 0
    make_repo(
        tmp_path,
        {"SINTEF": ["a", "b"]},
        skip_battery_json={("SINTEF", "a"), ("SINTEF", "b")},
    )
    report = build_metrics_report(tmp_path)
    alerts = check_alert_thresholds(report)
    # Should alert since consistency < 100%
    assert len(alerts) > 0


def test_check_alert_thresholds_returns_list():
    """check_alert_thresholds always returns a list, never raises."""
    from collect_metrics import MetricsReport
    import datetime

    report = MetricsReport(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        cell_counts={"total": 0, "by_contributor": {}, "with_battery_json": 0, "battery_json_coverage": 1.0},
        consistency_score=1.0,
        structure_errors=0,
        structure_warnings=0,
        quality_errors=0,
        quality_warnings=0,
        runtime_total_seconds=0.1,
        runtime_structure_seconds=0.05,
        runtime_quality_seconds=0.05,
    )
    result = check_alert_thresholds(report)
    assert isinstance(result, list)
