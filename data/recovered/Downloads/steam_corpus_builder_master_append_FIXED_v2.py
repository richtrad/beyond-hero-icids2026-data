import os
import json
import time
import re
import glob
import shutil
import traceback
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# CONFIG
# ============================================================

# API key je potřeba jen pro obnovení app listu přes IStoreService.
# Pokud už existuje steam_cache/app_list.json a APP_LIST_FORCE_REFRESH=False,
# skript běží i bez klíče.
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

CACHE_DIR = Path("steam_cache")
APP_LIST_CACHE = CACHE_DIR / "app_list.json"
DETAILS_CACHE_DIR = CACHE_DIR / "details"
REVIEWS_CACHE_DIR = CACHE_DIR / "reviews"
STEAMSPY_CACHE_DIR = CACHE_DIR / "steamspy"

CACHE_DIR.mkdir(exist_ok=True)
DETAILS_CACHE_DIR.mkdir(exist_ok=True)
REVIEWS_CACHE_DIR.mkdir(exist_ok=True)
STEAMSPY_CACHE_DIR.mkdir(exist_ok=True)

# Hlavní nastavení běhu
# Recovered master končil kolem absolute_index 22250.
# AUTO_RESUME_FROM_MASTER=True obvykle přepočítá start automaticky na max(absolute_index)+1.
START_INDEX = 22251
SCAN_LIMIT = 5000
TOP_N = 250
AUTO_RESUME_FROM_MASTER = True
SKIP_APPIDS_ALREADY_IN_MASTER = True

# Při prvním spuštění zkusí naimportovat staré batch CSV / recovered CSV do masteru.
# Po úspěšném obnovení můžeš klidně přepnout na False, aby start byl rychlejší.
IMPORT_EXISTING_BATCH_CSVS_ON_START = True

# False = používá lokální cache app listu.
# True = pokusí se obnovit celý seznam aplikací.
APP_LIST_FORCE_REFRESH = False

FORCE_REFRESH_DETAILS = False
FORCE_REFRESH_REVIEWS = False
FORCE_REFRESH_STEAMSPY = False

# Pokud True, projdou jen hry odpovídající našim žánrům/tagům.
# Pokud False, exportují se všechny skenované hry s dostupnými daty.
USE_INCLUSION_FILTER = True

# Ruční pojistka: appid sem lze přidat, pokud chceme hru zařadit i bez tagové shody.
FORCE_INCLUDE_APPIDS = set([
    # 632470,   # Disco Elysium - The Final Cut
])

# Pauza po skutečném web requestu. Čtení z cache nepauzuje.
SLEEP_AFTER_WEB_REQUEST = 1.0

MAX_RETRIES = 5
DEFAULT_429_WAIT_SECONDS = 60

SAVE_EVERY_FOUND = 25
PROGRESS_EVERY_SCANNED = 50

VERBOSE_HTTP = False

OUTPUT_PREFIX = "steam_corpus_candidates"

# Master výstupy. Skript na ně appenduje a deduplikuje podle appid.
MASTER_ALL_CSV = f"{OUTPUT_PREFIX}_master.csv"
MASTER_ALL_XLSX = f"{OUTPUT_PREFIX}_master.xlsx"
MASTER_TOP_CSV = f"{OUTPUT_PREFIX}_top{TOP_N}_master.csv"
MASTER_TOP_XLSX = f"{OUTPUT_PREFIX}_top{TOP_N}_master.xlsx"

RUNS_DIR = Path("steam_runs")
RUNS_DIR.mkdir(exist_ok=True)

# Import starých / recovered CSV.
# Recovered je záměrně poslední, aby při duplicitách přepsal starší verze.
EXISTING_BATCH_CSV_PATTERNS = [
    "steam_corpus_candidates_all_scanned.csv",
    "steam_runs/*/batch_all_scanned.csv",
    "steam_corpus_candidates_master_RECOVERED_best.csv",
]

