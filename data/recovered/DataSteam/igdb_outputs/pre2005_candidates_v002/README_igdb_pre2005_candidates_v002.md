# IGDB pre-2005 broad candidate catalog v002

This dataset is an IGDB-based historical candidate pool for later protagonist and archetype annotation.

## V002 fix

The previous v001 query was too strict and returned zero rows for 1998. V002 no longer filters `category = 0` or `themes != (42)` in the IGDB query. Instead, it fetches games by `first_release_date` and evaluates `game_type`, `category`, genres, themes, modes, and textual metadata locally.

## Important

- No LLM annotation is performed here.
- `original_release_year` is derived from IGDB `first_release_date`.
- `game_type` is retained for filtering and inspection.
- The broad candidate filter is intentionally loose.

## Outputs

- `igdb_pre2005_raw_games_v002.csv`
- `igdb_pre2005_broad_candidates_v002.csv`
- `igdb_pre2005_low_priority_review_v002.csv`
- `igdb_pre2005_year_counts_v002.csv`
- `igdb_pre2005_decade_counts_v002.csv`
- `igdb_pre2005_game_type_counts_v002.csv`
- `igdb_pre2005_examples_by_year_v002.csv`

## Summary

- Raw rows: 42533
- Broad candidates: 29054
- Low-priority/review: 13479
