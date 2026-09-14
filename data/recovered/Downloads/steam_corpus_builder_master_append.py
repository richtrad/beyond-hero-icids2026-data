import os
import json
import time
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
START_INDEX = 5000
SCAN_LIMIT = 5000
TOP_N = 250

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

OUTPUT_PREFIX = "steam_corpus_candidates"  # legacy batch prefix, kept for compatibility

# ------------------------------------------------------------
# MASTER OUTPUTS
# ------------------------------------------------------------
# Hlavní výstup se už nepřepisuje po blocích. Každý běh přidá
# nalezené kandidáty do master CSV a podle appid provede deduplikaci.
# XLSX se vždy znovu vygeneruje z master CSV, aby se nepoškodil při pádu.
MASTER_ALL_CSV = Path("steam_corpus_candidates_master.csv")
MASTER_ALL_XLSX = Path("steam_corpus_candidates_master.xlsx")
MASTER_TOP_CSV = Path(f"steam_corpus_candidates_top{TOP_N}_master.csv")
MASTER_TOP_XLSX = Path(f"steam_corpus_candidates_top{TOP_N}_master.xlsx")

# Volitelná archivace aktuálního běhu do samostatné složky. Název se vytvoří automaticky.
WRITE_RUN_SNAPSHOT_FILES = True
RUNS_DIR = Path("steam_runs")
RUN_TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_ID = f"start{START_INDEX}_limit{SCAN_LIMIT}_{RUN_TIMESTAMP}"
RUN_OUTPUT_DIR = RUNS_DIR / RUN_ID

# CSV master se aktualizuje často; XLSX je dražší, proto méně často.
# Finální uložení XLSX proběhne vždy na konci běhu.
XLSX_SAVE_EVERY_FOUND = 250

# Pokud True, appid už přítomné v master CSV se přeskočí úplně.
# Default False je bezpečnější: opakovaný běh projde data z cache a master se jen deduplikuje.
SKIP_APPIDS_ALREADY_IN_MASTER = False

# Pokud True, skript se na začátku pokusí načíst starší dávkové CSV soubory
# typu steam_corpus_candidates*_all_scanned.csv a přidat je do masteru.
# To pomůže, pokud už máš hotové první běhy ze starší verze skriptu.
IMPORT_EXISTING_CSVS_TO_MASTER_ON_START = True
EXISTING_BATCH_CSV_PATTERNS = [
    "steam_corpus_candidates*_all_scanned.csv",
    "steam_runs/*/batch_all_scanned.csv",
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


def write_dataframe_csv_atomic(df: pd.DataFrame, path: Path):
    """Zapíše CSV přes dočasný soubor, aby se při pádu méně riskovalo poškození."""
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(path)


def write_dataframe_xlsx_atomic(df: pd.DataFrame, path: Path):
    """Zapíše XLSX přes dočasný soubor. XLSX negenerujeme appendem po řádcích."""
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_excel(tmp_path, index=False)
    tmp_path.replace(path)


def align_dataframes_for_concat(old_df: pd.DataFrame, new_df: pd.DataFrame):
    """Sjednotí sloupce před concatem, aby se master dal rozšiřovat o nové proměnné."""
    all_columns = list(old_df.columns)
    for col in new_df.columns:
        if col not in all_columns:
            all_columns.append(col)

    for col in old_df.columns:
        if col not in new_df.columns:
            new_df[col] = ""

    for col in new_df.columns:
        if col not in old_df.columns:
            old_df[col] = ""

    return old_df[all_columns], new_df[all_columns]


def load_master_appids():
    if not MASTER_ALL_CSV.exists():
        return set()

    try:
        df = pd.read_csv(MASTER_ALL_CSV, usecols=["appid"])
        return set(df["appid"].dropna().astype(int).tolist())
    except Exception:
        return set()


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
        "player_shaped_arc": "",
        "ensemble_archetypes": "",
        "llm_primary_archetype_suggestion": "",
        "llm_secondary_archetype_suggestion": "",
        "llm_shadow_load_suggestion": "",
        "human_validation_primary_mode": "",
        "human_validation_secondary_mode": "",
        "human_validation_agreement_score": "",
        "human_validation_votes_json": "",
        "corpus_notes": "",
        "coding_source": "",
    }

    return {**row, **manual}


