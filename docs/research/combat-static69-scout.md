# Static combat queue after declaration requirements

Canonical cards and all official rulings for Akron Legionnaire, Katabatic Winds, Kemba's Legion and Flowering Lumberknot are frozen in `/tmp/combat69-static-canonical-rulings.json`.

Unregistered exact Akron leaf `backend/app/rules/combat_named_exception69.py` uses the existing native Creature selector, current controller, nonartifact predicate and literal `not_name:Akron Legionnaire` exception to impose `cant_attack`. The named exception must remain literal when the source is copied while retaining another name. No shared hook, runtime gate or admission yet.

Katabatic has no current owner in the mana lane. Current native activation prohibitions cover all abilities or nonmana abilities, not only abilities whose selected cost contains literal {T}; reusing either would over-prohibit. A reviewed activation boundary extension would be needed across explicit activations, native mana activations and availability/UI estimates, including actual selected cost metadata. Keep held for now; do not bypass with `cant_activate`.

Kemba's additional-block count currently accepts only fixed `block_extra:N:origin` native markers. A dynamic attached-Equipment count must be evaluated when blockers are declared, respect other additive block permissions, current Equipment types and attachments, and not revalidate already-declared blocks after Equipment leaves. No classification alias is sufficient.

Flowering must require a current ObjectRef pair whose partner currently has soulbond; merely being paired is insufficient. Official rulings explicitly say ability loss preserves the pair while forbidding new attacks/blocks, and unpairing after declaration does not undo combat. Existing native pairing OID state is reusable; declaration-only predicate and cold/identity/ability-loss counterexamples are required before admission.
