#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_prepare_protagonist_batch_v003_chunked_taxonomy.py

Cost-optimized batch preparation:
- Packs multiple games into one model request.
- Default chunk size: 50 games/request.
- Uses controlled archetype taxonomy.

Input:
  steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv

Outputs:
  steam_bulk_outputs/steam_protagonist_batch_input_v003_chunked_taxonomy.jsonl
  steam_bulk_outputs/steam_protagonist_batch_manifest_v003_chunked_taxonomy.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


INPUT_CSV = Path("steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv")
OUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_input_v003_chunked_taxonomy.jsonl")
OUT_MANIFEST = Path("steam_bulk_outputs/steam_protagonist_batch_manifest_v003_chunked_taxonomy.csv")


ARCHETYPES = [
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
    "Shadow/Antihero",
    "Not applicable",
    "Uncertain",
]

PROTAGONIST_TYPES = [
    "fixed_named_single",
    "fixed_role_single",
    "silent_fixed_protagonist",
    "nonhuman_fixed_protagonist",
    "customizable_but_defined",
    "fixed_dual",
    "fixed_ensemble",
    "player_avatar_weakly_defined",
    "strategy_or_systemic_role",
    "simulator_or_management_role",
    "sports_or_racing_role",
    "no_clear_protagonist",
    "uncertain",
]

EXCLUSION_REASONS = [
    "none",
    "no_clear_protagonist",
    "pure_strategy_or_systemic_role",
    "simulator_or_management",
    "sports_or_racing",
    "multiplayer_only_or_no_story_focus",
    "unknown_game",
    "insufficient_information",
    "other",
]

SYSTEM_PROMPT = """You are helping build a research corpus for video game protagonist archetype analysis.

You will receive a JSON array of multiple Steam games.

For EACH game, return exactly one result object with the same appid and name.
Do not skip games. Do not add games.

Task has two stages:
1. Identify whether the game has a clear main protagonist suitable for later archetypal analysis.
2. If there is a usable protagonist, assign archetypes ONLY from the fixed taxonomy.

Fixed archetype taxonomy:
1. Innocent — naive, pure, hopeful, childlike, uncorrupted, learning through wonder.
2. Everyman/Orphan — ordinary person, outsider, abandoned figure, survivor seeking belonging.
3. Hero/Warrior — courageous fighter, savior, protector through action, endurance, trials.
4. Caregiver/Guardian — nurturer, protector, parent, healer, ferryman, self-sacrificing support.
5. Explorer/Seeker — traveler, investigator of identity/world, search for truth, freedom, origin.
6. Rebel/Outlaw — rule-breaker, revolutionary, criminal, anti-system figure, punk defiance.
7. Lover — driven by love, intimacy, devotion, romance, loyalty, longing.
8. Creator/Artist — maker, writer, artist, inventor, world-shaper, imagination-centered protagonist.
9. Jester/Trickster — comic, chaotic, playful, deceptive, mask-wearing, subversive wit.
10. Sage/Investigator — detective, scholar, analyst, truth-seeker through knowledge or reason.
11. Magician/Transformer — occult, supernatural, reality-changing, transformative power or ritual.
12. Ruler/Leader — monarch, commander, leader, burden of authority, governance.
13. Shadow/Antihero — morally compromised, traumatized, violent, self-destructive, dark mirror.
14. Not applicable — use only if there is no usable protagonist.
15. Uncertain — use when there is not enough reliable information.

Rules:
- primary_archetype, secondary_archetype, and tertiary_archetype MUST be taxonomy labels exactly.
- Do not invent new archetype labels. Put nuance into archetype_notes.
- If there is no clear protagonist, set primary_archetype to "Not applicable".
- If the game has a customizable but narratively defined hero, use protagonist_type="customizable_but_defined".
- If the player controls a faction, city, empire, club, vehicle, team, or abstract system, usually use "no" and a systemic/simulator/sports type.
- If the game has two or more fixed protagonists, list them and use fixed_dual or fixed_ensemble.
- If a control seed protagonist is provided, use it as strong evidence, but still classify carefully.
- This is pre-coding, not final human coding. Use needs_manual_review=true for borderline or uncertain cases.
- Keep notes short and audit-friendly.
"""

ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "appid": {"type": "integer"},
        "name": {"type": "string"},
        "has_clear_main_protagonist": {"type": "string", "enum": ["yes", "no", "uncertain"]},
        "protagonist_name": {"type": "string"},
        "protagonist_type": {"type": "string", "enum": PROTAGONIST_TYPES},
        "protagonist_confidence_0_3": {"type": "integer", "minimum": 0, "maximum": 3},
        "primary_archetype": {"type": "string", "enum": ARCHETYPES},
        "secondary_archetype": {"type": "string", "enum": ARCHETYPES},
        "tertiary_archetype": {"type": "string", "enum": ARCHETYPES},
        "archetype_confidence_0_3": {"type": "integer", "minimum": 0, "maximum": 3},
        "archetype_suitability_0_3": {"type": "integer", "minimum": 0, "maximum": 3},
        "shadow_load_0_3": {"type": "integer", "minimum": 0, "maximum": 3},
        "player_projection_0_3": {"type": "integer", "minimum": 0, "maximum": 3},
        "narrative_complexity_0_3": {"type": "integer", "minimum": 0, "maximum": 3},
        "suggested_include_in_final_corpus": {"type": "string", "enum": ["yes", "no", "maybe"]},
        "exclusion_reason": {"type": "string", "enum": EXCLUSION_REASONS},
        "needs_manual_review": {"type": "boolean"},
        "evidence_basis": {"type": "string", "enum": ["general_knowledge", "control_seed", "metadata_inference", "uncertain"]},
        "protagonist_notes": {"type": "string"},
        "archetype_notes": {"type": "string"},
        "reason_short": {"type": "string"}
    },
    "required": [
        "appid", "name", "has_clear_main_protagonist", "protagonist_name",
        "protagonist_type", "protagonist_confidence_0_3",
        "primary_archetype", "secondary_archetype", "tertiary_archetype",
        "archetype_confidence_0_3", "archetype_suitability_0_3",
        "shadow_load_0_3", "player_projection_0_3", "narrative_complexity_0_3",
        "suggested_include_in_final_corpus", "exclusion_reason", "needs_manual_review",
        "evidence_basis", "protagonist_notes", "archetype_notes", "reason_short"
    ]
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


