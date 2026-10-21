# Entry counters from actual cast payments

Kalain, Reclusive Painter; Wildgrowth Archaic; Steel Exemplar; Freestrider
Commando; and Clay Champion share the native cast-payment and entry-counter
mechanisms. Canonical Oracle fixtures retain all mana costs, mana values, colors,
keywords and faces. No new mana solver or payment continuation is required.

Kalain's plural “mana from a Treasure spent to cast them” is normalized only in
the recognized entry-counter replacement count. Its mana valuation reads the
exact entering object's payment record, never the latest payment for any older
incarnation of that card. Pre-entry previews read the stack object's payment;
native spell resolution transfers that record to the permanent before applying
its entry counters. Reanimation and token copies have no old Treasure payment.
The coverage exemption is limited to a parsed replacement with a supported
`mana_from` value.

Wildgrowth's cast trigger uses an explicit event-spell color-count value. The
same value continues to mean the source's own cast payment in its existing
converge entry ability. The cast-trigger parser changes the binding only when
“it” unambiguously means the creature spell just cast; other ambiguous
mana-spent expressions remain refused. Native spell riders supply counters to
that particular spell. Source departure does not erase an existing trigger.

Steel Exemplar and Freestrider use native self-entry replacements with explicit
known-payment predicates. Colorless is not a color (CR 105.2c). Plotting spends
mana on a special action; a later free cast spends no mana unless additional
costs or taxes require it. A record whose manually paid mana is unknown never
becomes a fabricated positive entry condition: the engine records a manual
counter-adjustment note.

Clay Champion counts complete groups of identical actual mana types, using
floor(actual G/2) and floor(actual W/2). Its own entry counters and its ETB target
counter distribution reuse that generic value. The up-to-two target group is
announced before putting a counter on each selected creature for each group of
white mana, even when the amount is zero. Announced X remains independent of the
number of colored groups actually spent.

All effects retain native counter replacement ordering, counter prohibitions,
source identity, trigger targeting, spell copying, save/resume and replay.
Gameplay verification is in `tests/test_rules_entry_payment_family.py`, including
actual Kalain Treasure generation, paid/free/plotted/reanimated/token entries,
old-incarnation payment isolation, saved CR616 counter ordering, Solemnity,
Wildgrowth cast-event payment identity, countered triggers, Clay's actual two
targets and partial target illegality, and spend-as permissions.
