#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
igdb_build_pre2005_candidate_catalog_v001.py

Build a broad IGDB-based historical catalog of games released before a chosen year,
intended as a candidate pool for later protagonist/archetype annotation.

No OpenAI calls. No LLM cost.

Default:
  fetch IGDB main games with first_release_date from 1970-01-01 to 2005-01-01.

Outputs:
  igdb_outputs/pre2005_candidates_v001/
    igdb_pre2005_raw_main_games_v001.csv
    igdb_pre2005_broad_candidates_v001.csv
    igdb_pre2005_low_priority_review_v001.csv
    igdb_pre2005_year_counts_v001.csv
    igdb_pre2005_decade_counts_v001.csv
    igdb_pre2005_examples_by_year_v001.csv
    igdb_pre2005_summary_v001.json
    README_igdb_pre2005_candidates_v001.md

Required environment variables:
  IGDB_CLIENT_ID
  IGDB_CLIENT_SECRET

Optional:
  IGDB_ACCESS_TOKEN

The script obtains a token automatically if IGDB_ACCESS_TOKEN is missing.

Important:
- This is a broad candidate catalog, not final archetype data.
- It uses IGDB first_release_date as original release date.
- It filters to category=0, i.e. main_game, because the older enum is still
  exposed by IGDB and helps remove DLC, expansions, ports, remasters, etc.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_OUTDIR = Path("igdb_outputs/pre2005_candidates_v001")


POSITIVE_GENRE_KEYWORDS = {
    "adventure",
    "role-playing",
    "rpg",
    "platform",
    "shooter",
    "puzzle",
    "fighting",
    "hack and slash",
    "beat 'em up",
    "point-and-click",
    "visual novel",
    "arcade",
}

POSITIVE_THEME_KEYWORDS = {
    "action",
    "fantasy",
    "science fiction",
    "sci-fi",
    "horror",
    "thriller",
    "survival",
    "historical",
    "mystery",
    "drama",
    "comedy",
    "stealth",
    "warfare",
    "romance",
}

LOW_PRIORITY_GENRE_KEYWORDS = {
    "sport",
    "racing",
    "simulator",
    "strategy",
    "real time strategy",
    "turn-based strategy",
    "card",
    "board game",
    "quiz",
    "trivia",
    "pinball",
    "music",
}


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


