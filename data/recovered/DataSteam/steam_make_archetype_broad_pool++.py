#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_make_archetype_broad_pool.py

Broad, low-filter Steam candidate pool for protagonist/archetype coding.

Rationale
---------
Community tags are too noisy for reliable protagonist filtering. A strict filter
misses many excellent fixed-protagonist games; a loose filter includes false
positives. For the archetype project, it is safer to keep a broad pool and decide
later when we actually try to identify a protagonist and archetypes.

This script performs NO web requests.
It uses existing CSV files from steam_bulk_outputs/.

Preferred inputs:
- steam_bulk_outputs/steam_catalog_merged.csv

Fallback inputs:
- steam_bulk_outputs/steam_catalog_games.csv
- steam_bulk_outputs/steamspy_all_snapshot.csv

Optional:
- steam_archetype_control_100.csv
- steam_bulk_outputs/steam_archetype_control_100.csv

Outputs:
- steam_bulk_outputs/steam_archetype_broad_pool_all_ranked.csv
- steam_bulk_outputs/steam_archetype_broad_pool.csv
- steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv
- steam_bulk_outputs/steam_archetype_broad_pool_control_coverage.csv

Example:
    python steam_make_archetype_broad_pool.py
    python steam_make_archetype_broad_pool.py --min-reactions 100 --max-rows 30000
    python steam_make_archetype_broad_pool.py --min-reactions 0 --max-rows 0
