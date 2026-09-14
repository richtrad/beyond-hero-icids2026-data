#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_make_final_archetype_datasets_v001.py

Create clean final working datasets from the merged Steam LLM taxonomy file.

Default input:
  steam_bulk_outputs/steam_v006b_50k_with_taxonomy_top_v005_rest_parts_local.csv

Outputs in:
  steam_bulk_outputs/final_archetype_datasets_v001/

Main outputs:
  steam_core_strict_v001.csv
  steam_core_broad_v001.csv
  steam_core_maybe_v001.csv
  steam_review_pool_v001.csv
  steam_missing_llm_results_v001.csv
  steam_analysis_ready_v001.csv

Summary outputs:
  steam_dataset_summary_v001.json
  steam_primary_archetype_counts_v001.csv
  steam_model_counts_v001.csv
  steam_rank_bins_v001.csv
  README_final_datasets_v001.md

Definitions:
  CORE_STRICT:
    has protagonist = yes
    include = yes
    archetype_confidence >= 2
    archetype_suitability >= 2
    manual_review = false

  CORE_BROAD:
    has protagonist = yes
    include = yes

  CORE_MAYBE:
    has protagonist = yes
    include in {yes, maybe}

  REVIEW_POOL:
    manual_review = true
    OR has protagonist = uncertain
    OR archetype_confidence <= 1
    OR protagonist_confidence <= 1
    OR include = maybe

  MISSING:
    no LLM result in llm6_has_clear_main_protagonist
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path("steam_bulk_outputs/steam_v006b_50k_with_taxonomy_top_v005_rest_parts_local.csv")
DEFAULT_OUTDIR = Path("steam_bulk_outputs/final_archetype_datasets_v001")


def norm_str_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def to_num(s: pd.Series, default=0) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(default)


def require_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            "Input CSV is missing required columns:\n"
            + "\n".join(f"  - {c}" for c in missing)
            + "\n\nThis script expects the v006b merged file with llm6_* columns."
        )


