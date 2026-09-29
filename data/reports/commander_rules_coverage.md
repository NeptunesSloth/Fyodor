# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 05:45

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 921 | 2.9% |
| PARTIAL | 31147 | 97.0% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 37, PARTIAL 3464, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 832 | 356 | Talisman of Progress, Eldrazi Confluence, Divergent Growth |
| 2 | template:{M}: ~ gets ±N/±N until end of turn. | activated | 0 | 270 | 134 | Whispering Shade, Darkling Stalker, Dirtwater Wraith |
| 3 | template:~ enters tapped. | replacement | 0 | 545 | 117 | Savai Triome, Timber Gorge, Whiplash, Vengeful Engineer |
| 4 | keyword:protection | keyword | 0 | 186 | 71 | Valeron Outlander, Coast Watcher, Yavimaya Barbarian |
| 5 | template:Target creature gets ±N/±N until end of turn. | spell_effect | 0 | 129 | 53 | Bull Rush, Throttle, Pack's Favor |
| 6 | template:{M}: Regenerate ~. | activated | 0 | 119 | 50 | Darkling Stalker, Albino Troll, Ranger en-Vec |
| 7 | template:When ~ enters, you gain N life(s). | triggered | 0 | 119 | 44 | Illegitimate Business, Kazandu Refuge, Mindful Biomancer |
| 8 | keyword:flash | keyword | 0 | 608 | 33 | One with the Kami, Theorist's Proxy, Vizier of Deferment |
| 9 | template:{M}, {M}, Sacrifice ~: Draw N card(s). | activated | 0 | 66 | 32 | Courier's Briefcase, Airship Engine Room, Fiery Islet |
| 10 | keyword:morph | keyword | 0 | 153 | 31 | Gravel Slinger, Willbender, Brine Elemental |
| 11 | keyword:cycling | keyword | 0 | 300 | 30 | Savai Triome, Deem Worthy, Curator of Mysteries |
| 12 | template:When ~ enters, draw N card(s). | triggered | 0 | 130 | 29 | Messenger Falcons, Rune of Sustenance, Muse Drake |
| 13 | template:~ deals N damage to any target. | spell_effect | 0 | 107 | 25 | Staggershock, Blaze, Flame Jab |
| 14 | template:{M}, {M}: Tap target creature. | activated | 0 | 39 | 25 | Checkpoint Officer, Dazzling Ramparts, Rathi Trapper |
| 15 | template:Commander creatures you own have “…” | continuous | 0 | 25 | 25 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 16 | keyword:prowess | keyword | 0 | 93 | 24 | Soul-Scar Mage, Bedlam Reveler, Queen Brahne |
| 17 | template:All Slivers have “…” | continuous | 0 | 27 | 24 | Magma Sliver, Sedge Sliver, Mnemonic Sliver |
| 18 | keyword:hexproof | keyword | 0 | 88 | 23 | Soul of the Rapids, Flora Colossus, Troll Ascetic |
| 19 | template:When ~ enters, scry N. | triggered | 0 | 68 | 23 | Inquisitive Puppet, Mana Geode, Haunt of the Dead Marshes |
| 20 | keyword:swampwalk | keyword | 0 | 41 | 22 | Whispering Shade, Dirtwater Wraith, Slithery Stalker |
| 21 | template:~ can't block. | restriction | 0 | 92 | 20 | Fear of Infinity, Hulking Cyclops, Ozox, the Clattering King |
| 22 | template:Landfall — Whenever N land(s) you control enters, ~ gets ±N/±N until end of turn. | continuous | 0 | 27 | 20 | Akoum Hellhound, Hedron Scrabbler, Hedron Rover |
| 23 | template:Creatures you control get ±N/±N until end of turn. | spell_effect | 0 | 40 | 19 | Ethereal Guidance, Plated Onslaught, Bar the Door |
| 24 | template:~ can block only creatures with flying. | static | 0 | 30 | 19 | Welkin Tern, Devoted Grafkeeper // Departed Soulkeeper, Cloud Elemental |
| 25 | template:{M}: ~ gets ±N/±N until end of turn. Activate only once each turn. | activated | 0 | 28 | 19 | Mindful Biomancer, Frilled Oculus, Twinblade Slasher |
| 26 | keyword:affinity | keyword | 0 | 74 | 18 | Refurbished Familiar, Icebreaker Kraken, Thrumming Hivepool |
| 27 | template:~ enters prepared. | static | 0 | 40 | 18 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 28 | keyword:forestwalk | keyword | 0 | 28 | 18 | Zendikar Farguide, Zodiac Rabbit, Willow Dryad |
| 29 | template:Whenever ~ attacks, it gets ±N/±N until end of turn. | triggered | 0 | 23 | 18 | Steadfast Cathar, Brazen Wolves, Charging Bandits |
| 30 | template:When ~ dies, draw N card(s). | triggered | 0 | 26 | 17 | Youthful Scholar, Kingfisher, Buzz Bots |
| 31 | keyword:crew | keyword | 0 | 181 | 16 | Mindlink Mech, War Balloon, Rover Blades |
| 32 | keyword:banding | keyword | 0 | 24 | 16 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 33 | template:Target creature gets ±N/±N and gains trample until end of turn. | spell_effect | 0 | 22 | 16 | Tread Upon, Unnatural Predation, Collision // Colossus |
| 34 | template:~ attacks each combat if able. | static | 0 | 63 | 15 | Phyrexian Juggernaut, Ashen Monstrosity, Bloodrock Cyclops |
| 35 | keyword:infect | keyword | 0 | 45 | 15 | Phyrexian Juggernaut, Contagious Nim, Plague Stinger |
| 36 | template:{M}: ~ deals N damage to any target. | activated | 0 | 37 | 15 | Shivan Hellkite, Kamahl, Pit Fighter, Valakut Invoker |
| 37 | keyword:exalted | keyword | 0 | 34 | 15 | Aven Squire, Finest Hour, Nefarox, Overlord of Grixis |
| 38 | template:{M}: Creatures you control get ±N/±N until end of turn. | activated | 0 | 26 | 15 | Water Tribe Captain, Akroan Phalanx, Gerrard's Battle Cry |
| 39 | template:{M}: Target creature gets ±N/±N until end of turn. | activated | 0 | 25 | 15 | Wyluli Wolf, Ghitu War Cry, Scale of Chiss-Goria |
| 40 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 41 | template:~ can't be blocked. | restriction | 0 | 60 | 14 | Gilded Scuttler, Tidal Kraken, Talas Warrior |
| 42 | template:~ deals N damage to target creature. | spell_effect | 0 | 52 | 14 | Deem Worthy, Harvest Pyre, Thunderclap |
| 43 | keyword:echo | keyword | 0 | 50 | 14 | Albino Troll, Keldon Vandals, Hunting Moa |
| 44 | template:{M}, {M}: Draw N card(s), then discard N card(s). | activated | 0 | 30 | 14 | Troyan, Gutsy Explorer, Captain of Umbar, Agna Qel'a |
| 45 | template:When ~ enters, target creature gets ±N/±N until end of turn. | triggered | 0 | 23 | 14 | Vulshok Heartstoker, Ms. Marvel, Elastic Ally, Affa Guard Hound |
| 46 | keyword:convoke | keyword | 0 | 104 | 13 | Vault Guardsman, Pack's Favor, Kavu Primarch |
| 47 | keyword:cumulative upkeep | keyword | 0 | 80 | 13 | Prismatic Circle, Musician, Illusionary Terrain |
| 48 | keyword:shroud | keyword | 0 | 35 | 13 | Isleback Spawn, Pincher Beetles, Nimble Mongoose |
| 49 | template:{M}: ~ gains flying until end of turn. | activated | 0 | 32 | 13 | Stromgald Crusader, Goblin Balloon Brigade, Stream Hopper |
| 50 | keyword:horsemanship | keyword | 0 | 28 | 13 | Wei Strike Force, Ma Chao, Western Warrior, Shu General |
| 51 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 13 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 52 | template:Draw N card(s). | spell_effect | 0 | 328 | 12 | Instill Infection, Blur, Refocus |
| 53 | template:When ~ enters, put a ±N/±N counter(s) on target creature. | triggered | 0 | 26 | 12 | Guardian Gladewalker, Contagion Clasp, Satyr Grovedancer |
| 54 | template:Soulshift N | static | 0 | 25 | 12 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 55 | template:{M}, {M}: Target creature gets ±N/±N until end of turn. | activated | 0 | 22 | 12 | Tuknir Deathlock, Thriss, Nantuko Primus, Ceta Disciple |
| 56 | keyword:mountainwalk | keyword | 0 | 17 | 12 | Zodiac Goat, Mountain Goat, Goblin Spelunkers |
| 57 | template:At the beginning of your upkeep, sacrifice ~ unless you pay {M}. | triggered | 0 | 44 | 11 | Justice, Phantasmal Forces, Forethought Amulet |
| 58 | keyword:cascade | keyword | 0 | 37 | 11 | Etherium-Horn Sorcerer, Call Forth the Tempest, Call Forth the Tempest |
| 59 | keyword:bushido | keyword | 0 | 35 | 11 | Numai Outcast, Nezumi Ronin, Toshiro Umezawa |
| 60 | template:{M}: ~ gains first strike until end of turn. | activated | 0 | 28 | 11 | Unyielding Krumar, Burning Shield Askari, Truefire Paladin |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 861 | 17060 | 0 | 0 |
| Artifact | 94 | 3499 | 0 | 0 |
| Enchantment | 8 | 3639 | 0 | 0 |
| Sorcery | 0 | 3568 | 0 | 0 |
| Instant | 0 | 3754 | 0 | 0 |
| Land | 42 | 1170 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 13854, keyword 13820, spell_effect 9164, activated 7355, continuous 4285, static 3931, mana_ability 2177, replacement 1974, restriction 1493, loyalty 882, prevention 323, additional_cost 307, cost_modifier 261, characteristic_defining 248, permission 214, alternative_cost 182
