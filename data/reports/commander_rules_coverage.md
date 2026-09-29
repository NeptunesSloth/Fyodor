# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 18:42

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 5196 | 16.2% |
| PARTIAL | 26872 | 83.7% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 119, PARTIAL 3382, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 73337 (64.7%) · unrecognized clauses: 40009
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.1% · unclassified clauses: 3291
- Distinct missing-capability clusters: 9991

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11660 | 14131 |
| MISSING TRIGGER EVENT | 6611 | 7141 |
| MISSING SELECTOR | 4306 | 4569 |
| MISSING CONTINUOUS EFFECT | 2838 | 3016 |
| UNSUPPORTED ORACLE PATTERN | 2480 | 3291 |
| MISSING MECHANIC | 2136 | 2201 |
| MISSING COST | 1761 | 1841 |
| MISSING REPLACEMENT PATTERN | 1392 | 1431 |
| MISSING RESTRICTION | 1018 | 1064 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING TRIGGER EVENT | At the beginning of combat on your turn | 101 | 127 | 251 | Hot Pursuit, Greasefang, Okiba Boss, Cosmic Spider-Man |
| 2 | MISSING MECHANIC | partner | 91 | 5 | 101 | Lore Weaver, Ghost of Ramirez DePietro, Sophina, Spearsage Deserter |
| 3 | MISSING TRIGGER EVENT | Whenever ~ enters or attacks | 71 | 49 | 141 | Omo, Queen of Vesuva, Eluge, the Shoreless Sea, Great Goblin, Foul-Hearted |
| 4 | MISSING EFFECT | draw n … | 58 | 184 | 626 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 5 | MISSING MECHANIC | ward | 47 | 7 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 40 | 186 | 295 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 7 | MISSING TRIGGER EVENT | Whenever you attack | 40 | 34 | 90 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 8 | MISSING EFFECT | choose n … | 35 | 46 | 669 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 9 | UNSUPPORTED ORACLE PATTERN | planeswalker | 35 | 0 | 311 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 10 | MISSING EFFECT | put a ±n/±n counter(s) … | 33 | 134 | 227 | Benevolent Hydra, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 11 | MISSING EFFECT | pay {m} … | 33 | 101 | 141 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 12 | MISSING EFFECT | search your library for … | 32 | 274 | 424 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 13 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 45 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 14 | MISSING MECHANIC | choose a background | 32 | 1 | 32 | Halsin, Emerald Archdruid, Karlach, Fury of Avernus, Jaheira, Friend of the Forest |
| 15 | MISSING SELECTOR | target creature card | 28 | 145 | 248 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 16 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 57 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 17 | MISSING TRIGGER EVENT | Whenever you gain life | 28 | 40 | 79 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 18 | MISSING TRIGGER EVENT | At the beginning of each end step | 28 | 36 | 83 | Tinybones, Trinket Thief, Syndicate Heavy, Crested Sunmare |
| 19 | MISSING MECHANIC | doctor's companion | 27 | 0 | 27 | Nyssa of Traken, Donna Noble, Barbara Wright |
| 20 | MISSING TRIGGER EVENT | When ~ enters | 26 | 9 | 26 | Kiora of Fire and Ashes, Sharuum the Hegemon, Phage the Untouchable |
| 21 | MISSING EFFECT | create n … | 25 | 109 | 233 | Summon the School, Cogwork Assembler, Endless Evil |
| 22 | MISSING EFFECT | exile the top card … | 23 | 29 | 78 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 23 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 3 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 24 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 25 | UNSUPPORTED ORACLE PATTERN | ~ can be your commander | 22 | 0 | 22 | Teferi, Temporal Archmage, Saheeli, the Gifted, Will Kenrith |
| 26 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 32 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 27 | MISSING EFFECT | transform ~ … | 21 | 11 | 52 | Ulvenwald Captive // Ulvenwald Abomination, Seraph of New Capenna // Seraph of New Phyrexia, Sun-Blessed Guardian // Furnace-Blessed Conqueror |
| 28 | MISSING TRIGGER EVENT | Whenever ~ attacks | 21 | 8 | 21 | Durnan of the Yawning Portal, Acererak the Archlich, Edgar Markov |
| 29 | MISSING SELECTOR | target | 20 | 159 | 319 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 30 | MISSING EFFECT | put n … | 19 | 61 | 131 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 31 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 31 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 32 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 19 | 19 | 19 | Dungeon Delver, Noble Heritage, Agent of the Iron Throne |
| 33 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 22 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 34 | MISSING EFFECT | until end of turn … | 17 | 134 | 212 | Divergent Growth, Doorman, Strength of Will |
| 35 | MISSING EFFECT | mill n … | 17 | 58 | 98 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 36 | MISSING TRIGGER EVENT | At the beginning of your first main phase | 17 | 17 | 46 | Coalition Relic, Party Thrasher, Sab-Sunen, Luxa Embodied |
| 37 | MISSING SELECTOR | target creatures | 16 | 155 | 302 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 38 | MISSING EFFECT | another target … | 16 | 35 | 57 | Void Grafter, Flesh Burrower, Starry-Eyed Skyrider |
| 39 | MISSING TRIGGER EVENT | Whenever you draw your second card each turn | 16 | 31 | 54 | Lat-Nam Adept, Detective of the Month, Loxodon Eavesdropper |
| 40 | MISSING COST | {M}, Sacrifice another creature | 16 | 27 | 51 | Sanguine Spy, Skyclave Shadowcat, Phyrexian Warhorse |
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
| 61 | MISSING EFFECT | return ~ … | 11 | 69 | 114 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 62 | MISSING TRIGGER EVENT | Whenever ~ becomes tapped | 11 | 38 | 51 | Seedship Agrarian, Gran-Gran, Nanoform Sentinel |
| 63 | MISSING EFFECT | create a n/n green … | 11 | 34 | 91 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 64 | MISSING SELECTOR | target instant or sorcery card | 11 | 33 | 58 | Ogre Battlecaster, Scribe of the Mindful, Flood of Recollection |
| 65 | MISSING EFFECT | discard n … | 11 | 32 | 71 | Keldon Raider, Witch's Mark, Duplicity |
| 66 | MISSING EFFECT | create a n/n white … | 11 | 26 | 61 | Kaya, Spirits' Justice, Empyrial Storm, Archangel Elspeth |
| 67 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 12 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 68 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 9 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
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
| 80 | MISSING TRIGGER EVENT | Whenever another creature dies | 9 | 17 | 25 | Reaper of the Wilds, Syr Konrad, the Grim, Deathbringer Thoctar |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 669 | 46 | 35 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 2 | MISSING EFFECT | draw n … | 626 | 184 | 58 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 3 | MISSING EFFECT | search your library for … | 424 | 274 | 32 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 4 | MISSING EFFECT | ~ deals n … | 389 | 238 | 13 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING SELECTOR | target | 319 | 159 | 20 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 6 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 26 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 7 | UNSUPPORTED ORACLE PATTERN | planeswalker | 311 | 0 | 35 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 8 | MISSING SELECTOR | target creatures | 302 | 155 | 16 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 9 | MISSING EFFECT | look at the top … | 295 | 186 | 40 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 10 | MISSING EFFECT | destroy target … | 281 | 170 | 9 | Kalitas, Bloodchief of Ghet, Stand Up for Yourself, Misfortune's Gain |
| 11 | MISSING TRIGGER EVENT | At the beginning of combat on your turn | 251 | 127 | 101 | Hot Pursuit, Greasefang, Okiba Boss, Cosmic Spider-Man |
| 12 | MISSING SELECTOR | target creature card | 248 | 145 | 28 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 13 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 46 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 14 | MISSING EFFECT | create n … | 233 | 109 | 25 | Summon the School, Cogwork Assembler, Endless Evil |
| 15 | MISSING EFFECT | put a ±n/±n counter(s) … | 227 | 134 | 33 | Benevolent Hydra, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 16 | MISSING MECHANIC | kicker | 224 | 0 | 7 | Strength of Night, Goblin Barrage, Archangel of Wrath |
| 17 | MISSING EFFECT | until end of turn … | 212 | 134 | 17 | Divergent Growth, Doorman, Strength of Will |
| 18 | MISSING EFFECT | target creature gets ±n/±n … | 210 | 125 | 2 | Stern Marshal, Arachnoid Adaptation, Spontaneous Flight |
| 19 | MISSING EFFECT | target creature you control … | 194 | 133 | 8 | Oracle's Restoration, Plumecreed Escort, Blessed Defiance |
| 20 | MISSING EFFECT | you gain n … | 146 | 95 | 9 | River Hoopoe, Tatyova, Benthic Druid, Shu Farmer |
| 21 | MISSING TRIGGER EVENT | Whenever ~ enters or attacks | 141 | 49 | 71 | Omo, Queen of Vesuva, Eluge, the Shoreless Sea, Great Goblin, Foul-Hearted |
| 22 | MISSING EFFECT | pay {m} … | 141 | 101 | 33 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 23 | MISSING EFFECT | exile target … | 136 | 85 | 4 | Astarion's Thirst, Reaver Ambush, Deadly Rollick |
| 24 | MISSING EFFECT | put n … | 131 | 61 | 19 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 25 | MISSING SELECTOR | target card | 128 | 74 | 3 | Disposal Mummy, Crypt Creeper, Funeral Pyre |
| 26 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 57 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 27 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 45 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 28 | MISSING EFFECT | return ~ … | 114 | 69 | 11 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 29 | MANA ABILITY WORDING | {M}, … | 108 | 49 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 30 | MISSING MECHANIC | partner | 101 | 5 | 91 | Lore Weaver, Ghost of Ramirez DePietro, Sophina, Spearsage Deserter |
| 31 | MISSING EFFECT | mill n … | 98 | 58 | 17 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 32 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 87 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 33 | MISSING MECHANIC | ward | 97 | 7 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 34 | MISSING EFFECT | return target … | 95 | 53 | 2 | Surging Aether, Perilous Voyage, Trade Routes |
| 35 | MISSING SELECTOR | target player or planeswalker | 92 | 53 | 3 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 36 | MISSING EFFECT | create a n/n green … | 91 | 34 | 11 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 37 | MISSING TRIGGER EVENT | Whenever you attack | 90 | 34 | 40 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 38 | MISSING EFFECT | it deals n … | 87 | 54 | 5 | Goblin Chainwhirler, Chaos Maw, Festering Evil |
| 39 | MISSING EFFECT | creatures you control get … | 86 | 40 | 8 | Strength of Night, Zariel, Archduke of Avernus, Inner-Flame Igniter |
| 40 | MISSING TRIGGER EVENT | At the beginning of each end step | 83 | 36 | 28 | Tinybones, Trinket Thief, Syndicate Heavy, Crested Sunmare |
| 41 | MISSING TRIGGER EVENT | At the beginning of each player's upkeep | 81 | 51 | 8 | Seizan, Perverter of Truth, Quicksilver Fountain, Power Surge |
| 42 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 22 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 43 | MISSING TRIGGER EVENT | Whenever you gain life | 79 | 40 | 28 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 44 | MISSING COST | {M}, {M}, Discard N card(s) | 79 | 69 | 14 | Arc Mage, Sparkspitter, Instigator |
| 45 | MISSING COST | {M}, Discard N card(s) | 79 | 44 | 10 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 46 | MISSING EFFECT | exile the top card … | 78 | 29 | 23 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 47 | MISSING EFFECT | gain control of target … | 78 | 48 | 8 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 48 | MISSING EFFECT | tap target … | 78 | 46 | 2 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 49 | MISSING COST | {M}, Sacrifice N creature(s) | 75 | 54 | 12 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 50 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 32 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 197 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 43 | 30 | Ghostly Touch, Immobilizing Ink, Sunbond |
| 3 | template:Commander creatures you own have “…” | continuous | 0 | 23 | 23 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 4 | template:{M}: Return ~ to its owner's hand. | activated | 0 | 33 | 20 | Palinchron, Etherium-Horn Sorcerer, Shackles |
| 5 | template:Enchanted creature gets ±N/±N and has “…” | continuous | 0 | 25 | 20 | Arcane Teachings, Lunarch Mantle, Deviant Glee |
| 6 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 7 | keyword:bestow | keyword | 0 | 42 | 17 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 8 | template:All Slivers have “…” | continuous | 0 | 17 | 17 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 9 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 10 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 25 | 15 | Giant's Amulet, Iconic Shield, Candlestick |
| 11 | keyword:foretell | keyword | 0 | 51 | 13 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 12 | template:Enchanted land has “…” | continuous | 0 | 14 | 13 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 13 | keyword:enchant | keyword | 0 | 67 | 12 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 14 | keyword:splice | keyword | 0 | 30 | 12 | Evermind, Horobi's Whisper, Desperate Ritual |
| 15 | template:When ~ enters, tap enchanted creature. | triggered | 0 | 29 | 12 | Waterknot, Colossification, Tangle Kelp |
| 16 | keyword:backup | keyword | 0 | 25 | 12 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 17 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 18 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 12 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 19 | keyword:equip | keyword | 0 | 49 | 11 | Bloodthorn Flail, Strong Back, Team Pennant |
| 20 | template:~ enters prepared. | static | 0 | 40 | 11 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 21 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 11 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 22 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 11 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 23 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 24 | template:When ~ enters, each opponent discards N card(s). | triggered | 0 | 13 | 11 | Liliana's Specter, Cackling Fiend, Burglar Rat |
| 25 | template:Modular N | static | 0 | 23 | 10 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 26 | template:{M}: Untap ~. | activated | 0 | 21 | 10 | Staff of Compleation, Morphling, Glimmerbell |
| 27 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 28 | template:At the beginning of the end step, sacrifice ~. | triggered | 0 | 16 | 10 | Impetuous Devils, Underworld Breach, Putrefax |
| 29 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 10 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 30 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 31 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 32 | template:~ deals N damage to any target and you gain N life(s). | spell_effect | 0 | 12 | 10 | Agonizing Syphon, Integrity // Intervention, Vampiric Feast |
| 33 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 34 | template:When ~ enters, target creature can't block this turn. | triggered | 0 | 10 | 10 | Unstoppable Ogre, Goblin Shortcutter, Cartouche of Zeal |
| 35 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 36 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 37 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 38 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 39 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 40 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 41 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 42 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 9 | Voice of the Blessed, Essence Channeler, Wall of Limbs |
| 43 | template:All creatures get ±N/±N until end of turn. | spell_effect | 0 | 18 | 9 | Marsh Gas, Choking Miasma, Shrivel |
| 44 | template:Target player discards N card(s). | spell_effect | 0 | 18 | 9 | Mind Rake, Cry of Contrition, Skull Fracture |
| 45 | template:{M}: Enchanted creature gets ±N/±N until end of turn. | activated | 0 | 15 | 9 | Keldon Mantle, Flowstone Embrace, Fiery Mantle |
| 46 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 47 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 9 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 48 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 49 | template:{M}, {M}: Target player mills N card(s). | activated | 0 | 12 | 9 | Vedalken Entrancer, Persistent Petitioners, Relic Golem |
| 50 | template:~ deals N damage to each creature and each player. | spell_effect | 0 | 12 | 9 | Rain of Embers, Famine, Psychotic Haze |
| 51 | template:When ~ enters, you lose N life(s). | triggered | 0 | 10 | 9 | Nightdrinker Moroii, Foul Imp, Toxic Abomination |
| 52 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 53 | keyword:encore | keyword | 0 | 26 | 8 | Impulsivity, Sliver Gravemother, Belonging |
| 54 | template:When ~ is put into a graveyard from the battlefield, return it to its owner's hand. | triggered | 0 | 20 | 8 | Spine of Ish Sah, Slow Motion, Fiery Mantle |
| 55 | keyword:living weapon | keyword | 0 | 19 | 8 | Nettlecyst, Lashwrithe, Skinwing |
| 56 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 57 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 58 | template:When ~ is put into a graveyard from the battlefield, draw N card(s). | triggered | 0 | 13 | 8 | Nutrient Block, Implement of Examination, Implement of Malice |
| 59 | template:~ can block an additional creature each combat. | static | 0 | 12 | 8 | Selesnya Sagittars, Tangleclaw Werewolf // Fibrous Entangler, Tangleclaw Werewolf // Fibrous Entangler |
| 60 | template:Creatures your opponents control get ±N/±N until end of turn. | spell_effect | 0 | 11 | 8 | Turn the Tide, Make Obsolete, Hampering Snare |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 3378 | 14543 | 0 | 0 |
| Artifact | 620 | 2973 | 0 | 0 |
| Enchantment | 310 | 3337 | 0 | 0 |
| Sorcery | 259 | 3309 | 0 | 0 |
| Instant | 515 | 3239 | 0 | 0 |
| Land | 442 | 770 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
