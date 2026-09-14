#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_year_overview_12_v001.py

Simple first-pass year analysis for the corrected 12-archetype Steam dataset.

It counts games per Steam release year and prints/saves 10 example games from
each year for quick human inspection.

Default inputs, in priority order:
  steam_bulk_outputs/release_years_12_v002/steam_analysis_ready_12_with_year_v002.csv
  steam_bulk_outputs/release_years_12_v001/steam_analysis_ready_12_with_year_v001.csv

If --groups is enabled, it also tries to process:
  group_1_core_strict_12_with_year_v002.csv
  group_2_core_broad_12_with_year_v002.csv
  group_3_review_pool_12_with_year_v002.csv
or the v001 equivalents.

Default output directory:
  steam_bulk_outputs/year_overview_12_v001/

Outputs:
  year_counts_all_sources_12_v001.csv
  year_examples_10_per_year_all_sources_12_v001.csv
  year_overview_all_sources_12_v001.md
  year_overview_summary_12_v001.json

No network calls. No API calls. No money spent.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_OUTPUT_DIR = Path("steam_bulk_outputs/year_overview_12_v001")

ANALYSIS_CANDIDATES = [
    Path("steam_bulk_outputs/release_years_12_v002/steam_analysis_ready_12_with_year_v002.csv"),
    Path("steam_bulk_outputs/release_years_12_v001/steam_analysis_ready_12_with_year_v001.csv"),
]

