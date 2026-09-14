#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_analyze_reaction_thresholds.py

Analyze how many unique Steam apps/games remain under different reaction-count
thresholds.

No web requests. Reads local CSVs from steam_bulk_outputs/.

Preferred inputs:
- steam_bulk_outputs/steam_catalog_merged.csv

Fallback:
- steam_bulk_outputs/steamspy_all_snapshot.csv
- steam_bulk_outputs/steam_catalog_games.csv + steam_bulk_outputs/steamspy_all_snapshot.csv

Optional:
- steam_archetype_control_100.csv
- steam_bulk_outputs/steam_archetype_control_100.csv

Outputs:
- steam_bulk_outputs/steam_reaction_threshold_report.csv
- steam_bulk_outputs/steam_reaction_threshold_control_coverage.csv
- steam_bulk_outputs/steam_reaction_bands_report.csv
- steam_bulk_outputs/steam_reaction_top_examples.csv

Example:
    python steam_analyze_reaction_thresholds.py
    python steam_analyze_reaction_thresholds.py --thresholds 0,10,50,100,250,500,1000,2500,5000,10000,25000,50000,100000
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

OUT_THRESHOLD_REPORT = OUTPUT_DIR / "steam_reaction_threshold_report.csv"
OUT_CONTROL_COVERAGE = OUTPUT_DIR / "steam_reaction_threshold_control_coverage.csv"
OUT_BANDS_REPORT = OUTPUT_DIR / "steam_reaction_bands_report.csv"
OUT_TOP_EXAMPLES = OUTPUT_DIR / "steam_reaction_top_examples.csv"


DEFAULT_THRESHOLDS = [
    0,
    1,
    10,
    50,
    100,
    250,
    500,
    1000,
    2500,
    5000,
    10000,
    25000,
    50000,
    100000,
    250000,
    500000,
]

POSITIVE_RATIO_CUTS = [None, 0.50, 0.60, 0.70, 0.80]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.csv")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def get_first_existing_col(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


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


def load_source() -> pd.DataFrame:
    if MERGED_CATALOG.exists():
        print(f"Loading merged catalog: {MERGED_CATALOG}")
        df = read_csv(MERGED_CATALOG)
        df["analysis_source"] = str(MERGED_CATALOG)
        return df

    if STEAMSPY_ALL.exists():
        print(f"Loading SteamSpy snapshot: {STEAMSPY_ALL}")
        spy = read_csv(STEAMSPY_ALL)
        if "name" in spy.columns:
            spy = spy.rename(columns={"name": "steamspy_name"})
        if STEAM_CATALOG.exists():
            print(f"Loading Steam catalog: {STEAM_CATALOG}")
            catalog = read_csv(STEAM_CATALOG)
            if "appid" in catalog.columns and "appid" in spy.columns:
                df = catalog.merge(spy, on="appid", how="outer", suffixes=("", "_steamspy"))
                df["analysis_source"] = f"{STEAM_CATALOG}+{STEAMSPY_ALL}"
                return df
        spy["analysis_source"] = str(STEAMSPY_ALL)
        return spy

    raise FileNotFoundError(
        "No usable input found. Expected steam_bulk_outputs/steam_catalog_merged.csv "
        "or steam_bulk_outputs/steamspy_all_snapshot.csv"
    )


