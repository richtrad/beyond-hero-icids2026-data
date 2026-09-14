# Findings, figures and tables

[Overview](../README.md) · [Methods](how-the-evaluation-was-created.md) · [Complete data](data-catalogue.md)

The study treats archetypes as operational categories for playable protagonist functions. Its central distinction is between a fictional character and the role made available to the player, including silent avatars, customizable characters, ensembles and implicit systemic roles.

## Hero and Explorer

In the archived raw-share series, Hero falls from **40.5%** in 1980–1984 to **22.2%** in 2020–2024, while Explorer rises from **21.7%** to **31.6%**. These are shares of coded archetype weight, not percentages of players, sales, or mutually exclusive game identities. Lower relative share does not establish a lower absolute number of heroic protagonists.

![Hero, Explorer and Everyman in the raw and visibility-weighted exports](../results/figures/hero_explorer_overview.png)

The weighted export is shown separately. It does **not** reproduce every raw-share pattern: in 2020–2024 its Hero share is 18.6% and Explorer share is 17.1%. Weighting changes which games contribute most. This distinction is part of the interpretation, not an interchangeable plotting choice.

## The twelve-category picture

Everyman grows from 5.4% to 10.5% in the raw export. Other archetypes follow different trajectories. The heatmap keeps all twelve categories visible rather than reducing the corpus to a Hero-versus-Explorer contest.

![Raw shares of all twelve archetypes](../results/figures/twelve_archetypes_overview.png)

| Archetype | 1980–1984 | 2020–2024 | Change (percentage points) |
|---|---:|---:|---:|
| Innocent | 0.7% | 1.7% | +1.0 |
| Everyman/Orphan | 5.4% | 10.5% | +5.1 |
| Hero/Warrior | 40.5% | 22.2% | -18.3 |
| Caregiver/Guardian | 3.9% | 3.0% | -1.0 |
| Explorer/Seeker | 21.7% | 31.6% | +9.9 |
| Rebel/Outlaw | 1.6% | 4.0% | +2.4 |
| Lover | 0.8% | 3.9% | +3.2 |
| Creator/Artist | 4.2% | 3.9% | -0.3 |
| Jester/Trickster | 0.4% | 2.8% | +2.3 |
| Sage/Investigator | 9.4% | 7.2% | -2.1 |
| Magician/Transformer | 6.6% | 4.9% | -1.6 |
| Ruler/Leader | 4.9% | 4.4% | -0.5 |

## Protagonist form

The recovered type-profile table distinguishes a typed subset from the full corpus. Fixed-character records emphasize Hero (20.3%) and Explorer (18.0%); silent avatars emphasize Explorer (25.8%); systemic roles emphasize Ruler (33.0%) and Creator (15.6%). These values describe the recovered type-profile export and are not a human validation score.

| Protagonist type | Records in recovered typed subset | Leading archetypes |
|---|---:|---|
| Fixed character | 18,523 | Hero 20.3%; Explorer 18.0%; Everyman 13.1% |
| Silent avatar | 2,232 | Explorer 25.8%; Hero 15.4%; Everyman 14.1% |
| Systemic role | 1,744 | Ruler 33.0%; Creator 15.6%; Hero 14.4% |
| Customizable | 335 | Explorer 23.0%; Hero 22.3%; Everyman 12.4% |

[Original type-profile table](../data/recovered/Downloads/table_archetype_profiles_by_type.tex). Related type-share and within-type-change tables, PGFPlots sources, heatmaps, and annual weighting variants are included in the [file index](recovered-file-index.md).

## Interpretation and limits

“Heroic exploration” and “exploratory heroism” express the paper's interpretation of changing ranked archetypal configurations. The categories are a predefined codebook. Technological, formal and cultural causes are not isolated by this descriptive analysis. Catalogue coverage, metadata quality and computational pre-coding influence the observed distributions.

Participant comparison evaluates a selected subset and is not full-corpus validation. Broader label overlap does not establish coding validity. The literature examples in [comparison](../comparison/README.md) are explicitly separated from participant responses and computational labels.

## Reproduce the overview

Run `python tools/build_overview.py` with pandas and matplotlib installed. The two overview figures are **new renderings of archived aggregate CSV values**, restricted to 1980–2024; they do not rerun model inference or claim an independently reconstructed raw-to-figure pipeline. The original aggregate exports and plotting variants remain unchanged.

- [Raw source CSV](../data/recovered/Downloads/archetype_raw_share_by_half_decade_v2.csv)
- [Visibility-weighted source CSV](../data/recovered/Downloads/archetype_review_weighted_share_by_half_decade_v2.csv)
- [Endpoint table](../results/tables/archetype_endpoints.csv)
- [Corrected corpus counts](corpus-counts.md)
- [Full paper status](../paper/README.md)
