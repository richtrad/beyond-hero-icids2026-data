# IGDB × Steam LLM overlap v001

This folder estimates which IGDB master-catalog games already have Steam-derived
LLM protagonist/archetype annotations.

## Methods

1. High confidence: IGDB `external_games` Steam appid -> Steam `appid`.
2. Lower confidence fallback: exact normalized title match, excluding ambiguous Steam normalized titles.

## Summary

- IGDB broad analysis rows: 194354
- Steam rows: 50000
- External Steam appid links: 103454
- Already annotated, external high confidence: 27785
- Already annotated, title fallback lower confidence: 3100
- Already annotated, any method: 30885
- Needs LLM annotation: 163469

## Recommended interpretation

Use the external high-confidence count as conservative.
Use the combined count as an upper estimate, because title fallback may include false positives.