def add_rank_bins(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "selection_rank" not in out.columns:
        out["rank_bin_5000"] = "unknown"
        return out

    rank = pd.to_numeric(out["selection_rank"], errors="coerce")
    bin_start = (((rank - 1) // 5000) * 5000 + 1).astype("Int64")
    bin_end = (bin_start + 4999).astype("Int64")
    out["rank_bin_5000"] = bin_start.astype(str) + "-" + bin_end.astype(str)
    out.loc[rank.isna(), "rank_bin_5000"] = "unknown"
    return out


def add_corpus_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    has_prog = norm_str_series(out["llm6_has_clear_main_protagonist"]).str.lower()
    include = norm_str_series(out["llm6_suggested_include_in_final_corpus"]).str.lower()
    manual = out["llm6_needs_manual_review"].fillna(False).astype(bool)
    arch_conf = to_num(out["llm6_archetype_confidence_0_3"])
    prog_conf = to_num(out["llm6_protagonist_confidence_0_3"])
    suitability = to_num(out["llm6_archetype_suitability_0_3"])

    out["is_missing_llm_result"] = has_prog.eq("")
    out["is_core_broad"] = has_prog.eq("yes") & include.eq("yes")
    out["is_core_maybe"] = has_prog.eq("yes") & include.isin(["yes", "maybe"])
    out["is_core_strict"] = (
        has_prog.eq("yes")
        & include.eq("yes")
        & (arch_conf >= 2)
        & (suitability >= 2)
        & (~manual)
    )

    out["is_review_pool"] = (
        manual
        | has_prog.eq("uncertain")
        | (arch_conf <= 1)
        | (prog_conf <= 1)
        | include.eq("maybe")
    ) & (~out["is_missing_llm_result"])

    # A compact human-readable primary label for quick filtering.
    out["corpus_label"] = "other"
    out.loc[out["is_review_pool"], "corpus_label"] = "review_pool"
    out.loc[out["is_core_maybe"], "corpus_label"] = "core_maybe"
    out.loc[out["is_core_broad"], "corpus_label"] = "core_broad"
    out.loc[out["is_core_strict"], "corpus_label"] = "core_strict"
    out.loc[out["is_missing_llm_result"], "corpus_label"] = "missing_llm_result"

    return out


def preferred_columns(df: pd.DataFrame) -> list[str]:
    first = [
        "selection_rank",
        "appid",
        "name",
        "total_ratings_pos_neg",
        "positive_ratio",
        "steamspy_owners",
        "v005_split",
        "v005_model",
        "llm6_model_used",
        "corpus_label",
        "is_core_strict",
        "is_core_broad",
        "is_core_maybe",
        "is_review_pool",
        "is_missing_llm_result",
        "llm6_has_clear_main_protagonist",
        "llm6_protagonist_name",
        "llm6_protagonist_type",
        "llm6_protagonist_confidence_0_3",
        "llm6_primary_archetype",
        "llm6_secondary_archetype",
        "llm6_tertiary_archetype",
        "llm6_archetype_confidence_0_3",
        "llm6_archetype_suitability_0_3",
        "llm6_shadow_load_0_3",
        "llm6_player_projection_0_3",
        "llm6_narrative_complexity_0_3",
        "llm6_suggested_include_in_final_corpus",
        "llm6_needs_manual_review",
        "llm6_evidence_basis",
        "llm6_exclusion_reason",
        "llm6_note",
        "rank_bin_5000",
        "available_terms_for_later_inspection",
        "control_protagonist",
    ]
    first_existing = [c for c in first if c in df.columns]
    rest = [c for c in df.columns if c not in first_existing]
    return first_existing + rest


def counts_dict(s: pd.Series) -> dict:
    vc = s.fillna("<missing>").astype(str).value_counts(dropna=False)
    return {str(k): int(v) for k, v in vc.items()}


def make_primary_counts(df: pd.DataFrame, outdir: Path) -> pd.DataFrame:
    rows = []

    subsets = {
        "all_with_llm": df[~df["is_missing_llm_result"]],
        "core_strict": df[df["is_core_strict"]],
        "core_broad": df[df["is_core_broad"]],
        "core_maybe": df[df["is_core_maybe"]],
        "review_pool": df[df["is_review_pool"]],
    }

    for subset_name, sub in subsets.items():
        vc = sub["llm6_primary_archetype"].fillna("<missing>").astype(str).value_counts(dropna=False)
        total = len(sub)
        for archetype, count in vc.items():
            rows.append({
                "subset": subset_name,
                "primary_archetype": archetype,
                "count": int(count),
                "share": (float(count) / total) if total else 0.0,
            })

    result = pd.DataFrame(rows)
    result.to_csv(outdir / "steam_primary_archetype_counts_v001.csv", index=False, encoding="utf-8-sig")
    return result


def make_rank_bins(df: pd.DataFrame, outdir: Path) -> pd.DataFrame:
    if "rank_bin_5000" not in df.columns:
        return pd.DataFrame()

    grouped = (
        df.groupby("rank_bin_5000", dropna=False)
        .agg(
            rows=("appid", "count"),
            llm_results=("is_missing_llm_result", lambda x: int((~x).sum())),
            core_strict=("is_core_strict", "sum"),
            core_broad=("is_core_broad", "sum"),
            core_maybe=("is_core_maybe", "sum"),
            review_pool=("is_review_pool", "sum"),
        )
        .reset_index()
    )

    # Sort by numeric start where possible.
    def sort_key(label: str) -> int:
        try:
            return int(str(label).split("-")[0])
        except Exception:
            return 10**12

    grouped["_sort"] = grouped["rank_bin_5000"].map(sort_key)
    grouped = grouped.sort_values("_sort").drop(columns=["_sort"])
    grouped.to_csv(outdir / "steam_rank_bins_v001.csv", index=False, encoding="utf-8-sig")
    return grouped


def write_readme(outdir: Path, summary: dict) -> None:
    text = f"""# Steam archetype final datasets v001

Generated by `steam_make_final_archetype_datasets_v001.py`.

## Input

`{summary['input_csv']}`

## Main datasets

- `steam_analysis_ready_v001.csv` — full dataset with corpus flags and preferred column order.
- `steam_core_strict_v001.csv` — high-confidence clean analytical subset.
- `steam_core_broad_v001.csv` — protagonist=yes and include=yes.
- `steam_core_maybe_v001.csv` — protagonist=yes and include=yes/maybe.
- `steam_review_pool_v001.csv` — rows recommended for manual/agent review.
- `steam_missing_llm_results_v001.csv` — rows with missing LLM classification.

## Corpus definitions

### CORE_STRICT

- `llm6_has_clear_main_protagonist == yes`
- `llm6_suggested_include_in_final_corpus == yes`
- `llm6_archetype_confidence_0_3 >= 2`
- `llm6_archetype_suitability_0_3 >= 2`
- `llm6_needs_manual_review == false`

### CORE_BROAD

- `llm6_has_clear_main_protagonist == yes`
- `llm6_suggested_include_in_final_corpus == yes`

### CORE_MAYBE

- `llm6_has_clear_main_protagonist == yes`
- `llm6_suggested_include_in_final_corpus in [yes, maybe]`

### REVIEW_POOL

- `llm6_needs_manual_review == true`
- OR `llm6_has_clear_main_protagonist == uncertain`
- OR `llm6_archetype_confidence_0_3 <= 1`
- OR `llm6_protagonist_confidence_0_3 <= 1`
- OR `llm6_suggested_include_in_final_corpus == maybe`

## Summary

- Total rows: {summary['rows_total']}
- LLM results: {summary['rows_with_llm_result']}
- Missing LLM results: {summary['rows_missing_llm_result']}
- CORE_STRICT: {summary['core_strict_rows']}
- CORE_BROAD: {summary['core_broad_rows']}
- CORE_MAYBE: {summary['core_maybe_rows']}
- REVIEW_POOL: {summary['review_pool_rows']}
"""
    (outdir / "README_final_datasets_v001.md").write_text(text, encoding="utf-8")


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
        "appid",
        "name",
        "llm6_has_clear_main_protagonist",
        "llm6_suggested_include_in_final_corpus",
        "llm6_archetype_confidence_0_3",
        "llm6_archetype_suitability_0_3",
        "llm6_protagonist_confidence_0_3",
        "llm6_needs_manual_review",
        "llm6_primary_archetype",
    ])

    df = add_rank_bins(df)
    df = add_corpus_flags(df)

    cols = preferred_columns(df)
    analysis_ready = df[cols].copy()

    core_strict = analysis_ready[analysis_ready["is_core_strict"]].copy()
    core_broad = analysis_ready[analysis_ready["is_core_broad"]].copy()
    core_maybe = analysis_ready[analysis_ready["is_core_maybe"]].copy()
    review_pool = analysis_ready[analysis_ready["is_review_pool"]].copy()
    missing = analysis_ready[analysis_ready["is_missing_llm_result"]].copy()

    analysis_ready.to_csv(outdir / "steam_analysis_ready_v001.csv", index=False, encoding="utf-8-sig")
    core_strict.to_csv(outdir / "steam_core_strict_v001.csv", index=False, encoding="utf-8-sig")
    core_broad.to_csv(outdir / "steam_core_broad_v001.csv", index=False, encoding="utf-8-sig")
    core_maybe.to_csv(outdir / "steam_core_maybe_v001.csv", index=False, encoding="utf-8-sig")
    review_pool.to_csv(outdir / "steam_review_pool_v001.csv", index=False, encoding="utf-8-sig")
    missing.to_csv(outdir / "steam_missing_llm_results_v001.csv", index=False, encoding="utf-8-sig")

    primary_counts = make_primary_counts(analysis_ready, outdir)
    rank_bins = make_rank_bins(analysis_ready, outdir)

    model_counts = (
        analysis_ready["llm6_model_used"]
        .fillna("<missing>")
        .astype(str)
        .value_counts(dropna=False)
        .rename_axis("llm6_model_used")
        .reset_index(name="count")
    )
    model_counts.to_csv(outdir / "steam_model_counts_v001.csv", index=False, encoding="utf-8-sig")

    summary = {
        "input_csv": str(input_path),
        "output_dir": str(outdir),
        "rows_total": int(len(analysis_ready)),
        "rows_with_llm_result": int((~analysis_ready["is_missing_llm_result"]).sum()),
        "rows_missing_llm_result": int(analysis_ready["is_missing_llm_result"].sum()),
        "core_strict_rows": int(len(core_strict)),
        "core_broad_rows": int(len(core_broad)),
        "core_maybe_rows": int(len(core_maybe)),
        "review_pool_rows": int(len(review_pool)),
        "has_clear_main_protagonist_counts": counts_dict(analysis_ready["llm6_has_clear_main_protagonist"]),
        "include_counts": counts_dict(analysis_ready["llm6_suggested_include_in_final_corpus"]),
        "model_counts": counts_dict(analysis_ready["llm6_model_used"] if "llm6_model_used" in analysis_ready.columns else pd.Series(dtype=str)),
        "primary_archetype_counts_all_with_llm": counts_dict(analysis_ready.loc[~analysis_ready["is_missing_llm_result"], "llm6_primary_archetype"]),
    }

    (outdir / "steam_dataset_summary_v001.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_readme(outdir, summary)

    print("\nCreated final datasets:")
    print(f"  {outdir / 'steam_analysis_ready_v001.csv'} ({len(analysis_ready)} rows)")
    print(f"  {outdir / 'steam_core_strict_v001.csv'} ({len(core_strict)} rows)")
    print(f"  {outdir / 'steam_core_broad_v001.csv'} ({len(core_broad)} rows)")
    print(f"  {outdir / 'steam_core_maybe_v001.csv'} ({len(core_maybe)} rows)")
    print(f"  {outdir / 'steam_review_pool_v001.csv'} ({len(review_pool)} rows)")
    print(f"  {outdir / 'steam_missing_llm_results_v001.csv'} ({len(missing)} rows)")
    print("\nSummary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
