# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 06:00

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 2434 | 7.6% |
| PARTIAL | 29634 | 92.3% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 48, PARTIAL 3453, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 832 | 409 | Talisman of Progress, Eldrazi Confluence, Divergent Growth |
| 2 | keyword:cycling | keyword | 0 | 300 | 90 | Savai Triome, Deem Worthy, Curator of Mysteries |
| 3 | keyword:protection | keyword | 0 | 186 | 82 | Valeron Outlander, Coast Watcher, Yavimaya Barbarian |
| 4 | template:{M}: Regenerate ~. | activated | 0 | 119 | 56 | Darkling Stalker, Albino Troll, Ranger en-Vec |
| 5 | keyword:morph | keyword | 0 | 153 | 34 | Gravel Slinger, Willbender, Brine Elemental |
| 6 | keyword:convoke | keyword | 0 | 104 | 29 | Vault Guardsman, Pack's Favor, Kavu Primarch |
| 7 | keyword:prowess | keyword | 0 | 93 | 29 | Soul-Scar Mage, Bedlam Reveler, Queen Brahne |
| 8 | keyword:affinity | keyword | 0 | 74 | 29 | Refurbished Familiar, Icebreaker Kraken, Thrumming Hivepool |
| 9 | keyword:echo | keyword | 0 | 50 | 28 | Albino Troll, Keldon Vandals, Hunting Moa |
| 10 | keyword:swampwalk | keyword | 0 | 41 | 25 | Whispering Shade, Dirtwater Wraith, Slithery Stalker |
| 11 | template:Commander creatures you own have “…” | continuous | 0 | 25 | 25 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 12 | template:All Slivers have “…” | continuous | 0 | 27 | 24 | Magma Sliver, Sedge Sliver, Mnemonic Sliver |
| 13 | keyword:flashback | keyword | 0 | 199 | 23 | Cabal Therapy, Scorching Missile, Alter Reality |
| 14 | keyword:crew | keyword | 0 | 181 | 23 | Mindlink Mech, War Balloon, Rover Blades |
| 15 | template:~ can't block. | restriction | 0 | 92 | 21 | Fear of Infinity, Hulking Cyclops, Ozox, the Clattering King |
| 16 | template:Landfall — Whenever N land(s) you control enters, ~ gets ±N/±N until end of turn. | continuous | 0 | 27 | 21 | Akoum Hellhound, Hedron Scrabbler, Hedron Rover |
| 17 | template:~ enters prepared. | static | 0 | 40 | 20 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 18 | template:~ can block only creatures with flying. | static | 0 | 30 | 20 | Welkin Tern, Devoted Grafkeeper // Departed Soulkeeper, Cloud Elemental |
| 19 | template:{M}: ~ gets ±N/±N until end of turn. Activate only once each turn. | activated | 0 | 28 | 20 | Mindful Biomancer, Frilled Oculus, Twinblade Slasher |
| 20 | keyword:infect | keyword | 0 | 45 | 18 | Phyrexian Juggernaut, Contagious Nim, Plague Stinger |
| 21 | keyword:exalted | keyword | 0 | 34 | 18 | Aven Squire, Finest Hour, Nefarox, Overlord of Grixis |
| 22 | keyword:forestwalk | keyword | 0 | 28 | 18 | Zendikar Farguide, Zodiac Rabbit, Willow Dryad |
| 23 | keyword:cumulative upkeep | keyword | 0 | 80 | 17 | Prismatic Circle, Musician, Illusionary Terrain |
| 24 | keyword:banding | keyword | 0 | 24 | 17 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 25 | template:~ attacks each combat if able. | static | 0 | 63 | 16 | Phyrexian Juggernaut, Ashen Monstrosity, Bloodrock Cyclops |
| 26 | keyword:cascade | keyword | 0 | 37 | 16 | Etherium-Horn Sorcerer, Call Forth the Tempest, Call Forth the Tempest |
| 27 | keyword:suspend | keyword | 0 | 70 | 15 | Lotus Bloom, Resurgent Belief, Glimpse of Tomorrow |
| 28 | keyword:changeling | keyword | 0 | 62 | 15 | Barkform Harvester, Guardian Gladewalker, Wings of Velis Vel |
| 29 | template:~ can't be blocked. | restriction | 0 | 60 | 15 | Gilded Scuttler, Tidal Kraken, Talas Warrior |
| 30 | template:{M}, {M}: Draw N card(s), then discard N card(s). | activated | 0 | 30 | 15 | Troyan, Gutsy Explorer, Captain of Umbar, Agna Qel'a |
| 31 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 15 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 32 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 33 | template:At the beginning of your upkeep, sacrifice ~ unless you pay {M}. | triggered | 0 | 44 | 14 | Justice, Phantasmal Forces, Forethought Amulet |
| 34 | keyword:bushido | keyword | 0 | 35 | 14 | Numai Outcast, Nezumi Ronin, Toshiro Umezawa |
| 35 | keyword:horsemanship | keyword | 0 | 28 | 14 | Wei Strike Force, Ma Chao, Western Warrior, Shu General |
| 36 | template:Soulshift N | static | 0 | 25 | 14 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 37 | keyword:mountainwalk | keyword | 0 | 17 | 14 | Zodiac Goat, Mountain Goat, Goblin Spelunkers |
| 38 | keyword:madness | keyword | 0 | 60 | 13 | Strength of Lunacy, Muck Drubb, Gisa's Bidding |
| 39 | template:When ~ enters, put a ±N/±N counter(s) on target creature. | triggered | 0 | 26 | 12 | Guardian Gladewalker, Contagion Clasp, Satyr Grovedancer |
| 40 | template:When ~ becomes the target of a spell or ability, sacrifice it. | triggered | 0 | 15 | 12 | Tar Pit Warrior, Skulking Knight, Phantom Beast |
| 41 | template:{M}, {M}: Investigate. | activated | 0 | 13 | 12 | Dining Room, Library, Kitchen |
| 42 | template:When ~ enters, return N land(s) you control to its owner's hand. | triggered | 0 | 12 | 12 | Selesnya Sanctuary, Simic Growth Chamber, Rakdos Carnarium |
| 43 | template:~ enters with N ±N/±N counter(s) on it. | replacement | 0 | 163 | 11 | Yorvo, Lord of Garenbrig, Shrewd Hatchling, Benevolent Hydra |
| 44 | keyword:islandwalk | keyword | 0 | 34 | 11 | Goblin Flotilla, Merrow Harbinger, Pale Bears |
| 45 | template:When ~ enters, draw N card(s), then discard N card(s). | triggered | 0 | 27 | 11 | Owl Familiar, Sidequest: Card Collection // Magicked Card, Overwhelmed Archivist // Archive Haunt |
| 46 | keyword:wither | keyword | 0 | 26 | 11 | Twinblade Slasher, Boggart Ram-Gang, Noxious Hatchling |
| 47 | template:As ~ enters, you may pay N life(s). If you don't, it enters tapped. | replacement | 0 | 26 | 11 | Witch Enchanter // Witch-Blessed Meadow, Fell the Profane // Fell Mire, Stomping Ground |
| 48 | template:Bloodthirst N | static | 0 | 23 | 11 | Carnage Wurm, Skarrgan Skybreaker, Indoraptor, the Perfect Hybrid |
| 49 | template:~ deals N damage to target attacking or blocking creature. | spell_effect | 0 | 15 | 11 | Hamato Ninpō, Impeccable Timing, Sandblast |
| 50 | keyword:unearth | keyword | 0 | 56 | 10 | Royal Warden, Phyrexian Dragon Engine, Anathemancer |
| 51 | keyword:foretell | keyword | 0 | 51 | 10 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 52 | keyword:buyback | keyword | 0 | 39 | 10 | Walk the Aeons, Spell Burst, Pegasus Stampede |
| 53 | keyword:splice | keyword | 0 | 30 | 10 | Evermind, Horobi's Whisper, Desperate Ritual |
| 54 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 55 | template:Renown N | static | 0 | 20 | 10 | Rhox Maulers, Stalwart Aven, Relic Seeker |
| 56 | keyword:fabricate | keyword | 0 | 16 | 10 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 57 | keyword:unleash | keyword | 0 | 15 | 10 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 58 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 59 | template:Sliver creatures you control have “…” | continuous | 0 | 10 | 10 | Capricious Sliver, Lavabelly Sliver, Regal Sliver |
| 60 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 1680 | 16241 | 0 | 0 |
| Artifact | 302 | 3291 | 0 | 0 |
| Enchantment | 35 | 3612 | 0 | 0 |
| Sorcery | 93 | 3475 | 0 | 0 |
| Instant | 260 | 3494 | 0 | 0 |
| Land | 260 | 952 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 13854, keyword 13820, spell_effect 9164, activated 7355, continuous 4285, static 3931, mana_ability 2177, replacement 1974, restriction 1493, loyalty 882, prevention 323, additional_cost 307, cost_modifier 261, characteristic_defining 248, permission 214, alternative_cost 182