GROUP_CANDIDATES = {
    "CORE_STRICT": [
        Path("steam_bulk_outputs/release_years_12_v002/group_1_core_strict_12_with_year_v002.csv"),
        Path("steam_bulk_outputs/release_years_12_v001/group_1_core_strict_12_with_year_v001.csv"),
    ],
    "CORE_BROAD": [
        Path("steam_bulk_outputs/release_years_12_v002/group_2_core_broad_12_with_year_v002.csv"),
        Path("steam_bulk_outputs/release_years_12_v001/group_2_core_broad_12_with_year_v001.csv"),
    ],
    "REVIEW_POOL": [
        Path("steam_bulk_outputs/release_years_12_v002/group_3_review_pool_12_with_year_v002.csv"),
        Path("steam_bulk_outputs/release_years_12_v001/group_3_review_pool_12_with_year_v001.csv"),
    ],
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def normalize_year_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def release_year_label(s: pd.Series) -> pd.Series:
    return normalize_year_series(s).astype("string").fillna("<missing>")


def numeric_col(df: pd.DataFrame, col: str, default=0) -> pd.Series:
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def credibility_0_1(df: pd.DataFrame) -> pd.Series:
    def n(col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series([0.0] * len(df), index=df.index)
        return pd.to_numeric(df[col], errors="coerce").fillna(0).clip(0, 3) / 3.0

    return ((n("llm6_protagonist_confidence_0_3") +
             n("llm6_archetype_confidence_0_3") +
             n("llm6_archetype_suitability_0_3")) / 3.0).round(3)


def sort_for_examples(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Prefer selection_rank because it represents the original popularity/visibility order.
    if "selection_rank" in out.columns:
        out["_sort_rank"] = pd.to_numeric(out["selection_rank"], errors="coerce").fillna(10**12)
    elif "total_ratings_pos_neg" in out.columns:
        out["_sort_rank"] = -pd.to_numeric(out["total_ratings_pos_neg"], errors="coerce").fillna(0)
    else:
        out["_sort_rank"] = range(len(out))

    if "name" in out.columns:
        out["_sort_name"] = out["name"].fillna("").astype(str)
    else:
        out["_sort_name"] = ""

    return out.sort_values(["_sort_rank", "_sort_name"], ascending=[True, True])


def safe_col(df: pd.DataFrame, col: str, default="") -> pd.Series:
    if col in df.columns:
        return df[col].fillna("").astype(str)
    return pd.Series([default] * len(df), index=df.index)


def analyze_source(df: pd.DataFrame, source_label: str, examples_per_year: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if "release_year" not in df.columns:
        raise RuntimeError(f"{source_label}: input file has no release_year column.")

    work = df.copy()
    work["release_year_num"] = normalize_year_series(work["release_year"])
    work["release_year_label"] = release_year_label(work["release_year"])

    total = len(work)
    with_year = int(work["release_year_num"].notna().sum())
    missing_year = int(work["release_year_num"].isna().sum())

    counts = (
        work.groupby("release_year_label", dropna=False)
        .size()
        .reset_index(name="count")
    )
    counts.insert(0, "source", source_label)
    counts["share"] = (counts["count"] / total).round(6) if total else 0

    def year_sort_key(label: str) -> int:
        if str(label).isdigit():
            return int(label)
        return 999999

    counts["_sort_year"] = counts["release_year_label"].map(year_sort_key)
    counts = counts.sort_values("_sort_year").drop(columns=["_sort_year"])

    examples_rows = []
    sorted_work = sort_for_examples(work)

    for year_label, sub in sorted_work.groupby("release_year_label", dropna=False, sort=False):
        sub = sub.head(examples_per_year).copy()
        sub = sub.reset_index(drop=True)

        for i, row in sub.iterrows():
            examples_rows.append({
                "source": source_label,
                "release_year": year_label,
                "example_no": i + 1,
                "selection_rank": row.get("selection_rank", ""),
                "appid": row.get("appid", ""),
                "name": row.get("name", ""),
                "release_date_raw": row.get("release_date_raw", ""),
                "total_ratings_pos_neg": row.get("total_ratings_pos_neg", ""),
                "positive_ratio": row.get("positive_ratio", ""),
                "jmeno_postavy": row.get("llm6_protagonist_name", ""),
                "primarni_archetyp_12": row.get("primary_archetype_12", ""),
                "sekundarni_archetyp_12": row.get("secondary_archetype_12", ""),
                "tercialni_archetyp_12": row.get("tertiary_archetype_12", ""),
                "verohodnost_0_1": credibility_0_1(pd.DataFrame([row])).iloc[0],
            })

    examples = pd.DataFrame(examples_rows)

    summary = {
        "source": source_label,
        "rows_total": int(total),
        "rows_with_release_year": int(with_year),
        "rows_missing_release_year": int(missing_year),
        "min_release_year": int(work["release_year_num"].min()) if with_year else None,
        "max_release_year": int(work["release_year_num"].max()) if with_year else None,
    }

    return counts, examples, summary


def write_markdown(path: Path, summaries: list[dict], counts: pd.DataFrame, examples: pd.DataFrame) -> None:
    lines = []
    lines.append("# Steam year overview, 12-archetype dataset")
    lines.append("")
    lines.append(f"Generated: `{now_iso()}`")
    lines.append("")
    lines.append("Methodological note: `release_year` is the Steam Store release year, not necessarily the original release year of the game.")
    lines.append("")

    for summary in summaries:
        src = summary["source"]
        lines.append(f"## {src}")
        lines.append("")
        lines.append(f"- Rows total: **{summary['rows_total']}**")
        lines.append(f"- Rows with release year: **{summary['rows_with_release_year']}**")
        lines.append(f"- Rows missing release year: **{summary['rows_missing_release_year']}**")
        lines.append(f"- Year range: **{summary['min_release_year']}–{summary['max_release_year']}**")
        lines.append("")

        sub_counts = counts[counts["source"] == src].copy()
        sub_counts_no_missing = sub_counts[sub_counts["release_year_label"] != "<missing>"].copy()
        top_years = sub_counts_no_missing.sort_values("count", ascending=False).head(10)

        lines.append("### Top years by number of games")
        lines.append("")
        lines.append("| Year | Count | Share |")
        lines.append("|---:|---:|---:|")
        for _, row in top_years.iterrows():
            lines.append(f"| {row['release_year_label']} | {int(row['count'])} | {float(row['share']):.3%} |")
        lines.append("")

        lines.append("### 10 example games per year")
        lines.append("")
        sub_examples = examples[examples["source"] == src].copy()
        # Put real years first, missing last.
        year_labels = list(sub_counts["release_year_label"])
        year_labels = sorted(
            year_labels,
            key=lambda x: int(x) if str(x).isdigit() else 999999
        )

        for y in year_labels:
            ey = sub_examples[sub_examples["release_year"] == y]
            if ey.empty:
                continue

            count_row = sub_counts[sub_counts["release_year_label"] == y]
            count_text = int(count_row["count"].iloc[0]) if not count_row.empty else len(ey)

            lines.append(f"#### {y} ({count_text} games)")
            lines.append("")
            lines.append("| # | Game | AppID | Release date | Protagonist | Primary archetype | Credibility |")
            lines.append("|---:|---|---:|---|---|---|---:|")
            for _, row in ey.iterrows():
                game = str(row.get("name", "")).replace("|", "\\|")
                protagonist = str(row.get("jmeno_postavy", "")).replace("|", "\\|")
                primary = str(row.get("primarni_archetyp_12", "")).replace("|", "\\|")
                release_date = str(row.get("release_date_raw", "")).replace("|", "\\|")
                appid = row.get("appid", "")
                cred = row.get("verohodnost_0_1", "")
                try:
                    cred_text = f"{float(cred):.3f}"
                except Exception:
                    cred_text = ""
                lines.append(f"| {int(row['example_no'])} | {game} | {appid} | {release_date} | {protagonist} | {primary} | {cred_text} |")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="", help="Optional explicit CSV input. If omitted, uses default analysis-ready with year.")
    parser.add_argument("--label", default="ANALYSIS_READY_12", help="Label for explicit --input source.")
    parser.add_argument("--outdir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--examples-per-year", type=int, default=10)
    parser.add_argument("--groups", action="store_true", help="Also process the three standard groups if available.")
    parser.add_argument("--only-groups", action="store_true", help="Process only the three groups, not analysis-ready.")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sources: list[tuple[str, Path]] = []

    if args.input:
        sources.append((args.label, Path(args.input)))
    elif not args.only_groups:
        analysis_path = first_existing(ANALYSIS_CANDIDATES)
        if analysis_path is None:
            raise FileNotFoundError("No default analysis-ready-with-year file found. Run the release-year merge script first.")
        sources.append(("ANALYSIS_READY_12", analysis_path))

    if args.groups or args.only_groups:
        for label, candidates in GROUP_CANDIDATES.items():
            p = first_existing(candidates)
            if p is not None:
                sources.append((label, p))
            else:
                print(f"WARNING: no file found for group {label}, skipping.")

    if not sources:
        raise RuntimeError("No input sources selected.")

    all_counts = []
    all_examples = []
    summaries = []

    for label, path in sources:
        print(f"Reading {label}: {path}")
        df = pd.read_csv(path, dtype={"appid": str}, low_memory=False)
        counts, examples, summary = analyze_source(df, label, args.examples_per_year)
        all_counts.append(counts)
        all_examples.append(examples)
        summaries.append({
            **summary,
            "input_csv": str(path),
        })

        print(f"  rows: {summary['rows_total']}")
        print(f"  with year: {summary['rows_with_release_year']}")
        print(f"  missing year: {summary['rows_missing_release_year']}")
        print(f"  range: {summary['min_release_year']}–{summary['max_release_year']}")

    counts_all = pd.concat(all_counts, ignore_index=True)
    examples_all = pd.concat(all_examples, ignore_index=True)

    counts_path = outdir / "year_counts_all_sources_12_v001.csv"
    examples_path = outdir / "year_examples_10_per_year_all_sources_12_v001.csv"
    md_path = outdir / "year_overview_all_sources_12_v001.md"
    summary_path = outdir / "year_overview_summary_12_v001.json"

    counts_all.to_csv(counts_path, index=False, encoding="utf-8-sig")
    examples_all.to_csv(examples_path, index=False, encoding="utf-8-sig")
    write_markdown(md_path, summaries, counts_all, examples_all)

    summary = {
        "created_at": now_iso(),
        "output_dir": str(outdir),
        "examples_per_year": int(args.examples_per_year),
        "sources": summaries,
        "outputs": {
            "counts_csv": str(counts_path),
            "examples_csv": str(examples_path),
            "markdown_overview": str(md_path),
        },
        "note": "release_year is the Steam Store release year, not necessarily original game release year."
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nSaved:")
    print(f"  {counts_path}")
    print(f"  {examples_path}")
    print(f"  {md_path}")
    print(f"  {summary_path}")


if __name__ == "__main__":
    main()
