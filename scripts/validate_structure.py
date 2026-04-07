"""Validate bdf-datastore structure and metadata completeness.

Checks:
- Each cell directory has a battery.json
- Raw and processed file counts match per cell
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allowed data subdirectory names
DATA_TYPES = {"timeseries", "eis"}


def check_cell(cell_dir: Path, errors: list[str], warnings: list[str]) -> None:
    battery_json = cell_dir / "battery.json"
    if not battery_json.exists():
        errors.append(f"Missing battery.json: {cell_dir.relative_to(cell_dir.parent.parent)}")
    else:
        try:
            with battery_json.open() as f:
                data = json.load(f)
            if "spec" not in data:
                warnings.append(
                    f"battery.json missing 'spec' key: {battery_json.relative_to(cell_dir.parent.parent)}"
                )
        except json.JSONDecodeError as e:
            errors.append(
                f"Invalid JSON in {battery_json.relative_to(cell_dir.parent.parent)}: {e}"
            )

    for data_type_dir in sorted(cell_dir.iterdir()):
        if not data_type_dir.is_dir():
            continue
        if data_type_dir.name not in DATA_TYPES:
            continue

        raw_dir = data_type_dir / "raw"
        processed_dir = data_type_dir / "processed"

        if not raw_dir.exists() and not processed_dir.exists():
            warnings.append(
                f"No raw/ or processed/ under {data_type_dir.relative_to(cell_dir.parent.parent)}"
            )
            continue

        raw_files = sorted(raw_dir.rglob("*")) if raw_dir.exists() else []
        raw_files = [f for f in raw_files if f.is_file()]
        processed_files = sorted(processed_dir.rglob("*.bdf.csv")) if processed_dir.exists() else []

        if len(raw_files) != len(processed_files):
            errors.append(
                f"Raw/processed count mismatch in "
                f"{data_type_dir.relative_to(cell_dir.parent.parent)}: "
                f"{len(raw_files)} raw vs {len(processed_files)} processed"
            )



def validate(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    # A contributor directory must contain at least one cell with timeseries/ or eis/
    NON_CONTRIBUTOR_DIRS = {"scripts", ".github"}
    contributor_dirs = [
        p for p in sorted(root.iterdir())
        if p.is_dir() and not p.name.startswith(".") and p.name not in NON_CONTRIBUTOR_DIRS
    ]

    if not contributor_dirs:
        errors.append("No contributor directories found at repo root")
        return errors, warnings

    for contributor_dir in contributor_dirs:
        cell_dirs = [p for p in sorted(contributor_dir.iterdir()) if p.is_dir() and p.name != ".git"]
        if not cell_dirs:
            warnings.append(f"Contributor directory has no cells: {contributor_dir.name}")
            continue

        for cell_dir in cell_dirs:
            check_cell(cell_dir, errors, warnings)

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate bdf-datastore structure and metadata completeness."
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
    errors, warnings = validate(root)

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
        print(f"OK — validated {root}")
    else:
        print(
            f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
