"""Tests for scripts/validate_quality.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_quality import (
    check_cross_cell_consistency,
    check_spec_values,
    check_timeseries_metadata,
    validate_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SPEC = {
    "manufacturer": "acme",
    "model": "x100",
    "batch": "2024",
    "chemistry": "li-ion",
    "form_factor": "pouch",
    "nominal_voltage_v": 3.7,
    "rated_capacity_ah": 2.0,
    "rated_energy_wh": 7.4,
}


def make_cell(
    base: Path,
    contributor: str = "SINTEF",
    cell: str = "acme-x100-2024-aaaaaa",
    *,
    spec: dict | None = None,
    timeseries_json: list[dict] | None = None,
) -> Path:
    """Create a minimal cell directory for quality tests."""
    cell_dir = base / contributor / cell
    cell_dir.mkdir(parents=True, exist_ok=True)
    if spec is not None:
        battery = {"spec": spec, "ids": [cell.rsplit("-", 1)[-1]]}
        (cell_dir / "battery.json").write_text(json.dumps(battery))
    if timeseries_json is not None:
        ts_dir = cell_dir / "timeseries"
        ts_dir.mkdir(exist_ok=True)
        for i, data in enumerate(timeseries_json):
            (ts_dir / f"test_{i}.json").write_text(json.dumps(data))
    return cell_dir


# ---------------------------------------------------------------------------
# check_spec_values
# ---------------------------------------------------------------------------

class TestCheckSpecValues:
    def test_valid_spec_no_issues(self):
        errors, warnings = [], []
        check_spec_values("test/cell", VALID_SPEC.copy(), errors, warnings)
        assert not errors
        assert not warnings

    def test_voltage_too_low(self):
        spec = {**VALID_SPEC, "nominal_voltage_v": 0.1}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert any("nominal_voltage_v" in e and "out of range" in e for e in errors)

    def test_voltage_too_high(self):
        spec = {**VALID_SPEC, "nominal_voltage_v": 6.0}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert any("nominal_voltage_v" in e and "out of range" in e for e in errors)

    def test_voltage_at_min_boundary_valid(self):
        spec = {**VALID_SPEC, "nominal_voltage_v": 0.5, "rated_energy_wh": 1.0}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert not any("nominal_voltage_v" in e and "out of range" in e for e in errors)

    def test_voltage_at_max_boundary_valid(self):
        spec = {**VALID_SPEC, "nominal_voltage_v": 5.0, "rated_energy_wh": 10.0}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert not any("nominal_voltage_v" in e and "out of range" in e for e in errors)

    def test_energy_inconsistency_error(self):
        # 3.7V * 2.0Ah = 7.4 Wh, but we set 10.0 (35% error)
        spec = {**VALID_SPEC, "rated_energy_wh": 10.0}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert any("inconsistent" in e for e in errors)

    def test_energy_within_tolerance_no_error(self):
        # 3.7 * 2.0 = 7.4, set 7.5 (1.3% error, within 10% tolerance)
        spec = {**VALID_SPEC, "rated_energy_wh": 7.5}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert not any("inconsistent" in e for e in errors)

    def test_unknown_chemistry_warns(self):
        spec = {**VALID_SPEC, "chemistry": "unobtainium"}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert any("chemistry" in w for w in warnings)

    def test_known_chemistry_no_warning(self):
        for chemistry in ("li-ion", "na-ion", "primary-lithium"):
            errors, warnings = [], []
            check_spec_values("test/cell", {**VALID_SPEC, "chemistry": chemistry}, errors, warnings)
            assert not any("chemistry" in w for w in warnings), f"unexpected warning for {chemistry}"

    def test_unknown_form_factor_warns(self):
        spec = {**VALID_SPEC, "form_factor": "torus"}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert any("form_factor" in w for w in warnings)

    def test_known_form_factor_no_warning(self):
        for form_factor in ("coin", "pouch", "cylindrical", "prismatic"):
            errors, warnings = [], []
            check_spec_values("test/cell", {**VALID_SPEC, "form_factor": form_factor}, errors, warnings)
            assert not any("form_factor" in w for w in warnings), f"unexpected warning for {form_factor}"

    def test_missing_voltage_skips_range_check(self):
        spec = {k: v for k, v in VALID_SPEC.items() if k != "nominal_voltage_v"}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert not any("nominal_voltage_v" in e for e in errors)

    def test_missing_energy_skips_consistency_check(self):
        spec = {k: v for k, v in VALID_SPEC.items() if k != "rated_energy_wh"}
        errors, warnings = [], []
        check_spec_values("test/cell", spec, errors, warnings)
        assert not any("inconsistent" in e for e in errors)


# ---------------------------------------------------------------------------
# check_timeseries_metadata
# ---------------------------------------------------------------------------

class TestCheckTimeseriesMetadata:
    def test_valid_battery_test_json(self, tmp_path):
        cell_dir = make_cell(tmp_path, timeseries_json=[
            {"@type": "BatteryTest", "name": "test-1"}
        ])
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert not errors
        assert not warnings

    def test_multiple_valid_files(self, tmp_path):
        cell_dir = make_cell(tmp_path, timeseries_json=[
            {"@type": "BatteryTest", "name": "test-1"},
            {"@type": "BatteryTest", "name": "test-2"},
        ])
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert not errors

    def test_missing_type_field(self, tmp_path):
        cell_dir = make_cell(tmp_path, timeseries_json=[{"name": "test-1"}])
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert any("@type" in e and "BatteryTest" in e for e in errors)

    def test_wrong_type_value(self, tmp_path):
        cell_dir = make_cell(tmp_path, timeseries_json=[{"@type": "Dataset", "name": "test-1"}])
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert any("@type" in e and "BatteryTest" in e for e in errors)

    def test_missing_name_field(self, tmp_path):
        cell_dir = make_cell(tmp_path, timeseries_json=[{"@type": "BatteryTest"}])
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert any("name" in e for e in errors)

    def test_invalid_json_in_metadata(self, tmp_path):
        cell_dir = make_cell(tmp_path)
        ts_dir = cell_dir / "timeseries"
        ts_dir.mkdir(exist_ok=True)
        (ts_dir / "test_bad.json").write_text("{bad json")
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert any("Invalid JSON" in e for e in errors)

    def test_no_timeseries_dir_no_issues(self, tmp_path):
        cell_dir = make_cell(tmp_path)
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert not errors
        assert not warnings

    def test_eis_metadata_also_validated(self, tmp_path):
        cell_dir = make_cell(tmp_path)
        eis_dir = cell_dir / "eis"
        eis_dir.mkdir()
        (eis_dir / "test_eis.json").write_text(json.dumps({"name": "eis-1"}))  # missing @type
        errors, warnings = [], []
        check_timeseries_metadata(cell_dir, errors, warnings)
        assert any("@type" in e and "BatteryTest" in e for e in errors)


# ---------------------------------------------------------------------------
# check_cross_cell_consistency
# ---------------------------------------------------------------------------

class TestCheckCrossCellConsistency:
    def test_single_cell_no_issues(self, tmp_path):
        make_cell(tmp_path, spec=VALID_SPEC.copy())
        errors, warnings = [], []
        check_cross_cell_consistency(tmp_path / "SINTEF", errors, warnings)
        assert not errors

    def test_matching_specs_no_issues(self, tmp_path):
        make_cell(tmp_path, cell="acme-x100-2024-aaaaaa", spec=VALID_SPEC.copy())
        make_cell(tmp_path, cell="acme-x100-2024-bbbbbb", spec=VALID_SPEC.copy())
        errors, warnings = [], []
        check_cross_cell_consistency(tmp_path / "SINTEF", errors, warnings)
        assert not errors

    def test_mismatched_specs_error(self, tmp_path):
        make_cell(tmp_path, cell="acme-x100-2024-aaaaaa", spec=VALID_SPEC.copy())
        mismatched = {**VALID_SPEC, "nominal_voltage_v": 3.9}
        make_cell(tmp_path, cell="acme-x100-2024-bbbbbb", spec=mismatched)
        errors, warnings = [], []
        check_cross_cell_consistency(tmp_path / "SINTEF", errors, warnings)
        assert any("mismatch" in e.lower() for e in errors)
        assert any("nominal_voltage_v" in e for e in errors)

    def test_different_models_not_compared(self, tmp_path):
        make_cell(tmp_path, cell="acme-x100-2024-aaaaaa", spec=VALID_SPEC.copy())
        other_spec = {**VALID_SPEC, "model": "x200", "nominal_voltage_v": 3.9}
        make_cell(tmp_path, cell="acme-x200-2024-bbbbbb", spec=other_spec)
        errors, warnings = [], []
        check_cross_cell_consistency(tmp_path / "SINTEF", errors, warnings)
        assert not errors

    def test_different_batches_not_compared(self, tmp_path):
        make_cell(tmp_path, cell="acme-x100-2024-aaaaaa", spec=VALID_SPEC.copy())
        other_batch_spec = {**VALID_SPEC, "batch": "2025", "nominal_voltage_v": 3.9}
        make_cell(tmp_path, cell="acme-x100-2025-bbbbbb", spec=other_batch_spec)
        errors, warnings = [], []
        check_cross_cell_consistency(tmp_path / "SINTEF", errors, warnings)
        assert not errors

    def test_missing_battery_json_skipped(self, tmp_path):
        # One cell with no battery.json — should not crash
        cell_dir = tmp_path / "SINTEF" / "acme-x100-2024-cccccc"
        cell_dir.mkdir(parents=True)
        make_cell(tmp_path, cell="acme-x100-2024-aaaaaa", spec=VALID_SPEC.copy())
        errors, warnings = [], []
        check_cross_cell_consistency(tmp_path / "SINTEF", errors, warnings)
        assert not errors


# ---------------------------------------------------------------------------
# validate_quality (end-to-end)
# ---------------------------------------------------------------------------

class TestValidateQuality:
    def test_no_contributor_dirs_no_issues(self, tmp_path):
        errors, warnings = validate_quality(tmp_path)
        assert not errors
        assert not warnings

    def test_valid_cell_no_issues(self, tmp_path):
        make_cell(tmp_path, spec=VALID_SPEC.copy())
        errors, warnings = validate_quality(tmp_path)
        assert not errors

    def test_scripts_dir_excluded(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        make_cell(tmp_path, spec=VALID_SPEC.copy())
        errors, warnings = validate_quality(tmp_path)
        assert not errors

    def test_github_dir_excluded(self, tmp_path):
        (tmp_path / ".github").mkdir()
        make_cell(tmp_path, spec=VALID_SPEC.copy())
        errors, warnings = validate_quality(tmp_path)
        assert not errors

    def test_detects_voltage_out_of_range(self, tmp_path):
        make_cell(tmp_path, spec={**VALID_SPEC, "nominal_voltage_v": 0.1})
        errors, warnings = validate_quality(tmp_path)
        assert any("nominal_voltage_v" in e for e in errors)

    def test_detects_energy_inconsistency(self, tmp_path):
        make_cell(tmp_path, spec={**VALID_SPEC, "rated_energy_wh": 20.0})
        errors, warnings = validate_quality(tmp_path)
        assert any("inconsistent" in e for e in errors)

    def test_detects_timeseries_metadata_issue(self, tmp_path):
        make_cell(tmp_path, spec=VALID_SPEC.copy(), timeseries_json=[{"name": "bad"}])
        errors, warnings = validate_quality(tmp_path)
        assert any("@type" in e for e in errors)

    def test_detects_cross_cell_mismatch(self, tmp_path):
        make_cell(tmp_path, cell="acme-x100-2024-aaaaaa", spec=VALID_SPEC.copy())
        make_cell(tmp_path, cell="acme-x100-2024-bbbbbb", spec={**VALID_SPEC, "nominal_voltage_v": 4.2})
        errors, warnings = validate_quality(tmp_path)
        assert any("mismatch" in e.lower() for e in errors)
