#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_retrieve_openai_batch_v004_50k_5_5_economy.py

Retrieve the v004 50k GPT-5.5 economy batch, expand compact codes, and merge
results back into the selected source CSV and, when possible, the original source CSV.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from openai import OpenAI


BATCH_ID_FILE = Path("steam_bulk_outputs/steam_protagonist_batch_id_v004_50k_5_5_economy.txt")
SELECTED_CSV = Path("steam_bulk_outputs/steam_protagonist_batch_selected_games_v004_50k_5_5_economy.csv")
MANIFEST_CSV = Path("steam_bulk_outputs/steam_protagonist_batch_manifest_v004_50k_5_5_economy.csv")

OUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_output_v004_50k_5_5_economy.jsonl")
OUT_ERRORS = Path("steam_bulk_outputs/steam_protagonist_batch_errors_v004_50k_5_5_economy.jsonl")
OUT_ITEMS_COMPACT = Path("steam_bulk_outputs/steam_protagonist_batch_items_compact_v004_50k_5_5_economy.csv")
OUT_ITEMS_EXPANDED = Path("steam_bulk_outputs/steam_protagonist_batch_items_expanded_v004_50k_5_5_economy.csv")
OUT_MISSING = Path("steam_bulk_outputs/steam_protagonist_batch_missing_items_v004_50k_5_5_economy.csv")
OUT_MERGED_SELECTED = Path("steam_bulk_outputs/steam_archetype_50k_with_taxonomy_v004_5_5_economy.csv")
OUT_STATUS = Path("steam_bulk_outputs/steam_protagonist_batch_status_v004_50k_5_5_economy.json")


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

CLEAR_MAP = {"y": "yes", "n": "no", "u": "uncertain"}
INCLUDE_MAP = {"y": "yes", "n": "no", "m": "maybe"}
EVIDENCE_MAP = {"g": "general_knowledge", "c": "control_seed", "m": "metadata_inference", "u": "uncertain"}


def response_text_from_body(body: Dict[str, Any]) -> Optional[str]:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]

    output = body.get("output")
    if isinstance(output, list):
        parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if isinstance(c.get("text"), str):
                        parts.append(c["text"])
                    elif isinstance(c.get("content"), str):
                        parts.append(c["content"])
        if parts:
            return "\n".join(parts)

    return None


def parse_output_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    failures = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
                custom_id = item.get("custom_id", "")
                response = item.get("response", {})
                status_code = response.get("status_code")
                body = response.get("body", {})

                if status_code != 200:
                    failures.append({
                        "custom_id": custom_id,
                        "line_no": line_no,
                        "error": f"HTTP status {status_code}",
                        "raw": line[:1000],
                    })
                    continue

                text = response_text_from_body(body)
                if not text:
                    failures.append({
                        "custom_id": custom_id,
                        "line_no": line_no,
                        "error": "No output text found",
                        "raw": line[:1000],
                    })
                    continue

                try:
                    parsed = json.loads(text)
                except Exception:
                    failures.append({
                        "custom_id": custom_id,
                        "line_no": line_no,
                        "error": "Output text was not JSON",
                        "raw": text[:1000],
                    })
                    continue

                items = parsed.get("items")
                if not isinstance(items, list):
                    failures.append({
                        "custom_id": custom_id,
                        "line_no": line_no,
                        "error": "Parsed JSON has no items list",
                        "raw": text[:1000],
                    })
                    continue

                for result in items:
                    if isinstance(result, dict):
                        result["custom_id"] = custom_id
                        rows.append(result)
                    else:
                        failures.append({
                            "custom_id": custom_id,
                            "line_no": line_no,
                            "error": "Non-dict item in items",
                            "raw": str(result)[:1000],
                        })

            except Exception as e:
                failures.append({
                    "custom_id": "",
                    "line_no": line_no,
                    "error": str(e),
                    "raw": line[:1000],
                })

    if failures:
        fail_path = path.with_name(path.stem + "_parse_failures.csv")
        pd.DataFrame(failures).to_csv(fail_path, index=False, encoding="utf-8-sig")
        print(f"Parse failures saved: {fail_path} ({len(failures)})")

    return pd.DataFrame(rows)


