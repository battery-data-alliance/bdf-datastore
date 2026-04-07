"""Integration tests verifying all 9 Microsoft cells have valid battery.json files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MICROSOFT_DIR = REPO_ROOT / "Microsoft"

MICROSOFT_CELLS = [
    "manufacturer1-endt44198-2024",
    "manufacturer1-midt44198-2024",
    "manufacturer1-mult44198-2024",
    "manufacturer2-endt455110-2024",
    "manufacturer2-midt455110-2024",
    "manufacturer2-mult455110-2024",
    "manufacturer3-endt460100-2024",
    "manufacturer3-midt460100-2024",
    "manufacturer3-mult460100-2024",
]

REQUIRED_SPEC_FIELDS = [
    "manufacturer",
    "model",
    "batch",
    "chemistry",
    "form_factor",
    "nominal_voltage_v",
    "rated_capacity_ah",
    "rated_energy_wh",
]


@pytest.mark.parametrize("cell_name", MICROSOFT_CELLS)
class TestMicrosoftBatteryJson:
    def test_battery_json_exists(self, cell_name):
        path = MICROSOFT_DIR / cell_name / "battery.json"
        assert path.exists(), f"Missing battery.json for {cell_name}"

    def test_battery_json_valid(self, cell_name):
        path = MICROSOFT_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        assert "spec" in data, f"battery.json missing 'spec' key for {cell_name}"

    def test_spec_has_required_fields(self, cell_name):
        path = MICROSOFT_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        spec = data["spec"]
        for field in REQUIRED_SPEC_FIELDS:
            assert field in spec, f"spec missing '{field}' for {cell_name}"

    def test_nominal_voltage_positive(self, cell_name):
        path = MICROSOFT_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        assert data["spec"]["nominal_voltage_v"] > 0

    def test_rated_capacity_positive(self, cell_name):
        path = MICROSOFT_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        assert data["spec"]["rated_capacity_ah"] > 0

    def test_ids_list_not_empty(self, cell_name):
        path = MICROSOFT_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        assert "ids" in data, f"battery.json missing 'ids' for {cell_name}"
        assert len(data["ids"]) > 0, f"ids list is empty for {cell_name}"
