# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 15:18

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 3774 | 11.8% |
| PARTIAL | 28294 | 88.1% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 79, PARTIAL 3422, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 527 | 240 | Eldrazi Confluence, Divergent Growth, Discreet Retreat |
| 2 | keyword:morph | keyword | 0 | 153 | 41 | Gravel Slinger, Willbender, Brine Elemental |
| 3 | keyword:convoke | keyword | 0 | 104 | 35 | Vault Guardsman, Pack's Favor, Kavu Primarch |
| 4 | keyword:echo | keyword | 0 | 50 | 33 | Albino Troll, Keldon Vandals, Hunting Moa |
| 5 | keyword:affinity | keyword | 0 | 74 | 30 | Refurbished Familiar, Icebreaker Kraken, Thrumming Hivepool |
| 6 | template:Commander creatures you own have “…” | continuous | 0 | 25 | 25 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 7 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 8 | template:All Slivers have “…” | continuous | 0 | 27 | 24 | Magma Sliver, Sedge Sliver, Mnemonic Sliver |
| 9 | template:~ enters with N ±N/±N counter(s) on it. | replacement | 0 | 163 | 22 | Yorvo, Lord of Garenbrig, Shrewd Hatchling, Benevolent Hydra |
| 10 | keyword:suspend | keyword | 0 | 70 | 22 | Lotus Bloom, Resurgent Belief, Glimpse of Tomorrow |
| 11 | template:Landfall — Whenever N land(s) you control enters, ~ gets ±N/±N until end of turn. | continuous | 0 | 27 | 22 | Akoum Hellhound, Hedron Scrabbler, Hedron Rover |
| 12 | template:{M}: ~ gets ±N/±N until end of turn. Activate only once each turn. | activated | 0 | 28 | 21 | Mindful Biomancer, Frilled Oculus, Twinblade Slasher |
| 13 | keyword:cumulative upkeep | keyword | 0 | 80 | 19 | Prismatic Circle, Musician, Illusionary Terrain |
| 14 | keyword:changeling | keyword | 0 | 62 | 19 | Barkform Harvester, Guardian Gladewalker, Wings of Velis Vel |
| 15 | keyword:bushido | keyword | 0 | 35 | 19 | Numai Outcast, Nezumi Ronin, Toshiro Umezawa |
| 16 | template:At the beginning of your upkeep, sacrifice ~ unless you pay {M}. | triggered | 0 | 44 | 18 | Justice, Phantasmal Forces, Forethought Amulet |
| 17 | keyword:cascade | keyword | 0 | 37 | 18 | Etherium-Horn Sorcerer, Call Forth the Tempest, Call Forth the Tempest |
| 18 | keyword:banding | keyword | 0 | 24 | 18 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 19 | keyword:unearth | keyword | 0 | 56 | 17 | Royal Warden, Phyrexian Dragon Engine, Anathemancer |
| 20 | keyword:madness | keyword | 0 | 60 | 16 | Strength of Lunacy, Muck Drubb, Gisa's Bidding |
| 21 | keyword:ward | keyword | 0 | 186 | 15 | Tyranid Harridan, Grey Host Reinforcements, Cactusfolk Sureshot |
| 22 | template:Soulshift N | static | 0 | 25 | 15 | Hundred-Talon Kami, Harbinger of Spring, Elder Pine of Jukai |
| 23 | template:{M}: Prevent the next N damage that would be dealt to any target this turn. | activated | 0 | 22 | 15 | Barrenton Medic, Militant Monk, Jhessian Balmgiver |
| 24 | template:When ~ enters, it explores. | triggered | 0 | 15 | 15 | River Herald Scout, Merfolk Branchwalker, Pathfinding Axejaw |
| 25 | keyword:buyback | keyword | 0 | 39 | 14 | Walk the Aeons, Spell Burst, Pegasus Stampede |
| 26 | keyword:dash | keyword | 0 | 22 | 13 | Warbringer, Warbringer, Kolaghan Forerunners |
| 27 | keyword:foretell | keyword | 0 | 51 | 12 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 28 | keyword:storm | keyword | 0 | 35 | 12 | Volcanic Awakening, Weather the Storm, Empty the Warrens |
| 29 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 30 | template:Counter target spell unless its controller pays {M}. | spell_effect | 0 | 30 | 12 | Reasonable Doubt, Lose Focus, Runeboggle |
| 31 | template:Bloodthirst N | static | 0 | 23 | 12 | Carnage Wurm, Skarrgan Skybreaker, Indoraptor, the Perfect Hybrid |
| 32 | template:Renown N | static | 0 | 20 | 12 | Rhox Maulers, Stalwart Aven, Relic Seeker |
| 33 | template:When ~ becomes the target of a spell or ability, sacrifice it. | triggered | 0 | 15 | 12 | Tar Pit Warrior, Skulking Knight, Phantom Beast |
| 34 | template:~ deals N damage to target attacking or blocking creature. | spell_effect | 0 | 15 | 12 | Hamato Ninpō, Impeccable Timing, Sandblast |
| 35 | template:{M}, {M}: Investigate. | activated | 0 | 13 | 12 | Dining Room, Library, Kitchen |
| 36 | template:When ~ enters, return N land(s) you control to its owner's hand. | triggered | 0 | 12 | 12 | Selesnya Sanctuary, Simic Growth Chamber, Rakdos Carnarium |
| 37 | keyword:evoke | keyword | 0 | 35 | 11 | Walker of the Grove, Grief, Mournwhelk |
| 38 | template:Creatures you control get ±N/±N. | continuous | 0 | 34 | 11 | Angelic Shield, The Arkenstone // Seek the Heart, In the Trenches |
| 39 | keyword:megamorph | keyword | 0 | 31 | 11 | Kadena's Silencer, Segmented Krotiq, Kolaghan Stormsinger |
| 40 | keyword:flanking | keyword | 0 | 29 | 11 | Burning Shield Askari, Benalish Cavalry, Mtenda Herder |
| 41 | template:As ~ enters, you may pay N life(s). If you don't, it enters tapped. | replacement | 0 | 26 | 11 | Witch Enchanter // Witch-Blessed Meadow, Fell the Profane // Fell Mire, Stomping Ground |
| 42 | keyword:backup | keyword | 0 | 25 | 11 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 43 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 44 | keyword:toxic | keyword | 0 | 37 | 10 | Tyrranax Atrocity, Bloated Contaminator, Bloodroot Apothecary |
| 45 | keyword:rebound | keyword | 0 | 34 | 10 | World at War, Faithless Salvaging, Staggershock |
| 46 | template:When ~ enters, mill N card(s). | triggered | 0 | 30 | 10 | The Eighth Doctor, Devoted Grafkeeper // Departed Soulkeeper, Seedship Broodtender |
| 47 | template:~ can't attack unless defending player controls an Island. | restriction | 0 | 25 | 10 | Red Cliffs Armada, Zhou Yu, Chief Commander, Floodchaser |
| 48 | keyword:persist | keyword | 0 | 24 | 10 | Puppeteer Clique, Furystoke Giant, Trapjaw Kelpie |
| 49 | keyword:improvise | keyword | 0 | 23 | 10 | Fen Hauler, Whir of Invention, Sly Requisitioner |
| 50 | keyword:undying | keyword | 0 | 22 | 10 | Demonlord of Ashmouth, Hound of Griselbrand, Vengeful Vampire |
| 51 | keyword:fabricate | keyword | 0 | 16 | 10 | Visionary Augmenter, Angel of Invention, Maulfist Squad |
| 52 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 53 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 10 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 54 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 55 | template:Sliver creatures you control have “…” | continuous | 0 | 10 | 10 | Capricious Sliver, Lavabelly Sliver, Regal Sliver |
| 56 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 57 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 58 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 59 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 60 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 2539 | 15382 | 0 | 0 |
| Artifact | 473 | 3120 | 0 | 0 |
| Enchantment | 59 | 3588 | 0 | 0 |
| Sorcery | 203 | 3365 | 0 | 0 |
| Instant | 353 | 3401 | 0 | 0 |
| Land | 398 | 814 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

keyword 13914, triggered 13854, spell_effect 9143, activated 7355, continuous 4285, static 3858, mana_ability 2177, replacement 1974, restriction 1493, loyalty 882, prevention 323, additional_cost 307, cost_modifier 261, characteristic_defining 248, permission 214, alternative_cost 182
