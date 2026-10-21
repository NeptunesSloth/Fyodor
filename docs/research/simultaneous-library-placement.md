# Simultaneous owner top/bottom placement

Aetherspouts and Tolarian Contempt use one native `to_library(place='choice')` instruction across all affected creatures. Aetherspouts collects the attacking creatures as it resolves. Contempt retains its real enters trigger and rejection counters, then expands its end-step optional target group once per opponent; a strictly opt-in aggregate effect runs once across those legal groups instead of separately moving each target.

Aetherspouts' official WotC rulings of 2014-07-18 require each owner to make all their choices in APNAP order, followed by private ordering of any multiple cards put on the same top/bottom. The runtime therefore has three persisted phases:

1. Each owner selects the creatures going on top; their remaining creatures go on the bottom. Public placement notes let subsequent owners know earlier choices, without revealing private pile order.
2. Commander replacement choices and each owner's private physical-card ordering are collected. No creature has moved yet. Merged commanders' noncommander parts retain their selected library destination; tokens need no physical-card ordering.
3. One Move commits all surviving original objects. Optional `library_positions` and `library_order` metadata arrange top/bottom piles inside that event before tracking observes it. The fields default to `None`, preserving existing Move behavior. The handler admits ordering only for moved roots and their actual merged components, never unrelated library cards.

The saved queue pins each original root's exact object identity and source zone. An object that leaves and reenters during a saved choice is excluded; its new incarnation is never substituted. Existing single-object owner-choice effects continue through their original resume path.

Native zone and commander replacements still run. Only after simple command/exile replacements have actually been prepared, and only for these opt-in library moves without deferred choices, links, counters, madness or riders, a narrow replacement branch returns the prepared routes in one Move. This preserves simultaneous tracking for actual unearth and commander redirects, including merged-commanders' remaining parts. Other replacement cases retain the existing native path.

The serialized move/order metadata is internal history, not a client payload. Tests exercise actual REST, WebSocket and history endpoints: nonowners receive a waiting decision while an order is pending, no order metadata is sent, and resulting hidden library identities/order stay concealed. Public movement logs sort multiple names independently of their private order.

Canonical gameplay covers APNAP across three owners under one attacking controller, mixed top/bottom ordering, simultaneous batches, optional zero targets, rejection counters and target-per-opponent groups, nonattackers, untargeted hexproof/uncounterable Carnage Tyrant, real Krenko tokens, actual Gemrazer merged with commander Krenko, command-zone acceptance/decline, actual Dregscape Zombie unearth, and exact-object changes. Every continuation phase also resumes from a saved state in a fresh Python process and replays deterministically.

Validation: 169 selected existing/new tests passed together, plus the two subsequently added canonical optional-zero/untargeted cases (171 distinct cases total). Ruff passes the affected modules. Full inventory and full type checks are coordinated separately by the parent agent.
