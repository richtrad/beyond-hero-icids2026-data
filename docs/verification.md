# Verification — 14 September 2026

- Recovered-file SHA-256 checks pass. JSON files parse successfully. The four comparison cases link to application IDs and request IDs in the original batch output.
- The original output model identifier for these cases is `gpt-5.5-2026-04-23`.
- The local annotation interface loads and presents **337 displayed entries** from **362 stored candidate records**, after the preserved runtime grouping/ordering logic.
- A browser test selected Hero first and Caregiver second, enabled confirmation, advanced to the next character and displayed the local-save message. This created one synthetic browser-local demo response, not a study observation or an exported dataset record.
- The endpoint is empty. Same-origin connection restrictions are present in the demo HTML. The original study backend is not called.
- The comparison workbook was exported and visually inspected. The repository also provides plain UTF-8 CSV, JSON and Markdown.

These initial interface/comparison checks do not establish the correctness of all original annotations or a historical deployment reconstruction.

## Expanded game-data release — 14 September 2026

- 582 recovered source files are mapped to 487 unique archived files; original aliases and byte-level SHA-256 checksums are recorded in `provenance/data-manifest.json`.
- Original bytes were checked after compression during import. `python tools/verify_release.py --full` repeats archive and decompressed-byte checks offline.
- Row counts for the twelve principal CSV exports were parsed directly from the archived files, including compressed masters.
- The non-empty-title protagonist export and visibility export contain the same `(title, year, protagonist)` identity sets. The separate corrected count table has 90,180 title–year combinations and 35,652 in 2020–2024.
- Overview figures were generated from the preserved aggregate CSVs and visually inspected. The raw and weighted series are explicitly distinguished.
- New documentation links, citation consistency, generated artifact hashes and corrected table totals are checked by `verify_release.py`.

Counts and file integrity are verified; annotation validity, the full raw-to-analysis transformation chain and the unavailable final participant export remain separate questions.
