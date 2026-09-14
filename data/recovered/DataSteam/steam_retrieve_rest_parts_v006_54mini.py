#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_retrieve_rest_parts_v006_54mini.py

Retrieve one or all v006 REST part batches, expand compact codes, and optionally
merge all retrieved REST parts with v005 TOP results.

Typical:
  python steam_retrieve_rest_parts_v006_54mini.py --part 1
  python steam_retrieve_rest_parts_v006_54mini.py --all
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from openai import OpenAI


OUT_DIR = Path("steam_bulk_outputs/steam_v006_rest_parts")
INDEX_CSV = OUT_DIR / "steam_v006_rest_parts_index.csv"
SELECTED_CSV = Path("steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv")

TOP_V005_EXPANDED = Path("steam_bulk_outputs/steam_v005_items_expanded_split_1000_55_rest_54mini.csv")

OUT_REST_COMPACT_ALL = OUT_DIR / "steam_v006_rest_items_compact_all.csv"
OUT_REST_EXPANDED_ALL = OUT_DIR / "steam_v006_rest_items_expanded_all.csv"
OUT_FINAL_MERGED = Path("steam_bulk_outputs/steam_v006_50k_with_taxonomy_top_v005_rest_parts.csv")
OUT_MISSING = Path("steam_bulk_outputs/steam_v006_missing_items_top_v005_rest_parts.csv")


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


def parse_output_jsonl(path: Path, part_no: int) -> pd.DataFrame:
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
                    failures.append({"part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": f"HTTP status {status_code}", "raw": line[:1000]})
                    continue

                text = response_text_from_body(body)
                if not text:
                    failures.append({"part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": "No output text found", "raw": line[:1000]})
                    continue

                try:
                    parsed = json.loads(text)
                except Exception:
                    failures.append({"part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": "Output text was not JSON", "raw": text[:1000]})
                    continue

                items = parsed.get("items")
                if not isinstance(items, list):
                    failures.append({"part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": "Parsed JSON has no items list", "raw": text[:1000]})
                    continue

                for result in items:
                    if isinstance(result, dict):
                        result["custom_id"] = custom_id
                        result["part_no"] = part_no
                        rows.append(result)
            except Exception as e:
                failures.append({"part_no": part_no, "custom_id": "", "line_no": line_no, "error": str(e), "raw": line[:1000]})

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
    out["llm6_has_clear_main_protagonist"] = getcol("h").map(CLEAR_MAP).fillna("uncertain")
    out["llm6_protagonist_name"] = getcol("pn").astype(str)
    out["llm6_protagonist_type"] = getcol("pt").map(PROTAGONIST_TYPE_CODES).fillna("uncertain")
    out["llm6_protagonist_confidence_0_3"] = pd.to_numeric(getcol("pc", 0), errors="coerce")
    out["llm6_primary_archetype"] = getcol("p").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm6_secondary_archetype"] = getcol("s").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm6_tertiary_archetype"] = getcol("t").map(ARCHETYPE_CODES).fillna("Uncertain")
    out["llm6_archetype_confidence_0_3"] = pd.to_numeric(getcol("ac", 0), errors="coerce")
    out["llm6_archetype_suitability_0_3"] = pd.to_numeric(getcol("su", 0), errors="coerce")
    out["llm6_shadow_load_0_3"] = pd.to_numeric(getcol("sh", 0), errors="coerce")
    out["llm6_player_projection_0_3"] = pd.to_numeric(getcol("pp", 0), errors="coerce")
    out["llm6_narrative_complexity_0_3"] = pd.to_numeric(getcol("nc", 0), errors="coerce")
    out["llm6_suggested_include_in_final_corpus"] = getcol("inc").map(INCLUDE_MAP).fillna("maybe")
    out["llm6_exclusion_reason"] = getcol("ex").map(EXCLUSION_CODES).fillna("other")
    out["llm6_needs_manual_review"] = getcol("mr", False).astype(bool)
    out["llm6_evidence_basis"] = getcol("eb").map(EVIDENCE_MAP).fillna("uncertain")
    out["llm6_note"] = getcol("note").astype(str)
    out["llm6_model_used"] = "gpt-5.4-mini"
    out["llm6_part_no"] = pd.to_numeric(getcol("part_no", 0), errors="coerce")
    out["llm6_custom_id"] = getcol("custom_id").astype(str)

    out = out[out["appid"].notna()].copy()
    out["appid"] = out["appid"].astype(int)
    return out


