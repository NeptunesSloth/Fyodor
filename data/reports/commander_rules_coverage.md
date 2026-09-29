# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 19:27

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 7263 | 22.6% |
| PARTIAL | 24805 | 77.2% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 188, PARTIAL 3313, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 76891 (67.8%) · unrecognized clauses: 36455
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.1% · unclassified clauses: 3269
- Distinct missing-capability clusters: 9769

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 10397 | 12480 |
| MISSING TRIGGER EVENT | 5855 | 6215 |
| MISSING SELECTOR | 3602 | 3822 |
| MISSING CONTINUOUS EFFECT | 2828 | 3005 |
| UNSUPPORTED ORACLE PATTERN | 2480 | 3269 |
| MISSING MECHANIC | 2002 | 2065 |
| MISSING COST | 1761 | 1841 |
| MISSING REPLACEMENT PATTERN | 1387 | 1426 |
| MISSING RESTRICTION | 962 | 1008 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 51 | 173 | 565 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 2 | MISSING MECHANIC | ward | 47 | 8 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 3 | MISSING EFFECT | choose n … | 45 | 46 | 528 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 4 | MISSING EFFECT | pay {m} … | 42 | 111 | 162 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 5 | MISSING TRIGGER EVENT | Whenever you attack | 40 | 37 | 90 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 6 | UNSUPPORTED ORACLE PATTERN | planeswalker | 35 | 0 | 311 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 7 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 51 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 8 | MISSING EFFECT | look at the top … | 30 | 115 | 189 | Harald, King of Skemfar, Lantern of Revealing, Ponder |
| 9 | MISSING EFFECT | create n … | 28 | 111 | 233 | Summon the School, Cogwork Assembler, Endless Evil |
| 10 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 58 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 11 | MISSING TRIGGER EVENT | Whenever you gain life | 28 | 42 | 79 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 12 | MISSING TRIGGER EVENT | When ~ enters | 26 | 10 | 26 | Kiora of Fire and Ashes, Sharuum the Hegemon, Phage the Untouchable |
| 13 | MISSING EFFECT | put a ±n/±n counter(s) … | 25 | 103 | 165 | Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin, Hired Claw |
| 14 | MISSING SELECTOR | target creature card | 24 | 109 | 177 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 15 | MISSING EFFECT | exile the top card … | 24 | 30 | 79 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 16 | MISSING SELECTOR | target | 22 | 152 | 304 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 4 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 19 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 36 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 20 | MISSING EFFECT | transform ~ … | 21 | 13 | 52 | Ulvenwald Captive // Ulvenwald Abomination, Seraph of New Capenna // Seraph of New Phyrexia, Sun-Blessed Guardian // Furnace-Blessed Conqueror |
| 21 | MISSING TRIGGER EVENT | Whenever ~ attacks | 21 | 10 | 21 | Durnan of the Yawning Portal, Acererak the Archlich, Edgar Markov |
| 22 | MISSING EFFECT | put n … | 20 | 61 | 126 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 23 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 36 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 24 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 19 | 19 | 19 | Dungeon Delver, Noble Heritage, Agent of the Iron Throne |
| 25 | MISSING SELECTOR | target creatures | 18 | 162 | 306 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 26 | MISSING EFFECT | until end of turn … | 18 | 138 | 213 | Divergent Growth, Doorman, Strength of Will |
| 27 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 22 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 28 | MISSING EFFECT | mill n … | 17 | 57 | 97 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 29 | MISSING EFFECT | if n … | 17 | 27 | 49 | Hot Pursuit, Zombie Ogre, Sidequest: Card Collection // Magicked Card |
| 30 | MISSING TRIGGER EVENT | Whenever you draw your second card each turn | 16 | 34 | 54 | Lat-Nam Adept, Detective of the Month, Loxodon Eavesdropper |
| 31 | MISSING COST | {M}, Sacrifice another creature | 16 | 27 | 51 | Sanguine Spy, Skyclave Shadowcat, Phyrexian Warhorse |
| 32 | MISSING TRIGGER EVENT | Whenever you draw N card(s)(s) | 16 | 16 | 40 | Moonring Mirror, Vodalian Wave-Knight, Sphinx's Tutelage |
| 33 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 27 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 34 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 35 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 36 | MISSING EFFECT | search your library for … | 14 | 146 | 250 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 37 | MISSING COST | {M}, {M}, Discard N card(s) | 14 | 69 | 79 | Arc Mage, Sparkspitter, Instigator |
| 38 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 22 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 39 | MISSING TRIGGER EVENT | Whenever another nontoken creature you control dies | 14 | 11 | 20 | Bhaal, Lord of Murder, Myrkul, Lord of Bones, Agent Venom |
| 40 | MISSING MECHANIC | sneak | 14 | 10 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 41 | MISSING EFFECT | exile ~ … | 14 | 9 | 52 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 42 | MISSING MECHANIC | firebending | 14 | 5 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 43 | MISSING MECHANIC | partner | 14 | 4 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 44 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 45 | MISSING EFFECT | ~ deals n … | 13 | 199 | 340 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 46 | MISSING EFFECT | discard n … | 13 | 32 | 68 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 47 | MISSING COST | {M}, Sacrifice an artifact | 13 | 19 | 32 | Embraal Gear-Smasher, Orcish Mechanics, Lobelia, Defender of Bag End |
| 48 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 49 | MISSING COST | {M}, Sacrifice N creature(s) | 12 | 56 | 75 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 50 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 26 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 51 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 52 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) you control deals combat damage to a player | 12 | 11 | 30 | Angel of Destiny, Reconnaissance Mission, Marisi, Breaker of the Coil |
| 53 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) an opponent controls dies | 12 | 10 | 25 | Kamber, the Plunderer, Toshiro Umezawa, The Meathook Massacre |
| 54 | MISSING TRIGGER EVENT | Whenever ~ becomes tapped | 11 | 38 | 51 | Seedship Agrarian, Gran-Gran, Nanoform Sentinel |
| 55 | MISSING EFFECT | create a n/n green … | 11 | 37 | 89 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 56 | MISSING EFFECT | add {m} … | 11 | 34 | 64 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 57 | MISSING EFFECT | create a n/n white … | 11 | 25 | 60 | Kaya, Spirits' Justice, Empyrial Storm, Archangel Elspeth |
| 58 | MISSING SELECTOR | target instant or sorcery card | 11 | 17 | 38 | Ogre Battlecaster, Impulsivity, Kishla Trawlers |
| 59 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 60 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 9 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 61 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 62 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 63 | MISSING TRIGGER EVENT | When ~ enter | 11 | 4 | 11 | Mikey & Mona, Mutant Sitters, Cloak and Dagger, Entwined, The Immortal Weapons |
| 64 | MISSING EFFECT | target creature you control … | 10 | 122 | 177 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 65 | MISSING COST | {M}, Discard N card(s) | 10 | 46 | 79 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 66 | MISSING EFFECT | create a n/n black … | 10 | 20 | 48 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 67 | MISSING TRIGGER EVENT | Whenever another creature you control dies | 10 | 14 | 27 | South Wind Avatar, Meren of Clan Nel Toth, Unruly Mob |
| 68 | MISSING EFFECT | exile up to n … | 10 | 14 | 24 | Liminal Hold, S.H.I.E.L.D. Flying Car, Flickering Hound |
| 69 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 13 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 70 | MISSING EFFECT | another target … | 10 | 11 | 22 | Bazaar Krovod, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 71 | MISSING TRIGGER EVENT | Whenever ~ deals combat damage to a player | 10 | 1 | 10 | Phage the Untouchable, Ezio Auditore da Firenze, Daxos of Meletis |
| 72 | MISSING EFFECT | choose target … | 9 | 60 | 74 | Arcbond, Deglamer, Wreck Hunter |
| 73 | MISSING EFFECT | gain control of target … | 9 | 50 | 79 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 74 | MISSING EFFECT | if you control n … | 9 | 43 | 71 | Discourtesy Clerk, Boundary Lands Ranger, Psemilla, Meletian Poet |
| 75 | MISSING TRIGGER EVENT | Whenever you cast a Spirit or Arcane spell | 9 | 39 | 49 | Kami of the Painted Road, Soul of Magma, Elder Pine of Jukai |
| 76 | MISSING EFFECT | if ~ … | 9 | 34 | 85 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 77 | MISSING EFFECT | create a n/n red … | 9 | 20 | 50 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 78 | MISSING TRIGGER EVENT | Whenever another creature dies | 9 | 18 | 25 | Reaper of the Wilds, Syr Konrad, the Grim, Deathbringer Thoctar |
| 79 | MISSING SELECTOR | target equipment | 9 | 15 | 22 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 80 | MISSING EFFECT | earthbend n … | 9 | 8 | 24 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 565 | 173 | 51 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 2 | MISSING EFFECT | choose n … | 528 | 46 | 45 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING EFFECT | ~ deals n … | 340 | 199 | 13 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 4 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 29 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 5 | UNSUPPORTED ORACLE PATTERN | planeswalker | 311 | 0 | 35 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 6 | MISSING SELECTOR | target creatures | 306 | 162 | 18 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 7 | MISSING SELECTOR | target | 304 | 152 | 22 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 8 | MISSING EFFECT | search your library for … | 250 | 146 | 14 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 9 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 10 | MISSING EFFECT | create n … | 233 | 111 | 28 | Summon the School, Cogwork Assembler, Endless Evil |
| 11 | MISSING EFFECT | destroy target … | 230 | 130 | 7 | Kalitas, Bloodchief of Ghet, Misfortune's Gain, Raze |
| 12 | MISSING MECHANIC | kicker | 224 | 0 | 7 | Strength of Night, Goblin Barrage, Archangel of Wrath |
| 13 | MISSING EFFECT | until end of turn … | 213 | 138 | 18 | Divergent Growth, Doorman, Strength of Will |
| 14 | MISSING EFFECT | look at the top … | 189 | 115 | 30 | Harald, King of Skemfar, Lantern of Revealing, Ponder |
| 15 | MISSING EFFECT | target creature gets ±n/±n … | 186 | 102 | 2 | Stern Marshal, Rig for War, Defiant Stand |
| 16 | MISSING SELECTOR | target creature card | 177 | 109 | 24 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 17 | MISSING EFFECT | target creature you control … | 177 | 122 | 10 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 18 | MISSING EFFECT | put a ±n/±n counter(s) … | 165 | 103 | 25 | Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin, Hired Claw |
| 19 | MISSING EFFECT | pay {m} … | 162 | 111 | 42 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 20 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 58 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 21 | MISSING EFFECT | put n … | 126 | 61 | 20 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 22 | MISSING EFFECT | exile target … | 121 | 77 | 3 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 23 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 51 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 24 | MANA ABILITY WORDING | {M}, … | 108 | 71 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 25 | MISSING EFFECT | you gain n … | 102 | 59 | 6 | Shu Farmer, Essence Pulse, Ajani Resolute |
| 26 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 88 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 27 | MISSING MECHANIC | ward | 97 | 8 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 28 | MISSING EFFECT | mill n … | 97 | 57 | 17 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 29 | MISSING SELECTOR | target player or planeswalker | 92 | 54 | 3 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 30 | MISSING TRIGGER EVENT | Whenever you attack | 90 | 37 | 40 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 31 | MISSING EFFECT | create a n/n green … | 89 | 37 | 11 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 32 | MISSING SELECTOR | target card | 88 | 47 | 3 | Funeral Pyre, Barkform Harvester, Carrion Locust |
| 33 | MISSING EFFECT | if ~ … | 85 | 34 | 9 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 34 | MISSING EFFECT | return target … | 84 | 46 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 35 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 22 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 36 | MISSING TRIGGER EVENT | Whenever you gain life | 79 | 42 | 28 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 37 | MISSING EFFECT | exile the top card … | 79 | 30 | 24 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 38 | MISSING COST | {M}, {M}, Discard N card(s) | 79 | 69 | 14 | Arc Mage, Sparkspitter, Instigator |
| 39 | MISSING COST | {M}, Discard N card(s) | 79 | 46 | 10 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 40 | MISSING EFFECT | gain control of target … | 79 | 50 | 9 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 41 | MISSING COST | {M}, Sacrifice N creature(s) | 75 | 56 | 12 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 42 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 36 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 43 | MISSING EFFECT | choose target … | 74 | 60 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 44 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 36 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 45 | MISSING EFFECT | if you control n … | 71 | 43 | 9 | Discourtesy Clerk, Boundary Lands Ranger, Psemilla, Meletian Poet |
| 46 | MISSING EFFECT | return ~ … | 70 | 48 | 8 | Eternal Dragon, Retrofitted Transmogrant, Tunnel Rats |
| 47 | MISSING EFFECT | discard n … | 68 | 32 | 13 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 48 | MISSING EFFECT | reveal the top n … | 68 | 50 | 7 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 49 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 27 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 50 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 34 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 230 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 35 | 28 | Ghostly Touch, Immobilizing Ink, Sunbond |
| 3 | template:Commander creatures you own have “…” | continuous | 0 | 23 | 23 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 4 | template:Enchanted creature gets ±N/±N and has “…” | continuous | 0 | 25 | 20 | Arcane Teachings, Lunarch Mantle, Deviant Glee |
| 5 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 6 | keyword:foretell | keyword | 0 | 51 | 18 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 7 | keyword:bestow | keyword | 0 | 42 | 18 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 8 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 9 | keyword:enchant | keyword | 0 | 67 | 15 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 10 | keyword:splice | keyword | 0 | 30 | 15 | Evermind, Horobi's Whisper, Desperate Ritual |
| 11 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 25 | 15 | Giant's Amulet, Iconic Shield, Candlestick |
| 12 | keyword:equip | keyword | 0 | 49 | 14 | Bloodthorn Flail, Strong Back, Team Pennant |
| 13 | template:~ enters prepared. | static | 0 | 40 | 14 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 14 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 15 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 13 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 16 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 17 | keyword:backup | keyword | 0 | 25 | 13 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 18 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 12 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 19 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 20 | template:All Slivers have “…” | continuous | 0 | 12 | 12 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 21 | keyword:overload | keyword | 0 | 27 | 11 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 22 | template:Modular N | static | 0 | 23 | 11 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 23 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 24 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 11 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 25 | template:Enchanted land has “…” | continuous | 0 | 12 | 11 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 26 | keyword:entwine | keyword | 0 | 32 | 10 | Road of Return, Rain of Rust, Blinding Beam |
| 27 | keyword:sneak | keyword | 0 | 27 | 10 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 28 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 29 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 30 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 31 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 10 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 32 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 33 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 34 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 35 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 36 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 37 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 38 | keyword:disguise | keyword | 0 | 43 | 9 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 39 | keyword:ninjutsu | keyword | 0 | 35 | 9 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 40 | keyword:warp | keyword | 0 | 31 | 9 | Starbreach Whale, Knight Luminary, Loading Zone |
| 41 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 42 | keyword:evolve | keyword | 0 | 22 | 9 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 43 | template:When ~ is put into a graveyard from the battlefield, return it to its owner's hand. | triggered | 0 | 20 | 9 | Spine of Ish Sah, Slow Motion, Fiery Mantle |
| 44 | keyword:living weapon | keyword | 0 | 19 | 9 | Nettlecyst, Lashwrithe, Skinwing |
| 45 | keyword:prototype | keyword | 0 | 19 | 9 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 46 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 9 | Voice of the Blessed, Essence Channeler, Wall of Limbs |
| 47 | keyword:retrace | keyword | 0 | 17 | 9 | Flame Jab, Monstrify, Waves of Aggression |
| 48 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 49 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 50 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 51 | keyword:ward | keyword | 0 | 97 | 8 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 52 | keyword:offspring | keyword | 0 | 20 | 8 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 53 | keyword:mentor | keyword | 0 | 19 | 8 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 54 | keyword:extort | keyword | 0 | 17 | 8 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 55 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 56 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 57 | keyword:umbra armor | keyword | 0 | 15 | 8 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 58 | template:Graft N | static | 0 | 13 | 8 | Cytoplast Manipulator, Sporeback Troll, Vigean Hydropon |
| 59 | template:When ~ is put into a graveyard from the battlefield, draw N card(s). | triggered | 0 | 13 | 8 | Nutrient Block, Implement of Examination, Implement of Malice |
| 60 | template:Whenever ~ deals combat damage to a player, that player discards N card(s). | triggered | 0 | 12 | 8 | Chilling Apparition, Banshee of the Dread Choir, Silent Specter |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 4373 | 13548 | 0 | 0 |
| Artifact | 760 | 2833 | 0 | 0 |
| Enchantment | 448 | 3199 | 0 | 0 |
| Sorcery | 686 | 2882 | 0 | 0 |
| Instant | 931 | 2823 | 0 | 0 |
| Land | 495 | 717 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
