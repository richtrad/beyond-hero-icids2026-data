# Method and evidence boundaries

The expanded account is now [How the dataset and evaluation were created](how-the-evaluation-was-created.md). It documents the recovered acquisition scripts, inputs, model snapshots, run times, harmonization and participant procedure.

The [data catalogue](data-catalogue.md) contains complete recovered catalogues and analytical exports. The [count reconciliation](corpus-counts.md) resolves the units behind 89,043 distinct title strings, 90,180 title–year combinations and 90,387 non-empty-title protagonist rows.

Important remaining boundaries:

- The complete transformation chain from the IGDB candidate master to every analytical row is not yet reconstructed.
- The metadata wrapper's base annotation module is missing; its workflow identifier is not a verified LLM model snapshot.
- The final participant export, filtering implementation and final 150-game selection have not been recovered. Participant procedures clarified by the author are labelled as such.
- The archived interface revision does not establish the exact version seen by every participant.
- Published source labels, original model outputs and twelve-category harmonizations remain separate.
- Archive integrity and descriptive count checks do not establish the validity of every annotation.
