# Beyond the Hero — ICIDS 2026 research materials

Working supplement for paper 17, **Beyond the Hero: A Diachronic Study of Archetypal Shifts in Playable Protagonists Across Five Decades**.

Prepared 14 September 2026. This is a local working repository, not a released supplement. The recovered materials include different stages of the study. Their relationship to the final 89,043-title corpus is still being reconciled.

| Materials | Location | Status |
|---|---|---|
| Recovered batch prompts, input construction and schemas | `prompts/` | Extracted from original scripts; source filenames and hashes recorded |
| Original preparation and correction code | `archive/code/` | Preserved, not executed by this supplement |
| Recorded top-1,000 LLM requests and responses | `archive/batch/` | Original request and output files |
| Copy of the annotation wheel | `annotation-interface/` | Local demonstration; collection endpoint disabled |
| Game–character–LLM–literature comparison | `comparison/` | Initial cited cases and a queue of recovered interface records |
| Provenance and remaining gaps | `provenance/`, `docs/` | Explicitly distinguish evidence, mappings and unknowns |

Read [method and evidence boundaries](docs/method-and-evidence.md) and [comparison rules](comparison/README.md) before using these materials.

## Run the archived wheel

From this directory, run `python -m http.server 8173 --bind 127.0.0.1` and open `http://127.0.0.1:8173/annotation-interface/`.

The demonstration stores responses only in the browser under a separate demo prefix. It does not submit annotations to the original study. The recovered input list and runtime ordering code are retained; this does not establish that this exact snapshot was used for every participant.

## Verify

Run `python tools/verify_materials.py`. Verification checks archived-file hashes, JSON validity and the link between cited examples and recorded LLM outputs. It does not rerun paid model inference or certify the paper's full corpus.

## Remaining work before release

1. Locate the original interactive annotation tasks and any prompts not present in the batch scripts.
2. Recover the missing base IGDB annotation script and trace the final 89,043 titles to their annotation origins.
3. Confirm the study-era annotation-interface version and separate the displayed set from stored candidate records.
4. Extend the literature comparison beyond the initial cases. Preserve literature labels in their own terminology.
5. Reconcile the supplement with the current Overleaf manuscript, then assign a release version and public URL.

No participant response exports, credentials or active collection configuration are included.
