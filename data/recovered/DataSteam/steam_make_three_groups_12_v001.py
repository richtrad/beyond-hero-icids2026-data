#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_make_three_groups_12_v001.py

Create the three working groups from the corrected 12-archetype dataset.

Input:
  steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv

Outputs:
  steam_bulk_outputs/three_groups_12_v001/

Standard groups:
  group_1_core_strict_12_v001.csv
  group_2_core_broad_12_v001.csv
  group_3_review_pool_12_v001.csv

Also creates mutually exclusive priority groups:
  exclusive_group_1_core_strict_12_v001.csv
  exclusive_group_2_core_broad_nonreview_12_v001.csv
  exclusive_group_3_review_pool_noncorestrict_12_v001.csv

No API calls. No money spent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path("steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv")
DEFAULT_OUTDIR = Path("steam_bulk_outputs/three_groups_12_v001")


def require_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            "Input CSV is missing required columns:\n"
            + "\n".join(f"  - {c}" for c in missing)
            + "\n\nRun steam_make_final_archetype_datasets_12_v001.py first."
        )


def as_bool(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.fillna(False)
    return s.fillna(False).astype(str).str.lower().isin(["true", "1", "yes", "y"])


def value_counts_to_rows(name: str, df: pd.DataFrame) -> list[dict]:
    rows = []
    rows.append({"group": name, "metric": "rows", "value": int(len(df))})

    for col in [
        "primary_archetype_12",
        "llm6_model_used",
        "llm6_has_clear_main_protagonist",
        "llm6_suggested_include_in_final_corpus",
        "shadow_load_category",
        "rank_bin_5000",
    ]:
        if col not in df.columns:
            continue
        vc = df[col].fillna("<missing>").astype(str).value_counts(dropna=False)
        for key, count in vc.items():
            rows.append({
                "group": name,
                "metric": f"{col}={key}",
                "value": int(count),
            })

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    print(f"Loading: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)

    require_columns(df, [
        "is_core_strict_12",
        "is_core_broad_12",
        "is_review_pool_12",
        "primary_archetype_12",
    ])

    is_strict = as_bool(df["is_core_strict_12"])
    is_broad = as_bool(df["is_core_broad_12"])
    is_review = as_bool(df["is_review_pool_12"])

    # Standard groups. These preserve the methodological definitions and may overlap.
    group_strict = df[is_strict].copy()
    group_broad = df[is_broad].copy()
    group_review = df[is_review].copy()

    # Mutually exclusive priority groups.
    # Priority:
    # 1. strict high-confidence analytical core
    # 2. review pool for inspection
    # 3. remaining broad usable cases
    exclusive_strict = df[is_strict].copy()
    exclusive_review = df[is_review & ~is_strict].copy()
    exclusive_broad_nonreview = df[is_broad & ~is_strict & ~is_review].copy()

    group_strict.to_csv(outdir / "group_1_core_strict_12_v001.csv", index=False, encoding="utf-8-sig")
    group_broad.to_csv(outdir / "group_2_core_broad_12_v001.csv", index=False, encoding="utf-8-sig")
    group_review.to_csv(outdir / "group_3_review_pool_12_v001.csv", index=False, encoding="utf-8-sig")

    exclusive_strict.to_csv(outdir / "exclusive_group_1_core_strict_12_v001.csv", index=False, encoding="utf-8-sig")
    exclusive_broad_nonreview.to_csv(outdir / "exclusive_group_2_core_broad_nonreview_12_v001.csv", index=False, encoding="utf-8-sig")
    exclusive_review.to_csv(outdir / "exclusive_group_3_review_pool_noncorestrict_12_v001.csv", index=False, encoding="utf-8-sig")

    summary = {
        "input_csv": str(input_path),
        "output_dir": str(outdir),
        "total_rows": int(len(df)),
        "standard_groups_may_overlap": True,
        "standard_group_rows": {
            "group_1_core_strict": int(len(group_strict)),
            "group_2_core_broad": int(len(group_broad)),
            "group_3_review_pool": int(len(group_review)),
        },
        "exclusive_groups_do_not_overlap": True,
        "exclusive_group_rows": {
            "exclusive_group_1_core_strict": int(len(exclusive_strict)),
            "exclusive_group_2_core_broad_nonreview": int(len(exclusive_broad_nonreview)),
            "exclusive_group_3_review_pool_noncorestrict": int(len(exclusive_review)),
        },
        "notes": [
            "Standard groups preserve the published methodological definitions.",
            "CORE_STRICT is a subset of CORE_BROAD by definition.",
            "REVIEW_POOL can overlap with broader corpus flags when a row has a clear protagonist but low confidence or manual-review need.",
            "Exclusive groups are for operational work where each game should appear in only one group."
        ]
    }

    (outdir / "three_groups_12_summary_v001.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_rows = []
    for name, sub in [
        ("group_1_core_strict", group_strict),
        ("group_2_core_broad", group_broad),
        ("group_3_review_pool", group_review),
        ("exclusive_group_1_core_strict", exclusive_strict),
        ("exclusive_group_2_core_broad_nonreview", exclusive_broad_nonreview),
        ("exclusive_group_3_review_pool_noncorestrict", exclusive_review),
    ]:
        summary_rows.extend(value_counts_to_rows(name, sub))

    pd.DataFrame(summary_rows).to_csv(outdir / "three_groups_12_counts_v001.csv", index=False, encoding="utf-8-sig")

    readme = f"""# Three working groups, 12-archetype version v001

Input:

`{input_path}`

## Standard groups

These preserve the methodological definitions and may overlap:

1. `group_1_core_strict_12_v001.csv`
2. `group_2_core_broad_12_v001.csv`
3. `group_3_review_pool_12_v001.csv`

Rows:

- CORE_STRICT: {len(group_strict)}
- CORE_BROAD: {len(group_broad)}
- REVIEW_POOL: {len(group_review)}

## Exclusive groups

These are mutually exclusive operational groups:

1. `exclusive_group_1_core_strict_12_v001.csv`
2. `exclusive_group_2_core_broad_nonreview_12_v001.csv`
3. `exclusive_group_3_review_pool_noncorestrict_12_v001.csv`

Priority:

1. CORE_STRICT first.
2. REVIEW_POOL second.
3. Remaining CORE_BROAD cases third.

Rows:

- exclusive CORE_STRICT: {len(exclusive_strict)}
- exclusive CORE_BROAD non-review: {len(exclusive_broad_nonreview)}
- exclusive REVIEW_POOL non-strict: {len(exclusive_review)}

Use the standard groups for reporting methodology. Use the exclusive groups for task assignment, manual review, or sampling where each game should appear only once.
"""
    (outdir / "README_three_groups_12_v001.md").write_text(readme, encoding="utf-8")

    print("\nCreated three-group exports:")
    print(f"  {outdir / 'group_1_core_strict_12_v001.csv'} ({len(group_strict)} rows)")
    print(f"  {outdir / 'group_2_core_broad_12_v001.csv'} ({len(group_broad)} rows)")
    print(f"  {outdir / 'group_3_review_pool_12_v001.csv'} ({len(group_review)} rows)")

    print("\nCreated exclusive operational groups:")
    print(f"  {outdir / 'exclusive_group_1_core_strict_12_v001.csv'} ({len(exclusive_strict)} rows)")
    print(f"  {outdir / 'exclusive_group_2_core_broad_nonreview_12_v001.csv'} ({len(exclusive_broad_nonreview)} rows)")
    print(f"  {outdir / 'exclusive_group_3_review_pool_noncorestrict_12_v001.csv'} ({len(exclusive_review)} rows)")

    print(f"\nSummary: {outdir / 'three_groups_12_summary_v001.json'}")
    print(f"Counts:  {outdir / 'three_groups_12_counts_v001.csv'}")


if __name__ == "__main__":
    main()
