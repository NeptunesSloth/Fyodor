# Adamant compositions and payment-conditioned entry

Canonical cards: Once and Future, Outmuscle, Cauldron's Gift, Sundering Stroke,
and Primeval Spawn. Oracle fixture preserves mana value, colors, keywords and
printed text; official Adamant and Primeval Spawn rulings were
checked through Scryfall's WotC ruling records.

The Adamant parser composes native target/effect primitives. Once and Future
retains both announced distinct graveyard groups. Outmuscle grants indestructible
after fighting; state-based actions follow the entire spell. Cauldron's Gift's
mill is compulsory when BBB was spent, and its subsequent resolution-time
creature choice permits declining without skipping the mill. Sundering Stroke
retains mandatory announced division even if seven red mana will be spent;
only its resolution-time damage amount changes. Native actual-color payment
conditions mean copies do not inherit mana spent on the original spell.

Primeval Spawn uses an own entry replacement after as-enter copying and
prospective ability suppression. A separate exile diversion goes directly from
the current zone to exile, never through the battlefield. A copied token recipe
is checked before token creation, against prospective ability suppression. The
current spell object's payment record is required; a former cast after blinking
cannot authorize a new object. Unknown manual-cast payment produces an explicit
manual instruction rather than guessing that mana was paid.

Validation: 171 unique cases pass: 37 canonical gameplay/coverage cases and
134 existing entry-payment, token-entry-choice, entry-cost and divided-damage
regressions. The combined run passed 170; its one sandbox-manual-move test was
corrected to use actual opponent Swords to Plowshares, and passed in isolation.
That case verifies the native ten-card exile, saved budget choice and declining
without moving the cards back. Paid Clone, Double Major, Quasiduplicate, Humility
and Dress Down cases all pass. Freshly milled Walking Ballista survives its
additional entry counter; Doubling Season and Grafdigger's Cage use native entry
processing. Sundering Stroke copies preserve their announced division while the
original alone receives its actual seven-red-mana branch. Ruff and diff checks
pass. No inventory or individual type-check was run by this agent.
