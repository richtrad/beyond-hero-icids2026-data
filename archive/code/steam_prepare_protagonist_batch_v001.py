#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_prepare_protagonist_batch_v001.py

Prepare OpenAI Batch API JSONL requests for protagonist identification.

Input:
  steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv

Outputs:
  steam_bulk_outputs/steam_protagonist_batch_input_v001.jsonl
  steam_bulk_outputs/steam_protagonist_batch_manifest_v001.csv

No API calls are made by this script.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


INPUT_CSV = Path("steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv")
OUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_input_v001.jsonl")
OUT_MANIFEST = Path("steam_bulk_outputs/steam_protagonist_batch_manifest_v001.csv")


SYSTEM_PROMPT = """You are helping build a research corpus for video game protagonist archetype analysis.

Task:
Given Steam metadata for one game, identify whether the game has a clear main protagonist suitable for later archetypal coding.

Important rules:
- Use your general knowledge of well-known games, plus the provided metadata.
- Do not invent a named protagonist when the game is clearly a player avatar, strategy role, simulator, management game, sports/racing game, or no-protagonist game.
- If the game has a customizable but strongly defined role, mark it as customizable_but_defined.
- If it has several fixed protagonists, mark fixed_ensemble or fixed_dual.
- If uncertain, say uncertain and set needs_manual_review true.
- This stage is NOT final archetype coding. It is only protagonist identification and suitability triage.
- Keep notes short and practical.
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
            "enum": [
                "fixed_named_single",
                "fixed_role_single",
                "customizable_but_defined",
                "fixed_dual",
                "fixed_ensemble",
                "silent_fixed_protagonist",
                "nonhuman_fixed_protagonist",
                "player_avatar",
                "strategy_or_systemic_role",
                "simulator_or_management_role",
                "sports_or_racing_role",
                "no_clear_protagonist",
                "uncertain"
            ]
        },
        "protagonist_confidence_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },
        "archetype_suitability_0_3": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
        },
        "primary_archetype_candidate": {"type": "string"},
        "secondary_archetype_candidate": {"type": "string"},
        "reason_short": {"type": "string"},
        "needs_manual_review": {"type": "boolean"},
        "suggested_include_in_final_corpus": {
            "type": "string",
            "enum": ["yes", "no", "maybe"]
        }
    },
    "required": [
        "appid",
        "name",
        "has_clear_main_protagonist",
        "protagonist_name",
        "protagonist_type",
        "protagonist_confidence_0_3",
        "archetype_suitability_0_3",
        "primary_archetype_candidate",
        "secondary_archetype_candidate",
        "reason_short",
        "needs_manual_review",
        "suggested_include_in_final_corpus"
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

Return only the structured JSON requested by the schema.
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
            custom_id = f"steam-appid-{appid}"

            body = {
                "model": args.model,
                "input": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": make_user_prompt(row)}
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "steam_protagonist_identification",
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

    print(f"Prepared batch JSONL: {output_path} ({len(manifest_rows)} requests)")
    print(f"Prepared manifest: {manifest_path}")
    print("Next: python steam_submit_openai_batch_v001.py")


if __name__ == "__main__":
    main()
