#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_prepare_protagonist_batch_v005_split_1000_55_rest_54mini.py

Prepare split-model OpenAI Batch JSONL files:

- TOP 1000 games by reaction/review count -> gpt-5.5
- Remaining games up to target total -> gpt-5.4-mini
- Default target total: 50,000 games
- Default chunk size: 50 games/request
- Compact code output to reduce output-token cost

This script only prepares files. It does NOT spend API money.
Money is spent only by the submit script.

Default input:
  steam_bulk_outputs/steam_catalog_merged.csv

Outputs:
  steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv
  steam_bulk_outputs/steam_v005_top1000_55_input.jsonl
  steam_bulk_outputs/steam_v005_rest_54mini_input.jsonl
  steam_bulk_outputs/steam_v005_top1000_55_manifest.csv
  steam_bulk_outputs/steam_v005_rest_54mini_manifest.csv
  steam_bulk_outputs/steam_v005_cost_estimate_split_1000_55_rest_54mini.json
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
OUT_SELECTED = Path("steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv")
OUT_TOP_JSONL = Path("steam_bulk_outputs/steam_v005_top1000_55_input.jsonl")
OUT_REST_JSONL = Path("steam_bulk_outputs/steam_v005_rest_54mini_input.jsonl")
OUT_TOP_MANIFEST = Path("steam_bulk_outputs/steam_v005_top1000_55_manifest.csv")
OUT_REST_MANIFEST = Path("steam_bulk_outputs/steam_v005_rest_54mini_manifest.csv")
OUT_ESTIMATE = Path("steam_bulk_outputs/steam_v005_cost_estimate_split_1000_55_rest_54mini.json")


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
        raise RuntimeError(f"Could not find appid/name columns. First columns: {list(df.columns)[:50]}")

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


def write_jsonl_and_manifest(df_part: pd.DataFrame, output_jsonl: Path, output_manifest: Path, model: str, label: str, chunk_size: int) -> int:
    games = [row_to_game(row) for _, row in df_part.iterrows()]
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    request_count = 0
    manifest_rows = []

    with output_jsonl.open("w", encoding="utf-8") as f:
        for start_idx, chunk_games in iter_chunks(games, chunk_size):
            request_count += 1
            global_first_rank = int(df_part.iloc[start_idx]["selection_rank"])
            global_last_rank = int(df_part.iloc[start_idx + len(chunk_games) - 1]["selection_rank"])
            custom_id = f"steam-v005-{label}-chunk-{request_count:05d}-ranks-{global_first_rank}-{global_last_rank}"

            body = {
                "model": model,
                "input": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": make_user_prompt(chunk_games)}
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": f"steam_archetype_v005_{label}",
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
                    "model": model,
                    "split_label": label,
                    "chunk_request_number": request_count,
                    "chunk_size": len(chunk_games),
                })

    pd.DataFrame(manifest_rows).to_csv(output_manifest, index=False, encoding="utf-8-sig")
    return request_count