def row_to_game(row: pd.Series) -> dict:
    return {
        "appid": int(row["appid"]),
        "name": safe_str(row.get("name")),
        "total_ratings_pos_neg": safe_str(row.get("total_ratings_pos_neg")),
        "positive_ratio": safe_str(row.get("positive_ratio")),
        "owners_estimate": safe_str(row.get("steamspy_owners")),
        "available_tags_genres": safe_str(row.get("available_terms_for_later_inspection")),
        "control_seed_protagonist": safe_str(row.get("control_protagonist")),
    }


def make_user_prompt(games: list[dict]) -> str:
    return (
        "Classify the following games. Return exactly one item per input game, "
        "with the same appid and name.\n\n"
        "Games JSON:\n"
        + json.dumps(games, ensure_ascii=False, indent=2)
    )


def chunks(rows, size: int):
    for i in range(0, len(rows), size):
        yield i, rows[i:i + size]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT_CSV))
    parser.add_argument("--output", default=str(OUT_JSONL))
    parser.add_argument("--manifest", default=str(OUT_MANIFEST))
    parser.add_argument("--model", default="gpt-5.4-mini", help="Use cheaper model first; override if needed.")
    parser.add_argument("--limit", type=int, default=0, help="For testing. 0 = all rows.")
    parser.add_argument("--start", type=int, default=0, help="Start row offset for partial batches.")
    parser.add_argument("--chunk-size", type=int, default=50, help="Games per model request. Default: 50.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    manifest_path = Path(args.manifest)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    df = pd.read_csv(input_path, low_memory=False)
    if "appid" not in df.columns or "name" not in df.columns:
        raise RuntimeError("Input CSV must contain appid and name columns.")

    df = df.copy()
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce")
    df = df[df["appid"].notna()].copy()
    df["appid"] = df["appid"].astype(int)

    if args.start:
        df = df.iloc[args.start:].copy()
    if args.limit and args.limit > 0:
        df = df.head(args.limit).copy()

    games = [row_to_game(row) for _, row in df.iterrows()]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    request_count = 0

    with output_path.open("w", encoding="utf-8") as f:
        for start_idx, chunk_games in chunks(games, args.chunk_size):
            request_count += 1
            first_appid = chunk_games[0]["appid"]
            last_appid = chunk_games[-1]["appid"]
            custom_id = f"steam-v003-chunk-{request_count:05d}-rows-{start_idx + 1}-{start_idx + len(chunk_games)}"

            body = {
                "model": args.model,
                "input": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": make_user_prompt(chunk_games)}
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "steam_protagonist_archetype_chunk_v003",
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
            f.write(json.dumps(request, ensure_ascii=False) + "\n")

            for g in chunk_games:
                manifest_rows.append({
                    "custom_id": custom_id,
                    "appid": g["appid"],
                    "name": g["name"],
                    "chunk_request_number": request_count,
                    "chunk_size": len(chunk_games),
                    "chunk_first_appid": first_appid,
                    "chunk_last_appid": last_appid,
                })

    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False, encoding="utf-8-sig")

    print(f"Prepared v003 chunked taxonomy JSONL: {output_path}")
    print(f"Games: {len(games)}")
    print(f"Requests: {request_count}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Model: {args.model}")
    print(f"Prepared manifest: {manifest_path}")
    print("Next: python steam_submit_openai_batch_v003_chunked_taxonomy.py")


if __name__ == "__main__":
    main()
