# Payments offered to any player

Authority: Comprehensive Rules effective 2026-09-25, CR 101.4 / 101.4b (APNAP
choices), 118.3 and 118.12a (whole optional costs and “unless”), 605.3a (mana
abilities while asked to pay), 608.2b/c (target legality and ordered instructions),
and 611.2c (the objects affected by continuous effects).

Official rulings for Soul Strings, Nakaya Shade, Wild Might, and Rhystic Shield
say every player gets the option to pay. Rhystic Shield explicitly specifies the
current player first, then turn order. Source, date, Oracle IDs, and Wizards
rulings mirrored by Scryfall are recorded in
[research/shared_unless_payments_rulings.json](research/shared_unless_payments_rulings.json).

The grammar reuses `each_may` and ordinary optional payments for mana/life costs
with a shared verdict. The continuation remains flat so normal pronoun binding
preserves earlier targets and affected groups. Bindings receive the normal spell
prefix. Costs sized by cast X are determined for the resolution. A leading
“Unless any player pays …” gates the entire following instruction, including the
tutor and shuffle. Mana payment prompts permit the payer's mana abilities;
players without resources automatically decline. No new state fields.

27 focused scenarios and 661 selected regression tests pass (overlap). Gameplay
checks cover all-player choices after an earlier payment, X=0, tapping mana,
unauthorized activation rejection without state changes, first and conditional
pumps, Icy Prison's real ETB exile and leave return, one/all illegal targets, source
leave/return, and leading tutor instructions. Gameplay checks include replay and
save/load. Ruff, mypy (349 files), and whitespace checks pass.

The inventory promotes exactly Rhystic Tutor, Soul Strings, Icy Prison, Wild Might,
Rhystic Shield, and Nakaya Shade, with no lost FULL support:
27,662 FULL / 4,406 PARTIAL of 32,068 Commander-legal cards. Rhystic Cave and more
complex per-object or repeated shared payments still require separate support.
