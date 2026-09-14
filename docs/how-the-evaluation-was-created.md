# How the dataset and evaluation were created

[Back to the overview](../README.md) · [Data catalogue](data-catalogue.md) · [Recorded run timeline](run-timeline.md)

This page describes recovered code and recorded outputs, together with the author-described participant procedure. It distinguishes downloading metadata, constructing candidates, generating pre-codes, harmonizing labels, and comparing them with participant selections. These are different operations.

## 1. Downloading Steam and SteamSpy data

The recovered bulk-first collector first obtains the Steam application catalogue through `IStoreService/GetAppList/v1`, with an `ISteamApps/GetAppList/v2` fallback implemented when a Steam API key is unavailable. The archived catalogue records **IStoreService/GetAppList** as its source and **2026-06-20T18:38:37.448689+00:00** as its fetch timestamp. It contains **171,570 application IDs**.

The collector separately downloads paginated SteamSpy `request=all` data and tag/genre query results, caches the JSON responses, and writes CSV tables. The recovered all-snapshot contains **82,251 application IDs**; the merged catalogue contains **177,809**. These counts describe different retained files and must not be added together. The wider collection includes games outside the final analytical sample.

The code merges records by Steam application ID, retains review counts and metadata, scores candidate relevance, and supports optional Steam Store `appdetails` enrichment of selected candidates. The existence of this option does not mean every title received an individual detail request. Both cached responses and tabular outputs are archived.

Sources implemented in the collector:

- Steam catalogue: `https://api.steampowered.com/IStoreService/GetAppList/v1/`
- SteamSpy: `https://steamspy.com/api.php`
- Optional store details: `https://store.steampowered.com/api/appdetails`

The recovered broad review-filtered pool has **5,089 games**. The later large batch selection contains **50,000 games** and is a separate processing stage, not that 5,089-game pool expanded by participant annotations.

The [original collector](../data/recovered/DataSteam/F1.py), refinement scripts and complete outputs are linked in the [file index](recovered-file-index.md). The collector is stored under its byte-identical `F1.py` alias; the manifest also records its descriptive original filename, `steam_bulk_catalog_builder_csv.py`. Original defaults are preserved. Rerunning a live API today will produce a new snapshot, not the historical one.

## 2. Downloading the IGDB historical layer

The IGDB collectors use the v4 `games` endpoint, authenticated through Twitch client credentials supplied as environment variables. They query by `first_release_date`, paginate results, and retain fields describing identity, release timing, game type, genres, themes, modes, perspectives, summary and storyline. Credentials are not included in this repository.

The pre-2005 v002 script downloads release years **1970–2004**; the post-2004 v001 script downloads **2005–2026**. In v002, game-type exclusions are applied locally rather than restricting the initial API query to category zero. The older v001 experiment is also retained and is not the selected historical acquisition branch.

| Recorded acquisition stage | Raw records | Broad candidates | Summary timestamp |
|---|---:|---:|---|
| 1970–2004, v002 | 42,533 | 29,054 | 2026-06-22 01:54:44 |
| 2005–2026, v001 | 236,084 | 177,446 | 2026-06-22 02:15:20 |
| Merged, all acquired years | 278,617 | 206,500 | 2026-06-22 02:27:40 |
| Retained through 2025 | 264,491 | 194,354 | Same merge summary |

These summary timestamps have **no timezone offset in the source**. They are reproduced as recorded, not silently labelled UTC. The raw tables retain future-year and low-priority records; filtering does not remove them from the archive.

The local candidate rule combines genre/theme matches, text availability, single-player metadata, perspective availability and type exclusions. For example, v002 adds 2 for a positive genre, 1 for a positive theme, 1 for sufficiently long summary/storyline text, 1 for single-player metadata and 0.5 for a perspective, then applies penalties for low-priority genres and excluded types. Broad candidates require score ≥1 and no type exclusion. Exact keyword lists and thresholds are in the archived code.

See the [pre-2005 collector](../data/recovered/DataSteam/igdb_build_pre2005_candidate_catalog_v002.py), [post-2004 collector](../data/recovered/DataSteam/igdb_build_post2004_candidate_catalog_v001.py) and [merge script](../data/recovered/DataSteam/igdb_merge_candidate_catalogs_v001.py).

## 3. Linking IGDB games to existing Steam annotations

The overlap script queries IGDB `external_games` and first matches an IGDB game's Steam application ID to the Steam coding dataset. It then uses an exact normalized-title fallback, excluding ambiguous Steam title matches from that fallback. Match methods remain recorded in the output.

The recovered overlap summary reports **27,785 ID-linked annotated records**, **3,100 title-fallback matches**, and **163,469 records needing further annotation**, from 194,354 IGDB candidates. The later metadata-annotation summary preserves 44,180 pre-existing primary labels; that later number is not the same stage as the 30,885 initial overlap matches. Intermediate changes between those stages remain incompletely documented.

See the [linking script](../data/recovered/DataSteam/igdb_check_steam_llm_overlap_v001.py) and its archived match tables.

