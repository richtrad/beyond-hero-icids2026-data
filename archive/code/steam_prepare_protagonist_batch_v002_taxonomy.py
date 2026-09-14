#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_prepare_protagonist_batch_v002_taxonomy.py

Prepare OpenAI Batch API JSONL requests for protagonist identification and
CONTROLLED archetype pre-coding.

Changes vs v001:
- Fixed archetype taxonomy with enum values.
- Clear separation between protagonist identification and archetype coding.
- No free-form micro-archetypes such as "traumatized assassin" as the primary label.
- Output fields are designed for direct CSV analysis.

Input:
  steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv

Outputs:
  steam_bulk_outputs/steam_protagonist_batch_input_v002_taxonomy.jsonl
  steam_bulk_outputs/steam_protagonist_batch_manifest_v002_taxonomy.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


INPUT_CSV = Path("steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv")
OUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_input_v002_taxonomy.jsonl")
OUT_MANIFEST = Path("steam_bulk_outputs/steam_protagonist_batch_manifest_v002_taxonomy.csv")


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


SYSTEM_PROMPT = f"""You are helping build a research corpus for video game protagonist archetype analysis.

Your task has two stages:

STAGE 1 — protagonist identification
Decide whether the game has a clear main protagonist suitable for later archetypal analysis.

STAGE 2 — controlled archetype pre-coding
If there is a usable protagonist, assign ONLY the closest archetypes from the fixed taxonomy below.
Do not invent new archetype labels.

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
- primary_archetype, secondary_archetype, and tertiary_archetype MUST be one of the taxonomy labels exactly.
- Do NOT output labels like "traumatized assassin", "superhero protector", "existential android warrior", "wounded everyman" as archetype fields. Put such nuance into archetype_notes instead.
- If the game has no clear protagonist, set primary_archetype to "Not applicable".
- If the game has a customizable but narratively defined hero, use protagonist_type="customizable_but_defined".
- If the player controls a faction, city, empire, club, vehicle, team, or abstract system, usually use "no" and a systemic/simulator/sports type.
- If the game has two or more fixed protagonists, list them and use fixed_dual or fixed_ensemble.
- If a control seed protagonist is provided, use it as strong evidence, but still classify carefully.
- This is pre-coding, not final human coding. Use needs_manual_review=true for borderline or uncertain cases.
- Keep reasoning short and audit-friendly.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "appid": {"type": "integer"},
        "name": {"type": "string"},

        "has_clear_main_protagonist": {
            "type": "string",
            "enum": ["yes", "no", "uncertain"]
        },
        "protagonist_name": {"type": "string"},
        "protagonist_type": {
            "type": "string",
            "enum": PROTAGONIST_TYPES
        },
        "protagonist_confidence_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },

        "primary_archetype": {
            "type": "string",
            "enum": ARCHETYPES
        },
        "secondary_archetype": {
            "type": "string",
            "enum": ARCHETYPES
        },
        "tertiary_archetype": {
            "type": "string",
            "enum": ARCHETYPES
        },

        "archetype_confidence_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },
        "archetype_suitability_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },

        "shadow_load_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },
        "player_projection_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },
        "narrative_complexity_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },

        "suggested_include_in_final_corpus": {
            "type": "string",
            "enum": ["yes", "no", "maybe"]
        },
        "exclusion_reason": {
            "type": "string",
            "enum": EXCLUSION_REASONS
        },
        "needs_manual_review": {"type": "boolean"},

        "evidence_basis": {
            "type": "string",
            "enum": ["general_knowledge", "control_seed", "metadata_inference", "uncertain"]
        },
        "protagonist_notes": {"type": "string"},
        "archetype_notes": {"type": "string"},
        "reason_short": {"type": "string"}
    },
    "required": [
        "appid",
        "name",
        "has_clear_main_protagonist",
        "protagonist_name",
        "protagonist_type",
        "protagonist_confidence_0_3",
        "primary_archetype",
        "secondary_archetype",
        "tertiary_archetype",
        "archetype_confidence_0_3",
        "archetype_suitability_0_3",
        "shadow_load_0_3",
        "player_projection_0_3",
        "narrative_complexity_0_3",
        "suggested_include_in_final_corpus",
        "exclusion_reason",
        "needs_manual_review",
        "evidence_basis",
        "protagonist_notes",
        "archetype_notes",
        "reason_short"
    ]
}


def safe_str(x) -> str:
    if pd.isna(x):
        return ""
    return str(x)


def make_user_prompt(row: pd.Series) -> str:
    return f"""Game metadata:

appid: {int(row['appid'])}
title: {safe_str(row.get('name'))}
Steam reactions positive+negative: {safe_str(row.get('total_ratings_pos_neg'))}
positive ratio: {safe_str(row.get('positive_ratio'))}
owners estimate: {safe_str(row.get('steamspy_owners'))}
available tags/genres: {safe_str(row.get('available_terms_for_later_inspection'))}

Control seed protagonist, if any: {safe_str(row.get('control_protagonist'))}

Return only valid structured JSON according to the schema.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT_CSV))
    parser.add_argument("--output", default=str(OUT_JSONL))
    parser.add_argument("--manifest", default=str(OUT_MANIFEST))
    parser.add_argument("--model", default="gpt-5.5", help="Model name to put into each batch request.")
    parser.add_argument("--limit", type=int, default=0, help="For testing. 0 = all rows.")
    parser.add_argument("--start", type=int, default=0, help="Start row offset for partial batches.")
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

    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    with output_path.open("w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            appid = int(row["appid"])
            custom_id = f"steam-v002-appid-{appid}"

            body = {
                "model": args.model,
                "input": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": make_user_prompt(row)}
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "steam_protagonist_archetype_taxonomy_v002",
                        "strict": True,
                        "schema": SCHEMA
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

            manifest_rows.append({
                "custom_id": custom_id,
                "appid": appid,
                "name": safe_str(row.get("name")),
                "broad_rank": safe_str(row.get("broad_rank")),
                "total_ratings_pos_neg": safe_str(row.get("total_ratings_pos_neg")),
            })

    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False, encoding="utf-8-sig")

    print(f"Prepared v002 taxonomy batch JSONL: {output_path} ({len(manifest_rows)} requests)")
    print(f"Prepared manifest: {manifest_path}")
    print("Next: python steam_submit_openai_batch_v002_taxonomy.py")


if __name__ == "__main__":
    main()
