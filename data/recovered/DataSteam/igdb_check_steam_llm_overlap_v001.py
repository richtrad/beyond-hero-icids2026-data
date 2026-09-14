#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
igdb_check_steam_llm_overlap_v001.py

Estimate how many IGDB master-catalog games already have LLM protagonist/archetype
annotations in the existing Steam dataset.

Primary high-confidence method:
  IGDB external_games -> Steam appid -> Steam LLM dataset appid.

Fallback lower-confidence method:
  normalized title exact match.

No OpenAI calls. No LLM cost.

Default inputs:
  IGDB:
    igdb_outputs/master_candidates_v001/igdb_master_broad_analysis_years_v001.csv

  Steam LLM:
    steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv

Default output:
  igdb_outputs/master_steam_llm_overlap_v001/

Required for external-ID matching:
  IGDB_CLIENT_ID
  IGDB_CLIENT_SECRET

Optional:
  IGDB_ACCESS_TOKEN

Useful runs:
  # full: external_games + title fallback
  python igdb_check_steam_llm_overlap_v001.py

  # faster local-only title match, no IGDB API
  python igdb_check_steam_llm_overlap_v001.py --no-api

  # resume external_games cache if interrupted
  python igdb_check_steam_llm_overlap_v001.py --resume

  # rebuild output folder intentionally
  python igdb_check_steam_llm_overlap_v001.py --overwrite

Notes:
- External Steam appid matching is much more reliable than title matching.
- Title matching can overmatch generic names and editions; it is marked separately.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_IGDB = Path("igdb_outputs/master_candidates_v001/igdb_master_broad_analysis_years_v001.csv")
DEFAULT_STEAM = Path("steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv")
DEFAULT_OUTDIR = Path("igdb_outputs/master_steam_llm_overlap_v001")

VALID_ARCHETYPES_12 = {
    "Innocent",
    "Everyman/Orphan",
    "Hero/Warrior",
    "Caregiver/Guardian",
    "Explorer/Seeker",
    "Rebel/Outlaw",
    "Lover",
    "Creator/Artist",
    "Jester/Trickster",
    "Sage/Investigator",
    "Magician/Transformer",
    "Ruler/Leader",
}

EDITION_WORDS = [
    "game of the year",
    "goty",
    "definitive edition",
    "special edition",
    "complete edition",
    "anniversary edition",
    "ultimate edition",
    "collector s edition",
    "collectors edition",
    "deluxe edition",
    "remastered",
    "remaster",
    "enhanced edition",
    "director s cut",
    "directors cut",
    "legacy",
    "classic",
    "hd",
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def obtain_igdb_token() -> str:
    existing = os.environ.get("IGDB_ACCESS_TOKEN", "").strip()
    if existing:
        return existing

    client_id = get_env("IGDB_CLIENT_ID")
    client_secret = get_env("IGDB_CLIENT_SECRET")

    url = (
        "https://id.twitch.tv/oauth2/token?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        })
    )
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    token = data.get("access_token", "")
    if not token:
        raise RuntimeError(f"Could not obtain IGDB token: {data}")
    os.environ["IGDB_ACCESS_TOKEN"] = token
    return token


def safe_prepare_outdir(outdir: Path, overwrite: bool, resume: bool) -> None:
    marker = outdir / "_COMPLETED_steam_llm_overlap_v001.txt"
    if overwrite and resume:
        raise RuntimeError("Use either --overwrite or --resume, not both.")
    if outdir.exists() and marker.exists() and not overwrite and not resume:
        raise RuntimeError(
            f"Output folder already contains completed results: {outdir}\n"
            f"Use --resume, --overwrite, or --outdir with a new folder."
        )
    if outdir.exists() and overwrite:
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)