def make_cost_estimate(top_games: int, rest_games: int, chunk_size: int) -> dict:
    # Conservative estimate based on observed 50-game v003 runs:
    # GPT-5.5: input 7138, output 12122 per 50.
    # GPT-5.4-mini: input 7138, output 10809 per 50.
    top_chunks = math.ceil(top_games / chunk_size) if top_games else 0
    rest_chunks = math.ceil(rest_games / chunk_size) if rest_games else 0

    top_input = top_chunks * 7138
    top_output = top_chunks * 12122
    rest_input = rest_chunks * 7138
    rest_output = rest_chunks * 10809

    # Batch-estimate rates used previously:
    # gpt-5.5: input $2.50 / 1M, output $15 / 1M
    # gpt-5.4-mini: input $0.375 / 1M, output $2.25 / 1M
    top_cost = (top_input / 1_000_000) * 2.50 + (top_output / 1_000_000) * 15.00
    rest_cost = (rest_input / 1_000_000) * 0.375 + (rest_output / 1_000_000) * 2.25

    return {
        "note": "Conservative estimate from previous 50-game chunks. v005 compact output may be cheaper; actual billing is authoritative.",
        "top_model": "gpt-5.5",
        "rest_model": "gpt-5.4-mini",
        "chunk_size": chunk_size,
        "top_games": top_games,
        "rest_games": rest_games,
        "top_requests": top_chunks,
        "rest_requests": rest_chunks,
        "estimated_top_input_tokens": top_input,
        "estimated_top_output_tokens": top_output,
        "estimated_rest_input_tokens": rest_input,
        "estimated_rest_output_tokens": rest_output,
        "estimated_top_batch_usd": round(top_cost, 2),
        "estimated_rest_batch_usd": round(rest_cost, 2),
        "estimated_total_batch_usd": round(top_cost + rest_cost, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--target-total", type=int, default=50000)
    parser.add_argument("--top-n-55", type=int, default=1000)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--min-reactions", type=int, default=1)
    parser.add_argument("--top-model", default="gpt-5.5")
    parser.add_argument("--rest-model", default="gpt-5.4-mini")
    args = parser.parse_args()

    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be > 0")
    if args.top_n_55 < 0:
        raise ValueError("--top-n-55 must be >= 0")
    if args.target_total <= 0:
        raise ValueError("--target-total must be > 0")
    if args.top_n_55 > args.target_total:
        raise ValueError("--top-n-55 cannot be greater than --target-total")

    input_path = Path(args.input)
    if not input_path.exists():
        if input_path == DEFAULT_INPUT and FALLBACK_INPUT.exists():
            print(f"WARNING: {DEFAULT_INPUT} not found; falling back to {FALLBACK_INPUT}")
            input_path = FALLBACK_INPUT
        else:
            raise FileNotFoundError(input_path)

    print(f"Loading source catalog: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)

    selected = select_games(df, limit=args.target_total, min_reactions=args.min_reactions)
    selected["v005_split"] = selected["selection_rank"].apply(lambda r: "top1000_55" if int(r) <= args.top_n_55 else "rest_54mini")
    selected["v005_model"] = selected["v005_split"].map({"top1000_55": args.top_model, "rest_54mini": args.rest_model})

    OUT_SELECTED.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(OUT_SELECTED, index=False, encoding="utf-8-sig")

    top_df = selected[selected["selection_rank"] <= args.top_n_55].copy()
    rest_df = selected[selected["selection_rank"] > args.top_n_55].copy()

    top_requests = write_jsonl_and_manifest(
        top_df, OUT_TOP_JSONL, OUT_TOP_MANIFEST, args.top_model, "top1000-55", args.chunk_size
    )
    rest_requests = write_jsonl_and_manifest(
        rest_df, OUT_REST_JSONL, OUT_REST_MANIFEST, args.rest_model, "rest-54mini", args.chunk_size
    )

    estimate = make_cost_estimate(len(top_df), len(rest_df), args.chunk_size)
    estimate.update({
        "input_csv": str(input_path),
        "selected_games_csv": str(OUT_SELECTED),
        "top_jsonl": str(OUT_TOP_JSONL),
        "rest_jsonl": str(OUT_REST_JSONL),
        "top_manifest": str(OUT_TOP_MANIFEST),
        "rest_manifest": str(OUT_REST_MANIFEST),
        "target_total": args.target_total,
        "min_reactions": args.min_reactions,
    })
    OUT_ESTIMATE.write_text(json.dumps(estimate, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Prepared selected games CSV: {OUT_SELECTED}")
    print(f"Selected games: {len(selected)}")
    print(f"TOP split: {len(top_df)} games, {top_requests} requests, model {args.top_model}")
    print(f"REST split: {len(rest_df)} games, {rest_requests} requests, model {args.rest_model}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"TOP JSONL: {OUT_TOP_JSONL}")
    print(f"REST JSONL: {OUT_REST_JSONL}")
    print(f"Cost estimate JSON: {OUT_ESTIMATE}")
    print(f"Conservative estimated total Batch cost: ${estimate['estimated_total_batch_usd']} USD")
    print("This prepare step did not spend API money.")
    print("Next, if you want to submit both: python steam_submit_openai_batch_v005_split_1000_55_rest_54mini.py --top --rest --yes-i-know-this-costs-money")


if __name__ == "__main__":
    main()
