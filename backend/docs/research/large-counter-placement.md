# Large native counter placements

Yuna, Grand Summoner can transfer a quantity exceeding the manual Counter
action's per-action bound. A canonical Sol Ring with 1,005 charge counters,
destroyed by Disenchant, exposed that native replacements computed the correct
quantity but the final table action rejected its delta.

The counter choke point now commits oversized card deltas in legal chunks.
Every chunk preserves the same instruction group, actor, and recipient list.
Replacement planning runs once before the commit, so Hardened Scales changes
1,005 into 1,006 once. Counter triggers aggregate that original group: All Will
Be One produces one trigger for 1,006 damage rather than a trigger per chunk.
No manual input limit changes.

Canonical tests cover the 1,000 boundary, 1,005 source LKI, 1,006 after Scales,
and fresh-process replacement-order continuation with Scales and Doubling
Season. All Will Be One verifies a single complete damage event. Native replay
and 116 related counter placement, grouping, kind-choice, distribution, and
replacement cases pass.
