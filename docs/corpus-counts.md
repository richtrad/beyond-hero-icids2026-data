# Corpus count reconciliation

The counts refer to different units. Identical names in different years can identify different games, versions or releases. A title string is not a globally unique game identifier.

| Unit | Count |
|---|---:|
| Original protagonist-only rows | 90,388 |
| Rows with a non-empty game title | 90,387 |
| Distinct non-empty title strings | 89,043 |
| Distinct non-empty title–year combinations | 90,180 |

The original half-decade table totals 90,181 and includes one blank-title record from 2020. Excluding that record changes 2020–2024 from 35,653 to **35,652** and the total to **90,180**. The visibility export already excludes the blank-title row. The non-empty `(title, year, protagonist)` identity sets match between these two exports. This check does not establish agreement of every metadata or annotation field.

| Release period | Title–year combinations |
|---|---:|
| 1970--1974 | 15 |
| 1975--1979 | 89 |
| 1980--1984 | 1,339 |
| 1985--1989 | 1,926 |
| 1990--1994 | 2,873 |
| 1995--1999 | 3,076 |
| 2000--2004 | 3,348 |
| 2005--2009 | 4,545 |
| 2010--2014 | 6,892 |
| 2015--2019 | 20,839 |
| 2020--2024 | 35,652 |
| 2025 (partial) | 9,586 |
| **Total** | **90,180** |

Reproduce with `python tools/build_overview.py`. The [corrected CSV](../results/tables/title_year_counts_corrected.csv) is generated separately; the [original table](../data/recovered/Downloads/half_decade_game_counts_v2.csv) remains unchanged. Existing archived figure exports are preserved, not silently regenerated as if this correction had been part of their original computation.
