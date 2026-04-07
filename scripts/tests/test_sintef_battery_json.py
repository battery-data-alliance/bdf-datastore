"""Integration tests verifying all 19 SINTEF cells have valid battery.json files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SINTEF_DIR = REPO_ROOT / "SINTEF"

SINTEF_CELLS = [
    "energizer-cr2032-202602-dtjrga",
    "energizer-cr2032-202602-wg2h62",
    "google-g20m7-202512-5y1vrv",
    "google-g20m7-202512-cc6w49",
    "hina-nacr32140-mp10-2024-60adsr",
    "hina-nacr32140-mp10-2024-9sg4mz",
    "hina-nacr32140-mp10-2024-d9j8am",
    "hina-nacr32140-mp10-2024-vkpy9r",
    "hina-nacr32140-mp10-2024-vxw05v",
    "hina-nacr32140-mp10-2024-w8hzf9",
    "hina-nacr32140-mp10-2024-wsafar",
    "hina-nacr32140-mp10-2024-y31f2f",
    "melasta-slpba842124hv-202409-5ph3ta",
    "melasta-slpba842124hv-202409-bntnt5",
    "melasta-slpba842124hv-202409-cssch8",
    "melasta-slpba842124hv-202409-dys99s",
    "melasta-slpba842124hv-202409-g8tzp0",
    "melasta-slpba842124hv-202409-hybqmv",
    "melasta-slpba842124hv-202409-r4a3f6",
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


@pytest.mark.parametrize("cell_name", SINTEF_CELLS)
class TestSINTEFBatteryJson:
    def test_battery_json_exists(self, cell_name):
        path = SINTEF_DIR / cell_name / "battery.json"
        assert path.exists(), f"Missing battery.json for {cell_name}"

    def test_battery_json_valid(self, cell_name):
        path = SINTEF_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        assert "spec" in data, f"battery.json missing 'spec' key for {cell_name}"

    def test_spec_has_required_fields(self, cell_name):
        path = SINTEF_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        spec = data["spec"]
        for field in REQUIRED_SPEC_FIELDS:
            assert field in spec, f"spec missing '{field}' for {cell_name}"

    def test_cell_id_in_ids(self, cell_name):
        path = SINTEF_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        cell_id = cell_name.rsplit("-", 1)[-1]
        assert "ids" in data, f"battery.json missing 'ids' for {cell_name}"
        assert cell_id in data["ids"], (
            f"Cell ID '{cell_id}' not found in ids for {cell_name}"
        )

    def test_nominal_voltage_positive(self, cell_name):
        path = SINTEF_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        assert data["spec"]["nominal_voltage_v"] > 0

    def test_rated_capacity_positive(self, cell_name):
        path = SINTEF_DIR / cell_name / "battery.json"
        with path.open() as f:
            data = json.load(f)
        assert data["spec"]["rated_capacity_ah"] > 0
