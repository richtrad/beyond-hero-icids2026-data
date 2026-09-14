# IGDB protagonist + 12-archetype annotation agent specification v001

## Scope
Annotate only rows that do **not** already contain a usable `primary_archetype_12`. Existing protagonist/archetype data must be treated as locked and must not be overwritten.

Input files:
- `igdb_needs_llm_annotation_v001.csv` — work queue of IGDB rows without usable Steam overlap annotation.
- `igdb_master_broad_with_steam_llm_overlap_v001.csv` — master file; used only for preserving existing rows and as a schema/style model.

## Output contract
For each newly annotated row, fill the existing columns used by the previous annotation pipeline:
- `llm6_model_used`
- `corpus_label_12`
- `is_core_strict_12`, `is_core_broad_12`, `is_core_maybe_12`, `is_review_pool_12`
- `llm6_has_clear_main_protagonist`
- `llm6_protagonist_name`
- `llm6_protagonist_type`
- `llm6_protagonist_confidence_0_3`
- `primary_archetype_12`, `secondary_archetype_12`, `tertiary_archetype_12`
- `primary_archetype_12_is_valid`
- `original_shadow_antihero_present`, `original_primary_was_shadow_antihero`
- `llm6_shadow_load_0_3`, `shadow_load_category`
- `archetype_12_correction_method`
- `llm6_primary_archetype`, `llm6_secondary_archetype`, `llm6_tertiary_archetype`
- `llm6_archetype_confidence_0_3`, `llm6_archetype_suitability_0_3`, `llm6_player_projection_0_3`, `llm6_narrative_complexity_0_3`
- `llm6_suggested_include_in_final_corpus`
- `llm6_needs_manual_review`, `needs_manual_review_12`
- `llm6_evidence_basis`, `llm6_exclusion_reason`, `llm6_note`
- `llm6_custom_id`, `llm6_split_label`, `llm6_part_no`, `llm6_source_output_file`

## Valid primary/secondary/tertiary labels
Use exactly one of these labels:
- `Innocent`
- `Everyman/Orphan`
- `Hero/Warrior`
- `Caregiver/Guardian`
- `Explorer/Seeker`
- `Rebel/Outlaw`
- `Lover`
- `Creator/Artist`
- `Jester/Trickster`
- `Sage/Investigator`
- `Magician/Transformer`
- `Ruler/Leader`
- `Not applicable`
- `Uncertain`

`primary_archetype_12_is_valid` is `True` only for the twelve real archetypes. It is `False` for `Not applicable` and `Uncertain`.

## Protagonist types
Use the same controlled values as the existing file:
- `fixed_named_single`
- `fixed_dual`
- `fixed_ensemble`
- `nonhuman_fixed_protagonist`
- `silent_fixed_protagonist`
- `fixed_role_single`
- `customizable_but_defined`
- `player_avatar_weakly_defined`
- `strategy_or_systemic_role`
- `simulator_or_management_role`
- `sports_or_racing_role`
- `no_clear_protagonist`
- `uncertain`

## Decision rules
1. If a row is an abstract game, pure board/card game, quiz, pure sport/racing title, management/simulation without a story lead, MOBA, multiplayer-only roster shooter, or strategy game with factions instead of a lead character, mark protagonist as not clear/systemic and set `primary_archetype_12 = Not applicable` unless the metadata clearly states a fixed protagonist.
2. If the metadata explicitly names a lead character, use that name and infer archetypes from the role, theme, and story function.
3. If the protagonist is a defined role but not a fixed name (e.g. Hunter, Guardian, Commander, Pokémon Trainer), use that role and mark type as `fixed_role_single` or `customizable_but_defined`.
4. If the game has multiple equally central leads, use `fixed_dual` or `fixed_ensemble` and put a concise ensemble name in `llm6_protagonist_name`.
5. If information is insufficient, use `Uncertain`, set confidence low, and set both manual-review flags to `True`.
6. Never invent a specific name when the metadata only supports a role or player avatar. Prefer a role label plus manual review over a false named protagonist.

## Confidence scale
- 3: well-known title or explicit metadata directly names the lead.
- 2: metadata strongly implies the role/protagonist but does not fully name it.
- 1: weak metadata inference from genre/title only.
- 0: unknown/uncertain.

## Evidence basis
Use:
- `metadata_inference` when derived from IGDB title/summary/storyline/genre/theme fields.
- `general_knowledge` for well-known title/franchise mappings.
- `uncertain` when the agent cannot make a reliable annotation.

## Preservation rule
Rows that already contain a valid or intentionally non-valid previous annotation (`primary_archetype_12` not empty) must be copied byte-for-byte at the semantic row level, except CSV serialization may normalize quoting.
