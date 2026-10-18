# Rules coverage

Fyodor is Commander-only: coverage is measured over **cards legal in Commander today**
(`legalities.commander == "legal"` in the local card data, decided by
`app/rules/commander.legality`, never by guessing from Oracle wording). Banned cards are
COMMANDER_BANNED: their scripts are kept, but they leave every statistic until they are legal
again. Cards only relevant to other formats (Alchemy/Arena-only designs and "A-" rebalances,
acorn-stamped Un-cards, playtest cards) are ignored because the card data says so; Unfinity's
oval-stamped cards (stickers, Attractions, d20 rolls) are legal and count. Objects that can't be
deck cards (Unfinity sticker sheets, which the bulk data marks "legal", emblems, tokens,
dungeons, planes, schemes …) never count, so the denominator is 32,068 with the 2026-09-28 data
(32,116 before the sticker sheets were removed; they were the 48 MANUAL cards). Card data
without stored legalities falls back to the printing's other fields (digital-only, set type,
security stamp, border, the banned list) — see `commander._inferred_legality`.

Every card gets a level from what the rules engine really implements
(`backend/app/rules/coverage.py`):

| Level | Meaning |
|---|---|
| **FULL** | Every gameplay ability is automated by tested engine behaviour. |
| **PARTIAL** | Some of it is automated; the rest is listed as manual parts. |
| **REVIEW** | A script exists but the card's Oracle text changed since it was validated (or the tools found something ambiguous). Handled by hand until reviewed. |
| **MANUAL** | The engine treats it as a Magic object (it can be cast, move, attack), but its text is resolved by hand. |

- **What counts:** a card is broken into features: how it's played (land drop, casting),
  combat for creatures, intrinsic mana for basic land types, and one feature per ability line
  (keyword, mana ability, scripted ability, or text classified by `app/rules/analysis.py` into
  triggered / activated / static / replacement / prevention / permission / restriction / cost
  modifier / characteristic-defining / spell effect, with a normalised template).
- **The `SUPPORTED` set:** a feature is added only together with its scenario tests, so the
  report never claims more than the engine does. Casting it, attacking with it or recognising
  its keywords never makes a card FULL by itself.
- **Where it shows up:** `GET /api/rules/coverage` (per card) and `GET /api/rules/support`.

## Commander pool coverage

```bash
python -m tools.commander_coverage                 # from backend/, reads the local card DB
```

It writes `data/reports/commander_rules_coverage.{md,json}` (totals, by type / keyword / set,
commander eligibility, pod coverage, and **top Commander features to implement next**),
`commander_coverage.md` (every possible commander, most played first, with supported and missing
parts) and `mechanics.md` (every CR 701/702 mechanic with its Commander card count and status).

Progress (Scryfall data 2026-09-28, Comprehensive Rules 2026-09-25):

