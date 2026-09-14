#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
igdb_merge_candidate_catalogs_v001.py

Merge IGDB pre-2005 and post-2004 candidate catalogs into one master catalog.

No OpenAI calls. No LLM annotation.

Default inputs:
  igdb_outputs/pre2005_candidates_v002/igdb_pre2005_raw_games_v002.csv
  igdb_outputs/pre2005_candidates_v002/igdb_pre2005_broad_candidates_v002.csv
  igdb_outputs/pre2005_candidates_v002/igdb_pre2005_low_priority_review_v002.csv

  igdb_outputs/post2004_candidates_v001/igdb_post2004_raw_games_v001.csv
  igdb_outputs/post2004_candidates_v001/igdb_post2004_broad_candidates_v001.csv
  igdb_outputs/post2004_candidates_v001/igdb_post2004_low_priority_review_v001.csv

Default output:
  igdb_outputs/master_candidates_v001/

Overwrite policy:
- Refuses to overwrite a completed output folder by default.
- Use --overwrite only intentionally.
- Never touches source folders.

Default analysis max year:
  2025

Reason:
  2026 is incomplete and includes future/unreleased titles. It is kept in a
  separate excluded file by default.

Outputs:
  igdb_master_raw_all_years_v001.csv
  igdb_master_broad_all_years_v001.csv
  igdb_master_low_priority_all_years_v001.csv

  igdb_master_raw_analysis_years_v001.csv
  igdb_master_broad_analysis_years_v001.csv
  igdb_master_low_priority_analysis_years_v001.csv
  igdb_master_excluded_after_max_year_v001.csv

  igdb_master_year_counts_v001.csv
  igdb_master_decade_counts_v001.csv
  igdb_master_examples_by_year_v001.csv
  igdb_master_summary_v001.json
  README_igdb_master_candidates_v001.md
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_PRE_DIR = Path("igdb_outputs/pre2005_candidates_v002")
DEFAULT_POST_DIR = Path("igdb_outputs/post2004_candidates_v001")
DEFAULT_OUTDIR = Path("igdb_outputs/master_candidates_v001")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype={"igdb_id": str}, low_memory=False)


def safe_prepare_outdir(outdir: Path, overwrite: bool) -> None:
    completed_marker = outdir / "_COMPLETED_master_candidates_v001.txt"
    if outdir.exists() and completed_marker.exists() and not overwrite:
        raise RuntimeError(
            f"Output folder already contains completed results: {outdir}\n"
            f"Use --overwrite to rebuild it or --outdir with a new folder."
        )
    if outdir.exists() and overwrite:
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)


def add_source(df: pd.DataFrame, source_block: str, source_pool: str) -> pd.DataFrame:
    out = df.copy()
    out["source_block"] = source_block
    out["source_pool"] = source_pool
    return out


def normalize_bool_series(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(str).str.lower().isin(["true", "1", "yes"])


def merge_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True, sort=False)

    # Prefer records from broad pool over raw/low if duplicate igdb_id appears.
    pool_priority = {
        "broad": 0,
        "raw": 1,
        "low_priority": 2,
    }
    df["_pool_priority"] = df["source_pool"].map(pool_priority).fillna(9)

    if "visibility_count_score" in df.columns:
        df["_visibility_sort"] = pd.to_numeric(df["visibility_count_score"], errors="coerce").fillna(0)
    else:
        df["_visibility_sort"] = 0

    if "thematic_fit_score" in df.columns:
        df["_fit_sort"] = pd.to_numeric(df["thematic_fit_score"], errors="coerce").fillna(0)
    else:
        df["_fit_sort"] = 0

    df = df.sort_values(["igdb_id", "_pool_priority", "_visibility_sort", "_fit_sort"], ascending=[True, True, False, False])
    df = df.drop_duplicates(subset=["igdb_id"], keep="first").copy()
    df = df.drop(columns=[c for c in ["_pool_priority", "_visibility_sort", "_fit_sort"] if c in df.columns])

    if "original_release_year" in df.columns:
        df["original_release_year_num"] = pd.to_numeric(df["original_release_year"], errors="coerce").astype("Int64")
    else:
        df["original_release_year_num"] = pd.Series(dtype="Int64")

    if "visibility_count_score" in df.columns:
        df["visibility_count_score"] = pd.to_numeric(df["visibility_count_score"], errors="coerce").fillna(0)
    else:
        df["visibility_count_score"] = 0

    if "thematic_fit_score" in df.columns:
        df["thematic_fit_score"] = pd.to_numeric(df["thematic_fit_score"], errors="coerce").fillna(0)
    else:
        df["thematic_fit_score"] = 0

    if "broad_candidate_for_archetype_annotation" in df.columns:
        df["broad_candidate_for_archetype_annotation"] = normalize_bool_series(df["broad_candidate_for_archetype_annotation"])
    else:
        df["broad_candidate_for_archetype_annotation"] = False

    return df.sort_values(
        ["original_release_year_num", "broad_candidate_for_archetype_annotation", "visibility_count_score", "thematic_fit_score", "name"],
        ascending=[True, False, False, False, True],
    )