# ============================================================
# OUTPUT
# ============================================================

def sort_for_review_priority(df: pd.DataFrame):
    if df.empty:
        return df

    sort_cols = []
    ascending = []

    if "total_ratings_pos_neg" in df.columns:
        sort_cols.append("total_ratings_pos_neg")
        ascending.append(False)

    if "relevance_score" in df.columns:
        sort_cols.append("relevance_score")
        ascending.append(False)

    if sort_cols:
        return df.sort_values(
            by=sort_cols,
            ascending=ascending,
            na_position="last"
        )

    return df


def sort_master_rows(df: pd.DataFrame):
    if df.empty:
        return df

    if "absolute_index" in df.columns and "appid" in df.columns:
        return df.sort_values(
            by=["absolute_index", "appid"],
            ascending=[True, True],
            na_position="last"
        )

    if "appid" in df.columns:
        return df.sort_values(by=["appid"], ascending=[True], na_position="last")

    return df


def append_to_master_csv(new_df: pd.DataFrame):
    """
    Přidá aktuální batch do master CSV a deduplikuje podle appid.
    Vrací celý master DataFrame po deduplikaci.
    """
    if new_df is None or new_df.empty:
        if MASTER_ALL_CSV.exists():
            return pd.read_csv(MASTER_ALL_CSV)
        return pd.DataFrame()

    new_df = new_df.copy()

    if MASTER_ALL_CSV.exists():
        old_df = pd.read_csv(MASTER_ALL_CSV)
        old_df, new_df = align_dataframes_for_concat(old_df, new_df)
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df

    if "appid" in combined.columns:
        # keep="last" znamená: pokud se stejná hra objeví znovu, novější řádek nahradí starý.
        combined = combined.drop_duplicates(subset=["appid"], keep="last")

    combined = sort_master_rows(combined)
    write_dataframe_csv_atomic(combined, MASTER_ALL_CSV)

    return combined


def save_master_top_outputs(master_df: pd.DataFrame, force_xlsx=False):
    if master_df is None or master_df.empty:
        return pd.DataFrame()

    top_df = sort_for_review_priority(master_df).head(TOP_N)
    write_dataframe_csv_atomic(top_df, MASTER_TOP_CSV)

    if force_xlsx:
        write_dataframe_xlsx_atomic(top_df, MASTER_TOP_XLSX)

    return top_df


def save_run_snapshot(rows, force_xlsx=False):
    """
    Volitelně uloží samostatný snapshot právě běžící dávky do steam_runs/RUN_ID.
    Tím máme auditní stopu, ale ručně nepřepisujeme OUTPUT_PREFIX.
    """
    if not WRITE_RUN_SNAPSHOT_FILES or not rows:
        return

    RUN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    df = sort_for_review_priority(df)
    top = df.head(TOP_N)

    all_csv = RUN_OUTPUT_DIR / "batch_all_scanned.csv"
    top_csv = RUN_OUTPUT_DIR / f"batch_top{TOP_N}_by_reviews.csv"

    write_dataframe_csv_atomic(df, all_csv)
    write_dataframe_csv_atomic(top, top_csv)

    if force_xlsx:
        all_xlsx = RUN_OUTPUT_DIR / "batch_all_scanned.xlsx"
        top_xlsx = RUN_OUTPUT_DIR / f"batch_top{TOP_N}_by_reviews.xlsx"
        write_dataframe_xlsx_atomic(df, all_xlsx)
        write_dataframe_xlsx_atomic(top, top_xlsx)


def import_existing_batch_csvs_to_master():
    """
    Jednorázově přidá starší dávkové CSV výstupy do master CSV.
    Deduplikace proběhne podle appid. Master/top XLSX se potom vygeneruje.
    """
    if not IMPORT_EXISTING_CSVS_TO_MASTER_ON_START:
        return

    candidate_paths = []
    for pattern in EXISTING_BATCH_CSV_PATTERNS:
        candidate_paths.extend(Path(".").glob(pattern))

    # Neimportovat master/top master ani logy.
    filtered_paths = []
    for path in candidate_paths:
        name = path.name.lower()
        if "master" in name:
            continue
        if "top" in name:
            continue
        if not path.exists():
            continue
        filtered_paths.append(path)

    if not filtered_paths:
        return

    imported_frames = []
    for path in sorted(set(filtered_paths)):
        try:
            df = pd.read_csv(path)
            if "appid" in df.columns and not df.empty:
                imported_frames.append(df)
                print(f"Importing existing batch CSV into master: {path} ({len(df)} rows)")
        except Exception as e:
            print(f"Could not import {path}: {e}")

    if not imported_frames:
        return

    combined = pd.concat(imported_frames, ignore_index=True)
    master_df = append_to_master_csv(combined)
    top_df = save_master_top_outputs(master_df, force_xlsx=True)
    write_dataframe_xlsx_atomic(master_df, MASTER_ALL_XLSX)

    print(
        f"Existing batch import done. Master rows={len(master_df)}, "
        f"top rows={len(top_df)}"
    )


