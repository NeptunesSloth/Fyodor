# Actual spell payments across counters and cast triggers

Canonical family: Nix, Void Mirror, Unravel, Mana Sculpt, and Smoldering Egg //
Ashmouth Dragon. All use existing actual mana payment records; life, convoke,
improvise, delve, and copied cost decisions are not mana spent.

The reusable capture primitive records the target spell's effective stack mana
value and known actual mana dictionary before a native counter instruction.
These facts are named context bindings using the normal `ref:` syntax, so native
clause renaming, serialization, and delayed triggers preserve them. Nix tests
zero total mana. Unravel compares the amount with effective stack mana value,
including X, after attempting the counter; its draw does not depend on whether
the spell can be countered. Mana Sculpt checks its Wizard condition as it resolves
and retains the captured amount until the next main phase, even if the Wizard
leaves before that phase.

Void Mirror is an ordinary cast trigger with an intervening condition counting
only actual W/U/B/R/G mana. Colorless mana is mana for Nix, but not colored mana
for Void Mirror. A spell copy was not cast and does not generate Void Mirror's
trigger. It spent no mana and can be countered by Nix.

Cast-trigger events now also retain an optional actual mana dictionary. An empty
dictionary means known zero; null preserves compatibility with earlier events
that did not record the fact. A trigger's mana-spent amount can therefore be read
after the triggering spell was countered or resolved. Smoldering Egg's normalized
counter-count grammar uses that snapshot with the existing add-counters,
threshold, remove-all-counters, and transform instructions. Native source-object
identity and transform timestamp guards remain responsible for returned objects
and multiple stacked triggers.

Unknown older/manual payment facts produce an explicit table note and are not
inferred from mana value. No solver, allocation, source activation, or payment
continuation behavior changed for this family.

The separately scouted Myr Superion/Imperiosaur/Security Rhox producer-only family
remains deferred. Native filter planning does not yet serialize exact input unit
reservations and flexible-source options; aggregate feasibility alone cannot
safely preserve a qualified unit for the final spell payment. No coverage support
was added for those three restrictions.

Validation: 27 canonical gameplay/coverage cases plus 256 related native stack,
conditional, Opus, counter, and transform cases passed (283 unique cases).
One related legacy assertion was updated to count both plain mana and remembered
mana units. Fresh-process delayed-trigger resumption, history reconstruction,
and save/load equality are included.
