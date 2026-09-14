# Data catalogue

[Overview](../README.md) · [How the data were created](how-the-evaluation-was-created.md)

These are complete recovered files, not top-game samples. Counts below were parsed from the archived CSV files. Different stages overlap: do not sum rows across tables. Historical acquisition does not imply complete coverage of either platform.

| Dataset | Rows | Download |
|---|---:|---|
| Steam catalogue, all downloaded application IDs | 171,570 | [CSV (gzip)](../data/recovered/DataSteam/steam_bulk_outputs/steam_catalog_games.csv.gz) |
| SteamSpy all-snapshot | 82,251 | [CSV (gzip)](../data/recovered/DataSteam/steam_bulk_outputs/steamspy_all_snapshot.csv.gz) |
| Merged Steam-side catalogue | 177,809 | [CSV (gzip)](../data/recovered/DataSteam/steam_bulk_outputs/steam_catalog_merged.csv.gz) |
| Steam broad review-filtered pool | 5,089 | [CSV (gzip)](../data/recovered/DataSteam/steam_bulk_outputs/steam_archetype_broad_pool.csv.gz) |
| Steam batch selection and harmonized labels | 50,000 | [CSV (gzip)](../data/recovered/DataSteam/steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv.gz) |
| IGDB raw catalogue, all downloaded years | 278,617 | [CSV (gzip)](../data/recovered/DataSteam/igdb_outputs/master_candidates_v001/igdb_master_raw_all_years_v001.csv.gz) |
| IGDB raw catalogue through 2025 | 264,491 | [CSV (gzip)](../data/recovered/DataSteam/igdb_outputs/master_candidates_v001/igdb_master_raw_analysis_years_v001.csv.gz) |
| IGDB broad candidates through 2025 | 194,354 | [CSV (gzip)](../data/recovered/DataSteam/igdb_outputs/master_candidates_v001/igdb_master_broad_analysis_years_v001.csv.gz) |
| IGDB annotated master | 194,354 | [CSV (gzip)](../data/recovered/Downloads/igdb_master_broad_with_metadata_agent_annotations_v001%20%281%29.csv.gz) |
| Simplified full annotated master | 191,268 | [CSV (gzip)](../data/recovered/Downloads/igdb_archetype_annotations_simple_master_v001.csv.gz) |
| Protagonist-only export, original | 90,388 | [CSV (gzip)](../data/recovered/Downloads/igdb_archetype_annotations_simple_characters_only_v001%20%281%29.csv.gz) |
| Analytical rows with visibility weights | 90,387 | [CSV (gzip)](../data/recovered/Downloads/merged_rows_with_visibility_weights.csv.gz) |

## All recovered files

The [complete file index](recovered-file-index.md) also includes original API-response caches, acquisition scripts, batch requests and outputs, earlier versions, checkpoints, comparison tables and plotting sources. The machine-readable [manifest](../provenance/data-manifest.csv) records every original alias, archived path, size and both SHA-256 hashes. Byte-identical copies share one archive file.

Gzip compression preserves all rows and original bytes. For example, pandas can open a `.csv.gz` directly with `pd.read_csv(path)`. The archive scripts are historical research code, not automatically executed by the verification command.

## Column schemas

### Steam catalogue, all downloaded application IDs

`appid`, `last_modified`, `price_change_number`, `steam_catalog_name`, `steam_catalog_source`, `steam_catalog_fetched_at`

### SteamSpy all-snapshot

`appid`, `steamspy_name`, `steamspy_developer`, `steamspy_publisher`, `steamspy_genre`, `steamspy_tags`, `steamspy_positive`, `steamspy_negative`, `total_ratings_pos_neg`, `positive_ratio`, `steamspy_userscore`, `steamspy_score_rank`, `steamspy_owners`, `steamspy_owners_midpoint`, `steamspy_average_forever`, `steamspy_median_forever`, `steamspy_price`, `steamspy_initialprice`, `steamspy_discount`, `steamspy_ccu`, `steamspy_languages`

### Merged Steam-side catalogue

`appid`, `name`, `want_details`, `candidate_reason`, `bucket`, `matched_terms`, `relevance_score`, `reaction_rank`, `total_ratings_pos_neg`, `steamspy_positive`, `steamspy_negative`, `positive_ratio`, `steamspy_owners`, `steamspy_owners_midpoint`, `steamspy_genre`, `steamspy_tags`, `steamspy_hit_terms`, `steam_catalog_name`, `steamspy_name`, `last_modified`, `price_change_number`, `steam_catalog_source`, `steam_catalog_fetched_at`, `steamspy_developer`, `steamspy_publisher`, `steamspy_userscore`, `steamspy_score_rank`, `steamspy_average_forever`, `steamspy_median_forever`, `steamspy_price`, `steamspy_initialprice`, `steamspy_discount`, `steamspy_ccu`, `steamspy_languages`, `steamspy_hit_types`, `is_term_match`, `forced_include`, `candidate_by_term_and_reactions`, `candidate_by_popular_fallback`