def normalize_title(title: Any) -> str:
    s = str(title or "").lower()
    s = s.replace("™", "").replace("®", "")
    s = re.sub(r"\((?:19|20)\d{2}\)", " ", s)
    s = re.sub(r"\[(?:19|20)\d{2}\]", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"['’]", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    for w in EDITION_WORDS:
        s = re.sub(r"\b" + re.escape(w) + r"\b", " ", s)
    s = re.sub(r"\bthe\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def read_csv(path: Path, id_cols: list[str] | None = None) -> pd.DataFrame:
    dtype = {}
    for c in id_cols or []:
        dtype[c] = str
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def candidate_column(df: pd.DataFrame, names: list[str]) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def prepare_steam_annotations(steam: pd.DataFrame) -> pd.DataFrame:
    out = steam.copy()
    if "appid" not in out.columns:
        raise RuntimeError("Steam dataset must contain appid column.")
    if "name" not in out.columns:
        raise RuntimeError("Steam dataset must contain name column.")

    out["appid"] = out["appid"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    out["steam_name"] = out["name"].astype(str)
    out["steam_title_norm"] = out["steam_name"].map(normalize_title)

    primary_col = candidate_column(out, [
        "primary_archetype_12",
        "llm6_primary_archetype",
        "primary_archetype",
    ])
    secondary_col = candidate_column(out, [
        "secondary_archetype_12",
        "llm6_secondary_archetype",
        "secondary_archetype",
    ])
    tertiary_col = candidate_column(out, [
        "tertiary_archetype_12",
        "llm6_tertiary_archetype",
        "tertiary_archetype",
    ])
    protagonist_col = candidate_column(out, [
        "protagonist_name",
        "llm6_protagonist_name",
        "main_protagonist",
        "llm6_main_protagonist",
        "character_name",
        "llm6_character_name",
    ])

    out["steam_primary_archetype_12_like"] = out[primary_col].astype(str).str.strip() if primary_col else ""
    out["steam_secondary_archetype_12_like"] = out[secondary_col].astype(str).str.strip() if secondary_col else ""
    out["steam_tertiary_archetype_12_like"] = out[tertiary_col].astype(str).str.strip() if tertiary_col else ""
    out["steam_protagonist_like"] = out[protagonist_col].astype(str).str.strip() if protagonist_col else ""

    # Generic LLM result presence.
    llm_cols = [c for c in out.columns if c.lower().startswith("llm") or "archetype" in c.lower() or "protagonist" in c.lower()]
    out["steam_has_any_llm_columns"] = bool(llm_cols)

    primary_valid = out["steam_primary_archetype_12_like"].isin(VALID_ARCHETYPES_12)

    bad_proto = {"", "nan", "none", "unknown", "uncertain", "n/a", "na", "no clear protagonist", "no protagonist"}
    proto_ok = ~out["steam_protagonist_like"].astype(str).str.lower().str.strip().isin(bad_proto)

    # If protagonist column is absent, still count valid archetype as usable but mark separately.
    out["steam_has_valid_12_primary"] = primary_valid
    out["steam_has_protagonist_name_like"] = proto_ok if protagonist_col else False
    out["steam_has_usable_llm_annotation"] = primary_valid

    # Ranking if duplicates exist.
    if "selection_rank" in out.columns:
        out["_steam_rank"] = pd.to_numeric(out["selection_rank"], errors="coerce").fillna(10**12)
    else:
        out["_steam_rank"] = range(len(out))

    rating_cols = ["total_ratings_pos_neg", "total_reviews", "reviews_total", "positive_plus_negative"]
    rating_col = candidate_column(out, rating_cols)
    if rating_col:
        out["_steam_rating_count"] = pd.to_numeric(out[rating_col], errors="coerce").fillna(0)
    else:
        out["_steam_rating_count"] = 0

    out = out.sort_values(["appid", "steam_has_usable_llm_annotation", "_steam_rating_count", "_steam_rank"],
                          ascending=[True, False, False, True])
    out = out.drop_duplicates(subset=["appid"], keep="first").copy()

    return out


def igdb_post_external_games(body: str) -> list[dict[str, Any]]:
    token = obtain_igdb_token()
    client_id = get_env("IGDB_CLIENT_ID")

    req = urllib.request.Request(
        "https://api.igdb.com/v4/external_games",
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "text/plain",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def fetch_external_games_for_ids(ids: list[str], chunk_size: int, limit: int, delay: float, outdir: Path, resume: bool) -> pd.DataFrame:
    cache_path = outdir / "igdb_external_games_cache_v001.csv"

    cached = pd.DataFrame()
    if resume and cache_path.exists():
        cached = pd.read_csv(cache_path, dtype={"game": str, "uid": str}, low_memory=False)

    cached_games = set(cached["game"].astype(str).tolist()) if not cached.empty and "game" in cached.columns else set()
    ids_to_fetch = [str(i) for i in ids if str(i) not in cached_games]

    rows = cached.to_dict("records") if not cached.empty else []

    print(f"External-games cache rows: {len(rows)}")
    print(f"IGDB ids total: {len(ids)}")
    print(f"IGDB ids to fetch: {len(ids_to_fetch)}")

    for start in range(0, len(ids_to_fetch), chunk_size):
        chunk = ids_to_fetch[start:start + chunk_size]
        games_expr = ",".join(chunk)

        offset = 0
        page = 0
        while True:
            page += 1
            body = (
                "fields game,uid,name,url,category,external_game_source.name,external_game_source.id; "
                f"where game = ({games_expr}); "
                f"limit {limit}; offset {offset};"
            )

            try:
                data = igdb_post_external_games(body)
            except Exception as exc:
                # fallback without expanded source
                print(f"  expanded source failed, fallback: {type(exc).__name__}: {exc}")
                body = (
                    "fields game,uid,name,url,category,external_game_source; "
                    f"where game = ({games_expr}); "
                    f"limit {limit}; offset {offset};"
                )
                data = igdb_post_external_games(body)

            for r in data:
                src = r.get("external_game_source", "")
                if isinstance(src, dict):
                    source_name = src.get("name", "")
                    source_id = src.get("id", "")
                else:
                    source_name = ""
                    source_id = src

                rows.append({
                    "game": str(r.get("game", "")),
                    "uid": str(r.get("uid", "")),
                    "external_name": r.get("name", ""),
                    "external_url": r.get("url", ""),
                    "external_category": r.get("category", ""),
                    "external_source_name": source_name,
                    "external_source_id": source_id,
                    "fetched_at": now_iso(),
                })

            print(f"  chunk {start//chunk_size + 1}/{(len(ids_to_fetch)+chunk_size-1)//chunk_size}, page={page}, rows={len(data)}")

            if len(data) < limit:
                # Important: even if no external rows for a game, mark it as checked
                # via pseudo rows? Instead we track by chunk only. Good enough for first pass.
                break

            offset += limit
            if delay > 0:
                time.sleep(delay)

        # Save after every chunk.
        pd.DataFrame(rows).drop_duplicates().to_csv(cache_path, index=False, encoding="utf-8-sig")

        if delay > 0:
            time.sleep(delay)

    result = pd.DataFrame(rows).drop_duplicates()
    result.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return result


def mark_steam_external(external: pd.DataFrame, steam_appids: set[str]) -> pd.DataFrame:
    if external.empty:
        external["is_probable_steam_external"] = []
        return external

    out = external.copy()
    src = out.get("external_source_name", pd.Series("", index=out.index)).astype(str).str.lower()
    url = out.get("external_url", pd.Series("", index=out.index)).astype(str).str.lower()
    uid = out.get("uid", pd.Series("", index=out.index)).astype(str).str.strip()

    out["uid_clean"] = uid.str.replace(r"\.0$", "", regex=True)
    out["is_probable_steam_external"] = (
        src.str.contains("steam", na=False)
        | url.str.contains("steampowered.com|steamcommunity.com", na=False)
    )

    # Strict Steam appid candidate only if it is source/url-marked as Steam.
    out["steam_appid_from_external"] = out["uid_clean"].where(out["is_probable_steam_external"], "")

    # Diagnostic: numeric uid that equals known Steam appid but source not expanded.
    out["uid_matches_known_steam_appid_but_source_unknown"] = (
        out["uid_clean"].isin(steam_appids) & ~out["is_probable_steam_external"]
    )

    return out


def build_title_fallback(igdb: pd.DataFrame, steam: pd.DataFrame) -> pd.DataFrame:
    # Steam duplicate normalized titles are ambiguous; keep only unique norms for fallback.
    steam_norm_counts = steam.groupby("steam_title_norm").size().reset_index(name="steam_norm_count")
    steam_unique = steam.merge(steam_norm_counts, on="steam_title_norm", how="left")
    steam_unique = steam_unique[steam_unique["steam_norm_count"] == 1].copy()

    keep_cols = [
        "appid", "steam_name", "steam_title_norm",
        "steam_primary_archetype_12_like",
        "steam_secondary_archetype_12_like",
        "steam_tertiary_archetype_12_like",
        "steam_protagonist_like",
        "steam_has_valid_12_primary",
        "steam_has_protagonist_name_like",
        "steam_has_usable_llm_annotation",
    ]
    keep_cols = [c for c in keep_cols if c in steam_unique.columns]

    ig = igdb.copy()
    ig["igdb_title_norm"] = ig["name"].map(normalize_title)

    fallback = ig.merge(
        steam_unique[keep_cols],
        left_on="igdb_title_norm",
        right_on="steam_title_norm",
        how="left",
        suffixes=("", "_steam_title"),
    )
    fallback["title_fallback_matched"] = fallback["appid"].notna()
    return fallback


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--igdb", default=str(DEFAULT_IGDB))
    parser.add_argument("--steam", default=str(DEFAULT_STEAM))
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    parser.add_argument("--no-api", action="store_true", help="Skip IGDB external_games fetch; do title-only estimate.")
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--delay", type=float, default=0.30)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    safe_prepare_outdir(outdir, overwrite=args.overwrite, resume=args.resume)

    igdb = read_csv(Path(args.igdb), id_cols=["igdb_id"])
    steam_raw = read_csv(Path(args.steam), id_cols=["appid"])
    steam = prepare_steam_annotations(steam_raw)

    igdb["igdb_id"] = igdb["igdb_id"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    igdb["igdb_name"] = igdb["name"].astype(str)
    igdb["igdb_title_norm"] = igdb["igdb_name"].map(normalize_title)
    igdb["original_release_year_num"] = pd.to_numeric(igdb.get("original_release_year_num", igdb.get("original_release_year", None)), errors="coerce").astype("Int64")

    steam_appids = set(steam["appid"].astype(str).tolist())

    external_steam = pd.DataFrame()
    if not args.no_api:
        ids = igdb["igdb_id"].dropna().astype(str).drop_duplicates().tolist()
        external = fetch_external_games_for_ids(
            ids=ids,
            chunk_size=args.chunk_size,
            limit=args.limit,
            delay=args.delay,
            outdir=outdir,
            resume=args.resume,
        )
        external = mark_steam_external(external, steam_appids)
        external.to_csv(outdir / "igdb_external_games_all_v001.csv", index=False, encoding="utf-8-sig")

        external_steam = external[external["steam_appid_from_external"].astype(str).str.len() > 0].copy()
        external_steam = external_steam.sort_values(["game", "steam_appid_from_external"]).drop_duplicates(subset=["game"], keep="first")
        external_steam.to_csv(outdir / "igdb_external_steam_appids_v001.csv", index=False, encoding="utf-8-sig")

    # Build external/appid match.
    overlap = igdb.copy()

    if not external_steam.empty:
        overlap = overlap.merge(
            external_steam[["game", "steam_appid_from_external", "external_name", "external_url", "external_source_name"]],
            left_on="igdb_id",
            right_on="game",
            how="left",
        )
        overlap = overlap.merge(
            steam,
            left_on="steam_appid_from_external",
            right_on="appid",
            how="left",
            suffixes=("", "_steam_external"),
        )
        overlap["external_steam_matched"] = overlap["steam_appid_from_external"].notna()
        overlap["external_steam_llm_matched"] = overlap["steam_has_usable_llm_annotation"].fillna(False)
    else:
        overlap["steam_appid_from_external"] = ""
        overlap["external_steam_matched"] = False
        overlap["external_steam_llm_matched"] = False

    # Title fallback for rows not matched by external appid.
    title_fb = build_title_fallback(igdb, steam)
    title_cols = {
        "appid": "title_match_appid",
        "steam_name": "title_match_steam_name",
        "steam_primary_archetype_12_like": "title_match_primary_archetype",
        "steam_secondary_archetype_12_like": "title_match_secondary_archetype",
        "steam_tertiary_archetype_12_like": "title_match_tertiary_archetype",
        "steam_protagonist_like": "title_match_protagonist",
        "steam_has_usable_llm_annotation": "title_match_has_usable_llm_annotation",
    }
    title_small_cols = ["igdb_id", "title_fallback_matched"] + [c for c in title_cols.keys() if c in title_fb.columns]
    title_small = title_fb[title_small_cols].rename(columns=title_cols)

    overlap = overlap.merge(title_small, on="igdb_id", how="left")
    overlap["title_fallback_matched"] = overlap["title_fallback_matched"].fillna(False)

    overlap["already_has_steam_llm_annotation_external"] = overlap["external_steam_llm_matched"].fillna(False)
    overlap["already_has_steam_llm_annotation_title_fallback"] = (
        ~overlap["already_has_steam_llm_annotation_external"]
        & overlap.get("title_match_has_usable_llm_annotation", pd.Series(False, index=overlap.index)).fillna(False)
    )
    overlap["already_has_any_steam_llm_annotation"] = (
        overlap["already_has_steam_llm_annotation_external"]
        | overlap["already_has_steam_llm_annotation_title_fallback"]
    )

    overlap["match_method"] = "none"
    overlap.loc[overlap["already_has_steam_llm_annotation_title_fallback"], "match_method"] = "normalized_title_fallback"
    overlap.loc[overlap["already_has_steam_llm_annotation_external"], "match_method"] = "igdb_external_steam_appid"

    already = overlap[overlap["already_has_any_steam_llm_annotation"]].copy()
    needs = overlap[~overlap["already_has_any_steam_llm_annotation"]].copy()

    # Ambiguous title diagnostics.
    steam_norm_counts = steam.groupby("steam_title_norm").size().reset_index(name="steam_norm_count")
    steam_dup_norms = steam_norm_counts[steam_norm_counts["steam_norm_count"] > 1]
    ambiguous = steam.merge(steam_dup_norms[["steam_title_norm", "steam_norm_count"]], on="steam_title_norm", how="inner")
    ambiguous.to_csv(outdir / "steam_ambiguous_normalized_titles_v001.csv", index=False, encoding="utf-8-sig")

    # Counts by year.
    year_counts = overlap.groupby("original_release_year_num", dropna=False).agg(
        igdb_broad_rows=("igdb_id", "count"),
        external_steam_matches=("external_steam_matched", "sum"),
        external_llm_annotations=("already_has_steam_llm_annotation_external", "sum"),
        title_fallback_llm_annotations=("already_has_steam_llm_annotation_title_fallback", "sum"),
        any_steam_llm_annotations=("already_has_any_steam_llm_annotation", "sum"),
    ).reset_index().rename(columns={"original_release_year_num": "original_release_year"})
    year_counts["needs_llm_annotation"] = year_counts["igdb_broad_rows"] - year_counts["any_steam_llm_annotations"]

    # Save outputs.
    overlap.to_csv(outdir / "igdb_master_broad_with_steam_llm_overlap_v001.csv", index=False, encoding="utf-8-sig")
    already.to_csv(outdir / "igdb_already_annotated_from_steam_v001.csv", index=False, encoding="utf-8-sig")
    needs.to_csv(outdir / "igdb_needs_llm_annotation_v001.csv", index=False, encoding="utf-8-sig")
    year_counts.to_csv(outdir / "igdb_overlap_counts_by_year_v001.csv", index=False, encoding="utf-8-sig")

    summary = {
        "created_at": now_iso(),
        "inputs": {
            "igdb": str(Path(args.igdb)),
            "steam": str(Path(args.steam)),
        },
        "settings": {
            "no_api": bool(args.no_api),
            "chunk_size": args.chunk_size,
            "title_fallback": "exact normalized title; ambiguous Steam normalized titles excluded from fallback",
        },
        "rows": {
            "igdb_broad_analysis_rows": int(len(igdb)),
            "steam_rows": int(len(steam)),
            "external_steam_appid_links": int(len(external_steam)) if not external_steam.empty else 0,
            "already_annotated_external_high_confidence": int(overlap["already_has_steam_llm_annotation_external"].sum()),
            "already_annotated_title_fallback_lower_confidence": int(overlap["already_has_steam_llm_annotation_title_fallback"].sum()),
            "already_annotated_any": int(overlap["already_has_any_steam_llm_annotation"].sum()),
            "needs_llm_annotation": int((~overlap["already_has_any_steam_llm_annotation"]).sum()),
            "ambiguous_steam_normalized_title_rows": int(len(ambiguous)),
        },
        "outputs": {
            "overlap": str(outdir / "igdb_master_broad_with_steam_llm_overlap_v001.csv"),
            "already": str(outdir / "igdb_already_annotated_from_steam_v001.csv"),
            "needs": str(outdir / "igdb_needs_llm_annotation_v001.csv"),
            "year_counts": str(outdir / "igdb_overlap_counts_by_year_v001.csv"),
            "external_cache": str(outdir / "igdb_external_games_cache_v001.csv"),
        },
    }
    (outdir / "igdb_steam_llm_overlap_summary_v001.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# IGDB × Steam LLM overlap v001

This folder estimates which IGDB master-catalog games already have Steam-derived
LLM protagonist/archetype annotations.

## Methods

1. High confidence: IGDB `external_games` Steam appid -> Steam `appid`.
2. Lower confidence fallback: exact normalized title match, excluding ambiguous Steam normalized titles.

## Summary

- IGDB broad analysis rows: {len(igdb)}
- Steam rows: {len(steam)}
- External Steam appid links: {int(len(external_steam)) if not external_steam.empty else 0}
- Already annotated, external high confidence: {int(overlap["already_has_steam_llm_annotation_external"].sum())}
- Already annotated, title fallback lower confidence: {int(overlap["already_has_steam_llm_annotation_title_fallback"].sum())}
- Already annotated, any method: {int(overlap["already_has_any_steam_llm_annotation"].sum())}
- Needs LLM annotation: {int((~overlap["already_has_any_steam_llm_annotation"]).sum())}

## Recommended interpretation

Use the external high-confidence count as conservative.
Use the combined count as an upper estimate, because title fallback may include false positives.
"""
    (outdir / "README_igdb_steam_llm_overlap_v001.md").write_text(readme, encoding="utf-8")

    (outdir / "_COMPLETED_steam_llm_overlap_v001.txt").write_text(
        f"Completed at {now_iso()}\nAlready annotated any: {int(overlap['already_has_any_steam_llm_annotation'].sum())}\n",
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print("IGDB × STEAM LLM OVERLAP V001")
    print("=" * 100)
    print(f"IGDB broad analysis rows:                         {len(igdb):>8}")
    print(f"Steam annotation rows:                            {len(steam):>8}")
    print(f"External Steam appid links found:                 {int(len(external_steam)) if not external_steam.empty else 0:>8}")
    print(f"Already annotated via external Steam appid:       {int(overlap['already_has_steam_llm_annotation_external'].sum()):>8}")
    print(f"Already annotated via title fallback:             {int(overlap['already_has_steam_llm_annotation_title_fallback'].sum()):>8}")
    print(f"Already annotated by any method:                  {int(overlap['already_has_any_steam_llm_annotation'].sum()):>8}")
    print(f"Needs LLM annotation:                             {int((~overlap['already_has_any_steam_llm_annotation']).sum()):>8}")
    print()
    print("Saved:")
    print(f"  {outdir / 'igdb_steam_llm_overlap_summary_v001.json'}")
    print(f"  {outdir / 'igdb_overlap_counts_by_year_v001.csv'}")
    print(f"  {outdir / 'igdb_already_annotated_from_steam_v001.csv'}")
    print(f"  {outdir / 'igdb_needs_llm_annotation_v001.csv'}")


if __name__ == "__main__":
    main()
