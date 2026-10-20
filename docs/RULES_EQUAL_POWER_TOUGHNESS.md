# Trigger filters comparing a creature's power and toughness

Authority: Comprehensive Rules effective 2026-09-25, CR 208.1 (power/toughness can
be modified), 603.2 (trigger event matching), 603.2c (one trigger per occurrence),
603.3 (trigger placement), 603.4 (intervening “if” clauses), 508.1m (attacks triggers),
and 120.6 (damage marked on a creature).

Symmetry Matrix and Master Symmetrist use a creature's current derived power and
toughness when it enters or attacks. They do not compare the printed numbers or
subtract marked damage. Their trigger filters are not intervening “if” clauses:
later stat changes do not cancel an already triggered ability. A 0/0 entering
triggers Matrix even when it immediately dies to a state-based action.

The selector suffix “with power equal to its/their toughness” adds one ordinary
selector check. Existing event snapshots, trigger handling, mana payments, and
keyword grants handle the rest. No new state fields.

20 focused tests pass, with real Oracle fixtures and replay/save-load gameplay
checks. Cases include equal/unequal entering creatures, Castle's toughness bonus,
controller filtering, paying/declining, stat changes and source departure before
resolution, multiple attackers, Orcish Oriflamme's attacking power bonus, marked
damage, and Walking Ballista entering at X=0 or X=1. 276 selected regression tests
pass (overlap), alongside Ruff, mypy (349 files), and whitespace checks.

The catalog promotes exactly Symmetry Matrix and Master Symmetrist with no lost
FULL support: 27,664 FULL / 4,404 PARTIAL of 32,068 Commander-legal cards.