### Steam broad review-filtered pool

`broad_rank`, `appid`, `name`, `want_details`, `candidate_reason`, `bucket`, `matched_terms`, `relevance_score`, `reaction_rank`, `total_ratings_pos_neg`, `steamspy_positive`, `steamspy_negative`, `positive_ratio`, `steamspy_owners`, `steamspy_owners_midpoint`, `steamspy_genre`, `steamspy_tags`, `steamspy_hit_terms`, `steam_catalog_name`, `steamspy_name`, `last_modified`, `price_change_number`, `steam_catalog_source`, `steam_catalog_fetched_at`, `steamspy_developer`, `steamspy_publisher`, `steamspy_userscore`, `steamspy_score_rank`, `steamspy_average_forever`, `steamspy_median_forever`, `steamspy_price`, `steamspy_initialprice`, `steamspy_discount`, `steamspy_ccu`, `steamspy_languages`, `steamspy_hit_types`, `is_term_match`, `forced_include`, `candidate_by_term_and_reactions`, `candidate_by_popular_fallback`, `available_terms_for_later_inspection`, `source_row_count_for_appid`, `name_norm`, `is_control_seed`, `control_title`, `control_protagonist`, `control_match_score`, `broad_pool_reason`

### Steam batch selection and harmonized labels

`selection_rank`, `appid`, `name`, `total_ratings_pos_neg`, `positive_ratio`, `steamspy_owners`, `v005_split`, `v005_model`, `llm6_model_used`, `corpus_label_12`, `is_core_strict_12`, `is_core_broad_12`, `is_core_maybe_12`, `is_review_pool_12`, `is_missing_llm_result`, `llm6_has_clear_main_protagonist`, `llm6_protagonist_name`, `llm6_protagonist_type`, `llm6_protagonist_confidence_0_3`, `primary_archetype_12`, `secondary_archetype_12`, `tertiary_archetype_12`, `primary_archetype_12_is_valid`, `original_shadow_antihero_present`, `original_primary_was_shadow_antihero`, `llm6_shadow_load_0_3`, `shadow_load_category`, `archetype_12_correction_method`, `llm6_primary_archetype`, `llm6_secondary_archetype`, `llm6_tertiary_archetype`, `llm6_archetype_confidence_0_3`, `llm6_archetype_suitability_0_3`, `llm6_player_projection_0_3`, `llm6_narrative_complexity_0_3`, `llm6_suggested_include_in_final_corpus`, `llm6_needs_manual_review`, `needs_manual_review_12`, `llm6_evidence_basis`, `llm6_exclusion_reason`, `llm6_note`, `rank_bin_5000`, `available_terms_for_later_inspection`, `control_protagonist`, `llm6_custom_id`, `llm6_split_label`, `llm6_part_no`, `llm6_source_output_file`

### IGDB raw catalogue, all downloaded years

`igdb_id`, `name`, `slug`, `original_release_date`, `original_release_year`, `decade`, `category`, `game_type`, `status`, `genres`, `themes`, `game_modes`, `player_perspectives`, `platforms`, `rating`, `rating_count`, `total_rating`, `total_rating_count`, `aggregated_rating`, `aggregated_rating_count`, `summary`, `storyline`, `has_summary`, `has_storyline`, `parent_game`, `version_parent`, `version_title`, `collection`, `collections`, `franchise`, `franchises`, `url`, `fetched_at`, `broad_candidate_for_archetype_annotation`, `thematic_fit_score`, `candidate_reason`, `excluded_by_type_or_category`, `type_exclusion_reason`, `visibility_count_score`, `source_block`, `source_pool`, `original_release_year_num`

### IGDB raw catalogue through 2025

`igdb_id`, `name`, `slug`, `original_release_date`, `original_release_year`, `decade`, `category`, `game_type`, `status`, `genres`, `themes`, `game_modes`, `player_perspectives`, `platforms`, `rating`, `rating_count`, `total_rating`, `total_rating_count`, `aggregated_rating`, `aggregated_rating_count`, `summary`, `storyline`, `has_summary`, `has_storyline`, `parent_game`, `version_parent`, `version_title`, `collection`, `collections`, `franchise`, `franchises`, `url`, `fetched_at`, `broad_candidate_for_archetype_annotation`, `thematic_fit_score`, `candidate_reason`, `excluded_by_type_or_category`, `type_exclusion_reason`, `visibility_count_score`, `source_block`, `source_pool`, `original_release_year_num`

### IGDB broad candidates through 2025

