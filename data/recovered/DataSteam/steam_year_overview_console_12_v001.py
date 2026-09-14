#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_year_overview_console_12_v001.py

Console-first year overview for the corrected 12-archetype Steam dataset.

For each Steam release year it prints:
- number of games in that year
- 10 example games from that year

Default input:
  steam_bulk_outputs/release_years_12_v002/steam_analysis_ready_12_with_year_v002.csv

Optional:
  --groups       also print the three standard groups
  --only-groups  print only the three standard groups
  --examples-per-year 10

It also saves the same information to CSV/MD files:
  steam_bulk_outputs/year_overview_console_12_v001/

No network calls. No API calls. No money spent.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_OUTPUT_DIR = Path("steam_bulk_outputs/year_overview_console_12_v001")

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

    if "selection_rank" in out.columns:
        out["_sort_rank"] = pd.to_numeric(out["selection_rank"], errors="coerce").fillna(10**12)
    elif "total_ratings_pos_neg" in out.columns:
        out["_sort_rank"] = -pd.to_numeric(out["total_ratings_pos_neg"], errors="coerce").fillna(0)
    else:
        out["_sort_rank"] = range(len(out))

    out["_sort_name"] = out["name"].fillna("").astype(str) if "name" in out.columns else ""
    return out.sort_values(["_sort_rank", "_sort_name"], ascending=[True, True])


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
        return int(label) if str(label).isdigit() else 999999

    counts["_sort_year"] = counts["release_year_label"].map(year_sort_key)
    counts = counts.sort_values("_sort_year").drop(columns=["_sort_year"])

    examples_rows = []
    sorted_work = sort_for_examples(work)

    # Keep chronological year order.
    year_labels = list(counts["release_year_label"])
    year_labels = sorted(year_labels, key=lambda x: int(x) if str(x).isdigit() else 999999)

    for year_label in year_labels:
        sub = sorted_work[sorted_work["release_year_label"].astype(str).eq(str(year_label))].head(examples_per_year).copy()
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


def fmt_int(x) -> str:
    try:
        return f"{int(float(x)):,}".replace(",", " ")
    except Exception:
        return str(x)


def fmt_float(x, digits=3) -> str:
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return ""


def truncate(text: str, max_len: int) -> str:
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def print_source_to_console(source_label: str, counts: pd.DataFrame, examples: pd.DataFrame, summary: dict) -> None:
    print()
    print("=" * 100)
    print(f"{source_label}")
    print("=" * 100)
    print(f"Rows total:              {fmt_int(summary['rows_total'])}")
    print(f"Rows with release year:  {fmt_int(summary['rows_with_release_year'])}")
    print(f"Rows missing year:       {fmt_int(summary['rows_missing_release_year'])}")
    print(f"Year range:              {summary['min_release_year']}–{summary['max_release_year']}")
    print()
    print("COUNTS BY YEAR")
    print("-" * 100)

    for _, row in counts.iterrows():
        year = row["release_year_label"]
        count = int(row["count"])
        share = float(row["share"])
        print(f"{str(year):>10} : {count:>6} games  ({share:>7.3%})")

    print()
    print(f"EXAMPLE GAMES BY YEAR")
    print("-" * 100)

    for _, count_row in counts.iterrows():
        year = str(count_row["release_year_label"])
        count = int(count_row["count"])

        sub = examples[(examples["source"] == source_label) & (examples["release_year"].astype(str) == year)]
        if sub.empty:
            continue

        print()
        print(f"{year}  ({count} games)")
        print("-" * 100)

        for _, row in sub.iterrows():
            no = int(row["example_no"])
            name = truncate(row.get("name", ""), 42)
            appid = str(row.get("appid", ""))
            date = truncate(row.get("release_date_raw", ""), 16)
            protagonist = truncate(row.get("jmeno_postavy", ""), 28)
            primary = truncate(row.get("primarni_archetyp_12", ""), 24)
            cred = fmt_float(row.get("verohodnost_0_1", ""), 3)

            print(f"{no:>2}. {name:<42} | appid {appid:<8} | {date:<16} | {protagonist:<28} | {primary:<24} | cred {cred}")


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
        lines.append("### Counts by year")
        lines.append("")
        lines.append("| Year | Count | Share |")
        lines.append("|---:|---:|---:|")
        for _, row in sub_counts.iterrows():
            lines.append(f"| {row['release_year_label']} | {int(row['count'])} | {float(row['share']):.3%} |")
        lines.append("")

        lines.append("### Example games by year")
        lines.append("")
        sub_examples = examples[examples["source"] == src].copy()

        for _, count_row in sub_counts.iterrows():
            y = str(count_row["release_year_label"])
            ey = sub_examples[sub_examples["release_year"].astype(str) == y]
            if ey.empty:
                continue

            lines.append(f"#### {y} ({int(count_row['count'])} games)")
            lines.append("")
            lines.append("| # | Game | AppID | Release date | Protagonist | Primary archetype | Credibility |")
            lines.append("|---:|---|---:|---|---|---|---:|")
            for _, row in ey.iterrows():
                game = str(row.get("name", "")).replace("|", "\\|")
                protagonist = str(row.get("jmeno_postavy", "")).replace("|", "\\|")
                primary = str(row.get("primarni_archetyp_12", "")).replace("|", "\\|")
                release_date = str(row.get("release_date_raw", "")).replace("|", "\\|")
                cred = fmt_float(row.get("verohodnost_0_1", ""), 3)
                lines.append(f"| {int(row['example_no'])} | {game} | {row.get('appid', '')} | {release_date} | {protagonist} | {primary} | {cred} |")
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
    parser.add_argument("--no-save", action="store_true", help="Only print to console; do not save CSV/MD outputs.")
    args = parser.parse_args()

    sources: list[tuple[str, Path]] = []

    if args.input:
        sources.append((args.label, Path(args.input)))
    elif not args.only_groups:
        analysis_path = first_existing(ANALYSIS_CANDIDATES)
        if analysis_path is None:
            raise FileNotFoundError("No default analysis-ready-with-year file found. Run release-year merge first.")
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
        print(f"\nReading {label}: {path}")
        df = pd.read_csv(path, dtype={"appid": str}, low_memory=False)
        counts, examples, summary = analyze_source(df, label, args.examples_per_year)
        all_counts.append(counts)
        all_examples.append(examples)
        summaries.append({**summary, "input_csv": str(path)})

        print_source_to_console(label, counts, examples, summary)

    if not args.no_save:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        counts_all = pd.concat(all_counts, ignore_index=True)
        examples_all = pd.concat(all_examples, ignore_index=True)

        counts_path = outdir / "year_counts_all_sources_12_v001.csv"
        examples_path = outdir / "year_examples_10_per_year_all_sources_12_v001.csv"
        md_path = outdir / "year_overview_all_sources_12_v001.md"
        summary_path = outdir / "year_overview_summary_12_v001.json"

        counts_all.to_csv(counts_path, index=False, encoding="utf-8-sig")
        examples_all.to_csv(examples_path, index=False, encoding="utf-8-sig")
        write_markdown(md_path, summaries, counts_all, examples_all)

        summary_json = {
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
        summary_path.write_text(json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8")

        print()
        print("Saved:")
        print(f"  {counts_path}")
        print(f"  {examples_path}")
        print(f"  {md_path}")
        print(f"  {summary_path}")


if __name__ == "__main__":
    main()
