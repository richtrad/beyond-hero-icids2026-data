#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
igdb_test_original_year_matching_v001.py

Test IGDB matching for original release years on a small sample from the Steam
archetype dataset.

Purpose:
- Verify that IGDB can recover original_release_year for games whose Steam
  release year is missing or misleading.
- DO NOT annotate archetypes.
- DO NOT call OpenAI.
- Only query IGDB and save a small cache.

Default input:
  steam_bulk_outputs/release_years_12_v002/steam_analysis_ready_12_with_year_v002.csv

Default output:
  igdb_outputs/igdb_original_year_matching_test_v001.csv

Default behavior:
  Take first 100 games with missing Steam release year, sorted by selection_rank.

Environment variables:
  IGDB_CLIENT_ID
  IGDB_CLIENT_SECRET
  Optional: IGDB_ACCESS_TOKEN

If IGDB_ACCESS_TOKEN is not set, the script obtains a new token from Twitch using
IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.

Example:
  python igdb_test_original_year_matching_v001.py --limit 100

Specific sanity query:
  python igdb_test_original_year_matching_v001.py --title "Half-Life"
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_INPUT = Path("steam_bulk_outputs/release_years_12_v002/steam_analysis_ready_12_with_year_v002.csv")
DEFAULT_OUTPUT = Path("igdb_outputs/igdb_original_year_matching_test_v001.csv")


EDITION_PATTERNS = [
    r"\bgame of the year\b",
    r"\bgoty\b",
    r"\bdefinitive edition\b",
    r"\bspecial edition\b",
    r"\bcomplete edition\b",
    r"\banniversary edition\b",
    r"\bultimate edition\b",
    r"\bcollector'?s edition\b",
    r"\bdeluxe edition\b",
    r"\bremastered\b",
    r"\bremaster\b",
    r"\benhanced edition\b",
    r"\bdirector'?s cut\b",
    r"\blegacy\b",
    r"\bclassic\b",
    r"\bhd\b",
]