`igdb_id`, `name`, `slug`, `original_release_date`, `original_release_year`, `decade`, `category`, `game_type`, `status`, `genres`, `themes`, `game_modes`, `player_perspectives`, `platforms`, `rating`, `rating_count`, `total_rating`, `total_rating_count`, `aggregated_rating`, `aggregated_rating_count`, `summary`, `storyline`, `has_summary`, `has_storyline`, `parent_game`, `version_parent`, `version_title`, `collection`, `collections`, `franchise`, `franchises`, `url`, `fetched_at`, `broad_candidate_for_archetype_annotation`, `thematic_fit_score`, `candidate_reason`, `excluded_by_type_or_category`, `type_exclusion_reason`, `visibility_count_score`, `source_block`, `source_pool`, `original_release_year_num`

### IGDB annotated master

`igdb_id`, `name`, `slug`, `original_release_date`, `original_release_year`, `decade`, `category`, `game_type`, `status`, `genres`, `themes`, `game_modes`, `player_perspectives`, `platforms`, `rating`, `rating_count`, `total_rating`, `total_rating_count`, `aggregated_rating`, `aggregated_rating_count`, `summary`, `storyline`, `has_summary`, `has_storyline`, `parent_game`, `version_parent`, `version_title`, `collection`, `collections`, `franchise`, `franchises`, `url`, `fetched_at`, `broad_candidate_for_archetype_annotation`, `thematic_fit_score`, `candidate_reason`, `excluded_by_type_or_category`, `type_exclusion_reason`, `visibility_count_score`, `source_block`, `source_pool`, `original_release_year_num`, `igdb_name`, `igdb_title_norm`, `game`, `steam_appid_from_external`, `external_name`, `external_url`, `external_source_name`, `selection_rank`, `appid`, `name_steam_external`, `total_ratings_pos_neg`, `positive_ratio`, `steamspy_owners`, `v005_split`, `v005_model`, `llm6_model_used`, `corpus_label_12`, `is_core_strict_12`, `is_core_broad_12`, `is_core_maybe_12`, `is_review_pool_12`, `is_missing_llm_result`, `llm6_has_clear_main_protagonist`, `llm6_protagonist_name`, `llm6_protagonist_type`, `llm6_protagonist_confidence_0_3`, `primary_archetype_12`, `secondary_archetype_12`, `tertiary_archetype_12`, `primary_archetype_12_is_valid`, `original_shadow_antihero_present`, `original_primary_was_shadow_antihero`, `llm6_shadow_load_0_3`, `shadow_load_category`, `archetype_12_correction_method`, `llm6_primary_archetype`, `llm6_secondary_archetype`, `llm6_tertiary_archetype`, `llm6_archetype_confidence_0_3`, `llm6_archetype_suitability_0_3`, `llm6_player_projection_0_3`, `llm6_narrative_complexity_0_3`, `llm6_suggested_include_in_final_corpus`, `llm6_needs_manual_review`, `needs_manual_review_12`, `llm6_evidence_basis`, `llm6_exclusion_reason`, `llm6_note`, `rank_bin_5000`, `available_terms_for_later_inspection`, `control_protagonist`, `llm6_custom_id`, `llm6_split_label`, `llm6_part_no`, `llm6_source_output_file`, `steam_name`, `steam_title_norm`, `steam_primary_archetype_12_like`, `steam_secondary_archetype_12_like`, `steam_tertiary_archetype_12_like`, `steam_protagonist_like`, `steam_has_any_llm_columns`, `steam_has_valid_12_primary`, `steam_has_protagonist_name_like`, `steam_has_usable_llm_annotation`, `_steam_rank`, `_steam_rating_count`, `external_steam_matched`, `external_steam_llm_matched`, `title_fallback_matched`, `title_match_appid`, `title_match_steam_name`, `title_match_primary_archetype`, `title_match_secondary_archetype`, `title_match_tertiary_archetype`, `title_match_protagonist`, `title_match_has_usable_llm_annotation`, `already_has_steam_llm_annotation_external`, `already_has_steam_llm_annotation_title_fallback`, `already_has_any_steam_llm_annotation`, `match_method`

### Simplified full annotated master

`jméno hry`, `rok vydání`, `jméno protagonisty`, `archetyp 1`, `archetyp 2`, `archetyp 3`, `věrohodnost`

### Protagonist-only export, original

`jméno hry`, `rok vydání`, `jméno protagonisty`, `archetyp 1`, `archetyp 2`, `archetyp 3`, `věrohodnost`

### Analytical rows with visibility weights

`row_id`, `game`, `year`, `protagonist`, `arch1`, `arch2`, `arch3`, `confidence`, `confidence_0_1`, `reviews`, `visibility_available`, `visibility_match_method`, `weight_equal`, `weight_raw_reviews`, `weight_raw_cap_p99`, `weight_sqrt_reviews`, `weight_log_reviews`, `weight_log_cap_p99`, `weight_blend_equal_log`, `weight_tiered_reviews`
