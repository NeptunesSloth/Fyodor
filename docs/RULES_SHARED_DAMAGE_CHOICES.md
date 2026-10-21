# Shared optional damage choices

Rules authority: Comprehensive Rules effective 2026-09-25, CR 101.4 and 101.4b
(APNAP choices, then simultaneous actions), 118.12 and 118.12a (optional costs and
“unless”), 608.2c/h (ordered instructions and last known information), 400.7 (new
objects), and 605.3a (mana ability activation windows).

Official Vexing Devil rulings explicitly give every opponent a choice in turn order,
even when an earlier opponent accepts. Damage prevention does not undo acceptance,
and players cannot act between those choices and sacrificing the Devil. The Wizards
rulings mirrored by Scryfall are recorded with source and date in
[research/shared_damage_choices_rulings.json](research/shared_damage_choices_rulings.json).

`shared_damage.py` parses the complete shared-damage instruction and conditional
continuation. All eligible players choose before any damage is dealt. Ordinary damage
primitives apply simultaneous damage, prevention, and source information; the aggregate
choice gates the continuation. Existing JSON decision contexts preserve pending choices
through saves and replays. No new state fields or mana-payment window are introduced.

Real-card fixtures cover Browbeat, Book Burning, Breaking Point, Vexing Devil, and
Longhorn Firebeast. 26 focused tests exercise zero, one, and multiple acceptances,
all-player versus opponent-only eligibility, active-player ordering, prevented damage,
prohibited mana activation during choices, source departure and return, nonregenerable
destruction, and unknown-grammar refusal. Gameplay tests check replay and save/load.
211 selected regression tests pass, as do Ruff, mypy (349 files), and whitespace checks.

The catalog comparison promotes exactly these five cards, with no loss of FULL support:
27,656 FULL / 4,412 PARTIAL of 32,068 Commander-legal cards. Remaining partial cards
still require implementation and verification.
