#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_submit_openai_batch_v003_chunked_taxonomy.py

Upload v003 chunked taxonomy JSONL and create an OpenAI Batch job.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from openai import OpenAI


INPUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_input_v003_chunked_taxonomy.jsonl")
OUT_BATCH_ID = Path("steam_bulk_outputs/steam_protagonist_batch_id_v003_chunked_taxonomy.txt")
OUT_INFO = Path("steam_bulk_outputs/steam_protagonist_batch_submit_info_v003_chunked_taxonomy.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT_JSONL))
    parser.add_argument("--description", default="Steam protagonist/archetype chunked taxonomy v003")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = OpenAI()

    print(f"Uploading batch input file: {input_path}")
    batch_file = client.files.create(
        file=input_path.open("rb"),
        purpose="batch",
    )
    print(f"Uploaded file id: {batch_file.id}")

    print("Creating v003 chunked taxonomy batch...")
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={"description": args.description},
    )

    OUT_BATCH_ID.parent.mkdir(parents=True, exist_ok=True)
    OUT_BATCH_ID.write_text(batch.id, encoding="utf-8")

    info = batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)
    OUT_INFO.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Batch id: {batch.id}")
    print(f"Saved: {OUT_BATCH_ID}")
    print("Check later with: python steam_retrieve_openai_batch_v003_chunked_taxonomy.py")


if __name__ == "__main__":
    main()
