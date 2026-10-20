# Ichormoon Gauntlet

Canonical Oracle source: repository card database; full fixture stored in
`backend/tests/fixtures/ichormoon_counter_cards.json`.

The unsupported sentence chooses a counter on a target permanent and puts one
additional counter of that kind on it. It is equivalent to the existing native
"choose a counter ... give that permanent another counter of that kind" grammar.
The bounded normalization preserves choosing the target when the trigger is put
on the stack and choosing the counter kind when it resolves (CR 603.3d, 608.2d).
No counters means no effect; a single kind needs no decision. Counter quantity
does not change how many are added. Native counter replacement effects apply
(CR 122.6), and exact target identity prevents affecting a blinked replacement.

The already supported static planeswalker loyalty grants are unchanged. Canonical
tests verify noncreature casting, exclusion of creature spells, multiple kinds,
zero/one kind, opponent-controlled targets, Doubling Season, source departure,
target departure and replay/save equality. Existing counter-kind regressions
cover the shared machinery. No new callback or runtime primitive is introduced.
