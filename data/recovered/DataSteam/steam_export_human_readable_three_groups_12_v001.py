#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_export_human_readable_three_groups_12_v001.py

Create primitive human-readable exports for the three 12-archetype group files.

Input directory:
  steam_bulk_outputs/three_groups_12_v001/

Default input files:
  group_1_core_strict_12_v001.csv
  group_2_core_broad_12_v001.csv
  group_3_review_pool_12_v001.csv

Also supports exclusive groups with --exclusive:
  exclusive_group_1_core_strict_12_v001.csv
  exclusive_group_2_core_broad_nonreview_12_v001.csv
  exclusive_group_3_review_pool_noncorestrict_12_v001.csv

Output directory:
  steam_bulk_outputs/human_readable_three_groups_12_v001/

Output columns:
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

No API calls. No money spent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_INPUT_DIR = Path("steam_bulk_outputs/three_groups_12_v001")
DEFAULT_OUTPUT_DIR = Path("steam_bulk_outputs/human_readable_three_groups_12_v001")


STANDARD_GROUPS = [
    (
        "group_1_core_strict_12_v001.csv",
        "human_readable_group_1_core_strict_12_v001.csv",
        "CORE_STRICT",
    ),
    (
        "group_2_core_broad_12_v001.csv",
        "human_readable_group_2_core_broad_12_v001.csv",
        "CORE_BROAD",
    ),
    (
        "group_3_review_pool_12_v001.csv",
        "human_readable_group_3_review_pool_12_v001.csv",
        "REVIEW_POOL",
    ),
]

EXCLUSIVE_GROUPS = [
    (
        "exclusive_group_1_core_strict_12_v001.csv",
        "human_readable_exclusive_group_1_core_strict_12_v001.csv",
        "EXCLUSIVE_CORE_STRICT",
    ),
    (
        "exclusive_group_2_core_broad_nonreview_12_v001.csv",
        "human_readable_exclusive_group_2_core_broad_nonreview_12_v001.csv",
        "EXCLUSIVE_CORE_BROAD_NONREVIEW",
    ),
    (
        "exclusive_group_3_review_pool_noncorestrict_12_v001.csv",
        "human_readable_exclusive_group_3_review_pool_noncorestrict_12_v001.csv",
        "EXCLUSIVE_REVIEW_POOL_NONCORESTRICT",
    ),
]


def require_columns(df: pd.DataFrame, cols: list[str], source: Path) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"Input CSV is missing required columns: {source}\n"
            + "\n".join(f"  - {c}" for c in missing)
            + "\n\nRun steam_make_three_groups_12_v001.py first."
        )


def num01_from_0_3(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).clip(0, 3) / 3.0


def make_human_readable(df: pd.DataFrame) -> pd.DataFrame:
    protagonist_conf = num01_from_0_3(df["llm6_protagonist_confidence_0_3"])
    archetype_conf = num01_from_0_3(df["llm6_archetype_confidence_0_3"])
    suitability = num01_from_0_3(df["llm6_archetype_suitability_0_3"])

    credibility = ((protagonist_conf + archetype_conf + suitability) / 3.0).round(3)

    return pd.DataFrame({
        "jmeno hry": df["name"].fillna("").astype(str),
        "jmeno postavy": df["llm6_protagonist_name"].fillna("").astype(str),
        "primarni archetyp": df["primary_archetype_12"].fillna("").astype(str),
        "sekundarni archetyp": df["secondary_archetype_12"].fillna("").astype(str),
        "tercialni archetyp": df["tertiary_archetype_12"].fillna("").astype(str),
        "věrohodnost odhadu na škále 0 až 1": credibility,
    })


def process_group(input_dir: Path, output_dir: Path, input_name: str, output_name: str, group_label: str) -> dict:
    input_path = input_dir / input_name
    output_path = output_dir / output_name

    if not input_path.exists():
        print(f"WARNING: missing input group, skipping: {input_path}")
        return {
            "group": group_label,
            "input": str(input_path),
            "output": str(output_path),
            "status": "missing_input",
            "rows": 0,
        }

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
    ], input_path)

    out = make_human_readable(df)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"Saved {group_label}: {output_path} ({len(out)} rows)")

    return {
        "group": group_label,
        "input": str(input_path),
        "output": str(output_path),
        "status": "ok",
        "rows": int(len(out)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--exclusive",
        action="store_true",
        help="Use exclusive non-overlapping group files instead of the standard methodological group files."
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Export both standard and exclusive group files."
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        raise FileNotFoundError(input_dir)

    group_specs = []
    if args.both:
        group_specs.extend(STANDARD_GROUPS)
        group_specs.extend(EXCLUSIVE_GROUPS)
    elif args.exclusive:
        group_specs.extend(EXCLUSIVE_GROUPS)
    else:
        group_specs.extend(STANDARD_GROUPS)

    summary = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "mode": "both" if args.both else ("exclusive" if args.exclusive else "standard"),
        "groups": [],
        "columns": [
            "jmeno hry",
            "jmeno postavy",
            "primarni archetyp",
            "sekundarni archetyp",
            "tercialni archetyp",
            "věrohodnost odhadu na škále 0 až 1",
        ],
        "credibility_formula": "mean(protagonist_confidence_0_3, archetype_confidence_0_3, archetype_suitability_0_3) / 3"
    }

    for input_name, output_name, group_label in group_specs:
        result = process_group(input_dir, output_dir, input_name, output_name, group_label)
        summary["groups"].append(result)

    summary_path = output_dir / "human_readable_three_groups_12_summary_v001.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# Human-readable three-group exports, 12-archetype version v001

Input directory:

`{input_dir}`

Output directory:

`{output_dir}`

Mode:

`{summary['mode']}`

## Output columns

- jmeno hry
- jmeno postavy
- primarni archetyp
- sekundarni archetyp
- tercialni archetyp
- věrohodnost odhadu na škále 0 až 1

## Credibility formula

`mean(protagonist_confidence_0_3, archetype_confidence_0_3, archetype_suitability_0_3) / 3`

## Generated files

""" + "\n".join(
        f"- `{Path(g['output']).name}` — {g['rows']} rows, status: {g['status']}"
        for g in summary["groups"]
    ) + "\n"

    (output_dir / "README_human_readable_three_groups_12_v001.md").write_text(readme, encoding="utf-8")

    print(f"\nSummary: {summary_path}")
    print(f"README:  {output_dir / 'README_human_readable_three_groups_12_v001.md'}")


if __name__ == "__main__":
    main()