def ensure_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "appid" not in df.columns:
        raise RuntimeError("Input has no appid column.")

    df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
    df = df[df["appid"].notna()].copy()
    df["appid"] = df["appid"].astype(int)

    name_col = get_first_existing_col(df, ["name", "steam_name", "steam_catalog_name", "name_from_app_list", "steamspy_name"])
    if name_col is None:
        df["name"] = ""
    elif name_col != "name":
        df["name"] = df[name_col].fillna("")
    else:
        df["name"] = df["name"].fillna("")

    # Positive and negative columns vary by prior script version.
    pos_col = get_first_existing_col(df, ["steamspy_positive", "positive", "total_positive"])
    neg_col = get_first_existing_col(df, ["steamspy_negative", "negative", "total_negative"])

    if "total_ratings_pos_neg" not in df.columns:
        if pos_col and neg_col:
            df["total_ratings_pos_neg"] = (
                pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
                + pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            )
        else:
            df["total_ratings_pos_neg"] = 0
    else:
        df["total_ratings_pos_neg"] = pd.to_numeric(df["total_ratings_pos_neg"], errors="coerce").fillna(0)

    if "positive_ratio" not in df.columns or df["positive_ratio"].isna().all():
        if pos_col and neg_col:
            pos = pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
            neg = pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            denom = pos + neg
            df["positive_ratio"] = pos.where(denom > 0, 0) / denom.where(denom > 0, 1)
        else:
            df["positive_ratio"] = pd.NA
    else:
        df["positive_ratio"] = pd.to_numeric(df["positive_ratio"], errors="coerce")

    owners_col = get_first_existing_col(df, ["steamspy_owners", "owners"])
    if owners_col and owners_col != "steamspy_owners":
        df["steamspy_owners"] = df[owners_col]
    elif "steamspy_owners" not in df.columns:
        df["steamspy_owners"] = ""

    # Collapse duplicate appids.
    df = df.sort_values(["appid", "total_ratings_pos_neg"], ascending=[True, False])
    dedup = df.drop_duplicates(subset=["appid"], keep="first").copy()

    dedup["total_ratings_pos_neg"] = pd.to_numeric(dedup["total_ratings_pos_neg"], errors="coerce").fillna(0).astype(int)
    dedup["has_reaction_data"] = dedup["total_ratings_pos_neg"] > 0
    dedup["name_norm"] = dedup["name"].map(normalize_title)

    return dedup.reset_index(drop=True)


def parse_thresholds(text: str) -> List[int]:
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return sorted(set(out))


def make_threshold_report(df: pd.DataFrame, thresholds: List[int]) -> pd.DataFrame:
    total_unique = len(df)
    with_reaction_data = int((df["total_ratings_pos_neg"] > 0).sum())

    rows = []
    for threshold in thresholds:
        base_mask = df["total_ratings_pos_neg"] >= threshold
        for ratio_cut in POSITIVE_RATIO_CUTS:
            if ratio_cut is None:
                mask = base_mask
                label = "any"
            else:
                mask = base_mask & (pd.to_numeric(df["positive_ratio"], errors="coerce") >= ratio_cut)
                label = f">={ratio_cut:.2f}"

            count = int(mask.sum())
            rows.append({
                "min_reactions": threshold,
                "min_positive_ratio": label,
                "unique_apps": count,
                "percent_of_all_unique_apps": count / total_unique if total_unique else 0,
                "percent_of_apps_with_any_reactions": count / with_reaction_data if with_reaction_data else 0,
                "total_unique_apps_in_source": total_unique,
                "apps_with_any_reactions": with_reaction_data,
            })

    return pd.DataFrame(rows)


def make_bands_report(df: pd.DataFrame, thresholds: List[int]) -> pd.DataFrame:
    # Create adjacent bands: [0,1), [1,10), ..., [last, inf)
    thresholds = sorted(set(thresholds))
    rows = []

    for i, low in enumerate(thresholds):
        high = thresholds[i + 1] if i + 1 < len(thresholds) else None
        if high is None:
            mask = df["total_ratings_pos_neg"] >= low
            label = f">={low}"
        else:
            mask = (df["total_ratings_pos_neg"] >= low) & (df["total_ratings_pos_neg"] < high)
            label = f"{low}-{high - 1}"

        subset = df[mask]
        rows.append({
            "reaction_band": label,
            "min_inclusive": low,
            "max_exclusive": high,
            "unique_apps": len(subset),
            "median_reactions": float(subset["total_ratings_pos_neg"].median()) if len(subset) else None,
            "median_positive_ratio": float(pd.to_numeric(subset["positive_ratio"], errors="coerce").median()) if len(subset) else None,
        })

    return pd.DataFrame(rows)


def make_top_examples(df: pd.DataFrame, n: int = 1000) -> pd.DataFrame:
    cols = [
        "appid",
        "name",
        "total_ratings_pos_neg",
        "positive_ratio",
        "steamspy_owners",
    ]
    cols = [c for c in cols if c in df.columns]
    return df.sort_values(
        ["total_ratings_pos_neg", "positive_ratio", "name"],
        ascending=[False, False, True],
        na_position="last",
    )[cols].head(n).reset_index(drop=True)


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


