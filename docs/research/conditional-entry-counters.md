# Conditional entry counters

Canonical Oracle fixtures: `backend/tests/fixtures/conditional_entry_counter_cards.json`.
Full-card targets: Recommission, Heroic Return, Teferi's Time Twist and Semester's End.

The existing return-card instruction already supports entering counters and their
replacement pipeline. Conditional counters must examine entering characteristics
(CR 614.12), rather than checking the card in the graveyard. A returned Sol Ring
enters with a counter while March of the Machines makes it a creature; an ordinary
noncreature artifact receives none. Metadata now travels with the native entry
through entry choices and is evaluated in the battlefield preview and final
counter preparation. Existing counter selectors naming a "card" are normalized
to permanent selectors for this check. Prepared simultaneous moves use their
entry scratch state. The counter instruction remains in native replacement
ordering, so Doubling Season, Hardened Scales and Solemnity apply normally.

The bounded rider grammar also reads two/three additional counters and ordinary
lowercase creature types. Heroic Return additionally uses an existing live
"being attacked" condition for its discount: directly attacking the caster
qualifies; attacking another player does not. Its Hero entry adds two counters,
while non-Hero creatures receive none. The cost change remains native.

Teferi's Time Twist keeps the conditional counters on its delayed return, testing
the entering type at that later time. Semester's End stores two independent
conditional counter instructions. A creature planeswalker such as Gideon
Blackblade qualifies for both, so it enters with both the additional loyalty
counter and the +1/+1 counter. Ordinary creatures and planeswalkers receive only
their applicable additional kind, together with native starting loyalty.

Twenty-two focused tests pass, including a pending Phantasmal Image entry-copy
choice, actual opponent attacks/casting, zero-toughness entry protection from the
entering counter, exact target identity, replacement effects, replay and JSON
round trips. Conditional extras are frozen after entry costs and before the
simultaneous move (CR 614.12), including an explicitly empty result. A returning
March of the Machines cannot give a simultaneously returning Sol Ring the
creature entry counter; existing Opalescence does give March its own counter.
The pre-fix wrong Sol Ring counter was reproduced before adding this regression.
No new callback is added. A final coherent run passes all 129 focused
and shared entry/counter regression cases.