def retrieve_part(client: OpenAI, row: pd.Series) -> tuple[bool, pd.DataFrame]:
    part_no = int(row["part_no"])
    batch_id_path = Path(row["batch_id_txt"])
    output_path = OUT_DIR / f"steam_v006_rest_54mini_part_{part_no:03d}_output.jsonl"
    errors_path = OUT_DIR / f"steam_v006_rest_54mini_part_{part_no:03d}_errors.jsonl"
    status_path = OUT_DIR / f"steam_v006_rest_54mini_part_{part_no:03d}_status.json"

    if not batch_id_path.exists():
        print(f"Part {part_no}: no batch id yet.")
        return False, pd.DataFrame()

    batch_id = batch_id_path.read_text(encoding="utf-8").strip()
    batch = client.batches.retrieve(batch_id)
    status_obj = batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)
    status_path.write_text(json.dumps(status_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nPart {part_no} batch id: {batch.id}")
    print(f"Part {part_no} status: {batch.status}")
    print(f"Part {part_no} request counts: {getattr(batch, 'request_counts', None)}")

    if batch.status != "completed":
        return False, pd.DataFrame()

    if batch.output_file_id:
        content = client.files.content(batch.output_file_id)
        output_path.write_bytes(content.read())
        print(f"Part {part_no}: saved output {output_path}")

    if batch.error_file_id:
        content = client.files.content(batch.error_file_id)
        errors_path.write_bytes(content.read())
        print(f"Part {part_no}: saved errors {errors_path}")

    if not output_path.exists():
        return False, pd.DataFrame()

    compact = parse_output_jsonl(output_path, part_no)
    print(f"Part {part_no}: parsed {len(compact)} per-game rows")
    return True, compact


def load_top_as_llm6() -> pd.DataFrame:
    """Load already retrieved v005 TOP rows, convert llm5_* to llm6_* for final merge."""
    if not TOP_V005_EXPANDED.exists():
        return pd.DataFrame()

    top = pd.read_csv(TOP_V005_EXPANDED, low_memory=False)
    if "llm5_split_label" in top.columns:
        top = top[top["llm5_split_label"].astype(str).str.contains("top", case=False, na=False)].copy()

    if top.empty or "appid" not in top.columns:
        return pd.DataFrame()

    cols = [c for c in top.columns if c == "appid" or c.startswith("llm5_")]
    top = top[cols].copy()
    rename = {c: c.replace("llm5_", "llm6_") for c in cols if c.startswith("llm5_")}
    top = top.rename(columns=rename)
    top["llm6_model_used"] = "gpt-5.5"
    return top


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", type=int, default=0, help="Retrieve one part number.")
    parser.add_argument("--all", action="store_true", help="Retrieve all parts that have batch ids.")
    parser.add_argument("--no-final-merge", action="store_true")
    args = parser.parse_args()

    if not args.all and args.part <= 0:
        raise RuntimeError("Use --part N or --all")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    if not INDEX_CSV.exists():
        raise FileNotFoundError(INDEX_CSV)

    index = pd.read_csv(INDEX_CSV, low_memory=False)
    if args.part > 0:
        index = index[index["part_no"] == args.part].copy()
        if index.empty:
            raise RuntimeError(f"Part {args.part} not found.")

    client = OpenAI()
    compact_parts = []
    completed_parts = 0

    for _, row in index.iterrows():
        ok, compact = retrieve_part(client, row)
        if ok:
            completed_parts += 1
        if not compact.empty:
            compact_parts.append(compact)

    if not compact_parts:
        print("\nNo completed part outputs available yet.")
        return

    compact_all = pd.concat(compact_parts, ignore_index=True)
    compact_all.to_csv(OUT_REST_COMPACT_ALL, index=False, encoding="utf-8-sig")
    print(f"\nSaved REST compact combined: {OUT_REST_COMPACT_ALL} ({len(compact_all)} rows)")

    rest_expanded = expand_results(compact_all).drop_duplicates(subset=["appid"], keep="last")
    rest_expanded.to_csv(OUT_REST_EXPANDED_ALL, index=False, encoding="utf-8-sig")
    print(f"Saved REST expanded combined: {OUT_REST_EXPANDED_ALL} ({len(rest_expanded)} rows)")

    if args.no_final_merge:
        return

    if not SELECTED_CSV.exists():
        print("Selected CSV missing; final merge skipped.")
        return

    selected = pd.read_csv(SELECTED_CSV, low_memory=False)
    selected["appid"] = pd.to_numeric(selected["appid"], errors="coerce")
    selected = selected[selected["appid"].notna()].copy()
    selected["appid"] = selected["appid"].astype(int)

    top_expanded = load_top_as_llm6()
    all_results = pd.concat([top_expanded, rest_expanded], ignore_index=True) if not top_expanded.empty else rest_expanded
    all_results = all_results.drop_duplicates(subset=["appid"], keep="last")

    missing = selected[~selected["appid"].isin(set(all_results["appid"]))].copy()
    if not missing.empty:
        missing.to_csv(OUT_MISSING, index=False, encoding="utf-8-sig")
        print(f"Missing selected games saved: {OUT_MISSING} ({len(missing)})")
    else:
        print("All selected appids have results.")

    merged = selected.merge(all_results, on="appid", how="left")
    merged.to_csv(OUT_FINAL_MERGED, index=False, encoding="utf-8-sig")
    filled = merged["llm6_has_clear_main_protagonist"].notna().sum() if "llm6_has_clear_main_protagonist" in merged.columns else 0
    print(f"Saved final merged CSV: {OUT_FINAL_MERGED} ({len(merged)} rows, {filled} with llm6 results)")
    print(f"Completed parts retrieved in this run: {completed_parts}/{len(index)}")


if __name__ == "__main__":
    main()
