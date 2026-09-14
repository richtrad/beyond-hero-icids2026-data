#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_refine_candidates_v2_validate.py

Second-pass local-only refiner for the Steam archetype corpus.

Purpose
-------
The first bulk pipeline is intentionally recall-heavy. This script makes a stricter
candidate list for games with usable protagonists and validates it against a
manual control/seed list of games with clear protagonists.

It does NOT download anything.
It reads CSV files from steam_bulk_outputs/ and writes CSV reports.

Expected inputs, all optional except a candidate or merged catalog:
- steam_bulk_outputs/steam_catalog_candidates_refined.csv
- steam_bulk_outputs/steam_catalog_candidates.csv
- steam_bulk_outputs/steam_catalog_merged.csv
- steam_bulk_outputs/steamspy_all_snapshot.csv
- steam_archetype_control_100.csv OR steam_bulk_outputs/steam_archetype_control_100.csv

Outputs:
- steam_bulk_outputs/steam_catalog_candidates_refined_v2.csv
- steam_bulk_outputs/steam_catalog_candidates_refined_v2_quarantine.csv
- steam_bulk_outputs/steam_control_recall_report.csv
- steam_bulk_outputs/steam_control_missing_from_candidates.csv
- steam_bulk_outputs/steam_control_found_in_candidates.csv
"""

from __future__ import annotations

import ast
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

BASE_DIR = Path(".")
OUTPUT_DIR = Path("steam_bulk_outputs")

CANDIDATE_INPUTS = [
    OUTPUT_DIR / "steam_catalog_candidates_refined.csv",
    OUTPUT_DIR / "steam_catalog_candidates.csv",
    OUTPUT_DIR / "steam_catalog_merged.csv",
]

MERGED_CATALOG = OUTPUT_DIR / "steam_catalog_merged.csv"
STEAMSPY_ALL = OUTPUT_DIR / "steamspy_all_snapshot.csv"

CONTROL_LIST_CANDIDATES = [
    BASE_DIR / "steam_archetype_control_100.csv",
    OUTPUT_DIR / "steam_archetype_control_100.csv",
]

OUT_REFINED_V2 = OUTPUT_DIR / "steam_catalog_candidates_refined_v2.csv"
OUT_QUARANTINE = OUTPUT_DIR / "steam_catalog_candidates_refined_v2_quarantine.csv"
OUT_CONTROL_REPORT = OUTPUT_DIR / "steam_control_recall_report.csv"
OUT_CONTROL_MISSING = OUTPUT_DIR / "steam_control_missing_from_candidates.csv"
OUT_CONTROL_FOUND = OUTPUT_DIR / "steam_control_found_in_candidates.csv"


# ---------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------

HARD_NARRATIVE_TERMS = {
    "story rich",
    "choices matter",
    "multiple endings",
    "interactive fiction",
    "visual novel",
    "narrative",
    "dialogue heavy",
    "choose your own adventure",
}

DETECTIVE_STORY_TERMS = {
    "detective",
    "investigation",
    "mystery",
    "conversation",
    "dynamic narration",
    "lore rich",
}

PROTAGONIST_REPRESENTATION_TERMS = {
    "female protagonist",
    "character customization",
    "multiple protagonists",
}

CHARACTER_RPG_TERMS = {
    "crpg",
    "party based rpg",
    "action rpg",
    "jrpg",
    "tactical rpg",
    "strategy rpg",
    "role playing",
}

BROAD_SUPPORT_TERMS = {
    "action",
    "adventure",
    "singleplayer",
    "rpg",
    "simulation",
    "strategy",
    "first person",
    "third person",
    "fps",
    "shooter",
    "platformer",
    "survival",
    "open world",
    "sandbox",
    "stealth",
    "horror",
}

SYSTEMIC_TERMS = {
    "strategy",
    "rts",
    "turn based strategy",
    "grand strategy",
    "4x",
    "city builder",
    "colony sim",
    "management",
    "political sim",
    "simulation",
    "base building",
    "god game",
}

TAG_SPAM_COMBO_TERMS = {
    "action rpg",
    "jrpg",
    "survival horror",
    "walking simulator",
    "female protagonist",
    "lovecraftian",
    "god game",
    "party based rpg",
    "tactical rpg",
    "strategy rpg",
    "immersive sim",
}

LOW_PROTAGONIST_CONTEXT_TERMS = {
    "racing",
    "sports",
    "e sports",
    "esports",
    "card game",
    "board game",
    "tabletop",
    "casual",
    "arcade",
    "puzzle",
    "hidden object",
    "city builder",
    "colony sim",
    "management",
    "strategy",
    "simulation",
    "rts",
    "4x",
    "grand strategy",
    "sandbox",
}

TITLE_QUARANTINE_PATTERNS = [
    r"\bgarfield kart\b",
    r"^uno$",
    r"\bflash(?:ing)? lights\b",
    r"\bworkers\s*&\s*resources\b",
    r"\bmanor lords\b",
    r"\bagainst the storm\b",
]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

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
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"[\u2122\u00ae\u00a9]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(definitive|enhanced|complete|ultimate|remastered|remaster|director s cut|edition|collection|hd|windows|intergrade|reunion|the final cut)\b",
        " ",
        s,
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_term(s: object) -> str:
    s = "" if pd.isna(s) else str(s)
    s = s.lower()
    s = s.replace("-", " ").replace("_", " ")
    s = s.replace("™", "").replace("®", "").replace("©", "")
    s = re.sub(r"[^a-z0-9]+", " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def split_terms(value: object) -> List[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass

    if ";" in text:
        return [x.strip() for x in text.split(";") if x.strip()]

    if "," in text:
        return [x.strip() for x in text.split(",") if x.strip()]

    return [text]


def get_first_existing_col(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def extract_terms_from_row(row: pd.Series) -> List[str]:
    term_cols = [
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

    terms: List[str] = []
    for col in term_cols:
        if col in row.index:
            terms.extend(split_terms(row.get(col)))

    return sorted(set(t for t in terms if t))


def title_matches_quarantine(name: object) -> bool:
    n = normalize_title(name)
    for pat in TITLE_QUARANTINE_PATTERNS:
        if re.search(pat, n, flags=re.IGNORECASE):
            return True
    return False


def compute_scores(row: pd.Series) -> Dict[str, object]:
    name = row.get("name", row.get("steam_name", row.get("steam_search_title", "")))
    terms = extract_terms_from_row(row)
    norm_terms = {normalize_term(t) for t in terms}

    hard = norm_terms & HARD_NARRATIVE_TERMS
    detective = norm_terms & DETECTIVE_STORY_TERMS
    repr_terms = norm_terms & PROTAGONIST_REPRESENTATION_TERMS
    char_rpg = norm_terms & CHARACTER_RPG_TERMS
    broad = norm_terms & BROAD_SUPPORT_TERMS
    systemic = norm_terms & SYSTEMIC_TERMS
    low_context = norm_terms & LOW_PROTAGONIST_CONTEXT_TERMS
    spam_combo = norm_terms & TAG_SPAM_COMBO_TERMS

    score = 0
    score += 6 * len(hard)
    score += 4 * len(detective)
    score += 3 * len(repr_terms)
    score += 3 * len(char_rpg)
    score += 1 * min(len(broad), 3)

    if len(hard) >= 2:
        score += 8
    if "story rich" in norm_terms and ("choices matter" in norm_terms or "multiple endings" in norm_terms):
        score += 6
    if "detective" in norm_terms and ("investigation" in norm_terms or "mystery" in norm_terms):
        score += 5
    if "visual novel" in norm_terms and (
        "choices matter" in norm_terms or "multiple endings" in norm_terms or "interactive fiction" in norm_terms
    ):
        score += 5
    if "crpg" in norm_terms and (
        "choices matter" in norm_terms or "party based rpg" in norm_terms or "character customization" in norm_terms
    ):
        score += 5

    low_penalty = 0
    if low_context:
        low_penalty += 4 * len(low_context)
    if systemic and not (len(hard) >= 2 or len(detective) >= 2 or "crpg" in norm_terms):
        low_penalty += 5

    hit_count = row.get("hit_tracked_term_count", None)
    try:
        hit_count_int = int(float(hit_count))
    except Exception:
        hit_count_int = len(norm_terms)

    tag_spam_penalty = 0
    if hit_count_int >= 18 and len(spam_combo) >= 5:
        tag_spam_penalty += 18
    if hit_count_int >= 24 and len(spam_combo) >= 4:
        tag_spam_penalty += 22

    title_quarantine = title_matches_quarantine(name)
    title_penalty = 40 if title_quarantine else 0

    final_score = score - low_penalty - tag_spam_penalty - title_penalty

    if title_quarantine:
        tier = "Q_title_quarantine"
    elif tag_spam_penalty >= 18 and final_score < 40:
        tier = "Q_tagspam"
    elif final_score >= 45 and len(hard | detective | char_rpg) >= 3:
        tier = "A_core_strong"
    elif final_score >= 32 and len(hard | detective | char_rpg | repr_terms) >= 3:
        tier = "B_likely"
    elif final_score >= 22 and len(hard | detective) >= 1:
        tier = "C_possible"
    else:
        tier = "D_weak_or_systemic"

    return {
        "v2_score": final_score,
        "v2_raw_positive_score": score,
        "v2_low_context_penalty": low_penalty,
        "v2_tagspam_penalty": tag_spam_penalty,
        "v2_title_quarantine": title_quarantine,
        "v2_tier": tier,
        "v2_hard_terms": "; ".join(sorted(hard)),
        "v2_detective_terms": "; ".join(sorted(detective)),
        "v2_character_rpg_terms": "; ".join(sorted(char_rpg)),
        "v2_repr_terms": "; ".join(sorted(repr_terms)),
        "v2_low_context_terms": "; ".join(sorted(low_context)),
        "v2_spam_combo_terms": "; ".join(sorted(spam_combo)),
    }


def choose_candidate_input() -> Path:
    for p in CANDIDATE_INPUTS:
        if p.exists():
            return p
    raise FileNotFoundError(
        "No candidate/merged input found. Expected one of:\n"
        + "\n".join(str(p) for p in CANDIDATE_INPUTS)
    )


def load_main_input() -> pd.DataFrame:
    candidate_path = choose_candidate_input()
    print(f"Loading candidate input: {candidate_path}")
    df = read_csv(candidate_path)
    df["source_candidate_file"] = str(candidate_path)

    if STEAMSPY_ALL.exists() and "appid" in df.columns:
        spy = read_csv(STEAMSPY_ALL)
        if "appid" in spy.columns:
            keep = ["appid"] + [c for c in spy.columns if c != "appid" and c not in df.columns]
            if len(keep) > 1:
                print(f"Joining SteamSpy snapshot columns: {STEAMSPY_ALL}")
                df = df.merge(spy[keep], on="appid", how="left", suffixes=("", "_steamspy_all"))

    return df


def ensure_basic_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    name_col = get_first_existing_col(df, ["name", "steam_name", "name_from_app_list", "steam_search_title"])
    if name_col is None:
        df["name"] = ""
    elif name_col != "name":
        df["name"] = df[name_col]

    for col in ["appid", "total_ratings_pos_neg", "positive_ratio", "v2_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "total_ratings_pos_neg" not in df.columns:
        pos_col = get_first_existing_col(df, ["positive", "total_positive"])
        neg_col = get_first_existing_col(df, ["negative", "total_negative"])
        if pos_col and neg_col:
            df["total_ratings_pos_neg"] = (
                pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
                + pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            )
        else:
            df["total_ratings_pos_neg"] = 0

    if "positive_ratio" not in df.columns:
        pos_col = get_first_existing_col(df, ["positive", "total_positive"])
        neg_col = get_first_existing_col(df, ["negative", "total_negative"])
        if pos_col and neg_col:
            pos = pd.to_numeric(df[pos_col], errors="coerce").fillna(0)
            neg = pd.to_numeric(df[neg_col], errors="coerce").fillna(0)
            denom = pos + neg
            df["positive_ratio"] = pos.where(denom > 0, 0) / denom.where(denom > 0, 1)
        else:
            df["positive_ratio"] = None

    return df


def refine_v2(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = ensure_basic_columns(df)

    print("Computing v2 protagonist/narrative scores...")
    score_rows = [compute_scores(row) for _, row in df.iterrows()]
    score_df = pd.DataFrame(score_rows)
    out = pd.concat([df.reset_index(drop=True), score_df], axis=1)

    keep = out["v2_tier"].isin(["A_core_strong", "B_likely", "C_possible"])

    out["total_ratings_pos_neg"] = pd.to_numeric(out["total_ratings_pos_neg"], errors="coerce").fillna(0)
    keep &= out["total_ratings_pos_neg"] >= 300

    refined = out[keep].copy()
    quarantine = out[~keep].copy()

    tier_order = {
        "A_core_strong": 0,
        "B_likely": 1,
        "C_possible": 2,
        "D_weak_or_systemic": 3,
        "Q_tagspam": 4,
        "Q_title_quarantine": 5,
    }

    for d in [refined, quarantine]:
        d["v2_tier_order"] = d["v2_tier"].map(tier_order).fillna(99)
        d.sort_values(
            by=["v2_tier_order", "v2_score", "total_ratings_pos_neg"],
            ascending=[True, False, False],
            inplace=True,
            na_position="last",
        )
        d.drop(columns=["v2_tier_order"], inplace=True, errors="ignore")
        d.reset_index(drop=True, inplace=True)
        d.insert(0, "v2_rank", range(1, len(d) + 1))

    return refined, quarantine


def find_control_list() -> Optional[Path]:
    for p in CONTROL_LIST_CANDIDATES:
        if p.exists():
            return p
    return None


def best_title_match(control_title: str, catalog: pd.DataFrame) -> Tuple[Optional[int], Optional[str], float]:
    if catalog.empty:
        return None, None, 0.0

    target = normalize_title(control_title)
    if not target:
        return None, None, 0.0

    if "norm_name" not in catalog.columns:
        catalog = catalog.copy()
        catalog["norm_name"] = catalog["name"].map(normalize_title)

    exact = catalog[catalog["norm_name"] == target]
    if not exact.empty:
        row = exact.sort_values("total_ratings_pos_neg", ascending=False).iloc[0]
        return int(row["appid"]) if not pd.isna(row.get("appid")) else None, str(row["name"]), 1.0

    contains = catalog[catalog["norm_name"].str.contains(re.escape(target), na=False)]
    if contains.empty:
        contains = catalog[catalog["norm_name"].map(lambda x: target in x or x in target if isinstance(x, str) else False)]

    if not contains.empty:
        row = contains.sort_values("total_ratings_pos_neg", ascending=False).iloc[0]
        score = SequenceMatcher(None, target, str(row["norm_name"])).ratio()
        return int(row["appid"]) if not pd.isna(row.get("appid")) else None, str(row["name"]), float(score)

    target_words = set(target.split())
    if not target_words:
        return None, None, 0.0

    def word_overlap(n: str) -> int:
        return len(target_words & set(str(n).split()))

    tmp = catalog.copy()
    tmp["_overlap"] = tmp["norm_name"].map(word_overlap)
    tmp = tmp[tmp["_overlap"] > 0]
    if tmp.empty:
        return None, None, 0.0

    tmp = tmp.sort_values(["_overlap", "total_ratings_pos_neg"], ascending=[False, False]).head(200)

    best = None
    best_score = 0.0
    for _, row in tmp.iterrows():
        score = SequenceMatcher(None, target, str(row["norm_name"])).ratio()
        if score > best_score:
            best_score = score
            best = row

    if best is not None and best_score >= 0.72:
        return int(best["appid"]) if not pd.isna(best.get("appid")) else None, str(best["name"]), float(best_score)

    return None, None, float(best_score)


def validate_control_list(refined: pd.DataFrame, all_catalog: pd.DataFrame) -> None:
    control_path = find_control_list()
    if control_path is None:
        print("No control list found; skipping control-list validation.")
        print("Expected steam_archetype_control_100.csv in the current folder or steam_bulk_outputs/.")
        return

    print(f"Validating against control list: {control_path}")
    control = read_csv(control_path)
    if "steam_search_title" not in control.columns:
        print("Control list has no steam_search_title column; skipping.")
        return

    catalog = ensure_basic_columns(all_catalog.copy())
    if "name" not in catalog.columns:
        print("All-catalog input has no name column; skipping control matching.")
        return

    catalog["norm_name"] = catalog["name"].map(normalize_title)
    refined_appids = set(pd.to_numeric(refined.get("appid", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))

    rank_map = {}
    if "appid" in refined.columns:
        for idx, appid in enumerate(pd.to_numeric(refined["appid"], errors="coerce"), start=1):
            if not pd.isna(appid):
                rank_map[int(appid)] = idx

    report_rows = []
    for _, row in control.iterrows():
        title = row["steam_search_title"]
        appid, matched_name, score = best_title_match(title, catalog)
        in_refined = bool(appid in refined_appids) if appid is not None else False
        report_rows.append({
            **row.to_dict(),
            "matched_appid": appid,
            "matched_name": matched_name,
            "match_score": score,
            "in_refined_v2": in_refined,
            "refined_v2_rank": rank_map.get(appid),
        })

    report = pd.DataFrame(report_rows)
    write_csv(report, OUT_CONTROL_REPORT)

    found = report[report["in_refined_v2"] == True].copy()
    missing = report[report["in_refined_v2"] != True].copy()
    write_csv(found, OUT_CONTROL_FOUND)
    write_csv(missing, OUT_CONTROL_MISSING)

    total = len(report)
    matched_catalog = report["matched_appid"].notna().sum()
    found_count = len(found)

    print(f"Control titles: {total}")
    print(f"Matched somewhere in catalog: {matched_catalog}/{total}")
    print(f"Found in refined v2 candidates: {found_count}/{total}")
    if total:
        print(f"Control recall@refined_v2: {found_count / total:.1%}")

    if not missing.empty:
        print("\nFirst missing control titles:")
        cols = ["steam_search_title", "protagonist", "matched_name", "match_score"]
        cols = [c for c in cols if c in missing.columns]
        print(missing[cols].head(25).to_string(index=False))


def load_catalog_for_validation(main_df: pd.DataFrame) -> pd.DataFrame:
    if MERGED_CATALOG.exists():
        print(f"Loading merged catalog for control matching: {MERGED_CATALOG}")
        return read_csv(MERGED_CATALOG)
    return main_df


def main() -> None:
    print("Steam candidate refiner v2 + control validation")
    print(f"Working directory: {Path.cwd()}")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")

    main_df = load_main_input()
    main_df = ensure_basic_columns(main_df)

    refined, quarantine = refine_v2(main_df)

    write_csv(refined, OUT_REFINED_V2)
    write_csv(quarantine, OUT_QUARANTINE)

    print(f"Saved refined v2 candidates: {OUT_REFINED_V2} ({len(refined)} rows)")
    print(f"Saved v2 quarantine/non-core rows: {OUT_QUARANTINE} ({len(quarantine)} rows)")

    preview_cols = [
        "appid", "name", "v2_tier", "v2_score", "v2_hard_terms",
        "v2_detective_terms", "v2_character_rpg_terms",
        "v2_low_context_terms", "v2_tagspam_penalty",
        "total_ratings_pos_neg", "positive_ratio",
    ]
    preview_cols = [c for c in preview_cols if c in refined.columns]
    print("\nRefined v2 top candidates preview:")
    print(refined[preview_cols].head(35).to_string(index=False))

    quarantine_preview_cols = [
        "appid", "name", "v2_tier", "v2_score", "v2_low_context_terms",
        "v2_spam_combo_terms", "v2_tagspam_penalty", "v2_title_quarantine",
        "total_ratings_pos_neg",
    ]
    quarantine_preview_cols = [c for c in quarantine_preview_cols if c in quarantine.columns]
    print("\nQuarantine / demoted examples:")
    print(quarantine[quarantine_preview_cols].head(25).to_string(index=False))

    all_catalog = load_catalog_for_validation(main_df)
    validate_control_list(refined, all_catalog)

    print("\nDone.")


if __name__ == "__main__":
    main()
