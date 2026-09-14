#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_fetch_release_years_and_merge_12_v001.py

Fetch Steam release dates by appid and merge release year into the corrected
12-archetype datasets and three group exports.

No OpenAI API calls. No LLM cost.

It uses the public Steam Store appdetails endpoint:
  https://store.steampowered.com/api/appdetails?appids=<appid>&filters=release_date

Default input files:
  steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv
  steam_bulk_outputs/three_groups_12_v001/group_1_core_strict_12_v001.csv
  steam_bulk_outputs/three_groups_12_v001/group_2_core_broad_12_v001.csv
  steam_bulk_outputs/three_groups_12_v001/group_3_review_pool_12_v001.csv

Cache:
  steam_bulk_outputs/steam_release_dates_cache_v001.csv

Output directory:
  steam_bulk_outputs/release_years_12_v001/

Main outputs:
  steam_analysis_ready_12_with_year_v001.csv
  group_1_core_strict_12_with_year_v001.csv
  group_2_core_broad_12_with_year_v001.csv
  group_3_review_pool_12_with_year_v001.csv

Human-readable outputs:
  human_readable_group_1_core_strict_12_with_year_v001.csv
  human_readable_group_2_core_broad_12_with_year_v001.csv
  human_readable_group_3_review_pool_12_with_year_v001.csv

Summary outputs:
  release_year_counts_by_group_12_v001.csv
  release_year_fetch_summary_v001.json
  README_release_years_12_v001.md

Behavior:
- Reads unique appids from the analysis-ready file.
- Loads existing cache if present.
- Fetches only appids missing from the cache unless --refresh is used.
- Saves cache continuously every N fetched rows, so interrupted runs can resume.
- Merges release_year into analysis-ready and group files.
- Does not overwrite previous final_archetype_datasets_* or three_groups_* folders.

Recommended run:
  python steam_fetch_release_years_and_merge_12_v001.py

If interrupted, run the same command again.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_ANALYSIS = Path("steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv")
DEFAULT_GROUP_DIR = Path("steam_bulk_outputs/three_groups_12_v001")
DEFAULT_OUTPUT_DIR = Path("steam_bulk_outputs/release_years_12_v001")
DEFAULT_CACHE = Path("steam_bulk_outputs/steam_release_dates_cache_v001.csv")

GROUP_FILES = [
    ("group_1_core_strict_12_v001.csv", "group_1_core_strict_12_with_year_v001.csv", "CORE_STRICT"),
    ("group_2_core_broad_12_v001.csv", "group_2_core_broad_12_with_year_v001.csv", "CORE_BROAD"),
    ("group_3_review_pool_12_v001.csv", "group_3_review_pool_12_with_year_v001.csv", "REVIEW_POOL"),
]

EXCLUSIVE_GROUP_FILES = [
    ("exclusive_group_1_core_strict_12_v001.csv", "exclusive_group_1_core_strict_12_with_year_v001.csv", "EXCLUSIVE_CORE_STRICT"),
    ("exclusive_group_2_core_broad_nonreview_12_v001.csv", "exclusive_group_2_core_broad_nonreview_12_with_year_v001.csv", "EXCLUSIVE_CORE_BROAD_NONREVIEW"),
    ("exclusive_group_3_review_pool_noncorestrict_12_v001.csv", "exclusive_group_3_review_pool_noncorestrict_12_with_year_v001.csv", "EXCLUSIVE_REVIEW_POOL_NONCORESTRICT"),
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def require_columns(df: pd.DataFrame, cols: list[str], source: Path) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"Input CSV is missing required columns: {source}\n"
            + "\n".join(f"  - {c}" for c in missing)
        )


def normalize_appid(value: Any) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if not s:
        return ""
    # Pandas may render integer-looking values as 123.0.
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def parse_year_from_release_date(date_text: str) -> str:
    """
    Steam release_date.date is not fully standardized.

    Common examples:
      "Nov 16, 2004"
      "16 Nov, 2004"
      "2004"
      "Coming soon"
      ""
    We take the first plausible year between 1970 and 2100.
    """
    if not date_text:
        return ""
    match = re.search(r"(19[7-9]\d|20\d\d|2100)", str(date_text))
    return match.group(1) if match else ""


def load_cache(cache_path: Path) -> pd.DataFrame:
    if not cache_path.exists():
        return pd.DataFrame(columns=[
            "appid",
            "steam_success",
            "release_date_raw",
            "release_year",
            "coming_soon",
            "fetch_status",
            "error",
            "fetched_at",
        ])

    df = pd.read_csv(cache_path, dtype={"appid": str}, low_memory=False)
    if "appid" not in df.columns:
        raise RuntimeError(f"Cache file has no appid column: {cache_path}")

    df["appid"] = df["appid"].map(normalize_appid)
    return df.drop_duplicates(subset=["appid"], keep="last")


