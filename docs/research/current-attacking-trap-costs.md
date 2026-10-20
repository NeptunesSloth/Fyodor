# Current attacking creatures and Trap alternative costs

Nemesis Trap, Lethargy Trap, Arrow Volley Trap, Pitfall Trap, and Slingbow Trap
offer an alternative mana cost when a condition about currently attacking
creatures holds. Their canonical Oracle lines require, respectively, a white
attacker, at least three attackers, at least four attackers, exactly one attacker,
and a black attacker with flying.

Three narrow condition grammar normalizations express these statements through
the existing battlefield selector counts. Existing alternative-cost machinery
evaluates them when the cost is chosen and performs ordinary target selection,
cost calculation, payment, and recording. No new casting path is introduced.
Attacker color and flying must match the same creature. The creature need not
attack the caster, and an unrelated qualifying attacker can enable the cost.
Creatures that attacked earlier but are no longer attacking do not count.

The canonical gameplay suite exercises all five real effects and paid alternative
costs, threshold boundaries, conjunction and nonattacking exclusions, a native
bounce changing eligibility, normal-cost fallback, atomic rejection of an
ineligible alternative, divided damage with a disappearing target, the Nemesis
copy's delayed exile, replay, cold resume, and countering a paid spell.

History-based Trap costs are separate. In particular, “an opponent had two or
more” requires one opponent to satisfy the threshold; a normalization that merely
totals entries across all opponents would be incorrect.
