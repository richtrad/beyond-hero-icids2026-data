# Method and evidence boundaries

## What was recovered

The local Steam batch pipeline selected 50,000 games. Its corrected-dataset summary reports 49,979 available LLM results and 21 missing results. This is a particular stage, not the paper's complete 89,043-title corpus.

The v005 request files separate the top 1,000 games (`gpt-5.5`) from the remaining games (`gpt-5.4-mini`). The archived top-1,000 responses identify the concrete returned model as `gpt-5.5-2026-04-23`. Request model names and returned model identifiers are different provenance fields.

The compact Steam request contains an application ID, game title, review count, positive-review ratio, ownership estimate, selected metadata terms and an optional control protagonist. It is not evidence that every request supplied a full premise, protagonist biography or narrative arc. Inspect the actual requests and `row_to_game` functions.

## Original versus corrected archetypes

Some original prompts allowed `Shadow/Antihero` alongside twelve archetypes. The later twelve-category script moves a valid secondary or tertiary archetype into the primary position when the original primary is `Shadow/Antihero`. The source summary reports 2,504 original primary Shadow/Antihero cases, 2,451 reassigned cases and 53 unresolved cases.

Original LLM labels, corrected twelve-category labels and literature labels must remain separate. A corrected primary label is not the exact original LLM output.

## IGDB metadata branch

The recovered `run_annotation_fast_v003.py` extends a base Python annotation module using regular expressions and explicit title mappings. It is evidence of rule-based metadata processing, not of an LLM API call for every record. Its summary uses the identifier `metadata_agent_v001_gpt55_schema_compatible_fast_extract_v003`; that identifier is not a verified model snapshot.

The summary reports 147,088 newly filled master rows and 44,180 preserved existing primary annotations. The base module `annotate_igdb_archetypes_agent_v001.py` has not yet been located. The specification and wrapper alone cannot reproduce the entire branch. Their association with the final analytical subset remains to be traced.

## Manuscript reconciliation

The current Overleaf project was located at `https://www.overleaf.com/project/6a35a60ab7f6eca6d4a71fe4`; file `V18_icids_archetypes_fullpaper_minus1000.tex` was read on 14 September 2026 without editing. Its pre-coding section describes GPT-5.5 and structured protagonist/premise/role/arc inputs. The recovered branches above require a more specific multi-stage account if they contribute to the published corpus.

An older visibility export contains 90,387 rows. That number must not be relabelled as 89,043 titles without recovering the cleaning and deduplication step. Rows, unique titles, interface candidates, displayed characters and participant responses are distinct counts.

## Annotation interface

The recovered `characters.json` contains 362 candidate records. Runtime code filters and groups these records, reorders prominent characters and can add a modern Kratos record. Consequently, 362 is not a count of displayed stimuli, participants or unique games. The original interface also contains internal suggested labels; these are not automatically independent source-defined archetypes.

The local demo replaces `config.js` with an empty collection endpoint, isolates local-storage keys and adds a content-security policy allowing only same-origin connections. The visible demo notice identifies this change. Original hashes and modified-copy hashes are recorded in the manifest.

## What this supplement does not yet establish

It does not establish full-corpus reproducibility, independent model validation, participant recruitment, filtering thresholds or inter-rater reliability. These require the relevant original artifacts. No missing prompt, recruitment detail, source label or model version is reconstructed and presented as historical fact.
