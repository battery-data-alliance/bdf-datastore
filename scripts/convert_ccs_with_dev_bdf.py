from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd


BLOCK_SAMPLES = {
    0x00000002: 0,
    0x00000103: 1,
    0x00000203: 2,
    0x00000303: 3,
    0x00000403: 4,
    0x00000503: 5,
    0x00000603: 6,
}


def load_dev_bdf(dev_src: Path):
    sys.path.insert(0, str(dev_src))
    import bdf  # type: ignore
    from bdf.io import save  # type: ignore

    return bdf, save


def find_payload_offset(raw: bytes) -> int:
    seek_end = min(len(raw) - 128 * 6, 0x4000)
    for off in range(0, max(seek_end, 0) + 1, 0x80):
        if all(
            struct.unpack_from("<I", raw, off + 128 * k)[0] in BLOCK_SAMPLES
            for k in range(6)
        ):
            return off
    raise ValueError("Could not locate CCS payload block sequence.")


def detect_record_size(raw: bytes, start: int) -> int:
    probe_words = [
        struct.unpack_from("<I", raw, start + 128 * k)[0]
        for k in range(min((len(raw) - start) // 128, 32))
    ]
    return 20 if 0x00000603 in probe_words else 24


def parse_landt_ccs_variant(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    start = find_payload_offset(raw)
    record_size = detect_record_size(raw, start)

    dt_ms: list[int] = []
    voltage: list[float] = []
    current: list[float] = []
    delta_capacity: list[float] = []
    delta_energy: list[float] = []
    resistance: list[float] = []

    n_blocks = (len(raw) - start) // 128
    for i in range(n_blocks):
        off = start + i * 128
        word = struct.unpack_from("<I", raw, off)[0]
        n_samples = BLOCK_SAMPLES.get(word, 0)
        if n_samples == 0:
            continue

        for j in range(n_samples):
            rec_off = off + 8 + j * record_size
            if record_size == 20:
                dti, v, ia, dq, de = struct.unpack_from("<Iffff", raw, rec_off)
                rint = np.nan
            else:
                dti, v, ia, dq, de, rint = struct.unpack_from("<Ifffff", raw, rec_off)

            if dti <= 0:
                continue
            if not np.isfinite([v, ia, dq, de]).all():
                continue

            dt_ms.append(int(dti))
            voltage.append(float(v))
            current.append(float(ia))
            delta_capacity.append(abs(float(dq)))
            delta_energy.append(abs(float(de)))
            resistance.append(float(rint))

    if not dt_ms:
        raise ValueError(f"No measurement records found in {path.name}.")

    dt = np.asarray(dt_ms, dtype="float64") / 1000.0
    test_time = np.cumsum(dt, dtype="float64")
    test_time -= test_time[0]

    current_arr = np.asarray(current, dtype="float64")
    delta_capacity_arr = np.asarray(delta_capacity, dtype="float64")
    delta_energy_arr = np.asarray(delta_energy, dtype="float64")
    is_charge = current_arr >= 0.0

    charging_capacity = np.cumsum(
        np.where(is_charge, delta_capacity_arr, 0.0),
        dtype="float64",
    )
    discharging_capacity = np.cumsum(
        np.where(~is_charge, delta_capacity_arr, 0.0),
        dtype="float64",
    )
    charging_energy = np.cumsum(
        np.where(is_charge, delta_energy_arr, 0.0),
        dtype="float64",
    )
    discharging_energy = np.cumsum(
        np.where(~is_charge, delta_energy_arr, 0.0),
        dtype="float64",
    )

    return pd.DataFrame(
        {
            "Test Time / s": test_time,
            "Voltage / V": np.asarray(voltage, dtype="float64"),
            "Current / A": current_arr,
            "Charging Capacity / Ah": charging_capacity,
            "Discharging Capacity / Ah": discharging_capacity,
            "Charging Energy / Wh": charging_energy,
            "Discharging Energy / Wh": discharging_energy,
            "Internal Resistance / ohm": np.asarray(resistance, dtype="float64"),
            "Step Index / 1": np.arange(1, len(test_time) + 1, dtype="int64"),
        }
    )


def output_path_for(raw_file: Path) -> Path:
    raw_dir = raw_file.parent
    while raw_dir.name != "raw":
        raw_dir = raw_dir.parent
    return (raw_dir.parent / "processed" / raw_file.relative_to(raw_dir)).with_suffix(".bdf.csv")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert LAND .ccs files using a local battery-data-format development checkout."
    )
    parser.add_argument("files", nargs="+", help="CCS files to convert")
    parser.add_argument(
        "--dev-src",
        required=True,
        help="Path to the local battery-data-format src directory",
    )
    args = parser.parse_args()

    dev_src = Path(args.dev_src).resolve()
    bdf, save = load_dev_bdf(dev_src)

    for file_arg in args.files:
        raw_file = Path(file_arg).resolve()
        df = parse_landt_ccs_variant(raw_file)
        bdf.validate_df(df)
        out_path = output_path_for(raw_file)
        save(df, out_path, index=False)
        print(out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
