# Rules coverage

Every card gets a coverage level from what the rules engine really implements
(`backend/app/rules/coverage.py`):

| Level | Meaning |
|---|---|
| **FULL** | Everything on the card is automated. |
| **PARTIAL** | Some of it is automated; the rest is listed as manual parts. |
| **MANUAL** | The engine can move the card around, but its text and costs are handled by hand. |

- **What counts:** a card is broken into features:
  - how it's played (land drop, casting);
  - combat, for creatures;
  - intrinsic mana, for basic land types;
  - one feature per ability line (keyword, mana ability, scripted ability or free text).
- **The `SUPPORTED` set:** coverage compares a card's features with this set. A feature is
  only added to it together with its scenario tests, so the report never claims more than
  the engine does.
- **Where it shows up:** coverage is served per card at `GET /api/rules/coverage`. Features
  and keywords supported today are at `GET /api/rules/support`.

## Inventory of the pod's cards

Run it on the host computer (from `backend/`):

```bash
python -m tools.rules_inventory                     # deck library (Archidekt imports, lists) + saved games
python -m tools.rules_inventory --archidekt https://archidekt.com/decks/123456/my-deck   # add public Archidekt decks
python -m tools.rules_inventory --deck-file deck.txt                                     # add deck files
```

- **Output:** it writes `data/reports/rules_inventory.md` and `.json`. The host computer can
  also open `GET /api/rules/inventory` (JSON) or `/api/rules/inventory.md`.
- **Order:** cards are ranked by how many pod decks play them, then by saved games and copies.
  That's the order they get automated in milestone 17.
- **Refreshing:** re-importing a deck from Archidekt updates the library, so re-running the
  tool refreshes the report.
- **Counting:** cards are counted by Oracle id (every printing is one card). The commander,
  companion, main deck and sideboard count; the maybeboard doesn't.
- **Saved games** add cards from decks players brought to a LAN lobby without saving them.

## Progress on the sample decks

Regenerate with the command above after each milestone.

| After | FULL | PARTIAL | MANUAL | Copies fully automated | What changed |
|---|---|---|---|---|---|
| M14 | 0 | 32 | 121 | 0% | Land drop only |
| M15a | 8 | 145 | 0 | 25.5% | Casting (timing, costs, commander tax, the stack), mana abilities incl. basic land types. Every card can now be cast or played through the engine. Mana rocks and basic lands are FULL. |
| M15b–c | 8 | 145 | 0 | 25.5% | State-based actions and combat. These decks have no vanilla creatures: every creature still has manual text, so FULL doesn't move. Combat keywords (flying, trample, deathtouch, lifelink, first/double strike, menace, vigilance, haste, defender, reach, indestructible) are now automated everywhere. The remaining work is text effects (M16). |

## Baseline (milestone 14): the two sample decks

`docs/sample-decks/atraxa-counters.txt` and `krenko-goblins.txt` were run against Scryfall's
Oracle cards. This is a stand-in until the report is run on the pod's own decks.

- **Totals:** 153 unique cards. FULL 0, PARTIAL 32 (lands: the land drop is automated),
  MANUAL 121.
- **What would unlock the most**, counted as manual parts across the 153 cards:

| Manual part | Cards |
|---|---|
| Casting spells (timing, costs, the stack) | 122 |
| Free-text abilities (need effect primitives or scripts) | 196 lines |
| Combat for creatures | 50 |
| Mana abilities (`{T}: Add …`) | 22 |
| Intrinsic mana of basic land types | 14 |
| Keywords: haste 6, flying 4, equip 3, flashback 2, overload 2, others 1 each | — |

That is why milestone 15 starts with mana, casting and combat, which covers most of the table
at once, before per-card scripting.

Top of the baseline list:

| # | Card | Decks | Copies | Games | Coverage | Manual parts |
|---|---|---|---|---|---|---|
| 1 | Arcane Signet | 2 | 2 | 0 | MANUAL | Cast it (timing, costs, the stack); {T}: Add one mana of any color in your commander's color identity. |
| 2 | Command Tower | 2 | 2 | 0 | PARTIAL | {T}: Add one mana of any color in your commander's color identity. |
| 3 | Fellwar Stone | 2 | 2 | 0 | MANUAL | Cast it (timing, costs, the stack); {T}: Add one mana of any color that a land an opponent controls could produce. |
| 4 | Lightning Greaves | 2 | 2 | 0 | MANUAL | Cast it (timing, costs, the stack); Equipped creature has haste and shroud.; Equip |
| 5 | Skullclamp | 2 | 2 | 0 | MANUAL | Cast it (timing, costs, the stack); Equipped creature gets +1/-1.; Whenever equipped creature dies, draw two cards.; Equip |
| 6 | Sol Ring | 2 | 2 | 0 | MANUAL | Cast it (timing, costs, the stack); {T}: Add {C}{C}. |
| 7 | Swiftfoot Boots | 2 | 2 | 0 | MANUAL | Cast it (timing, costs, the stack); Equipped creature has hexproof and haste.; Equip |
| 8 | Mountain | 1 | 28 | 0 | PARTIAL | {T}: Add {R} (basic land type) |
| 9 | Swamp | 1 | 5 | 0 | PARTIAL | {T}: Add {B} (basic land type) |
| 10 | Forest | 1 | 4 | 0 | PARTIAL | {T}: Add {G} (basic land type) |
| 11 | Island | 1 | 4 | 0 | PARTIAL | {T}: Add {U} (basic land type) |
| 12 | Plains | 1 | 4 | 0 | PARTIAL | {T}: Add {W} (basic land type) |
| 13 | Ajani, Mentor of Heroes | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Loyalty and damage to planeswalkers; +1: Distribute three +1/+1 counters among one, two, or three target creatures you co… |
| 14 | Anger | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Attack and block; Haste; As long as this card is in your graveyard and you control a Mountain, creatures you control have… |
| 15 | Anguished Unmaking | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Exile target nonland permanent. You lose 3 life. |
| 16 | Assassin's Trophy | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Destroy target permanent an opponent controls. Its controller may search their library for a basic land card, put it onto… |
| 17 | Atraxa, Praetors' Voice | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Attack and block; Flying; Vigilance; Deathtouch; Lifelink; At the beginning of your end step, proliferate. |
| 18 | Battle Hymn | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Add {R} for each creature you control. |
| 19 | Beast Within | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Destroy target permanent. Its controller creates a 3/3 green Beast creature token. |
| 20 | Beetleback Chief | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Attack and block; When this creature enters, create two 1/1 red Goblin creature tokens. |
| 21 | Blasphemous Act | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); This spell costs {1} less to cast for each creature on the battlefield.; Blasphemous Act deals 13 damage to each creature. |
| 22 | Breeding Pool | 1 | 1 | 0 | PARTIAL | {T}: Add {G}{U} (basic land type); As this land enters, you may pay 2 life. If you don't, it enters tapped. |
| 23 | Brightstone Ritual | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Add {R} for each Goblin on the battlefield. |
| 24 | Burnished Hart | 1 | 1 | 0 | MANUAL | Cast it (timing, costs, the stack); Attack and block; {3}, Sacrifice this creature: Search your library for up to two basic land cards, put them onto the bat… |
| 25 | Canopy Vista | 1 | 1 | 0 | PARTIAL | {T}: Add {G}{W} (basic land type); This land enters tapped unless you control two or more basic lands. |
