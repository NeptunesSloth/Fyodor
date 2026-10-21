# Six effects based on actual mana spent

Canonical cards: Tellah, Great Sage; Chandra, Dressed to Kill; Wurmquake;
Magmablood Archaic; Transcendent Archaic; Exert Influence.

The shared grammar composes native token creation, draw/discard, damage,
control, emblems, and cast permissions. Total amounts and distinct colors read
actual payment records or the immutable cast-event payment snapshot. Spell
copies spend zero mana and do not cast. Life and nonmana contributions are not
mana; colorless mana contributes to total amount but not W/U/B/R/G colors.

Tellah's final 'that much' is the actual amount spent on the triggering spell,
not the threshold eight and not a damage-event quantity. Its native integer
thresholds now retain that known cast amount after the spell leaves. Damage
refers to Tellah's original source identity/LKI even if it could not be
sacrificed because it had already left. Threshold, draw, sacrifice, token,
and opponent damage still execute in printed order.

Chandra's ultimate uses the existing filtered among-cards cast permission,
with trailing 'this turn' normalized to its native prefix duration. It permits
red spells, at their ordinary costs and timing, until end of turn. The emblem
uses the actual amount spent on the later red spell. Tests also cover both +1
abilities, source death at zero loyalty, nonred rejection, and expiry.

Magmablood's pump uses colors spent on the triggering spell, including after
that spell is countered. Resolved pump effects affect the creatures present
when they resolve, and expire normally.

Transcendent's optional draw uses its own permanent's cast payment, including
zero for a permanent-spell copy. The follow-up discards only if the controller
actually drew at least one card. The shared drawn-this-way value supports an
explicit controller-only qualifier: Notion Thief drawing instead does not
force the original controller to discard. Abundance putting cards in hand also
does not count as drawing. Native replacement/optional/discard continuations
retain the original draw baseline across a saved pending decision and cold
process resumption.

Exert Influence targets any otherwise legal creature. Its power comparison is
checked at resolution, then the native permanent control effect runs only if
it passes. Actual colors spent remain independent of spell color or mana value;
a spell copy does not inherit the original's mana spending.

Wurmquake first creates its normal token and then creates the additional batch
for qualifying opponents. The latter reuses the immutable original token
recipe, not the objects created or modified by earlier replacements. Player
counter counts exclude the controller and players no longer in the game.
Token replacement, additional tokens, doubling, flashback payment of ten mana,
zero-mana copied/free spells, and zero-toughness state-based actions use the
native engine paths. No payment solver or commit logic changed.

Validation: 45 canonical gameplay/coverage cases and 129 related existing
Opus, cast-payment, converge, actual-drawn, emblem, and trigger cases passed
(174 unique cases). Two fresh-process save/resume scenarios preserve actual
cast payment after a counter/source departure and the actual-draw baseline
through Abundance's paused replacement choices. Ruff and diff checks passed.
