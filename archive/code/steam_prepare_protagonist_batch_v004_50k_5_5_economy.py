#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_prepare_protagonist_batch_v004_50k_5_5_economy.py

Prepare a cost-optimized OpenAI Batch JSONL for up to 50,000 Steam games.

Default behavior:
- Reads steam_bulk_outputs/steam_catalog_merged.csv
- Selects top 50,000 games by positive+negative review/reaction count
- Packs 50 games into one model request
- Uses gpt-5.5 by default
- Uses compact output codes to reduce output-token cost
- Writes a manifest and selected-games CSV for audit

This script only prepares files. It does NOT spend API money.
Money is spent only when you run the submit script.

Outputs:
  steam_bulk_outputs/steam_protagonist_batch_input_v004_50k_5_5_economy.jsonl
  steam_bulk_outputs/steam_protagonist_batch_manifest_v004_50k_5_5_economy.csv
  steam_bulk_outputs/steam_protagonist_batch_selected_games_v004_50k_5_5_economy.csv
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Optional

import pandas as pd


DEFAULT_INPUT = Path("steam_bulk_outputs/steam_catalog_merged.csv")
FALLBACK_INPUT = Path("steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv")

OUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_input_v004_50k_5_5_economy.jsonl")
OUT_MANIFEST = Path("steam_bulk_outputs/steam_protagonist_batch_manifest_v004_50k_5_5_economy.csv")
OUT_SELECTED = Path("steam_bulk_outputs/steam_protagonist_batch_selected_games_v004_50k_5_5_economy.csv")
OUT_ESTIMATE = Path("steam_bulk_outputs/steam_protagonist_batch_cost_estimate_v004_50k_5_5_economy.json")


ARCHETYPE_CODES = {
    "INN": "Innocent",
    "EVE": "Everyman/Orphan",
    "HER": "Hero/Warrior",
    "CAR": "Caregiver/Guardian",
    "EXP": "Explorer/Seeker",
    "REB": "Rebel/Outlaw",
    "LOV": "Lover",
    "CRE": "Creator/Artist",
    "JES": "Jester/Trickster",
    "SAG": "Sage/Investigator",
    "MAG": "Magician/Transformer",
    "RUL": "Ruler/Leader",
    "SHA": "Shadow/Antihero",
    "NA": "Not applicable",
    "UNC": "Uncertain",
}

PROTAGONIST_TYPE_CODES = {
    "fns": "fixed_named_single",
    "frs": "fixed_role_single",
    "sfx": "silent_fixed_protagonist",
    "nfx": "nonhuman_fixed_protagonist",
    "cbd": "customizable_but_defined",
    "fdu": "fixed_dual",
    "fen": "fixed_ensemble",
    "pav": "player_avatar_weakly_defined",
    "sys": "strategy_or_systemic_role",
    "sim": "simulator_or_management_role",
    "spr": "sports_or_racing_role",
    "nop": "no_clear_protagonist",
    "unc": "uncertain",
}

EXCLUSION_CODES = {
    "none": "none",
    "nop": "no_clear_protagonist",
    "sys": "pure_strategy_or_systemic_role",
    "sim": "simulator_or_management",
    "spr": "sports_or_racing",
    "multi": "multiplayer_only_or_no_story_focus",
    "unk": "unknown_game",
    "info": "insufficient_information",
    "other": "other",
}

