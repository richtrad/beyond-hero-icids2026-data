#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_make_archetype_broad_pool_minimal.py

Minimal robust broad-pool builder.

No web requests.
No genre/tag filtering.
No pandas string-dtype tricks.

Reads:
- steam_bulk_outputs/steam_catalog_merged.csv

Writes:
- steam_bulk_outputs/steam_archetype_broad_pool.csv
- steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv
- steam_bulk_outputs/steam_archetype_broad_pool_control_coverage.csv
"""

from __future__ import annotations

import argparse
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Sequence, Tuple

import pandas as pd


OUTPUT_DIR = Path("steam_bulk_outputs")
MERGED_CATALOG = OUTPUT_DIR / "steam_catalog_merged.csv"
CONTROL_CANDIDATES = [
    Path("steam_archetype_control_100.csv"),
    OUTPUT_DIR / "steam_archetype_control_100.csv",
]

OUT_POOL = OUTPUT_DIR / "steam_archetype_broad_pool.csv"
OUT_CODING = OUTPUT_DIR / "steam_archetype_broad_pool_for_coding.csv"
OUT_CONTROL = OUTPUT_DIR / "steam_archetype_broad_pool_control_coverage.csv"


MANUAL_COLUMNS = [
    "coding_status",
    "protagonist",
    "protagonist_clarity",
    "protagonist_type",
    "protagonist_gender",
    "is_clear_main_protagonist",
    "protagonist_confidence_0_3",
    "primary_archetype",
    "secondary_archetype",
    "tertiary_archetype",
    "shadow_load_0_3",
    "player_projection_0_3",
    "narrative_complexity_0_3",
    "include_in_final_corpus",
    "exclusion_reason",
    "coding_notes",
    "coding_source",
]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.csv")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def first_col(df: pd.DataFrame, names: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def normalize_title(s: object) -> str:
    if pd.isna(s):
        s = ""
    s = str(s).lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'")
    s = re.sub(r"[\u2122\u00ae\u00a9]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(definitive|enhanced|complete|ultimate|remastered|remaster|director s cut|game of the year|goty|edition|collection|hd|windows|intergrade|reunion|the final cut|remake|director cut)\b",
        " ",
        s,
    )
    return re.sub(r"\s+", " ", s).strip()


def split_terms(v: object):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return []
    txt = str(v).strip()
    if not txt or txt.lower() == "nan":
        return []
    sep = ";" if ";" in txt else ","
    if sep in txt:
        return [x.strip() for x in txt.split(sep) if x.strip()]
    return [txt]


def join_terms(values) -> str:
    seen = set()
    out = []
    for v in values:
        for t in split_terms(v):
            k = t.lower()
            if k not in seen:
                seen.add(k)
                out.append(t)
    return "; ".join(sorted(out, key=lambda x: x.lower()))


def compute_reactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "appid" not in df.columns:
        raise RuntimeError("Input file has no appid column.")

    df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
    df = df[df["appid"].notna()].copy()
    df["appid"] = df["appid"].astype(int)

    name_col = first_col(df, ["name", "steam_name", "steam_catalog_name", "name_from_app_list", "steamspy_name"])
    if name_col:
        df["name"] = df[name_col].fillna("").astype(str)
    else:
        df["name"] = ""

    if "total_ratings_pos_neg" not in df.columns:
        pos_col = first_col(df, ["steamspy_positive", "positive", "total_positive"])
        neg_col = first_col(df, ["steamspy_negative", "negative", "total_negative"])
        if pos_col and neg_col:
            df["total_ratings_pos_neg"] = (
                pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
                + pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            )
        else:
            df["total_ratings_pos_neg"] = 0
    df["total_ratings_pos_neg"] = pd.to_numeric(df["total_ratings_pos_neg"], errors="coerce").fillna(0).astype(int)

    if "positive_ratio" not in df.columns:
        pos_col = first_col(df, ["steamspy_positive", "positive", "total_positive"])
        neg_col = first_col(df, ["steamspy_negative", "negative", "total_negative"])
        if pos_col and neg_col:
            pos = pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
            neg = pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            denom = pos + neg
            df["positive_ratio"] = pos.where(denom > 0, 0) / denom.where(denom > 0, 1)
        else:
            df["positive_ratio"] = ""

    owners_col = first_col(df, ["steamspy_owners", "owners"])
    if owners_col:
        df["steamspy_owners"] = df[owners_col].fillna("").astype(str)
    else:
        df["steamspy_owners"] = ""

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
        df["available_terms_for_later_inspection"] = df[term_cols].apply(lambda r: join_terms(r.values), axis=1)
    else:
        df["available_terms_for_later_inspection"] = ""

    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    df = compute_reactions(df)

    rows = []
    for appid, g in df.groupby("appid", sort=False):
        base = g.sort_values("total_ratings_pos_neg", ascending=False).iloc[0].copy()
        base["available_terms_for_later_inspection"] = join_terms(g["available_terms_for_later_inspection"].tolist())
        base["source_row_count_for_appid"] = len(g)
        rows.append(base)

    out = pd.DataFrame(rows)
    out["name_norm"] = out["name"].map(normalize_title)
    return out.reset_index(drop=True)


def control_path() -> Optional[Path]:
    for p in CONTROL_CANDIDATES:
        if p.exists():
            return p
    return None


def best_match(title: str, catalog: pd.DataFrame) -> Tuple[Optional[int], Optional[str], float]:
    target = normalize_title(title)
    if not target:
        return None, None, 0.0

    exact = catalog[catalog["name_norm"] == target]
    if not exact.empty:
        r = exact.sort_values("total_ratings_pos_neg", ascending=False).iloc[0]
        return int(r["appid"]), str(r["name"]), 1.0

    contains = catalog[catalog["name_norm"].str.contains(re.escape(target), na=False)]
    if contains.empty:
        contains = catalog[catalog["name_norm"].map(lambda x: (target in x or x in target) if isinstance(x, str) else False)]
    if not contains.empty:
        r = contains.sort_values("total_ratings_pos_neg", ascending=False).iloc[0]
        score = SequenceMatcher(None, target, str(r["name_norm"])).ratio()
        return int(r["appid"]), str(r["name"]), float(score)

    words = set(target.split())
    if not words:
        return None, None, 0.0

    tmp = catalog.copy()
    tmp["_overlap"] = tmp["name_norm"].map(lambda n: len(words & set(str(n).split())))
    tmp = tmp[tmp["_overlap"] > 0]
    if tmp.empty:
        return None, None, 0.0

    tmp = tmp.sort_values(["_overlap", "total_ratings_pos_neg"], ascending=[False, False]).head(250)
    best = None
    best_score = 0.0
    for _, r in tmp.iterrows():
        score = SequenceMatcher(None, target, str(r["name_norm"])).ratio()
        if score > best_score:
            best = r
            best_score = score

    if best is not None and best_score >= 0.72:
        return int(best["appid"]), str(best["name"]), float(best_score)

    return None, None, float(best_score)


def attach_control(catalog: pd.DataFrame) -> pd.DataFrame:
    catalog = catalog.copy()

    # Object dtype: avoids pandas StringArray errors.
    catalog["is_control_seed"] = False
    catalog["control_title"] = pd.Series([""] * len(catalog), index=catalog.index, dtype="object")
    catalog["control_protagonist"] = pd.Series([""] * len(catalog), index=catalog.index, dtype="object")
    catalog["control_match_score"] = pd.Series([""] * len(catalog), index=catalog.index, dtype="object")

    cp = control_path()
    if cp is None:
        print("No control list found; continuing without control coverage.")
        return catalog

    print(f"Loading control list: {cp}")
    control = read_csv(cp)
    if "steam_search_title" not in control.columns:
        print("Control list has no steam_search_title column; continuing without control coverage.")
        return catalog

    coverage_rows = []
    for _, row in control.iterrows():
        title = str(row["steam_search_title"])
        appid, matched_name, score = best_match(title, catalog)

        cov = row.to_dict()
        cov.update({
            "matched_appid": appid,
            "matched_name": matched_name,
            "match_score": score,
            "matched_in_source_catalog": appid is not None,
        })
        coverage_rows.append(cov)

        if appid is not None:
            mask = catalog["appid"] == int(appid)
            catalog.loc[mask, "is_control_seed"] = True
            catalog.loc[mask, "control_title"] = str(row.get("steam_search_title", ""))
            catalog.loc[mask, "control_protagonist"] = str(row.get("protagonist", ""))
            catalog.loc[mask, "control_match_score"] = str(score)

    coverage = pd.DataFrame(coverage_rows)
    write_csv(coverage, OUT_CONTROL)

    found = int(coverage["matched_in_source_catalog"].sum()) if len(coverage) else 0
    print(f"Control coverage in source catalog: {found}/{len(coverage)}")
    return catalog


def make_pool(catalog: pd.DataFrame, min_reactions: int, max_rows: int) -> pd.DataFrame:
    catalog = catalog.copy()
    catalog["broad_pool_reason"] = ""

    reaction_mask = catalog["total_ratings_pos_neg"] >= min_reactions
    catalog.loc[reaction_mask, "broad_pool_reason"] = f"reactions>={min_reactions}"

    seed_mask = catalog["is_control_seed"] == True if "is_control_seed" in catalog.columns else False
    catalog.loc[seed_mask & reaction_mask, "broad_pool_reason"] = catalog.loc[seed_mask & reaction_mask, "broad_pool_reason"] + "; control_seed"
    catalog.loc[seed_mask & ~reaction_mask, "broad_pool_reason"] = "control_seed_below_reaction_threshold"

    pool = catalog[reaction_mask | seed_mask].copy()

    pool["sort_control"] = pool["is_control_seed"].astype(int) if "is_control_seed" in pool.columns else 0
    pool = pool.sort_values(
        ["sort_control", "total_ratings_pos_neg", "positive_ratio", "name"],
        ascending=[False, False, False, True],
        na_position="last",
    ).drop(columns=["sort_control"], errors="ignore")

    if max_rows and max_rows > 0:
        pool = pool.head(max_rows).copy()

    pool.reset_index(drop=True, inplace=True)
    pool.insert(0, "broad_rank", range(1, len(pool) + 1))
    return pool


def make_coding(pool: pd.DataFrame) -> pd.DataFrame:
    cols = [
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
    ]
    cols = [c for c in cols if c in pool.columns]
    coding = pool[cols].copy()

    insert_at = 3
    for i, col in enumerate(MANUAL_COLUMNS):
        coding.insert(insert_at + i, col, "")

    return coding


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-reactions", type=int, default=2000)
    parser.add_argument("--max-rows", type=int, default=0, help="0 = unlimited")
    args = parser.parse_args()

    print("Steam broad archetype pool builder MINIMAL v1.0")
    print(f"Output dir: {OUTPUT_DIR.resolve()}")
    print(f"min_reactions={args.min_reactions}")
    print(f"max_rows={'unlimited' if args.max_rows == 0 else args.max_rows}")

    if not MERGED_CATALOG.exists():
        raise FileNotFoundError(f"Missing {MERGED_CATALOG}")

    print(f"Loading merged catalog: {MERGED_CATALOG}")
    raw = read_csv(MERGED_CATALOG)
    catalog = aggregate(raw)
    print(f"Unique appids in source catalog: {len(catalog)}")

    catalog = attach_control(catalog)
    pool = make_pool(catalog, min_reactions=args.min_reactions, max_rows=args.max_rows)
    coding = make_coding(pool)

    write_csv(pool, OUT_POOL)
    write_csv(coding, OUT_CODING)

    print(f"Saved broad pool: {OUT_POOL} ({len(pool)} rows)")
    print(f"Saved coding pool: {OUT_CODING} ({len(coding)} rows)")

    preview_cols = [
        "broad_rank", "appid", "name", "total_ratings_pos_neg",
        "positive_ratio", "broad_pool_reason", "is_control_seed", "control_protagonist",
    ]
    preview_cols = [c for c in preview_cols if c in pool.columns]
    print("\nPreview:")
    print(pool[preview_cols].head(30).to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
