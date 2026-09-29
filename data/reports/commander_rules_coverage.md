# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 18:13

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 4933 | 15.4% |
| PARTIAL | 27135 | 84.5% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 119, PARTIAL 3382, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 70719 (62.4%) · unrecognized clauses: 42627
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.1% · unclassified clauses: 3294
- Distinct missing-capability clusters: 10040

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11660 | 14131 |
| MISSING TRIGGER EVENT | 6611 | 7141 |
| MISSING SELECTOR | 4312 | 4575 |
| MISSING MECHANIC | 3772 | 3943 |
| MISSING CONTINUOUS EFFECT | 3507 | 3735 |
| UNSUPPORTED ORACLE PATTERN | 2483 | 3294 |
| MISSING COST | 1761 | 1841 |
| MISSING REPLACEMENT PATTERN | 1394 | 1433 |
| MISSING RESTRICTION | 1161 | 1210 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING TRIGGER EVENT | At the beginning of combat on your turn | 101 | 126 | 251 | Hot Pursuit, Greasefang, Okiba Boss, Cosmic Spider-Man |
| 2 | MISSING MECHANIC | partner | 91 | 5 | 101 | Lore Weaver, Ghost of Ramirez DePietro, Sophina, Spearsage Deserter |
| 3 | MISSING TRIGGER EVENT | Whenever ~ enters or attacks | 71 | 49 | 141 | Omo, Queen of Vesuva, Eluge, the Shoreless Sea, Great Goblin, Foul-Hearted |
| 4 | MISSING EFFECT | draw n … | 58 | 182 | 626 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 5 | MISSING MECHANIC | ward | 47 | 7 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 40 | 185 | 295 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 7 | MISSING TRIGGER EVENT | Whenever you attack | 40 | 34 | 90 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 8 | MISSING EFFECT | choose n … | 35 | 46 | 669 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 9 | UNSUPPORTED ORACLE PATTERN | planeswalker | 35 | 0 | 311 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 10 | MISSING EFFECT | put a ±n/±n counter(s) … | 33 | 128 | 227 | Benevolent Hydra, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 11 | MISSING EFFECT | pay {m} … | 33 | 90 | 141 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 12 | MISSING EFFECT | search your library for … | 32 | 273 | 424 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 13 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 45 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 14 | MISSING MECHANIC | choose a background | 32 | 1 | 32 | Halsin, Emerald Archdruid, Karlach, Fury of Avernus, Jaheira, Friend of the Forest |
| 15 | MISSING SELECTOR | target creature card | 28 | 145 | 248 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 16 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 57 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 17 | MISSING TRIGGER EVENT | Whenever you gain life | 28 | 38 | 79 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 18 | MISSING TRIGGER EVENT | At the beginning of each end step | 28 | 35 | 83 | Tinybones, Trinket Thief, Syndicate Heavy, Crested Sunmare |
| 19 | MISSING MECHANIC | doctor's companion | 27 | 0 | 27 | Nyssa of Traken, Donna Noble, Barbara Wright |
| 20 | MISSING TRIGGER EVENT | When ~ enters | 26 | 9 | 26 | Kiora of Fire and Ashes, Sharuum the Hegemon, Phage the Untouchable |
| 21 | MISSING EFFECT | create n … | 25 | 107 | 233 | Summon the School, Cogwork Assembler, Endless Evil |
| 22 | MISSING EFFECT | exile the top card … | 23 | 29 | 78 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 23 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 3 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 24 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 25 | UNSUPPORTED ORACLE PATTERN | ~ can be your commander | 22 | 0 | 22 | Teferi, Temporal Archmage, Saheeli, the Gifted, Will Kenrith |
| 26 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 28 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 27 | MISSING EFFECT | transform ~ … | 21 | 11 | 52 | Ulvenwald Captive // Ulvenwald Abomination, Seraph of New Capenna // Seraph of New Phyrexia, Sun-Blessed Guardian // Furnace-Blessed Conqueror |
| 28 | MISSING TRIGGER EVENT | Whenever ~ attacks | 21 | 8 | 21 | Durnan of the Yawning Portal, Acererak the Archlich, Edgar Markov |
| 29 | MISSING SELECTOR | target | 20 | 152 | 325 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 30 | MISSING EFFECT | put n … | 19 | 61 | 131 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 31 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 30 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 32 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 19 | 19 | 19 | Dungeon Delver, Noble Heritage, Agent of the Iron Throne |
| 33 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 22 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 34 | MISSING EFFECT | until end of turn … | 17 | 131 | 212 | Divergent Growth, Doorman, Strength of Will |
| 35 | MISSING EFFECT | mill n … | 17 | 58 | 98 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 36 | MISSING TRIGGER EVENT | At the beginning of your first main phase | 17 | 16 | 46 | Coalition Relic, Party Thrasher, Sab-Sunen, Luxa Embodied |
| 37 | MISSING SELECTOR | target creatures | 16 | 155 | 302 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 38 | MISSING EFFECT | another target … | 16 | 35 | 57 | Void Grafter, Flesh Burrower, Starry-Eyed Skyrider |
| 39 | MISSING TRIGGER EVENT | Whenever you draw your second card each turn | 16 | 30 | 54 | Lat-Nam Adept, Detective of the Month, Loxodon Eavesdropper |
| 40 | MISSING COST | {M}, Sacrifice another creature | 16 | 26 | 51 | Sanguine Spy, Skyclave Shadowcat, Phyrexian Warhorse |
| 41 | MISSING TRIGGER EVENT | Whenever you draw N card(s)(s) | 16 | 16 | 40 | Moonring Mirror, Vodalian Wave-Knight, Sphinx's Tutelage |
| 42 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 26 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 43 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 44 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 45 | MISSING COST | {M}, {M}, Discard N card(s) | 14 | 69 | 79 | Arc Mage, Sparkspitter, Instigator |
| 46 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 20 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 47 | MISSING TRIGGER EVENT | Whenever another nontoken creature you control dies | 14 | 11 | 20 | Bhaal, Lord of Murder, Myrkul, Lord of Bones, Agent Venom |
| 48 | MISSING EFFECT | exile ~ … | 14 | 7 | 54 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 49 | MISSING MECHANIC | sneak | 14 | 5 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 50 | MISSING MECHANIC | firebending | 14 | 3 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 51 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 52 | MISSING EFFECT | ~ deals n … | 13 | 238 | 389 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 53 | MISSING EFFECT | if n … | 13 | 19 | 36 | Zombie Ogre, Sidequest: Card Collection // Magicked Card, Malcator, Purity Overseer |
| 54 | MISSING COST | {M}, Sacrifice an artifact | 13 | 15 | 32 | Embraal Gear-Smasher, Orcish Mechanics, Lobelia, Defender of Bag End |
| 55 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 56 | MISSING COST | {M}, Sacrifice N creature(s) | 12 | 54 | 75 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 57 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 24 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 58 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 59 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) you control deals combat damage to a player | 12 | 8 | 30 | Angel of Destiny, Reconnaissance Mission, Marisi, Breaker of the Coil |
| 60 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) an opponent controls dies | 12 | 8 | 25 | Kamber, the Plunderer, Toshiro Umezawa, The Meathook Massacre |
| 61 | MISSING EFFECT | return ~ … | 11 | 52 | 114 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 62 | MISSING TRIGGER EVENT | Whenever ~ becomes tapped | 11 | 38 | 51 | Seedship Agrarian, Gran-Gran, Nanoform Sentinel |
| 63 | MISSING EFFECT | create a n/n green … | 11 | 34 | 91 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 64 | MISSING SELECTOR | target instant or sorcery card | 11 | 33 | 58 | Ogre Battlecaster, Scribe of the Mindful, Flood of Recollection |
| 65 | MISSING EFFECT | discard n … | 11 | 30 | 71 | Keldon Raider, Witch's Mark, Duplicity |
| 66 | MISSING EFFECT | create a n/n white … | 11 | 23 | 61 | Kaya, Spirits' Justice, Empyrial Storm, Archangel Elspeth |
| 67 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 12 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 68 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 8 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 69 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 6 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 70 | MISSING TRIGGER EVENT | When ~ enter | 11 | 4 | 11 | Mikey & Mona, Mutant Sitters, Cloak and Dagger, Entwined, The Immortal Weapons |
| 71 | MISSING COST | {M}, Discard N card(s) | 10 | 44 | 79 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 72 | MISSING TRIGGER EVENT | Whenever another creature you control dies | 10 | 13 | 27 | South Wind Avatar, Meren of Clan Nel Toth, Unruly Mob |
| 73 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 11 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 74 | MISSING TRIGGER EVENT | At the beginning of each combat | 10 | 10 | 23 | Goblin Flotilla, Timin, Youthful Geist, Psemilla, Meletian Poet |
| 75 | MISSING TRIGGER EVENT | Whenever ~ deals combat damage to a player | 10 | 1 | 10 | Phage the Untouchable, Ezio Auditore da Firenze, Daxos of Meletis |
| 76 | MISSING EFFECT | destroy target … | 9 | 170 | 281 | Kalitas, Bloodchief of Ghet, Stand Up for Yourself, Misfortune's Gain |
| 77 | MISSING EFFECT | you gain n … | 9 | 95 | 146 | River Hoopoe, Tatyova, Benthic Druid, Shu Farmer |
| 78 | MISSING EFFECT | choose target … | 9 | 60 | 74 | Arcbond, Deglamer, Wreck Hunter |
| 79 | MISSING TRIGGER EVENT | Whenever you cast a Spirit or Arcane spell | 9 | 38 | 49 | Kami of the Painted Road, Soul of Magma, Elder Pine of Jukai |
| 80 | MISSING TRIGGER EVENT | Whenever another creature dies | 9 | 16 | 25 | Reaper of the Wilds, Syr Konrad, the Grim, Deathbringer Thoctar |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING MECHANIC | enchant | 1237 | 5 | 2 | Sensory Deprivation, Waterknot, Strength of Unity |
| 2 | MISSING EFFECT | choose n … | 669 | 46 | 35 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING EFFECT | draw n … | 626 | 182 | 58 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 4 | MISSING MECHANIC | equip | 597 | 1 | 4 | Behemoth Sledge, Giant's Amulet, Bloodthorn Flail |
| 5 | MISSING EFFECT | search your library for … | 424 | 273 | 32 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 6 | MISSING EFFECT | ~ deals n … | 389 | 238 | 13 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 7 | MISSING SELECTOR | target | 325 | 152 | 20 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 8 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 26 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 9 | UNSUPPORTED ORACLE PATTERN | planeswalker | 311 | 0 | 35 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 10 | MISSING SELECTOR | target creatures | 302 | 155 | 16 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 11 | MISSING EFFECT | look at the top … | 295 | 185 | 40 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 12 | MISSING EFFECT | destroy target … | 281 | 170 | 9 | Kalitas, Bloodchief of Ghet, Stand Up for Yourself, Misfortune's Gain |
| 13 | MISSING TRIGGER EVENT | At the beginning of combat on your turn | 251 | 126 | 101 | Hot Pursuit, Greasefang, Okiba Boss, Cosmic Spider-Man |
| 14 | MISSING SELECTOR | target creature card | 248 | 145 | 28 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 15 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 45 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 16 | MISSING EFFECT | create n … | 233 | 107 | 25 | Summon the School, Cogwork Assembler, Endless Evil |
| 17 | MISSING EFFECT | put a ±n/±n counter(s) … | 227 | 128 | 33 | Benevolent Hydra, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 18 | MISSING MECHANIC | kicker | 224 | 0 | 7 | Strength of Night, Goblin Barrage, Archangel of Wrath |
| 19 | MISSING EFFECT | until end of turn … | 212 | 131 | 17 | Divergent Growth, Doorman, Strength of Will |
| 20 | MISSING EFFECT | target creature gets ±n/±n … | 210 | 125 | 2 | Stern Marshal, Arachnoid Adaptation, Spontaneous Flight |
| 21 | MISSING EFFECT | target creature you control … | 194 | 132 | 8 | Oracle's Restoration, Plumecreed Escort, Blessed Defiance |
| 22 | MISSING EFFECT | you gain n … | 146 | 95 | 9 | River Hoopoe, Tatyova, Benthic Druid, Shu Farmer |
| 23 | MISSING TRIGGER EVENT | Whenever ~ enters or attacks | 141 | 49 | 71 | Omo, Queen of Vesuva, Eluge, the Shoreless Sea, Great Goblin, Foul-Hearted |
| 24 | MISSING EFFECT | pay {m} … | 141 | 90 | 33 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 25 | MISSING EFFECT | exile target … | 136 | 85 | 4 | Astarion's Thirst, Reaver Ambush, Deadly Rollick |
| 26 | MISSING EFFECT | put n … | 131 | 61 | 19 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 27 | MISSING SELECTOR | target card | 128 | 74 | 3 | Disposal Mummy, Crypt Creeper, Funeral Pyre |
| 28 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 57 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 29 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 45 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 30 | MISSING EFFECT | return ~ … | 114 | 52 | 11 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 31 | MANA ABILITY WORDING | {M}, … | 108 | 49 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 32 | MISSING MECHANIC | partner | 101 | 5 | 91 | Lore Weaver, Ghost of Ramirez DePietro, Sophina, Spearsage Deserter |
| 33 | MISSING EFFECT | mill n … | 98 | 58 | 17 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 34 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 87 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 35 | MISSING MECHANIC | ward | 97 | 7 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 36 | MISSING EFFECT | return target … | 95 | 53 | 2 | Surging Aether, Perilous Voyage, Trade Routes |
| 37 | MISSING SELECTOR | target player or planeswalker | 92 | 52 | 3 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 38 | MISSING EFFECT | create a n/n green … | 91 | 34 | 11 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 39 | MISSING TRIGGER EVENT | Whenever you attack | 90 | 34 | 40 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 40 | MISSING EFFECT | it deals n … | 87 | 53 | 5 | Goblin Chainwhirler, Chaos Maw, Festering Evil |
| 41 | MISSING EFFECT | creatures you control get … | 86 | 40 | 8 | Strength of Night, Zariel, Archduke of Avernus, Inner-Flame Igniter |
| 42 | MISSING TRIGGER EVENT | At the beginning of each end step | 83 | 35 | 28 | Tinybones, Trinket Thief, Syndicate Heavy, Crested Sunmare |
| 43 | MISSING TRIGGER EVENT | At the beginning of each player's upkeep | 81 | 51 | 8 | Seizan, Perverter of Truth, Quicksilver Fountain, Power Surge |
| 44 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 22 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 45 | MISSING TRIGGER EVENT | Whenever you gain life | 79 | 38 | 28 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 46 | MISSING COST | {M}, {M}, Discard N card(s) | 79 | 69 | 14 | Arc Mage, Sparkspitter, Instigator |
| 47 | MISSING COST | {M}, Discard N card(s) | 79 | 44 | 10 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 48 | MISSING EFFECT | exile the top card … | 78 | 29 | 23 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 49 | MISSING EFFECT | gain control of target … | 78 | 47 | 8 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 50 | MISSING EFFECT | tap target … | 78 | 46 | 2 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 197 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Commander creatures you own have “…” | continuous | 0 | 23 | 23 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 3 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 4 | template:All Slivers have “…” | continuous | 0 | 17 | 17 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 5 | keyword:foretell | keyword | 0 | 51 | 13 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 6 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 7 | keyword:backup | keyword | 0 | 25 | 12 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 8 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 9 | template:~ enters prepared. | static | 0 | 40 | 11 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 10 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 11 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 11 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 12 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 11 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 13 | template:Modular N | static | 0 | 23 | 10 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 14 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 15 | template:At the beginning of the end step, sacrifice ~. | triggered | 0 | 16 | 10 | Impetuous Devils, Underworld Breach, Putrefax |
| 16 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 17 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 18 | template:~ deals N damage to any target and you gain N life(s). | spell_effect | 0 | 12 | 10 | Agonizing Syphon, Integrity // Intervention, Vampiric Feast |
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
| 31 | template:Target player discards N card(s). | spell_effect | 0 | 18 | 9 | Mind Rake, Cry of Contrition, Skull Fracture |
| 32 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 9 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 33 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 34 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 9 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 35 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 36 | template:{M}, {M}: Target player mills N card(s). | activated | 0 | 12 | 9 | Vedalken Entrancer, Persistent Petitioners, Relic Golem |
| 37 | template:~ deals N damage to each creature and each player. | spell_effect | 0 | 12 | 9 | Rain of Embers, Famine, Psychotic Haze |
| 38 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 39 | keyword:encore | keyword | 0 | 26 | 8 | Impulsivity, Sliver Gravemother, Belonging |
| 40 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 41 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 42 | template:~ can block an additional creature each combat. | static | 0 | 12 | 8 | Selesnya Sagittars, Tangleclaw Werewolf // Fibrous Entangler, Tangleclaw Werewolf // Fibrous Entangler |
| 43 | template:Creatures your opponents control get ±N/±N until end of turn. | spell_effect | 0 | 11 | 8 | Turn the Tide, Make Obsolete, Hampering Snare |
| 44 | template:When ~ enters, target creature an opponent controls gets ±N/±N until end of turn. | triggered | 0 | 11 | 8 | Humbling Elder, Eyeblight Assassin, Grim Bauble |
| 45 | template:When ~ enters, target creature can't block this turn. | triggered | 0 | 10 | 8 | Unstoppable Ogre, Goblin Shortcutter, Cartouche of Zeal |
| 46 | template:When ~ enters, you lose N life(s). | triggered | 0 | 10 | 8 | Nightdrinker Moroii, Foul Imp, Toxic Abomination |
| 47 | template:{M}, {M}: Search your library for a Rebel permanent card with mana value N or less, put it onto the battlefield, then shuffle. | activated | 0 | 10 | 8 | Ramosian Commander, Blightspeaker, Ramosian Captain |
| 48 | template:Threshold — As long as there are N or more cards in your graveyard, ~ has “…” | continuous | 0 | 9 | 8 | Cephalid Sage, Hunting Grounds, Centaur Chieftain |
| 49 | template:Whenever ~ becomes blocked, it gets ±N/±N until end of turn. | triggered | 0 | 9 | 8 | Deeproot Warrior, Snorting Gahr, Razorclaw Bear |
| 50 | template:Whenever ~ blocks or becomes blocked, it gets ±N/±N until end of turn. | triggered | 0 | 9 | 8 | Raging Gorilla, Brushwagg, Dromosaur |
| 51 | template:Whenever ~ blocks, it gets ±N/±N until end of turn. | triggered | 0 | 9 | 8 | Jareth, Leonine Titan, Shu Defender, Zhao Zilong, Tiger General |
| 52 | template:When ~ enters, return target instant or sorcery card from your graveyard to your hand. | triggered | 0 | 8 | 8 | Izzet Chronarch, Ardent Elementalist, Salvager of Secrets |
| 53 | template:~ enters tapped unless your opponents control N or more lands. | replacement | 0 | 8 | 8 | Turbulent Fen, Turbulent Moor, Turbulent Springs |
| 54 | keyword:ward | keyword | 0 | 97 | 7 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 55 | keyword:disguise | keyword | 0 | 43 | 7 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 56 | keyword:warp | keyword | 0 | 31 | 7 | Starbreach Whale, Knight Luminary, Loading Zone |
| 57 | keyword:overload | keyword | 0 | 27 | 7 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 58 | template:{M}: Untap ~. | activated | 0 | 21 | 7 | Staff of Compleation, Morphling, Glimmerbell |
| 59 | keyword:mentor | keyword | 0 | 19 | 7 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 60 | keyword:prototype | keyword | 0 | 19 | 7 | Goring Warplow, Combat Thresher, Woodcaller Automaton |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 3378 | 14543 | 0 | 0 |
| Artifact | 546 | 3047 | 0 | 0 |
| Enchantment | 121 | 3526 | 0 | 0 |
| Sorcery | 259 | 3309 | 0 | 0 |
| Instant | 515 | 3239 | 0 | 0 |
| Land | 441 | 771 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