def save_outputs(rows, force_xlsx=False, final=False):
    """
    Hlavní save funkce:
    1) aktuální rows přidá do master CSV,
    2) deduplikuje podle appid,
    3) vygeneruje top master CSV,
    4) XLSX generuje jen občas nebo finálně.
    """
    if not rows:
        print("No rows to save yet.")
        return

    batch_df = pd.DataFrame(rows)

    should_write_xlsx = (
        force_xlsx
        or final
        or (len(batch_df) > 0 and len(batch_df) % XLSX_SAVE_EVERY_FOUND == 0)
    )

    master_df = append_to_master_csv(batch_df)
    top_df = save_master_top_outputs(master_df, force_xlsx=should_write_xlsx)

    if should_write_xlsx:
        write_dataframe_xlsx_atomic(master_df, MASTER_ALL_XLSX)

    save_run_snapshot(rows, force_xlsx=should_write_xlsx)

    print(f"Saved/updated {MASTER_ALL_CSV} ({len(master_df)} unique rows)")
    print(f"Saved/updated {MASTER_TOP_CSV} ({len(top_df)} rows)")

    if should_write_xlsx:
        print(f"Saved/updated {MASTER_ALL_XLSX}")
        print(f"Saved/updated {MASTER_TOP_XLSX}")
        if WRITE_RUN_SNAPSHOT_FILES:
            print(f"Saved/updated run snapshot XLSX in {RUN_OUTPUT_DIR}")

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

    existing_cols = [c for c in preview_cols if c in top_df.columns]

    print("\nCurrent top master candidates:")
    print(top_df[existing_cols].head(30).to_string(index=False))


# ============================================================
# MAIN
# ============================================================

def main():
    apps = get_app_list()

    print(f"\nTotal apps available: {len(apps)}")
    print(apps.head(10))

    app_slice = apps.iloc[START_INDEX:START_INDEX + SCAN_LIMIT]

    import_existing_batch_csvs_to_master()

    already_in_master = load_master_appids() if SKIP_APPIDS_ALREADY_IN_MASTER else set()
    if already_in_master:
        print(f"Master already contains {len(already_in_master)} appids; those will be skipped.")

    print(f"Run ID: {RUN_ID}")
    print(f"Master CSV: {MASTER_ALL_CSV}")
    print(f"Run snapshot dir: {RUN_OUTPUT_DIR if WRITE_RUN_SNAPSHOT_FILES else 'disabled'}")

    rows = []
    scanned = 0
    found = 0
    errors = 0

    try:
        for absolute_index, app_row in app_slice.iterrows():
            scanned += 1

            appid = int(app_row["appid"])
            list_name = str(app_row.get("name", ""))

            if appid in already_in_master:
                if scanned % PROGRESS_EVERY_SCANNED == 0:
                    print(
                        f"Checked {scanned}/{SCAN_LIMIT} "
                        f"(absolute index {absolute_index}), "
                        f"found={found}, errors={errors}, skipped_existing_master={len(already_in_master)}"
                    )
                continue

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
                "run_id": RUN_ID,
                "run_start_index": START_INDEX,
                "run_scan_limit": SCAN_LIMIT,
                "scanned_at_utc": now_iso(),
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
        save_outputs(rows, force_xlsx=True, final=True)
        print(
            f"\nDone. scanned={scanned}, found={found}, errors={errors}, "
            f"START_INDEX={START_INDEX}, SCAN_LIMIT={SCAN_LIMIT}"
        )


if __name__ == "__main__":
    main()