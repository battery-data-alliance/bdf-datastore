"""Validate data quality and cross-cell consistency for bdf-datastore.

Checks:
- battery.json spec values are within reasonable ranges
- Rated energy is internally consistent (Wh ≈ V × Ah, within 10%)
- Chemistry and form_factor use known values (warning for unknown)
- Cells sharing same manufacturer+model+batch have consistent spec values
- Timeseries metadata JSON files have required BatteryTest fields
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

KNOWN_CHEMISTRIES = {
    "li-ion", "na-ion", "primary-lithium", "lco", "lfp", "nmc", "nca",
    "lmfp", "lfmp", "nimh", "lead-acid", "flow",
}
KNOWN_FORM_FACTORS = {
    "coin", "button", "pouch", "cylindrical", "prismatic", "blade",
}

VOLTAGE_MIN = 0.5   # V
VOLTAGE_MAX = 5.0   # V
ENERGY_CONSISTENCY_TOLERANCE = 0.10  # 10%


def check_spec_values(cell_path: str, spec: dict, errors: list[str], warnings: list[str]) -> None:
    """Validate spec field values are within expected ranges."""
    voltage = spec.get("nominal_voltage_v")
    capacity = spec.get("rated_capacity_ah")
    energy = spec.get("rated_energy_wh")

    if voltage is not None:
        if not (VOLTAGE_MIN <= voltage <= VOLTAGE_MAX):
            errors.append(
                f"nominal_voltage_v={voltage} out of range "
                f"[{VOLTAGE_MIN}, {VOLTAGE_MAX}] in {cell_path}"
            )

    if voltage is not None and capacity is not None and energy is not None:
        expected_energy = voltage * capacity
        if expected_energy > 0:
            rel_error = abs(energy - expected_energy) / expected_energy
            if rel_error > ENERGY_CONSISTENCY_TOLERANCE:
                errors.append(
                    f"rated_energy_wh={energy} inconsistent with "
                    f"nominal_voltage_v={voltage} × rated_capacity_ah={capacity} "
                    f"= {expected_energy:.3f} (error={rel_error:.1%}) in {cell_path}"
                )

    chemistry = spec.get("chemistry")
    if chemistry is not None and chemistry not in KNOWN_CHEMISTRIES:
        warnings.append(f"Unknown chemistry '{chemistry}' in {cell_path}")

    form_factor = spec.get("form_factor")
    if form_factor is not None and form_factor not in KNOWN_FORM_FACTORS:
        warnings.append(f"Unknown form_factor '{form_factor}' in {cell_path}")


def check_timeseries_metadata(cell_dir: Path, errors: list[str], warnings: list[str]) -> None:
    """Validate timeseries/eis test metadata JSON files (test_*.json)."""
    root = cell_dir.parent.parent
    for data_type in ("timeseries", "eis"):
        data_dir = cell_dir / data_type
        if not data_dir.exists():
            continue
        for json_file in sorted(data_dir.glob("*.json")):
            rel = json_file.relative_to(root)
            try:
                with json_file.open() as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in {rel}: {e}")
                continue
            if data.get("@type") != "BatteryTest":
                errors.append(
                    f"Metadata file missing '@type': 'BatteryTest' in {rel}"
                )
            if "name" not in data:
                errors.append(f"Metadata file missing 'name' field in {rel}")


def check_cross_cell_consistency(
    contributor_dir: Path, errors: list[str], warnings: list[str]
) -> None:
    """Cells sharing manufacturer+model+batch must have identical spec values."""
    groups: dict[tuple[str, str, str], list[tuple[str, dict]]] = defaultdict(list)

    for cell_dir in sorted(contributor_dir.iterdir()):
        if not cell_dir.is_dir():
            continue
        battery_json = cell_dir / "battery.json"
        if not battery_json.exists():
            continue
        try:
            with battery_json.open() as f:
                data = json.load(f)
        except json.JSONDecodeError:
            continue  # already reported by validate_structure.py
        spec = data.get("spec")
        if not spec:
            continue
        manufacturer = spec.get("manufacturer")
        model = spec.get("model")
        batch = spec.get("batch")
        if None in (manufacturer, model, batch):
            continue
        key = (manufacturer, model, batch)
        groups[key].append((cell_dir.name, dict(spec)))

    for (manufacturer, model, batch), cells in groups.items():
        if len(cells) < 2:
            continue
        reference_name, reference_spec = cells[0]
        for cell_name, cell_spec in cells[1:]:
            all_fields = set(reference_spec) | set(cell_spec)
            mismatches = [
                f"{field}: {reference_spec.get(field)!r} != {cell_spec.get(field)!r}"
                for field in sorted(all_fields)
                if reference_spec.get(field) != cell_spec.get(field)
            ]
            if mismatches:
                errors.append(
                    f"Spec mismatch between '{reference_name}' and '{cell_name}' "
                    f"({manufacturer}/{model}/{batch}): {'; '.join(mismatches)}"
                )


def validate_quality(root: Path) -> tuple[list[str], list[str]]:
    """Run all data quality checks across all contributors and cells."""
    errors: list[str] = []
    warnings: list[str] = []

    NON_CONTRIBUTOR_DIRS = {"scripts", ".github"}
    contributor_dirs = [
        p for p in sorted(root.iterdir())
        if p.is_dir() and not p.name.startswith(".") and p.name not in NON_CONTRIBUTOR_DIRS
    ]

    for contributor_dir in contributor_dirs:
        cell_dirs = [p for p in sorted(contributor_dir.iterdir()) if p.is_dir()]

        for cell_dir in cell_dirs:
            battery_json = cell_dir / "battery.json"
            if battery_json.exists():
                try:
                    with battery_json.open() as f:
                        data = json.load(f)
                    spec = data.get("spec")
                    if spec:
                        rel = str(cell_dir.relative_to(root))
                        check_spec_values(rel, spec, errors, warnings)
                except json.JSONDecodeError:
                    pass  # caught by validate_structure.py

            check_timeseries_metadata(cell_dir, errors, warnings)

        check_cross_cell_consistency(contributor_dir, errors, warnings)

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate bdf-datastore data quality and consistency."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root to validate (default: current directory).",
    )
    parser.add_argument(
        "--warn-as-error",
        action="store_true",
        help="Treat warnings as errors.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors, warnings = validate_quality(root)

    if warnings:
        print("Warnings:", file=sys.stderr)
        for w in warnings:
            print(f"  WARN  {w}", file=sys.stderr)

    if errors:
        print("Errors:", file=sys.stderr)
        for e in errors:
            print(f"  ERROR {e}", file=sys.stderr)

    total_issues = len(errors) + (len(warnings) if args.warn_as_error else 0)

    if total_issues == 0:
        print(f"OK — quality validated {root}")
    else:
        print(
            f"Quality validation failed: {len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
