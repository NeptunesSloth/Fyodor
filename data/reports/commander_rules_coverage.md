# Commander rules coverage

Card data: Scryfall `2026-11-06T22:06:52.389+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-11-16 23:03

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32138**

| Level | Cards | Share |
|---|---|---|
| FULL | 32126 | 100.0% |
| PARTIAL | 12 | 0.0% |
| REVIEW | 0 | 0.0% |
| MANUAL | 0 | 0.0% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3563** — FULL 3560, PARTIAL 3, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113459
- Automated: 113445 (100.0%) · unrecognized clauses: 14
- Oracle text classified (automated, or sorted into a concrete missing capability): 100.0% · unclassified clauses: 0
- Distinct missing-capability clusters: 12

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 8 | 8 |
| MISSING TRIGGER EVENT | 4 | 4 |
| MISSING SELECTOR | 1 | 1 |
| MISSING COST / PERMISSION RULE | 1 | 1 |
| MISSING MECHANIC | 0 | 0 |
| MISSING REPLACEMENT PATTERN | 0 | 0 |
| MISSING CONTINUOUS EFFECT | 0 | 0 |
| MISSING RESTRICTION | 0 | 0 |
| MISSING COST | 0 | 0 |
| MANA ABILITY WORDING | 0 | 0 |
| UNSUPPORTED ORACLE PATTERN | 0 | 0 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | forage … | 1 | 1 | 1 | Euru, Acorn Scrounger |
| 2 | MISSING TRIGGER EVENT | Whenever you discard N or more cards at random | 1 | 1 | 1 | Chira, All In |
| 3 | MISSING TRIGGER EVENT | Whenever ~ deals combat damage to a player who doesn't have a contract counter | 1 | 1 | 1 | Miss Highwater |
| 4 | MISSING EFFECT | conjure n … | 0 | 2 | 3 | Ruby Collector, Emerald Collector, Case of the Lost Witness |
| 5 | MISSING EFFECT | create a food token … | 0 | 1 | 1 | Overcooked |
| 6 | MISSING EFFECT | for each creature your … | 0 | 1 | 1 | Perforator Crocodile |
| 7 | MISSING EFFECT | if there are n … | 0 | 1 | 1 | Jet Collector |
| 8 | MISSING TRIGGER EVENT | When you cast your second noncreature spell in a turn | 0 | 1 | 1 | Sapphire Collector |
| 9 | MISSING TRIGGER EVENT | When ~ enters the battlefield | 0 | 1 | 1 | Oracle of the Alpha |
| 10 | MISSING COST / PERMISSION RULE | Solved — You may look at … | 0 | 0 | 1 | Case of the Lost Witness |
| 11 | MISSING EFFECT | if you gained n … | 0 | 0 | 1 | Pearl Collector |
| 12 | MISSING SELECTOR | target creature perpetually | 0 | 0 | 1 | Pearl Collector |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | conjure n … | 3 | 2 | 0 | Ruby Collector, Emerald Collector, Case of the Lost Witness |
| 2 | MISSING EFFECT | forage … | 1 | 1 | 1 | Euru, Acorn Scrounger |
| 3 | MISSING TRIGGER EVENT | Whenever you discard N or more cards at random | 1 | 1 | 1 | Chira, All In |
| 4 | MISSING TRIGGER EVENT | Whenever ~ deals combat damage to a player who doesn't have a contract counter | 1 | 1 | 1 | Miss Highwater |
| 5 | MISSING EFFECT | create a food token … | 1 | 1 | 0 | Overcooked |
| 6 | MISSING EFFECT | for each creature your … | 1 | 1 | 0 | Perforator Crocodile |
| 7 | MISSING EFFECT | if there are n … | 1 | 1 | 0 | Jet Collector |
| 8 | MISSING TRIGGER EVENT | When you cast your second noncreature spell in a turn | 1 | 1 | 0 | Sapphire Collector |
| 9 | MISSING TRIGGER EVENT | When ~ enters the battlefield | 1 | 1 | 0 | Oracle of the Alpha |
| 10 | MISSING COST / PERMISSION RULE | Solved — You may look at … | 1 | 0 | 0 | Case of the Lost Witness |
| 11 | MISSING EFFECT | if you gained n … | 1 | 0 | 0 | Pearl Collector |
| 12 | MISSING SELECTOR | target creature perpetually | 1 | 0 | 0 | Pearl Collector |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | template:At the beginning of your second main phase, if there are N or more cards in your graveyard, conjure N card(s) named Mox ~ into your hand. This ability triggers only once. | triggered | 0 | 1 | 1 | Jet Collector |
| 2 | template:Celebration — At the beginning of your end step, create a Food token. If N or more nonland permanents entered the battlefield under your control this turn, instead conjure N card(s) named Food Fight onto the battlefield. | triggered | 0 | 1 | 1 | Overcooked |
| 3 | template:When you attack with N or more creatures, conjure N card(s) named Mox ~ into your hand. This ability triggers only once. | triggered | 0 | 1 | 1 | Ruby Collector |
| 4 | template:When you cast your second noncreature spell in a turn, conjure N card(s) named Mox ~ into your hand. This ability triggers only once. | triggered | 0 | 1 | 1 | Sapphire Collector |
| 5 | template:When you draw your third card in a turn, conjure N card(s) named Mox ~ into your hand. This ability triggers only once. | triggered | 0 | 1 | 1 | Emerald Collector |
| 6 | template:When ~ enters the battlefield, conjure the Power Nine into your library, then shuffle. | triggered | 0 | 1 | 1 | Oracle of the Alpha |
| 7 | template:When ~ enters, for each creature your opponents control, conjure N card(s) named Stab Wound onto the battlefield attached to that creature. | triggered | 0 | 1 | 1 | Perforator Crocodile |
| 8 | template:When ~ enters, you may forage. When you do, conjure N card(s) named Chitterspitter onto the battlefield. | triggered | 0 | 1 | 1 | Euru, Acorn Scrounger |
| 9 | template:Whenever you discard N or more cards at random, select N or more targets at random, choose N or more modes at random, flip N or more coins, or roll N or more dice, put a ±N/±N counter(s) on ~ and create a tapped Treasure token. | triggered | 0 | 1 | 1 | Chira, All In |
| 10 | template:Whenever ~ deals combat damage to a player who doesn't have a contract counter, they may discard their hand. If they do, they draw N card(s) and get a contract counter. For as long as they have a contract counter, when they lose the game, for each artifact and creature they controlled, create N token(s) that's a copy of it. | triggered | 0 | 1 | 1 | Miss Highwater |
| 11 | template:At the beginning of your second main phase, if you gained N or more life this turn, conjure N card(s) named Mox ~ into your hand. This ability triggers only once. | triggered | 0 | 1 | 0 | Pearl Collector |
| 12 | template:Solved — You may look at the top card of your library any time and you may play lands and cast spells from the top of your library. | permission | 0 | 1 | 0 | Case of the Lost Witness |
| 13 | template:When this ~ enters, conjure N card(s) named Fblthp, the Lost into your library, then shuffle. Draw N card(s). | triggered | 0 | 1 | 0 | Case of the Lost Witness |
| 14 | template:{M}: Another target creature perpetually gains lifelink. | activated | 0 | 1 | 0 | Pearl Collector |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Land | 1212 | 0 | 0 | 0 |
| Creature | 17968 | 10 | 0 | 0 |
| Enchantment | 3647 | 2 | 0 | 0 |
| Instant | 3754 | 0 | 0 | 0 |
| Sorcery | 3569 | 0 | 0 | 0 |
| Artifact | 3595 | 0 | 0 | 0 |
| Planeswalker | 320 | 0 | 0 | 0 |
| Battle | 36 | 0 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 15011, keyword 14575, spell_effect 8906, activated 7705, continuous 4117, static 2149, mana_ability 2043, replacement 1967, restriction 1465, loyalty 906, prevention 319, additional_cost 305, cost_modifier 278, characteristic_defining 247, permission 233, alternative_cost 180