REQUEST_HEADERS = {
    "User-Agent": "FIT-CTU-research-script/0.1 contact: richtrad@fit.cvut.cz"
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


# ============================================================
# BASIC HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_term(s):
    s = str(s).lower()

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
        "\"": "",
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


def read_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


# ============================================================
# CSV / EXCEL OUTPUT HELPERS
# ============================================================

# openpyxl/Excel nesnese některé neviditelné control characters.
# Steam short_description je občas obsahuje a pak spadne celý XLSX export.
# Původní regex čistil jen object sloupce; to nestačí, protože pandas může mít
# string/categorical/mixed sloupce. Tady čistíme KAŽDOU string hodnotu.
ILLEGAL_EXCEL_CHARS_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]")
EXCEL_MAX_CELL_CHARS = 32767


def clean_excel_value(value):
    """Vrátí hodnotu bezpečnou pro zápis přes openpyxl do XLSX."""
    if isinstance(value, str):
        # 1) explicitní Excel/openpyxl control chars
        value = ILLEGAL_EXCEL_CHARS_RE.sub("", value)

        # 2) širší pojistka: odstraň Unicode control/surrogate/private/noncharacter
        #    kromě běžných whitespace znaků, které Excel snese.
        safe_chars = []
        for ch in value:
            code = ord(ch)
            if ch in "\t\n\r":
                safe_chars.append(ch)
                continue
            if code < 32:
                continue
            if 0x7F <= code <= 0x9F:
                continue
            if 0xD800 <= code <= 0xDFFF:
                continue
            if code in (0xFFFE, 0xFFFF):
                continue
            safe_chars.append(ch)
        value = "".join(safe_chars)

        # 3) Excel limit na délku buňky
        if len(value) > EXCEL_MAX_CELL_CHARS:
            value = value[:EXCEL_MAX_CELL_CHARS - 20] + " …[truncated]"
    return value


def clean_dataframe_for_excel(df):
    """Vyčistí všechny string hodnoty ve všech sloupcích, nejen dtype=object."""
    cleaned = df.copy()
    for col in cleaned.columns:
        cleaned[col] = cleaned[col].map(clean_excel_value)
    return cleaned


def read_csv_safely(path):
    return pd.read_csv(path, low_memory=False)


def write_dataframe_csv_atomic(df, path):
    path = Path(path)
    tmp_path = path.with_name(path.stem + ".tmp.csv")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(path)


