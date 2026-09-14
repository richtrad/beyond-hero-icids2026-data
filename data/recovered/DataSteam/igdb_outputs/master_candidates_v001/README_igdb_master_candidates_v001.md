# IGDB master candidate catalog v001

Merged candidate catalog from:

- `pre2005_candidates_v002`
- `post2004_candidates_v001`

## Important

- No LLM annotation is performed here.
- `original_release_year` comes from IGDB `first_release_date`.
- All-year files retain all fetched years.
- Analysis-year files keep only years `<= 2025`.
- Future/incomplete years are written separately to `igdb_master_excluded_after_max_year_v001.csv`.

## Row counts

- Master raw all years: 278617
- Master broad all years: 206500
- Analysis raw: 264491
- Analysis broad: 194354
- Excluded after max year: 14126

## Recommended next input for stratified candidate selection

Use:

`igdb_master_broad_analysis_years_v001.csv`

Then build a smaller stratified candidate set per decade/year before running LLM protagonist and archetype annotation.
