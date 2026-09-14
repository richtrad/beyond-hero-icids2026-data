# Three working groups, 12-archetype version v001

Input:

`steam_bulk_outputs\final_archetype_datasets_12_v001\steam_analysis_ready_12_v001.csv`

## Standard groups

These preserve the methodological definitions and may overlap:

1. `group_1_core_strict_12_v001.csv`
2. `group_2_core_broad_12_v001.csv`
3. `group_3_review_pool_12_v001.csv`

Rows:

- CORE_STRICT: 13359
- CORE_BROAD: 24654
- REVIEW_POOL: 32959

## Exclusive groups

These are mutually exclusive operational groups:

1. `exclusive_group_1_core_strict_12_v001.csv`
2. `exclusive_group_2_core_broad_nonreview_12_v001.csv`
3. `exclusive_group_3_review_pool_noncorestrict_12_v001.csv`

Priority:

1. CORE_STRICT first.
2. REVIEW_POOL second.
3. Remaining CORE_BROAD cases third.

Rows:

- exclusive CORE_STRICT: 13359
- exclusive CORE_BROAD non-review: 1228
- exclusive REVIEW_POOL non-strict: 32945

Use the standard groups for reporting methodology. Use the exclusive groups for task assignment, manual review, or sampling where each game should appear only once.
