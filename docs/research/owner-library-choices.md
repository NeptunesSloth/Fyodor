# One target's owner chooses library top or bottom

Subtlety, Aether Gust, and Endless Detour now parse into native `to_library` effects with an owner-controlled top/bottom decision. Subtlety preserves its optional single creature-or-planeswalker spell target. Aether Gust retains its red-or-green spell/permanent selector. Endless Detour uses a typed union of any spell, any nonland battlefield permanent, and any card in any graveyard; a land card in a graveyard is legal.

The decision uses the object's owner, including when Commandeer has changed a spell's controller. Its serialized resume now pins the exact target object identity, so moving a card away and back while a saved decision is pending cannot move its new incarnation. Older saves without that optional identity retain their previous interpretation.

Canonical Carnage Tyrant revealed an existing targeting error: printed hexproof, shroud, and protection were applied to stack objects. Their native keyword checks now apply on the battlefield (CR 113.6, 702.11, 702.16, 702.18), while explicit prohibitions and imposed targeting restrictions remain checked. Subtlety can therefore move the uncounterable, printed-hexproof creature spell; Aether Gust still cannot target the opponent's Carnage Tyrant permanent.

This implementation deliberately does not claim Aetherspouts, Hinder, or Power of Persuasion. Multiple attacking creatures require real per-owner choices plus private top/bottom ordering; a single-object choice must not silently become an all-top movement. Hinder additionally requires successful countering before its library destination replacement, respecting uncounterability. Power of Persuasion needs its distinct dice-result branches and owner binding validated.

Focused canonical tests cover top and bottom in all three zones, spell types, optional zero targets, the nonland/land distinction, illegal zones, actual Commandeer, actual pitch evoke, pending save/replay, and object identity changes. No new callback or resume kind is introduced.