SYSTEM_PROMPT = """You are building a research corpus for video game protagonist archetype analysis.

You will receive a JSON array of Steam games. Classify EACH game. Return exactly one item per input game, with the same appid in field "a". Do not skip games. Do not add games.

Use compact output codes exactly as defined.

Clear protagonist field h:
- y = clear usable main protagonist
- n = no clear usable main protagonist
- u = uncertain

Protagonist type pt:
- fns fixed named single protagonist
- frs fixed role single protagonist
- sfx silent fixed protagonist
- nfx nonhuman fixed protagonist
- cbd customizable but narratively defined protagonist
- fdu fixed dual protagonists
- fen fixed ensemble
- pav weakly defined player avatar
- sys strategy/systemic role: faction, empire, city, abstract commander
- sim simulator/management role
- spr sports/racing role
- nop no clear protagonist
- unc uncertain

Archetype codes p/s/t for primary/secondary/tertiary:
- INN Innocent: naive, pure, hopeful, childlike, uncorrupted, wonder
- EVE Everyman/Orphan: ordinary person, outsider, abandoned, survivor seeking belonging
- HER Hero/Warrior: courageous fighter, savior, protector through action/trials
- CAR Caregiver/Guardian: nurturer, parent, healer, protector, self-sacrifice
- EXP Explorer/Seeker: traveler, identity/world search, truth, freedom, origin
- REB Rebel/Outlaw: rule-breaker, revolutionary, criminal, anti-system defiance
- LOV Lover: love, intimacy, devotion, romance, loyalty, longing
- CRE Creator/Artist: maker, artist, inventor, writer, world-shaper
- JES Jester/Trickster: comic, chaotic, playful, deceptive, subversive wit
- SAG Sage/Investigator: detective, scholar, analyst, truth through reason/knowledge
- MAG Magician/Transformer: occult, supernatural, reality-changing, transformation
- RUL Ruler/Leader: monarch, commander, leader, burden of authority/governance
- SHA Shadow/Antihero: morally compromised, traumatized, violent, dark mirror
- NA Not applicable: no usable protagonist
- UNC Uncertain: insufficient reliable information

Other fields:
- pc/ac/su/sh/pp/nc are integers 0..3:
  pc protagonist confidence, ac archetype confidence, su suitability for final corpus,
  sh shadow/antihero load, pp player projection, nc narrative complexity.
- inc: y/n/m for include in final corpus yes/no/maybe.
- ex: none/nop/sys/sim/spr/multi/unk/info/other.
- mr: true if manual review is needed.
- eb: g general knowledge, c control seed, m metadata inference, u uncertain.
- note: very short audit note, max about 12 words.

Rules:
- p, s, and t MUST be archetype codes, not invented labels.
- If h is n, set p=NA, s=NA, t=NA, inc=n unless there is a special reason.
- If h is u, use p=UNC unless a safe archetype is obvious.
- If the player controls a faction/city/club/team/vehicle/system, usually h=n and pt=sys/sim/spr.
- If control seed protagonist cp is present, use it as strong evidence but still classify carefully.
- Keep output compact and deterministic.
"""

ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "a": {"type": "integer"},
        "h": {"type": "string", "enum": ["y", "n", "u"]},
        "pn": {"type": "string"},
        "pt": {"type": "string", "enum": list(PROTAGONIST_TYPE_CODES.keys())},
        "pc": {"type": "integer", "minimum": 0, "maximum": 3},
        "p": {"type": "string", "enum": list(ARCHETYPE_CODES.keys())},
        "s": {"type": "string", "enum": list(ARCHETYPE_CODES.keys())},
        "t": {"type": "string", "enum": list(ARCHETYPE_CODES.keys())},
        "ac": {"type": "integer", "minimum": 0, "maximum": 3},
        "su": {"type": "integer", "minimum": 0, "maximum": 3},
        "sh": {"type": "integer", "minimum": 0, "maximum": 3},
        "pp": {"type": "integer", "minimum": 0, "maximum": 3},
        "nc": {"type": "integer", "minimum": 0, "maximum": 3},
        "inc": {"type": "string", "enum": ["y", "n", "m"]},
        "ex": {"type": "string", "enum": list(EXCLUSION_CODES.keys())},
        "mr": {"type": "boolean"},
        "eb": {"type": "string", "enum": ["g", "c", "m", "u"]},
        "note": {"type": "string"}
    },
    "required": ["a", "h", "pn", "pt", "pc", "p", "s", "t", "ac", "su", "sh", "pp", "nc", "inc", "ex", "mr", "eb", "note"]
}

BATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": ITEM_SCHEMA
        }
    },
    "required": ["items"]
}


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def safe_str(x) -> str:
    if pd.isna(x):
        return ""
    return str(x)


def clean_short_text(x, max_chars: int = 320) -> str:
    s = safe_str(x).replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    if len(s) > max_chars:
        return s[:max_chars - 1] + "…"
    return s


def parse_num_series(df: pd.DataFrame, col: Optional[str], default=0) -> pd.Series:
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def combine_terms(row: pd.Series, cols: list[str], max_chars: int = 380) -> str:
    parts = []
    for c in cols:
        val = row.get(c, "")
        if pd.isna(val):
            continue
        s = str(val).strip()
        if s and s.lower() not in {"nan", "none", "null", "{}"}:
            parts.append(s)
    text = " | ".join(parts)
    text = " ".join(text.replace("\n", " ").replace("\r", " ").split())
    return text[:max_chars]


