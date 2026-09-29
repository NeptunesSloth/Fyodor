# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 11:13

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 3115 | 9.7% |
| PARTIAL | 28953 | 90.2% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 61, PARTIAL 3440, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 527 | 235 | Eldrazi Confluence, Divergent Growth, Discreet Retreat |
| 2 | keyword:cycling | keyword | 0 | 300 | 95 | Savai Triome, Deem Worthy, Curator of Mysteries |
| 3 | keyword:protection | keyword | 0 | 186 | 82 | Valeron Outlander, Coast Watcher, Yavimaya Barbarian |
| 4 | template:{M}: Regenerate ~. | activated | 0 | 119 | 56 | Darkling Stalker, Albino Troll, Ranger en-Vec |
| 5 | keyword:flashback | keyword | 0 | 199 | 44 | Cabal Therapy, Scorching Missile, Alter Reality |
| 6 | keyword:crew | keyword | 0 | 181 | 35 | Mindlink Mech, War Balloon, Rover Blades |
| 7 | keyword:convoke | keyword | 0 | 104 | 35 | Vault Guardsman, Pack's Favor, Kavu Primarch |
| 8 | keyword:morph | keyword | 0 | 153 | 34 | Gravel Slinger, Willbender, Brine Elemental |
| 9 | keyword:prowess | keyword | 0 | 93 | 32 | Soul-Scar Mage, Bedlam Reveler, Queen Brahne |
| 10 | keyword:affinity | keyword | 0 | 74 | 29 | Refurbished Familiar, Icebreaker Kraken, Thrumming Hivepool |
| 11 | keyword:echo | keyword | 0 | 50 | 29 | Albino Troll, Keldon Vandals, Hunting Moa |
| 12 | keyword:swampwalk | keyword | 0 | 41 | 25 | Whispering Shade, Dirtwater Wraith, Slithery Stalker |
| 13 | template:Commander creatures you own have “…” | continuous | 0 | 25 | 25 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 14 | template:All Slivers have “…” | continuous | 0 | 27 | 24 | Magma Sliver, Sedge Sliver, Mnemonic Sliver |
| 15 | template:~ can't block. | restriction | 0 | 92 | 21 | Fear of Infinity, Hulking Cyclops, Ozox, the Clattering King |
| 16 | keyword:infect | keyword | 0 | 45 | 21 | Phyrexian Juggernaut, Contagious Nim, Plague Stinger |
| 17 | template:~ enters prepared. | static | 0 | 40 | 21 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 18 | template:Landfall — Whenever N land(s) you control enters, ~ gets ±N/±N until end of turn. | continuous | 0 | 27 | 21 | Akoum Hellhound, Hedron Scrabbler, Hedron Rover |
| 19 | template:~ can block only creatures with flying. | static | 0 | 30 | 20 | Welkin Tern, Devoted Grafkeeper // Departed Soulkeeper, Cloud Elemental |
| 20 | template:{M}: ~ gets ±N/±N until end of turn. Activate only once each turn. | activated | 0 | 28 | 20 | Mindful Biomancer, Frilled Oculus, Twinblade Slasher |
| 21 | keyword:suspend | keyword | 0 | 70 | 19 | Lotus Bloom, Resurgent Belief, Glimpse of Tomorrow |
| 22 | keyword:exalted | keyword | 0 | 34 | 19 | Aven Squire, Finest Hour, Nefarox, Overlord of Grixis |
| 23 | template:~ enters with N ±N/±N counter(s) on it. | replacement | 0 | 163 | 18 | Yorvo, Lord of Garenbrig, Shrewd Hatchling, Benevolent Hydra |
| 24 | keyword:changeling | keyword | 0 | 62 | 18 | Barkform Harvester, Guardian Gladewalker, Wings of Velis Vel |
| 25 | keyword:forestwalk | keyword | 0 | 28 | 18 | Zendikar Farguide, Zodiac Rabbit, Willow Dryad |
| 26 | keyword:cumulative upkeep | keyword | 0 | 80 | 17 | Prismatic Circle, Musician, Illusionary Terrain |
| 27 | template:~ attacks each combat if able. | static | 0 | 63 | 17 | Phyrexian Juggernaut, Ashen Monstrosity, Bloodrock Cyclops |
| 28 | keyword:banding | keyword | 0 | 24 | 17 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 29 | keyword:cascade | keyword | 0 | 37 | 16 | Etherium-Horn Sorcerer, Call Forth the Tempest, Call Forth the Tempest |
| 30 | template:~ can't be blocked. | restriction | 0 | 60 | 15 | Gilded Scuttler, Tidal Kraken, Talas Warrior |
| 31 | template:At the beginning of your upkeep, sacrifice ~ unless you pay {M}. | triggered | 0 | 44 | 15 | Justice, Phantasmal Forces, Forethought Amulet |
| 32 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 15 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 33 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 34 | keyword:madness | keyword | 0 | 60 | 14 | Strength of Lunacy, Muck Drubb, Gisa's Bidding |
| 35 | keyword:unearth | keyword | 0 | 56 | 14 | Royal Warden, Phyrexian Dragon Engine, Anathemancer |
| 36 | keyword:buyback | keyword | 0 | 39 | 14 | Walk the Aeons, Spell Burst, Pegasus Stampede |
| 37 | keyword:bushido | keyword | 0 | 35 | 14 | Numai Outcast, Nezumi Ronin, Toshiro Umezawa |
| 38 | keyword:horsemanship | keyword | 0 | 28 | 14 | Wei Strike Force, Ma Chao, Western Warrior, Shu General |
| 39 | template:Soulshift N | static | 0 | 25 | 14 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 40 | keyword:mountainwalk | keyword | 0 | 17 | 14 | Zodiac Goat, Mountain Goat, Goblin Spelunkers |
| 41 | keyword:ward | keyword | 0 | 186 | 12 | Tyranid Harridan, Grey Host Reinforcements, Cactusfolk Sureshot |
| 42 | keyword:foretell | keyword | 0 | 51 | 12 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 43 | keyword:storm | keyword | 0 | 35 | 12 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 44 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 45 | template:When ~ becomes the target of a spell or ability, sacrifice it. | triggered | 0 | 15 | 12 | Tar Pit Warrior, Skulking Knight, Phantom Beast |
| 46 | template:{M}, {M}: Investigate. | activated | 0 | 13 | 12 | Dining Room, Library, Kitchen |
| 47 | template:When ~ enters, return N land(s) you control to its owner's hand. | triggered | 0 | 12 | 12 | Selesnya Sanctuary, Simic Growth Chamber, Rakdos Carnarium |
| 48 | keyword:evoke | keyword | 0 | 35 | 11 | Walker of the Grove, Grief, Mournwhelk |
| 49 | keyword:islandwalk | keyword | 0 | 34 | 11 | Goblin Flotilla, Merrow Harbinger, Pale Bears |
| 50 | template:Creatures you control get ±N/±N. | continuous | 0 | 34 | 11 | Angelic Shield, The Arkenstone // Seek the Heart, In the Trenches |
| 51 | keyword:wither | keyword | 0 | 26 | 11 | Twinblade Slasher, Boggart Ram-Gang, Noxious Hatchling |
| 52 | template:As ~ enters, you may pay N life(s). If you don't, it enters tapped. | replacement | 0 | 26 | 11 | Witch Enchanter // Witch-Blessed Meadow, Fell the Profane // Fell Mire, Stomping Ground |
| 53 | template:Bloodthirst N | static | 0 | 23 | 11 | Carnage Wurm, Skarrgan Skybreaker, Indoraptor, the Perfect Hybrid |
| 54 | keyword:dash | keyword | 0 | 22 | 11 | Warbringer, Warbringer, Kolaghan Forerunners |
| 55 | template:~ deals N damage to target attacking or blocking creature. | spell_effect | 0 | 15 | 11 | Hamato Ninpō, Impeccable Timing, Sandblast |
| 56 | keyword:rebound | keyword | 0 | 34 | 10 | World at War, Faithless Salvaging, Staggershock |
| 57 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 58 | template:Renown N | static | 0 | 20 | 10 | Rhox Maulers, Stalwart Aven, Relic Seeker |
| 59 | keyword:fabricate | keyword | 0 | 16 | 10 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 60 | keyword:unleash | keyword | 0 | 15 | 10 | Rakdos Drake, Grim Roustabout, Chaos Imps |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 2042 | 15879 | 0 | 0 |
| Artifact | 410 | 3183 | 0 | 0 |
| Enchantment | 59 | 3588 | 0 | 0 |
| Sorcery | 168 | 3400 | 0 | 0 |
| Instant | 311 | 3443 | 0 | 0 |
| Land | 357 | 855 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 13854, keyword 13820, spell_effect 9164, activated 7355, continuous 4285, static 3931, mana_ability 2177, replacement 1974, restriction 1493, loyalty 882, prevention 323, additional_cost 307, cost_modifier 261, characteristic_defining 248, permission 214, alternative_cost 182
