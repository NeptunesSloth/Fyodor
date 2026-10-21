# Qualified search packets

Fourteen canonical Oracle cards share native tutor slots and explicit name-reference preparation: Secret Salvage; Infernal Tutor; Assembly Hall; Mishra, Artificer Prodigy; Doubling Chant; Clarion Ultimatum; Canoptek Wraith; Alpine Houndmaster; Agency Outfitter; Nissa's Encouragement; Journey for the Elixir; Verdant Crescendo; Firemind's Foresight; Gaea's Balance.

Canonical complete metadata and gameplay cases live in `tests/fixtures/qualified_search_packet_cards.json` and `tests/test_rules_qualified_search_packets.py`. The parser prepares native `search` effects; searching, authority, zone replacement, entering and shuffling remain the existing engine's responsibility. Legacy string selector slots remain compatible. The current slot selector now applies to the library, graveyard and hand consistently; previously the latter two reused the first slot's selector.

## Names and choices

A reference's name group is read at the instruction that asks for it (CR 608.2c/h), preserving current characteristics, last-known event/target information, and all names of a split card (201.2a, 709.4a). One JSON-native name group per slot preserves repeated names without allowing the same found object to fill two slots. Named literal searches remain fixed under source copy/rename effects. Native selectors use current derived characteristics; Grist in hand is eligible for Assembly Hall's creature-card reveal.

Infernal Tutor determines Hellbent when it resolves, before any reveal; revealing keeps the card in hand. Assembly Hall reveals just the chosen creature, not the hand. Cleanup hides the exact hand object after the linked search. Secret Salvage binds its actual exiled target's information using a standard `ref:` reference, so the per-spell-line namespacer rewrites the producing `as` and consuming reference together; an illegal sole target causes the spell to fail to resolve, without searching. Canoptek Wraith uses the native optional mana-plus-sacrifice payment and asks for the land only after that entire cost is paid.

Library/hand choices remain private and use native search authority. Opposition Agent controls the library search and replaces found library cards with exile and its native play permissions; searches confined to graveyard/hand do not give Agent library authority. A search confined to public zones must find an available requested quantity (701.23b); an optional whole search can still be declined before it starts. Hidden qualified searches may fail to find. Aven Mindcensor constrains every slot to the same actual top four library cards.

## Official ruling edges

Official Scryfall/Gatherer rulings were fetched on 2026-10-20; raw research is `/tmp/qualified-search-packets32-rulings.json`.

* **Clarion Ultimatum**, 2009-10-01: “You make just one search.” Its “for each” wording creates qualification slots within ONE native search, rather than separate search events. Doubling Chant uses the same packet structure. Actual Archivist of Oghma sees exactly one search. Each quality may fail independently, and duplicate permanent names produce distinct slots.
* Clarion chooses five different permanents as it resolves, or every permanent if fewer than five. Found permanents enter together and tapped. Choices are not targets. Auras can attach only to things already on the battlefield, using native simultaneous entry.
* Clarion may find a nonpermanent card with the name of a chosen token, such as Illusion // Reality for an Illusion token; that card remains in the library. CR 304.4/307.4 now have a shared `attachments.enter` safeguard based on the actual prospective battlefield characteristics AFTER copy-entry choices, including the requested transformed/modal back face and existing face-down state. It does not blanket-reject a printed instant manifested as a creature or a legitimate permanent back face.
* **Doubling Chant**, 2011-09-22: with no creatures “you may still search your library and you must shuffle your library.” Therefore the optional search has `shuffle=False`, followed by a mandatory separate native shuffle; declining the search or controlling no creatures still shuffles once. Found cards must be creature cards, including when the reference is an animated land.
* **Gaea's Balance**, 2004-10-04: nonbasic lands qualify if they have the required basic land type; the player can fail to find any basic-land-type slot. A dual-typed card fills only one slot.
* **Canoptek Wraith**, 2022-10-07: both basic lands must have the same name as the chosen land. Paying is before choosing that land.

Textual order is preserved where the instruction requires separate movement: Verdant Crescendo's first land enters before the second search, with a single final shuffle; Firemind's Foresight repeats each search-and-hand movement before the next mana-value slot, then shuffles once. Other packet found permanents enter together after all choices.

## Validation

The canonical suite exercises all fourteen cards through actual casts, triggers or activations, including native combat damage for Wraith, cost selection for Gaea's Balance, source departure/controller change, illegal targets, current Grist types, split-name groups, duplicate names, same-zone exclusion, Agent, Mindcensor, entry replacement, mandatory public finds, one search event, required final shuffle, privacy through REST and WebSocket, JSON round-trips/replay, and a genuinely new GameSession resuming a saved Mishra choice.

Separate entry regressions cover manifested noncreature cards, face-down morphs through related native suites, a played modal land face, a permanent entering transformed, and copy-before-entry replacement. Full-catalog/type/core verification remains centralized by the parent agent; no local full inventory was run.

Final positive audit: all fourteen cards have actual successful found-card movement tests. The strengthened Secret Salvage multiple-match test caught and repaired a previously empty reference caused by per-line namespacing (`qs_name` -> `l0_qs_name`); the leaf now uses standard `ref:qs_name` and resolves that exact binding, without guessing a name or scanning another zone. The complete canonical suite is 53 passing cases after that repair, including real normal/Hellbent Infernal finds and Gaea finding all five land-type slots.

CR701.23h follow-up: multiple search instructions before the single final shuffle on Firemind’s Foresight and Verdant Crescendo now share one native search event AND the same original exact searched portion/Agent decider. See `conditional-tutor-outcomes.md` and the canonical Archivist/Mindcensor/Agent/cold-session tests; merely suppressing duplicate events without preserving the original top four would be insufficient.
