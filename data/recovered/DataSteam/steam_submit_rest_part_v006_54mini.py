#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
steam_submit_rest_part_v006_54mini.py

Submit one prepared v006 REST part.

Important:
Submit one part at a time to avoid the gpt-5.4-mini enqueued token limit.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
from openai import OpenAI


OUT_DIR = Path("steam_bulk_outputs/steam_v006_rest_parts")
INDEX_CSV = OUT_DIR / "steam_v006_rest_parts_index.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", type=int, required=True, help="Part number, e.g. 1")
    parser.add_argument("--yes-i-know-this-costs-money", action="store_true")
    args = parser.parse_args()

    if not args.yes_i_know_this_costs_money:
        raise RuntimeError("This submit step spends API money. Re-run with --yes-i-know-this-costs-money.")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    if not INDEX_CSV.exists():
        raise FileNotFoundError(INDEX_CSV)

    index = pd.read_csv(INDEX_CSV, low_memory=False)
    row = index[index["part_no"] == args.part]
    if row.empty:
        raise RuntimeError(f"Part {args.part} not found in {INDEX_CSV}")

    row = row.iloc[0]
    input_jsonl = Path(row["input_jsonl"])
    batch_id_txt = Path(row["batch_id_txt"])
    submit_info = OUT_DIR / f"steam_v006_rest_54mini_part_{args.part:03d}_submit_info.json"

    if not input_jsonl.exists():
        raise FileNotFoundError(input_jsonl)

    line_count = sum(1 for _ in input_jsonl.open("r", encoding="utf-8"))
    print(f"Submitting REST part {args.part}")
    print(f"Input JSONL: {input_jsonl}")
    print(f"Games: {row['games']}")
    print(f"Requests: {line_count}")

    client = OpenAI()

    batch_file = client.files.create(file=input_jsonl.open("rb"), purpose="batch")
    print(f"Uploaded file id: {batch_file.id}")

    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={"description": f"Steam v006 REST gpt-5.4-mini part {args.part:03d}"}
    )

    batch_id_txt.write_text(batch.id, encoding="utf-8")
    info = batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)
    submit_info.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Batch id: {batch.id}")
    print(f"Saved batch id: {batch_id_txt}")
    print("Check with:")
    print(f"  python steam_retrieve_rest_parts_v006_54mini.py --part {args.part}")


if __name__ == "__main__":
    main()