BAD_CANDIDATE_TERMS = [
    "mod",
    "mmod",
    "update",
    "patch",
    "demo",
    "soundtrack",
    "ost",
    "trailer",
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


def clean_title_for_query(title: str) -> str:
    t = str(title or "")

    # Remove common trailing bracketed year/edition hints but keep core title.
    t = re.sub(r"\((?:19|20)\d{2}\)", " ", t)
    t = re.sub(r"\[(?:19|20)\d{2}\]", " ", t)

    # Remove trademark marks.
    t = t.replace("™", "").replace("®", "")

    # Normalize common separators.
    t = re.sub(r"[:：]\s*the\s+.+$", lambda m: m.group(0), t, flags=re.I)

    # Remove edition terms for query.
    q = t
    for pat in EDITION_PATTERNS:
        q = re.sub(pat, " ", q, flags=re.I)

    q = re.sub(r"\s+", " ", q).strip(" -:|")
    return q or str(title or "").strip()


def normalize_title(title: str) -> str:
    t = clean_title_for_query(title).lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\bthe\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


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


def escape_apicalypse_string(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def igdb_search_games(query: str, limit: int, delay: float) -> list[dict[str, Any]]:
    token = obtain_igdb_token()
    client_id = get_env("IGDB_CLIENT_ID")

    q = escape_apicalypse_string(query)
    body = (
        f'search "{q}"; '
        "fields id,name,slug,first_release_date,category,version_parent,parent_game,platforms.name,total_rating_count,rating_count,follows,hypes; "
        f"limit {int(limit)};"
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.igdb.com/v4/games",
        data=body,
        method="POST",
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "text/plain",
        },
    )

    if delay > 0:
        time.sleep(delay)

    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def score_candidate(steam_title: str, query_title: str, candidate: dict[str, Any]) -> float:
    steam_norm = normalize_title(steam_title)
    query_norm = normalize_title(query_title)
    cand_name = str(candidate.get("name", "") or "")
    cand_norm = normalize_title(cand_name)

    if not cand_norm:
        return 0.0

    score = difflib.SequenceMatcher(None, query_norm, cand_norm).ratio()

    # Strong exact-title bonuses.
    if cand_norm == query_norm:
        score += 0.30
    elif cand_norm == steam_norm:
        score += 0.25
    elif query_norm and query_norm in cand_norm:
        score += 0.08
    elif cand_norm and cand_norm in query_norm:
        score += 0.08

    # Release date helps but should not override title mismatch.
    if candidate.get("first_release_date"):
        score += 0.04

    # Penalize obvious mods/updates if the original title did not contain those terms.
    steam_lower = str(steam_title).lower()
    cand_lower = cand_name.lower()
    for term in BAD_CANDIDATE_TERMS:
        if term in cand_lower and term not in steam_lower:
            score -= 0.12

    # Penalize very long candidate names when query is short and exact base title exists elsewhere.
    q_tokens = set(query_norm.split())
    c_tokens = set(cand_norm.split())
    if len(c_tokens) > len(q_tokens) + 4:
        score -= 0.05

    return max(0.0, min(1.0, score))


def choose_best_candidate(steam_title: str, query_title: str, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float, list[dict[str, Any]]]:
    scored = []
    for c in candidates:
        c2 = dict(c)
        c2["match_score_0_1"] = round(score_candidate(steam_title, query_title, c), 4)
        c2["first_release_date_text"] = unix_to_date_text(c2.get("first_release_date"))
        c2["original_release_year"] = unix_to_year(c2.get("first_release_date"))
        scored.append(c2)

    scored.sort(key=lambda x: x.get("match_score_0_1", 0), reverse=True)
    best = scored[0] if scored else None
    score = float(best.get("match_score_0_1", 0)) if best else 0.0
    return best, score, scored


def select_input_rows(input_path: Path, limit: int, mode: str) -> pd.DataFrame:
    df = pd.read_csv(input_path, dtype={"appid": str}, low_memory=False)

    if "name" not in df.columns:
        raise RuntimeError("Input CSV has no name column.")

    if "selection_rank" in df.columns:
        df["_rank"] = pd.to_numeric(df["selection_rank"], errors="coerce").fillna(10**12)
    else:
        df["_rank"] = range(len(df))

    if mode == "missing-steam-year":
        if "release_year" not in df.columns:
            raise RuntimeError("mode=missing-steam-year requires release_year column.")
        y = pd.to_numeric(df["release_year"], errors="coerce")
        df = df[y.isna()].copy()
    elif mode == "core-strict":
        if "is_core_strict_12" not in df.columns:
            raise RuntimeError("mode=core-strict requires is_core_strict_12 column.")
        mask = df["is_core_strict_12"].fillna(False).astype(str).str.lower().isin(["true", "1", "yes"])
        df = df[mask].copy()
    elif mode == "all":
        pass
    else:
        raise RuntimeError(f"Unknown mode: {mode}")

    df = df.sort_values("_rank").head(limit).copy()
    return df


def result_row_from_match(appid: str, steam_name: str, query_name: str, best: dict[str, Any] | None, score: float, candidates: list[dict[str, Any]], error: str = "") -> dict[str, Any]:
    if best is None:
        return {
            "appid": appid,
            "steam_name": steam_name,
            "query_name": query_name,
            "igdb_id": "",
            "igdb_name": "",
            "igdb_slug": "",
            "igdb_first_release_date_unix": "",
            "original_release_date": "",
            "original_release_year": "",
            "match_score_0_1": 0.0,
            "needs_year_review": True,
            "error": error,
            "candidates_json": json.dumps(candidates, ensure_ascii=False),
            "fetched_at": now_iso(),
        }

    original_year = best.get("original_release_year", "")
    needs_review = (score < 0.85) or not original_year

    return {
        "appid": appid,
        "steam_name": steam_name,
        "query_name": query_name,
        "igdb_id": best.get("id", ""),
        "igdb_name": best.get("name", ""),
        "igdb_slug": best.get("slug", ""),
        "igdb_first_release_date_unix": best.get("first_release_date", ""),
        "original_release_date": best.get("first_release_date_text", ""),
        "original_release_year": original_year,
        "match_score_0_1": round(float(score), 4),
        "needs_year_review": bool(needs_review),
        "error": error,
        "candidates_json": json.dumps(candidates[:10], ensure_ascii=False),
        "fetched_at": now_iso(),
    }


def run_one_title(title: str, candidates_limit: int, delay: float) -> list[dict[str, Any]]:
    query_name = clean_title_for_query(title)
    candidates = igdb_search_games(query_name, candidates_limit, delay=delay)
    best, score, scored = choose_best_candidate(title, query_name, candidates)
    row = result_row_from_match("", title, query_name, best, score, scored)
    print(json.dumps(row, ensure_ascii=False, indent=2))
    print("\nCandidates:")
    for c in scored:
        print(f"  score={c.get('match_score_0_1'):.3f} id={c.get('id')} year={c.get('original_release_year')} name={c.get('name')}")
    return [row]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--mode", choices=["missing-steam-year", "core-strict", "all"], default="missing-steam-year")
    parser.add_argument("--candidates", type=int, default=10)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--title", default="", help="Run one specific title instead of reading CSV.")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []

    if args.title:
        rows = run_one_title(args.title, args.candidates, args.delay)
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            raise FileNotFoundError(input_path)

        df = select_input_rows(input_path, args.limit, args.mode)
        print(f"Selected {len(df)} rows from {input_path} with mode={args.mode}")

        for idx, (_, row) in enumerate(df.iterrows(), start=1):
            appid = str(row.get("appid", "") or "")
            steam_name = str(row.get("name", "") or "")
            query_name = clean_title_for_query(steam_name)

            print(f"[{idx}/{len(df)}] {steam_name!r} -> query {query_name!r}")

            try:
                candidates = igdb_search_games(query_name, args.candidates, delay=args.delay)
                best, score, scored = choose_best_candidate(steam_name, query_name, candidates)
                outrow = result_row_from_match(appid, steam_name, query_name, best, score, scored)
                print(f"  best: {outrow['igdb_name']!r}, year={outrow['original_release_year']}, score={outrow['match_score_0_1']}, review={outrow['needs_year_review']}")
            except Exception as exc:
                outrow = result_row_from_match(appid, steam_name, query_name, None, 0.0, [], error=f"{type(exc).__name__}: {exc}")
                print(f"  ERROR: {outrow['error']}")

            rows.append(outrow)

            # Save after every row, so interruption is harmless.
            pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")

    out = pd.DataFrame(rows)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"\nSaved: {output_path} ({len(out)} rows)")
    if len(out):
        print("\nSummary:")
        print(out[["steam_name", "igdb_name", "original_release_year", "match_score_0_1", "needs_year_review"]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