def write_dataframe_xlsx_atomic(df, path):
    """
    Bezpečný XLSX export.

    DŮLEŽITÉ: CSV je kanonický výstup. XLSX je jen pohodlná kopie pro Excel.
    Pokud XLSX selže i po čištění, skript NESMÍ spadnout a zahodit běh.
    """
    path = Path(path)
    tmp_path = path.with_name(path.stem + ".tmp.xlsx")
    df_for_excel = clean_dataframe_for_excel(df)

    try:
        df_for_excel.to_excel(tmp_path, index=False, engine="openpyxl")
        tmp_path.replace(path)
        return True
    except PermissionError:
        # Excel/OneDrive umí cílový soubor zamknout. Zachráníme timestampovanou kopii.
        fallback = path.with_name(path.stem + "_LOCKED_" + datetime.now().strftime("%Y%m%d_%H%M%S") + path.suffix)
        print(f"WARNING: {path} is locked. Saving XLSX as {fallback}")
        try:
            df_for_excel.to_excel(fallback, index=False, engine="openpyxl")
            return True
        except Exception as e:
            print(f"WARNING: XLSX fallback also failed: {type(e).__name__}: {e}")
            print("CSV output is already saved / will be saved; continuing without XLSX.")
            return False
    except Exception as e:
        # Poslední pojistka: žádný XLSX problém nesmí zabít dlouhý scraping run.
        print(f"WARNING: XLSX export failed for {path}: {type(e).__name__}: {e}")
        print("CSV output is canonical and remains available; continuing without XLSX.")
        return False
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def normalize_master_df(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    if "appid" in df.columns:
        df = df[df["appid"].notna()]
        df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
        df = df[df["appid"].notna()]
        df["appid"] = df["appid"].astype(int)
        df = df.drop_duplicates(subset=["appid"], keep="last")

    if "total_ratings_pos_neg" in df.columns:
        df["total_ratings_pos_neg"] = pd.to_numeric(df["total_ratings_pos_neg"], errors="coerce")

    if "relevance_score" in df.columns:
        df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce")

    if "absolute_index" in df.columns:
        df["absolute_index"] = pd.to_numeric(df["absolute_index"], errors="coerce")

    sort_cols = [c for c in ["total_ratings_pos_neg", "relevance_score"] if c in df.columns]
    if sort_cols:
        ascending = [False for _ in sort_cols]
        df = df.sort_values(by=sort_cols, ascending=ascending, na_position="last")

    return df.reset_index(drop=True)


def load_master_df():
    if Path(MASTER_ALL_CSV).exists():
        return normalize_master_df(read_csv_safely(MASTER_ALL_CSV))

    return pd.DataFrame()


def save_master_outputs(master_df):
    master_df = normalize_master_df(master_df)
    if master_df.empty:
        print("Master is empty; nothing to save.")
        return master_df

    top_df = master_df.head(TOP_N)

    write_dataframe_csv_atomic(master_df, MASTER_ALL_CSV)
    write_dataframe_xlsx_atomic(master_df, MASTER_ALL_XLSX)
    write_dataframe_csv_atomic(top_df, MASTER_TOP_CSV)
    write_dataframe_xlsx_atomic(top_df, MASTER_TOP_XLSX)

    print(f"Saved {MASTER_ALL_CSV} ({len(master_df)} rows)")
    print(f"Saved {MASTER_ALL_XLSX}")
    print(f"Saved {MASTER_TOP_CSV} ({len(top_df)} rows)")
    print(f"Saved {MASTER_TOP_XLSX}")

    return master_df


def get_seen_appids_from_master():
    master_df = load_master_df()
    if master_df.empty or "appid" not in master_df.columns:
        return set()
    return set(master_df["appid"].dropna().astype(int))


def get_resume_start_from_master(default_start):
    master_df = load_master_df()
    if master_df.empty or "absolute_index" not in master_df.columns:
        return default_start

    max_abs = pd.to_numeric(master_df["absolute_index"], errors="coerce").max()
    if pd.isna(max_abs):
        return default_start

    resume = int(max_abs) + 1
    if resume > default_start:
        print(f"AUTO_RESUME_FROM_MASTER: max absolute_index={int(max_abs)}, starting at {resume}")
        return resume

    return default_start


def import_existing_batch_csvs_to_master():
    if not IMPORT_EXISTING_BATCH_CSVS_ON_START:
        return load_master_df()

    frames = []

    existing_master = load_master_df()
    if not existing_master.empty:
        frames.append(existing_master)
        print(f"Loaded existing master: {MASTER_ALL_CSV} ({len(existing_master)} rows)")

    imported_paths = []
    for pattern in EXISTING_BATCH_CSV_PATTERNS:
        for raw_path in glob.glob(pattern):
            path = Path(raw_path)
            if not path.exists() or path.name.endswith(".tmp.csv"):
                continue
            if path.resolve() == Path(MASTER_ALL_CSV).resolve():
                continue
            if path in imported_paths:
                continue

            try:
                df = read_csv_safely(path)
                if df.empty or "appid" not in df.columns:
                    print(f"Skipping {path}: no appid / empty")
                    continue
                frames.append(df)
                imported_paths.append(path)
                print(f"Importing existing batch CSV into master: {path} ({len(df)} rows)")
            except Exception as e:
                print(f"WARNING: failed to import {path}: {e}")

    if not frames:
        return pd.DataFrame()

    master_df = normalize_master_df(pd.concat(frames, ignore_index=True, sort=False))
    master_df = save_master_outputs(master_df)
    return master_df


def make_run_dir(start_index, scan_limit):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_DIR / f"start{start_index}_limit{scan_limit}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def request_json(url, params=None, timeout=60, label="request"):
    """
    GET request s retry logikou.
    Nepoužívá raise_for_status(), aby při chybě nevypsal URL s API key.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.get(
            url,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=timeout
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")

            if retry_after and retry_after.isdigit():
                wait_seconds = int(retry_after)
            else:
                wait_seconds = DEFAULT_429_WAIT_SECONDS * attempt

            print(
                f"429 Too Many Requests during {label}. "
                f"Waiting {wait_seconds}s, attempt {attempt}/{MAX_RETRIES}..."
            )
            time.sleep(wait_seconds)
            continue

        if response.status_code in {500, 502, 503, 504}:
            wait_seconds = 10 * attempt
            print(
                f"{response.status_code} server error during {label}. "
                f"Waiting {wait_seconds}s, attempt {attempt}/{MAX_RETRIES}..."
            )
            time.sleep(wait_seconds)
            continue

        if VERBOSE_HTTP:
            print(f"{label} HTTP status:", response.status_code)

        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"{label} failed with HTTP status {response.status_code}"
            )

        return response.json()

    raise RuntimeError(f"Repeated request failure during {label}")


def get_cached_or_fetch(cache_path: Path, fetch_function, label: str, force_refresh=False):
    if cache_path.exists() and not force_refresh:
        return read_json(cache_path), True

    data = fetch_function()

    wrapped = {
        "fetched_at": now_iso(),
        "label": label,
        "data": data,
    }

    write_json(cache_path, wrapped)
    time.sleep(SLEEP_AFTER_WEB_REQUEST)

    return wrapped, False


# ============================================================
# APP LIST
# ============================================================

def fetch_app_list_from_steam_istoreservice():
    """
    Stáhne celý app list přes IStoreService a stránkuje přes last_appid.
    """
    if not STEAM_API_KEY:
        raise RuntimeError(
            'STEAM_API_KEY is not set. In PowerShell use: '
            '$env:STEAM_API_KEY="YOUR_KEY"'
        )

    url = "https://api.steampowered.com/IStoreService/GetAppList/v1/"

    all_apps = []
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

        raw = request_json(
            url,
            params=params,
            timeout=90,
            label=f"IStoreService app list page {page}"
        )

        batch = raw.get("response", {}).get("apps", [])

        if not batch:
            print("No more app list pages.")
            break

        all_apps.extend(batch)

        new_last_appid = int(batch[-1]["appid"])

        print(
            f"Fetched app list page {page}: {len(batch)} apps, "
            f"last_appid={new_last_appid}, total={len(all_apps)}"
        )

        if new_last_appid == last_appid:
            print("last_appid did not change, stopping to avoid loop.")
            break

        last_appid = new_last_appid

        if len(batch) < max_results:
            print("Last app list page shorter than max_results, stopping.")
            break

        time.sleep(SLEEP_AFTER_WEB_REQUEST)

    return {
        "response": {
            "apps": all_apps
        }
    }


def fetch_app_list_from_github_fallback():
    """
    Fallback seznam appid. Bereme jako technickou pojistku,
    ne jako hlavní vědecký zdroj.
    """
    url = "https://raw.githubusercontent.com/jsnli/steamappidlist/master/data/games_appid.json"

    return request_json(
        url,
        params=None,
        timeout=90,
        label="GitHub app list fallback"
    )


def normalize_app_list(raw):
    data = raw

    if isinstance(data, dict):
        if "response" in data and "apps" in data["response"]:
            data = data["response"]["apps"]
        elif "applist" in data and "apps" in data["applist"]:
            data = data["applist"]["apps"]
        elif "apps" in data:
            data = data["apps"]
        else:
            data = list(data.values())

    df = pd.DataFrame(data)

    if "app_name" in df.columns and "name" not in df.columns:
        df = df.rename(columns={"app_name": "name"})

    if "appid" not in df.columns:
        possible = [c for c in df.columns if c.lower() in ["appid", "app_id", "id"]]
        if possible:
            df = df.rename(columns={possible[0]: "appid"})

    if "name" not in df.columns:
        df["name"] = ""

    df = df[df["appid"].notna()]
    df = df[df["name"].notna()]
    df = df[df["name"].astype(str).str.strip() != ""]

    df["appid"] = df["appid"].astype(int)
    df["name"] = df["name"].astype(str)
    df["norm_name"] = df["name"].apply(normalize_term)

    df = df.drop_duplicates(subset=["appid"])
    df = df.sort_values("appid").reset_index(drop=True)

    return df


def get_app_list():
    if APP_LIST_CACHE.exists() and not APP_LIST_FORCE_REFRESH:
        wrapped = read_json(APP_LIST_CACHE)
        print("App list loaded from cache.")
        return normalize_app_list(wrapped["data"])

    print("Fetching app list...")

    try:
        raw = fetch_app_list_from_steam_istoreservice()
        source = "steam_istoreservice"
    except Exception as e:
        print("Steam IStoreService failed:")
        print(e)
        print("Trying GitHub fallback app list...")
        raw = fetch_app_list_from_github_fallback()
        source = "github_fallback"

    wrapped = {
        "fetched_at": now_iso(),
        "source": source,
        "data": raw,
    }

    write_json(APP_LIST_CACHE, wrapped)

    return normalize_app_list(raw)


# ============================================================
# APP DETAILS
# ============================================================

def fetch_app_details(appid: int):
    url = "https://store.steampowered.com/api/appdetails"

    params = {
        "appids": appid,
        "cc": "us",
        "l": "english",
    }

    return request_json(
        url,
        params=params,
        timeout=60,
        label=f"appdetails {appid}"
    )


def get_app_details(appid: int):
    cache_path = DETAILS_CACHE_DIR / f"{appid}.json"

    wrapped, from_cache = get_cached_or_fetch(
        cache_path=cache_path,
        fetch_function=lambda: fetch_app_details(appid),
        label=f"appdetails:{appid}",
        force_refresh=FORCE_REFRESH_DETAILS,
    )

    raw = wrapped["data"]
    item = raw.get(str(appid), {})

    if not item.get("success"):
        return None, from_cache

    return item.get("data", {}), from_cache


# ============================================================
# REVIEWS
# ============================================================

def fetch_review_summary(appid: int):
    url = f"https://store.steampowered.com/appreviews/{appid}"

    params = {
        "json": 1,
        "filter": "all",
        "language": "all",
        "purchase_type": "all",
        "num_per_page": 0,
    }

    return request_json(
        url,
        params=params,
        timeout=45,
        label=f"reviews {appid}"
    )


def get_review_summary(appid: int):
    cache_path = REVIEWS_CACHE_DIR / f"{appid}.json"

    try:
        wrapped, from_cache = get_cached_or_fetch(
            cache_path=cache_path,
            fetch_function=lambda: fetch_review_summary(appid),
            label=f"reviews:{appid}",
            force_refresh=FORCE_REFRESH_REVIEWS,
        )

        raw = wrapped["data"]
        summary = raw.get("query_summary", {})

        total_positive = summary.get("total_positive") or 0
        total_negative = summary.get("total_negative") or 0
        total_reviews = summary.get("total_reviews") or 0
        total_ratings_pos_neg = total_positive + total_negative

        positive_ratio = None
        if total_ratings_pos_neg > 0:
            positive_ratio = total_positive / total_ratings_pos_neg

        return {
            "total_reviews": total_reviews,
            "total_positive": total_positive,
            "total_negative": total_negative,
            "total_ratings_pos_neg": total_ratings_pos_neg,
            "positive_ratio": positive_ratio,
            "review_score": summary.get("review_score"),
            "review_score_desc": summary.get("review_score_desc"),
            "reviews_from_cache": from_cache,
        }

    except Exception as e:
        return {
            "total_reviews": None,
            "total_positive": None,
            "total_negative": None,
            "total_ratings_pos_neg": None,
            "positive_ratio": None,
            "review_score": None,
            "review_score_desc": None,
            "reviews_from_cache": False,
            "review_error": str(e),
        }


# ============================================================
# STEAMSPY TAGS
# ============================================================

def fetch_steamspy_details(appid: int):
    url = "https://steamspy.com/api.php"

    params = {
        "request": "appdetails",
        "appid": appid,
    }

    return request_json(
        url,
        params=params,
        timeout=60,
        label=f"steamspy {appid}"
    )


def get_steamspy_details(appid: int):
    cache_path = STEAMSPY_CACHE_DIR / f"{appid}.json"

    try:
        wrapped, from_cache = get_cached_or_fetch(
            cache_path=cache_path,
            fetch_function=lambda: fetch_steamspy_details(appid),
            label=f"steamspy:{appid}",
            force_refresh=FORCE_REFRESH_STEAMSPY,
        )

        return wrapped["data"], from_cache

    except Exception as e:
        return {
            "steamspy_error": str(e)
        }, False


# ============================================================
# EXTRACTION
# ============================================================

def extract_steam_genres(details):
    if not details:
        return []

    return [
        g.get("description", "")
        for g in details.get("genres", []) or []
        if g.get("description")
    ]


def extract_steam_categories(details):
    if not details:
        return []

    return [
        c.get("description", "")
        for c in details.get("categories", []) or []
        if c.get("description")
    ]


def extract_steamspy_tags(steamspy_data):
    if not steamspy_data:
        return []

    tags = steamspy_data.get("tags", {})

    if isinstance(tags, dict):
        return list(tags.keys())

    if isinstance(tags, list):
        return tags

    return []


def find_matching_terms(all_terms, inclusion_terms):
    matches = []

    normalized_terms = []
    for term in all_terms:
        if term is None:
            continue
        normalized_terms.append((normalize_term(term), term))

    for inclusion in inclusion_terms:
        inc_norm = normalize_term(inclusion)

        for term_norm, original_term in normalized_terms:
            if inc_norm == term_norm or inc_norm in term_norm or term_norm in inc_norm:
                matches.append(original_term)

    return sorted(set(matches))


def calculate_relevance_score(matching_terms):
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


def classify_bucket(matching_terms):
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

    if matching_terms:
        return "general genre match"

    return "NO MATCH"


def flatten_details(details, steamspy_data):
    if not details:
        details = {}

    release_date = details.get("release_date", {}) or {}
    platforms = details.get("platforms", {}) or {}
    metacritic = details.get("metacritic", {}) or {}
    recommendations = details.get("recommendations", {}) or {}
    support_info = details.get("support_info", {}) or {}

    developers = ", ".join(details.get("developers", []) or [])
    publishers = ", ".join(details.get("publishers", []) or [])

    steam_genres = ", ".join(extract_steam_genres(details))
    steam_categories = ", ".join(extract_steam_categories(details))

    return {
        "steam_type": details.get("type"),
        "steam_name": details.get("name"),
        "is_free": details.get("is_free"),
        "required_age": details.get("required_age"),
        "release_date_coming_soon": release_date.get("coming_soon"),
        "steam_release_date": release_date.get("date"),
        "developers": developers,
        "publishers": publishers,
        "steam_genres": steam_genres,
        "steam_categories": steam_categories,
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
        "steamspy_owners": steamspy_data.get("owners") if steamspy_data else None,
        "steamspy_median_forever": steamspy_data.get("median_forever") if steamspy_data else None,
        "steamspy_average_forever": steamspy_data.get("average_forever") if steamspy_data else None,
    }


def add_manual_corpus_columns(row):
    manual = {
        "include_in_corpus": "",
        "exclusion_reason": "",
        "original_release_year": "",
        "original_release_decade": "",
        "game_series": "",
        "protagonist": "",
        "protagonist_type": "",
        "protagonist_gender": "",
        "primary_archetype": "",
        "secondary_archetype": "",
        "shadow_load_0_3": "",
        "player_projection_0_3": "",
        "narrative_complexity_0_3": "",
        "corpus_notes": "",
        "coding_source": "",
    }

    return {**row, **manual}


# ============================================================
# OUTPUT
# ============================================================

def save_outputs(rows, run_dir=None, final=False):
    if not rows:
        print("No new rows to save yet.")
        return load_master_df()

    batch_df = pd.DataFrame(rows)
    batch_df = normalize_master_df(batch_df)

    if run_dir is not None:
        batch_csv = run_dir / "batch_all_scanned.csv"
        batch_xlsx = run_dir / "batch_all_scanned.xlsx"
        batch_top_csv = run_dir / f"batch_top{TOP_N}_by_reviews.csv"
        batch_top_xlsx = run_dir / f"batch_top{TOP_N}_by_reviews.xlsx"

        write_dataframe_csv_atomic(batch_df, batch_csv)
        write_dataframe_xlsx_atomic(batch_df, batch_xlsx)
        write_dataframe_csv_atomic(batch_df.head(TOP_N), batch_top_csv)
        write_dataframe_xlsx_atomic(batch_df.head(TOP_N), batch_top_xlsx)

        print(f"Saved run batch: {batch_csv} ({len(batch_df)} rows)")

    old_master_df = load_master_df()

    if old_master_df.empty:
        master_df = batch_df
    else:
        master_df = pd.concat([old_master_df, batch_df], ignore_index=True, sort=False)

    master_df = save_master_outputs(master_df)

    preview_cols = [
        "appid",
        "steam_name",
        "bucket",
        "matched_terms",
        "total_ratings_pos_neg",
        "positive_ratio",
        "review_score_desc",
        "steam_release_date",
        "steam_genres",
        "steamspy_tags",
    ]
    existing_cols = [c for c in preview_cols if c in master_df.columns]

    print("\nCurrent master top candidates:")
    print(master_df[existing_cols].head(30).to_string(index=False))

    if final:
        print("\nFinal master saved.")

    return master_df


# ============================================================
# MAIN
# ============================================================

def main():
    apps = get_app_list()

    print(f"\nTotal apps available: {len(apps)}")
    print(apps.head(10))

    app_slice = apps.iloc[START_INDEX:START_INDEX + SCAN_LIMIT]

    rows = []
    scanned = 0
    found = 0
    errors = 0

    try:
        for absolute_index, app_row in app_slice.iterrows():
            scanned += 1

            appid = int(app_row["appid"])
            list_name = str(app_row.get("name", ""))

            try:
                details, details_from_cache = get_app_details(appid)
            except Exception as e:
                errors += 1
                print(f"DETAILS FAILED for {appid} {list_name}: {e}")
                time.sleep(5)
                continue

            steamspy_data, steamspy_from_cache = get_steamspy_details(appid)

            steam_genres = extract_steam_genres(details)
            steam_categories = extract_steam_categories(details)
            steamspy_tags = extract_steamspy_tags(steamspy_data)

            all_terms = steam_genres + steam_categories + steamspy_tags
            matching_terms = find_matching_terms(all_terms, INCLUSION_TERMS)

            forced_include = appid in FORCE_INCLUDE_APPIDS
            would_include = forced_include or len(matching_terms) > 0 or not USE_INCLUSION_FILTER

            if not would_include:
                if scanned % PROGRESS_EVERY_SCANNED == 0:
                    print(
                        f"Checked {scanned}/{SCAN_LIMIT} "
                        f"(absolute index {absolute_index}), "
                        f"found={found}, errors={errors}"
                    )
                continue

            reviews = get_review_summary(appid)

            relevance_score = calculate_relevance_score(matching_terms)
            bucket = classify_bucket(matching_terms)

            flat = flatten_details(details, steamspy_data)

            row = {
                "appid": appid,
                "name_from_app_list": list_name,
                "absolute_index": absolute_index,
                "details_from_cache": details_from_cache,
                "steamspy_from_cache": steamspy_from_cache,
                "forced_include": forced_include,
                "bucket": bucket,
                "matched_terms": ", ".join(matching_terms),
                "relevance_score": relevance_score,
                "steamspy_tags": ", ".join(steamspy_tags),
                **flat,
                **reviews,
            }

            row = add_manual_corpus_columns(row)
            rows.append(row)

            found += 1

            print(
                f"{scanned}/{SCAN_LIMIT} "
                f"(absolute index {absolute_index}): FOUND - "
                f"{appid} {flat.get('steam_name') or list_name} | "
                f"bucket={bucket} | "
                f"ratings={reviews.get('total_ratings_pos_neg')} | "
                f"details_cache={details_from_cache} | "
                f"steamspy_cache={steamspy_from_cache} | "
                f"reviews_cache={reviews.get('reviews_from_cache')}"
            )

            if found % SAVE_EVERY_FOUND == 0:
                print("\nAutosaving partial outputs...")
                save_outputs(rows)
                print("Autosave done.\n")

    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving partial outputs...")

    finally:
        print("\nFinal save...")
        save_outputs(rows)
        print(
            f"\nDone. scanned={scanned}, found={found}, errors={errors}, "
            f"START_INDEX={START_INDEX}, SCAN_LIMIT={SCAN_LIMIT}"
        )


if __name__ == "__main__":
    main()