def select_games(df: pd.DataFrame, limit: int, min_reactions: int) -> pd.DataFrame:
    appid_col = find_col(df, ["appid", "steam_appid", "app_id"])
    name_col = find_col(df, ["name", "title", "steam_name", "app_name"])

    if not appid_col or not name_col:
        raise RuntimeError(f"Could not find appid/name columns. Columns: {list(df.columns)[:50]}")

    work = df.copy()
    work["appid"] = pd.to_numeric(work[appid_col], errors="coerce")
    work = work[work["appid"].notna()].copy()
    work["appid"] = work["appid"].astype(int)
    work["name"] = work[name_col].map(clean_short_text)

    total_col = find_col(work, ["total_ratings_pos_neg", "total_reviews", "review_count", "reviews_total"])
    pos_col = find_col(work, ["positive", "steamspy_positive", "reviews_positive", "positive_reviews", "review_positive"])
    neg_col = find_col(work, ["negative", "steamspy_negative", "reviews_negative", "negative_reviews", "review_negative"])

    if total_col:
        work["total_ratings_pos_neg"] = parse_num_series(work, total_col, 0).astype(int)
    else:
        pos = parse_num_series(work, pos_col, 0)
        neg = parse_num_series(work, neg_col, 0)
        work["total_ratings_pos_neg"] = (pos + neg).astype(int)

    if pos_col and neg_col:
        pos = parse_num_series(work, pos_col, 0)
        neg = parse_num_series(work, neg_col, 0)
        denom = (pos + neg).replace(0, pd.NA)
        work["positive_ratio"] = (pos / denom).fillna("").astype(str)
    elif "positive_ratio" in work.columns:
        work["positive_ratio"] = work["positive_ratio"].map(safe_str)
    else:
        work["positive_ratio"] = ""

    owners_col = find_col(work, ["steamspy_owners", "owners", "estimated_owners", "owners_estimate"])
    work["steamspy_owners"] = work[owners_col].map(clean_short_text) if owners_col else ""

    control_col = find_col(work, ["control_protagonist", "protagonist", "control_seed_protagonist"])
    work["control_protagonist"] = work[control_col].map(clean_short_text) if control_col else ""

    term_cols = []
    preferred_terms = [
        "available_terms_for_later_inspection",
        "steamspy_tags",
        "tags",
        "genres",
        "genre",
        "categories",
        "steam_categories",
        "steam_genres",
        "short_description",
        "detailed_description",
    ]
    for c in preferred_terms:
        found = find_col(work, [c])
        if found and found not in term_cols:
            term_cols.append(found)

    # If the explicit list misses the local naming, add columns whose names look useful.
    for c in work.columns:
        lc = c.lower()
        if any(k in lc for k in ["tag", "genre", "categor", "description"]):
            if c not in term_cols:
                term_cols.append(c)

    if term_cols:
        work["available_terms_for_later_inspection"] = work.apply(lambda r: combine_terms(r, term_cols), axis=1)
    else:
        work["available_terms_for_later_inspection"] = ""

    work = work.drop_duplicates(subset=["appid"], keep="first")
    work = work[work["name"].astype(str).str.len() > 0].copy()

    if min_reactions > 0:
        work = work[work["total_ratings_pos_neg"] >= min_reactions].copy()

    work = work.sort_values(["total_ratings_pos_neg", "appid"], ascending=[False, True]).copy()
    if limit and limit > 0:
        work = work.head(limit).copy()

    work.insert(0, "selection_rank", range(1, len(work) + 1))

    keep_cols = [
        "selection_rank",
        "appid",
        "name",
        "total_ratings_pos_neg",
        "positive_ratio",
        "steamspy_owners",
        "available_terms_for_later_inspection",
        "control_protagonist",
    ]
    return work[keep_cols].copy()


def row_to_game(row: pd.Series) -> dict:
    return {
        "a": int(row["appid"]),
        "n": clean_short_text(row.get("name"), 120),
        "r": safe_str(row.get("total_ratings_pos_neg")),
        "pr": clean_short_text(row.get("positive_ratio"), 24),
        "o": clean_short_text(row.get("steamspy_owners"), 80),
        "tg": clean_short_text(row.get("available_terms_for_later_inspection"), 420),
        "cp": clean_short_text(row.get("control_protagonist"), 120),
    }


def make_user_prompt(games: list[dict]) -> str:
    return "Classify these games. Return JSON only.\n" + json.dumps(games, ensure_ascii=False, separators=(",", ":"))


