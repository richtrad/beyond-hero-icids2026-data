#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_submit_openai_batch_v005_split_1000_55_rest_54mini.py

Submit one or both v005 split-model batches.

WARNING: This script spends API money if run with --yes-i-know-this-costs-money.

Examples:
  Submit only TOP 1000 GPT-5.5:
    python steam_submit_openai_batch_v005_split_1000_55_rest_54mini.py --top --yes-i-know-this-costs-money

  Submit only REST GPT-5.4-mini:
    python steam_submit_openai_batch_v005_split_1000_55_rest_54mini.py --rest --yes-i-know-this-costs-money

  Submit both:
    python steam_submit_openai_batch_v005_split_1000_55_rest_54mini.py --top --rest --yes-i-know-this-costs-money
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from openai import OpenAI


TOP_JSONL = Path("steam_bulk_outputs/steam_v005_top1000_55_input.jsonl")
REST_JSONL = Path("steam_bulk_outputs/steam_v005_rest_54mini_input.jsonl")

TOP_BATCH_ID = Path("steam_bulk_outputs/steam_v005_top1000_55_batch_id.txt")
REST_BATCH_ID = Path("steam_bulk_outputs/steam_v005_rest_54mini_batch_id.txt")

TOP_SUBMIT_INFO = Path("steam_bulk_outputs/steam_v005_top1000_55_submit_info.json")
REST_SUBMIT_INFO = Path("steam_bulk_outputs/steam_v005_rest_54mini_submit_info.json")


def submit_one(client: OpenAI, input_path: Path, batch_id_path: Path, info_path: Path, description: str) -> None:
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    line_count = sum(1 for _ in input_path.open("r", encoding="utf-8"))
    print(f"\nInput JSONL: {input_path}")
    print(f"Requests in file: {line_count}")
    print("Uploading batch input file...")

    batch_file = client.files.create(
        file=input_path.open("rb"),
        purpose="batch",
    )
    print(f"Uploaded file id: {batch_file.id}")

    print("Creating batch...")
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={"description": description},
    )

    batch_id_path.parent.mkdir(parents=True, exist_ok=True)
    batch_id_path.write_text(batch.id, encoding="utf-8")

    info = batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Batch id: {batch.id}")
    print(f"Saved batch id: {batch_id_path}")
    print(f"Saved submit info: {info_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", action="store_true", help="Submit TOP 1000 GPT-5.5 batch.")
    parser.add_argument("--rest", action="store_true", help="Submit REST GPT-5.4-mini batch.")
    parser.add_argument("--yes-i-know-this-costs-money", action="store_true")
    args = parser.parse_args()

    if not args.top and not args.rest:
        raise RuntimeError("Choose at least one: --top and/or --rest")

    if not args.yes_i_know_this_costs_money:
        raise RuntimeError(
            "This submit step spends API money. Re-run with --yes-i-know-this-costs-money "
            "if you really want to submit the selected batch(es)."
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = OpenAI()

    if args.top:
        submit_one(
            client,
            TOP_JSONL,
            TOP_BATCH_ID,
            TOP_SUBMIT_INFO,
            "Steam v005 TOP 1000 protagonist/archetype GPT-5.5"
        )

    if args.rest:
        submit_one(
            client,
            REST_JSONL,
            REST_BATCH_ID,
            REST_SUBMIT_INFO,
            "Steam v005 REST protagonist/archetype GPT-5.4-mini"
        )

    print("\nCheck later with: python steam_retrieve_openai_batch_v005_split_1000_55_rest_54mini.py --top --rest")


if __name__ == "__main__":
    main()
