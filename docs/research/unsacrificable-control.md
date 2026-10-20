# Alexios and unsacrificable permanents

Oracle/rulings: https://api.scryfall.com/cards/e81b94b2-4052-4686-a788-9baf0fa0f81a/rulings (2024-07-05).

- Alexios cannot be sacrificed for any reason, including spell/ability costs, resolving optional payments, direct sacrifice effects, edicts, and state-based Saga sacrifice if its characteristics become those of a Saga. CR 101.2, 701.21 and 704.5s apply. An effect requiring a creature sacrifice must choose another eligible creature, if one exists.
- A prohibition on being sacrificed is independent of indestructible. Losing Alexios's own abilities removes its printed prohibition; a rule imposed by an attached Assault Suit continues to apply.
- The ordinary attack requirement and owner-specific attack prohibition use the existing combat rules. Its owner cannot be attacked, while planeswalkers the owner controls and battles the owner protects can be attacked.
- Its upkeep ability performs the printed actions in order (CR 608.2c): the upkeep player gains control, untaps Alexios, puts the counter on it, then haste is granted until end of turn. That player puts the counter, even when another player controls the triggered ability; counter replacement effects must use that putter (CR 122.6, 614.1).
- Each control effect remains a separate permanent-duration effect. Existing control-layer and leaving-player rules retain the previous applicable control effect if a controlling player leaves (CR 800.4a).

Goblin Welder: https://api.scryfall.com/cards/17cd920a-de09-454a-a9da-c84512e3aff1/rulings (2008-08-01). Both targets must remain legal. Being unsacrificable does not make an artifact an illegal target: when both targets are legal, the impossible outgoing sacrifice is skipped while the incoming artifact still returns (CR 609.3). Existing simultaneous preparation remains in use.

Tests use canonical Oracle metadata, real spells/equipment, public gameplay actions, and replay plus JSON save/load. Shared checks cover additional/emerge/offering costs, mana-producing self-sacrifice, echo refusal, edict/direct sacrifice, simultaneous return, final-chapter Saga sacrifice, ability loss, owner/planeswalker attacks, upkeep transfers and the actual counter putter under Vorinclex.
