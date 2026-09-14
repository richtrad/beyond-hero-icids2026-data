# IGDB post-2004 broad candidate catalog v001

This dataset is an IGDB-based candidate pool for games released from 2005 onward.

## Important

- No LLM annotation is performed here.
- `original_release_year` is derived from IGDB `first_release_date`.
- This is a companion to the pre-2005 historical block.
- It does not touch `igdb_outputs/pre2005_candidates_v002/`.
- `game_type` is retained for filtering and inspection.
- The broad candidate filter is intentionally loose.

## Outputs

- `igdb_post2004_raw_games_v001.csv`
- `igdb_post2004_broad_candidates_v001.csv`
- `igdb_post2004_low_priority_review_v001.csv`
- `igdb_post2004_year_counts_v001.csv`
- `igdb_post2004_decade_counts_v001.csv`
- `igdb_post2004_game_type_counts_v001.csv`
- `igdb_post2004_examples_by_year_v001.csv`

## Summary

- Raw rows: 236084
- Broad candidates: 177446
- Low-priority/review: 58638
