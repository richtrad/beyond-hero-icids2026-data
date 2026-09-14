#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_retrieve_openai_batch_v005_split_1000_55_rest_54mini.py

Retrieve one or both v005 split-model batches, expand compact codes, and merge
all returned per-game results into one CSV.

Examples:
  python steam_retrieve_openai_batch_v005_split_1000_55_rest_54mini.py --top
  python steam_retrieve_openai_batch_v005_split_1000_55_rest_54mini.py --rest
  python steam_retrieve_openai_batch_v005_split_1000_55_rest_54mini.py --top --rest
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from openai import OpenAI


SELECTED_CSV = Path("steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv")

TOP_BATCH_ID = Path("steam_bulk_outputs/steam_v005_top1000_55_batch_id.txt")
REST_BATCH_ID = Path("steam_bulk_outputs/steam_v005_rest_54mini_batch_id.txt")

TOP_OUTPUT_JSONL = Path("steam_bulk_outputs/steam_v005_top1000_55_output.jsonl")
REST_OUTPUT_JSONL = Path("steam_bulk_outputs/steam_v005_rest_54mini_output.jsonl")

TOP_ERRORS_JSONL = Path("steam_bulk_outputs/steam_v005_top1000_55_errors.jsonl")
REST_ERRORS_JSONL = Path("steam_bulk_outputs/steam_v005_rest_54mini_errors.jsonl")

TOP_STATUS = Path("steam_bulk_outputs/steam_v005_top1000_55_status.json")
REST_STATUS = Path("steam_bulk_outputs/steam_v005_rest_54mini_status.json")

OUT_ITEMS_COMPACT = Path("steam_bulk_outputs/steam_v005_items_compact_split_1000_55_rest_54mini.csv")
OUT_ITEMS_EXPANDED = Path("steam_bulk_outputs/steam_v005_items_expanded_split_1000_55_rest_54mini.csv")
OUT_MERGED = Path("steam_bulk_outputs/steam_v005_50k_with_taxonomy_split_1000_55_rest_54mini.csv")
OUT_MISSING = Path("steam_bulk_outputs/steam_v005_missing_items_split_1000_55_rest_54mini.csv")


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


