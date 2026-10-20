# Activated-ability payment provenance

Canonical Oracle fixtures from the local imported catalog cover Forsworn Paladin,
Jetmir's Fixer, and Paragon of Modernity. Their missing clauses observe mana spent
to activate a particular ability. These are distinct from the payment for casting
the source permanent and from other activations of that permanent.

The native post-activation stage already has the actual settled mana payment.
It now preserves its colors, source tags and exact source identities on the
ability stack object's own PaymentRecord, including activations with no nonmana
costs. The conditions use the resolving ability's stack object, not the source
permanent's cast record. Source departure does not erase the payment.

Two reusable conditions are recognized: mana from a Treasure spent on this
activation, and exactly N distinct colors spent on it. Colorless mana is not a
color (CR 105.2c). Native buff, conditional grant, counter and instead instructions
perform the card effects. The coverage refusal is exempted only for these exact
modeled condition clauses; quantity-dependent dice and other unmodeled
activation-payment clauses remain refused.

CR 707.10 says copies of activated abilities are not activated and mana is not an
object used to pay a cost. Native ability-copy payment aliases therefore have no
mana spent, tags or source identities. Actual Lithoform Engine copying a
Treasure-paid Jetmir's Fixer activation produces the ordinary temporary buff;
only the original activation puts a permanent counter on the Fixer.

No payment solver, action schema or continuation format was added. Existing
PaymentRecord fields and native mana payment resumes are reused. Old records
without tags or spent mana do not invent a positive condition; previously manual
ability definitions remain manual in saved stack entries.

Gameplay tests cover all three cards, source departure, actual Paladin-created
Treasure production, Treasure mana versus a Treasure-paid permanent's unrelated
cast, independent activations, exactly three versus four colors with Suppression
Field, colorless versus colored quantities, actual ability copies, save/replay,
and fresh-process native self-payment continuation with Treasure provenance.