## 4. LLM-assisted pre-coding: prompts, inputs, models and time

The Steam batch workflow submits compact structured inputs to the Responses API through batch jobs. Inputs include application ID, game title, review statistics, selected metadata terms and an optional control protagonist. It does **not** uniformly supply a complete biography, plot and character arc.

Prompts request structured protagonist and ranked-archetype outputs, confidence and brief rationales. The [prompt index](../prompts/index.json) links six recovered prompt versions; [original preparation code](../archive/code/) preserves input construction and JSON schemas. Literal strings and unevaluated template expressions are distinguished. Actual JSONL requests preserve the fully instantiated input sent in the recorded runs.

| Workflow | Request alias | Recorded model snapshot | Recorded processing time (UTC) |
|---|---|---|---|
| v005 top 1,000 | `gpt-5.5` | `gpt-5.5-2026-04-23` | 20 June 2026, 23:18:53–23:24:50 |
| v005 remaining batch | `gpt-5.4-mini` | `gpt-5.4-mini-2026-03-17` | Created 20 June 2026, 23:19:00; recorded status **failed** |
| v006 remaining games, ten parts | `gpt-5.4-mini` | `gpt-5.4-mini-2026-03-17` | 21 June 2026, earliest creation 00:08:37; latest completion 13:49:08 |

The last interval is the span of separately scheduled jobs, not continuous inference time. A model snapshot date is not the date when the study ran. Detailed job timestamps and statuses are in the [run timeline](run-timeline.md). Failed and earlier pilot stages are retained as historical records; their presence does not establish use in the final analysis.

The recovered final Steam summary reports **49,979 available results out of 50,000 selected games**, with **21 missing results**. Original requests, returned outputs, compact/expanded extraction tables, manifests and collection scripts are included, including the remaining-game parts rather than only the top 1,000.

## 5. Harmonization and the IGDB metadata branch

Some original Steam prompts permit `Shadow/Antihero` in addition to the twelve-category framework. The subsequent harmonization script retains original labels and moves a valid secondary or tertiary category into the primary position when the original primary is `Shadow/Antihero`. The summary records **2,504 original primary Shadow/Antihero cases**, **2,451 reassigned** and **53 unresolved**. A harmonized label is not the unmodified model output.

The recovered IGDB wrapper uses regular expressions and explicit title mappings to fill missing labels, while preserving existing primary annotations. Its summary reports **147,088 filled rows** and **44,180 preserved annotations**. The identifier `metadata_agent_v001_gpt55_schema_compatible_fast_extract_v003` names that processing workflow; it is not evidence of an LLM request for every IGDB row or a verified model snapshot.

The wrapper and specification are archived, as are the full updated master, the annotation delta and simplified exports. Its imported base module, `annotate_igdb_archetypes_agent_v001.py`, has not been recovered. No exact execution timestamp for this step has been established. File modification dates are not substituted for missing execution logs.

## 6. Analytical exports and counts

The protagonist-only export contains **90,388 rows**, including one row without a game title. The visibility-weight export contains **90,387 non-empty-title protagonist-level records**. These represent **90,180 distinct title–year combinations** and **89,043 distinct exact title strings**. Repeated names across release years are not automatically the same game identity.

Both original exports are preserved. [The count reconciliation](corpus-counts.md) and its reproducible table explain the blank-title exclusion. The original half-decade count export has a total of 90,181 because it includes that blank-title record in 2020; the corrected table has 90,180. Original files are never silently overwritten with corrected counts.

The archive establishes the contents of these exports. It does not yet establish every transformation linking the 194,354-candidate master to the analytical subset. It also does not certify that every archived plotting variant is the final manuscript figure.

## 7. Participant annotation and filtering

Participants used a web interface showing a game title and protagonist or player role, with archetype definitions available. They could select up to three ranked archetypes or skip an item. Computational suggestions were not displayed. The interface did not supply the metadata records used for pre-coding, so human and computational inputs were not held constant.

The manuscript describes 250 most-reviewed Steam games plus 150 manually selected games. The final 150-game list and its overlap with the Steam selection have not been reconstructed. The recovered demonstration has 362 stored records and runtime code that displays 337 entries; those are not interchangeable with game counts or a verified final stimulus inventory.

The author reports that game design students were invited through the school's Discord server and participation was voluntary. The author also reports excluding affected sessions with at least five consecutive responses selecting the same archetype, with intervals below one second between successive responses. Skipping alone was not an exclusion criterion. These details were clarified on 14 September 2026; the final filtering implementation and final participant export have not been recovered for independent verification.

The [archived interface](../annotation-interface/) is an offline demonstration with collection disabled. Participant-level exports and participant identifiers are not part of the game-data release. The public literature comparison distinguishes published source terminology from this study's proposed twelve-category mappings.

## Evidence boundary

This is an archive of recovered research materials with reproducible integrity checks and selected descriptive outputs. Missing logs, missing code and unresolved stage mappings are identified explicitly. Available materials are not presented as a fully reconstructed end-to-end pipeline. For the main historical findings and their limits, see [results](results.md).
