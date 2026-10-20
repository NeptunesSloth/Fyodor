# Continuous type forms

These static sentences compose existing layered grants. Attached type setters
preserve abilities unless the text actually removes them. Adding a type preserves
other types; setting card types removes the old types and their associated
subtypes. Colors and supertypes remain unless separately changed (CR205.1,
205.3,613.1). Swift Reconfiguration adds Crew5 while retaining printed abilities
and any previous crew ability. One with the Stars preserves abilities.

The Vehicle Auras use a native group selector for Vehicle plus the existing exact
`host_of_source` relationship. This evaluates the current attachment and type
through the normal group-membership/dependency machinery. It does not bypass the
parser's restriction on recursive characteristic-dependent attached conditions.
Their separate P/T and keyword bonuses remain independent.

Bello uses a union of non-Equipment artifacts and non-Aura enchantments. The
exclusions belong to their respective branches. Its single layered definition
keeps the same members across type, ability and P/T layers, including when Bello
loses abilities in layer6 after its effect has begun in layer4 (CR613.6). The
controller's turn gate and current mana value are native selector conditions.

Dune Chanter distinguishes controlled lands on the battlefield from owned land
cards elsewhere. Secret Arcade's additional outside-battlefield scope is only
permanent spells on the stack; it does not affect cards in hand or graveyards.
Both use the existing `everywhere` scope with the native ownership/controller and
zone rules. Room door discovery controls whether Secret Arcade's static exists.

CR208.3 gives a noncreature permanent no power or toughness even when its card
prints them. Final battlefield derivation therefore clears effective power,
toughness and base values for noncreatures after the type/ability layers. Printed
copiable values and saved continuous effects remain intact. Crew/animation
recomputes from those values, and off-battlefield cards retain printed stats.
This prevents an enchanted noncreature Marwyn from incorrectly adding mana equal
to its former power while preserving its mana ability.

Canonical gameplay fixtures preserve Oracle colors, mana value, keywords and all
faces. Tests exercise actual Aura casts, equip and crew activations, Room casting,
battle defeat/back-face casting, damage triggers, ownership/control boundaries,
turn changes, source departure, save/load and replay. WotC rulings and detailed
preparation are recorded under `/tmp/fyodor-static-type38-*` during this task.
