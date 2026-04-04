"""Tests for scripts/validate_structure.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Allow importing from the scripts directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_structure import check_cell, validate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cell(
    base: Path,
    contributor: str = "contrib",
    cell: str = "cell-001",
    *,
    battery_json: dict | None = None,
    battery_json_raw: str | None = None,
    raw_files: int = 0,
    processed_files: int = 0,
    data_type: str = "timeseries",
) -> Path:
    """Create a minimal cell directory tree under *base*."""
    cell_dir = base / contributor / cell
    ts = cell_dir / data_type

    if battery_json is not None:
        (cell_dir).mkdir(parents=True, exist_ok=True)
        (cell_dir / "battery.json").write_text(json.dumps(battery_json))
    elif battery_json_raw is not None:
        (cell_dir).mkdir(parents=True, exist_ok=True)
        (cell_dir / "battery.json").write_text(battery_json_raw)
    else:
        cell_dir.mkdir(parents=True, exist_ok=True)

    if raw_files > 0:
        (ts / "raw").mkdir(parents=True, exist_ok=True)
        for i in range(raw_files):
            (ts / "raw" / f"test_{i}.csv").write_text("data")

    if processed_files > 0:
        (ts / "processed").mkdir(parents=True, exist_ok=True)
        for i in range(processed_files):
            (ts / "processed" / f"test_{i}.bdf.csv").write_text("data")

    return cell_dir


# ---------------------------------------------------------------------------
# check_cell
# ---------------------------------------------------------------------------

class TestCheckCell:
    def test_missing_battery_json(self, tmp_path):
        cell_dir = tmp_path / "contrib" / "cell-001"
        cell_dir.mkdir(parents=True)
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert any("Missing battery.json" in e for e in errors)

    def test_valid_battery_json_with_spec(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json={"spec": {"capacity_Ah": 2.5}})
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert not errors
        assert not warnings

    def test_battery_json_missing_spec_key(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json={"chemistry": "NMC"})
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert not errors
        assert any("missing 'spec' key" in w for w in warnings)

    def test_invalid_json_in_battery_json(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json_raw="{invalid json}")
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert any("Invalid JSON" in e for e in errors)

    def test_raw_processed_count_match(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json={"spec": {}}, raw_files=3, processed_files=3)
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert not errors

    def test_raw_processed_count_mismatch(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json={"spec": {}}, raw_files=3, processed_files=2)
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert any("mismatch" in e for e in errors)

    def test_no_raw_or_processed_warns(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json={"spec": {}})
        # Create a timeseries dir with no raw/ or processed/ subdirs
        (cell_dir / "timeseries").mkdir(parents=True, exist_ok=True)
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert any("No raw/ or processed/" in w for w in warnings)

    def test_unknown_data_type_dir_ignored(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json={"spec": {}})
        # Create a dir that's not in DATA_TYPES
        (cell_dir / "metadata").mkdir()
        errors, warnings = [], []
        check_cell(cell_dir, errors, warnings)
        assert not errors
        assert not warnings


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_no_contributor_dirs(self, tmp_path):
        errors, warnings = validate(tmp_path)
        assert any("No contributor directories" in e for e in errors)

    def test_contributor_with_no_cells_warns(self, tmp_path):
        (tmp_path / "contrib").mkdir()
        errors, warnings = validate(tmp_path)
        assert not errors
        assert any("no cells" in w for w in warnings)

    def test_valid_single_cell(self, tmp_path):
        make_cell(tmp_path, battery_json={"spec": {}}, raw_files=1, processed_files=1)
        errors, warnings = validate(tmp_path)
        assert not errors

    def test_scripts_dir_excluded(self, tmp_path):
        # scripts/ should not be treated as a contributor
        (tmp_path / "scripts").mkdir()
        make_cell(tmp_path, battery_json={"spec": {}}, raw_files=1, processed_files=1)
        errors, warnings = validate(tmp_path)
        assert not errors

    def test_github_dir_excluded(self, tmp_path):
        (tmp_path / ".github").mkdir()
        make_cell(tmp_path, battery_json={"spec": {}}, raw_files=1, processed_files=1)
        errors, warnings = validate(tmp_path)
        assert not errors

    def test_multiple_contributors_multiple_cells(self, tmp_path):
        make_cell(tmp_path, contributor="SINTEF", cell="cell-A", battery_json={"spec": {}}, raw_files=2, processed_files=2)
        make_cell(tmp_path, contributor="Microsoft", cell="cell-B", battery_json={"spec": {}}, raw_files=1, processed_files=1)
        errors, warnings = validate(tmp_path)
        assert not errors

    def test_eis_data_type_checked(self, tmp_path):
        cell_dir = make_cell(tmp_path, battery_json={"spec": {}}, data_type="eis", raw_files=2, processed_files=1)
        errors, warnings = validate(tmp_path)
        assert any("mismatch" in e for e in errors)
