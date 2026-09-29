# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 17:01

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 4895 | 15.2% |
| PARTIAL | 27173 | 84.6% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 117, PARTIAL 3384, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 197 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:~ enters prepared. | static | 0 | 40 | 25 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 3 | template:Commander creatures you own have “…” | continuous | 0 | 23 | 23 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 4 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 5 | template:All Slivers have “…” | continuous | 0 | 17 | 17 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 6 | keyword:storm | keyword | 0 | 35 | 16 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 7 | keyword:foretell | keyword | 0 | 51 | 13 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 8 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 9 | keyword:backup | keyword | 0 | 25 | 12 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 10 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 11 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 12 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 10 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 13 | template:Modular N | static | 0 | 23 | 10 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 14 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 15 | template:At the beginning of the end step, sacrifice ~. | triggered | 0 | 16 | 10 | Impetuous Devils, Underworld Breach, Putrefax |
| 16 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 17 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 10 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 18 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 19 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 20 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 21 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 22 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 23 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 24 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 25 | template:{M}: Return ~ to its owner's hand. | activated | 0 | 33 | 9 | Palinchron, Etherium-Horn Sorcerer, Shackles |
| 26 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 27 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 28 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 9 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 29 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 9 | Voice of the Blessed, Essence Channeler, Wall of Limbs |
| 30 | template:All creatures get ±N/±N until end of turn. | spell_effect | 0 | 18 | 9 | Marsh Gas, Choking Miasma, Shrivel |
| 31 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 9 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 32 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 33 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 9 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 34 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 35 | template:{M}, {M}: Target player mills N card(s). | activated | 0 | 12 | 9 | Vedalken Entrancer, Persistent Petitioners, Relic Golem |
| 36 | template:~ deals N damage to any target and you gain N life(s). | spell_effect | 0 | 12 | 9 | Agonizing Syphon, Integrity // Intervention, Vampiric Feast |
| 37 | template:~ deals N damage to each creature and each player. | spell_effect | 0 | 12 | 9 | Rain of Embers, Famine, Psychotic Haze |
| 38 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 39 | keyword:encore | keyword | 0 | 26 | 8 | Impulsivity, Sliver Gravemother, Belonging |
| 40 | template:Target player discards N card(s). | spell_effect | 0 | 18 | 8 | Mind Rake, Cry of Contrition, Skull Fracture |
| 41 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 42 | template:~ can block an additional creature each combat. | static | 0 | 12 | 8 | Selesnya Sagittars, Tangleclaw Werewolf // Fibrous Entangler, Tangleclaw Werewolf // Fibrous Entangler |
| 43 | template:When ~ enters, target creature an opponent controls gets ±N/±N until end of turn. | triggered | 0 | 11 | 8 | Humbling Elder, Eyeblight Assassin, Grim Bauble |
| 44 | template:When ~ enters, target creature can't block this turn. | triggered | 0 | 10 | 8 | Unstoppable Ogre, Goblin Shortcutter, Cartouche of Zeal |
| 45 | template:When ~ enters, you lose N life(s). | triggered | 0 | 10 | 8 | Nightdrinker Moroii, Foul Imp, Toxic Abomination |
| 46 | template:{M}, {M}: Search your library for a Rebel permanent card with mana value N or less, put it onto the battlefield, then shuffle. | activated | 0 | 10 | 8 | Ramosian Commander, Blightspeaker, Ramosian Captain |
| 47 | template:Threshold — As long as there are N or more cards in your graveyard, ~ has “…” | continuous | 0 | 9 | 8 | Cephalid Sage, Hunting Grounds, Centaur Chieftain |
| 48 | template:Whenever ~ becomes blocked, it gets ±N/±N until end of turn. | triggered | 0 | 9 | 8 | Deeproot Warrior, Snorting Gahr, Razorclaw Bear |
| 49 | template:Whenever ~ blocks or becomes blocked, it gets ±N/±N until end of turn. | triggered | 0 | 9 | 8 | Raging Gorilla, Brushwagg, Dromosaur |
| 50 | template:Whenever ~ blocks, it gets ±N/±N until end of turn. | triggered | 0 | 9 | 8 | Jareth, Leonine Titan, Shu Defender, Zhao Zilong, Tiger General |
| 51 | template:When ~ enters, return target instant or sorcery card from your graveyard to your hand. | triggered | 0 | 8 | 8 | Izzet Chronarch, Ardent Elementalist, Salvager of Secrets |
| 52 | template:~ enters tapped unless your opponents control N or more lands. | replacement | 0 | 8 | 8 | Turbulent Fen, Turbulent Moor, Turbulent Springs |
| 53 | keyword:ward | keyword | 0 | 97 | 7 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 54 | keyword:disguise | keyword | 0 | 43 | 7 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 55 | keyword:warp | keyword | 0 | 31 | 7 | Starbreach Whale, Knight Luminary, Loading Zone |
| 56 | keyword:overload | keyword | 0 | 27 | 7 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 57 | template:{M}: Untap ~. | activated | 0 | 21 | 7 | Staff of Compleation, Morphling, Glimmerbell |
| 58 | keyword:mentor | keyword | 0 | 19 | 7 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 59 | keyword:prototype | keyword | 0 | 19 | 7 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 60 | keyword:replicate | keyword | 0 | 19 | 7 | Consign to Memory, Psionic Ritual, Lose Focus |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 3359 | 14562 | 0 | 0 |
| Artifact | 546 | 3047 | 0 | 0 |
| Enchantment | 121 | 3526 | 0 | 0 |
| Sorcery | 242 | 3326 | 0 | 0 |
| Instant | 495 | 3259 | 0 | 0 |
| Land | 441 | 771 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