def make_control_coverage(df: pd.DataFrame, thresholds: List[int]) -> Optional[pd.DataFrame]:
    control_path = find_control_list()
    if control_path is None:
        print("No control list found; skipping control threshold coverage.")
        return None

    control = read_csv(control_path)
    if "steam_search_title" not in control.columns:
        print("Control list has no steam_search_title; skipping control threshold coverage.")
        return None

    control_rows = []
    for _, row in control.iterrows():
        appid, matched_name, score = best_title_match(str(row["steam_search_title"]), df)
        reactions = None
        positive_ratio = None
        if appid is not None:
            hit = df[df["appid"] == appid]
            if not hit.empty:
                reactions = int(hit.iloc[0]["total_ratings_pos_neg"])
                pr = hit.iloc[0].get("positive_ratio")
                try:
                    positive_ratio = float(pr)
                except Exception:
                    positive_ratio = None

        base = row.to_dict()
        base.update({
            "matched_appid": appid,
            "matched_name": matched_name,
            "match_score": score,
            "total_ratings_pos_neg": reactions,
            "positive_ratio": positive_ratio,
        })
        control_rows.append(base)

    controls = pd.DataFrame(control_rows)

    rows = []
    total_controls = len(controls)
    matched_controls = int(controls["matched_appid"].notna().sum())
    for threshold in thresholds:
        mask = controls["matched_appid"].notna() & (pd.to_numeric(controls["total_ratings_pos_neg"], errors="coerce") >= threshold)
        count = int(mask.sum())
        rows.append({
            "min_reactions": threshold,
            "control_titles_total": total_controls,
            "control_titles_matched_in_catalog": matched_controls,
            "control_titles_above_threshold": count,
            "control_coverage_of_all_control_titles": count / total_controls if total_controls else 0,
            "control_coverage_of_matched_control_titles": count / matched_controls if matched_controls else 0,
        })

    coverage = pd.DataFrame(rows)

    # Also append per-title details after a separator-like column by writing a separate block would be awkward in CSV,
    # so we only write summary here. Per-title report can be made from controls if needed.
    write_csv(controls, OUTPUT_DIR / "steam_reaction_threshold_control_title_details.csv")
    return coverage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--thresholds",
        default=",".join(str(x) for x in DEFAULT_THRESHOLDS),
        help="Comma-separated reaction thresholds.",
    )
    args = parser.parse_args()

    thresholds = parse_thresholds(args.thresholds)

    print("Steam reaction-threshold analyzer")
    print(f"Output dir: {OUTPUT_DIR.resolve()}")
    print(f"Thresholds: {thresholds}")

    raw = load_source()
    df = ensure_metrics(raw)

    print(f"Unique appids in source: {len(df)}")
    print(f"Apps with at least 1 reaction: {(df['total_ratings_pos_neg'] > 0).sum()}")

    threshold_report = make_threshold_report(df, thresholds)
    bands_report = make_bands_report(df, thresholds)
    top_examples = make_top_examples(df, n=1000)

    write_csv(threshold_report, OUT_THRESHOLD_REPORT)
    write_csv(bands_report, OUT_BANDS_REPORT)
    write_csv(top_examples, OUT_TOP_EXAMPLES)

    print(f"Saved threshold report: {OUT_THRESHOLD_REPORT}")
    print(f"Saved bands report: {OUT_BANDS_REPORT}")
    print(f"Saved top examples: {OUT_TOP_EXAMPLES}")

    control_coverage = make_control_coverage(df, thresholds)
    if control_coverage is not None:
        write_csv(control_coverage, OUT_CONTROL_COVERAGE)
        print(f"Saved control coverage report: {OUT_CONTROL_COVERAGE}")

    print("\nThreshold summary, all positive ratios:")
    summary = threshold_report[threshold_report["min_positive_ratio"] == "any"][
        [
            "min_reactions",
            "unique_apps",
            "percent_of_all_unique_apps",
            "percent_of_apps_with_any_reactions",
        ]
    ].copy()
    summary["percent_of_all_unique_apps"] = (summary["percent_of_all_unique_apps"] * 100).round(2)
    summary["percent_of_apps_with_any_reactions"] = (summary["percent_of_apps_with_any_reactions"] * 100).round(2)
    print(summary.to_string(index=False))

    if control_coverage is not None:
        print("\nControl coverage by threshold:")
        cc = control_coverage.copy()
        cc["control_coverage_of_all_control_titles"] = (cc["control_coverage_of_all_control_titles"] * 100).round(2)
        cc["control_coverage_of_matched_control_titles"] = (cc["control_coverage_of_matched_control_titles"] * 100).round(2)
        print(cc.to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
