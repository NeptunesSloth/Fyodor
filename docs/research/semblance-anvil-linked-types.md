# Semblance Anvil: linked card-type cost reduction

Implemented as a reusable static cost modifier in `backend/app/rules/cost_changes.py`. The qualifier “spells you cast that share a card type with the exiled card(s)” uses the existing `exiled_with` object-identity linkage. The existing native imprint trigger records the card; the modifier reads only linked objects still in exile.

The prospective spell and linked cards use current characteristics. Subtypes do not qualify. A modifier applies once if any card type overlaps, even when multiple types or multiple cards were imprinted through a doubled trigger. Separate Anvils each contribute their reduction. The ordinary cost pipeline preserves colored costs and floors the generic component at zero.

The source controller determines “you”; neither source ownership nor ownership of the exiled card changes that restriction. Source blink creates a new link identity. A linked card leaving exile and returning likewise becomes a new, unlinked object.

Canonical Oracle fixtures and thirteen gameplay/cost regressions in `backend/tests/test_rules_semblance_anvil.py` cover actual casting and imprint decisions, decline, source/controller changes, both identity boundaries, multiple sources, multiple card types, current type-changing effects in exile, and split-card characteristics. Scenarios verify deterministic history replay and JSON save/load. No casting/payment implementation changes were needed.
