# Public name relations and linked continuations

Batch35 promotes fourteen cards through native effects: Retraced Image, Mitotic Manipulation, Spellweaver Helix, Harness the Storm, Kotose the Silent Spider, Dual Nature, Jester's Scepter, Mindreaver, Hint of Insanity, Key to the Side-Door, Pirated Copy, Yenna Redtooth Regent, Scalpelexis, and Twinning Glass.

`CastNote.names` records the public actual-as-cast names, including selected faces, before the spell leaves the stack. A face-down receipt is nameless. An older save with no names has unknown public history, not an empty set: a native typed choice explicitly restores that receipt without looking at the card's current identity. New ordinary receipts require no intervention.

Targeted matching and linked matching retain exact event/source object identity and re-evaluate current characteristics or native last-known information. Harness does not freeze names at announcement. Mindreaver retains its sacrificed source's original link namespace and checks the current linked pool when its ability resolves. Jester's cost records names made public by paying its linked-exile cost; another imprinted card cannot substitute for the card actually paid.

Kotose's original target and subsequent search finds share one native play allowance. Agent-diverted search finds remain invisible to subsequent search effects. The source-controlled duration expires permanently on control loss. Helix treats cast copies of cards differently from uncast stack copies and offers exactly one other imprinted card, including when both imprints share the triggering name.

Dual Nature records exact created-token object identities for source cleanup, while its separate nontoken-leaves trigger compares names from that event. Pirated Copy uses the existing self-or selector event semantics. Yenna consumes its actual created token reference, including copy exceptions, before its Aura rider.

Scalpelexis checks only the cards actually exiled in the latest batch. A bounded processing budget yields a native mandatory Continue decision; accepting it resumes the remaining operation. This is not an optional stop, arbitrary completion, or a game outcome. Its fresh-process regression crosses 128 cards before resuming to finish the library.

Canonical fixture: `tests/fixtures/name_relation_cards.json`. Verification: 33 cases in `tests/test_rules_name_relation_continuations.py` pass, including positive gameplay for all fourteen, replay/JSON roundtrips, and both new callbacks resumed in fresh processes. Scoped Ruff and diff checks pass.

Minamo's Meddling and Search the City remain PARTIAL. Minamo needs an authoritative public splice-name receipt preserved across relevant spell copies. Search the City needs an as-played land event even when entry is replaced/diverted, with exact selected MDFC land-face characteristics. Neither is implemented using a guess from the card's current zone or printed front face. Read-only followup design is staged at `/tmp/name-event-receipts36-plan.md`.