"""

from __future__ import annotations

import argparse
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


OUTPUT_DIR = Path("steam_bulk_outputs")

MERGED_CATALOG = OUTPUT_DIR / "steam_catalog_merged.csv"
STEAM_CATALOG = OUTPUT_DIR / "steam_catalog_games.csv"
STEAMSPY_ALL = OUTPUT_DIR / "steamspy_all_snapshot.csv"

CONTROL_LIST_CANDIDATES = [
    Path("steam_archetype_control_100.csv"),
    OUTPUT_DIR / "steam_archetype_control_100.csv",
]

OUT_ALL_RANKED = OUTPUT_DIR / "steam_archetype_broad_pool_all_ranked.csv"
OUT_POOL = OUTPUT_DIR / "steam_archetype_broad_pool.csv"
OUT_FOR_CODING = OUTPUT_DIR / "steam_archetype_broad_pool_for_coding.csv"
OUT_CONTROL_COVERAGE = OUTPUT_DIR / "steam_archetype_broad_pool_control_coverage.csv"


MANUAL_CODING_COLUMNS = {
    "coding_status": "",
    "protagonist": "",
    "protagonist_clarity": "",
    "protagonist_type": "",
    "protagonist_gender": "",
    "is_clear_main_protagonist": "",
    "protagonist_confidence_0_3": "",
    "primary_archetype": "",
    "secondary_archetype": "",
    "tertiary_archetype": "",
    "shadow_load_0_3": "",
    "player_projection_0_3": "",
    "narrative_complexity_0_3": "",
    "include_in_final_corpus": "",
    "exclusion_reason": "",
    "coding_notes": "",
    "coding_source": "",
}


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.csv")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def normalize_title(s: object) -> str:
    s = "" if pd.isna(s) else str(s)
    s = s.lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'")
    s = re.sub(r"[\u2122\u00ae\u00a9]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(definitive|enhanced|complete|ultimate|remastered|remaster|director s cut|game of the year|goty|edition|collection|hd|windows|intergrade|reunion|the final cut|remake|director cut)\b",
        " ",
        s,
    )
    return re.sub(r"\s+", " ", s).strip()


def get_first_existing_col(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def split_terms(value: object) -> List[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return []
    if ";" in text:
        return [x.strip() for x in text.split(";") if x.strip()]
    if "," in text:
        return [x.strip() for x in text.split(",") if x.strip()]
    return [text]


def join_unique_terms(values: Sequence[object]) -> str:
    out = []
    seen = set()
    for v in values:
        for term in split_terms(v):
            key = term.lower().strip()
            if key and key not in seen:
                seen.add(key)
                out.append(term)
    return "; ".join(sorted(out, key=lambda x: x.lower()))


def load_source() -> pd.DataFrame:
    if MERGED_CATALOG.exists():
        print(f"Loading merged catalog: {MERGED_CATALOG}")
        df = read_csv(MERGED_CATALOG)
        df["source_input"] = str(MERGED_CATALOG)
        return df

    if not STEAM_CATALOG.exists():
        raise FileNotFoundError(f"Missing {STEAM_CATALOG}")
    if not STEAMSPY_ALL.exists():
        raise FileNotFoundError(f"Missing {STEAMSPY_ALL}")

    print(f"Loading Steam catalog: {STEAM_CATALOG}")
    catalog = read_csv(STEAM_CATALOG)
    print(f"Loading SteamSpy snapshot: {STEAMSPY_ALL}")
    spy = read_csv(STEAMSPY_ALL)

    if "appid" not in catalog.columns or "appid" not in spy.columns:
        raise RuntimeError("Both catalog and SteamSpy snapshot must contain appid.")

    # Rename SteamSpy name to avoid collisions.
    if "name" in spy.columns:
        spy = spy.rename(columns={"name": "steamspy_name"})

    df = catalog.merge(spy, on="appid", how="left", suffixes=("", "_steamspy"))
    df["source_input"] = f"{STEAM_CATALOG}+{STEAMSPY_ALL}"
    return df


def ensure_basic_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "appid" not in df.columns:
        raise RuntimeError("Input has no appid column.")
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
    df = df[df["appid"].notna()].copy()
    df["appid"] = df["appid"].astype(int)

    name_col = get_first_existing_col(df, ["name", "steam_name", "steam_catalog_name", "name_from_app_list"])
    if name_col is None:
        spy_name_col = get_first_existing_col(df, ["steamspy_name"])
        if spy_name_col:
            df["name"] = df[spy_name_col]
        else:
            df["name"] = ""
    elif name_col != "name":
        df["name"] = df[name_col]

    # Compute reaction counts. Prefer existing total_ratings_pos_neg, otherwise positive+negative.
    if "total_ratings_pos_neg" not in df.columns:
        pos_col = get_first_existing_col(df, ["steamspy_positive", "positive", "total_positive"])
        neg_col = get_first_existing_col(df, ["steamspy_negative", "negative", "total_negative"])
        if pos_col and neg_col:
            df["total_ratings_pos_neg"] = (
                pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
                + pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            )
        else:
            df["total_ratings_pos_neg"] = 0
    df["total_ratings_pos_neg"] = pd.to_numeric(df["total_ratings_pos_neg"], errors="coerce").fillna(0).astype(int)

    if "positive_ratio" not in df.columns:
        pos_col = get_first_existing_col(df, ["steamspy_positive", "positive", "total_positive"])
        neg_col = get_first_existing_col(df, ["steamspy_negative", "negative", "total_negative"])
        if pos_col and neg_col:
            pos = pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
            neg = pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            denom = pos + neg
            df["positive_ratio"] = pos.where(denom > 0, 0) / denom.where(denom > 0, 1)
        else:
            df["positive_ratio"] = None

    # Owners are useful for sorting but often approximate strings like "1,000,000 .. 2,000,000".
    owners_col = get_first_existing_col(df, ["steamspy_owners", "owners"])
    if owners_col and owners_col != "steamspy_owners":
        df["steamspy_owners"] = df[owners_col]
    elif "steamspy_owners" not in df.columns:
        df["steamspy_owners"] = ""

    # Consolidate terms for later human/LLM inspection, not for filtering.
    term_cols = [
        c for c in [
            "primary_terms",
            "matched_terms",
            "support_terms",
            "steamspy_tags",
            "tags",
            "genre",
            "genres",
            "steamspy_genre",
            "steam_genres",
            "steam_categories",
        ]
        if c in df.columns
    ]
    if term_cols:
        df["available_terms_for_later_inspection"] = df[term_cols].apply(
            lambda row: join_unique_terms(list(row.values)),
            axis=1,
        )
    else:
        df["available_terms_for_later_inspection"] = ""

    return df


def aggregate_by_appid(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_basic_columns(df)

    # Aggregate duplicate appids from merged/tag-hit catalogs.
    rows = []
    for appid, group in df.groupby("appid", sort=False):
        # Choose the row with the largest reaction count as base.
        base = group.sort_values("total_ratings_pos_neg", ascending=False).iloc[0].copy()
        base["available_terms_for_later_inspection"] = join_unique_terms(
            group["available_terms_for_later_inspection"].tolist()
        )
        base["source_row_count_for_appid"] = len(group)
        rows.append(base)

    out = pd.DataFrame(rows)
    out["name_norm"] = out["name"].map(normalize_title)
    out = out.drop_duplicates(subset=["appid"], keep="first")
    return out


def find_control_list() -> Optional[Path]:
    for p in CONTROL_LIST_CANDIDATES:
        if p.exists():
            return p
    return None


def best_title_match(control_title: str, catalog: pd.DataFrame) -> Tuple[Optional[int], Optional[str], float]:
    target = normalize_title(control_title)
    if not target:
        return None, None, 0.0

    exact = catalog[catalog["name_norm"] == target]
    if not exact.empty:
        row = exact.sort_values("total_ratings_pos_neg", ascending=False).iloc[0]
        return int(row["appid"]), str(row["name"]), 1.0

    contains = catalog[catalog["name_norm"].str.contains(re.escape(target), na=False)]
    if contains.empty:
        contains = catalog[catalog["name_norm"].map(lambda x: (target in x or x in target) if isinstance(x, str) else False)]

    if not contains.empty:
        row = contains.sort_values("total_ratings_pos_neg", ascending=False).iloc[0]
        score = SequenceMatcher(None, target, str(row["name_norm"])).ratio()
        return int(row["appid"]), str(row["name"]), float(score)

    target_words = set(target.split())
    if not target_words:
        return None, None, 0.0

    def overlap(n: str) -> int:
        return len(target_words & set(str(n).split()))

    tmp = catalog.copy()
    tmp["_overlap"] = tmp["name_norm"].map(overlap)
    tmp = tmp[tmp["_overlap"] > 0]
    if tmp.empty:
        return None, None, 0.0

    tmp = tmp.sort_values(["_overlap", "total_ratings_pos_neg"], ascending=[False, False]).head(250)
    best = None
    best_score = 0.0
    for _, row in tmp.iterrows():
        score = SequenceMatcher(None, target, str(row["name_norm"])).ratio()
        if score > best_score:
            best = row
            best_score = score

    if best is not None and best_score >= 0.72:
        return int(best["appid"]), str(best["name"]), float(best_score)

    return None, None, float(best_score)


def attach_control_coverage(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_control_seed"] = False
    df["control_title"] = ""
    df["control_protagonist"] = ""
    df["control_match_score"] = ""

    control_path = find_control_list()
    if control_path is None:
        print("No control list found. Skipping control coverage.")
        return df

    print(f"Loading control list: {control_path}")
    control = read_csv(control_path)
    if "steam_search_title" not in control.columns:
        print("Control list has no steam_search_title column. Skipping.")
        return df

    coverage_rows = []
    appid_to_control: Dict[int, Dict[str, object]] = {}

    for _, row in control.iterrows():
        title = str(row["steam_search_title"])
        appid, matched_name, score = best_title_match(title, df)
        coverage = row.to_dict()
        coverage.update({
            "matched_appid": appid,
            "matched_name": matched_name,
            "match_score": score,
            "matched_in_broad_source_catalog": appid is not None,
        })
        coverage_rows.append(coverage)
        if appid is not None:
            appid_to_control[int(appid)] = coverage

    for appid, meta in appid_to_control.items():
        mask = df["appid"] == appid
        df.loc[mask, "is_control_seed"] = True
        df.loc[mask, "control_title"] = meta.get("steam_search_title", "")
        df.loc[mask, "control_protagonist"] = meta.get("protagonist", "")
        df.loc[mask, "control_match_score"] = meta.get("match_score", "")

    coverage_df = pd.DataFrame(coverage_rows)
    write_csv(coverage_df, OUT_CONTROL_COVERAGE)

    total = len(coverage_df)
    found = int(coverage_df["matched_in_broad_source_catalog"].sum()) if total else 0
    print(f"Control coverage in broad source catalog: {found}/{total}")

    return df


def make_pool(df: pd.DataFrame, min_reactions: int, max_rows: int, include_control_seeds: bool) -> pd.DataFrame:
    df = df.copy()

    df["broad_pool_reason"] = ""
    reason_mask = df["total_ratings_pos_neg"] >= min_reactions
    df.loc[reason_mask, "broad_pool_reason"] = f"reactions>={min_reactions}"

    if include_control_seeds and "is_control_seed" in df.columns:
        seed_mask = df["is_control_seed"] == True
        df.loc[seed_mask & reason_mask, "broad_pool_reason"] = df.loc[seed_mask & reason_mask, "broad_pool_reason"] + "; control_seed"
        df.loc[seed_mask & ~reason_mask, "broad_pool_reason"] = "control_seed_below_reaction_threshold"
        reason_mask = reason_mask | seed_mask

    pool = df[reason_mask].copy()

    # Sort primarily by control seed and reactions. No genre scoring.
    pool["sort_control"] = pool.get("is_control_seed", False).astype(int) if "is_control_seed" in pool.columns else 0
    pool = pool.sort_values(
        by=["sort_control", "total_ratings_pos_neg", "positive_ratio", "name"],
        ascending=[False, False, False, True],
        na_position="last",
    ).drop(columns=["sort_control"], errors="ignore")

    if max_rows and max_rows > 0:
        pool = pool.head(max_rows).copy()

    pool.reset_index(drop=True, inplace=True)
    pool.insert(0, "broad_rank", range(1, len(pool) + 1))
    return pool


def make_coding_table(pool: pd.DataFrame) -> pd.DataFrame:
    keep_cols_preferred = [
        "broad_rank",
        "appid",
        "name",
        "total_ratings_pos_neg",
        "positive_ratio",
        "steamspy_owners",
        "available_terms_for_later_inspection",
        "broad_pool_reason",
        "is_control_seed",
        "control_title",
        "control_protagonist",
        "control_match_score",
        "steam_release_date",
        "release_date",
        "developers",
        "publishers",
        "header_image",
        "website",
    ]

    keep_cols = [c for c in keep_cols_preferred if c in pool.columns]
    coding = pool[keep_cols].copy()

    # Insert manual coding columns after core identifiers.
    insert_after = 3 if len(coding.columns) >= 3 else len(coding.columns)
    for offset, (col, default) in enumerate(MANUAL_CODING_COLUMNS.items()):
        coding.insert(insert_after + offset, col, default)

    return coding


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-reactions",
        type=int,
        default=100,
        help="Minimum positive+negative SteamSpy reactions for inclusion. Default: 100.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=30000,
        help="Maximum rows in broad pool. Use 0 for unlimited. Default: 30000.",
    )
    parser.add_argument(
        "--no-control-seeds",
        action="store_true",
        help="Do not force matched control-list titles into the pool.",
    )
    args = parser.parse_args()

    print("Steam broad archetype pool builder")
    print(f"Output dir: {OUTPUT_DIR.resolve()}")
    print(f"min_reactions={args.min_reactions}")
    print(f"max_rows={args.max_rows if args.max_rows else 'unlimited'}")

    raw = load_source()
    catalog = aggregate_by_appid(raw)
    print(f"Unique appids in source catalog: {len(catalog)}")

    catalog = attach_control_coverage(catalog)

    # Save all ranked source rows for transparency.
    all_ranked = catalog.sort_values(
        by=["total_ratings_pos_neg", "positive_ratio", "name"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    all_ranked.insert(0, "all_rank", range(1, len(all_ranked) + 1))
    write_csv(all_ranked, OUT_ALL_RANKED)
    print(f"Saved all ranked source catalog: {OUT_ALL_RANKED} ({len(all_ranked)} rows)")

    pool = make_pool(
        catalog,
        min_reactions=args.min_reactions,
        max_rows=args.max_rows,
        include_control_seeds=not args.no_control_seeds,
    )
    write_csv(pool, OUT_POOL)
    print(f"Saved broad pool: {OUT_POOL} ({len(pool)} rows)")

    coding = make_coding_table(pool)
    write_csv(coding, OUT_FOR_CODING)
    print(f"Saved broad pool for coding: {OUT_FOR_CODING} ({len(coding)} rows)")

    preview_cols = [
        "broad_rank",
        "appid",
        "name",
        "total_ratings_pos_neg",
        "positive_ratio",
        "broad_pool_reason",
        "is_control_seed",
        "control_protagonist",
        "available_terms_for_later_inspection",
    ]
    preview_cols = [c for c in preview_cols if c in pool.columns]
    print("\nTop preview:")
    print(pool[preview_cols].head(40).to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
