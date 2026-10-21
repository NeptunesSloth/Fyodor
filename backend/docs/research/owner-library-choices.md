# One target's owner chooses library top or bottom

Subtlety, Aether Gust, and Endless Detour parse into native `to_library` effects with an owner-controlled top/bottom decision. Subtlety preserves its optional single creature-or-planeswalker spell target. Aether Gust retains its red-or-green spell/permanent selector. Endless Detour uses a typed union of any spell, any nonland battlefield permanent, and any card in any graveyard; a land card in a graveyard is legal.

The decision uses the object's owner, including when Commandeer has changed a spell's controller. Its saved resume pins the exact target object identity, so moving a card away and back during a saved decision cannot move its new incarnation. Older saves without that optional identity preserve their previous interpretation.

Canonical Carnage Tyrant exposed an existing targeting error: printed hexproof, shroud, and protection were applied to stack objects. Their keyword checks now apply on the battlefield (CR113.6,702.11,702.16,702.18), while explicit prohibitions and imposed restrictions remain checked. Subtlety can move the uncounterable creature spell; Aether Gust still cannot target an opponent's Carnage Tyrant permanent.

Canonical gameplay covers both destinations and all three zones, optional zero targets, illegal types/zones, actual Commandeer, actual pitch evoke, saved decisions/replay, and object identity changes. Thirty own cases and selected existing library, targeting, spell-control, attachment, and keyword tests passed.

Aetherspouts and Tolarian Contempt subsequently gained a separately validated simultaneous placement runtime, documented in [simultaneous-library-placement.md](simultaneous-library-placement.md). Hinder still needs successful-counter replacement semantics; Power of Persuasion's dice branches and owner binding remain separate work.

## Collateral validation: Swat Away

The batch22 inventory additionally promoted actual Swat Away. Its complete canonical Oracle has both a discount of {2} when a creature attacks its caster and the owner-choice tuck for a target spell or creature. Dedicated gameplay tests verify battlefield creatures and stack instants, both destinations, owner-only decision projection, the attacked-player condition versus an attack on another opponent, refusal of a noncreature battlefield artifact, and actual Commandeer changing spell control without changing its owner chooser. The pending owner choice is saved/loaded and every resulting game replays. This required no additional application changes.
