# Revealing a hand card or the library top

Eladamri, Korvecdal's activated ability uses native mana/tap/other-creature costs
and its existing own-turn restriction. The missing instruction is a private
choice between any hand card and the current library top, followed by revealing
the chosen card and putting it onto the battlefield if it is a creature card.

A bounded two-sentence grammar creates a private native decision. The top option
has a synthetic ID and no card ID or name. Merely asking the question does not
allow looking at the top, including if Eladamri has left the battlefield. Exact
object references persist in the server-only continuation. Revealing happens
only after choosing, then the current creature-card characteristics determine
whether the native battlefield-entry path runs. Its entry replacements and
choices preserve the rest of the resolving effect.

Canonical tests cover both origins and both creature/noncreature outcomes,
source removal and loss of top-look permission, cost atomicity, empty zones,
Priest/Cage restrictions, private views, saved choices, and full replay.