def filter_analysis_years(df: pd.DataFrame, max_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df.copy(), df.copy()
    year = pd.to_numeric(df["original_release_year_num"], errors="coerce")
    analysis = df[year.notna() & (year <= max_year)].copy()
    excluded = df[year.notna() & (year > max_year)].copy()
    return analysis, excluded


def write_counts(df: pd.DataFrame, outdir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        year_counts = pd.DataFrame(columns=["original_release_year", "raw_count", "broad_candidate_count"])
        decade_counts = pd.DataFrame(columns=["decade", "raw_count", "broad_candidate_count"])
    else:
        work = df.copy()
        work["original_release_year"] = work["original_release_year_num"]

        year_counts = work.groupby("original_release_year", dropna=False).size().reset_index(name="raw_count")
        broad = work[work["broad_candidate_for_archetype_annotation"]]
        broad_counts = broad.groupby("original_release_year", dropna=False).size().reset_index(name="broad_candidate_count")
        year_counts = year_counts.merge(broad_counts, on="original_release_year", how="left").fillna(0)
        year_counts["broad_candidate_count"] = year_counts["broad_candidate_count"].astype(int)

        decade_counts = work.groupby("decade", dropna=False).size().reset_index(name="raw_count")
        broad_decade = broad.groupby("decade", dropna=False).size().reset_index(name="broad_candidate_count")
        decade_counts = decade_counts.merge(broad_decade, on="decade", how="left").fillna(0)
        decade_counts["broad_candidate_count"] = decade_counts["broad_candidate_count"].astype(int)

    year_counts.to_csv(outdir / "igdb_master_year_counts_v001.csv", index=False, encoding="utf-8-sig")
    decade_counts.to_csv(outdir / "igdb_master_decade_counts_v001.csv", index=False, encoding="utf-8-sig")
    return year_counts, decade_counts


def write_examples(df: pd.DataFrame, outdir: Path, examples_per_year: int) -> pd.DataFrame:
    cols = [
        "original_release_year", "example_no", "igdb_id", "name", "game_type",
        "genres", "themes", "game_modes", "platforms",
        "thematic_fit_score", "visibility_count_score",
        "broad_candidate_for_archetype_annotation", "source_block"
    ]
    if df.empty:
        examples = pd.DataFrame(columns=cols)
        examples.to_csv(outdir / "igdb_master_examples_by_year_v001.csv", index=False, encoding="utf-8-sig")
        return examples

    work = df.copy().sort_values(
        ["original_release_year_num", "broad_candidate_for_archetype_annotation", "visibility_count_score", "thematic_fit_score", "name"],
        ascending=[True, False, False, False, True],
    )

    rows = []
    for year, sub in work.groupby("original_release_year_num", dropna=False):
        sub = sub.head(examples_per_year)
        for i, (_, row) in enumerate(sub.iterrows(), start=1):
            rows.append({
                "original_release_year": year,
                "example_no": i,
                "igdb_id": row.get("igdb_id", ""),
                "name": row.get("name", ""),
                "game_type": row.get("game_type", ""),
                "genres": row.get("genres", ""),
                "themes": row.get("themes", ""),
                "game_modes": row.get("game_modes", ""),
                "platforms": row.get("platforms", ""),
                "thematic_fit_score": row.get("thematic_fit_score", ""),
                "visibility_count_score": row.get("visibility_count_score", ""),
                "broad_candidate_for_archetype_annotation": row.get("broad_candidate_for_archetype_annotation", ""),
                "source_block": row.get("source_block", ""),
            })

    examples = pd.DataFrame(rows)
    examples.to_csv(outdir / "igdb_master_examples_by_year_v001.csv", index=False, encoding="utf-8-sig")
    return examples


def print_summary(master_raw: pd.DataFrame, master_broad: pd.DataFrame, analysis_raw: pd.DataFrame, analysis_broad: pd.DataFrame, excluded: pd.DataFrame, year_counts: pd.DataFrame) -> None:
    print()
    print("=" * 100)
    print("IGDB MASTER CANDIDATE CATALOG V001")
    print("=" * 100)
    print(f"All years raw rows:        {len(master_raw):>8}")
    print(f"All years broad rows:      {len(master_broad):>8}")
    print(f"Analysis years raw rows:   {len(analysis_raw):>8}")
    print(f"Analysis years broad rows: {len(analysis_broad):>8}")
    print(f"Excluded after max year:   {len(excluded):>8}")
    print()

    if not year_counts.empty:
        print("COUNTS BY YEAR")
        print("-" * 100)
        for _, row in year_counts.iterrows():
            print(f"{str(row['original_release_year']):>6}: {int(row['raw_count']):>7} raw, {int(row['broad_candidate_count']):>7} broad")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-dir", default=str(DEFAULT_PRE_DIR))
    parser.add_argument("--post-dir", default=str(DEFAULT_POST_DIR))
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    parser.add_argument("--analysis-max-year", type=int, default=2025)
    parser.add_argument("--examples-per-year", type=int, default=15)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    pre_dir = Path(args.pre_dir)
    post_dir = Path(args.post_dir)
    outdir = Path(args.outdir)
    safe_prepare_outdir(outdir, args.overwrite)

    pre_raw = add_source(read_csv_safe(pre_dir / "igdb_pre2005_raw_games_v002.csv"), "pre2005", "raw")
    pre_broad = add_source(read_csv_safe(pre_dir / "igdb_pre2005_broad_candidates_v002.csv"), "pre2005", "broad")
    pre_low = add_source(read_csv_safe(pre_dir / "igdb_pre2005_low_priority_review_v002.csv"), "pre2005", "low_priority")

    post_raw = add_source(read_csv_safe(post_dir / "igdb_post2004_raw_games_v001.csv"), "post2004", "raw")
    post_broad = add_source(read_csv_safe(post_dir / "igdb_post2004_broad_candidates_v001.csv"), "post2004", "broad")
    post_low = add_source(read_csv_safe(post_dir / "igdb_post2004_low_priority_review_v001.csv"), "post2004", "low_priority")

    master_raw = merge_frames([pre_raw, post_raw])
    master_broad = merge_frames([pre_broad, post_broad])
    master_low = merge_frames([pre_low, post_low])

    analysis_raw, excluded_raw = filter_analysis_years(master_raw, args.analysis_max_year)
    analysis_broad, excluded_broad = filter_analysis_years(master_broad, args.analysis_max_year)
    analysis_low, excluded_low = filter_analysis_years(master_low, args.analysis_max_year)

    # Combined excluded is useful mainly from raw, but include pool marker.
    excluded_all = excluded_raw.copy()

    master_raw.to_csv(outdir / "igdb_master_raw_all_years_v001.csv", index=False, encoding="utf-8-sig")
    master_broad.to_csv(outdir / "igdb_master_broad_all_years_v001.csv", index=False, encoding="utf-8-sig")
    master_low.to_csv(outdir / "igdb_master_low_priority_all_years_v001.csv", index=False, encoding="utf-8-sig")

    analysis_raw.to_csv(outdir / "igdb_master_raw_analysis_years_v001.csv", index=False, encoding="utf-8-sig")
    analysis_broad.to_csv(outdir / "igdb_master_broad_analysis_years_v001.csv", index=False, encoding="utf-8-sig")
    analysis_low.to_csv(outdir / "igdb_master_low_priority_analysis_years_v001.csv", index=False, encoding="utf-8-sig")
    excluded_all.to_csv(outdir / "igdb_master_excluded_after_max_year_v001.csv", index=False, encoding="utf-8-sig")

    year_counts, decade_counts = write_counts(analysis_raw, outdir)
    examples = write_examples(analysis_raw, outdir, args.examples_per_year)

    summary = {
        "created_at": now_iso(),
        "analysis_max_year": args.analysis_max_year,
        "inputs": {
            "pre_dir": str(pre_dir),
            "post_dir": str(post_dir),
        },
        "rows": {
            "master_raw_all_years": int(len(master_raw)),
            "master_broad_all_years": int(len(master_broad)),
            "master_low_priority_all_years": int(len(master_low)),
            "analysis_raw": int(len(analysis_raw)),
            "analysis_broad": int(len(analysis_broad)),
            "analysis_low_priority": int(len(analysis_low)),
            "excluded_after_max_year_raw": int(len(excluded_raw)),
        },
        "outputs": {
            "master_raw_all_years": str(outdir / "igdb_master_raw_all_years_v001.csv"),
            "master_broad_all_years": str(outdir / "igdb_master_broad_all_years_v001.csv"),
            "analysis_raw": str(outdir / "igdb_master_raw_analysis_years_v001.csv"),
            "analysis_broad": str(outdir / "igdb_master_broad_analysis_years_v001.csv"),
            "year_counts": str(outdir / "igdb_master_year_counts_v001.csv"),
            "decade_counts": str(outdir / "igdb_master_decade_counts_v001.csv"),
            "examples_by_year": str(outdir / "igdb_master_examples_by_year_v001.csv"),
        },
        "note": "No LLM annotation. 2026+ excluded from analysis by default because the year is incomplete and may contain future/unreleased games."
    }
    (outdir / "igdb_master_summary_v001.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# IGDB master candidate catalog v001

Merged candidate catalog from:

- `pre2005_candidates_v002`
- `post2004_candidates_v001`

## Important

- No LLM annotation is performed here.
- `original_release_year` comes from IGDB `first_release_date`.
- All-year files retain all fetched years.
- Analysis-year files keep only years `<= {args.analysis_max_year}`.
- Future/incomplete years are written separately to `igdb_master_excluded_after_max_year_v001.csv`.

## Row counts

- Master raw all years: {len(master_raw)}
- Master broad all years: {len(master_broad)}
- Analysis raw: {len(analysis_raw)}
- Analysis broad: {len(analysis_broad)}
- Excluded after max year: {len(excluded_raw)}

## Recommended next input for stratified candidate selection

Use:

`igdb_master_broad_analysis_years_v001.csv`

Then build a smaller stratified candidate set per decade/year before running LLM protagonist and archetype annotation.
"""
    (outdir / "README_igdb_master_candidates_v001.md").write_text(readme, encoding="utf-8")

    (outdir / "_COMPLETED_master_candidates_v001.txt").write_text(
        f"Completed at {now_iso()}\nAnalysis max year: {args.analysis_max_year}\nAnalysis broad rows: {len(analysis_broad)}\n",
        encoding="utf-8",
    )

    print_summary(master_raw, master_broad, analysis_raw, analysis_broad, excluded_raw, year_counts)

    print("\nSaved:")
    for name in [
        "igdb_master_raw_all_years_v001.csv",
        "igdb_master_broad_all_years_v001.csv",
        "igdb_master_raw_analysis_years_v001.csv",
        "igdb_master_broad_analysis_years_v001.csv",
        "igdb_master_year_counts_v001.csv",
        "igdb_master_examples_by_year_v001.csv",
        "igdb_master_summary_v001.json",
        "_COMPLETED_master_candidates_v001.txt",
    ]:
        print(f"  {outdir / name}")


if __name__ == "__main__":
    main()