def save_cache(cache_df: pd.DataFrame, cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_df = cache_df.copy()
    cache_df["appid"] = cache_df["appid"].map(normalize_appid)
    cache_df = cache_df.drop_duplicates(subset=["appid"], keep="last")
    cache_df.to_csv(cache_path, index=False, encoding="utf-8-sig")


def fetch_release_date_for_appid(appid: str, timeout: float = 20.0) -> dict[str, Any]:
    params = urllib.parse.urlencode({
        "appids": appid,
        "filters": "release_date",
    })
    url = f"https://store.steampowered.com/api/appdetails?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SteamReleaseYearCorpusBuilder/1.0)",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw)

        item = data.get(str(appid), {})
        success = bool(item.get("success", False))
        payload = item.get("data", {}) if success else {}
        release_obj = payload.get("release_date", {}) if isinstance(payload, dict) else {}

        release_date_raw = ""
        coming_soon = ""
        if isinstance(release_obj, dict):
            release_date_raw = str(release_obj.get("date", "") or "").strip()
            coming_soon = str(release_obj.get("coming_soon", "")).strip()

        return {
            "appid": appid,
            "steam_success": success,
            "release_date_raw": release_date_raw,
            "release_year": parse_year_from_release_date(release_date_raw),
            "coming_soon": coming_soon,
            "fetch_status": "ok" if success else "steam_success_false",
            "error": "",
            "fetched_at": now_iso(),
        }

    except Exception as exc:
        return {
            "appid": appid,
            "steam_success": False,
            "release_date_raw": "",
            "release_year": "",
            "coming_soon": "",
            "fetch_status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "fetched_at": now_iso(),
        }


def collect_unique_appids(analysis_path: Path) -> list[str]:
    df = pd.read_csv(analysis_path, usecols=["appid"], dtype={"appid": str}, low_memory=False)
    appids = df["appid"].map(normalize_appid)
    appids = [a for a in appids.dropna().unique().tolist() if a]
    appids = sorted(appids, key=lambda x: int(x) if x.isdigit() else x)
    return appids


def fetch_missing_release_dates(
    appids: list[str],
    cache_path: Path,
    delay: float,
    save_every: int,
    limit: int,
    refresh: bool,
) -> pd.DataFrame:
    cache_df = load_cache(cache_path)

    cached_appids = set() if refresh else set(cache_df["appid"].map(normalize_appid).tolist())
    missing = [appid for appid in appids if appid not in cached_appids]

    if limit and limit > 0:
        missing = missing[:limit]

    print(f"Total appids in dataset: {len(appids)}")
    print(f"Cached appids: {len(cached_appids)}")
    print(f"To fetch now: {len(missing)}")
    print(f"Cache: {cache_path}")

    if not missing:
        return cache_df

    rows = []
    fetched_count = 0

    for idx, appid in enumerate(missing, start=1):
        result = fetch_release_date_for_appid(appid)
        rows.append(result)
        fetched_count += 1

        year = result.get("release_year", "")
        raw = result.get("release_date_raw", "")
        status = result.get("fetch_status", "")
        print(f"[{idx}/{len(missing)}] appid={appid} status={status} year={year} raw={raw!r}")

        if fetched_count % save_every == 0:
            new_df = pd.DataFrame(rows)
            cache_df = pd.concat([cache_df, new_df], ignore_index=True)
            save_cache(cache_df, cache_path)
            print(f"Saved cache checkpoint after {fetched_count} fetched rows.")
            rows = []

        if delay > 0:
            time.sleep(delay)

    if rows:
        new_df = pd.DataFrame(rows)
        cache_df = pd.concat([cache_df, new_df], ignore_index=True)
        save_cache(cache_df, cache_path)
        print(f"Saved final cache checkpoint after {fetched_count} fetched rows.")

    return load_cache(cache_path)