def expand_results(compact: pd.DataFrame) -> pd.DataFrame:
    c = compact.copy()

    def getcol(name, default=""):
        return c[name] if name in c.columns else pd.Series([default] * len(c), index=c.index)

    out = pd.DataFrame()
    out["appid"] = pd.to_numeric(getcol("a"), errors="coerce")
    out["llm4_has_clear_main_protagonist"] = getcol("h").map(CLEAR_MAP).fillna("uncertain")
    out["llm4_protagonist_name"] = getcol("pn").astype(str)
    out["llm4_protagonist_type"] = getcol("pt").map(PROTAGONIST_TYPE_CODES).fillna("uncertain")
    out["llm4_protagonist_confidence_0_3"] = pd.to_numeric(getcol("pc", 0), errors="coerce")
    out["llm4_primary_archetype"] = getcol("p").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm4_secondary_archetype"] = getcol("s").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm4_tertiary_archetype"] = getcol("t").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm4_archetype_confidence_0_3"] = pd.to_numeric(getcol("ac", 0), errors="coerce")
    out["llm4_archetype_suitability_0_3"] = pd.to_numeric(getcol("su", 0), errors="coerce")
    out["llm4_shadow_load_0_3"] = pd.to_numeric(getcol("sh", 0), errors="coerce")
    out["llm4_player_projection_0_3"] = pd.to_numeric(getcol("pp", 0), errors="coerce")
    out["llm4_narrative_complexity_0_3"] = pd.to_numeric(getcol("nc", 0), errors="coerce")
    out["llm4_suggested_include_in_final_corpus"] = getcol("inc").map(INCLUDE_MAP).fillna("maybe")
    out["llm4_exclusion_reason"] = getcol("ex").map(EXCLUSION_CODES).fillna("other")
    out["llm4_needs_manual_review"] = getcol("mr", False).astype(bool)
    out["llm4_evidence_basis"] = getcol("eb").map(EVIDENCE_MAP).fillna("uncertain")
    out["llm4_note"] = getcol("note").astype(str)
    out["llm4_custom_id"] = getcol("custom_id").astype(str)

    out = out[out["appid"].notna()].copy()
    out["appid"] = out["appid"].astype(int)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    batch_id = args.batch_id.strip()
    if not batch_id:
        if not BATCH_ID_FILE.exists():
            raise FileNotFoundError(BATCH_ID_FILE)
        batch_id = BATCH_ID_FILE.read_text(encoding="utf-8").strip()

    client = OpenAI()

    batch = client.batches.retrieve(batch_id)
    status_obj = batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)
    OUT_STATUS.parent.mkdir(parents=True, exist_ok=True)
    OUT_STATUS.write_text(json.dumps(status_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Batch id: {batch.id}")
    print(f"Status: {batch.status}")
    print(f"Request counts: {getattr(batch, 'request_counts', None)}")

    if batch.status != "completed":
        print("Batch is not completed yet. Run this script again later.")
        return

    if batch.output_file_id:
        print(f"Downloading output file: {batch.output_file_id}")
        content = client.files.content(batch.output_file_id)
        OUT_JSONL.write_bytes(content.read())
        print(f"Saved output: {OUT_JSONL}")

    if batch.error_file_id:
        print(f"Downloading error file: {batch.error_file_id}")
        content = client.files.content(batch.error_file_id)
        OUT_ERRORS.write_bytes(content.read())
        print(f"Saved errors: {OUT_ERRORS}")

    if not OUT_JSONL.exists():
        print("No output JSONL found; cannot merge.")
        return

    compact = parse_output_jsonl(OUT_JSONL)
    print(f"Parsed compact per-game v004 results: {len(compact)} rows")

    if compact.empty:
        print("No parsed results; stopping.")
        return

    compact.to_csv(OUT_ITEMS_COMPACT, index=False, encoding="utf-8-sig")
    expanded = expand_results(compact)

    dupes = expanded[expanded.duplicated(subset=["appid"], keep=False)]
    if not dupes.empty:
        dupes_path = OUT_ITEMS_EXPANDED.with_name(OUT_ITEMS_EXPANDED.stem + "_duplicates.csv")
        dupes.to_csv(dupes_path, index=False, encoding="utf-8-sig")
        print(f"Duplicate appid results saved: {dupes_path} ({len(dupes)})")
    expanded = expanded.drop_duplicates(subset=["appid"], keep="last")

    expanded.to_csv(OUT_ITEMS_EXPANDED, index=False, encoding="utf-8-sig")
    print(f"Saved expanded per-game results: {OUT_ITEMS_EXPANDED}")

    if MANIFEST_CSV.exists():
        manifest = pd.read_csv(MANIFEST_CSV, low_memory=False)
        manifest["appid"] = pd.to_numeric(manifest["appid"], errors="coerce")
        manifest = manifest[manifest["appid"].notna()].copy()
        manifest["appid"] = manifest["appid"].astype(int)
        missing = manifest[~manifest["appid"].isin(set(expanded["appid"]))].copy()
        if not missing.empty:
            missing.to_csv(OUT_MISSING, index=False, encoding="utf-8-sig")
            print(f"WARNING: missing per-game results: {OUT_MISSING} ({len(missing)})")
        else:
            print("All manifest appids were returned.")

    if not SELECTED_CSV.exists():
        raise FileNotFoundError(SELECTED_CSV)

    selected = pd.read_csv(SELECTED_CSV, low_memory=False)
    selected["appid"] = pd.to_numeric(selected["appid"], errors="coerce")
    selected = selected[selected["appid"].notna()].copy()
    selected["appid"] = selected["appid"].astype(int)

    merged = selected.merge(expanded, on="appid", how="left")
    merged.to_csv(OUT_MERGED_SELECTED, index=False, encoding="utf-8-sig")

    filled = merged["llm4_has_clear_main_protagonist"].notna().sum() if "llm4_has_clear_main_protagonist" in merged.columns else 0
    print(f"Saved merged selected CSV: {OUT_MERGED_SELECTED} ({len(merged)} rows, {filled} with llm4 results)")

    if "usage" in status_obj and status_obj["usage"]:
        usage = status_obj["usage"]
        print("Usage from batch status:")
        print(json.dumps(usage, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
