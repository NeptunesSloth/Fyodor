# Descendants' Path: reveal, qualify a card, cast, then clean up

The generic upkeep trigger delegates the exact Oracle body to two leaf primitives. The first records the actual top card as an ObjectRef and reveals it publicly. It reads the card's derived characteristics in the library and the current characteristics of creatures controlled by the trigger controller. A common subtype must belong to CREATURE_TYPES. This supports native changeling, Maskwood Nexus, and Grist's outside-battlefield creature characteristic; it does not use printed-only or hypothetical battlefield characteristics. Source departure or control changes do not change the existing trigger controller. Matching creatures are checked at resolution, not when the trigger first went on the stack.

A qualifying creature CARD grants the native optional free cast, without a creature-SPELL filter. An otherwise legal noncreature MDFC back or Adventure is available. A creature land cannot be cast. Native casting handles prohibitions, targets, additional costs, free X=0, cancellation, and the continuation when a cast is abandoned. No casting or permissions implementation is duplicated or rewritten.

The second primitive runs immediately after the cast is completed, declined, impossible, or cancelled. It bottoms only the original saved object still in that controller's library. A successfully cast card has changed objects and is excluded. This cleanup finishes before players receive priority for a later counterspell, so a countered spell stays in its proper graveyard. Empty library does not draw or lose the game.

The new primitives register during effects-module import; all cast-choice and payment callbacks remain the existing native callbacks. Fresh-process registration and history/JSON replay at offers and additional-cost choices are checked. Canonical fixture metadata covers creature types, CDA/changeling, MDFC/Adventure faces, and additional costs.

Rules: CR 603.3/608.2h, 608.2g, 205.3m/702.73a, 118.9/107.3b, 305.9, 400.7, and 601.2. Remote Scryfall ruling requests returned HTTP 400 during preparation; no unverified ruling comment is claimed as evidence.
