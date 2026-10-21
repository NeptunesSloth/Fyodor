# Actual black mana spent on X

Drain Life and Soul Burn retain their announced X. Generic reductions, convoke,
improvise and delve can pay the generic-origin X requirement without spending
mana. Soul Burn additionally observes how much actual black mana the player
assigned to X, rather than its printed black symbol or other generic costs.

The player can assign the same aggregate payment differently. With Soul Burn
announced at X=2 and a pool of three black and two red mana, assigning zero, one,
or two black mana to X are distinct legal choices. A generic reduction can also
be allocated between X and the remaining generic part of the cost. The life
outcome therefore cannot be reconstructed from aggregate black mana spent.

The generic restricted-X metadata carries its minimum remaining requirement and
maximum before a final minimum-cost floor. A selected black quantity reserves
that many actual black requirements; remaining required X accepts the permitted
nonblack mana or generic nonmana contributions. Actual black requirements are
not ordinary black mana symbols: K'rrik cannot replace them with life. Spending
mana as though it were another color does not change its actual color.

The scalar decision occurs after the spell's total cost and additional costs
are fixed, before committing convoke taps, delve exiles or mana. Feasibility is
checked jointly with native helper assignment. In AUTO, helper sets are selected
again for each scalar candidate. Negative-index synthetic helper options cannot
pay an actual-black requirement. This distinguishes a black creature convoking
the printed black symbol from convoking generic X.

The mandatory choice uses a registered, typed, serializable continuation. It
resumes only the helper/mana payment stage, never the original cast or previously
paid additional costs. The ordinary earlier payment prompt retains cancellation;
the committed-cost quantity stage has no cancellation option. Paged choices
support more than one hundred feasible quantities.

`PaymentRecord.x_black_spent` records the exact scalar. An absent value remains
`None` for old saves and unrelated records; it never means a guessed payment.
A free spell has zero spent on X, and spell copies reset the scalar to zero,
consistent with CR 707.10's mana-spent example.

Large colored-X payments use the normal mana solver's branch order and search
budget. At 256 requirements the depth-first traversal uses an explicit iterator
stack, so an actual Crypt Rats activation at X=1000 is not limited by Python's
recursion depth. This does not introduce a new X cap.

Tests: `test_rules_soul_burn_x_payment.py`, `test_rules_x_mana_allocation.py`,
`test_rules_large_mana_requirements.py`, and the actual X=1000 case in
`test_rules_x_mana_restrictions.py`. These cover canonical gameplay, saved
quantity choices, fresh-process continuation registration, replay, cancellation,
reductions, minimum-cost floors, K'rrik, spend-as permissions, and joint explicit
and automatic convoke assignment. Damage and life-gain caps are covered separately
in `test_rules_capped_damage_life.py`.
