# Sunforger: unattach, search, cast, then shuffle

The self-unattach activation cost uses the existing UNATTACH component without a chosen selector. It validates the source's current attachment with the ordinary attachment legality helper, then detaches that actual source as payment. Equipment must be attached to a creature; other attachment kinds retain their own legal-host rules. Existing granter-bound unattach costs receive the same affordability check.

A reusable `conditional_search_cast` grammar sequences native search, a bound library-only free cast, and an explicit final shuffle. Searching can find zero cards. The found card stays in the library until actually cast. A prohibited or impossible cast leaves it there for the final shuffle. Opposition Agent's redirected exile object does not satisfy the library-only permission.

The search tests the card's colors, types and mana value in the library. Those qualifiers do not become restrictions on the selected spell face: Fire // Ice qualifies and its blue Ice half can be cast. Split-card combined mana value, MDFC front characteristics and Adventure creature characteristics follow the native card and casting layers.

The required offer cannot be declined when casting is mandatory and possible. Cancelling an unfinished legal announcement returns to that required offer. Hidden stated-quality additional costs retain the CR 118.8c exception. Generic additional costs are checked without assuming that cards in hand are present. A locked mana cost is handled by the native casting payment pipeline: already sufficient pooled mana must be paid; activating additional mana abilities remains optional under CR 118.3c. Declining that activation opportunity ends the unsuccessful cast and proceeds to shuffle. The scoped required-unpayable marker does not alter ordinary optional free casts.

Canonical tests cover payment and rollback, failure to find, impossible targets and costs, Grafdigger's Cage, Opposition Agent, face selection, source departure and control change, opponent-controlled equipped host, a Lithoform Engine copy, Fling sacrifice, Lightning Axe's mandatory cost alternatives, optional kicker, X=0, taxes and pooled mana, and deterministic replay plus JSON save/load. A subprocess test resumes the required-payment decline from a save in a genuinely fresh Python process with no test rule imports.

Official rulings: https://api.scryfall.com/cards/0f9a9654-edf1-486f-a002-57418f03de8e/rulings

No casting continuation implementation was duplicated. The small required-payment integration in casting.py was implemented by the payment-pipeline owner and uses the existing pay_mana resume handler.
