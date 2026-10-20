# Creatures attacking opponents or their planeswalkers

Authority: Comprehensive Rules effective 2026-09-25, CR 102.2 (opponents), 506.3
(attackable objects), 508.1 (declaring attackers), 603.2c (one or more trigger events),
608.2c (ordered instructions), and 611.2c (affected objects fixed as the effect begins).

Roar of Resistance gives its controller a single optional payment when one or more
creatures attack. If paid, its bonus applies to creatures attacking that controller's
opponents or those opponents' planeswalkers, including creatures controlled by other
players. Creatures attacking its controller or that controller's planeswalkers do
not qualify.

The existing attacking-opponent selector gains the optional planeswalker wording.
It reads each attacking creature's current attack target and a planeswalker's current
controller; it excludes departed players and non-planeswalker card targets. Existing
optional payments and pump effects handle the ability. No new state fields.

Six focused tests pass, including the real-card FULL check, three-player combat against
players and planeswalkers, payment/decline, one trigger for multiple attackers, filtering
attacks against the controller and their walker, and its separate haste grant to creature
tokens. Gameplay checks replay and save/load. 211 selected regression tests pass
(overlap); Ruff, mypy (349 files), and whitespace checks pass.

The catalog promotes only Roar of Resistance, with no lost FULL support:
27,665 FULL / 4,403 PARTIAL of 32,068 Commander-legal cards.
