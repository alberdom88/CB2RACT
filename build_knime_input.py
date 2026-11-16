#!/usr/bin/env python3
"""
Build a KNIME input file from a single SIFt (Structural Interaction
FingerprinT) CSV.

The script keeps the ``Title`` column plus the 176 fingerprint bit columns
listed below -- in that exact order -- and discards every other column
(docking score included). The expected bit layout is hard-coded here, so no
external reference file is needed.

Best-pose / best-docking-score selection is assumed to have been done
upstream: this script does not merge, sort or deduplicate anything.

Usage
-----
    python build_knime_input.py INPUT.csv
    python build_knime_input.py INPUT.csv -o OUTPUT.csv
    python build_knime_input.py INPUT.csv --fail-on-duplicates
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------
# 1. EXPECTED LAYOUT
# ---------------------------------------------------------------------

ID_COLUMN = "Title"

# The 176 interaction-fingerprint bits, in reference order.
BIT_COLUMNS = [
    "A25_contact", "A25_backbone", "A25_sidechain",
    "A25_hydrophobic", "A25_acceptor", "A25_aromatic",
    "A27_contact", "A27_backbone", "A27_sidechain",
    "A27_hydrophobic", "A87_contact", "A87_backbone",
    "A87_sidechain", "A87_hydrophobic", "A87_aromatic",
    "A90_contact", "A90_backbone", "A90_sidechain",
    "A90_polar", "A90_acceptor", "A91_contact",
    "A91_backbone", "A91_sidechain", "A91_hydrophobic",
    "A91_aromatic", "A93_contact", "A93_backbone",
    "A93_sidechain", "A93_polar", "A93_donor",
    "A94_contact", "A94_backbone", "A94_sidechain",
    "A94_hydrophobic", "A94_aromatic", "A95_contact",
    "A95_sidechain", "A95_polar", "A95_acceptor",
    "A95_donor", "A99_contact", "A99_backbone",
    "A101_contact", "A101_sidechain", "A101_polar",
    "A101_acceptor", "A101_charged", "A106_contact",
    "A106_backbone", "A106_sidechain", "A106_hydrophobic",
    "A106_aromatic", "A109_contact", "A109_backbone",
    "A109_sidechain", "A109_polar", "A109_charged",
    "A110_contact", "A110_backbone", "A110_sidechain",
    "A110_hydrophobic", "A111_contact", "A111_backbone",
    "A113_contact", "A113_backbone", "A113_sidechain",
    "A113_hydrophobic", "A114_contact", "A114_backbone",
    "A114_sidechain", "A114_polar", "A114_acceptor",
    "A117_contact", "A117_sidechain", "A117_hydrophobic",
    "A117_aromatic", "A165_contact", "A165_backbone",
    "A165_acceptor", "A168_contact", "A168_sidechain",
    "A168_hydrophobic", "A181_contact", "A181_backbone",
    "A182_contact", "A182_backbone", "A182_sidechain",
    "A182_hydrophobic", "A182_acceptor", "A183_contact",
    "A183_backbone", "A183_sidechain", "A183_hydrophobic",
    "A183_aromatic", "A184_contact", "A184_sidechain",
    "A184_hydrophobic", "A186_contact", "A186_sidechain",
    "A186_hydrophobic", "A190_contact", "A190_backbone",
    "A190_sidechain", "A190_hydrophobic", "A190_aromatic",
    "A191_contact", "A191_backbone", "A191_sidechain",
    "A191_hydrophobic", "A194_contact", "A194_sidechain",
    "A194_hydrophobic", "A194_aromatic", "A258_contact",
    "A258_backbone", "A258_sidechain", "A258_hydrophobic",
    "A258_aromatic", "A261_contact", "A261_backbone",
    "A261_sidechain", "A261_hydrophobic", "A262_contact",
    "A262_backbone", "A262_sidechain", "A262_hydrophobic",
    "A265_contact", "A265_sidechain", "A265_hydrophobic",
    "A278_contact", "A278_backbone", "A278_sidechain",
    "A278_polar", "A278_acceptor", "A278_charged",
    "A279_contact", "A279_backbone", "A281_contact",
    "A281_backbone", "A281_sidechain", "A281_hydrophobic",
    "A281_aromatic", "A282_contact", "A282_backbone",
    "A282_sidechain", "A282_hydrophobic", "A285_contact",
    "A285_backbone", "A285_sidechain", "A285_polar",
    "A288_contact", "A288_sidechain", "A288_hydrophobic",
    "A26_contact", "A26_backbone", "A27_donor",
    "A28_contact", "A28_sidechain", "A28_hydrophobic",
    "A36_contact", "A36_sidechain", "A36_hydrophobic",
    "A110_acceptor", "A114_donor", "A117_backbone",
    "A118_contact", "A118_backbone", "A118_sidechain",
    "A118_polar", "A181_acceptor", "A184_backbone",
    "A190_acceptor", "A279_sidechain", "A279_polar",
    "A279_charged", "A285_acceptor",
]

N_EXPECTED_BITS = 176


# ---------------------------------------------------------------------
# 2. COMMAND-LINE INTERFACE
# ---------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Keep 'Title' plus the 176 reference fingerprint bits from a "
            "SIFt CSV and write a KNIME-ready file."
        )
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Input CSV file (one row per pose, best pose already selected).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Output CSV file. Defaults to '<input stem>_knime.csv' next to "
            "the input file."
        ),
    )
    parser.add_argument(
        "--fail-on-duplicates",
        action="store_true",
        help=(
            "Exit with an error if the same Title appears more than once "
            "(default: only warn)."
        ),
    )
    return parser.parse_args(argv)


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_knime.csv")


# ---------------------------------------------------------------------
# 3. MAIN
# ---------------------------------------------------------------------

def main(argv=None) -> int:
    args = parse_args(argv)

    # -- Sanity check on the hard-coded layout -------------------------
    if len(BIT_COLUMNS) != N_EXPECTED_BITS:
        sys.exit(
            f"Internal error: expected {N_EXPECTED_BITS} bit columns, "
            f"found {len(BIT_COLUMNS)} in BIT_COLUMNS."
        )
    if len(set(BIT_COLUMNS)) != len(BIT_COLUMNS):
        sys.exit("Internal error: BIT_COLUMNS contains duplicated names.")

    input_path: Path = args.input_file
    if not input_path.is_file():
        sys.exit(f"Input file not found: {input_path}")

    output_path: Path = args.output or default_output_path(input_path)

    # -- Read ----------------------------------------------------------
    try:
        df = pd.read_csv(input_path)
    except Exception as exc:  # pragma: no cover - defensive
        sys.exit(f"Could not read '{input_path}': {exc}")

    print(f"Input file : {input_path}")
    print(f"Rows read  : {len(df)}")
    print(f"Columns    : {len(df.columns)}")

    # -- Validate required columns -------------------------------------
    required = [ID_COLUMN] + BIT_COLUMNS
    missing = [col for col in required if col not in df.columns]
    if missing:
        preview = ", ".join(missing[:10])
        suffix = f" ... (+{len(missing) - 10} more)" if len(missing) > 10 else ""
        sys.exit(
            f"Missing {len(missing)} required column(s): {preview}{suffix}"
        )

    extra = [col for col in df.columns if col not in required]
    if extra:
        print(f"Dropped    : {len(extra)} extra column(s) (e.g. {extra[0]})")

    # -- Select and reorder --------------------------------------------
    final_df = df[required].copy()

    # -- Data quality checks -------------------------------------------
    n_missing_ids = int(final_df[ID_COLUMN].isna().sum())
    if n_missing_ids:
        sys.exit(f"Found {n_missing_ids} row(s) with an empty '{ID_COLUMN}'.")

    n_missing_bits = int(final_df[BIT_COLUMNS].isna().sum().sum())
    if n_missing_bits:
        sys.exit(
            f"Found {n_missing_bits} missing value(s) in the fingerprint "
            "bit columns."
        )

    duplicated = final_df[ID_COLUMN].duplicated(keep=False)
    n_dup_titles = int(final_df.loc[duplicated, ID_COLUMN].nunique())
    if n_dup_titles:
        message = (
            f"{n_dup_titles} Title(s) appear more than once "
            f"({int(duplicated.sum())} rows involved)."
        )
        if args.fail_on_duplicates:
            sys.exit(f"Error: {message}")
        print(f"Warning    : {message}")

    # -- Write ---------------------------------------------------------
    try:
        final_df.to_csv(output_path, index=False)
    except Exception as exc:  # pragma: no cover - defensive
        sys.exit(f"Could not write '{output_path}': {exc}")

    # -- Report --------------------------------------------------------
    print("-" * 46)
    print("DONE")
    print(f"Rows written   : {len(final_df)}")
    print(f"Columns written: {len(final_df.columns)} "
          f"(1 identifier + {len(BIT_COLUMNS)} bits)")
    print(f"Output file    : {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
