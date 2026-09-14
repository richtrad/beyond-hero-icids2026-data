#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_merge_release_years_from_cache_12_v002.py

Fix-up script after the v001 release-year fetch crashed during human-readable export.

It DOES NOT fetch anything. It only reads the already created cache:
  steam_bulk_outputs/steam_release_dates_cache_v001.csv

and creates new v002 outputs:
  steam_bulk_outputs/release_years_12_v002/

Run:
  python steam_merge_release_years_from_cache_12_v002.py

Optional:
  python steam_merge_release_years_from_cache_12_v002.py --exclusive
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_CACHE = Path("steam_bulk_outputs/steam_release_dates_cache_v001.csv")
DEFAULT_ANALYSIS = Path("steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv")
DEFAULT_GROUP_DIR = Path("steam_bulk_outputs/three_groups_12_v001")
DEFAULT_OUTPUT_DIR = Path("steam_bulk_outputs/release_years_12_v002")

STANDARD_GROUPS = [
    ("group_1_core_strict_12_v001.csv", "group_1_core_strict_12_with_year_v002.csv", "human_readable_group_1_core_strict_12_with_year_v002.csv", "CORE_STRICT"),
    ("group_2_core_broad_12_v001.csv", "group_2_core_broad_12_with_year_v002.csv", "human_readable_group_2_core_broad_12_with_year_v002.csv", "CORE_BROAD"),
    ("group_3_review_pool_12_v001.csv", "group_3_review_pool_12_with_year_v002.csv", "human_readable_group_3_review_pool_12_with_year_v002.csv", "REVIEW_POOL"),
]

EXCLUSIVE_GROUPS = [
    ("exclusive_group_1_core_strict_12_v001.csv", "exclusive_group_1_core_strict_12_with_year_v002.csv", "human_readable_exclusive_group_1_core_strict_12_with_year_v002.csv", "EXCLUSIVE_CORE_STRICT"),
    ("exclusive_group_2_core_broad_nonreview_12_v001.csv", "exclusive_group_2_core_broad_nonreview_12_with_year_v002.csv", "human_readable_exclusive_group_2_core_broad_nonreview_12_with_year_v002.csv", "EXCLUSIVE_CORE_BROAD_NONREVIEW"),
    ("exclusive_group_3_review_pool_noncorestrict_12_v001.csv", "exclusive_group_3_review_pool_noncorestrict_12_with_year_v002.csv", "human_readable_exclusive_group_3_review_pool_noncorestrict_12_with_year_v002.csv", "EXCLUSIVE_REVIEW_POOL_NONCORESTRICT"),
]


