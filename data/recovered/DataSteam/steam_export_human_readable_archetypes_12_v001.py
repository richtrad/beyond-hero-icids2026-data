#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_export_human_readable_archetypes_12_v001.py

Primitive human-readable export from the corrected 12-archetype dataset.

Input:
  steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv

Output:
  steam_bulk_outputs/human_readable_archetypes_12_v001.csv

Columns:
  jmeno hry
  jmeno postavy
  primarni archetyp
  sekundarni archetyp
  tercialni archetyp
  věrohodnost odhadu na škále 0 až 1

Credibility formula:
  credibility = mean(
      protagonist_confidence_0_3,
      archetype_confidence_0_3,
      archetype_suitability_0_3
  ) / 3

So:
  0 = very weak / unusable estimate
  1 = strongest estimate
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path("steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv")
DEFAULT_OUTPUT = Path("steam_bulk_outputs/human_readable_archetypes_12_v001.csv")


def require_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            "Input CSV is missing required columns:\n"
            + "\n".join(f"  - {c}" for c in missing)
            + "\n\nRun steam_make_final_archetype_datasets_12_v001.py first."
        )


def num01_from_0_3(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).clip(0, 3) / 3.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--only-core",
        action="store_true",
        help="Export only rows marked as is_core_broad_12 == True."
    )
    parser.add_argument(
        "--only-strict",
        action="store_true",
        help="Export only rows marked as is_core_strict_12 == True."
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    print(f"Loading: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)

    require_columns(df, [
        "name",
        "llm6_protagonist_name",
        "primary_archetype_12",
        "secondary_archetype_12",
        "tertiary_archetype_12",
        "llm6_protagonist_confidence_0_3",
        "llm6_archetype_confidence_0_3",
        "llm6_archetype_suitability_0_3",
    ])

    if args.only_strict:
        require_columns(df, ["is_core_strict_12"])
        mask = df["is_core_strict_12"].fillna(False).astype(str).str.lower().isin(["true", "1", "yes", "y"])
        df = df[mask].copy()
    elif args.only_core:
        require_columns(df, ["is_core_broad_12"])
        mask = df["is_core_broad_12"].fillna(False).astype(str).str.lower().isin(["true", "1", "yes", "y"])
        df = df[mask].copy()

    protagonist_conf = num01_from_0_3(df["llm6_protagonist_confidence_0_3"])
    archetype_conf = num01_from_0_3(df["llm6_archetype_confidence_0_3"])
    suitability = num01_from_0_3(df["llm6_archetype_suitability_0_3"])

    credibility = ((protagonist_conf + archetype_conf + suitability) / 3.0).round(3)

    out = pd.DataFrame({
        "jmeno hry": df["name"].fillna("").astype(str),
        "jmeno postavy": df["llm6_protagonist_name"].fillna("").astype(str),
        "primarni archetyp": df["primary_archetype_12"].fillna("").astype(str),
        "sekundarni archetyp": df["secondary_archetype_12"].fillna("").astype(str),
        "tercialni archetyp": df["tertiary_archetype_12"].fillna("").astype(str),
        "věrohodnost odhadu na škále 0 až 1": credibility,
    })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"Saved: {output_path}")
    print(f"Rows: {len(out)}")
    print("Columns:")
    for col in out.columns:
        print(f"  - {col}")


if __name__ == "__main__":
    main()
