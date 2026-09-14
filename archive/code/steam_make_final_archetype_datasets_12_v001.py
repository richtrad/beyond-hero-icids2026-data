#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_make_final_archetype_datasets_12_v001.py

Repair/finalize Steam archetype datasets using ONLY the classic 12 archetypes.

Why this exists:
Earlier LLM output allowed "Shadow/Antihero" as a pseudo-archetype. That was a
methodological mistake if the paper uses the classic 12-archetype framework.
This script removes Shadow/Antihero from the archetype taxonomy and treats it as
a separate dimension using llm6_shadow_load_0_3 and a boolean flag.

No API calls. No money spent.

Default input:
  steam_bulk_outputs/steam_v006b_50k_with_taxonomy_top_v005_rest_parts_local.csv

Outputs:
  steam_bulk_outputs/final_archetype_datasets_12_v001/

Main outputs:
  steam_analysis_ready_12_v001.csv
  steam_core_strict_12_v001.csv
  steam_core_broad_12_v001.csv
  steam_core_maybe_12_v001.csv
  steam_review_pool_12_v001.csv
  steam_missing_llm_results_12_v001.csv
  steam_shadow_reassigned_cases_12_v001.csv

Summary outputs:
  steam_dataset_summary_12_v001.json
  steam_primary_archetype_12_counts_v001.csv
  steam_secondary_archetype_12_counts_v001.csv
  steam_shadow_dimension_counts_v001.csv
  steam_model_counts_12_v001.csv
  steam_rank_bins_12_v001.csv
  README_final_datasets_12_v001.md

Correction rule:
- Valid archetypes are only:
  Innocent, Everyman/Orphan, Hero/Warrior, Caregiver/Guardian,
  Explorer/Seeker, Rebel/Outlaw, Lover, Creator/Artist,
  Jester/Trickster, Sage/Investigator, Magician/Transformer, Ruler/Leader.
- If original primary is Shadow/Antihero:
  use the first valid 12-archetype found in original secondary or tertiary.
- If no valid 12-archetype is available:
  set corrected primary to Uncertain and mark manual review.
- Shadow/Antihero presence is preserved as:
  original_shadow_antihero_present
  llm6_shadow_load_0_3
  shadow_load_category

CORE_STRICT_12 additionally requires corrected primary archetype to be one of
the 12 valid archetypes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path("steam_bulk_outputs/steam_v006b_50k_with_taxonomy_top_v005_rest_parts_local.csv")
DEFAULT_OUTDIR = Path("steam_bulk_outputs/final_archetype_datasets_12_v001")

VALID_12 = [
    "Innocent",
    "Everyman/Orphan",
    "Hero/Warrior",
    "Caregiver/Guardian",
    "Explorer/Seeker",
    "Rebel/Outlaw",
    "Lover",
    "Creator/Artist",
    "Jester/Trickster",
    "Sage/Investigator",
    "Magician/Transformer",
    "Ruler/Leader",
]

VALID_12_SET = set(VALID_12)
META_VALUES = {"Not applicable", "Uncertain", "", "nan", "None", "<NA>"}
SHADOW_VALUE = "Shadow/Antihero"