def iter_chunks(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield i, items[i:i + size]


def make_cost_estimate(num_games: int, chunk_size: int) -> dict:
    # Based on the previous 50-game GPT-5.5 v003 run:
    # input_tokens=7138, output_tokens=12122 for one chunk of 50.
    # v004 uses compact output, so this is intentionally a conservative v003-style estimate.
    chunks = math.ceil(num_games / chunk_size) if chunk_size else 0
    observed_input_per_50 = 7138
    observed_output_per_50 = 12122

    est_input = chunks * observed_input_per_50
    est_output = chunks * observed_output_per_50

    # Current GPT-5.5 standard rates are $5 input / $30 output per 1M.
    # Batch is 50% of standard: $2.50 input / $15 output per 1M.
    input_rate_batch = 2.50
    output_rate_batch = 15.00
    est_cost = (est_input / 1_000_000) * input_rate_batch + (est_output / 1_000_000) * output_rate_batch

    return {
        "note": "Conservative estimate based on previous v003 50-game GPT-5.5 chunk. v004 compact output may be cheaper.",
        "games": num_games,
        "chunk_size": chunk_size,
        "requests": chunks,
        "estimated_input_tokens": est_input,
        "estimated_output_tokens": est_output,
        "estimated_batch_usd": round(est_cost, 2),
        "batch_rates_assumed_usd_per_1m": {
            "input": input_rate_batch,
            "output": output_rate_batch
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input CSV. Default: steam_catalog_merged.csv")
    parser.add_argument("--output", default=str(OUT_JSONL))
    parser.add_argument("--manifest", default=str(OUT_MANIFEST))
    parser.add_argument("--selected-output", default=str(OUT_SELECTED))
    parser.add_argument("--estimate-output", default=str(OUT_ESTIMATE))
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--min-reactions", type=int, default=1)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        if input_path == DEFAULT_INPUT and FALLBACK_INPUT.exists():
            print(f"WARNING: {DEFAULT_INPUT} not found; falling back to {FALLBACK_INPUT}")
            input_path = FALLBACK_INPUT
        else:
            raise FileNotFoundError(input_path)

    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be > 0")

    print(f"Loading source catalog: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)

    selected = select_games(df, limit=args.limit, min_reactions=args.min_reactions)

    out_selected = Path(args.selected_output)
    out_selected.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(out_selected, index=False, encoding="utf-8-sig")

    games = [row_to_game(row) for _, row in selected.iterrows()]
    request_count = 0
    manifest_rows = []

    out_jsonl = Path(args.output)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    with out_jsonl.open("w", encoding="utf-8") as f:
        for start_idx, chunk_games in iter_chunks(games, args.chunk_size):
            request_count += 1
            custom_id = f"steam-v004-50k-55-chunk-{request_count:05d}-rows-{start_idx + 1}-{start_idx + len(chunk_games)}"

            body = {
                "model": args.model,
                "input": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": make_user_prompt(chunk_games)}
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "steam_archetype_50k_economy_v004",
                        "strict": True,
                        "schema": BATCH_SCHEMA
                    }
                }
            }

            request = {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/v1/responses",
                "body": body
            }
            f.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n")

            for g in chunk_games:
                manifest_rows.append({
                    "custom_id": custom_id,
                    "appid": g["a"],
                    "name": g["n"],
                    "chunk_request_number": request_count,
                    "chunk_size": len(chunk_games),
                })

    out_manifest = Path(args.manifest)
    pd.DataFrame(manifest_rows).to_csv(out_manifest, index=False, encoding="utf-8-sig")

    estimate = make_cost_estimate(len(games), args.chunk_size)
    estimate.update({
        "model": args.model,
        "input_csv": str(input_path),
        "jsonl_output": str(out_jsonl),
        "selected_games_csv": str(out_selected),
        "manifest_csv": str(out_manifest),
        "min_reactions": args.min_reactions,
    })
    out_estimate = Path(args.estimate_output)
    out_estimate.write_text(json.dumps(estimate, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Prepared v004 economy JSONL: {out_jsonl}")
    print(f"Selected games: {len(games)}")
    print(f"Requests: {request_count}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Model: {args.model}")
    print(f"Min reactions: {args.min_reactions}")
    print(f"Selected games audit CSV: {out_selected}")
    print(f"Manifest: {out_manifest}")
    print(f"Conservative cost estimate JSON: {out_estimate}")
    print(f"Conservative estimated Batch cost: ${estimate['estimated_batch_usd']} USD")
    print("This prepare step did not spend API money.")
    print("Next, if you really want to run it: python steam_submit_openai_batch_v004_50k_5_5_economy.py")


if __name__ == "__main__":
    main()