| Milestone | Commander-legal cards | FULL | PARTIAL | REVIEW | MANUAL | Possible commanders FULL |
|---|---|---|---|---|---|---|
| M17b baseline (M15 engine) | 32,116 | 921 (2.9%) | 31,147 | 0 | 48 | 37 / 3,501 |
| M16b triggers, targets, effects, layers, templates | 32,116 | 2,434 (7.6%) | 29,634 | 0 | 48 | 48 / 3,501 |
| M16c Commander patterns (tokens, wipes, blink, tutors, monarch, looting, Treasure, proliferate) | 32,116 | 2,939 (9.2%) | 29,129 | 0 | 48 | 61 / 3,501 |
| Mana abilities: filters, pain lands, restrictions, counters/life as costs, chosen color, lands' mana | 32,116 | 3,115 (9.7%) | 28,953 | 0 | 48 | 61 / 3,501 |
| Evasion (landwalk, shadow, horsemanship, fear, intimidate, skulk), prowess, combat restrictions | 32,116 | 3,340 (10.4%) | 28,728 | 0 | 48 | 71 / 3,501 |
| Cycling and typecycling (mana costs) | 32,116 | 3,474 (10.8%) | 28,594 | 0 | 48 | 73 / 3,501 |
| Protection (colors, card types, creature types, multicolored, everything): DEBT | 32,116 | 3,564 (11.1%) | 28,504 | 0 | 48 | 76 / 3,501 |
| Regeneration shields (destroy, lethal damage, "can't be regenerated") | 32,116 | 3,636 (11.3%) | 28,432 | 0 | 48 | 78 / 3,501 |
| Flashback (mana costs; exiled as it leaves the stack) | 32,116 | 3,675 (11.4%) | 28,393 | 0 | 48 | 78 / 3,501 |
| Crew (Vehicles; layer-4 type change until end of turn) | 32,116 | 3,712 (11.6%) | 28,356 | 0 | 48 | 78 / 3,501 |
| Wither, infect (poison), exalted | 32,116 | 3,774 (11.8%) | 28,294 | 0 | 48 | 79 / 3,501 |
| Enters with N (or X) counters | 32,116 | 3,812 (11.9%) | 28,256 | 0 | 48 | 79 / 3,501 |
| Affinity (card types, creature and land types) | 32,116 | 3,841 (12.0%) | 28,227 | 0 | 48 | 80 / 3,501 |
| Changeling, echo, "sacrifice ~ unless you pay" upkeep costs | 32,116 | 3,909 (12.2%) | 28,159 | 0 | 48 | 83 / 3,501 |
| Landfall and ability-word triggers, "Activate only once each turn", attacking/blocking targets | 32,116 | 4,023 (12.5%) | 28,045 | 0 | 48 | 87 / 3,501 |
| Convoke (+ generic-payment solver fix) | 32,116 | 4,061 (12.6%) | 28,007 | 0 | 48 | 88 / 3,501 |
| Counted mana (Gaea's Cradle, Cabal Coffers, power), Scion/Spawn token makers | 32,116 | 4,080 (12.7%) | 27,988 | 0 | 48 | 89 / 3,501 |
| Static anthems and lords (P/T and keyword grants, layers 6/7c) + derived P/T on the table | 32,116 | 4,223 (13.1%) | 27,845 | 0 | 48 | 100 / 3,501 |
| Morph and megamorph (face-down casting, turn face up; hidden from opponents) | 32,116 | 4,275 (13.3%) | 27,793 | 0 | 48 | 100 / 3,501 |
| Devoid, bushido, renown, bloodthirst, bounce lands | 32,116 | 4,359 (13.6%) | 27,709 | 0 | 48 | 101 / 3,501 |
| Granted quoted abilities (All Slivers / Lands you control / Commander creatures you own have "…") | 32,116 | 4,386 (13.7%) | 27,682 | 0 | 48 | 105 / 3,501 |
| Suspend (time counters, free cast, haste) | 32,116 | 4,408 (13.7%) | 27,660 | 0 | 48 | 105 / 3,501 |
| Cascade, cumulative upkeep | 32,116 | 4,435 (13.8%) | 27,633 | 0 | 48 | 106 / 3,501 |
| Unearth, dash (delayed end-step triggers, exile-instead replacement) | 32,116 | 4,463 (13.9%) | 27,605 | 0 | 48 | 106 / 3,501 |
| Buyback, madness | 32,116 | 4,493 (14.0%) | 27,575 | 0 | 48 | 106 / 3,501 |
| Counterspells ("counter target spell", "… unless its controller pays"), ward | 32,116 | 4,565 (14.2%) | 27,503 | 0 | 48 | 108 / 3,501 |
| Shock lands, explore, investigate, "becomes the target … sacrifice it" | 32,116 | 4,633 (14.4%) | 27,435 | 0 | 48 | 108 / 3,501 |
| Prevention shields, soulshift (graveyard targets), convoke with self-tap | 32,116 | 4,685 (14.6%) | 27,383 | 0 | 48 | 110 / 3,501 |
| Persist, undying, toxic, flanking, "can't be countered", combat-damage-to-player triggers, mill, Island attack restriction | 32,116 | 4,817 (15.0%) | 27,251 | 0 | 48 | 117 / 3,501 |
| Delve, improvise (player-paid), evoke, rebound | 32,116 | 4,861 (15.1%) | 27,207 | 0 | 48 | 117 / 3,501 |
| "Exile … until ~ leaves the battlefield", fabricate | 32,116 | 4,895 (15.2%) | 27,173 | 0 | 48 | 117 / 3,501 |
| Storm (spell copies; same or new targets) | 32,116 | 4,911 (15.3%) | 27,157 | 0 | 48 | 117 / 3,501 |
| Split cards / adventures analysed per half (report fix) | 32,116 | 4,933 (15.4%) | 27,135 | 0 | 48 | 119 / 3,501 |
| Attachments (one model: Auras incl. player Auras, Equipment; targeted Aura casting, Auras entering without being cast choose a host, equip), "Enchanted/Equipped … gets/has", attached restrictions (can't attack/block/activate, doesn't untap) — +189 Auras, +74 Equipment | 32,116 | 5,196 (16.2%) | 26,872 | 0 | 48 | 119 / 3,501 |
| "At the beginning of [whose] [step]" (your / each / each opponent's / enchanted player's; upkeep, draw, first/second main, beginning of combat, end step) | 32,116 | 5,219 (16.3%) | 26,849 | 0 | 48 | 121 / 3,501 |
| Partner-family keywords and "~ can be your commander" (deck construction only, 702.124a / 903.3a) | 32,116 | 5,222 (16.3%) | 26,846 | 0 | 48 | 124 / 3,501 |
| "Whenever ~ enters or attacks" (one ability, each event, 603.2) | 32,116 | 5,225 (16.3%) | 26,843 | 0 | 48 | 125 / 3,501 |
| Modal spells (700.2: choose one / two / one or both / one or more / same mode more than once / commander "choose both"; a target per mode) | 32,116 | 5,269 (16.4%) | 26,799 | 0 | 48 | 125 / 3,501 |
| Generic selector + value expressions + effect grammar (draw, life, discard, mill, sacrifice, damage, destroy/exile/tap/untap, return, counters, pump/grant, "for each", "where X is") | 32,116 | 6,672 (20.8%) | 25,396 | 0 | 48 | 174 / 3,501 |
| Enchanted/equipped hosts, "can't block/attack this turn", compound clauses ("…, then …", "… and …") | 32,116 | 7,042 | | | | 182 / 3,501 |
| Library search (selector, up to N, reveal, destinations, put on top after the shuffle) | 32,116 | 7,179 | | | | 183 / 3,501 |
| Look at the top N (pick, reveal, rest to graveyard / bottom in any or random order) | 32,116 | 7,263 | | | | 188 / 3,501 |
| Generic trigger conditions (events.py) — then false FULLs removed: pronoun "it" resolved against its antecedent, counters with unmodeled rules (122.1b-j) manual | 32,116 | 7,768 | | | | 269 / 3,501 |
| Review fixes (clause subjects, LKI trigger facts, "permanent card") + planeswalker loyalty abilities, ability words, short names | 32,116 | 7,908 | | | | 286 / 3,501 |
| "That player" / "that much" bound from the trigger event | 32,116 | 7,941 | | | | 290 / 3,501 |
| Conditions: "If …, [effect]", intervening-if triggers (603.4) | 32,116 | 8,025 (25.0%) | 24,043 | 0 | 48 | 293 / 3,501 |
| Merge: target groups / divided damage and counters (115, 601.2c-d, 608.2b) | 32,116 | 8,240 | | | | 303 / 3,501 |
| Merge: non-mana cost components ({Q}, sacrifice, discard, exile from graveyard, return, tap others, counters, {10}) and kicker/multikicker (702.33) | 32,116 | 8,852 (27.6%) | 23,216 | 0 | 48 | 341 / 3,501 |
| Independent-review fixes (intervening-if scope, "other" in event conditions, per-opponent counts, 205.4e) | 32,116 | 8,855 (27.6%) | 23,213 | 0 | 48 | 342 / 3,501 |
| PR #6 merges so far: shared context contract, statics, optional payments, resolution refs, selectors, permissions, trigger context + events; legality follows the card data (48 Unfinity sticker sheets = the MANUAL cards leave the denominator) | 32,068 | 10,304 (32.1%) | 21,764 | 0 | 0 | 478 / 3,501 |

83 banned cards are excluded. The queue (`commander_rules_coverage.md`) is ranked by pod cards,
pod commanders, how many cards a feature is the *only* missing piece for, then Commander cards
needing it. Current leaders: unsupported mana-ability wordings,

**Commander eligibility and color identity** (`app/rules/commander.py`) follow CR 903.3 (a
legendary creature, Vehicle, or Spacecraft with power/toughness, or "can be your commander"),
702.124 (partner, partner—[text], partner with, choose a Background, Doctor's companion) and
903.4. The same implementation serves the deck checks, the lobby and the rules engine. Checked
against Scryfall's `color_identity` over the whole pool: the only differences are 104 lands with
basic land types (the CR handles those with 903.5d, which the deck checks apply separately,
plus the 903.12e colorless exception) and 3 meld results that can't be in a deck.

**Companion** (wave 38D, CR 702.139, 116.2g, 103.2b): the ten conditions are predicates in `commander.COMPANION_RESTRICTIONS` over the
starting deck, the commander included (702.139b; Yorion can never qualify in Commander, 903.5a). The deck check reports a failing or second
companion; the special action (pay {3}, main phase, empty stack, once per game) is `activate_ability` on the card in the companion zone
and re-checks the deck at the table. A companion in the deck or as the commander does nothing. The Commander rules committee's extra
rule (the companion must fit the commander's color identity and singleton) is not checked.

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
