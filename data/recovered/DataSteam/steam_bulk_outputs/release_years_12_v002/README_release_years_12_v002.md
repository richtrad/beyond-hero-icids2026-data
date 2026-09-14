# Release years merged into 12-archetype datasets v002

This script performs no network calls. It only reads the existing cache:

`steam_bulk_outputs\steam_release_dates_cache_v001.csv`

## Outputs

- `steam_analysis_ready_12_with_year_v002.csv`
- `group_1_core_strict_12_with_year_v002.csv`
- `group_2_core_broad_12_with_year_v002.csv`
- `group_3_review_pool_12_with_year_v002.csv`
- `human_readable_group_1_core_strict_12_with_year_v002.csv`
- `human_readable_group_2_core_broad_12_with_year_v002.csv`
- `human_readable_group_3_review_pool_12_with_year_v002.csv`
- `release_year_counts_by_group_12_v002.csv`

## Cache summary

- Cache rows: 50000
- Rows with release year: 18748
- Error rows in cache: 31143

## Methodological note

`release_year` is the Steam Store release year, not necessarily the original release year of the game.
