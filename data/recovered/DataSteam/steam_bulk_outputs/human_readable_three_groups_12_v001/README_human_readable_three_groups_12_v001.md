# Human-readable three-group exports, 12-archetype version v001

Input directory:

`steam_bulk_outputs\three_groups_12_v001`

Output directory:

`steam_bulk_outputs\human_readable_three_groups_12_v001`

Mode:

`standard`

## Output columns

- jmeno hry
- jmeno postavy
- primarni archetyp
- sekundarni archetyp
- tercialni archetyp
- věrohodnost odhadu na škále 0 až 1

## Credibility formula

`mean(protagonist_confidence_0_3, archetype_confidence_0_3, archetype_suitability_0_3) / 3`

## Generated files

- `human_readable_group_1_core_strict_12_v001.csv` — 13359 rows, status: ok
- `human_readable_group_2_core_broad_12_v001.csv` — 24654 rows, status: ok
- `human_readable_group_3_review_pool_12_v001.csv` — 32959 rows, status: ok
