# Source damage values51

Pain Magnification and Tamanoa use exact canonical clauses over native damage events, selector source identity, stored event amounts and existing discard/gain-life primitives. Full canonical records and all official rulings were read from `/tmp/trigger51-source-damage-{canonical,rulings}.json`. No shared damage/event algorithm or runtime callback was added.

Pain filters each actual source/recipient damage fact at minimum3 and binds the damaged opponent as event_player. `subject=source` would instead freeze the damage source controller, so the typed all-zone source selector is essential. Native paid tests cover foreign source controllers, self-recipient exclusion, separate small damage events, repeated activations of one source, two simultaneous small creature sources, and each opponent damaged simultaneously.

Tamanoa excludes the Creature type at the current/LKI source, across all card zones. Native `to:any` aggregates damage per source/batch, preserving the total in event_amount. Paid spell, simultaneous multi-recipient damage, own damage, lethal damage to Tamanoa, foreign spell controller versus owner/caster, creature activated damage, and actual Gempalm Incinerator cycling damage from the graveyard are covered. Two actual saved-stack cold processes exercise stored amount/recipient identity.

Independent leaf semantics review by remaining_counters passed. Whole staged19 plus simultaneous-combat negative1 passed; production20 and related57 run PASS in `/tmp/trigger51-damage-values-production.log`. Admission and the authoritative exact list are recorded only after those production gates in `/tmp/trigger50-admitted-manifest.json`.
