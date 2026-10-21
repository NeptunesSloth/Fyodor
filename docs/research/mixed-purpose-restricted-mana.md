# Mixed-purpose restricted mana

Canonical cards: Discreet Retreat, Creeping Peeper, Unblinking Observer,
Cultivator Drone, Tin Street Gossip, Qarsi Deceiver. Fixtures retain Oracle text,
colors, mana values, keywords, and double-faced/Room faces from the local catalog.

The shared restriction descriptor is a union of spell characteristics, activated
ability source characteristics, casting alternative, special action, selected
face-up payment method, and a literal colorless symbol in the cost being paid.
The ordinary mana solver remains responsible for actual colors and quantities.
Spending mana as though it were another type does not remove its restriction.

Disturb uses the selected native alternative, not merely a graveyard origin.
Face-down spells use their masked characteristics when selecting mana sources in
an interactive payment. The selected alternative and original colorless-symbol
qualification travel with the locked payment frame and typed post-payment tail,
including save/load and fresh-process resumption.

Unlocking a Room and turning a permanent face up are special actions, not
activated abilities of those permanents. Their costs therefore cannot use mana
restricted solely to activated abilities. Creeping Peeper explicitly allows
both actions. Qarsi Deceiver distinguishes paying a morph cost (including
megamorph) from paying a manifested creature's mana cost. Paying a cloaked
creature's mana cost and paying a disguise cost are separate methods; neither is
one of Qarsi Deceiver's permissions. A manifested or cloaked card can still use
its own morph ability.

Cultivator Drone's third alternative examines the actual cost containing {C};
it does not infer that condition from colorless mana chosen for generic mana.
The qualification is retained before spend-as permissions rewrite the solver's
cost representation. A colorless spell or colorless permanent's activated
ability is independently permitted by the other two alternatives.

Discreet Retreat's source selector uses the shared outlaw subtype family and
therefore includes changelings through normal characteristic derivation.
Its uniform two-mana output also exercises native color selection: a choice of
G permits an option GG, while mixed-color options do not qualify as one color.
The permanent-source alternative also checks battlefield membership. A colorless
card's cycling ability in hand is not an ability of a colorless permanent.

Validation: 37 canonical gameplay/coverage cases and 118 existing related mana,
Room, morph, face-down identity, and colored-X cases passed. The 37 include
fresh-process saved interactive payments for an actual disturb creature spell
and a face-down spell, with native payment records and history reconstruction.
