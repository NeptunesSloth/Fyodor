# Conditional copy of a resolving spell

Sevinne’s Reclamation’s second sentence checks whether the original was cast from a
graveyard, then offers an optional copy and new targets (CR 707.10, 707.10c). The existing
chain-spell copy machinery handles the resolving spell, including its original targets.
A narrow grammar adds the cast-origin condition and optional-payment gate.

The copy retains the spell’s effects but was not cast, so the condition is false when
the copy resolves. Keeping the original target is permitted even when it has become
illegal; such a copy fails to resolve unless it has another legal target. If the original
has no legal target, none of its effects run and it does not offer a copy.

Seven focused scenarios and 81 selected regression tests passed, with replay/save-load.
Mypy (339 app files), Ruff and whitespace checks passed. The complete catalog promotes only Sevinne’s Reclamation: 27,749 FULL / 4,319 PARTIAL.
