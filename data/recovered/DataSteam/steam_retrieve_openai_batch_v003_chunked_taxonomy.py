#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_retrieve_openai_batch_v003_chunked_taxonomy.py

Retrieve v003 chunked taxonomy batch and merge per-game items back into CSV.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from openai import OpenAI


BATCH_ID_FILE = Path("steam_bulk_outputs/steam_protagonist_batch_id_v003_chunked_taxonomy.txt")
BASE_CSV = Path("steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv")
MANIFEST_CSV = Path("steam_bulk_outputs/steam_protagonist_batch_manifest_v003_chunked_taxonomy.csv")

OUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_output_v003_chunked_taxonomy.jsonl")
OUT_ERRORS = Path("steam_bulk_outputs/steam_protagonist_batch_errors_v003_chunked_taxonomy.jsonl")
OUT_ITEMS = Path("steam_bulk_outputs/steam_protagonist_batch_items_v003_chunked_taxonomy.csv")
OUT_MISSING = Path("steam_bulk_outputs/steam_protagonist_batch_missing_items_v003_chunked_taxonomy.csv")
OUT_MERGED = Path("steam_bulk_outputs/steam_archetype_broad_pool_with_taxonomy_v003_chunked.csv")
OUT_STATUS = Path("steam_bulk_outputs/steam_protagonist_batch_status_v003_chunked_taxonomy.json")


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

    results = parse_output_jsonl(OUT_JSONL)
    print(f"Parsed per-game v003 taxonomy results: {len(results)} rows")

    if results.empty:
        print("No parsed results; stopping.")
        return

    if "appid" not in results.columns:
        raise RuntimeError("Parsed results have no appid column.")

    results["appid"] = pd.to_numeric(results["appid"], errors="coerce")
    results = results[results["appid"].notna()].copy()
    results["appid"] = results["appid"].astype(int)

    dupes = results[results.duplicated(subset=["appid"], keep=False)]
    if not dupes.empty:
        dupes_path = OUT_ITEMS.with_name(OUT_ITEMS.stem + "_duplicates.csv")
        dupes.to_csv(dupes_path, index=False, encoding="utf-8-sig")
        print(f"Duplicate appid results saved: {dupes_path} ({len(dupes)})")
    results = results.drop_duplicates(subset=["appid"], keep="last")

    results.to_csv(OUT_ITEMS, index=False, encoding="utf-8-sig")
    print(f"Saved per-game item results: {OUT_ITEMS}")

    if MANIFEST_CSV.exists():
        manifest = pd.read_csv(MANIFEST_CSV, low_memory=False)
        manifest["appid"] = pd.to_numeric(manifest["appid"], errors="coerce")
        manifest = manifest[manifest["appid"].notna()].copy()
        manifest["appid"] = manifest["appid"].astype(int)
        got = set(results["appid"])
        missing = manifest[~manifest["appid"].isin(got)].copy()
        if not missing.empty:
            missing.to_csv(OUT_MISSING, index=False, encoding="utf-8-sig")
            print(f"WARNING: missing per-game results: {OUT_MISSING} ({len(missing)})")
        else:
            print("All manifest appids were returned.")

    if not BASE_CSV.exists():
        raise FileNotFoundError(BASE_CSV)

    base = pd.read_csv(BASE_CSV, low_memory=False)
    base["appid"] = pd.to_numeric(base["appid"], errors="coerce")
    base = base[base["appid"].notna()].copy()
    base["appid"] = base["appid"].astype(int)

    keep_result_cols = [c for c in results.columns if c not in ["custom_id"]]
    prefixed = results[keep_result_cols].copy()
    prefixed = prefixed.rename(columns={
        c: f"llm3_{c}" for c in prefixed.columns if c != "appid"
    })

    merged = base.merge(prefixed, on="appid", how="left")
    merged.to_csv(OUT_MERGED, index=False, encoding="utf-8-sig")

    filled = merged["llm3_has_clear_main_protagonist"].notna().sum() if "llm3_has_clear_main_protagonist" in merged.columns else 0
    print(f"Saved merged v003 taxonomy CSV: {OUT_MERGED} ({len(merged)} rows, {filled} with llm3 results)")
    print("Suggested next: inspect llm3_needs_manual_review and taxonomy columns.")


if __name__ == "__main__":
    main()