def merge_release_year(df: pd.DataFrame, cache_df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["appid"] = out["appid"].map(normalize_appid)

    release_cols = [
        "appid",
        "release_date_raw",
        "release_year",
        "coming_soon",
        "steam_success",
        "fetch_status",
        "error",
        "fetched_at",
    ]
    cache_small = cache_df[[c for c in release_cols if c in cache_df.columns]].copy()
    cache_small["appid"] = cache_small["appid"].map(normalize_appid)
    cache_small = cache_small.drop_duplicates(subset=["appid"], keep="last")

    # Avoid duplicate columns if rerun on an already merged file.
    for col in release_cols:
        if col != "appid" and col in out.columns:
            out = out.drop(columns=[col])

    out = out.merge(cache_small, on="appid", how="left")
    out["release_year"] = pd.to_numeric(out["release_year"], errors="coerce").astype("Int64")
    return out


def credibility_0_1(df: pd.DataFrame) -> pd.Series:
    def num01(col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series([0] * len(df), index=df.index, dtype=float)
        return pd.to_numeric(df[col], errors="coerce").fillna(0).clip(0, 3) / 3.0

    return ((num01("llm6_protagonist_confidence_0_3") +
             num01("llm6_archetype_confidence_0_3") +
             num01("llm6_archetype_suitability_0_3")) / 3.0).round(3)


def make_human_readable_with_year(df: pd.DataFrame) -> pd.DataFrame:
    for col in [
        "name",
        "llm6_protagonist_name",
        "primary_archetype_12",
        "secondary_archetype_12",
        "tertiary_archetype_12",
        "release_year",
    ]:
        if col not in df.columns:
            df[col] = ""

    return pd.DataFrame({
        "jmeno hry": df["name"].fillna("").astype(str),
        "rok vydani": df["release_year"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True),
        "jmeno postavy": df["llm6_protagonist_name"].fillna("").astype(str),
        "primarni archetyp": df["primary_archetype_12"].fillna("").astype(str),
        "sekundarni archetyp": df["secondary_archetype_12"].fillna("").astype(str),
        "tercialni archetyp": df["tertiary_archetype_12"].fillna("").astype(str),
        "věrohodnost odhadu na škále 0 až 1": credibility_0_1(df),
    })


def year_counts_for_group(df: pd.DataFrame, group_label: str) -> pd.DataFrame:
    if "release_year" not in df.columns:
        return pd.DataFrame(columns=["group", "release_year", "count"])

    tmp = df.copy()
    tmp["release_year"] = pd.to_numeric(tmp["release_year"], errors="coerce").astype("Int64")
    counts = (
        tmp.groupby("release_year", dropna=False)
        .size()
        .reset_index(name="count")
    )
    counts.insert(0, "group", group_label)
    return counts


def process_dataset_file(
    input_path: Path,
    output_path: Path,
    human_output_path: Path | None,
    cache_df: pd.DataFrame,
    group_label: str,
) -> tuple[int, pd.DataFrame]:
    if not input_path.exists():
        print(f"WARNING: missing input file, skipping: {input_path}")
        return 0, pd.DataFrame(columns=["group", "release_year", "count"])

    print(f"Merging release years into: {input_path}")
    df = pd.read_csv(input_path, dtype={"appid": str}, low_memory=False)
    require_columns(df, ["appid"], input_path)

    merged = merge_release_year(df, cache_df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {output_path} ({len(merged)} rows)")

    if human_output_path is not None:
        human = make_human_readable_with_year(merged)
        human.to_csv(human_output_path, index=False, encoding="utf-8-sig")
        print(f"Saved human-readable: {human_output_path} ({len(human)} rows)")

    return len(merged), year_counts_for_group(merged, group_label)


def write_readme(output_dir: Path, summary: dict) -> None:
    text = f"""# Release years merged into 12-archetype datasets v001

Generated by `steam_fetch_release_years_and_merge_12_v001.py`.

## Cache

`{summary['cache_csv']}`

The cache can be reused. If the script is interrupted, run it again and it will
continue from the cached appids.

## Input

Analysis-ready dataset:

`{summary['analysis_input']}`

Group directory:

`{summary['group_dir']}`

## Output directory

`{summary['output_dir']}`

## Main outputs

- `steam_analysis_ready_12_with_year_v001.csv`
- `group_1_core_strict_12_with_year_v001.csv`
- `group_2_core_broad_12_with_year_v001.csv`
- `group_3_review_pool_12_with_year_v001.csv`
- `human_readable_group_1_core_strict_12_with_year_v001.csv`
- `human_readable_group_2_core_broad_12_with_year_v001.csv`
- `human_readable_group_3_review_pool_12_with_year_v001.csv`
- `release_year_counts_by_group_12_v001.csv`

## Summary

- Total appids in analysis dataset: {summary['total_appids']}
- Cache rows: {summary['cache_rows']}
- Cache rows with release year: {summary['cache_rows_with_year']}
- Analysis rows processed: {summary['analysis_rows']}
"""
    (output_dir / "README_release_years_12_v001.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", default=str(DEFAULT_ANALYSIS))
    parser.add_argument("--group-dir", default=str(DEFAULT_GROUP_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between Steam Store API requests in seconds.")
    parser.add_argument("--save-every", type=int, default=100, help="Save cache checkpoint every N fetched appids.")
    parser.add_argument("--limit", type=int, default=0, help="Fetch only first N missing appids; 0 = no limit.")
    parser.add_argument("--refresh", action="store_true", help="Ignore existing cache and refetch all appids.")
    parser.add_argument("--skip-fetch", action="store_true", help="Do not fetch; only merge using existing cache.")
    parser.add_argument("--exclusive", action="store_true", help="Also process exclusive group files.")
    args = parser.parse_args()

    analysis_path = Path(args.analysis)
    group_dir = Path(args.group_dir)
    output_dir = Path(args.output_dir)
    cache_path = Path(args.cache)

    if not analysis_path.exists():
        raise FileNotFoundError(analysis_path)
    if not group_dir.exists():
        raise FileNotFoundError(group_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    appids = collect_unique_appids(analysis_path)

    if args.skip_fetch:
        print("Skipping fetch; loading existing cache only.")
        cache_df = load_cache(cache_path)
    else:
        cache_df = fetch_missing_release_dates(
            appids=appids,
            cache_path=cache_path,
            delay=args.delay,
            save_every=args.save_every,
            limit=args.limit,
            refresh=args.refresh,
        )

    cache_df = load_cache(cache_path)
    cache_rows_with_year = int(cache_df["release_year"].fillna("").astype(str).str.strip().ne("").sum()) if "release_year" in cache_df.columns else 0

    all_year_counts = []

    analysis_rows, analysis_counts = process_dataset_file(
        input_path=analysis_path,
        output_path=output_dir / "steam_analysis_ready_12_with_year_v001.csv",
        human_output_path=None,
        cache_df=cache_df,
        group_label="ANALYSIS_READY_12",
    )
    all_year_counts.append(analysis_counts)

    for input_name, output_name, group_label in GROUP_FILES:
        input_path = group_dir / input_name
        output_path = output_dir / output_name
        human_output_name = output_name.replace(".csv", "").replace("group_", "human_readable_group_") + ".csv"
        # The replace above would produce human_readable_group_1_... for normal group files.
        # Keep exact expected names:
        if group_label == "CORE_STRICT":
            human_output_name = "human_readable_group_1_core_strict_12_with_year_v001.csv"
        elif group_label == "CORE_BROAD":
            human_output_name = "human_readable_group_2_core_broad_12_with_year_v001.csv"
        elif group_label == "REVIEW_POOL":
            human_output_name = "human_readable_group_3_review_pool_12_with_year_v001.csv"

        rows, counts = process_dataset_file(
            input_path=input_path,
            output_path=output_path,
            human_output_path=output_dir / human_output_name,
            cache_df=cache_df,
            group_label=group_label,
        )
        all_year_counts.append(counts)

    if args.exclusive:
        for input_name, output_name, group_label in EXCLUSIVE_GROUP_FILES:
            input_path = group_dir / input_name
            output_path = output_dir / output_name
            human_output_name = "human_readable_" + output_name

            rows, counts = process_dataset_file(
                input_path=input_path,
                output_path=output_path,
                human_output_path=output_dir / human_output_name,
                cache_df=cache_df,
                group_label=group_label,
            )
            all_year_counts.append(counts)

    counts_df = pd.concat(all_year_counts, ignore_index=True) if all_year_counts else pd.DataFrame()
    if not counts_df.empty:
        counts_df.to_csv(output_dir / "release_year_counts_by_group_12_v001.csv", index=False, encoding="utf-8-sig")
        print(f"Saved year counts: {output_dir / 'release_year_counts_by_group_12_v001.csv'}")

    summary = {
        "created_at": now_iso(),
        "analysis_input": str(analysis_path),
        "group_dir": str(group_dir),
        "output_dir": str(output_dir),
        "cache_csv": str(cache_path),
        "total_appids": int(len(appids)),
        "cache_rows": int(len(cache_df)),
        "cache_rows_with_year": int(cache_rows_with_year),
        "analysis_rows": int(analysis_rows),
        "delay_seconds": args.delay,
        "limit": args.limit,
        "skip_fetch": bool(args.skip_fetch),
        "refresh": bool(args.refresh),
        "processed_exclusive_groups": bool(args.exclusive),
    }

    summary_path = output_dir / "release_year_fetch_summary_v001.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(output_dir, summary)

    print("\nDone.")
    print(f"Summary: {summary_path}")
    print(f"README:  {output_dir / 'README_release_years_12_v001.md'}")
    print(f"Cache:   {cache_path}")


if __name__ == "__main__":
    main()
