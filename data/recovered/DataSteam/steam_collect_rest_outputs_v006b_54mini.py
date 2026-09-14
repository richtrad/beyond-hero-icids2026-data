#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_collect_rest_outputs_v006b_54mini.py

Local-only collector/fixer for v006 REST parts.

Problem it fixes:
If you ran retrieve with --part 1 and later --part 2, the previous retrieve script
could overwrite the combined CSV with only the currently retrieved part.
This script scans the local folder for all already downloaded part output JSONL files,
parses them all, combines them, and merges with the TOP 1000 v005 results.

This script does NOT call OpenAI API and does NOT spend money.

Inputs:
  steam_bulk_outputs/steam_v006_rest_parts/steam_v006_rest_54mini_part_*_output.jsonl
  steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv
  steam_bulk_outputs/steam_v005_items_expanded_split_1000_55_rest_54mini.csv

Outputs:
  steam_bulk_outputs/steam_v006_rest_parts/steam_v006b_rest_items_compact_all_local.csv
  steam_bulk_outputs/steam_v006_rest_parts/steam_v006b_rest_items_expanded_all_local.csv
  steam_bulk_outputs/steam_v006b_50k_with_taxonomy_top_v005_rest_parts_local.csv
  steam_bulk_outputs/steam_v006b_missing_items_top_v005_rest_parts_local.csv
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


OUT_DIR = Path("steam_bulk_outputs/steam_v006_rest_parts")
SELECTED_CSV = Path("steam_bulk_outputs/steam_v005_selected_games_split_1000_55_rest_54mini.csv")
TOP_V005_EXPANDED = Path("steam_bulk_outputs/steam_v005_items_expanded_split_1000_55_rest_54mini.csv")

OUT_REST_COMPACT_ALL = OUT_DIR / "steam_v006b_rest_items_compact_all_local.csv"
OUT_REST_EXPANDED_ALL = OUT_DIR / "steam_v006b_rest_items_expanded_all_local.csv"
OUT_FINAL_MERGED = Path("steam_bulk_outputs/steam_v006b_50k_with_taxonomy_top_v005_rest_parts_local.csv")
OUT_MISSING = Path("steam_bulk_outputs/steam_v006b_missing_items_top_v005_rest_parts_local.csv")


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


def part_no_from_path(path: Path) -> int:
    m = re.search(r"part_(\d+)_output", path.name)
    return int(m.group(1)) if m else 0


def parse_output_jsonl(path: Path) -> pd.DataFrame:
    part_no = part_no_from_path(path)
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
                    failures.append({"file": str(path), "part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": f"HTTP status {status_code}", "raw": line[:1000]})
                    continue

                text = response_text_from_body(body)
                if not text:
                    failures.append({"file": str(path), "part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": "No output text found", "raw": line[:1000]})
                    continue

                try:
                    parsed = json.loads(text)
                except Exception:
                    failures.append({"file": str(path), "part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": "Output text was not JSON", "raw": text[:1000]})
                    continue

                items = parsed.get("items")
                if not isinstance(items, list):
                    failures.append({"file": str(path), "part_no": part_no, "custom_id": custom_id, "line_no": line_no, "error": "Parsed JSON has no items list", "raw": text[:1000]})
                    continue

                for result in items:
                    if isinstance(result, dict):
                        result["custom_id"] = custom_id
                        result["part_no"] = part_no
                        result["source_output_file"] = str(path)
                        rows.append(result)

            except Exception as e:
                failures.append({"file": str(path), "part_no": part_no, "custom_id": "", "line_no": line_no, "error": str(e), "raw": line[:1000]})

    if failures:
        fail_path = path.with_name(path.stem + "_v006b_parse_failures.csv")
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
    out["llm6_source_output_file"] = getcol("source_output_file").astype(str)

    out = out[out["appid"].notna()].copy()
    out["appid"] = out["appid"].astype(int)
    return out


def load_top_as_llm6() -> pd.DataFrame:
    if not TOP_V005_EXPANDED.exists():
        print(f"TOP v005 expanded file not found: {TOP_V005_EXPANDED}")
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
    top["llm6_part_no"] = pd.NA
    return top


def main() -> None:
    if not OUT_DIR.exists():
        raise FileNotFoundError(OUT_DIR)

    output_files = sorted(OUT_DIR.glob("steam_v006_rest_54mini_part_*_output.jsonl"))
    if not output_files:
        print(f"No local part output JSONL files found in {OUT_DIR}")
        return

    print("Found local REST output files:")
    for p in output_files:
        print(f"  {p.name}")

    compact_parts = []
    for path in output_files:
        part_df = parse_output_jsonl(path)
        print(f"Parsed {len(part_df)} rows from {path.name}")
        if not part_df.empty:
            compact_parts.append(part_df)

    if not compact_parts:
        print("No parsed REST rows.")
        return

    compact_all = pd.concat(compact_parts, ignore_index=True)
    compact_all.to_csv(OUT_REST_COMPACT_ALL, index=False, encoding="utf-8-sig")

    rest_expanded = expand_results(compact_all).drop_duplicates(subset=["appid"], keep="last")
    rest_expanded.to_csv(OUT_REST_EXPANDED_ALL, index=False, encoding="utf-8-sig")

    print(f"Saved REST compact combined: {OUT_REST_COMPACT_ALL} ({len(compact_all)} rows)")
    print(f"Saved REST expanded combined: {OUT_REST_EXPANDED_ALL} ({len(rest_expanded)} rows)")

    top_expanded = load_top_as_llm6()
    if not top_expanded.empty:
        all_results = pd.concat([top_expanded, rest_expanded], ignore_index=True)
    else:
        all_results = rest_expanded
    all_results = all_results.drop_duplicates(subset=["appid"], keep="last")

    if not SELECTED_CSV.exists():
        print(f"Selected CSV not found, cannot make final merged file: {SELECTED_CSV}")
        return

    selected = pd.read_csv(SELECTED_CSV, low_memory=False)
    selected["appid"] = pd.to_numeric(selected["appid"], errors="coerce")
    selected = selected[selected["appid"].notna()].copy()
    selected["appid"] = selected["appid"].astype(int)

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

    if "llm6_model_used" in merged.columns:
        print("\nResults by model:")
        print(merged["llm6_model_used"].value_counts(dropna=False).to_string())

    if "llm6_part_no" in merged.columns:
        print("\nREST results by part:")
        rest = merged[merged["llm6_model_used"].eq("gpt-5.4-mini")]
        print(rest["llm6_part_no"].value_counts(dropna=False).sort_index().to_string())


if __name__ == "__main__":
    main()
