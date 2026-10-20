# Same-name search subjects and hand-exile riders

Test of Talents and The End extend the existing same-name search with a draw for
each card exiled from the searched player's hand. The original spell/permanent
name and controller use the native target or its last known information. Failing
to counter an uncounterable spell does not prevent the subsequent search.

Necromentia uses the existing chosen-name search and creates one Zombie for each
hand card found. The follow-up uses native token creation, including replacement
ordering, recipient ownership, and paused continuation. Library and graveyard
cards do not increase the hand-only count. The End's cost reduction additionally
uses a narrow normalization of “your life total is 5 or less” to the existing
typed life comparison.

Lobotomy and Shimian Specter reuse native hand reveal and card selection before
the same-name search. The selected card supplies the name and its hand supplies
the searched player. Lobotomy may choose a nonbasic land; Shimian requires a
nonland card. With no eligible chosen card, the dependent search is skipped.
Search quality still permits finding fewer cards, including with “all” wording
(CR 701.23b). Hidden search options remain private to the searcher.

The shared native search preserves search prohibitions, library-depth limits,
Opposition Agent behavior, shuffling, and exact saved continuations. Draws use
the native replacement-aware draw path. Canonical gameplay tests cover all five
cards, native counters and uncounterable spells, normal/reduced costs, a stolen
permanent's controller, combat damage, fail-to-find, empty hands, nonbasic lands,
private options, native dredge, token replacement ordering, replay, and fresh
process saves during hand selection, search selection, and token replacement.
