# Persisted permissions with a mana-value life alternative

Nashi, Moon Sage's Scion exiles the top card of each player's library after dealing combat damage to a player. Until end of turn, its controller may play one of those cards. A spell cast this way requires life equal to its mana value instead of its mana cost.

Official rulings were retrieved from [Scryfall](https://api.scryfall.com/cards/1e62de3b-6a41-43e3-93ad-9a1e3894be3b/rulings). They confirm that the life alternative is mandatory, other alternative costs cannot substitute for it, additional costs remain payable, normal timing and land-play limits apply, and X must be zero. Rules references use the repository's pinned 2026-09-25 Comprehensive Rules: 107.3b, 118.3b, 118.9a–d, 119.4b, 305.2 and 400.7.

The generic permission representation now persists `life_mv`, defaulting to false for old saves. The narrow permission-rider grammar binds the instruction to the actual objects exiled by the resolving ability. The existing permission group shares one remaining play across all those cards: playing a land or completing a cast consumes the same limit. A copied trigger creates another independent group; source departure does not end the grant. Re-exiling a card after a zone change creates a different object and does not inherit the old permission.

The cast pipeline's existing life alternative uses the selected spell's characteristics. A shared helper builds the life payment both for actual casting and for castability hints, so insufficient life, forbidden life payment and life-total locks are checked consistently. Paying zero life remains legal even when an effect forbids paying life (118.3b/119.4b). Equal available life may be paid. Split, modal double-faced and adventurer cards use the selected spell face's mana value; a land play requires no life.

Internally the existing `free` alternative-cost flag means the printed mana cost is replaced, allowing the established X=0 and mutually exclusive alternative-cost rules to apply. The stored permission label describes life payment. Additional costs, cost increases and Trinisphere still require their ordinary resources. No payment continuation code was changed for this scope.

Canonical fixtures retain full face metadata. Tests use actual combat damage, recorded choices, saved replay, copied triggers, land/spell group consumption, cost prohibitions, taxes, kicker, split/MDFC/adventure faces, source departure and expiry. Existing static Bolas's Citadel permissions share the same life-payment hint check.
