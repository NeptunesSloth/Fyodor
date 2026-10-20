# Prevention for the group that gained abilities

Mutational Advantage first grants hexproof and indestructible to the permanents its controller currently controls with counters. “Those permanents” refers to that resolution-bound group, not a selector evaluated again after proliferating or later in the turn (CR 611.2c, 615).

The existing grant primitive can bind its objects before applying abilities, and the existing prevent_all primitive can resolve a bound group to exact object ids. A narrow sentence hook connects the two when an immediately preceding selector-based grant is followed by prevention to “those permanents” or “those creatures.” Creature wording requires a creature selector. Ambiguous references without that preceding group remain refused.

No runtime or schema changes are needed. Both the granted abilities and prevention stay on the same objects if their counters are removed or their controllers change. A later entrant, a permanent that gains its first counter later, or a blinked new object does not gain them. Proliferate follows the snapshot and still happens when no permanent qualified.

Canonical gameplay cases cover own/opposing permanent scope, artifact abilities, proliferating both friendly and opposing counters, saved proliferate choice, losing/gaining counters, later entry, blinking, unpreventable damage, actual destruction, hexproof target validation, end-of-turn expiration, and an empty group followed by player proliferation and Scheming Aspirant's real trigger. Completed gameplay cases verify replay and save/load.
