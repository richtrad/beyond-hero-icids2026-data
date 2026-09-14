# -*- coding: utf-8 -*-
"""
steam_bulk_catalog_builder_csv.py

Bulk-first Steam corpus builder.

Goal
----
1) Download a complete Steam game catalog first.
2) Download a SteamSpy bulk snapshot and optional tag/genre hit lists.
3) Build a local CSV shortlist of games that deserve expensive per-app details.
4) Optionally enrich only the shortlist with Steam Store appdetails.

Why this version exists
-----------------------
The older pipeline queried appdetails + SteamSpy appdetails per appid before it
knew whether the app was interesting. That is slow by construction. This version
uses bulk-ish data first and saves everything as CSV.

Typical use
-----------
PowerShell:
    $env:STEAM_API_KEY="YOUR_KEY"   # recommended for IStoreService/GetAppList
    python steam_bulk_catalog_builder_csv.py --mode build-candidates

Then, after you inspect/tune steam_bulk_outputs/steam_catalog_candidates.csv:
    python steam_bulk_catalog_builder_csv.py --mode details --detail-limit 3000

All CSV outputs go to steam_bulk_outputs/.
All JSON caches go to steam_bulk_cache/.

Notes
-----
- Steam IStoreService/GetAppList needs a Web API key.
- If the key is missing, the script falls back to the public/deprecated
  ISteamApps/GetAppList. That fallback is less clean because it is not a
  game-only catalog.
- SteamSpy request=all is rate-limited. The default sleep is intentionally long.
- Store appdetails is still per-app, so this script only calls it for shortlisted
  candidates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import requests


# ============================================================
# CONFIG
# ============================================================

STEAM_API_KEY = os.getenv("STEAM_API_KEY")

CACHE_DIR = Path("steam_bulk_cache")
OUTPUT_DIR = Path("steam_bulk_outputs")
APPDETAILS_CACHE_DIR = CACHE_DIR / "appdetails"

CACHE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
APPDETAILS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# CSV outputs
STEAM_CATALOG_CSV = OUTPUT_DIR / "steam_catalog_games.csv"
STEAMSPY_ALL_CSV = OUTPUT_DIR / "steamspy_all_snapshot.csv"
STEAMSPY_TAG_GENRE_HITS_CSV = OUTPUT_DIR / "steamspy_tag_genre_hits.csv"
MERGED_CATALOG_CSV = OUTPUT_DIR / "steam_catalog_merged.csv"
CANDIDATES_CSV = OUTPUT_DIR / "steam_catalog_candidates.csv"
APPDETAILS_CSV = OUTPUT_DIR / "steam_appdetails_shortlist.csv"
CANDIDATES_WITH_DETAILS_CSV = OUTPUT_DIR / "steam_candidates_with_details.csv"

# JSON cache files
STEAM_CATALOG_JSON = CACHE_DIR / "steam_catalog_raw.json"
STEAMSPY_ALL_JSON_DIR = CACHE_DIR / "steamspy_all_pages"
STEAMSPY_QUERY_JSON_DIR = CACHE_DIR / "steamspy_tag_genre_queries"
STEAMSPY_ALL_JSON_DIR.mkdir(exist_ok=True)
STEAMSPY_QUERY_JSON_DIR.mkdir(exist_ok=True)

REQUEST_HEADERS = {
    "User-Agent": "FIT-CTU-research-script/0.2 contact: richtrad@fit.cvut.cz"
}

MAX_RETRIES = 5
DEFAULT_429_WAIT_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 90

# SteamSpy request=all is documented/known to be heavily limited.
# Leave this high if you run the complete bulk download.
STEAMSPY_ALL_SLEEP_SECONDS = 61.0

# Other SteamSpy requests can also be rate-limited. Keep this conservative.
STEAMSPY_QUERY_SLEEP_SECONDS = 2.0

# Store appdetails is per-app. This is deliberately moderate.
APPDETAILS_SLEEP_SECONDS = 0.35

# Candidate selection knobs. Tune these after first run.
MIN_REACTIONS_FOR_TERM_MATCH = 500
MIN_REACTIONS_POPULAR_FALLBACK = 5000
TOP_N_POPULAR_FALLBACK = 2500
MAX_CANDIDATES_DEFAULT = 5000

# Data freshness / re-download switches. Usually keep False.
FORCE_REFRESH_STEAM_CATALOG = False
FORCE_REFRESH_STEAMSPY_ALL = False
FORCE_REFRESH_STEAMSPY_TAG_GENRE = False
FORCE_REFRESH_APPDETAILS = False

# SteamSpy bulk page safety. None = continue until empty page.
STEAMSPY_ALL_MAX_PAGES: int | None = None

# Querying every inclusion tag is useful but not mandatory.
FETCH_STEAMSPY_TAG_HITS = True
FETCH_STEAMSPY_GENRE_HITS = True

# If a game is manually important, add its appid here.
FORCE_INCLUDE_APPIDS = {
    # 632470,  # Disco Elysium - The Final Cut
}


# ============================================================
# FILTER TERMS
# ============================================================

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

RPG_TERMS = {
    "RPG",
    "Action RPG",
    "JRPG",
    "CRPG",
    "Party-Based RPG",
    "Strategy RPG",
    "Tactical RPG",
    "Role-Playing",
}

ACTION_ADVENTURE_TERMS = {
    "Adventure",
    "Action-Adventure",
    "Third Person",
    "Third-Person Shooter",
    "First-Person",
    "FPS",
    "Shooter",
    "Action",
    "Platformer",
    "Point & Click",
    "Walking Simulator",
    "Immersive Sim",
    "Stealth",
}

SURVIVAL_HORROR_TERMS = {
    "Survival Horror",
    "Horror",
    "Lovecraftian",
    "Survival",
    "Open World",
    "Sandbox",
    "Zombies",
}

SYSTEMIC_ROLE_TERMS = {
    "Strategy",
    "RTS",
    "Turn-Based Strategy",
    "Grand Strategy",
    "4X",
    "City Builder",
    "Colony Sim",
    "Management",
    "Political Sim",
    "Simulation",
    "Base Building",
    "God Game",
}

PROTAGONIST_REPRESENTATION_TERMS = {
    "Female Protagonist",
    "Character Customization",
    "Singleplayer",
    "Choices Matter",
    "Multiple Protagonists",
}

INCLUSION_TERMS = (
    NARRATIVE_TERMS
    | RPG_TERMS
    | ACTION_ADVENTURE_TERMS
    | SURVIVAL_HORROR_TERMS
    | SYSTEMIC_ROLE_TERMS
    | PROTAGONIST_REPRESENTATION_TERMS
)

# SteamSpy genre endpoint is useful only for broad genre labels.
STEAMSPY_GENRE_TERMS = {
    "Action",
    "Adventure",
    "RPG",
    "Strategy",
    "Simulation",
}

# SteamSpy tag endpoint can handle user tags and more specific descriptors.
STEAMSPY_TAG_TERMS = sorted(INCLUSION_TERMS)


# ============================================================
# BASIC HELPERS
# ============================================================

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def clean_text(value: Any) -> Any:
    if isinstance(value, str):
        return CONTROL_CHARS_RE.sub("", value)
    return value


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def write_csv_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    cleaned = df.copy()
    for col in cleaned.columns:
        if cleaned[col].dtype == "object":
            cleaned[col] = cleaned[col].map(clean_text)
    cleaned.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(path)


def to_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except TypeError:
        pass

    if isinstance(value, dict):
        return [str(k).strip() for k in value.keys() if str(k).strip()]

    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]

    s = str(value).strip()
    if not s:
        return []

    # SteamSpy uses comma-separated genre strings. Our own strings may use semicolons.
    parts = re.split(r"[,;]", s)
    return [p.strip() for p in parts if p.strip()]


def join_unique(values: Iterable[Any], sep: str = "; ") -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        for part in split_terms(value):
            key = normalize_term(part)
            if key and key not in seen:
                seen.add(key)
                out.append(part)
    return sep.join(out)


def parse_owners_midpoint(owners: Any) -> int | None:
    """Parse SteamSpy owner bucket such as '1,000,000 .. 2,000,000'."""
    if owners is None:
        return None
    s = str(owners)
    nums = re.findall(r"[0-9][0-9,]*", s)
    if not nums:
        return None
    values = [int(n.replace(",", "")) for n in nums]
    if len(values) == 1:
        return values[0]
    return int(sum(values[:2]) / 2)


# ============================================================
# HTTP HELPERS
# ============================================================


def request_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    label: str = "request",
) -> Any:
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.get(
            url,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=timeout,
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait_seconds = int(retry_after)
            else:
                wait_seconds = DEFAULT_429_WAIT_SECONDS * attempt
            print(f"429 during {label}. Waiting {wait_seconds}s ({attempt}/{MAX_RETRIES})...")
            time.sleep(wait_seconds)
            continue

        if response.status_code in {500, 502, 503, 504}:
            wait_seconds = 10 * attempt
            print(f"{response.status_code} during {label}. Waiting {wait_seconds}s ({attempt}/{MAX_RETRIES})...")
            time.sleep(wait_seconds)
            continue

        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"{label} failed with HTTP {response.status_code}")

        return response.json()

    raise RuntimeError(f"Repeated request failure during {label}")


# ============================================================
# STEAM APP CATALOG
# ============================================================


def fetch_steam_catalog_istoreservice() -> dict[str, Any]:
    if not STEAM_API_KEY:
        raise RuntimeError("STEAM_API_KEY is missing")

    url = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
    all_apps: list[dict[str, Any]] = []
    last_appid = 0
    page = 0
    max_results = 50000

    while True:
        page += 1
        input_data = {
            "include_games": True,
            "include_dlc": False,
            "include_software": False,
            "include_videos": False,
            "include_hardware": False,
            "max_results": max_results,
            "last_appid": last_appid,
        }
        params = {
            "key": STEAM_API_KEY,
            "input_json": json.dumps(input_data),
        }
        raw = request_json(url, params=params, label=f"IStoreService/GetAppList page {page}")
        batch = raw.get("response", {}).get("apps", [])
        if not batch:
            print("Steam catalog: no more pages.")
            break

        all_apps.extend(batch)
        new_last_appid = int(batch[-1]["appid"])
        print(f"Steam catalog page {page}: {len(batch)} apps, last_appid={new_last_appid}, total={len(all_apps)}")

        if new_last_appid == last_appid:
            print("Steam catalog: last_appid did not change; stopping.")
            break
        last_appid = new_last_appid

        if len(batch) < max_results:
            print("Steam catalog: final page shorter than max_results.")
            break

        time.sleep(1.0)

    return {
        "fetched_at": now_iso(),
        "source": "IStoreService/GetAppList",
        "data": {"response": {"apps": all_apps}},
    }


def fetch_steam_catalog_public_fallback() -> dict[str, Any]:
    url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
    raw = request_json(url, label="ISteamApps/GetAppList public fallback")
    return {
        "fetched_at": now_iso(),
        "source": "ISteamApps/GetAppList fallback",
        "data": raw,
    }


def normalize_steam_catalog(raw_wrapped: dict[str, Any]) -> pd.DataFrame:
    raw = raw_wrapped.get("data", raw_wrapped)
    source = raw_wrapped.get("source", "unknown")

    apps: Any
    if isinstance(raw, dict) and "response" in raw and "apps" in raw["response"]:
        apps = raw["response"]["apps"]
    elif isinstance(raw, dict) and "applist" in raw and "apps" in raw["applist"]:
        apps = raw["applist"]["apps"]
    elif isinstance(raw, dict) and "apps" in raw:
        apps = raw["apps"]
    else:
        apps = raw

    df = pd.DataFrame(apps)
    if df.empty:
        return df

    if "app_name" in df.columns and "name" not in df.columns:
        df = df.rename(columns={"app_name": "name"})

    if "appid" not in df.columns:
        raise ValueError("Steam catalog has no appid column")

    if "name" not in df.columns:
        df["name"] = ""

    keep_cols = [c for c in ["appid", "name", "last_modified", "price_change_number"] if c in df.columns]
    df = df[keep_cols].copy()
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
    df = df[df["appid"].notna()].copy()
    df["appid"] = df["appid"].astype(int)
    df["steam_catalog_name"] = df["name"].astype(str)
    df = df.drop(columns=["name"])
    df["steam_catalog_source"] = source
    df["steam_catalog_fetched_at"] = raw_wrapped.get("fetched_at", "")
    df = df.drop_duplicates(subset=["appid"], keep="last")
    df = df.sort_values("appid").reset_index(drop=True)
    return df


def build_steam_catalog(force_refresh: bool = FORCE_REFRESH_STEAM_CATALOG) -> pd.DataFrame:
    if STEAM_CATALOG_CSV.exists() and not force_refresh:
        print(f"Loading Steam catalog CSV: {STEAM_CATALOG_CSV}")
        return read_csv_if_exists(STEAM_CATALOG_CSV)

    if STEAM_CATALOG_JSON.exists() and not force_refresh:
        print(f"Loading Steam catalog JSON cache: {STEAM_CATALOG_JSON}")
        wrapped = read_json(STEAM_CATALOG_JSON)
    else:
        print("Fetching Steam catalog...")
        try:
            wrapped = fetch_steam_catalog_istoreservice()
        except Exception as e:
            print(f"IStoreService failed: {type(e).__name__}: {e}")
            print("Falling back to public ISteamApps/GetAppList. This is not game-only.")
            wrapped = fetch_steam_catalog_public_fallback()
        write_json_atomic(STEAM_CATALOG_JSON, wrapped)

    df = normalize_steam_catalog(wrapped)
    write_csv_atomic(df, STEAM_CATALOG_CSV)
    print(f"Saved Steam catalog: {STEAM_CATALOG_CSV} ({len(df)} rows)")
    return df


# ============================================================
# STEAMSPY
# ============================================================


def normalize_steamspy_response(raw: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    if raw is None:
        return records

    if isinstance(raw, list):
        iterable = enumerate(raw)
    elif isinstance(raw, dict):
        # Common SteamSpy shape: {"appid": {record}, ...}
        iterable = raw.items()
    else:
        return records

    for key, value in iterable:
        if not isinstance(value, dict):
            continue
        row = dict(value)
        if "appid" not in row or row.get("appid") in (None, ""):
            try:
                row["appid"] = int(key)
            except (TypeError, ValueError):
                pass
        if "appid" in row:
            appid = to_int_or_none(row.get("appid"))
            if appid is not None:
                row["appid"] = appid
                records.append(row)

    return records


def steamspy_tags_to_string(value: Any) -> str:
    if isinstance(value, dict):
        sorted_items = sorted(value.items(), key=lambda kv: to_int_or_none(kv[1]) or 0, reverse=True)
        return "; ".join(str(k) for k, _ in sorted_items if str(k).strip())
    if isinstance(value, list):
        return "; ".join(str(x) for x in value if str(x).strip())
    if isinstance(value, str):
        return value
    return ""


def normalize_steamspy_all_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for rec in records:
        appid = to_int_or_none(rec.get("appid"))
        if appid is None:
            continue
        positive = to_int_or_none(rec.get("positive")) or 0
        negative = to_int_or_none(rec.get("negative")) or 0
        total = positive + negative
        owners = rec.get("owners")

        row = {
            "appid": appid,
            "steamspy_name": rec.get("name"),
            "steamspy_developer": rec.get("developer"),
            "steamspy_publisher": rec.get("publisher"),
            "steamspy_genre": rec.get("genre"),
            "steamspy_tags": steamspy_tags_to_string(rec.get("tags")),
            "steamspy_positive": positive,
            "steamspy_negative": negative,
            "total_ratings_pos_neg": total,
            "positive_ratio": positive / total if total else None,
            "steamspy_userscore": rec.get("userscore"),
            "steamspy_score_rank": rec.get("score_rank"),
            "steamspy_owners": owners,
            "steamspy_owners_midpoint": parse_owners_midpoint(owners),
            "steamspy_average_forever": rec.get("average_forever"),
            "steamspy_median_forever": rec.get("median_forever"),
            "steamspy_price": rec.get("price"),
            "steamspy_initialprice": rec.get("initialprice"),
            "steamspy_discount": rec.get("discount"),
            "steamspy_ccu": rec.get("ccu"),
            "steamspy_languages": rec.get("languages"),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["appid"], keep="last")
    df = df.sort_values("total_ratings_pos_neg", ascending=False, na_position="last").reset_index(drop=True)
    return df


def fetch_steamspy_all_pages(
    force_refresh: bool = FORCE_REFRESH_STEAMSPY_ALL,
    max_pages: int | None = STEAMSPY_ALL_MAX_PAGES,
) -> pd.DataFrame:
    if STEAMSPY_ALL_CSV.exists() and not force_refresh:
        print(f"Loading SteamSpy all snapshot CSV: {STEAMSPY_ALL_CSV}")
        return read_csv_if_exists(STEAMSPY_ALL_CSV)

    url = "https://steamspy.com/api.php"
    all_records: list[dict[str, Any]] = []
    page = 0

    while True:
        if max_pages is not None and page >= max_pages:
            print(f"SteamSpy all: reached max_pages={max_pages}.")
            break

        cache_path = STEAMSPY_ALL_JSON_DIR / f"page_{page:05d}.json"
        if cache_path.exists() and not force_refresh:
            raw_wrapped = read_json(cache_path)
            raw = raw_wrapped.get("data")
            print(f"SteamSpy all page {page}: loaded from cache")
        else:
            params = {"request": "all", "page": page}
            raw = request_json(url, params=params, timeout=120, label=f"SteamSpy all page {page}")
            raw_wrapped = {
                "fetched_at": now_iso(),
                "request": "all",
                "page": page,
                "data": raw,
            }
            write_json_atomic(cache_path, raw_wrapped)

        records = normalize_steamspy_response(raw)
        if not records:
            print(f"SteamSpy all page {page}: empty; stopping.")
            break

        all_records.extend(records)
        df_partial = normalize_steamspy_all_records(all_records)
        write_csv_atomic(df_partial, STEAMSPY_ALL_CSV)
        print(f"SteamSpy all page {page}: {len(records)} records, total unique={len(df_partial)}")

        page += 1
        if not cache_path.exists() or force_refresh:
            time.sleep(STEAMSPY_ALL_SLEEP_SECONDS)
        else:
            # Cache reads do not need the long wait.
            time.sleep(0.05)

    df = normalize_steamspy_all_records(all_records)
    write_csv_atomic(df, STEAMSPY_ALL_CSV)
    print(f"Saved SteamSpy all snapshot: {STEAMSPY_ALL_CSV} ({len(df)} rows)")
    return df


def safe_query_filename(request_type: str, term: str) -> str:
    key = normalize_term(term).replace(" ", "_")
    key = re.sub(r"[^a-z0-9_]+", "", key)
    return f"{request_type}_{key or 'empty'}.json"


def fetch_steamspy_tag_genre_hits(force_refresh: bool = FORCE_REFRESH_STEAMSPY_TAG_GENRE) -> pd.DataFrame:
    if STEAMSPY_TAG_GENRE_HITS_CSV.exists() and not force_refresh:
        print(f"Loading SteamSpy tag/genre hits CSV: {STEAMSPY_TAG_GENRE_HITS_CSV}")
        return read_csv_if_exists(STEAMSPY_TAG_GENRE_HITS_CSV)

    queries: list[tuple[str, str]] = []
    if FETCH_STEAMSPY_TAG_HITS:
        queries.extend(("tag", term) for term in STEAMSPY_TAG_TERMS)
    if FETCH_STEAMSPY_GENRE_HITS:
        queries.extend(("genre", term) for term in sorted(STEAMSPY_GENRE_TERMS))

    url = "https://steamspy.com/api.php"
    hit_rows: list[dict[str, Any]] = []

    for idx, (request_type, term) in enumerate(queries, start=1):
        cache_path = STEAMSPY_QUERY_JSON_DIR / safe_query_filename(request_type, term)
        if cache_path.exists() and not force_refresh:
            raw_wrapped = read_json(cache_path)
            raw = raw_wrapped.get("data")
            print(f"SteamSpy {request_type}={term!r}: loaded from cache ({idx}/{len(queries)})")
        else:
            params = {"request": request_type, request_type: term}
            raw = request_json(url, params=params, timeout=120, label=f"SteamSpy {request_type} {term}")
            raw_wrapped = {
                "fetched_at": now_iso(),
                "request": request_type,
                request_type: term,
                "data": raw,
            }
            write_json_atomic(cache_path, raw_wrapped)
            time.sleep(STEAMSPY_QUERY_SLEEP_SECONDS)

        records = normalize_steamspy_response(raw)
        for rec in records:
            appid = to_int_or_none(rec.get("appid"))
            if appid is None:
                continue
            hit_rows.append(
                {
                    "appid": appid,
                    "hit_type": request_type,
                    "hit_term": term,
                    "hit_name": rec.get("name"),
                    "hit_positive": to_int_or_none(rec.get("positive")),
                    "hit_negative": to_int_or_none(rec.get("negative")),
                    "hit_owners": rec.get("owners"),
                }
            )

        df_partial = pd.DataFrame(hit_rows)
        if not df_partial.empty:
            df_partial = df_partial.drop_duplicates(subset=["appid", "hit_type", "hit_term"])
            write_csv_atomic(df_partial, STEAMSPY_TAG_GENRE_HITS_CSV)
        print(f"SteamSpy {request_type}={term!r}: {len(records)} records ({idx}/{len(queries)})")

    df = pd.DataFrame(hit_rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["appid", "hit_type", "hit_term"])
        df = df.sort_values(["appid", "hit_type", "hit_term"]).reset_index(drop=True)
    write_csv_atomic(df, STEAMSPY_TAG_GENRE_HITS_CSV)
    print(f"Saved SteamSpy tag/genre hits: {STEAMSPY_TAG_GENRE_HITS_CSV} ({len(df)} rows)")
    return df


# ============================================================
# CANDIDATE SCORING
# ============================================================


def find_matching_terms(all_terms: Iterable[Any], inclusion_terms: Iterable[str]) -> list[str]:
    normalized_terms: list[tuple[str, str]] = []
    for term in all_terms:
        if term is None:
            continue
        original = str(term).strip()
        if not original:
            continue
        normalized_terms.append((normalize_term(original), original))

    matches: list[str] = []
    for inclusion in inclusion_terms:
        inc_norm = normalize_term(inclusion)
        for term_norm, original_term in normalized_terms:
            if not term_norm:
                continue
            if inc_norm == term_norm or inc_norm in term_norm or term_norm in inc_norm:
                matches.append(original_term)

    return sorted(set(matches), key=lambda x: normalize_term(x))


def calculate_relevance_score(matching_terms: Iterable[str]) -> int:
    score = 0
    normalized = {normalize_term(t) for t in matching_terms}

    for term in NARRATIVE_TERMS:
        if normalize_term(term) in normalized:
            score += 3
    for term in PROTAGONIST_REPRESENTATION_TERMS:
        if normalize_term(term) in normalized:
            score += 3
    for term in RPG_TERMS:
        if normalize_term(term) in normalized:
            score += 2
    for term in SYSTEMIC_ROLE_TERMS:
        if normalize_term(term) in normalized:
            score += 2
    for term in SURVIVAL_HORROR_TERMS:
        if normalize_term(term) in normalized:
            score += 2
    for term in ACTION_ADVENTURE_TERMS:
        if normalize_term(term) in normalized:
            score += 1
    return score


def classify_bucket(matching_terms: Iterable[str]) -> str:
    normalized = {normalize_term(t) for t in matching_terms}

    narrative = {normalize_term(t) for t in NARRATIVE_TERMS}
    systemic = {normalize_term(t) for t in SYSTEMIC_ROLE_TERMS}
    survival = {normalize_term(t) for t in SURVIVAL_HORROR_TERMS}
    rpg = {normalize_term(t) for t in RPG_TERMS}
    action = {normalize_term(t) for t in ACTION_ADVENTURE_TERMS}

    if normalized & narrative:
        return "narrative/protagonist-heavy"
    if normalized & rpg:
        return "RPG/character progression"
    if normalized & systemic:
        return "systemic/player-role"
    if normalized & survival:
        return "survival/sandbox or horror"
    if normalized & action:
        return "action/adventure protagonist"
    if normalized:
        return "general genre/tag match"
    return "NO MATCH"


def aggregate_hit_terms(hits_df: pd.DataFrame) -> pd.DataFrame:
    if hits_df.empty:
        return pd.DataFrame(columns=["appid", "steamspy_hit_terms", "steamspy_hit_types"])

    hits = hits_df.copy()
    hits["appid"] = pd.to_numeric(hits["appid"], errors="coerce")
    hits = hits[hits["appid"].notna()].copy()
    hits["appid"] = hits["appid"].astype(int)

    grouped = (
        hits.groupby("appid")
        .agg(
            steamspy_hit_terms=("hit_term", lambda s: join_unique(s)),
            steamspy_hit_types=("hit_type", lambda s: join_unique(s)),
        )
        .reset_index()
    )
    return grouped


def build_merged_catalog(
    steam_catalog_df: pd.DataFrame,
    steamspy_all_df: pd.DataFrame,
    hits_df: pd.DataFrame,
) -> pd.DataFrame:
    catalog = steam_catalog_df.copy()
    spy = steamspy_all_df.copy()

    for df in [catalog, spy]:
        if not df.empty and "appid" in df.columns:
            df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
            df.dropna(subset=["appid"], inplace=True)
            df["appid"] = df["appid"].astype(int)

    if catalog.empty and spy.empty:
        return pd.DataFrame()

    if catalog.empty:
        merged = spy
    elif spy.empty:
        merged = catalog
    else:
        merged = catalog.merge(spy, on="appid", how="outer")

    hit_terms = aggregate_hit_terms(hits_df)
    if not hit_terms.empty:
        merged = merged.merge(hit_terms, on="appid", how="left")
    else:
        merged["steamspy_hit_terms"] = ""
        merged["steamspy_hit_types"] = ""

    # Choose best display name.
    name_cols = [c for c in ["steamspy_name", "steam_catalog_name"] if c in merged.columns]
    if name_cols:
        merged["name"] = merged[name_cols].bfill(axis=1).iloc[:, 0]
    else:
        merged["name"] = ""

    # Ensure numeric columns exist.
    if "steamspy_positive" not in merged.columns:
        merged["steamspy_positive"] = 0
    if "steamspy_negative" not in merged.columns:
        merged["steamspy_negative"] = 0

    merged["steamspy_positive"] = pd.to_numeric(merged["steamspy_positive"], errors="coerce").fillna(0).astype(int)
    merged["steamspy_negative"] = pd.to_numeric(merged["steamspy_negative"], errors="coerce").fillna(0).astype(int)
    merged["total_ratings_pos_neg"] = merged["steamspy_positive"] + merged["steamspy_negative"]
    merged["positive_ratio"] = merged.apply(
        lambda r: r["steamspy_positive"] / r["total_ratings_pos_neg"] if r["total_ratings_pos_neg"] else None,
        axis=1,
    )

    # Terms and scoring.
    matched_terms: list[str] = []
    relevance_scores: list[int] = []
    buckets: list[str] = []

    for _, row in merged.iterrows():
        terms: list[str] = []
        terms.extend(split_terms(row.get("steamspy_genre")))
        terms.extend(split_terms(row.get("steamspy_tags")))
        terms.extend(split_terms(row.get("steamspy_hit_terms")))
        matches = find_matching_terms(terms, INCLUSION_TERMS)
        matched_terms.append("; ".join(matches))
        relevance_scores.append(calculate_relevance_score(matches))
        buckets.append(classify_bucket(matches))

    merged["matched_terms"] = matched_terms
    merged["relevance_score"] = relevance_scores
    merged["bucket"] = buckets
    merged["is_term_match"] = merged["matched_terms"].astype(str).str.strip() != ""
    merged["forced_include"] = merged["appid"].isin(FORCE_INCLUDE_APPIDS)

    # Popularity rank by reactions.
    merged = merged.sort_values("total_ratings_pos_neg", ascending=False, na_position="last").reset_index(drop=True)
    merged["reaction_rank"] = range(1, len(merged) + 1)

    # Candidate selection.
    merged["candidate_by_term_and_reactions"] = (
        merged["is_term_match"] & (merged["total_ratings_pos_neg"] >= MIN_REACTIONS_FOR_TERM_MATCH)
    )
    merged["candidate_by_popular_fallback"] = (
        (merged["total_ratings_pos_neg"] >= MIN_REACTIONS_POPULAR_FALLBACK)
        & (merged["reaction_rank"] <= TOP_N_POPULAR_FALLBACK)
    )
    merged["want_details"] = (
        merged["candidate_by_term_and_reactions"]
        | merged["candidate_by_popular_fallback"]
        | merged["forced_include"]
    )

    def reason(row: pd.Series) -> str:
        reasons: list[str] = []
        if row.get("forced_include"):
            reasons.append("forced")
        if row.get("candidate_by_term_and_reactions"):
            reasons.append(f"term_match+reactions>={MIN_REACTIONS_FOR_TERM_MATCH}")
        if row.get("candidate_by_popular_fallback"):
            reasons.append(f"popular_fallback_top{TOP_N_POPULAR_FALLBACK}_or_reactions>={MIN_REACTIONS_POPULAR_FALLBACK}")
        return "; ".join(reasons)

    merged["candidate_reason"] = merged.apply(reason, axis=1)

    # Useful column order.
    preferred_cols = [
        "appid",
        "name",
        "want_details",
        "candidate_reason",
        "bucket",
        "matched_terms",
        "relevance_score",
        "reaction_rank",
        "total_ratings_pos_neg",
        "steamspy_positive",
        "steamspy_negative",
        "positive_ratio",
        "steamspy_owners",
        "steamspy_owners_midpoint",
        "steamspy_genre",
        "steamspy_tags",
        "steamspy_hit_terms",
        "steam_catalog_name",
        "steamspy_name",
    ]
    existing_preferred = [c for c in preferred_cols if c in merged.columns]
    rest = [c for c in merged.columns if c not in existing_preferred]
    merged = merged[existing_preferred + rest]

    write_csv_atomic(merged, MERGED_CATALOG_CSV)
    print(f"Saved merged catalog: {MERGED_CATALOG_CSV} ({len(merged)} rows)")
    return merged


def build_candidates(merged_df: pd.DataFrame, max_candidates: int = MAX_CANDIDATES_DEFAULT) -> pd.DataFrame:
    if merged_df.empty:
        return pd.DataFrame()

    candidates = merged_df[merged_df["want_details"] == True].copy()  # noqa: E712

    # Prioritize strong thematic matches, then reaction count.
    candidates["candidate_priority"] = 0
    candidates.loc[candidates["candidate_by_popular_fallback"] == True, "candidate_priority"] += 10  # noqa: E712
    candidates.loc[candidates["candidate_by_term_and_reactions"] == True, "candidate_priority"] += 50  # noqa: E712
    candidates.loc[candidates["forced_include"] == True, "candidate_priority"] += 100  # noqa: E712
    candidates["candidate_priority"] += pd.to_numeric(candidates["relevance_score"], errors="coerce").fillna(0)

    candidates = candidates.sort_values(
        ["candidate_priority", "total_ratings_pos_neg", "relevance_score"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)

    if max_candidates and max_candidates > 0:
        candidates = candidates.head(max_candidates).copy()

    write_csv_atomic(candidates, CANDIDATES_CSV)
    print(f"Saved candidates: {CANDIDATES_CSV} ({len(candidates)} rows)")

    preview_cols = [
        "appid",
        "name",
        "candidate_reason",
        "bucket",
        "matched_terms",
        "total_ratings_pos_neg",
        "positive_ratio",
    ]
    existing = [c for c in preview_cols if c in candidates.columns]
    if existing:
        print("\nTop candidates preview:")
        print(candidates[existing].head(30).to_string(index=False))

    return candidates


# ============================================================
# OPTIONAL APPDETAILS ENRICHMENT
# ============================================================


def fetch_appdetails(appid: int) -> Any:
    url = "https://store.steampowered.com/api/appdetails"
    params = {
        "appids": appid,
        "cc": "us",
        "l": "english",
    }
    return request_json(url, params=params, timeout=60, label=f"appdetails {appid}")


def get_appdetails_cached(appid: int, force_refresh: bool = FORCE_REFRESH_APPDETAILS) -> tuple[dict[str, Any] | None, bool, str]:
    cache_path = APPDETAILS_CACHE_DIR / f"{appid}.json"
    if cache_path.exists() and not force_refresh:
        wrapped = read_json(cache_path)
        from_cache = True
    else:
        raw = fetch_appdetails(appid)
        wrapped = {
            "fetched_at": now_iso(),
            "appid": appid,
            "data": raw,
        }
        write_json_atomic(cache_path, wrapped)
        from_cache = False
        time.sleep(APPDETAILS_SLEEP_SECONDS)

    raw = wrapped.get("data", {})
    item = raw.get(str(appid), {}) if isinstance(raw, dict) else {}
    if not item.get("success"):
        return None, from_cache, f"success_false_or_missing: {item}"
    return item.get("data", {}), from_cache, ""


def extract_descriptions(items: Any) -> str:
    if not items:
        return ""
    out: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                desc = item.get("description") or item.get("name")
                if desc:
                    out.append(str(desc))
    return "; ".join(out)


def flatten_appdetails(appid: int, details: dict[str, Any] | None, from_cache: bool, error: str = "") -> dict[str, Any]:
    if not details:
        return {
            "appid": appid,
            "appdetails_from_cache": from_cache,
            "appdetails_error": error,
        }

    release_date = details.get("release_date", {}) or {}
    platforms = details.get("platforms", {}) or {}
    metacritic = details.get("metacritic", {}) or {}
    recommendations = details.get("recommendations", {}) or {}
    support_info = details.get("support_info", {}) or {}

    return {
        "appid": appid,
        "appdetails_from_cache": from_cache,
        "appdetails_error": error,
        "steam_type": details.get("type"),
        "steam_name": details.get("name"),
        "is_free": details.get("is_free"),
        "required_age": details.get("required_age"),
        "release_date_coming_soon": release_date.get("coming_soon"),
        "steam_release_date": release_date.get("date"),
        "developers": "; ".join(details.get("developers", []) or []),
        "publishers": "; ".join(details.get("publishers", []) or []),
        "steam_genres": extract_descriptions(details.get("genres")),
        "steam_categories": extract_descriptions(details.get("categories")),
        "platform_windows": platforms.get("windows"),
        "platform_mac": platforms.get("mac"),
        "platform_linux": platforms.get("linux"),
        "metacritic_score": metacritic.get("score"),
        "recommendations_total": recommendations.get("total"),
        "short_description": details.get("short_description"),
        "header_image": details.get("header_image"),
        "website": details.get("website"),
        "support_url": support_info.get("url"),
        "support_email": support_info.get("email"),
    }


def fetch_details_for_candidates(detail_limit: int | None = None, force_refresh: bool = FORCE_REFRESH_APPDETAILS) -> pd.DataFrame:
    candidates = read_csv_if_exists(CANDIDATES_CSV)
    if candidates.empty:
        raise RuntimeError(f"Candidate CSV not found or empty: {CANDIDATES_CSV}. Run --mode build-candidates first.")

    existing = read_csv_if_exists(APPDETAILS_CSV)
    existing_appids: set[int] = set()
    rows: list[dict[str, Any]] = []
    if not existing.empty and "appid" in existing.columns and not force_refresh:
        existing_appids = set(pd.to_numeric(existing["appid"], errors="coerce").dropna().astype(int))
        rows = existing.to_dict("records")
        print(f"Loaded existing appdetails CSV: {APPDETAILS_CSV} ({len(existing_appids)} appids)")

    appids = pd.to_numeric(candidates["appid"], errors="coerce").dropna().astype(int).tolist()
    if detail_limit and detail_limit > 0:
        appids = appids[:detail_limit]

    target_appids = [appid for appid in appids if force_refresh or appid not in existing_appids]
    print(f"Appdetails target appids: {len(target_appids)} / {len(appids)}")

    for idx, appid in enumerate(target_appids, start=1):
        try:
            details, from_cache, error = get_appdetails_cached(appid, force_refresh=force_refresh)
            row = flatten_appdetails(appid, details, from_cache=from_cache, error=error)
        except Exception as e:
            row = flatten_appdetails(appid, None, from_cache=False, error=f"{type(e).__name__}: {e}")

        rows.append(row)
        if idx % 25 == 0 or idx == len(target_appids):
            df_partial = pd.DataFrame(rows)
            df_partial = df_partial.drop_duplicates(subset=["appid"], keep="last")
            write_csv_atomic(df_partial, APPDETAILS_CSV)
            print(f"Saved appdetails progress: {idx}/{len(target_appids)} new, total rows={len(df_partial)}")

    details_df = read_csv_if_exists(APPDETAILS_CSV)
    if details_df.empty:
        details_df = pd.DataFrame(rows)
    details_df = details_df.drop_duplicates(subset=["appid"], keep="last")
    write_csv_atomic(details_df, APPDETAILS_CSV)

    candidates["appid"] = pd.to_numeric(candidates["appid"], errors="coerce").astype("Int64")
    details_df["appid"] = pd.to_numeric(details_df["appid"], errors="coerce").astype("Int64")
    combined = candidates.merge(details_df, on="appid", how="left")
    write_csv_atomic(combined, CANDIDATES_WITH_DETAILS_CSV)
    print(f"Saved candidates with details: {CANDIDATES_WITH_DETAILS_CSV} ({len(combined)} rows)")
    return combined


# ============================================================
# ORCHESTRATION
# ============================================================


@dataclass
class BuildResult:
    steam_catalog_rows: int
    steamspy_all_rows: int
    hit_rows: int
    merged_rows: int
    candidate_rows: int


def run_build_candidates(max_candidates: int = MAX_CANDIDATES_DEFAULT) -> BuildResult:
    steam_catalog = build_steam_catalog()
    steamspy_all = fetch_steamspy_all_pages()
    hits = fetch_steamspy_tag_genre_hits()
    merged = build_merged_catalog(steam_catalog, steamspy_all, hits)
    candidates = build_candidates(merged, max_candidates=max_candidates)

    return BuildResult(
        steam_catalog_rows=len(steam_catalog),
        steamspy_all_rows=len(steamspy_all),
        hit_rows=len(hits),
        merged_rows=len(merged),
        candidate_rows=len(candidates),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk-first Steam corpus builder using CSV outputs.")
    parser.add_argument(
        "--mode",
        choices=["catalog", "steamspy-all", "tag-genre", "build-candidates", "details", "all"],
        default="build-candidates",
        help="Which phase to run. Default: build-candidates.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=MAX_CANDIDATES_DEFAULT,
        help=f"Maximum number of candidates written to {CANDIDATES_CSV}. Default: {MAX_CANDIDATES_DEFAULT}.",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=0,
        help="Limit appdetails fetch to first N candidates. 0 = all candidates.",
    )
    parser.add_argument(
        "--fetch-details",
        action="store_true",
        help="With --mode all, also fetch Store appdetails for candidates.",
    )
    parser.add_argument(
        "--force-refresh-catalog",
        action="store_true",
        help="Re-download Steam catalog even if local CSV/JSON exists.",
    )
    parser.add_argument(
        "--force-refresh-steamspy-all",
        action="store_true",
        help="Re-download SteamSpy all pages even if local CSV/JSON exists.",
    )
    parser.add_argument(
        "--force-refresh-tag-genre",
        action="store_true",
        help="Re-download SteamSpy tag/genre queries even if local CSV/JSON exists.",
    )
    parser.add_argument(
        "--force-refresh-appdetails",
        action="store_true",
        help="Re-download appdetails even if local cache exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    global FORCE_REFRESH_STEAM_CATALOG
    global FORCE_REFRESH_STEAMSPY_ALL
    global FORCE_REFRESH_STEAMSPY_TAG_GENRE
    global FORCE_REFRESH_APPDETAILS

    FORCE_REFRESH_STEAM_CATALOG = args.force_refresh_catalog
    FORCE_REFRESH_STEAMSPY_ALL = args.force_refresh_steamspy_all
    FORCE_REFRESH_STEAMSPY_TAG_GENRE = args.force_refresh_tag_genre
    FORCE_REFRESH_APPDETAILS = args.force_refresh_appdetails

    print("Steam bulk CSV corpus builder")
    print(f"Mode: {args.mode}")
    print(f"Output dir: {OUTPUT_DIR.resolve()}")
    print(f"Cache dir: {CACHE_DIR.resolve()}")
    print(f"Steam API key present: {bool(STEAM_API_KEY)}")

    if args.mode == "catalog":
        build_steam_catalog(force_refresh=FORCE_REFRESH_STEAM_CATALOG)
        return

    if args.mode == "steamspy-all":
        fetch_steamspy_all_pages(force_refresh=FORCE_REFRESH_STEAMSPY_ALL)
        return

    if args.mode == "tag-genre":
        fetch_steamspy_tag_genre_hits(force_refresh=FORCE_REFRESH_STEAMSPY_TAG_GENRE)
        return

    if args.mode == "build-candidates":
        result = run_build_candidates(max_candidates=args.max_candidates)
        print(f"\nBuild result: {result}")
        return

    if args.mode == "details":
        detail_limit = args.detail_limit or None
        fetch_details_for_candidates(detail_limit=detail_limit, force_refresh=FORCE_REFRESH_APPDETAILS)
        return

    if args.mode == "all":
        result = run_build_candidates(max_candidates=args.max_candidates)
        print(f"\nBuild result: {result}")
        if args.fetch_details:
            detail_limit = args.detail_limit or None
            fetch_details_for_candidates(detail_limit=detail_limit, force_refresh=FORCE_REFRESH_APPDETAILS)
        else:
            print("\nSkipping appdetails. Use --fetch-details or run --mode details after inspecting candidates.")
        return

    raise ValueError(f"Unknown mode: {args.mode}")


if __name__ == "__main__":
    main()
