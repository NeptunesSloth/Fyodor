# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 18:48

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 5222 | 16.3% |
| PARTIAL | 26846 | 83.6% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 124, PARTIAL 3377, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 73540 (64.9%) · unrecognized clauses: 39806
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.1% · unclassified clauses: 3269
- Distinct missing-capability clusters: 10086

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 12198 | 14808 |
| MISSING TRIGGER EVENT | 5971 | 6356 |
| MISSING SELECTOR | 4366 | 4632 |
| MISSING CONTINUOUS EFFECT | 2838 | 3016 |
| UNSUPPORTED ORACLE PATTERN | 2480 | 3269 |
| MISSING MECHANIC | 2002 | 2065 |
| MISSING COST | 1761 | 1841 |
| MISSING REPLACEMENT PATTERN | 1392 | 1431 |
| MISSING RESTRICTION | 1018 | 1064 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING TRIGGER EVENT | Whenever ~ enters or attacks | 71 | 50 | 141 | Omo, Queen of Vesuva, Eluge, the Shoreless Sea, Great Goblin, Foul-Hearted |
| 2 | MISSING EFFECT | draw n … | 58 | 191 | 632 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 3 | MISSING MECHANIC | ward | 47 | 7 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 4 | MISSING EFFECT | pay {m} … | 42 | 109 | 162 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 5 | MISSING EFFECT | look at the top … | 41 | 188 | 297 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 6 | MISSING EFFECT | choose n … | 40 | 46 | 678 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 7 | MISSING TRIGGER EVENT | Whenever you attack | 40 | 37 | 90 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 8 | MISSING EFFECT | put a ±n/±n counter(s) … | 38 | 142 | 240 | Benevolent Hydra, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 9 | UNSUPPORTED ORACLE PATTERN | planeswalker | 35 | 0 | 311 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 10 | MISSING EFFECT | search your library for … | 32 | 274 | 424 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 11 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 46 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 12 | MISSING SELECTOR | target creature card | 28 | 147 | 249 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 13 | MISSING EFFECT | create n … | 28 | 112 | 237 | Summon the School, Cogwork Assembler, Endless Evil |
| 14 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 57 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 15 | MISSING TRIGGER EVENT | Whenever you gain life | 28 | 40 | 79 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 16 | MISSING TRIGGER EVENT | When ~ enters | 26 | 9 | 26 | Kiora of Fire and Ashes, Sharuum the Hegemon, Phage the Untouchable |
| 17 | MISSING EFFECT | exile the top card … | 23 | 30 | 78 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 18 | MISSING SELECTOR | target | 22 | 161 | 322 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 19 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 3 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 20 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 21 | MISSING EFFECT | put n … | 21 | 64 | 137 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 22 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 34 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 23 | MISSING EFFECT | transform ~ … | 21 | 11 | 52 | Ulvenwald Captive // Ulvenwald Abomination, Seraph of New Capenna // Seraph of New Phyrexia, Sun-Blessed Guardian // Furnace-Blessed Conqueror |
| 24 | MISSING TRIGGER EVENT | Whenever ~ attacks | 21 | 10 | 21 | Durnan of the Yawning Portal, Acererak the Archlich, Edgar Markov |
| 25 | MISSING EFFECT | another target … | 20 | 41 | 66 | Void Grafter, Flesh Burrower, Starry-Eyed Skyrider |
| 26 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 31 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 27 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 19 | 19 | 19 | Dungeon Delver, Noble Heritage, Agent of the Iron Throne |
| 28 | MISSING SELECTOR | target creatures | 18 | 161 | 306 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 29 | MISSING EFFECT | until end of turn … | 18 | 135 | 213 | Divergent Growth, Doorman, Strength of Will |
| 30 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 22 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 31 | MISSING EFFECT | mill n … | 17 | 61 | 102 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 32 | MISSING EFFECT | if n … | 17 | 25 | 49 | Hot Pursuit, Zombie Ogre, Sidequest: Card Collection // Magicked Card |
| 33 | MISSING TRIGGER EVENT | Whenever you draw your second card each turn | 16 | 31 | 54 | Lat-Nam Adept, Detective of the Month, Loxodon Eavesdropper |
| 34 | MISSING COST | {M}, Sacrifice another creature | 16 | 27 | 51 | Sanguine Spy, Skyclave Shadowcat, Phyrexian Warhorse |
| 35 | MISSING TRIGGER EVENT | Whenever you draw N card(s)(s) | 16 | 16 | 40 | Moonring Mirror, Vodalian Wave-Knight, Sphinx's Tutelage |
| 36 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 26 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 37 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 38 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 39 | MISSING EFFECT | ~ deals n … | 14 | 259 | 417 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 40 | MISSING COST | {M}, {M}, Discard N card(s) | 14 | 69 | 79 | Arc Mage, Sparkspitter, Instigator |
| 41 | MISSING EFFECT | discard n … | 14 | 34 | 77 | Keldon Raider, Witch's Mark, Duplicity |
| 42 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 21 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 43 | MISSING TRIGGER EVENT | Whenever another nontoken creature you control dies | 14 | 11 | 20 | Bhaal, Lord of Murder, Myrkul, Lord of Bones, Agent Venom |
| 44 | MISSING EFFECT | exile ~ … | 14 | 7 | 54 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 45 | MISSING MECHANIC | sneak | 14 | 5 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 46 | MISSING MECHANIC | partner | 14 | 3 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 47 | MISSING MECHANIC | firebending | 14 | 3 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 48 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 49 | MISSING COST | {M}, Sacrifice an artifact | 13 | 16 | 32 | Embraal Gear-Smasher, Orcish Mechanics, Lobelia, Defender of Bag End |
| 50 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 51 | MISSING COST | {M}, Sacrifice N creature(s) | 12 | 54 | 75 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 52 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 24 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 53 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 54 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) you control deals combat damage to a player | 12 | 9 | 30 | Angel of Destiny, Reconnaissance Mission, Marisi, Breaker of the Coil |
| 55 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) an opponent controls dies | 12 | 8 | 25 | Kamber, the Plunderer, Toshiro Umezawa, The Meathook Massacre |
| 56 | MISSING EFFECT | target creature you control … | 11 | 139 | 206 | Oracle's Restoration, Plumecreed Escort, Blessed Defiance |
| 57 | MISSING EFFECT | return ~ … | 11 | 76 | 121 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 58 | MISSING TRIGGER EVENT | Whenever ~ becomes tapped | 11 | 38 | 51 | Seedship Agrarian, Gran-Gran, Nanoform Sentinel |
| 59 | MISSING EFFECT | create a n/n green … | 11 | 34 | 91 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 60 | MISSING EFFECT | add {m} … | 11 | 33 | 64 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 61 | MISSING SELECTOR | target instant or sorcery card | 11 | 33 | 58 | Ogre Battlecaster, Scribe of the Mindful, Flood of Recollection |
| 62 | MISSING EFFECT | create a n/n white … | 11 | 26 | 61 | Kaya, Spirits' Justice, Empyrial Storm, Archangel Elspeth |
| 63 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 14 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 64 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 9 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 65 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 6 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 66 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 67 | MISSING TRIGGER EVENT | When ~ enter | 11 | 4 | 11 | Mikey & Mona, Mutant Sitters, Cloak and Dagger, Entwined, The Immortal Weapons |
| 68 | MISSING COST | {M}, Discard N card(s) | 10 | 44 | 79 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 69 | MISSING EFFECT | creatures you control get … | 10 | 40 | 88 | Strength of Night, Zariel, Archduke of Avernus, Inner-Flame Igniter |
| 70 | MISSING EFFECT | create a n/n black … | 10 | 20 | 49 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 71 | MISSING TRIGGER EVENT | Whenever another creature you control dies | 10 | 13 | 27 | South Wind Avatar, Meren of Clan Nel Toth, Unruly Mob |
| 72 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 11 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 73 | MISSING TRIGGER EVENT | Whenever ~ deals combat damage to a player | 10 | 1 | 10 | Phage the Untouchable, Ezio Auditore da Firenze, Daxos of Meletis |
| 74 | MISSING EFFECT | destroy target … | 9 | 170 | 281 | Kalitas, Bloodchief of Ghet, Stand Up for Yourself, Misfortune's Gain |
| 75 | MISSING EFFECT | you gain n … | 9 | 95 | 146 | River Hoopoe, Tatyova, Benthic Druid, Shu Farmer |
| 76 | MISSING EFFECT | choose target … | 9 | 60 | 74 | Arcbond, Deglamer, Wreck Hunter |
| 77 | MISSING EFFECT | gain control of target … | 9 | 48 | 79 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 78 | MISSING EFFECT | if you control n … | 9 | 41 | 71 | Discourtesy Clerk, Boundary Lands Ranger, Psemilla, Meletian Poet |
| 79 | MISSING TRIGGER EVENT | Whenever you cast a Spirit or Arcane spell | 9 | 38 | 49 | Kami of the Painted Road, Soul of Magma, Elder Pine of Jukai |
| 80 | MISSING EFFECT | if ~ … | 9 | 34 | 85 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 678 | 46 | 40 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 2 | MISSING EFFECT | draw n … | 632 | 191 | 58 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 3 | MISSING EFFECT | search your library for … | 424 | 274 | 32 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 4 | MISSING EFFECT | ~ deals n … | 417 | 259 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING SELECTOR | target | 322 | 161 | 22 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 6 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 27 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 7 | UNSUPPORTED ORACLE PATTERN | planeswalker | 311 | 0 | 35 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 8 | MISSING SELECTOR | target creatures | 306 | 161 | 18 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 9 | MISSING EFFECT | look at the top … | 297 | 188 | 41 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 10 | MISSING EFFECT | destroy target … | 281 | 170 | 9 | Kalitas, Bloodchief of Ghet, Stand Up for Yourself, Misfortune's Gain |
| 11 | MISSING SELECTOR | target creature card | 249 | 147 | 28 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 12 | MISSING EFFECT | put a ±n/±n counter(s) … | 240 | 142 | 38 | Benevolent Hydra, Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin |
| 13 | MISSING EFFECT | create n … | 237 | 112 | 28 | Summon the School, Cogwork Assembler, Endless Evil |
| 14 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 46 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 15 | MISSING MECHANIC | kicker | 224 | 0 | 7 | Strength of Night, Goblin Barrage, Archangel of Wrath |
| 16 | MISSING EFFECT | until end of turn … | 213 | 135 | 18 | Divergent Growth, Doorman, Strength of Will |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 210 | 125 | 2 | Stern Marshal, Arachnoid Adaptation, Spontaneous Flight |
| 18 | MISSING EFFECT | target creature you control … | 206 | 139 | 11 | Oracle's Restoration, Plumecreed Escort, Blessed Defiance |
| 19 | MISSING EFFECT | pay {m} … | 162 | 109 | 42 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 20 | MISSING EFFECT | you gain n … | 146 | 95 | 9 | River Hoopoe, Tatyova, Benthic Druid, Shu Farmer |
| 21 | MISSING TRIGGER EVENT | Whenever ~ enters or attacks | 141 | 50 | 71 | Omo, Queen of Vesuva, Eluge, the Shoreless Sea, Great Goblin, Foul-Hearted |
| 22 | MISSING EFFECT | put n … | 137 | 64 | 21 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 23 | MISSING EFFECT | exile target … | 136 | 85 | 4 | Astarion's Thirst, Reaver Ambush, Deadly Rollick |
| 24 | MISSING SELECTOR | target card | 132 | 75 | 4 | Disposal Mummy, Crypt Creeper, Funeral Pyre |
| 25 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 57 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 26 | MISSING EFFECT | return ~ … | 121 | 76 | 11 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 27 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 46 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 28 | MANA ABILITY WORDING | {M}, … | 108 | 49 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 29 | MISSING EFFECT | mill n … | 102 | 61 | 17 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 30 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 87 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 31 | MISSING MECHANIC | ward | 97 | 7 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 32 | MISSING EFFECT | return target … | 95 | 53 | 2 | Surging Aether, Perilous Voyage, Trade Routes |
| 33 | MISSING SELECTOR | target player or planeswalker | 92 | 53 | 3 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 34 | MISSING EFFECT | create a n/n green … | 91 | 34 | 11 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 35 | MISSING TRIGGER EVENT | Whenever you attack | 90 | 37 | 40 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 36 | MISSING EFFECT | creatures you control get … | 88 | 40 | 10 | Strength of Night, Zariel, Archduke of Avernus, Inner-Flame Igniter |
| 37 | MISSING EFFECT | it deals n … | 87 | 54 | 5 | Goblin Chainwhirler, Chaos Maw, Festering Evil |
| 38 | MISSING EFFECT | if ~ … | 85 | 34 | 9 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 39 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 22 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 40 | MISSING TRIGGER EVENT | Whenever you gain life | 79 | 40 | 28 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 41 | MISSING COST | {M}, {M}, Discard N card(s) | 79 | 69 | 14 | Arc Mage, Sparkspitter, Instigator |
| 42 | MISSING COST | {M}, Discard N card(s) | 79 | 44 | 10 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 43 | MISSING EFFECT | gain control of target … | 79 | 48 | 9 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 44 | MISSING EFFECT | tap target … | 79 | 47 | 2 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 45 | MISSING EFFECT | exile the top card … | 78 | 30 | 23 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 46 | MISSING EFFECT | discard n … | 77 | 34 | 14 | Keldon Raider, Witch's Mark, Duplicity |
| 47 | MISSING COST | {M}, Sacrifice N creature(s) | 75 | 54 | 12 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 48 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 34 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 49 | MISSING EFFECT | choose target … | 74 | 60 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 50 | MISSING SELECTOR | target player mills N card(s) | 73 | 42 | 4 | Jace, the Perfected Mind, Breaking // Entering, Vedalken Entrancer |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 202 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
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
| 28 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 10 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 29 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 30 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 31 | template:~ deals N damage to any target and you gain N life(s). | spell_effect | 0 | 12 | 10 | Agonizing Syphon, Integrity // Intervention, Vampiric Feast |
| 32 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 33 | template:When ~ enters, target creature can't block this turn. | triggered | 0 | 10 | 10 | Unstoppable Ogre, Goblin Shortcutter, Cartouche of Zeal |
| 34 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 35 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 36 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 37 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 38 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 39 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 40 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 41 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 9 | Voice of the Blessed, Essence Channeler, Wall of Limbs |
| 42 | template:All creatures get ±N/±N until end of turn. | spell_effect | 0 | 18 | 9 | Marsh Gas, Choking Miasma, Shrivel |
| 43 | template:Target player discards N card(s). | spell_effect | 0 | 18 | 9 | Mind Rake, Cry of Contrition, Skull Fracture |
| 44 | template:{M}: Enchanted creature gets ±N/±N until end of turn. | activated | 0 | 15 | 9 | Keldon Mantle, Flowstone Embrace, Fiery Mantle |
| 45 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 46 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 9 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 47 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 48 | template:{M}, {M}: Target player mills N card(s). | activated | 0 | 12 | 9 | Vedalken Entrancer, Persistent Petitioners, Relic Golem |
| 49 | template:~ deals N damage to each creature and each player. | spell_effect | 0 | 12 | 9 | Rain of Embers, Famine, Psychotic Haze |
| 50 | template:When ~ enters, you lose N life(s). | triggered | 0 | 10 | 9 | Nightdrinker Moroii, Foul Imp, Toxic Abomination |
| 51 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 52 | keyword:encore | keyword | 0 | 26 | 8 | Impulsivity, Sliver Gravemother, Belonging |
| 53 | template:When ~ is put into a graveyard from the battlefield, return it to its owner's hand. | triggered | 0 | 20 | 8 | Spine of Ish Sah, Slow Motion, Fiery Mantle |
| 54 | keyword:living weapon | keyword | 0 | 19 | 8 | Nettlecyst, Lashwrithe, Skinwing |
| 55 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 56 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 57 | template:When ~ is put into a graveyard from the battlefield, draw N card(s). | triggered | 0 | 13 | 8 | Nutrient Block, Implement of Examination, Implement of Malice |
| 58 | template:Whenever ~ deals combat damage to a player, that player discards N card(s). | triggered | 0 | 12 | 8 | Chilling Apparition, Banshee of the Dread Choir, Silent Specter |
| 59 | template:~ can block an additional creature each combat. | static | 0 | 12 | 8 | Selesnya Sagittars, Tangleclaw Werewolf // Fibrous Entangler, Tangleclaw Werewolf // Fibrous Entangler |
| 60 | template:Creatures your opponents control get ±N/±N until end of turn. | spell_effect | 0 | 11 | 8 | Turn the Tide, Make Obsolete, Hampering Snare |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 3400 | 14521 | 0 | 0 |
| Artifact | 620 | 2973 | 0 | 0 |
| Enchantment | 315 | 3332 | 0 | 0 |
| Sorcery | 259 | 3309 | 0 | 0 |
| Instant | 515 | 3239 | 0 | 0 |
| Land | 442 | 770 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
