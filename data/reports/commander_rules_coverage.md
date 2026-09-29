# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 16:30

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 4435 | 13.8% |
| PARTIAL | 27633 | 86.0% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 106, PARTIAL 3395, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 196 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 3 | template:Commander creatures you own have “…” | continuous | 0 | 23 | 23 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 4 | keyword:madness | keyword | 0 | 60 | 19 | Strength of Lunacy, Muck Drubb, Gisa's Bidding |
| 5 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 6 | keyword:unearth | keyword | 0 | 56 | 17 | Royal Warden, Phyrexian Dragon Engine, Anathemancer |
| 7 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 17 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 8 | template:All Slivers have “…” | continuous | 0 | 17 | 17 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 9 | template:Soulshift N | static | 0 | 25 | 16 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 10 | keyword:ward | keyword | 0 | 186 | 15 | Tyranid Harridan, Grey Host Reinforcements, Cactusfolk Sureshot |
| 11 | keyword:buyback | keyword | 0 | 39 | 15 | Walk the Aeons, Spell Burst, Pegasus Stampede |
| 12 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 13 | keyword:storm | keyword | 0 | 35 | 13 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 14 | keyword:flanking | keyword | 0 | 29 | 13 | Burning Shield Askari, Benalish Cavalry, Mtenda Herder |
| 15 | keyword:dash | keyword | 0 | 22 | 13 | Warbringer, Warbringer, Kolaghan Forerunners |
| 16 | keyword:foretell | keyword | 0 | 51 | 12 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 17 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 18 | template:Counter target spell unless its controller pays {M}. | spell_effect | 0 | 30 | 12 | Reasonable Doubt, Lose Focus, Runeboggle |
| 19 | template:As ~ enters, you may pay N life(s). If you don't, it enters tapped. | replacement | 0 | 26 | 12 | Witch Enchanter // Witch-Blessed Meadow, Fell the Profane // Fell Mire, Stomping Ground |
| 20 | template:When ~ becomes the target of a spell or ability, sacrifice it. | triggered | 0 | 15 | 12 | Tar Pit Warrior, Skulking Knight, Phantom Beast |
| 21 | template:{M}, {M}: Investigate. | activated | 0 | 13 | 12 | Dining Room, Library, Kitchen |
| 22 | template:~ can't be countered. | restriction | 0 | 87 | 11 | Supreme Verdict, Rending Volley, Heated Debate |
| 23 | keyword:evoke | keyword | 0 | 35 | 11 | Walker of the Grove, Grief, Mournwhelk |
| 24 | keyword:rebound | keyword | 0 | 34 | 11 | World at War, Faithless Salvaging, Staggershock |
| 25 | keyword:backup | keyword | 0 | 25 | 11 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 26 | keyword:fabricate | keyword | 0 | 16 | 11 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 27 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 28 | keyword:toxic | keyword | 0 | 37 | 10 | Tyrranax Atrocity, Bloated Contaminator, Bloodroot Apothecary |
| 29 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 30 | template:~ can't attack unless defending player controls an Island. | restriction | 0 | 25 | 10 | Red Cliffs Armada, Zhou Yu, Chief Commander, Floodchaser |
| 31 | keyword:persist | keyword | 0 | 24 | 10 | Puppeteer Clique, Furystoke Giant, Trapjaw Kelpie |
| 32 | keyword:improvise | keyword | 0 | 23 | 10 | Fen Hauler, Whir of Invention, Sly Requisitioner |
| 33 | keyword:undying | keyword | 0 | 22 | 10 | Demonlord of Ashmouth, Hound of Griselbrand, Vengeful Vampire |
| 34 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 35 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 10 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 36 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 37 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 38 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 39 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 40 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 41 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 42 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 43 | template:{M}: Return ~ to its owner's hand. | activated | 0 | 33 | 9 | Palinchron, Etherium-Horn Sorcerer, Shackles |
| 44 | keyword:delve | keyword | 0 | 28 | 9 | Empty the Pits, Dead Drop, Afterlife from the Loam |
| 45 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 46 | template:Modular N | static | 0 | 23 | 9 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 47 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 48 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 9 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 49 | template:When ~ enters, exile target nonland permanent an opponent controls until ~ leaves the battlefield. | triggered | 0 | 19 | 9 | Hieromancer's Cage, Journey to Oblivion, Static Net |
| 50 | template:Whenever ~ deals combat damage to a player, put a ±N/±N counter(s) on it. | triggered | 0 | 19 | 9 | Skullbriar, the Walking Grave, Hexgold Slith, Arcbound Slith |
| 51 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 52 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 53 | template:{M}, {M}: Target player mills N card(s). | activated | 0 | 12 | 9 | Vedalken Entrancer, Persistent Petitioners, Relic Golem |
| 54 | template:~ deals N damage to any target and you gain N life(s). | spell_effect | 0 | 12 | 9 | Agonizing Syphon, Integrity // Intervention, Vampiric Feast |
| 55 | template:Sliver creatures you control have “…” | continuous | 0 | 9 | 9 | Capricious Sliver, Lavabelly Sliver, Regal Sliver |
| 56 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 57 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 8 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 58 | keyword:encore | keyword | 0 | 26 | 8 | Impulsivity, Sliver Gravemother, Belonging |
| 59 | keyword:myriad | keyword | 0 | 23 | 8 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 60 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 8 | Voice of the Blessed, Essence Channeler, Wall of Limbs |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 3055 | 14866 | 0 | 0 |
| Artifact | 521 | 3072 | 0 | 0 |
| Enchantment | 104 | 3543 | 0 | 0 |
| Sorcery | 222 | 3346 | 0 | 0 |
| Instant | 404 | 3350 | 0 | 0 |
| Land | 416 | 796 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14089, spell_effect 9123, activated 7358, continuous 4014, static 3095, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