def unix_ts(year: int, month: int = 1, day: int = 1) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def unix_to_date_text(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def unix_to_year(value: Any) -> str:
    text = unix_to_date_text(value)
    return text[:4] if text else ""


def decade_from_year(year: Any) -> str:
    try:
        y = int(year)
        return f"{(y // 10) * 10}s"
    except Exception:
        return ""


def names_from_array(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    names = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name", "")
            if name:
                names.append(str(name))
        elif item:
            names.append(str(item))
    return " | ".join(sorted(set(names)))


def first_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name", "") or "")
    return ""


def apicalypse_query(year: int, offset: int, limit: int) -> str:
    start = unix_ts(year, 1, 1)
    end = unix_ts(year + 1, 1, 1)

    # category=0 is main_game. It is marked deprecated in docs in favor of
    # game_type, but still available and documented with enum values.
    # themes != (42) removes erotic theme per IGDB docs.
    fields = (
        "id,name,slug,first_release_date,category,status,"
        "genres.name,themes.name,game_modes.name,player_perspectives.name,platforms.name,"
        "rating,rating_count,total_rating,total_rating_count,aggregated_rating,aggregated_rating_count,"
        "summary,storyline,url,parent_game.name,version_parent,version_title,collection.name,franchise.name"
    )

    return (
        f"fields {fields}; "
        f"where first_release_date >= {start} "
        f"& first_release_date < {end} "
        f"& first_release_date != null "
        f"& category = 0 "
        f"& version_parent = null "
        f"& themes != (42); "
        f"sort first_release_date asc; "
        f"limit {limit}; "
        f"offset {offset};"
    )


def igdb_post(endpoint: str, body: str) -> list[dict[str, Any]]:
    token = obtain_igdb_token()
    client_id = get_env("IGDB_CLIENT_ID")

    req = urllib.request.Request(
        f"https://api.igdb.com/v4/{endpoint}",
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


def flatten_game(g: dict[str, Any]) -> dict[str, Any]:
    year = unix_to_year(g.get("first_release_date"))
    summary = str(g.get("summary", "") or "")
    storyline = str(g.get("storyline", "") or "")

    return {
        "igdb_id": g.get("id", ""),
        "name": g.get("name", ""),
        "slug": g.get("slug", ""),
        "original_release_date": unix_to_date_text(g.get("first_release_date")),
        "original_release_year": year,
        "decade": decade_from_year(year),
        "category": g.get("category", ""),
        "status": g.get("status", ""),
        "genres": names_from_array(g.get("genres")),
        "themes": names_from_array(g.get("themes")),
        "game_modes": names_from_array(g.get("game_modes")),
        "player_perspectives": names_from_array(g.get("player_perspectives")),
        "platforms": names_from_array(g.get("platforms")),
        "rating": g.get("rating", ""),
        "rating_count": g.get("rating_count", ""),
        "total_rating": g.get("total_rating", ""),
        "total_rating_count": g.get("total_rating_count", ""),
        "aggregated_rating": g.get("aggregated_rating", ""),
        "aggregated_rating_count": g.get("aggregated_rating_count", ""),
        "summary": summary,
        "storyline": storyline,
        "has_summary": bool(summary.strip()),
        "has_storyline": bool(storyline.strip()),
        "parent_game": first_name(g.get("parent_game")),
        "version_parent": g.get("version_parent", ""),
        "version_title": g.get("version_title", ""),
        "collection": first_name(g.get("collection")),
        "franchise": first_name(g.get("franchise")),
        "url": g.get("url", ""),
        "fetched_at": now_iso(),
    }


def contains_any(text: str, words: set[str]) -> bool:
    low = str(text or "").lower()
    return any(w in low for w in words)


def compute_candidate_flags(row: pd.Series) -> dict[str, Any]:
    genres = str(row.get("genres", "") or "")
    themes = str(row.get("themes", "") or "")
    modes = str(row.get("game_modes", "") or "")
    perspectives = str(row.get("player_perspectives", "") or "")
    summary = str(row.get("summary", "") or "")
    storyline = str(row.get("storyline", "") or "")

    positive_genre = contains_any(genres, POSITIVE_GENRE_KEYWORDS)
    positive_theme = contains_any(themes, POSITIVE_THEME_KEYWORDS)
    low_priority_genre = contains_any(genres, LOW_PRIORITY_GENRE_KEYWORDS)
    has_text = len(summary.strip()) >= 80 or len(storyline.strip()) >= 40

    # Broad by design: include many old games, only push clearly low-priority cases
    # into review instead of deleting them.
    thematic_score = 0
    if positive_genre:
        thematic_score += 2
    if positive_theme:
        thematic_score += 1
    if has_text:
        thematic_score += 1
    if "single player" in modes.lower():
        thematic_score += 1
    if perspectives.strip():
        thematic_score += 0.5
    if low_priority_genre:
        thematic_score -= 1.5

    # Broad candidate: keep if there is any positive sign, or if not clearly low-priority.
    broad_candidate = thematic_score >= 1 or not low_priority_genre

    reasons = []
    if positive_genre:
        reasons.append("positive_genre")
    if positive_theme:
        reasons.append("positive_theme")
    if has_text:
        reasons.append("summary_or_storyline")
    if "single player" in modes.lower():
        reasons.append("single_player")
    if low_priority_genre:
        reasons.append("low_priority_genre")

    return {
        "broad_candidate_for_archetype_annotation": bool(broad_candidate),
        "thematic_fit_score": round(float(thematic_score), 2),
        "candidate_reason": " | ".join(reasons),
    }


def add_candidate_flags(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    flags = df.apply(compute_candidate_flags, axis=1, result_type="expand")
    out = pd.concat([df, flags], axis=1)

    # Visibility score: deliberately simple and robust to missing old-game data.
    for col in ["total_rating_count", "rating_count", "aggregated_rating_count"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    out["visibility_count_score"] = (
        out["total_rating_count"] * 2
        + out["rating_count"]
        + out["aggregated_rating_count"] * 2
    )

    out = out.sort_values(
        ["original_release_year", "broad_candidate_for_archetype_annotation", "visibility_count_score", "thematic_fit_score", "name"],
        ascending=[True, False, False, False, True],
    )
    return out


def fetch_year(year: int, limit: int, delay: float, max_pages: int) -> list[dict[str, Any]]:
    rows = []
    offset = 0
    page = 0

    while True:
        page += 1
        if max_pages and page > max_pages:
            print(f"  reached max_pages={max_pages}, stopping year {year}")
            break

        body = apicalypse_query(year, offset, limit)
        data = igdb_post("games", body)

        print(f"  year={year}, page={page}, offset={offset}, rows={len(data)}")

        if not data:
            break

        rows.extend(flatten_game(g) for g in data)

        if len(data) < limit:
            break

        offset += limit

        if delay > 0:
            time.sleep(delay)

    return rows


def write_examples(df: pd.DataFrame, out_path: Path, examples_per_year: int) -> pd.DataFrame:
    rows = []
    if df.empty:
        result = pd.DataFrame()
        result.to_csv(out_path, index=False, encoding="utf-8-sig")
        return result

    work = df.copy()
    work["original_release_year"] = pd.to_numeric(work["original_release_year"], errors="coerce").astype("Int64")
    work = work.sort_values(
        ["original_release_year", "broad_candidate_for_archetype_annotation", "visibility_count_score", "thematic_fit_score", "name"],
        ascending=[True, False, False, False, True],
    )

    for year, sub in work.groupby("original_release_year", dropna=False):
        sub = sub.head(examples_per_year)
        for i, (_, row) in enumerate(sub.iterrows(), start=1):
            rows.append({
                "original_release_year": year,
                "example_no": i,
                "igdb_id": row.get("igdb_id", ""),
                "name": row.get("name", ""),
                "genres": row.get("genres", ""),
                "themes": row.get("themes", ""),
                "game_modes": row.get("game_modes", ""),
                "platforms": row.get("platforms", ""),
                "thematic_fit_score": row.get("thematic_fit_score", ""),
                "visibility_count_score": row.get("visibility_count_score", ""),
                "broad_candidate_for_archetype_annotation": row.get("broad_candidate_for_archetype_annotation", ""),
            })

    result = pd.DataFrame(rows)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    return result


def print_console_summary(df: pd.DataFrame, examples: pd.DataFrame) -> None:
    if df.empty:
        print("No rows.")
        return

    print()
    print("=" * 100)
    print("IGDB PRE-2005 CANDIDATE CATALOG SUMMARY")
    print("=" * 100)
    print(f"Raw rows: {len(df)}")
    print(f"Broad candidates: {int(df['broad_candidate_for_archetype_annotation'].sum())}")
    print(f"Low-priority/review: {int((~df['broad_candidate_for_archetype_annotation']).sum())}")
    print()

    counts = df.groupby("original_release_year", dropna=False).size().reset_index(name="count")
    cand_counts = df[df["broad_candidate_for_archetype_annotation"]].groupby("original_release_year", dropna=False).size().reset_index(name="candidate_count")
    merged = counts.merge(cand_counts, on="original_release_year", how="left").fillna(0)
    merged["candidate_count"] = merged["candidate_count"].astype(int)

    print("COUNTS BY YEAR")
    print("-" * 100)
    for _, row in merged.iterrows():
        print(f"{str(row['original_release_year']):>6}: {int(row['count']):>5} games, {int(row['candidate_count']):>5} broad candidates")

    print()
    print("EXAMPLES BY YEAR")
    print("-" * 100)
    for year, sub in examples.groupby("original_release_year", dropna=False):
        print()
        print(f"{year}")
        print("-" * 100)
        for _, row in sub.iterrows():
            name = str(row.get("name", ""))[:42]
            genres = str(row.get("genres", ""))[:38]
            themes = str(row.get("themes", ""))[:30]
            fit = row.get("thematic_fit_score", "")
            vis = row.get("visibility_count_score", "")
            cand = row.get("broad_candidate_for_archetype_annotation", "")
            print(f"{int(row['example_no']):>2}. {name:<42} | fit {fit!s:<4} | vis {vis!s:<5} | cand {str(cand):<5} | {genres} | {themes}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-year", type=int, default=1970)
    parser.add_argument("--to-year-exclusive", type=int, default=2005)
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--max-pages-per-year", type=int, default=0, help="0 = no max.")
    parser.add_argument("--examples-per-year", type=int, default=15)
    parser.add_argument("--test-year", type=int, default=0, help="Fetch only one year for testing.")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    years = [args.test_year] if args.test_year else list(range(args.from_year, args.to_year_exclusive))

    all_rows = []
    for year in years:
        print(f"\nFetching IGDB year {year}")
        try:
            rows = fetch_year(year, limit=args.limit, delay=args.delay, max_pages=args.max_pages_per_year)
            all_rows.extend(rows)

            # checkpoint after every year
            checkpoint = pd.DataFrame(all_rows)
            if not checkpoint.empty:
                checkpoint.to_csv(outdir / "igdb_pre2005_raw_main_games_v001_checkpoint.csv", index=False, encoding="utf-8-sig")
        except Exception as exc:
            print(f"ERROR while fetching year {year}: {type(exc).__name__}: {exc}")

    raw = pd.DataFrame(all_rows).drop_duplicates(subset=["igdb_id"], keep="first") if all_rows else pd.DataFrame()
    if not raw.empty:
        raw = add_candidate_flags(raw)

    broad = raw[raw["broad_candidate_for_archetype_annotation"]].copy() if not raw.empty else pd.DataFrame()
    low = raw[~raw["broad_candidate_for_archetype_annotation"]].copy() if not raw.empty else pd.DataFrame()

    raw_path = outdir / "igdb_pre2005_raw_main_games_v001.csv"
    broad_path = outdir / "igdb_pre2005_broad_candidates_v001.csv"
    low_path = outdir / "igdb_pre2005_low_priority_review_v001.csv"

    raw.to_csv(raw_path, index=False, encoding="utf-8-sig")
    broad.to_csv(broad_path, index=False, encoding="utf-8-sig")
    low.to_csv(low_path, index=False, encoding="utf-8-sig")

    if not raw.empty:
        year_counts = raw.groupby("original_release_year", dropna=False).size().reset_index(name="raw_count")
        cand_counts = broad.groupby("original_release_year", dropna=False).size().reset_index(name="broad_candidate_count")
        year_counts = year_counts.merge(cand_counts, on="original_release_year", how="left").fillna(0)
        year_counts["broad_candidate_count"] = year_counts["broad_candidate_count"].astype(int)
    else:
        year_counts = pd.DataFrame(columns=["original_release_year", "raw_count", "broad_candidate_count"])

    year_counts.to_csv(outdir / "igdb_pre2005_year_counts_v001.csv", index=False, encoding="utf-8-sig")

    if not raw.empty:
        decade_counts = raw.groupby("decade", dropna=False).size().reset_index(name="raw_count")
        decade_cand = broad.groupby("decade", dropna=False).size().reset_index(name="broad_candidate_count")
        decade_counts = decade_counts.merge(decade_cand, on="decade", how="left").fillna(0)
        decade_counts["broad_candidate_count"] = decade_counts["broad_candidate_count"].astype(int)
    else:
        decade_counts = pd.DataFrame(columns=["decade", "raw_count", "broad_candidate_count"])

    decade_counts.to_csv(outdir / "igdb_pre2005_decade_counts_v001.csv", index=False, encoding="utf-8-sig")

    examples = write_examples(raw, outdir / "igdb_pre2005_examples_by_year_v001.csv", args.examples_per_year)

    summary = {
        "created_at": now_iso(),
        "from_year": args.from_year,
        "to_year_exclusive": args.to_year_exclusive,
        "test_year": args.test_year,
        "raw_rows": int(len(raw)),
        "broad_candidate_rows": int(len(broad)),
        "low_priority_review_rows": int(len(low)),
        "outputs": {
            "raw": str(raw_path),
            "broad_candidates": str(broad_path),
            "low_priority_review": str(low_path),
            "year_counts": str(outdir / "igdb_pre2005_year_counts_v001.csv"),
            "decade_counts": str(outdir / "igdb_pre2005_decade_counts_v001.csv"),
            "examples_by_year": str(outdir / "igdb_pre2005_examples_by_year_v001.csv"),
        },
        "note": "This catalog uses IGDB first_release_date and category=0 main_game. It is a broad pre-LLM candidate pool."
    }
    (outdir / "igdb_pre2005_summary_v001.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# IGDB pre-2005 broad candidate catalog v001

This dataset is an IGDB-based historical candidate pool for later protagonist and archetype annotation.

## Important

- No LLM annotation is performed here.
- `original_release_year` is derived from IGDB `first_release_date`.
- The query uses `category = 0` to prefer main games and avoid DLC, expansions, bundles, ports, remasters, etc.
- The broad candidate filter is intentionally loose: it marks likely useful games, but does not delete the low-priority cases.

## Outputs

- `igdb_pre2005_raw_main_games_v001.csv`
- `igdb_pre2005_broad_candidates_v001.csv`
- `igdb_pre2005_low_priority_review_v001.csv`
- `igdb_pre2005_year_counts_v001.csv`
- `igdb_pre2005_decade_counts_v001.csv`
- `igdb_pre2005_examples_by_year_v001.csv`

## Summary

- Raw rows: {len(raw)}
- Broad candidates: {len(broad)}
- Low-priority/review: {len(low)}
"""
    (outdir / "README_igdb_pre2005_candidates_v001.md").write_text(readme, encoding="utf-8")

    print_console_summary(raw, examples)

    print("\nSaved:")
    print(f"  {raw_path}")
    print(f"  {broad_path}")
    print(f"  {low_path}")
    print(f"  {outdir / 'igdb_pre2005_year_counts_v001.csv'}")
    print(f"  {outdir / 'igdb_pre2005_examples_by_year_v001.csv'}")


if __name__ == "__main__":
    main()
