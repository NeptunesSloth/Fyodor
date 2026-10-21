# Trigger-bound damage replacement records

Lightning, Army of One's Stagger resolves after combat damage has happened. It creates a continuous replacement until the trigger controller's next turn. It does not double its triggering first-strike hit; a subsequent double-strike hit is doubled, and that hit's second Stagger then creates a second independently stacking replacement (CR 510, 603, 611.2, 614.5, 616).

Bind the damaged player once when the trigger resolves. Damage to that player or any permanent they currently control is doubled, from any source. The permanent set is not locked at resolution: a permanent acquired later qualifies and one that changes away no longer does. Existing recipient player ids and a selector with controller `player:<id>` provide this behavior.

The record is independent of Lightning's subsequent zone or controller. Its original trigger controller anchors duration. It survives intervening players' turns and ends as that controller's next turn begins. If that player leaves, CR 800.4m in the pinned rules says it continues until the turn would begin, rather than ending immediately or persisting indefinitely.

Both replacement implementations must share liveness: the legacy prevention-record collector used to prune every record from other turns, while modern records also required the current turn. Timed records must survive both collectors. The existing next-turn turn-begin hook prunes them for the active or skipped departed seat. Ordinary turn records keep their existing expiration.

Canonical tests cover first strike/lifelink, double strike and stacked multipliers, dynamically controlled creature recipients, planeswalker damage, sources controlled by other players, source departure/control change, intervening turns, and actual concession/skipped-seat expiration. All gameplay scenarios check event replay and save/load.
