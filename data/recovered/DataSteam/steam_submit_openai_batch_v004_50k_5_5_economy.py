#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_submit_openai_batch_v004_50k_5_5_economy.py

Submit the v004 50k GPT-5.5 economy batch.

WARNING: This is the step that spends API money.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from openai import OpenAI


INPUT_JSONL = Path("steam_bulk_outputs/steam_protagonist_batch_input_v004_50k_5_5_economy.jsonl")
OUT_BATCH_ID = Path("steam_bulk_outputs/steam_protagonist_batch_id_v004_50k_5_5_economy.txt")
OUT_INFO = Path("steam_bulk_outputs/steam_protagonist_batch_submit_info_v004_50k_5_5_economy.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT_JSONL))
    parser.add_argument("--description", default="Steam 50k protagonist/archetype GPT-5.5 economy v004")
    parser.add_argument("--yes-i-know-this-costs-money", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    if not args.yes_i_know_this_costs_money:
        raise RuntimeError(
            "This submit step spends API money. Re-run with --yes-i-know-this-costs-money "
            "if you really want to submit the batch."
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    line_count = sum(1 for _ in input_path.open("r", encoding="utf-8"))
    print(f"Input JSONL: {input_path}")
    print(f"Requests in file: {line_count}")
    print("Uploading batch input file...")

    client = OpenAI()

    batch_file = client.files.create(
        file=input_path.open("rb"),
        purpose="batch",
    )
    print(f"Uploaded file id: {batch_file.id}")

    print("Creating v004 50k GPT-5.5 economy batch...")
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
    print("Check later with: python steam_retrieve_openai_batch_v004_50k_5_5_economy.py")


if __name__ == "__main__":
    main()
