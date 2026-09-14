# IGDB pre-2005 broad candidate catalog v001

This dataset is an IGDB-based historical candidate pool for later protagonist and archetype annotation.

## Important

- No LLM annotation is performed here.
- `original_release_year` is derived from IGDB `first_release_date`.
- The query uses `category = 0` to prefer main games and avoid DLC, expansions, bundles, ports, remasters, etc.
- The broad candidate filter is intentionally loose: it marks likely useful games, but does not delete the low-priority cases.

## Outputs

- `igdb_pre2005_raw_main_games_v001.csv`
- `igdb_pre2005_broad_candidates_v001.csv`
- `igdb_pre2005_low_priority_review_v001.csv`
- `igdb_pre2005_year_counts_v001.csv`
- `igdb_pre2005_decade_counts_v001.csv`
- `igdb_pre2005_examples_by_year_v001.csv`

## Summary

- Raw rows: 0
- Broad candidates: 0
- Low-priority/review: 0
