# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 16:40

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 4565 | 14.2% |
| PARTIAL | 27503 | 85.6% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 108, PARTIAL 3393, REVIEW 0, MANUAL 0

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
| 5 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 17 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 6 | template:All Slivers have “…” | continuous | 0 | 17 | 17 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 7 | keyword:storm | keyword | 0 | 35 | 16 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 8 | template:Soulshift N | static | 0 | 25 | 16 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 9 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 10 | keyword:foretell | keyword | 0 | 51 | 13 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 11 | keyword:flanking | keyword | 0 | 29 | 13 | Burning Shield Askari, Benalish Cavalry, Mtenda Herder |
| 12 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 13 | template:As ~ enters, you may pay N life(s). If you don't, it enters tapped. | replacement | 0 | 26 | 12 | Witch Enchanter // Witch-Blessed Meadow, Fell the Profane // Fell Mire, Stomping Ground |
| 14 | keyword:backup | keyword | 0 | 25 | 12 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 15 | template:When ~ becomes the target of a spell or ability, sacrifice it. | triggered | 0 | 15 | 12 | Tar Pit Warrior, Skulking Knight, Phantom Beast |
| 16 | template:{M}, {M}: Investigate. | activated | 0 | 13 | 12 | Dining Room, Library, Kitchen |
| 17 | template:~ can't be countered. | restriction | 0 | 87 | 11 | Supreme Verdict, Rending Volley, Heated Debate |
| 18 | keyword:evoke | keyword | 0 | 35 | 11 | Walker of the Grove, Grief, Mournwhelk |
| 19 | keyword:rebound | keyword | 0 | 34 | 11 | World at War, Faithless Salvaging, Staggershock |
| 20 | keyword:persist | keyword | 0 | 24 | 11 | Puppeteer Clique, Furystoke Giant, Trapjaw Kelpie |
| 21 | keyword:improvise | keyword | 0 | 23 | 11 | Fen Hauler, Whir of Invention, Sly Requisitioner |
| 22 | keyword:fabricate | keyword | 0 | 16 | 11 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 23 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 24 | keyword:toxic | keyword | 0 | 37 | 10 | Tyrranax Atrocity, Bloated Contaminator, Bloodroot Apothecary |
| 25 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 26 | keyword:delve | keyword | 0 | 28 | 10 | Empty the Pits, Dead Drop, Afterlife from the Loam |
| 27 | template:~ can't attack unless defending player controls an Island. | restriction | 0 | 25 | 10 | Red Cliffs Armada, Zhou Yu, Chief Commander, Floodchaser |
| 28 | keyword:undying | keyword | 0 | 22 | 10 | Demonlord of Ashmouth, Hound of Griselbrand, Vengeful Vampire |
| 29 | template:When ~ enters, exile target nonland permanent an opponent controls until ~ leaves the battlefield. | triggered | 0 | 19 | 10 | Hieromancer's Cage, Journey to Oblivion, Static Net |
| 30 | template:Whenever ~ deals combat damage to a player, put a ±N/±N counter(s) on it. | triggered | 0 | 19 | 10 | Skullbriar, the Walking Grave, Hexgold Slith, Arcbound Slith |
| 31 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 32 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 10 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 33 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 34 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 35 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 36 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 37 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 38 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 39 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 40 | template:{M}: Return ~ to its owner's hand. | activated | 0 | 33 | 9 | Palinchron, Etherium-Horn Sorcerer, Shackles |
| 41 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 42 | template:Modular N | static | 0 | 23 | 9 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 43 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 44 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 9 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 45 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 9 | Voice of the Blessed, Essence Channeler, Wall of Limbs |
| 46 | template:All creatures get ±N/±N until end of turn. | spell_effect | 0 | 18 | 9 | Marsh Gas, Choking Miasma, Shrivel |
| 47 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 48 | template:At the beginning of the end step, sacrifice ~. | triggered | 0 | 16 | 9 | Impetuous Devils, Underworld Breach, Putrefax |
| 49 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 9 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 50 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 51 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 52 | template:{M}, {M}: Target player mills N card(s). | activated | 0 | 12 | 9 | Vedalken Entrancer, Persistent Petitioners, Relic Golem |
| 53 | template:~ deals N damage to any target and you gain N life(s). | spell_effect | 0 | 12 | 9 | Agonizing Syphon, Integrity // Intervention, Vampiric Feast |
| 54 | template:~ deals N damage to each creature and each player. | spell_effect | 0 | 12 | 9 | Rain of Embers, Famine, Psychotic Haze |
| 55 | template:Sliver creatures you control have “…” | continuous | 0 | 9 | 9 | Capricious Sliver, Lavabelly Sliver, Regal Sliver |
| 56 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 57 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 8 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 58 | keyword:encore | keyword | 0 | 26 | 8 | Impulsivity, Sliver Gravemother, Belonging |
| 59 | keyword:myriad | keyword | 0 | 23 | 8 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 60 | template:Target player discards N card(s). | spell_effect | 0 | 18 | 8 | Mind Rake, Cry of Contrition, Skull Fracture |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 3117 | 14804 | 0 | 0 |
| Artifact | 532 | 3061 | 0 | 0 |
| Enchantment | 104 | 3543 | 0 | 0 |
| Sorcery | 230 | 3338 | 0 | 0 |
| Instant | 464 | 3290 | 0 | 0 |
| Land | 417 | 795 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14089, spell_effect 9123, activated 7358, continuous 4014, static 3095, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
