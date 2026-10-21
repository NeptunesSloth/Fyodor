# Banding among resolution choices

Urza's Avenger and Nature's Blessing extend the existing effect-choice grammar, with no
card-name checks. Urza's Avenger's pump and chosen keyword expire at end of turn.
Nature's Blessing targets a creature and pays mana plus a discard when activated. Its
controller chooses the counter or one of the listed keywords during resolution, rather
than declaring a mode on activation (CR 608.2d, 700.2). Its keyword grant has no stated
duration and therefore persists across turns and source departure (CR 611.2a).

The shared choice primitive omits a counter option forbidden by a “can't” effect and
rejects answers outside the offered options. Chosen instructions enter the ordinary
effect continuation, so replacement decisions pause and resume safely. A replacement
that changes the counter amount still applies through the normal counter machinery.

Gameplay checks cover every listed option, turn expiration/persistence, paid discard,
illegal targets, departed/reentered sources, counter prohibitions, competing counter
replacement effects, and declaring a band with the granted ability after the enchantment
leaves. Every scenario checks replay and saved-state reload.
