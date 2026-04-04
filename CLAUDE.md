# bdf-datastore

## Project Status
Data repo with 28 cells (SINTEF: 19, Microsoft: 9); 100% raw→processed parity; all 19 SINTEF `battery.json` files added; CI live with metrics collection + alert enforcement (240 pytest tests, exits non-zero on any error or consistency score < 100%).

## What This Repo Is

A **data repository** (not a software project) containing battery test data in BDF format. Contributions from SINTEF and Microsoft. Uses Git LFS for all binary and large CSV files.

## Structure

```
{contributor}/
  {cell}/                  # manufacturer-model-batch-id
    battery.json           # cell-level metadata (specs, IDs)
    timeseries/
      raw/                 # original test hardware output (LFS)
      processed/           # *.bdf.csv converted files (LFS)
      *.json               # per-test metadata (schema.org/BatteryTest)
```

## Scripts

- `scripts/convert_raw_to_bdf.py` — batch converts all `raw/` files to `processed/*.bdf.csv` using the `bdf` package
- `scripts/convert_ccs_with_dev_bdf.py` — converts LAND .ccs files with a local dev checkout of battery-data-format

### Setup

```bash
pip install -r requirements.txt
```

### Running conversion

```bash
python scripts/convert_raw_to_bdf.py [repo-root]
```

## Known Issues / Open Work

1. **SINTEF battery.json missing** — 19/19 SINTEF cells lack cell-level metadata (`battery.json`). Needed for BDA website integration.
2. **Melasta model name inconsistency** — Folder names use `melasta-slpba842124hv-*` but filenames contain `melasta-slpba842124hvr-*` (extra `r`). One is wrong; needs reconciliation with SINTEF.
3. **No EIS data** — README mentions EIS but no EIS directories exist yet.
4. ~~**CI validation**~~ — resolved; GitHub Actions runs pytest + structure validation on every PR.

## CI

GitHub Actions (`.github/workflows/validate.yml`) runs on every PR and push to main:
1. **pytest** — 15 unit tests for `validate_structure.py` (`scripts/tests/`)
2. **Structure validation** — `scripts/validate_structure.py .` checks all cells have `battery.json`, raw/processed counts match
