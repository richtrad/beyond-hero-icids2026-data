#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_prepare_rest_parts_v006_54mini.py

Split the v005 REST part into multiple smaller gpt-5.4-mini Batch JSONL files.

Why:
The full REST batch may exceed the organization's enqueued token limit.
This script creates smaller independent parts, intended to be submitted one at a time.

Input:
  steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv

Default:
  REST only, 5000 games per batch part, 50 games per request/chunk.

Outputs:
  steam_bulk_outputs/steam_v006_rest_parts/
    steam_v006_rest_54mini_part_001_input.jsonl
    steam_v006_rest_54mini_part_001_manifest.csv
    ...
    steam_v006_rest_parts_index.csv
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


SELECTED_CSV = Path("steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv")
OUT_DIR = Path("steam_bulk_outputs/steam_v006_rest_parts")
INDEX_CSV = OUT_DIR / "steam_v006_rest_parts_index.csv"


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


def iter_chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield i, items[i:i + size]


def write_part(part_df: pd.DataFrame, part_no: int, model: str, chunk_size: int) -> dict:
    part_tag = f"part_{part_no:03d}"
    jsonl_path = OUT_DIR / f"steam_v006_rest_54mini_{part_tag}_input.jsonl"
    manifest_path = OUT_DIR / f"steam_v006_rest_54mini_{part_tag}_manifest.csv"

    games = [row_to_game(row) for _, row in part_df.iterrows()]
    request_count = 0
    manifest_rows = []

    with jsonl_path.open("w", encoding="utf-8") as f:
        for start_idx, chunk_games in iter_chunks(games, chunk_size):
            request_count += 1
            first_rank = int(part_df.iloc[start_idx]["selection_rank"])
            last_rank = int(part_df.iloc[start_idx + len(chunk_games) - 1]["selection_rank"])
            custom_id = f"steam-v006-rest54mini-{part_tag}-chunk-{request_count:04d}-ranks-{first_rank}-{last_rank}"

            body = {
                "model": model,
                "input": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": make_user_prompt(chunk_games)}
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "steam_archetype_v006_rest54mini",
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
                    "part_no": part_no,
                    "custom_id": custom_id,
                    "appid": g["a"],
                    "name": g["n"],
                    "model": model,
                    "chunk_request_number": request_count,
                    "chunk_size": len(chunk_games),
                })

    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False, encoding="utf-8-sig")

    return {
        "part_no": part_no,
        "model": model,
        "games": len(part_df),
        "requests": request_count,
        "first_selection_rank": int(part_df["selection_rank"].min()),
        "last_selection_rank": int(part_df["selection_rank"].max()),
        "input_jsonl": str(jsonl_path),
        "manifest_csv": str(manifest_path),
        "batch_id_txt": str(OUT_DIR / f"steam_v006_rest_54mini_{part_tag}_batch_id.txt"),
        "status": "prepared"
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", default=str(SELECTED_CSV))
    parser.add_argument("--games-per-part", type=int, default=5000)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--model", default="gpt-5.4-mini")
    args = parser.parse_args()

    selected_path = Path(args.selected)
    if not selected_path.exists():
        raise FileNotFoundError(selected_path)

    if args.games_per_part <= 0:
        raise ValueError("--games-per-part must be > 0")
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be > 0")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(selected_path, low_memory=False)
    if "selection_rank" not in df.columns:
        raise RuntimeError("Selected CSV must contain selection_rank.")
    if "v005_split" in df.columns:
        rest = df[df["v005_split"].astype(str).str.contains("rest", case=False, na=False)].copy()
    else:
        rest = df[pd.to_numeric(df["selection_rank"], errors="coerce") > 1000].copy()

    rest["selection_rank"] = pd.to_numeric(rest["selection_rank"], errors="coerce")
    rest = rest[rest["selection_rank"].notna()].copy()
    rest["selection_rank"] = rest["selection_rank"].astype(int)
    rest = rest.sort_values("selection_rank").copy()

    index_rows = []
    part_no = 0
    for start in range(0, len(rest), args.games_per_part):
        part_no += 1
        part_df = rest.iloc[start:start + args.games_per_part].copy()
        index_rows.append(write_part(part_df, part_no, args.model, args.chunk_size))

    index = pd.DataFrame(index_rows)
    index.to_csv(INDEX_CSV, index=False, encoding="utf-8-sig")

    print(f"Prepared REST parts in: {OUT_DIR}")
    print(f"REST games: {len(rest)}")
    print(f"Games per part: {args.games_per_part}")
    print(f"Parts: {len(index)}")
    print(f"Requests total: {int(index['requests'].sum()) if not index.empty else 0}")
    print(f"Index CSV: {INDEX_CSV}")
    print("Submit one part at a time, e.g.:")
    print("  python steam_submit_rest_part_v006_54mini.py --part 1 --yes-i-know-this-costs-money")


if __name__ == "__main__":
    main()
