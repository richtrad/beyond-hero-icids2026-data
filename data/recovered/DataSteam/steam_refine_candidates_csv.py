# -*- coding: utf-8 -*-
"""
steam_refine_candidates_csv.py

Second-pass cleaner for steam_bulk_catalog_builder_csv.py outputs.

It does NOT download anything. It reads the CSV/JSON files created by the bulk
builder and creates a cleaner shortlist for expensive Steam appdetails calls.

Why this exists
---------------
The first bulk version intentionally gathered broad SteamSpy tag/genre hits. That
is useful for recall, but too noisy for ranking: Steam community tags can be
meme/troll/noisy and broad tags such as Action, Adventure, Singleplayer, RPG or
Simulation should not by themselves make a game a good protagonist/narrative
candidate.

This refiner therefore:
- uses SteamSpy weighted/top tags from the raw all-page JSON cache when available;
- treats broad tags as support only, not as primary evidence;
- separates core candidates from popular-control titles;
- penalizes likely tag-spam / contradictory community-tag profiles;
- writes CSV only.

Typical use from the same folder as the original script:
    python steam_refine_candidates_csv.py

Outputs:
    steam_bulk_outputs/steam_catalog_candidates_refined.csv
    steam_bulk_outputs/steam_catalog_candidates_popular_control.csv
    steam_bulk_outputs/steam_catalog_candidates_tagspam_review.csv
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


OUTPUT_DIR = Path("steam_bulk_outputs")
CACHE_DIR = Path("steam_bulk_cache")
STEAMSPY_ALL_JSON_DIR = CACHE_DIR / "steamspy_all_pages"

MERGED_CATALOG_CSV = OUTPUT_DIR / "steam_catalog_merged.csv"
STEAM_CATALOG_CSV = OUTPUT_DIR / "steam_catalog_games.csv"
STEAMSPY_ALL_CSV = OUTPUT_DIR / "steamspy_all_snapshot.csv"
STEAMSPY_HITS_CSV = OUTPUT_DIR / "steamspy_tag_genre_hits.csv"

REFINED_CSV = OUTPUT_DIR / "steam_catalog_candidates_refined.csv"
POPULAR_CONTROL_CSV = OUTPUT_DIR / "steam_catalog_candidates_popular_control.csv"
TAGSPAM_REVIEW_CSV = OUTPUT_DIR / "steam_catalog_candidates_tagspam_review.csv"

# Thresholds. Tune here if needed.
MIN_REACTIONS_CORE_A = 500
MIN_REACTIONS_CORE_B = 1000
MIN_REACTIONS_CORE_C = 5000
POPULAR_CONTROL_TOP_N = 2500
REFINED_LIMIT = 5000
TOP_TAGS_PER_GAME = 12


NARRATIVE_TERMS = {
    "Story Rich",
    "Choices Matter",
    "Multiple Endings",
    "Interactive Fiction",
    "Choose Your Own Adventure",
    "Visual Novel",
    "Lore-Rich",
    "Dialogue Heavy",
    "Narrative",
    "Dynamic Narration",
    "Conversation",
    "Investigation",
    "Detective",
    "Mystery",
}

SPECIFIC_RPG_TERMS = {
    "Action RPG",
    "JRPG",
    "CRPG",
    "Party-Based RPG",
    "Strategy RPG",
    "Tactical RPG",
}

CHARACTER_TERMS = {
    "Female Protagonist",
    "Character Customization",
    "Multiple Protagonists",
}

SPECIFIC_ROLE_WORLD_TERMS = {
    "Immersive Sim",
    "Walking Simulator",
    "Survival Horror",
    "Lovecraftian",
    "Political Sim",
    "Detective",
    "Mystery",
}

# These terms can support inclusion, but should not be a primary reason by themselves.
SUPPORT_TERMS = {
    "RPG",
    "Role-Playing",
    "Adventure",
    "Strategy",
    "Simulation",
    "Management",
    "Grand Strategy",
    "4X",
    "City Builder",
    "Colony Sim",
    "Turn-Based Strategy",
    "RTS",
    "Open World",
    "Sandbox",
    "Stealth",
    "Horror",
    "Survival",
}

# Very broad/noisy tags: useful as metadata, bad as candidate evidence.
BROAD_NOISE_TERMS = {
    "Action",
    "Singleplayer",
    "First-Person",
    "Third Person",
    "FPS",
    "Shooter",
    "Third-Person Shooter",
    "Platformer",
    "Open World",
    "Sandbox",
    "Survival",
    "Horror",
    "Simulation",
    "Strategy",
    "Adventure",
    "RPG",
}

PRIMARY_TERMS = NARRATIVE_TERMS | SPECIFIC_RPG_TERMS | CHARACTER_TERMS | SPECIFIC_ROLE_WORLD_TERMS
ALL_TRACKED_TERMS = PRIMARY_TERMS | SUPPORT_TERMS | BROAD_NOISE_TERMS


def normalize_term(value: Any) -> str:
    s = str(value or "").lower()
    replacements = {
        "™": "",
        "®": "",
        "©": "",
        ":": " ",
        "-": " ",
        "_": " ",
        ".": " ",
        ",": " ",
        "'": "",
        '"': "",
        "’": "",
        "“": "",
        "”": "",
        "(": " ",
        ")": " ",
        "[": " ",
        "]": " ",
        "/": " ",
        "\\": " ",
        "|": " ",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return " ".join(s.split())


def split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except TypeError:
        pass
    if isinstance(value, dict):
        return [str(k).strip() for k in value if str(k).strip()]
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    if not s:
        return []
    return [p.strip() for p in re.split(r"[,;]", s) if p.strip()]


def join_unique(values: Iterable[Any], sep: str = "; ") -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        for term in split_terms(value):
            key = normalize_term(term)
            if key and key not in seen:
                seen.add(key)
                out.append(term)
    return sep.join(out)


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def find_terms(source_terms: Iterable[Any], allowed_terms: set[str]) -> list[str]:
    allowed_norm = {normalize_term(t): t for t in allowed_terms}
    out: list[str] = []
    seen: set[str] = set()
    for term in source_terms:
        norm = normalize_term(term)
        if not norm:
            continue
        # Prefer exact normalized matches. Avoid substring matching here; it was
        # too permissive for noisy Steam community tags.
        if norm in allowed_norm and norm not in seen:
            seen.add(norm)
            out.append(allowed_norm[norm])
    return sorted(out, key=normalize_term)


def parse_steamspy_records(raw: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(raw, list):
        iterable = enumerate(raw)
    elif isinstance(raw, dict):
        iterable = raw.items()
    else:
        return records
    for key, value in iterable:
        if not isinstance(value, dict):
            continue
        row = dict(value)
        if "appid" not in row or row.get("appid") in (None, ""):
            # In SteamSpy all-page data, the outer key is normally appid. For
            # safety, only infer from plausible Steam appid-like keys, not from
            # tiny sequential list indexes.
            try:
                key_int = int(key)
                if key_int >= 10:
                    row["appid"] = key_int
            except (TypeError, ValueError):
                pass
        appid = to_int(row.get("appid"), default=0)
        if appid > 0:
            row["appid"] = appid
            records.append(row)
    return records


def top_tags_from_value(value: Any, max_tags: int = TOP_TAGS_PER_GAME) -> tuple[str, str]:
    """Return (top_tag_names, top_tags_with_scores) from a SteamSpy tags field."""
    if isinstance(value, dict):
        pairs: list[tuple[str, int]] = []
        for tag, score in value.items():
            tag_s = str(tag).strip()
            if not tag_s:
                continue
            pairs.append((tag_s, to_int(score, default=0)))
        pairs.sort(key=lambda kv: kv[1], reverse=True)
        pairs = pairs[:max_tags]
        return "; ".join(tag for tag, _ in pairs), "; ".join(f"{tag}:{score}" for tag, score in pairs)
    if isinstance(value, list):
        tags = [str(x).strip() for x in value if str(x).strip()][:max_tags]
        return "; ".join(tags), "; ".join(tags)
    if isinstance(value, str):
        tags = split_terms(value)[:max_tags]
        return "; ".join(tags), "; ".join(tags)
    return "", ""


def load_weighted_top_tags_from_cache() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not STEAMSPY_ALL_JSON_DIR.exists():
        return pd.DataFrame()
    for path in sorted(STEAMSPY_ALL_JSON_DIR.glob("page_*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                wrapped = json.load(f)
        except Exception:
            continue
        raw = wrapped.get("data", wrapped)
        for rec in parse_steamspy_records(raw):
            appid = to_int(rec.get("appid"), default=0)
            if appid <= 0:
                continue
            top_names, top_with_scores = top_tags_from_value(rec.get("tags"))
            rows.append(
                {
                    "appid": appid,
                    "steamspy_top_tags": top_names,
                    "steamspy_top_tags_with_scores": top_with_scores,
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["appid"], keep="last")
    return df


def build_merged_if_missing() -> pd.DataFrame:
    if MERGED_CATALOG_CSV.exists():
        return read_csv(MERGED_CATALOG_CSV)

    catalog = read_csv(STEAM_CATALOG_CSV)
    spy = read_csv(STEAMSPY_ALL_CSV)
    hits = read_csv(STEAMSPY_HITS_CSV)
    if catalog.empty and spy.empty:
        raise RuntimeError("Cannot find merged catalog or source CSVs. Run the bulk builder first.")

    for df in [catalog, spy, hits]:
        if not df.empty and "appid" in df.columns:
            df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
            df.dropna(subset=["appid"], inplace=True)
            df["appid"] = df["appid"].astype(int)

    if catalog.empty:
        merged = spy.copy()
    elif spy.empty:
        merged = catalog.copy()
    else:
        merged = catalog.merge(spy, on="appid", how="outer")

    if not hits.empty and {"appid", "hit_term"}.issubset(hits.columns):
        agg = hits.groupby("appid").agg(steamspy_hit_terms=("hit_term", join_unique)).reset_index()
        merged = merged.merge(agg, on="appid", how="left")
    else:
        merged["steamspy_hit_terms"] = ""
    return merged


def refine_candidates(limit: int = REFINED_LIMIT) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    merged = build_merged_if_missing()
    if merged.empty:
        raise RuntimeError("Merged catalog is empty.")

    merged["appid"] = pd.to_numeric(merged["appid"], errors="coerce")
    merged = merged[merged["appid"].notna()].copy()
    merged["appid"] = merged["appid"].astype(int)

    top_tags = load_weighted_top_tags_from_cache()
    if not top_tags.empty:
        # Replace/augment older string-only steamspy_tags with weighted top tags
        # from raw cache pages. This avoids treating every meme tag as equal.
        merged = merged.merge(top_tags, on="appid", how="left")
    else:
        merged["steamspy_top_tags"] = merged.get("steamspy_tags", "")
        merged["steamspy_top_tags_with_scores"] = ""

    if "name" not in merged.columns:
        name_cols = [c for c in ["steamspy_name", "steam_catalog_name"] if c in merged.columns]
        if name_cols:
            merged["name"] = merged[name_cols].bfill(axis=1).iloc[:, 0]
        else:
            merged["name"] = ""

    # Ensure popularity columns.
    if "total_ratings_pos_neg" not in merged.columns:
        pos = pd.to_numeric(merged.get("steamspy_positive", 0), errors="coerce").fillna(0)
        neg = pd.to_numeric(merged.get("steamspy_negative", 0), errors="coerce").fillna(0)
        merged["total_ratings_pos_neg"] = pos + neg
    merged["total_ratings_pos_neg"] = pd.to_numeric(merged["total_ratings_pos_neg"], errors="coerce").fillna(0).astype(int)
    if "positive_ratio" not in merged.columns:
        pos = pd.to_numeric(merged.get("steamspy_positive", 0), errors="coerce").fillna(0)
        merged["positive_ratio"] = pos / merged["total_ratings_pos_neg"].replace({0: pd.NA})

    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        genre_terms = split_terms(row.get("steamspy_genre"))
        top_tag_terms = split_terms(row.get("steamspy_top_tags"))
        hit_terms = split_terms(row.get("steamspy_hit_terms"))

        base_terms = genre_terms + top_tag_terms
        primary_base = find_terms(base_terms, PRIMARY_TERMS)
        support_base = find_terms(base_terms, SUPPORT_TERMS)
        broad_base = find_terms(base_terms, BROAD_NOISE_TERMS)

        # Hit terms are lower-trust: only use them as weak evidence if the game
        # has no usable weighted top tags. This prevents tag-query spam from
        # dominating the shortlist.
        hit_primary = []
        if not top_tag_terms:
            hit_primary = find_terms(hit_terms, PRIMARY_TERMS)

        all_primary = join_unique(primary_base + hit_primary)
        all_support = join_unique(support_base)
        all_broad = join_unique(broad_base)

        primary_count = len(split_terms(all_primary))
        support_count = len(split_terms(all_support))
        broad_count = len(split_terms(all_broad))
        hit_count = len(find_terms(hit_terms, ALL_TRACKED_TERMS))
        reactions = to_int(row.get("total_ratings_pos_neg"), default=0)

        # Heuristic: many query-hit terms but few/no top-tag primary terms =
        # likely Steam community meme/noise. Keep it for review, but downgrade.
        possible_tagspam = hit_count >= 15 and len(primary_base) <= 1

        tier = ""
        reason = ""
        if reactions >= MIN_REACTIONS_CORE_A and primary_count >= 2:
            tier = "A_core_strong"
            reason = f">=2 primary top-tag signals and reactions>={MIN_REACTIONS_CORE_A}"
        elif reactions >= MIN_REACTIONS_CORE_B and primary_count >= 1 and support_count >= 1:
            tier = "B_core_supported"
            reason = f">=1 primary + support signal and reactions>={MIN_REACTIONS_CORE_B}"
        elif reactions >= MIN_REACTIONS_CORE_C and primary_count >= 1:
            tier = "C_core_popular"
            reason = f">=1 primary signal and reactions>={MIN_REACTIONS_CORE_C}"
        elif reactions > 0:
            tier = "D_popular_control_candidate"
            reason = "popular/control pool only; not enough core signals"

        # Downgrade likely tagspam unless there are at least two primary top-tag signals.
        if possible_tagspam and tier in {"B_core_supported", "C_core_popular"} and len(primary_base) < 2:
            tier = "D_tagspam_review"
            reason = "downgraded: many broad/query-hit terms but weak primary top-tag evidence"

        rows.append(
            {
                **row.to_dict(),
                "primary_terms": all_primary,
                "support_terms": all_support,
                "broad_terms": all_broad,
                "primary_term_count": primary_count,
                "support_term_count": support_count,
                "broad_term_count": broad_count,
                "hit_tracked_term_count": hit_count,
                "possible_tagspam": possible_tagspam,
                "refined_tier": tier,
                "refined_reason": reason,
            }
        )

    refined_all = pd.DataFrame(rows)
    refined_all = refined_all.sort_values("total_ratings_pos_neg", ascending=False, na_position="last").reset_index(drop=True)
    refined_all["reaction_rank"] = range(1, len(refined_all) + 1)

    core = refined_all[refined_all["refined_tier"].isin(["A_core_strong", "B_core_supported", "C_core_popular"])].copy()

    tier_order = {"A_core_strong": 0, "B_core_supported": 1, "C_core_popular": 2}
    core["tier_order"] = core["refined_tier"].map(tier_order).fillna(99)
    core = core.sort_values(
        ["tier_order", "primary_term_count", "total_ratings_pos_neg", "positive_ratio"],
        ascending=[True, False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    if limit and limit > 0:
        core = core.head(limit).copy()
    core = core.drop(columns=["tier_order"], errors="ignore")

    popular = refined_all[
        (~refined_all["appid"].isin(core["appid"]))
        & (refined_all["total_ratings_pos_neg"] > 0)
    ].sort_values("total_ratings_pos_neg", ascending=False).head(POPULAR_CONTROL_TOP_N).copy()

    tagspam = refined_all[refined_all["possible_tagspam"] == True].sort_values(  # noqa: E712
        ["hit_tracked_term_count", "total_ratings_pos_neg"], ascending=[False, False]
    ).head(500).copy()

    # Friendly column order.
    front = [
        "appid",
        "name",
        "refined_tier",
        "refined_reason",
        "primary_terms",
        "support_terms",
        "broad_terms",
        "primary_term_count",
        "support_term_count",
        "hit_tracked_term_count",
        "possible_tagspam",
        "total_ratings_pos_neg",
        "positive_ratio",
        "steamspy_owners",
        "steamspy_genre",
        "steamspy_top_tags",
        "steamspy_top_tags_with_scores",
    ]
    def reorder(df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in front if c in df.columns] + [c for c in df.columns if c not in front]
        return df[cols]

    core = reorder(core)
    popular = reorder(popular)
    tagspam = reorder(tagspam)

    write_csv(core, REFINED_CSV)
    write_csv(popular, POPULAR_CONTROL_CSV)
    write_csv(tagspam, TAGSPAM_REVIEW_CSV)
    return core, popular, tagspam


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=REFINED_LIMIT, help="Maximum refined core candidates to write. 0 = all.")
    args = parser.parse_args()

    print("Steam candidate refiner")
    print(f"Reading from: {OUTPUT_DIR.resolve()}")
    print(f"Using raw SteamSpy cache if present: {STEAMSPY_ALL_JSON_DIR.resolve()}")
    core, popular, tagspam = refine_candidates(limit=args.limit)

    print(f"Saved refined core candidates: {REFINED_CSV} ({len(core)} rows)")
    print(f"Saved popular/control pool: {POPULAR_CONTROL_CSV} ({len(popular)} rows)")
    print(f"Saved tag-spam review sample: {TAGSPAM_REVIEW_CSV} ({len(tagspam)} rows)")

    preview_cols = [
        "appid",
        "name",
        "refined_tier",
        "primary_terms",
        "support_terms",
        "total_ratings_pos_neg",
        "positive_ratio",
    ]
    existing = [c for c in preview_cols if c in core.columns]
    if existing:
        print("\nRefined top candidates preview:")
        print(core[existing].head(30).to_string(index=False))

    if not tagspam.empty:
        existing_spam = [c for c in ["appid", "name", "primary_terms", "hit_tracked_term_count", "total_ratings_pos_neg"] if c in tagspam.columns]
        print("\nLikely tag-spam/noisy examples to inspect:")
        print(tagspam[existing_spam].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
