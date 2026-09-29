# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 11:28

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 3564 | 11.1% |
| PARTIAL | 28504 | 88.8% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 76, PARTIAL 3425, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 527 | 239 | Eldrazi Confluence, Divergent Growth, Discreet Retreat |
| 2 | template:{M}: Regenerate ~. | activated | 0 | 119 | 61 | Darkling Stalker, Albino Troll, Ranger en-Vec |
| 3 | keyword:flashback | keyword | 0 | 199 | 44 | Cabal Therapy, Scorching Missile, Alter Reality |
| 4 | keyword:morph | keyword | 0 | 153 | 40 | Gravel Slinger, Willbender, Brine Elemental |
| 5 | keyword:crew | keyword | 0 | 181 | 37 | Mindlink Mech, War Balloon, Rover Blades |
| 6 | keyword:convoke | keyword | 0 | 104 | 35 | Vault Guardsman, Pack's Favor, Kavu Primarch |
| 7 | keyword:echo | keyword | 0 | 50 | 32 | Albino Troll, Keldon Vandals, Hunting Moa |
| 8 | keyword:affinity | keyword | 0 | 74 | 30 | Refurbished Familiar, Icebreaker Kraken, Thrumming Hivepool |
| 9 | keyword:infect | keyword | 0 | 45 | 25 | Phyrexian Juggernaut, Contagious Nim, Plague Stinger |
| 10 | template:Commander creatures you own have “…” | continuous | 0 | 25 | 25 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 11 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 12 | template:All Slivers have “…” | continuous | 0 | 27 | 24 | Magma Sliver, Sedge Sliver, Mnemonic Sliver |
| 13 | keyword:suspend | keyword | 0 | 70 | 22 | Lotus Bloom, Resurgent Belief, Glimpse of Tomorrow |
| 14 | template:Landfall — Whenever N land(s) you control enters, ~ gets ±N/±N until end of turn. | continuous | 0 | 27 | 22 | Akoum Hellhound, Hedron Scrabbler, Hedron Rover |
| 15 | keyword:exalted | keyword | 0 | 34 | 21 | Aven Squire, Finest Hour, Nefarox, Overlord of Grixis |
| 16 | template:{M}: ~ gets ±N/±N until end of turn. Activate only once each turn. | activated | 0 | 28 | 20 | Mindful Biomancer, Frilled Oculus, Twinblade Slasher |
| 17 | template:~ enters with N ±N/±N counter(s) on it. | replacement | 0 | 163 | 19 | Yorvo, Lord of Garenbrig, Shrewd Hatchling, Benevolent Hydra |
| 18 | keyword:cumulative upkeep | keyword | 0 | 80 | 19 | Prismatic Circle, Musician, Illusionary Terrain |
| 19 | keyword:changeling | keyword | 0 | 62 | 18 | Barkform Harvester, Guardian Gladewalker, Wings of Velis Vel |
| 20 | keyword:banding | keyword | 0 | 24 | 18 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 21 | keyword:unearth | keyword | 0 | 56 | 17 | Royal Warden, Phyrexian Dragon Engine, Anathemancer |
| 22 | template:At the beginning of your upkeep, sacrifice ~ unless you pay {M}. | triggered | 0 | 44 | 17 | Justice, Phantasmal Forces, Forethought Amulet |
| 23 | keyword:bushido | keyword | 0 | 35 | 17 | Numai Outcast, Nezumi Ronin, Toshiro Umezawa |
| 24 | keyword:madness | keyword | 0 | 60 | 16 | Strength of Lunacy, Muck Drubb, Gisa's Bidding |
| 25 | keyword:cascade | keyword | 0 | 37 | 16 | Etherium-Horn Sorcerer, Call Forth the Tempest, Call Forth the Tempest |
| 26 | keyword:ward | keyword | 0 | 186 | 15 | Tyranid Harridan, Grey Host Reinforcements, Cactusfolk Sureshot |
| 27 | template:Soulshift N | static | 0 | 25 | 15 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 28 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 15 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 29 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 30 | keyword:buyback | keyword | 0 | 39 | 14 | Walk the Aeons, Spell Burst, Pegasus Stampede |
| 31 | keyword:dash | keyword | 0 | 22 | 13 | Warbringer, Warbringer, Kolaghan Forerunners |
| 32 | keyword:foretell | keyword | 0 | 51 | 12 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 33 | keyword:storm | keyword | 0 | 35 | 12 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 34 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 35 | template:Counter target spell unless its controller pays {M}. | spell_effect | 0 | 30 | 12 | Reasonable Doubt, Lose Focus, Runeboggle |
| 36 | template:Bloodthirst N | static | 0 | 23 | 12 | Carnage Wurm, Skarrgan Skybreaker, Indoraptor, the Perfect Hybrid |
| 37 | template:When ~ becomes the target of a spell or ability, sacrifice it. | triggered | 0 | 15 | 12 | Tar Pit Warrior, Skulking Knight, Phantom Beast |
| 38 | template:{M}, {M}: Investigate. | activated | 0 | 13 | 12 | Dining Room, Library, Kitchen |
| 39 | template:When ~ enters, return N land(s) you control to its owner's hand. | triggered | 0 | 12 | 12 | Selesnya Sanctuary, Simic Growth Chamber, Rakdos Carnarium |
| 40 | keyword:evoke | keyword | 0 | 35 | 11 | Walker of the Grove, Grief, Mournwhelk |
| 41 | template:Creatures you control get ±N/±N. | continuous | 0 | 34 | 11 | Angelic Shield, The Arkenstone // Seek the Heart, In the Trenches |
| 42 | keyword:wither | keyword | 0 | 26 | 11 | Twinblade Slasher, Boggart Ram-Gang, Noxious Hatchling |
| 43 | template:As ~ enters, you may pay N life(s). If you don't, it enters tapped. | replacement | 0 | 26 | 11 | Witch Enchanter // Witch-Blessed Meadow, Fell the Profane // Fell Mire, Stomping Ground |
| 44 | keyword:backup | keyword | 0 | 25 | 11 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 45 | template:Renown N | static | 0 | 20 | 11 | Rhox Maulers, Stalwart Aven, Relic Seeker |
| 46 | template:~ deals N damage to target attacking or blocking creature. | spell_effect | 0 | 15 | 11 | Hamato Ninpō, Impeccable Timing, Sandblast |
| 47 | keyword:rebound | keyword | 0 | 34 | 10 | World at War, Faithless Salvaging, Staggershock |
| 48 | keyword:megamorph | keyword | 0 | 31 | 10 | Kadena's Silencer, Segmented Krotiq, Kolaghan Stormsinger |
| 49 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 50 | keyword:flanking | keyword | 0 | 29 | 10 | Burning Shield Askari, Benalish Cavalry, Mtenda Herder |
| 51 | template:~ can't attack unless defending player controls an Island. | restriction | 0 | 25 | 10 | Red Cliffs Armada, Zhou Yu, Chief Commander, Floodchaser |
| 52 | keyword:improvise | keyword | 0 | 23 | 10 | Fen Hauler, Whir of Invention, Sly Requisitioner |
| 53 | keyword:undying | keyword | 0 | 22 | 10 | Demonlord of Ashmouth, Hound of Griselbrand, Vengeful Vampire |
| 54 | keyword:fabricate | keyword | 0 | 16 | 10 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 55 | keyword:unleash | keyword | 0 | 15 | 10 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 56 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 57 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 58 | template:Sliver creatures you control have “…” | continuous | 0 | 10 | 10 | Capricious Sliver, Lavabelly Sliver, Regal Sliver |
| 59 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 60 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 2414 | 15507 | 0 | 0 |
| Artifact | 424 | 3169 | 0 | 0 |
| Enchantment | 59 | 3588 | 0 | 0 |
| Sorcery | 180 | 3388 | 0 | 0 |
| Instant | 331 | 3423 | 0 | 0 |
| Land | 396 | 816 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

keyword 13914, triggered 13854, spell_effect 9143, activated 7355, continuous 4285, static 3858, mana_ability 2177, replacement 1974, restriction 1493, loyalty 882, prevention 323, additional_cost 307, cost_modifier 261, characteristic_defining 248, permission 214, alternative_cost 182
