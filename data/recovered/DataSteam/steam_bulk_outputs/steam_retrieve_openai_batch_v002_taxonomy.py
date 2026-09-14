#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_retrieve_openai_batch_v002_taxonomy.py

Check a v002 taxonomy Batch job, download output/error files if available, and
merge structured results back into the broad pool CSV.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from openai import OpenAI


BATCH_ID_FILE = Path("steam_bulk_outputs/steam_protagonist_batch_id_v002_taxonomy.txt")
BASE_CSV = Path("steam_bulk_outputs/steam_archetype_broad_pool_for_coding.csv")
OUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_output_v002_taxonomy.jsonl")
OUT_ERRORS = Path("steam_bulk_outputs/steam_protagonist_batch_errors_v002_taxonomy.jsonl")
OUT_MERGED = Path("steam_bulk_outputs/steam_archetype_broad_pool_with_taxonomy_v002.csv")
OUT_STATUS = Path("steam_bulk_outputs/steam_protagonist_batch_status_v002_taxonomy.json")


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

                parsed["custom_id"] = custom_id
                rows.append(parsed)

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
    print(f"Parsed structured v002 taxonomy results: {len(results)} rows")

    if results.empty:
        print("No parsed results; stopping.")
        return

    if "appid" not in results.columns:
        raise RuntimeError("Parsed results have no appid column.")

    results["appid"] = pd.to_numeric(results["appid"], errors="coerce")
    results = results[results["appid"].notna()].copy()
    results["appid"] = results["appid"].astype(int)
    results = results.drop_duplicates(subset=["appid"], keep="last")

    if not BASE_CSV.exists():
        raise FileNotFoundError(BASE_CSV)

    base = pd.read_csv(BASE_CSV, low_memory=False)
    base["appid"] = pd.to_numeric(base["appid"], errors="coerce")
    base = base[base["appid"].notna()].copy()
    base["appid"] = base["appid"].astype(int)

    keep_result_cols = [c for c in results.columns if c not in ["custom_id"]]
    prefixed = results[keep_result_cols].copy()
    prefixed = prefixed.rename(columns={
        c: f"llm2_{c}" for c in prefixed.columns if c != "appid"
    })

    merged = base.merge(prefixed, on="appid", how="left")
    merged.to_csv(OUT_MERGED, index=False, encoding="utf-8-sig")

    print(f"Saved merged v002 taxonomy CSV: {OUT_MERGED} ({len(merged)} rows)")
    print("Suggested next: inspect llm2_needs_manual_review and taxonomy columns.")


if __name__ == "__main__":
    main()
