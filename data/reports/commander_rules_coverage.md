# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 16:50

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 4685 | 14.6% |
| PARTIAL | 27383 | 85.3% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 110, PARTIAL 3391, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 196 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:~ enters prepared. | static | 0 | 40 | 25 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 3 | template:Commander creatures you own have “…” | continuous | 0 | 23 | 23 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 4 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 5 | template:All Slivers have “…” | continuous | 0 | 17 | 17 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 6 | keyword:storm | keyword | 0 | 35 | 16 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 7 | keyword:flanking | keyword | 0 | 29 | 14 | Burning Shield Askari, Benalish Cavalry, Mtenda Herder |
| 8 | keyword:foretell | keyword | 0 | 51 | 13 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 9 | keyword:evoke | keyword | 0 | 35 | 12 | Walker of the Grove, Grief, Mournwhelk |
| 10 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 11 | keyword:backup | keyword | 0 | 25 | 12 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 12 | template:~ can't be countered. | restriction | 0 | 87 | 11 | Supreme Verdict, Rending Volley, Heated Debate |
| 13 | keyword:rebound | keyword | 0 | 34 | 11 | World at War, Faithless Salvaging, Staggershock |
| 14 | keyword:persist | keyword | 0 | 24 | 11 | Puppeteer Clique, Furystoke Giant, Trapjaw Kelpie |
| 15 | keyword:improvise | keyword | 0 | 23 | 11 | Fen Hauler, Whir of Invention, Sly Requisitioner |
| 16 | keyword:fabricate | keyword | 0 | 16 | 11 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 17 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 18 | keyword:toxic | keyword | 0 | 37 | 10 | Tyrranax Atrocity, Bloated Contaminator, Bloodroot Apothecary |
| 19 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 20 | keyword:delve | keyword | 0 | 28 | 10 | Empty the Pits, Dead Drop, Afterlife from the Loam |
| 21 | template:~ can't attack unless defending player controls an Island. | restriction | 0 | 25 | 10 | Red Cliffs Armada, Zhou Yu, Chief Commander, Floodchaser |
| 22 | keyword:undying | keyword | 0 | 22 | 10 | Demonlord of Ashmouth, Hound of Griselbrand, Vengeful Vampire |
| 23 | template:When ~ enters, exile target nonland permanent an opponent controls until ~ leaves the battlefield. | triggered | 0 | 19 | 10 | Hieromancer's Cage, Journey to Oblivion, Static Net |
| 24 | template:Whenever ~ deals combat damage to a player, put a ±N/±N counter(s) on it. | triggered | 0 | 19 | 10 | Skullbriar, the Walking Grave, Hexgold Slith, Arcbound Slith |
| 25 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 26 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 27 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 10 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 28 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 29 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 30 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 31 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 32 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 33 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 34 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 35 | template:{M}: Return ~ to its owner's hand. | activated | 0 | 33 | 9 | Palinchron, Etherium-Horn Sorcerer, Shackles |
| 36 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 37 | template:Modular N | static | 0 | 23 | 9 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 38 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 39 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 9 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 40 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 9 | Voice of the Blessed, Essence Channeler, Wall of Limbs |
| 41 | template:All creatures get ±N/±N until end of turn. | spell_effect | 0 | 18 | 9 | Marsh Gas, Choking Miasma, Shrivel |
| 42 | template:At the beginning of the end step, sacrifice ~. | triggered | 0 | 16 | 9 | Impetuous Devils, Underworld Breach, Putrefax |
| 43 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 9 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 44 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 45 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 46 | template:{M}, {M}: Target player mills N card(s). | activated | 0 | 12 | 9 | Vedalken Entrancer, Persistent Petitioners, Relic Golem |
| 47 | template:~ deals N damage to any target and you gain N life(s). | spell_effect | 0 | 12 | 9 | Agonizing Syphon, Integrity // Intervention, Vampiric Feast |
| 48 | template:~ deals N damage to each creature and each player. | spell_effect | 0 | 12 | 9 | Rain of Embers, Famine, Psychotic Haze |
| 49 | template:Sliver creatures you control have “…” | continuous | 0 | 9 | 9 | Capricious Sliver, Lavabelly Sliver, Regal Sliver |
| 50 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 51 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 8 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 52 | keyword:encore | keyword | 0 | 26 | 8 | Impulsivity, Sliver Gravemother, Belonging |
| 53 | keyword:myriad | keyword | 0 | 23 | 8 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 54 | template:Target player discards N card(s). | spell_effect | 0 | 18 | 8 | Mind Rake, Cry of Contrition, Skull Fracture |
| 55 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 8 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 56 | template:~ can block an additional creature each combat. | static | 0 | 12 | 8 | Selesnya Sagittars, Tangleclaw Werewolf // Fibrous Entangler, Tangleclaw Werewolf // Fibrous Entangler |
| 57 | template:When ~ enters, target creature an opponent controls gets ±N/±N until end of turn. | triggered | 0 | 11 | 8 | Humbling Elder, Eyeblight Assassin, Grim Bauble |
| 58 | template:When ~ enters, target creature can't block this turn. | triggered | 0 | 10 | 8 | Unstoppable Ogre, Goblin Shortcutter, Cartouche of Zeal |
| 59 | template:When ~ enters, you lose N life(s). | triggered | 0 | 10 | 8 | Nightdrinker Moroii, Foul Imp, Toxic Abomination |
| 60 | template:{M}, {M}: Search your library for a Rebel permanent card with mana value N or less, put it onto the battlefield, then shuffle. | activated | 0 | 10 | 8 | Ramosian Commander, Blightspeaker, Ramosian Captain |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 3192 | 14729 | 0 | 0 |
| Artifact | 536 | 3057 | 0 | 0 |
| Enchantment | 107 | 3540 | 0 | 0 |
| Sorcery | 233 | 3335 | 0 | 0 |
| Instant | 478 | 3276 | 0 | 0 |
| Land | 440 | 772 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
