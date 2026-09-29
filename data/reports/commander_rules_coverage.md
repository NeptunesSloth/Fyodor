# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 15:30

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 4023 | 12.5% |
| PARTIAL | 28045 | 87.3% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 87, PARTIAL 3414, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 527 | 245 | Eldrazi Confluence, Divergent Growth, Discreet Retreat |
| 2 | keyword:morph | keyword | 0 | 153 | 43 | Gravel Slinger, Willbender, Brine Elemental |
| 3 | keyword:convoke | keyword | 0 | 104 | 38 | Vault Guardsman, Pack's Favor, Kavu Primarch |
| 4 | template:Commander creatures you own have “…” | continuous | 0 | 25 | 25 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 5 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 6 | template:All Slivers have “…” | continuous | 0 | 27 | 24 | Magma Sliver, Sedge Sliver, Mnemonic Sliver |
| 7 | keyword:suspend | keyword | 0 | 70 | 22 | Lotus Bloom, Resurgent Belief, Glimpse of Tomorrow |
| 8 | keyword:cumulative upkeep | keyword | 0 | 80 | 19 | Prismatic Circle, Musician, Illusionary Terrain |
| 9 | keyword:cascade | keyword | 0 | 37 | 19 | Etherium-Horn Sorcerer, Call Forth the Tempest, Call Forth the Tempest |
| 10 | keyword:bushido | keyword | 0 | 35 | 19 | Numai Outcast, Nezumi Ronin, Toshiro Umezawa |
| 11 | keyword:madness | keyword | 0 | 60 | 18 | Strength of Lunacy, Muck Drubb, Gisa's Bidding |
| 12 | keyword:banding | keyword | 0 | 24 | 18 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 13 | keyword:unearth | keyword | 0 | 56 | 17 | Royal Warden, Phyrexian Dragon Engine, Anathemancer |
| 14 | template:Soulshift N | static | 0 | 25 | 16 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 15 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 16 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 16 | keyword:ward | keyword | 0 | 186 | 15 | Tyranid Harridan, Grey Host Reinforcements, Cactusfolk Sureshot |
| 17 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 18 | keyword:buyback | keyword | 0 | 39 | 14 | Walk the Aeons, Spell Burst, Pegasus Stampede |
| 19 | keyword:dash | keyword | 0 | 22 | 13 | Warbringer, Warbringer, Kolaghan Forerunners |
| 20 | keyword:foretell | keyword | 0 | 51 | 12 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 21 | keyword:storm | keyword | 0 | 35 | 12 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 22 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 23 | template:Counter target spell unless its controller pays {M}. | spell_effect | 0 | 30 | 12 | Reasonable Doubt, Lose Focus, Runeboggle |
| 24 | template:As ~ enters, you may pay N life(s). If you don't, it enters tapped. | replacement | 0 | 26 | 12 | Witch Enchanter // Witch-Blessed Meadow, Fell the Profane // Fell Mire, Stomping Ground |
| 25 | template:Bloodthirst N | static | 0 | 23 | 12 | Carnage Wurm, Skarrgan Skybreaker, Indoraptor, the Perfect Hybrid |
| 26 | template:Renown N | static | 0 | 20 | 12 | Rhox Maulers, Stalwart Aven, Relic Seeker |
| 27 | template:When ~ becomes the target of a spell or ability, sacrifice it. | triggered | 0 | 15 | 12 | Tar Pit Warrior, Skulking Knight, Phantom Beast |
| 28 | template:{M}, {M}: Investigate. | activated | 0 | 13 | 12 | Dining Room, Library, Kitchen |
| 29 | template:When ~ enters, return N land(s) you control to its owner's hand. | triggered | 0 | 12 | 12 | Selesnya Sanctuary, Simic Growth Chamber, Rakdos Carnarium |
| 30 | keyword:evoke | keyword | 0 | 35 | 11 | Walker of the Grove, Grief, Mournwhelk |
| 31 | template:Creatures you control get ±N/±N. | continuous | 0 | 34 | 11 | Angelic Shield, The Arkenstone // Seek the Heart, In the Trenches |
| 32 | keyword:megamorph | keyword | 0 | 31 | 11 | Kadena's Silencer, Segmented Krotiq, Kolaghan Stormsinger |
| 33 | keyword:flanking | keyword | 0 | 29 | 11 | Burning Shield Askari, Benalish Cavalry, Mtenda Herder |
| 34 | keyword:backup | keyword | 0 | 25 | 11 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 35 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 36 | template:~ can't be countered. | restriction | 0 | 87 | 10 | Supreme Verdict, Rending Volley, Heated Debate |
| 37 | keyword:toxic | keyword | 0 | 37 | 10 | Tyrranax Atrocity, Bloated Contaminator, Bloodroot Apothecary |
| 38 | keyword:rebound | keyword | 0 | 34 | 10 | World at War, Faithless Salvaging, Staggershock |
| 39 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 40 | template:~ can't attack unless defending player controls an Island. | restriction | 0 | 25 | 10 | Red Cliffs Armada, Zhou Yu, Chief Commander, Floodchaser |
| 41 | keyword:persist | keyword | 0 | 24 | 10 | Puppeteer Clique, Furystoke Giant, Trapjaw Kelpie |
| 42 | keyword:improvise | keyword | 0 | 23 | 10 | Fen Hauler, Whir of Invention, Sly Requisitioner |
| 43 | keyword:undying | keyword | 0 | 22 | 10 | Demonlord of Ashmouth, Hound of Griselbrand, Vengeful Vampire |
| 44 | keyword:fabricate | keyword | 0 | 16 | 10 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 45 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 46 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 10 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 47 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 48 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 49 | template:Sliver creatures you control have “…” | continuous | 0 | 10 | 10 | Capricious Sliver, Lavabelly Sliver, Regal Sliver |
| 50 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 51 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 52 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 53 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 54 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 55 | template:Devoid | static | 0 | 132 | 9 | Void Grafter, Consuming Sinkhole, Slaughter Drone |
| 56 | keyword:delve | keyword | 0 | 28 | 9 | Empty the Pits, Dead Drop, Afterlife from the Loam |
| 57 | template:Modular N | static | 0 | 23 | 9 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 58 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 59 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 9 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 60 | template:Whenever ~ deals combat damage to a player, put a ±N/±N counter(s) on it. | triggered | 0 | 19 | 9 | Skullbriar, the Walking Grave, Hexgold Slith, Arcbound Slith |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 2747 | 15174 | 0 | 0 |
| Artifact | 504 | 3089 | 0 | 0 |
| Enchantment | 63 | 3584 | 0 | 0 |
| Sorcery | 205 | 3363 | 0 | 0 |
| Instant | 382 | 3372 | 0 | 0 |
| Land | 400 | 812 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14866, keyword 13914, spell_effect 9141, activated 7355, continuous 3937, static 3237, mana_ability 2177, replacement 1966, restriction 1473, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
