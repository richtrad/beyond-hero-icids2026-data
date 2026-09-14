# Comparing model labels with published character interpretations

The unit is a particular game/version and character or player role. Record the scope of the original model output as well as the scope of the cited source.

Keep these columns separate:

- `llm_primary_original`, `llm_secondary_original`, `llm_tertiary_original`: exact decoded recorded output, before correction.
- `primary_12`: primary label after the archived twelve-category correction.
- `source_archetype_original`: the label explicitly used in the cited source, in its terminology.
- `mapped_archetype_12`: an optional author interpretation, never a quotation from the source.
- `citation`, `source_locator`, `source_url`: bibliographic identification and exact supporting location.
- `comparison_status`, `scope_note`: whether category systems and game versions are comparable.

The initial four-case table uses Freire-Sánchez and Vidal-Mestre (2024), who explicitly analyze the *padre circunstancial* figure. This is not the same label system as the twelve-category scheme. The possible Caregiver connection is documented as interpretation, and no exact agreement score is calculated.

The source covers The Last of Us (2013), while the recovered Steam model record covers The Last of Us Part I. That version difference is exposed. In two cases the recorded protagonist field contains the game title; the character named by the literature must not silently replace that raw model value.

The 362-record `interface_source_queue.json` preserves internal suggestions and source leads from the interface snapshot. Its links have not been verified as explicit archetype assignments. A wiki biography, a Steam description or a Google search URL is not independent archetype ground truth. Missing comparisons remain unfilled.

This literature selection was made during camera-ready preparation after the original model labels were available. It is an illustrative source comparison, not a blind or representative validation sample.