def norm_value(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


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


def first_valid_12(values: list[str]) -> str:
    for v in values:
        v = norm_value(v)
        if v in VALID_12_SET:
            return v
    return ""


def corrected_archetype_row(row: pd.Series) -> pd.Series:
    p = norm_value(row.get("llm6_primary_archetype", ""))
    s = norm_value(row.get("llm6_secondary_archetype", ""))
    t = norm_value(row.get("llm6_tertiary_archetype", ""))

    original_values = [p, s, t]
    valid_ordered = []
    for v in original_values:
        if v in VALID_12_SET and v not in valid_ordered:
            valid_ordered.append(v)

    shadow_present = SHADOW_VALUE in original_values
    primary_was_shadow = p == SHADOW_VALUE

    # Corrected primary.
    if p in VALID_12_SET:
        cp = p
        method = "original_primary_valid_12"
    elif p == SHADOW_VALUE:
        cp = first_valid_12([s, t])
        if cp:
            method = "primary_shadow_reassigned_from_secondary_or_tertiary"
        else:
            cp = "Uncertain"
            method = "primary_shadow_no_valid_12_available"
    elif p == "Not applicable":
        cp = "Not applicable"
        method = "not_applicable"
    elif p == "Uncertain" or p == "":
        cp = "Uncertain"
        method = "original_primary_uncertain"
    else:
        cp = first_valid_12([s, t])
        if cp:
            method = "unknown_primary_reassigned_from_secondary_or_tertiary"
        else:
            cp = "Uncertain"
            method = "unknown_primary_no_valid_12_available"

    # Corrected secondary / tertiary: use ordered unique valid 12 archetypes, excluding corrected primary first.
    ordered = []
    if cp in VALID_12_SET:
        ordered.append(cp)
    for v in valid_ordered:
        if v not in ordered:
            ordered.append(v)

    cs = ordered[1] if len(ordered) >= 2 else "Uncertain"
    ct = ordered[2] if len(ordered) >= 3 else "Uncertain"

    shadow_load = row.get("llm6_shadow_load_0_3", "")
    try:
        shadow_load_num = int(float(shadow_load))
    except Exception:
        shadow_load_num = 0

    if shadow_load_num <= 0 and not shadow_present:
        shadow_cat = "none"
    elif shadow_load_num <= 1:
        shadow_cat = "low"
    elif shadow_load_num == 2:
        shadow_cat = "medium"
    else:
        shadow_cat = "high"

    return pd.Series({
        "primary_archetype_12": cp,
        "secondary_archetype_12": cs,
        "tertiary_archetype_12": ct,
        "primary_archetype_12_is_valid": cp in VALID_12_SET,
        "original_shadow_antihero_present": bool(shadow_present),
        "original_primary_was_shadow_antihero": bool(primary_was_shadow),
        "archetype_12_correction_method": method,
        "shadow_load_category": shadow_cat,
    })


def add_corrections(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    corrections = out.apply(corrected_archetype_row, axis=1)
    for c in corrections.columns:
        out[c] = corrections[c]

    # Force additional review for rows where primary was Shadow and no valid 12 archetype was available.
    needs = out["llm6_needs_manual_review"].fillna(False).astype(bool)
    needs = needs | out["archetype_12_correction_method"].eq("primary_shadow_no_valid_12_available")
    out["needs_manual_review_12"] = needs

    return out


def add_corpus_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    has_prog = norm_str_series(out["llm6_has_clear_main_protagonist"]).str.lower()
    include = norm_str_series(out["llm6_suggested_include_in_final_corpus"]).str.lower()
    manual = out["needs_manual_review_12"].fillna(False).astype(bool)
    arch_conf = to_num(out["llm6_archetype_confidence_0_3"])
    prog_conf = to_num(out["llm6_protagonist_confidence_0_3"])
    suitability = to_num(out["llm6_archetype_suitability_0_3"])
    valid_primary = out["primary_archetype_12_is_valid"].fillna(False).astype(bool)

    out["is_missing_llm_result"] = has_prog.eq("")
    out["is_core_broad_12"] = has_prog.eq("yes") & include.eq("yes") & valid_primary
    out["is_core_maybe_12"] = has_prog.eq("yes") & include.isin(["yes", "maybe"]) & valid_primary
    out["is_core_strict_12"] = (
        has_prog.eq("yes")
        & include.eq("yes")
        & valid_primary
        & (arch_conf >= 2)
        & (suitability >= 2)
        & (~manual)
    )

    out["is_review_pool_12"] = (
        manual
        | has_prog.eq("uncertain")
        | (arch_conf <= 1)
        | (prog_conf <= 1)
        | include.eq("maybe")
        | (~valid_primary & has_prog.eq("yes"))
    ) & (~out["is_missing_llm_result"])

    out["corpus_label_12"] = "other"
    out.loc[out["is_review_pool_12"], "corpus_label_12"] = "review_pool"
    out.loc[out["is_core_maybe_12"], "corpus_label_12"] = "core_maybe"
    out.loc[out["is_core_broad_12"], "corpus_label_12"] = "core_broad"
    out.loc[out["is_core_strict_12"], "corpus_label_12"] = "core_strict"
    out.loc[out["is_missing_llm_result"], "corpus_label_12"] = "missing_llm_result"

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
        "corpus_label_12",
        "is_core_strict_12",
        "is_core_broad_12",
        "is_core_maybe_12",
        "is_review_pool_12",
        "is_missing_llm_result",
        "llm6_has_clear_main_protagonist",
        "llm6_protagonist_name",
        "llm6_protagonist_type",
        "llm6_protagonist_confidence_0_3",
        "primary_archetype_12",
        "secondary_archetype_12",
        "tertiary_archetype_12",
        "primary_archetype_12_is_valid",
        "original_shadow_antihero_present",
        "original_primary_was_shadow_antihero",
        "llm6_shadow_load_0_3",
        "shadow_load_category",
        "archetype_12_correction_method",
        "llm6_primary_archetype",
        "llm6_secondary_archetype",
        "llm6_tertiary_archetype",
        "llm6_archetype_confidence_0_3",
        "llm6_archetype_suitability_0_3",
        "llm6_player_projection_0_3",
        "llm6_narrative_complexity_0_3",
        "llm6_suggested_include_in_final_corpus",
        "llm6_needs_manual_review",
        "needs_manual_review_12",
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


def make_archetype_counts(df: pd.DataFrame, outdir: Path, col: str, filename: str) -> pd.DataFrame:
    rows = []

    subsets = {
        "all_with_llm": df[~df["is_missing_llm_result"]],
        "core_strict_12": df[df["is_core_strict_12"]],
        "core_broad_12": df[df["is_core_broad_12"]],
        "core_maybe_12": df[df["is_core_maybe_12"]],
        "review_pool_12": df[df["is_review_pool_12"]],
    }

    for subset_name, sub in subsets.items():
        vc = sub[col].fillna("<missing>").astype(str).value_counts(dropna=False)
        total = len(sub)
        for archetype, count in vc.items():
            rows.append({
                "subset": subset_name,
                "archetype": archetype,
                "count": int(count),
                "share": (float(count) / total) if total else 0.0,
            })

    result = pd.DataFrame(rows)
    result.to_csv(outdir / filename, index=False, encoding="utf-8-sig")
    return result


def make_shadow_counts(df: pd.DataFrame, outdir: Path) -> pd.DataFrame:
    rows = []
    for subset_name, sub in {
        "all_with_llm": df[~df["is_missing_llm_result"]],
        "core_strict_12": df[df["is_core_strict_12"]],
        "core_broad_12": df[df["is_core_broad_12"]],
        "core_maybe_12": df[df["is_core_maybe_12"]],
    }.items():
        total = len(sub)
        vc = sub["shadow_load_category"].fillna("<missing>").astype(str).value_counts(dropna=False)
        for cat, count in vc.items():
            rows.append({
                "subset": subset_name,
                "shadow_load_category": cat,
                "count": int(count),
                "share": (float(count) / total) if total else 0.0,
            })

    result = pd.DataFrame(rows)
    result.to_csv(outdir / "steam_shadow_dimension_counts_v001.csv", index=False, encoding="utf-8-sig")
    return result


def make_rank_bins(df: pd.DataFrame, outdir: Path) -> pd.DataFrame:
    if "rank_bin_5000" not in df.columns:
        return pd.DataFrame()

    grouped = (
        df.groupby("rank_bin_5000", dropna=False)
        .agg(
            rows=("appid", "count"),
            llm_results=("is_missing_llm_result", lambda x: int((~x).sum())),
            core_strict_12=("is_core_strict_12", "sum"),
            core_broad_12=("is_core_broad_12", "sum"),
            core_maybe_12=("is_core_maybe_12", "sum"),
            review_pool_12=("is_review_pool_12", "sum"),
            original_primary_shadow=("original_primary_was_shadow_antihero", "sum"),
        )
        .reset_index()
    )

    def sort_key(label: str) -> int:
        try:
            return int(str(label).split("-")[0])
        except Exception:
            return 10**12

    grouped["_sort"] = grouped["rank_bin_5000"].map(sort_key)
    grouped = grouped.sort_values("_sort").drop(columns=["_sort"])
    grouped.to_csv(outdir / "steam_rank_bins_12_v001.csv", index=False, encoding="utf-8-sig")
    return grouped


def write_readme(outdir: Path, summary: dict) -> None:
    text = f"""# Steam archetype final datasets: 12-archetype corrected v001

Generated by `steam_make_final_archetype_datasets_12_v001.py`.

## Why this version exists

The previous LLM taxonomy allowed `Shadow/Antihero` as an archetype. This is
not part of the classic 12-archetype framework used for the paper. In this
corrected version, `Shadow/Antihero` is removed from archetype counts and kept
only as a separate shadow/antihero dimension.

## Valid 12 archetypes

{", ".join(VALID_12)}

## Correction rule

If original `llm6_primary_archetype` is `Shadow/Antihero`, the script assigns
`primary_archetype_12` from the first valid 12-archetype in original secondary
or tertiary archetype. If none is available, the row becomes `Uncertain` and is
flagged for review.

Original shadow information is preserved in:

- `original_shadow_antihero_present`
- `original_primary_was_shadow_antihero`
- `llm6_shadow_load_0_3`
- `shadow_load_category`

## Main datasets

- `steam_analysis_ready_12_v001.csv` — full dataset with corrected 12-archetype fields.
- `steam_core_strict_12_v001.csv` — high-confidence clean analytical subset.
- `steam_core_broad_12_v001.csv` — protagonist=yes, include=yes, valid 12 primary.
- `steam_core_maybe_12_v001.csv` — protagonist=yes, include=yes/maybe, valid 12 primary.
- `steam_review_pool_12_v001.csv` — rows recommended for manual/agent review.
- `steam_missing_llm_results_12_v001.csv` — rows with missing LLM classification.
- `steam_shadow_reassigned_cases_12_v001.csv` — cases where original primary was Shadow/Antihero.

## Summary

- Total rows: {summary['rows_total']}
- LLM results: {summary['rows_with_llm_result']}
- Missing LLM results: {summary['rows_missing_llm_result']}
- Original primary Shadow/Antihero: {summary['original_primary_shadow_rows']}
- Shadow reassigned to valid 12 archetype: {summary['shadow_reassigned_to_valid_12_rows']}
- Shadow unresolved / review needed: {summary['shadow_unresolved_rows']}
- CORE_STRICT_12: {summary['core_strict_12_rows']}
- CORE_BROAD_12: {summary['core_broad_12_rows']}
- CORE_MAYBE_12: {summary['core_maybe_12_rows']}
- REVIEW_POOL_12: {summary['review_pool_12_rows']}
"""
    (outdir / "README_final_datasets_12_v001.md").write_text(text, encoding="utf-8")


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
        "llm6_secondary_archetype",
        "llm6_tertiary_archetype",
        "llm6_shadow_load_0_3",
    ])

    df = add_rank_bins(df)
    df = add_corrections(df)
    df = add_corpus_flags(df)

    cols = preferred_columns(df)
    analysis_ready = df[cols].copy()

    core_strict = analysis_ready[analysis_ready["is_core_strict_12"]].copy()
    core_broad = analysis_ready[analysis_ready["is_core_broad_12"]].copy()
    core_maybe = analysis_ready[analysis_ready["is_core_maybe_12"]].copy()
    review_pool = analysis_ready[analysis_ready["is_review_pool_12"]].copy()
    missing = analysis_ready[analysis_ready["is_missing_llm_result"]].copy()
    shadow_reassigned = analysis_ready[analysis_ready["original_primary_was_shadow_antihero"]].copy()

    analysis_ready.to_csv(outdir / "steam_analysis_ready_12_v001.csv", index=False, encoding="utf-8-sig")
    core_strict.to_csv(outdir / "steam_core_strict_12_v001.csv", index=False, encoding="utf-8-sig")
    core_broad.to_csv(outdir / "steam_core_broad_12_v001.csv", index=False, encoding="utf-8-sig")
    core_maybe.to_csv(outdir / "steam_core_maybe_12_v001.csv", index=False, encoding="utf-8-sig")
    review_pool.to_csv(outdir / "steam_review_pool_12_v001.csv", index=False, encoding="utf-8-sig")
    missing.to_csv(outdir / "steam_missing_llm_results_12_v001.csv", index=False, encoding="utf-8-sig")
    shadow_reassigned.to_csv(outdir / "steam_shadow_reassigned_cases_12_v001.csv", index=False, encoding="utf-8-sig")

    make_archetype_counts(analysis_ready, outdir, "primary_archetype_12", "steam_primary_archetype_12_counts_v001.csv")
    make_archetype_counts(analysis_ready, outdir, "secondary_archetype_12", "steam_secondary_archetype_12_counts_v001.csv")
    make_shadow_counts(analysis_ready, outdir)
    make_rank_bins(analysis_ready, outdir)

    model_counts = (
        analysis_ready["llm6_model_used"]
        .fillna("<missing>")
        .astype(str)
        .value_counts(dropna=False)
        .rename_axis("llm6_model_used")
        .reset_index(name="count")
    )
    model_counts.to_csv(outdir / "steam_model_counts_12_v001.csv", index=False, encoding="utf-8-sig")

    orig_primary = norm_str_series(analysis_ready["llm6_primary_archetype"])
    original_primary_shadow_rows = int(orig_primary.eq(SHADOW_VALUE).sum())
    shadow_reassigned_to_valid = int(
        analysis_ready["original_primary_was_shadow_antihero"].fillna(False).astype(bool)
        .where(analysis_ready["primary_archetype_12_is_valid"].fillna(False).astype(bool), False)
        .sum()
    )
    shadow_unresolved = int(
        analysis_ready["original_primary_was_shadow_antihero"].fillna(False).astype(bool)
        .where(~analysis_ready["primary_archetype_12_is_valid"].fillna(False).astype(bool), False)
        .sum()
    )

    summary = {
        "input_csv": str(input_path),
        "output_dir": str(outdir),
        "valid_12_archetypes": VALID_12,
        "rows_total": int(len(analysis_ready)),
        "rows_with_llm_result": int((~analysis_ready["is_missing_llm_result"]).sum()),
        "rows_missing_llm_result": int(analysis_ready["is_missing_llm_result"].sum()),
        "original_primary_shadow_rows": original_primary_shadow_rows,
        "shadow_reassigned_to_valid_12_rows": shadow_reassigned_to_valid,
        "shadow_unresolved_rows": shadow_unresolved,
        "core_strict_12_rows": int(len(core_strict)),
        "core_broad_12_rows": int(len(core_broad)),
        "core_maybe_12_rows": int(len(core_maybe)),
        "review_pool_12_rows": int(len(review_pool)),
        "has_clear_main_protagonist_counts": counts_dict(analysis_ready["llm6_has_clear_main_protagonist"]),
        "include_counts": counts_dict(analysis_ready["llm6_suggested_include_in_final_corpus"]),
        "primary_archetype_12_counts_all_with_llm": counts_dict(
            analysis_ready.loc[~analysis_ready["is_missing_llm_result"], "primary_archetype_12"]
        ),
        "primary_archetype_12_counts_core_strict": counts_dict(core_strict["primary_archetype_12"]),
        "shadow_load_category_counts_all_with_llm": counts_dict(
            analysis_ready.loc[~analysis_ready["is_missing_llm_result"], "shadow_load_category"]
        ),
    }

    (outdir / "steam_dataset_summary_12_v001.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_readme(outdir, summary)

    print("\nCreated 12-archetype corrected datasets:")
    print(f"  {outdir / 'steam_analysis_ready_12_v001.csv'} ({len(analysis_ready)} rows)")
    print(f"  {outdir / 'steam_core_strict_12_v001.csv'} ({len(core_strict)} rows)")
    print(f"  {outdir / 'steam_core_broad_12_v001.csv'} ({len(core_broad)} rows)")
    print(f"  {outdir / 'steam_core_maybe_12_v001.csv'} ({len(core_maybe)} rows)")
    print(f"  {outdir / 'steam_review_pool_12_v001.csv'} ({len(review_pool)} rows)")
    print(f"  {outdir / 'steam_shadow_reassigned_cases_12_v001.csv'} ({len(shadow_reassigned)} rows)")

    print("\nSummary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