def parse_output_jsonl(path: Path, split_label: str) -> pd.DataFrame:
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
                        "split_label": split_label,
                        "line_no": line_no,
                        "error": f"HTTP status {status_code}",
                        "raw": line[:1000],
                    })
                    continue

                text = response_text_from_body(body)
                if not text:
                    failures.append({
                        "custom_id": custom_id,
                        "split_label": split_label,
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
                        "split_label": split_label,
                        "line_no": line_no,
                        "error": "Output text was not JSON",
                        "raw": text[:1000],
                    })
                    continue

                items = parsed.get("items")
                if not isinstance(items, list):
                    failures.append({
                        "custom_id": custom_id,
                        "split_label": split_label,
                        "line_no": line_no,
                        "error": "Parsed JSON has no items list",
                        "raw": text[:1000],
                    })
                    continue

                for result in items:
                    if isinstance(result, dict):
                        result["custom_id"] = custom_id
                        result["split_label"] = split_label
                        rows.append(result)
                    else:
                        failures.append({
                            "custom_id": custom_id,
                            "split_label": split_label,
                            "line_no": line_no,
                            "error": "Non-dict item in items",
                            "raw": str(result)[:1000],
                        })

            except Exception as e:
                failures.append({
                    "custom_id": "",
                    "split_label": split_label,
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
    out["llm5_has_clear_main_protagonist"] = getcol("h").map(CLEAR_MAP).fillna("uncertain")
    out["llm5_protagonist_name"] = getcol("pn").astype(str)
    out["llm5_protagonist_type"] = getcol("pt").map(PROTAGONIST_TYPE_CODES).fillna("uncertain")
    out["llm5_protagonist_confidence_0_3"] = pd.to_numeric(getcol("pc", 0), errors="coerce")
    out["llm5_primary_archetype"] = getcol("p").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm5_secondary_archetype"] = getcol("s").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm5_tertiary_archetype"] = getcol("t").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm5_archetype_confidence_0_3"] = pd.to_numeric(getcol("ac", 0), errors="coerce")
    out["llm5_archetype_suitability_0_3"] = pd.to_numeric(getcol("su", 0), errors="coerce")
    out["llm5_shadow_load_0_3"] = pd.to_numeric(getcol("sh", 0), errors="coerce")
    out["llm5_player_projection_0_3"] = pd.to_numeric(getcol("pp", 0), errors="coerce")
    out["llm5_narrative_complexity_0_3"] = pd.to_numeric(getcol("nc", 0), errors="coerce")
    out["llm5_suggested_include_in_final_corpus"] = getcol("inc").map(INCLUDE_MAP).fillna("maybe")
    out["llm5_exclusion_reason"] = getcol("ex").map(EXCLUSION_CODES).fillna("other")
    out["llm5_needs_manual_review"] = getcol("mr", False).astype(bool)
    out["llm5_evidence_basis"] = getcol("eb").map(EVIDENCE_MAP).fillna("uncertain")
    out["llm5_note"] = getcol("note").astype(str)
    out["llm5_custom_id"] = getcol("custom_id").astype(str)
    out["llm5_split_label"] = getcol("split_label").astype(str)
    out["llm5_model_used"] = out["llm5_split_label"].map({
        "top1000_55": "gpt-5.5",
        "rest_54mini": "gpt-5.4-mini",
    }).fillna("unknown")

    out = out[out["appid"].notna()].copy()
    out["appid"] = out["appid"].astype(int)
    return out


def retrieve_one(client: OpenAI, batch_id_path: Path, output_path: Path, errors_path: Path, status_path: Path, split_label: str) -> tuple[bool, pd.DataFrame]:
    if not batch_id_path.exists():
        print(f"Batch ID file not found for {split_label}: {batch_id_path}")
        return False, pd.DataFrame()

    batch_id = batch_id_path.read_text(encoding="utf-8").strip()
    batch = client.batches.retrieve(batch_id)
    status_obj = batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{split_label} batch id: {batch.id}")
    print(f"{split_label} status: {batch.status}")
    print(f"{split_label} request counts: {getattr(batch, 'request_counts', None)}")

    if batch.status != "completed":
        print(f"{split_label} is not completed yet.")
        return False, pd.DataFrame()

    if batch.output_file_id:
        print(f"Downloading {split_label} output file: {batch.output_file_id}")
        content = client.files.content(batch.output_file_id)
        output_path.write_bytes(content.read())
        print(f"Saved output: {output_path}")

    if batch.error_file_id:
        print(f"Downloading {split_label} error file: {batch.error_file_id}")
        content = client.files.content(batch.error_file_id)
        errors_path.write_bytes(content.read())
        print(f"Saved errors: {errors_path}")

    if not output_path.exists():
        print(f"No output JSONL found for {split_label}.")
        return False, pd.DataFrame()

    compact = parse_output_jsonl(output_path, split_label)
    print(f"Parsed {split_label} compact per-game results: {len(compact)} rows")

    return True, compact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", action="store_true", help="Retrieve TOP 1000 GPT-5.5 batch.")
    parser.add_argument("--rest", action="store_true", help="Retrieve REST GPT-5.4-mini batch.")
    args = parser.parse_args()

    if not args.top and not args.rest:
        raise RuntimeError("Choose at least one: --top and/or --rest")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = OpenAI()
    compact_parts = []
    all_completed = True

    if args.top:
        ok, compact = retrieve_one(
            client, TOP_BATCH_ID, TOP_OUTPUT_JSONL, TOP_ERRORS_JSONL, TOP_STATUS, "top1000_55"
        )
        all_completed = all_completed and ok
        if not compact.empty:
            compact_parts.append(compact)

    if args.rest:
        ok, compact = retrieve_one(
            client, REST_BATCH_ID, REST_OUTPUT_JSONL, REST_ERRORS_JSONL, REST_STATUS, "rest_54mini"
        )
        all_completed = all_completed and ok
        if not compact.empty:
            compact_parts.append(compact)

    if not compact_parts:
        print("\nNo parsed results available yet. Run again later.")
        return

    compact_all = pd.concat(compact_parts, ignore_index=True)
    compact_all.to_csv(OUT_ITEMS_COMPACT, index=False, encoding="utf-8-sig")
    print(f"\nSaved compact combined results: {OUT_ITEMS_COMPACT} ({len(compact_all)} rows)")

    expanded = expand_results(compact_all)

    dupes = expanded[expanded.duplicated(subset=["appid"], keep=False)]
    if not dupes.empty:
        dupes_path = OUT_ITEMS_EXPANDED.with_name(OUT_ITEMS_EXPANDED.stem + "_duplicates.csv")
        dupes.to_csv(dupes_path, index=False, encoding="utf-8-sig")
        print(f"Duplicate appid results saved: {dupes_path} ({len(dupes)})")
    expanded = expanded.drop_duplicates(subset=["appid"], keep="last")

    expanded.to_csv(OUT_ITEMS_EXPANDED, index=False, encoding="utf-8-sig")
    print(f"Saved expanded combined results: {OUT_ITEMS_EXPANDED} ({len(expanded)} rows)")

    if not SELECTED_CSV.exists():
        raise FileNotFoundError(SELECTED_CSV)

    selected = pd.read_csv(SELECTED_CSV, low_memory=False)
    selected["appid"] = pd.to_numeric(selected["appid"], errors="coerce")
    selected = selected[selected["appid"].notna()].copy()
    selected["appid"] = selected["appid"].astype(int)

    missing = selected[~selected["appid"].isin(set(expanded["appid"]))].copy()
    if not missing.empty:
        missing.to_csv(OUT_MISSING, index=False, encoding="utf-8-sig")
        print(f"Missing selected games saved: {OUT_MISSING} ({len(missing)})")
    else:
        print("All selected appids were returned.")

    merged = selected.merge(expanded, on="appid", how="left")
    merged.to_csv(OUT_MERGED, index=False, encoding="utf-8-sig")

    filled = merged["llm5_has_clear_main_protagonist"].notna().sum() if "llm5_has_clear_main_protagonist" in merged.columns else 0
    print(f"Saved merged v005 CSV: {OUT_MERGED} ({len(merged)} rows, {filled} with llm5 results)")

    if not all_completed:
        print("\nAt least one requested batch is not completed yet. Re-run this script later.")


if __name__ == "__main__":
    main()
