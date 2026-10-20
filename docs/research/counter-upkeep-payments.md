# Counter-sized upkeep payments

Canonical Oracle fixtures cover Primordial Ooze, Rogue Skycaptain, Phantasmal
Sphere, Cyclone, and Delaying Shield. Their upkeep instructions compose native
counter placement/removal, optional payments, conditional effects, damage,
sacrifice, and control choices. Payment costs use the existing replacement-aware
payment pipeline and support manual mana activation while paying.

The current counter quantity is captured when the payment begins, after the
preceding counter placement and its replacements. Primordial Ooze's following X
damage reads that captured value. Zero-cost payments remain optional because
choosing not to pay can still tap, sacrifice, or transfer control of the source.
Native object references prevent a departed source from mutating its new
incarnation. Cyclone deals damage only after successful payment.

Delaying Shield removes counters first and uses the actual removed count.
Every removed counter creates its own optional {1}{W} payment and, if unpaid,
its own life-loss event. A lazy descriptor keeps one pending iteration and the
original tail, preserving context across payment and replacement choices. It
never expands the count into an effect list or aggregates distinct life losses.

Very long mandatory processing uses the established native Continue-resolving
checkpoint pattern already used by card-copy and mill processes. It preserves
remaining work in the save and grants no priority. This respects the shared
transaction safeguard without imposing a counter limit or widening it globally.
Tests cover 1,005 counters, exact remaining work after cold load, separate Vilis
triggers, optional zero payments, paid and unpaid branches, current replacement
counts, source departure, actual mana activation, and replay.

Large computed payments also split oversized negative plain-pool deltas into
native table-action chunks. Source taps, sacrifices, unit changes, and payment
attribution are committed once. Actual 1,006-mana upkeep payments are verified
both from a plain pool and with a real Sol Ring contribution.
