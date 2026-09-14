# Beyond the Hero

**If you use these data or research materials, we kindly ask you to cite the accompanying paper. Thank you for acknowledging the work behind this dataset.**

Radek Richtr. *Beyond the Hero: A Diachronic Study of Archetypal Shifts in Playable Protagonists Across Five Decades*. ICIDS 2026, accepted paper.

```bibtex
@inproceedings{richtr2026beyondhero,
  author    = {Richtr, Radek},
  title     = {Beyond the Hero: A Diachronic Study of Archetypal Shifts in Playable Protagonists Across Five Decades},
  booktitle = {International Conference on Interactive Digital Storytelling (ICIDS 2026)},
  year      = {2026},
  note      = {Accepted paper. Final proceedings metadata forthcoming}
}
```

[Download BibTeX](CITATION.bib) · [How the data and evaluation were created](docs/how-the-evaluation-was-created.md) · [All game data](docs/data-catalogue.md) · [Findings and figures](docs/results.md) · [Paper](paper/README.md)

## What this study asks

How have playable protagonist archetypes changed across five decades of games? A protagonist can be an authored fictional character, a silent avatar, a customizable figure, an ensemble, or an implicit role such as a ruler or creator. The study therefore distinguishes **the archetype of the character** from **the role made available to the player**.

Twelve predefined categories provide a shared vocabulary; ranked primary, secondary and tertiary labels allow multiple functions within one record. The analysis describes historical distributions within this framework. It does not classify players' personalities or identify the causes of historical change.

## From heroic exploration to exploratory heroism

In the archived raw-share series, Hero's relative share decreases while Explorer's increases. This does not mean heroic protagonists disappear: the interpretation concerns their relative prominence and their combinations with other roles.

![Hero, Explorer and Everyman across five decades, with raw and visibility-weighted views](results/figures/hero_explorer_overview.png)

| Archetype | Raw share, 1980–1984 | Raw share, 2020–2024 |
|---|---:|---:|
| Hero / Warrior | 40.5% | 22.2% |
| Explorer / Seeker | 21.7% | 31.6% |
| Everyman / Orphan | 5.4% | 10.5% |

These percentages describe shares of coded archetype weight, not player numbers or sales. The visibility-weighted view answers a different question and does not reproduce every raw trend: its 2020–2024 Hero and Explorer shares are 18.6% and 17.1%, respectively. The overview plots are reproducible renderings of preserved aggregate CSV exports, not newly inferred labels.

## More than a Hero–Explorer comparison

![All twelve archetypes in the archived raw-share export](results/figures/twelve_archetypes_overview.png)

Protagonist form also matters. In the recovered typed subset, silent avatars emphasize Explorer (25.8%), while systemic roles emphasize Ruler (33.0%) and Creator (15.6%). These patterns connect archetypal functions with the actions and positions games make playable.

The [results page](docs/results.md) includes the full twelve-category endpoint table, protagonist-type comparisons, source links and interpretation limits. Annual matrices, alternative weighting schemes, original heatmaps, PGFPlots sources and further tables are preserved in the [complete file index](docs/recovered-file-index.md).

## The data behind the study

The release includes **complete recovered game catalogues and processing outputs**, including records outside the selected analytical corpus. The archive covers 582 source files, represented by 487 distinct archived files after byte-identical duplicate detection. These contain approximately 3.04 GB of unique original material in approximately 832 MB of archive storage. Large text files use lossless gzip compression; they are not samples.

| Layer | Size | Where to start |
|---|---:|---|
| Downloaded Steam catalogue | 171,570 application IDs | [Data catalogue](docs/data-catalogue.md) |
| SteamSpy all-snapshot | 82,251 application IDs | [Data catalogue](docs/data-catalogue.md) |
| Merged Steam-side catalogue | 177,809 application IDs | [Data catalogue](docs/data-catalogue.md) |
| Downloaded IGDB catalogue, all acquired years | 278,617 records | [Data catalogue](docs/data-catalogue.md) |
| IGDB broad candidates through 2025 | 194,354 records | [Acquisition and selection](docs/how-the-evaluation-was-created.md) |
| Steam batch selection | 50,000 games; 49,979 available LLM results | [Models, prompts and times](docs/how-the-evaluation-was-created.md#4-llm-assisted-pre-coding-prompts-inputs-models-and-time) |
| Analytical visibility export | 90,387 protagonist rows | [Count reconciliation](docs/corpus-counts.md) |
| Distinct non-empty title–year combinations | 90,180 | [Corrected period table](results/tables/title_year_counts_corrected.csv) |
| Distinct exact title strings | 89,043 | [Meaning of the counts](docs/corpus-counts.md) |

The layers overlap and **must not be added together**. A title string, a title–year combination, a protagonist row and an annotation are different units. One blank-title record explains the difference between the original 90,181-combination table and the corrected 90,180 count; both the original material and the separate correction are retained.

## How the evaluation was created

The [method page](docs/how-the-evaluation-was-created.md) explains acquisition from Steam/SteamSpy and IGDB, source matching, model inputs, prompt versions, LLM batch runs, twelve-category harmonization, metadata-based coding and participant annotation.

- **Prompts and schemas:** [prompt index](prompts/index.json), original preparation scripts and instantiated batch inputs.
- **Models:** recorded Steam runs use `gpt-5.5-2026-04-23` and `gpt-5.4-mini-2026-03-17`.
- **Time:** [recorded job timeline](docs/run-timeline.md), distinguishing submission, completion, failed runs and unknown times.
- **Annotation interface:** [archived demonstration](annotation-interface/), with collection disabled.
- **Game–character–LLM–source comparison:** [cited examples](comparison/initial_comparison.md), keeping published terminology separate from proposed mappings to this codebook.

The recovered IGDB metadata branch also uses rules and explicit title mappings; not every code is a direct LLM prediction. Some intermediate transformations and the base IGDB annotation module remain missing. The final participant export has not been recovered. This release provides the available evidence without claiming complete end-to-end reproducibility or full-corpus human validation.

## Explore and verify locally

```sh
git clone https://github.com/richtrad/beyond-hero-icids2026-data.git
cd beyond-hero-icids2026-data
python tools/verify_materials.py
python tools/verify_release.py
```

To regenerate the overview figures and descriptive tables, install the packages listed in [requirements-overview.txt](requirements-overview.txt), then run `python tools/build_overview.py`. This is an offline analysis of archived files; no model calls or paid inference are launched.

To try the annotation interface, run `python -m http.server 8173 --bind 127.0.0.1` and open `http://127.0.0.1:8173/annotation-interface/`. The demo stores responses locally in the browser under a separate prefix and does not submit them to the study.

[Checksums and source aliases](provenance/data-manifest.csv) make every archive file traceable. Original game metadata retain their source attribution; the citation request above does not assign new rights to third-party content. Participant-level response exports, credentials and the original collection backend are not included.

## Full article

The complete camera-ready PDF will be added to [paper/](paper/README.md) after the manuscript revisions are finalized. The [BibTeX citation](CITATION.bib) will be updated with the DOI, pages and final proceedings details when available.