def normalize_appid(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def read_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    cache = pd.read_csv(path, dtype={"appid": str}, low_memory=False)
    if "appid" not in cache.columns:
        raise RuntimeError(f"Cache has no appid column: {path}")
    cache["appid"] = cache["appid"].map(normalize_appid)
    cache = cache.drop_duplicates(subset=["appid"], keep="last")
    if "release_year" in cache.columns:
        cache["release_year"] = pd.to_numeric(cache["release_year"], errors="coerce").astype("Int64")
    else:
        cache["release_year"] = pd.Series([pd.NA] * len(cache), dtype="Int64")
    return cache


def merge_years(df: pd.DataFrame, cache: pd.DataFrame) -> pd.DataFrame:
    if "appid" not in df.columns:
        raise RuntimeError("Input dataset has no appid column.")
    out = df.copy()
    out["appid"] = out["appid"].map(normalize_appid)

    cols = [
        "release_date_raw",
        "release_year",
        "coming_soon",
        "steam_success",
        "fetch_status",
        "error",
        "fetched_at",
    ]
    for c in cols:
        if c in out.columns:
            out = out.drop(columns=[c])

    cache_cols = ["appid"] + [c for c in cols if c in cache.columns]
    out = out.merge(cache[cache_cols], on="appid", how="left")
    out["release_year"] = pd.to_numeric(out["release_year"], errors="coerce").astype("Int64")
    return out


def cred(df: pd.DataFrame) -> pd.Series:
    def n(col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series([0.0] * len(df), index=df.index)
        return pd.to_numeric(df[col], errors="coerce").fillna(0).clip(0, 3) / 3.0
    return ((n("llm6_protagonist_confidence_0_3") + n("llm6_archetype_confidence_0_3") + n("llm6_archetype_suitability_0_3")) / 3.0).round(3)


def year_as_text(s: pd.Series) -> pd.Series:
    # Bugfix against Pandas nullable Int64: convert to string dtype before fillna("")
    return pd.to_numeric(s, errors="coerce").astype("Int64").astype("string").fillna("")


def human_readable(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["name", "release_year", "llm6_protagonist_name", "primary_archetype_12", "secondary_archetype_12", "tertiary_archetype_12"]:
        if col not in df.columns:
            df[col] = ""
    return pd.DataFrame({
        "jmeno hry": df["name"].fillna("").astype(str),
        "rok vydani": year_as_text(df["release_year"]),
        "jmeno postavy": df["llm6_protagonist_name"].fillna("").astype(str),
        "primarni archetyp": df["primary_archetype_12"].fillna("").astype(str),
        "sekundarni archetyp": df["secondary_archetype_12"].fillna("").astype(str),
        "tercialni archetyp": df["tertiary_archetype_12"].fillna("").astype(str),
        "věrohodnost odhadu na škále 0 až 1": cred(df),
    })


def year_counts(df: pd.DataFrame, label: str) -> pd.DataFrame:
    if "release_year" not in df.columns:
        return pd.DataFrame(columns=["group", "release_year", "count"])
    y = pd.to_numeric(df["release_year"], errors="coerce").astype("Int64")
    out = y.groupby(y, dropna=False).size().reset_index(name="count").rename(columns={"release_year": "release_year"})
    out.insert(0, "group", label)
    return out


def process_file(input_path: Path, output_path: Path, human_path: Path | None, cache: pd.DataFrame, label: str) -> tuple[int, pd.DataFrame]:
    if not input_path.exists():
        print(f"WARNING: missing, skipping: {input_path}")
        return 0, pd.DataFrame(columns=["group", "release_year", "count"])

    print(f"Merging: {input_path}")
    df = pd.read_csv(input_path, dtype={"appid": str}, low_memory=False)
    merged = merge_years(df, cache)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {output_path} ({len(merged)} rows)")

    if human_path is not None:
        hr = human_readable(merged)
        hr.to_csv(human_path, index=False, encoding="utf-8-sig")
        print(f"Saved human-readable: {human_path} ({len(hr)} rows)")

    return len(merged), year_counts(merged, label)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--analysis", default=str(DEFAULT_ANALYSIS))
    ap.add_argument("--group-dir", default=str(DEFAULT_GROUP_DIR))
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    ap.add_argument("--exclusive", action="store_true")
    args = ap.parse_args()

    cache_path = Path(args.cache)
    analysis_path = Path(args.analysis)
    group_dir = Path(args.group_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = read_cache(cache_path)
    cache_years = int(cache["release_year"].notna().sum())
    cache_errors = int(cache["fetch_status"].fillna("").astype(str).eq("error").sum()) if "fetch_status" in cache.columns else 0

    all_counts = []

    rows, counts = process_file(
        analysis_path,
        output_dir / "steam_analysis_ready_12_with_year_v002.csv",
        None,
        cache,
        "ANALYSIS_READY_12",
    )
    all_counts.append(counts)

    for inp, outp, hrp, label in STANDARD_GROUPS:
        _, counts = process_file(group_dir / inp, output_dir / outp, output_dir / hrp, cache, label)
        all_counts.append(counts)

    if args.exclusive:
        for inp, outp, hrp, label in EXCLUSIVE_GROUPS:
            _, counts = process_file(group_dir / inp, output_dir / outp, output_dir / hrp, cache, label)
            all_counts.append(counts)

    counts_df = pd.concat(all_counts, ignore_index=True)
    counts_path = output_dir / "release_year_counts_by_group_12_v002.csv"
    counts_df.to_csv(counts_path, index=False, encoding="utf-8-sig")
    print(f"Saved year counts: {counts_path}")

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "cache_csv": str(cache_path),
        "cache_rows": int(len(cache)),
        "cache_rows_with_release_year": cache_years,
        "cache_error_rows": cache_errors,
        "analysis_input": str(analysis_path),
        "group_dir": str(group_dir),
        "output_dir": str(output_dir),
        "analysis_rows": int(rows),
        "processed_exclusive_groups": bool(args.exclusive),
        "note": "No fetching. Existing cache only. release_year is Steam Store release year, not necessarily original release year."
    }
    (output_dir / "release_year_merge_summary_v002.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# Release years merged into 12-archetype datasets v002

This script performs no network calls. It only reads the existing cache:

`{cache_path}`

## Outputs

- `steam_analysis_ready_12_with_year_v002.csv`
- `group_1_core_strict_12_with_year_v002.csv`
- `group_2_core_broad_12_with_year_v002.csv`
- `group_3_review_pool_12_with_year_v002.csv`
- `human_readable_group_1_core_strict_12_with_year_v002.csv`
- `human_readable_group_2_core_broad_12_with_year_v002.csv`
- `human_readable_group_3_review_pool_12_with_year_v002.csv`
- `release_year_counts_by_group_12_v002.csv`

## Cache summary

- Cache rows: {len(cache)}
- Rows with release year: {cache_years}
- Error rows in cache: {cache_errors}

## Methodological note

`release_year` is the Steam Store release year, not necessarily the original release year of the game.
"""
    (output_dir / "README_release_years_12_v002.md").write_text(readme, encoding="utf-8")

    print("\nDone.")
    print(f"Summary: {output_dir / 'release_year_merge_summary_v002.json'}")
    print(f"README:  {output_dir / 'README_release_years_12_v002.md'}")


if __name__ == "__main__":
    main()
