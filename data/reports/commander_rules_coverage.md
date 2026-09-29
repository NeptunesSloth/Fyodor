# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 19:15

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 6672 | 20.8% |
| PARTIAL | 25396 | 79.1% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 174, PARTIAL 3327, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 76023 (67.1%) · unrecognized clauses: 37323
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.1% · unclassified clauses: 3269
- Distinct missing-capability clusters: 9806

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11087 | 13272 |
| MISSING TRIGGER EVENT | 5856 | 6216 |
| MISSING SELECTOR | 3646 | 3866 |
| MISSING CONTINUOUS EFFECT | 2830 | 3007 |
| UNSUPPORTED ORACLE PATTERN | 2480 | 3269 |
| MISSING MECHANIC | 2002 | 2065 |
| MISSING COST | 1761 | 1841 |
| MISSING REPLACEMENT PATTERN | 1387 | 1426 |
| MISSING RESTRICTION | 991 | 1037 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 52 | 181 | 584 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 2 | MISSING MECHANIC | ward | 47 | 8 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 3 | MISSING EFFECT | choose n … | 45 | 46 | 538 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 4 | MISSING EFFECT | look at the top … | 43 | 190 | 299 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 5 | MISSING EFFECT | pay {m} … | 42 | 110 | 162 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 6 | MISSING TRIGGER EVENT | Whenever you attack | 40 | 37 | 90 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 7 | UNSUPPORTED ORACLE PATTERN | planeswalker | 35 | 0 | 311 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 8 | MISSING EFFECT | search your library for … | 32 | 277 | 423 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 9 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 49 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 10 | MISSING EFFECT | create n … | 28 | 112 | 236 | Summon the School, Cogwork Assembler, Endless Evil |
| 11 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 58 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 12 | MISSING TRIGGER EVENT | Whenever you gain life | 28 | 42 | 79 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 13 | MISSING EFFECT | put a ±n/±n counter(s) … | 26 | 110 | 183 | Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin, Hired Claw |
| 14 | MISSING TRIGGER EVENT | When ~ enters | 26 | 10 | 26 | Kiora of Fire and Ashes, Sharuum the Hegemon, Phage the Untouchable |
| 15 | MISSING SELECTOR | target creature card | 24 | 110 | 180 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 16 | MISSING EFFECT | exile the top card … | 24 | 30 | 79 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 17 | MISSING SELECTOR | target | 23 | 164 | 320 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 18 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 3 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 19 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 20 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 34 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 21 | MISSING EFFECT | transform ~ … | 21 | 13 | 52 | Ulvenwald Captive // Ulvenwald Abomination, Seraph of New Capenna // Seraph of New Phyrexia, Sun-Blessed Guardian // Furnace-Blessed Conqueror |
| 22 | MISSING TRIGGER EVENT | Whenever ~ attacks | 21 | 10 | 21 | Durnan of the Yawning Portal, Acererak the Archlich, Edgar Markov |
| 23 | MISSING EFFECT | put n … | 20 | 62 | 131 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 24 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 35 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 25 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 19 | 19 | 19 | Dungeon Delver, Noble Heritage, Agent of the Iron Throne |
| 26 | MISSING SELECTOR | target creatures | 18 | 162 | 306 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 27 | MISSING EFFECT | until end of turn … | 18 | 138 | 213 | Divergent Growth, Doorman, Strength of Will |
| 28 | MISSING EFFECT | mill n … | 18 | 63 | 107 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 29 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 22 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 30 | MISSING EFFECT | if n … | 17 | 27 | 49 | Hot Pursuit, Zombie Ogre, Sidequest: Card Collection // Magicked Card |
| 31 | MISSING TRIGGER EVENT | Whenever you draw your second card each turn | 16 | 33 | 54 | Lat-Nam Adept, Detective of the Month, Loxodon Eavesdropper |
| 32 | MISSING COST | {M}, Sacrifice another creature | 16 | 27 | 51 | Sanguine Spy, Skyclave Shadowcat, Phyrexian Warhorse |
| 33 | MISSING TRIGGER EVENT | Whenever you draw N card(s)(s) | 16 | 16 | 40 | Moonring Mirror, Vodalian Wave-Knight, Sphinx's Tutelage |
| 34 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 27 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 35 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 36 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 37 | MISSING EFFECT | ~ deals n … | 14 | 207 | 351 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 38 | MISSING COST | {M}, {M}, Discard N card(s) | 14 | 69 | 79 | Arc Mage, Sparkspitter, Instigator |
| 39 | MISSING EFFECT | discard n … | 14 | 35 | 73 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 40 | MISSING TRIGGER EVENT | Whenever you cast your second spell each turn | 14 | 21 | 34 | Sunstar Lightsmith, Wanda's Vision, Kraum, Violent Cacophony |
| 41 | MISSING TRIGGER EVENT | Whenever another nontoken creature you control dies | 14 | 11 | 20 | Bhaal, Lord of Murder, Myrkul, Lord of Bones, Agent Venom |
| 42 | MISSING MECHANIC | sneak | 14 | 8 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 43 | MISSING EFFECT | exile ~ … | 14 | 7 | 52 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 44 | MISSING MECHANIC | partner | 14 | 4 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 45 | MISSING MECHANIC | firebending | 14 | 4 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 46 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 47 | MISSING COST | {M}, Sacrifice an artifact | 13 | 18 | 32 | Embraal Gear-Smasher, Orcish Mechanics, Lobelia, Defender of Bag End |
| 48 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 49 | MISSING EFFECT | target creature you control … | 12 | 124 | 181 | Oracle's Restoration, Blessed Defiance, Hard-Hitting Question |
| 50 | MISSING COST | {M}, Sacrifice N creature(s) | 12 | 55 | 75 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 51 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 25 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 52 | MISSING EFFECT | another target … | 12 | 16 | 29 | Bazaar Krovod, Syr Faren, the Hengehammer, Eardrum Rattler |
| 53 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 54 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) you control deals combat damage to a player | 12 | 10 | 30 | Angel of Destiny, Reconnaissance Mission, Marisi, Breaker of the Coil |
| 55 | MISSING TRIGGER EVENT | Whenever N creature(s)(s) an opponent controls dies | 12 | 10 | 25 | Kamber, the Plunderer, Toshiro Umezawa, The Meathook Massacre |
| 56 | MISSING EFFECT | return ~ … | 11 | 79 | 121 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 57 | MISSING TRIGGER EVENT | Whenever ~ becomes tapped | 11 | 38 | 51 | Seedship Agrarian, Gran-Gran, Nanoform Sentinel |
| 58 | MISSING EFFECT | create a n/n green … | 11 | 36 | 90 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 59 | MISSING EFFECT | add {m} … | 11 | 34 | 64 | Akki Rockspeaker, Brightstone Ritual, Infernal Plunge |
| 60 | MISSING EFFECT | create a n/n white … | 11 | 25 | 60 | Kaya, Spirits' Justice, Empyrial Storm, Archangel Elspeth |
| 61 | MISSING SELECTOR | target instant or sorcery card | 11 | 17 | 38 | Ogre Battlecaster, Impulsivity, Kishla Trawlers |
| 62 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 63 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 9 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 64 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 65 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 66 | MISSING TRIGGER EVENT | When ~ enter | 11 | 4 | 11 | Mikey & Mona, Mutant Sitters, Cloak and Dagger, Entwined, The Immortal Weapons |
| 67 | MISSING COST | {M}, Discard N card(s) | 10 | 46 | 79 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 68 | MISSING EFFECT | create a n/n black … | 10 | 21 | 49 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 69 | MISSING TRIGGER EVENT | Whenever another creature you control dies | 10 | 14 | 27 | South Wind Avatar, Meren of Clan Nel Toth, Unruly Mob |
| 70 | MISSING EFFECT | exile up to n … | 10 | 14 | 24 | Liminal Hold, S.H.I.E.L.D. Flying Car, Flickering Hound |
| 71 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 13 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 72 | MISSING TRIGGER EVENT | Whenever ~ deals combat damage to a player | 10 | 1 | 10 | Phage the Untouchable, Ezio Auditore da Firenze, Daxos of Meletis |
| 73 | MISSING EFFECT | you gain n … | 9 | 71 | 120 | River Hoopoe, Tatyova, Benthic Druid, Shu Farmer |
| 74 | MISSING EFFECT | choose target … | 9 | 60 | 74 | Arcbond, Deglamer, Wreck Hunter |
| 75 | MISSING EFFECT | gain control of target … | 9 | 50 | 79 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 76 | MISSING EFFECT | if you control n … | 9 | 41 | 71 | Discourtesy Clerk, Boundary Lands Ranger, Psemilla, Meletian Poet |
| 77 | MISSING TRIGGER EVENT | Whenever you cast a Spirit or Arcane spell | 9 | 39 | 49 | Kami of the Painted Road, Soul of Magma, Elder Pine of Jukai |
| 78 | MISSING EFFECT | if ~ … | 9 | 34 | 85 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 79 | MISSING EFFECT | create a n/n red … | 9 | 20 | 50 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 80 | MISSING TRIGGER EVENT | Whenever another creature dies | 9 | 18 | 25 | Reaper of the Wilds, Syr Konrad, the Grim, Deathbringer Thoctar |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 584 | 181 | 52 | Errand-Rider of Gondor, Heal, Grip of Amnesia |
| 2 | MISSING EFFECT | choose n … | 538 | 46 | 45 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING EFFECT | search your library for … | 423 | 277 | 32 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 4 | MISSING EFFECT | ~ deals n … | 351 | 207 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING SELECTOR | target | 320 | 164 | 23 | Cinder Elemental, Archangel of Wrath, Granger Guildmage |
| 6 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 29 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 7 | UNSUPPORTED ORACLE PATTERN | planeswalker | 311 | 0 | 35 | Tamiyo, Compleated Sage, Jace, the Perfected Mind, Huatli, Dinosaur Knight |
| 8 | MISSING SELECTOR | target creatures | 306 | 162 | 18 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 9 | MISSING EFFECT | look at the top … | 299 | 190 | 43 | Harald, King of Skemfar, Courageous Outrider, Lantern of Revealing |
| 10 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 11 | MISSING EFFECT | create n … | 236 | 112 | 28 | Summon the School, Cogwork Assembler, Endless Evil |
| 12 | MISSING EFFECT | destroy target … | 233 | 133 | 7 | Kalitas, Bloodchief of Ghet, Misfortune's Gain, Raze |
| 13 | MISSING MECHANIC | kicker | 224 | 0 | 7 | Strength of Night, Goblin Barrage, Archangel of Wrath |
| 14 | MISSING EFFECT | until end of turn … | 213 | 138 | 18 | Divergent Growth, Doorman, Strength of Will |
| 15 | MISSING EFFECT | target creature gets ±n/±n … | 186 | 102 | 2 | Stern Marshal, Rig for War, Defiant Stand |
| 16 | MISSING EFFECT | put a ±n/±n counter(s) … | 183 | 110 | 26 | Gollum, Silent Slinker // Meager Meal, Ent-Draught Basin, Hired Claw |
| 17 | MISSING EFFECT | target creature you control … | 181 | 124 | 12 | Oracle's Restoration, Blessed Defiance, Hard-Hitting Question |
| 18 | MISSING SELECTOR | target creature card | 180 | 110 | 24 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 19 | MISSING EFFECT | pay {m} … | 162 | 110 | 42 | Minion Reflector, Giant's Amulet, Order of the Golden Cricket |
| 20 | MISSING EFFECT | put n … | 131 | 62 | 20 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 21 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 58 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 22 | MISSING EFFECT | exile target … | 125 | 78 | 4 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 23 | MISSING EFFECT | return ~ … | 121 | 79 | 11 | Palinchron, Etherium-Horn Sorcerer, Eternal Dragon |
| 24 | MISSING EFFECT | you gain n … | 120 | 71 | 9 | River Hoopoe, Tatyova, Benthic Druid, Shu Farmer |
| 25 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 49 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 26 | MANA ABILITY WORDING | {M}, … | 108 | 69 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 27 | MISSING EFFECT | mill n … | 107 | 63 | 18 | Sparring Dummy, Beluna Grandsquall // Seek Thrills, Cache Grab |
| 28 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 87 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 29 | MISSING MECHANIC | ward | 97 | 8 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 30 | MISSING SELECTOR | target player or planeswalker | 92 | 54 | 3 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 31 | MISSING TRIGGER EVENT | Whenever you attack | 90 | 37 | 40 | Labyrinth Adversary, Karlach, Fury of Avernus, Director Nick Fury |
| 32 | MISSING EFFECT | create a n/n green … | 90 | 36 | 11 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 33 | MISSING SELECTOR | target card | 89 | 47 | 4 | Funeral Pyre, Barkform Harvester, Carrion Locust |
| 34 | MISSING EFFECT | if ~ … | 85 | 34 | 9 | Warden of the First Tree, Blinkmoth Urn, Mad Dog |
| 35 | MISSING EFFECT | return target … | 84 | 46 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 36 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 22 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 37 | MISSING TRIGGER EVENT | Whenever you gain life | 79 | 42 | 28 | South Wind Avatar, Voice of the Blessed, MJ, Rising Star |
| 38 | MISSING EFFECT | exile the top card … | 79 | 30 | 24 | Mezzio Mugger, Etali, Primal Storm, Abbot of Keral Keep |
| 39 | MISSING COST | {M}, {M}, Discard N card(s) | 79 | 69 | 14 | Arc Mage, Sparkspitter, Instigator |
| 40 | MISSING COST | {M}, Discard N card(s) | 79 | 46 | 10 | Viashino Lashclaw, Haunted Dead, Junk Golem |
| 41 | MISSING EFFECT | gain control of target … | 79 | 50 | 9 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 42 | MISSING COST | {M}, Sacrifice N creature(s) | 75 | 55 | 12 | Ruthless Knave, Tymaret, the Murder King, Starved Rusalka |
| 43 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 34 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 44 | MISSING EFFECT | choose target … | 74 | 60 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 45 | MISSING EFFECT | discard n … | 73 | 35 | 14 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 46 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 35 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 47 | MISSING EFFECT | if you control n … | 71 | 41 | 9 | Discourtesy Clerk, Boundary Lands Ranger, Psemilla, Meletian Poet |
| 48 | MISSING EFFECT | you draw n … | 71 | 37 | 8 | Live Fast, Vraska, Betrayal's Sting, Greed's Gambit |
| 49 | MISSING EFFECT | tap target … | 71 | 41 | 2 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 50 | MISSING EFFECT | reveal the top n … | 68 | 50 | 7 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 224 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 37 | 28 | Ghostly Touch, Immobilizing Ink, Sunbond |
| 3 | template:Commander creatures you own have “…” | continuous | 0 | 23 | 23 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 4 | template:{M}: Return ~ to its owner's hand. | activated | 0 | 33 | 20 | Palinchron, Etherium-Horn Sorcerer, Shackles |
| 5 | template:Enchanted creature gets ±N/±N and has “…” | continuous | 0 | 25 | 20 | Arcane Teachings, Lunarch Mantle, Deviant Glee |
| 6 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 7 | keyword:bestow | keyword | 0 | 42 | 18 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 8 | keyword:foretell | keyword | 0 | 51 | 17 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 9 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 10 | keyword:splice | keyword | 0 | 30 | 15 | Evermind, Horobi's Whisper, Desperate Ritual |
| 11 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 25 | 15 | Giant's Amulet, Iconic Shield, Candlestick |
| 12 | template:When ~ enters, tap enchanted creature. | triggered | 0 | 29 | 14 | Waterknot, Colossification, Tangle Kelp |
| 13 | keyword:equip | keyword | 0 | 49 | 13 | Bloodthorn Flail, Strong Back, Team Pennant |
| 14 | template:~ enters prepared. | static | 0 | 40 | 13 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 15 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 16 | keyword:backup | keyword | 0 | 25 | 13 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 17 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 13 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 18 | template:All Slivers have “…” | continuous | 0 | 13 | 13 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 19 | keyword:enchant | keyword | 0 | 67 | 12 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 20 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 12 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 21 | keyword:myriad | keyword | 0 | 23 | 12 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 22 | template:Enchanted land has “…” | continuous | 0 | 13 | 12 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 23 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 11 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 24 | keyword:overload | keyword | 0 | 27 | 11 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 25 | template:Modular N | static | 0 | 23 | 11 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 26 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 27 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 11 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 28 | keyword:entwine | keyword | 0 | 32 | 10 | Road of Return, Rain of Rust, Blinding Beam |
| 29 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
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
| 42 | keyword:prototype | keyword | 0 | 19 | 9 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 43 | template:Whenever you gain life, put a ±N/±N counter(s) on ~. | triggered | 0 | 19 | 9 | Voice of the Blessed, Essence Channeler, Wall of Limbs |
| 44 | template:{M}: Enchanted creature gets ±N/±N until end of turn. | activated | 0 | 15 | 9 | Keldon Mantle, Flowstone Embrace, Fiery Mantle |
| 45 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 46 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 9 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 47 | template:Whenever you draw your second card each turn, put a ±N/±N counter(s) on ~. | triggered | 0 | 12 | 9 | Lat-Nam Adept, Blue Marvel, Adam Brashear, Kid Loki |
| 48 | template:Whenever ~ or another Ally you control enters, you may put a ±N/±N counter(s) on ~. | triggered | 0 | 9 | 9 | Kazandu Blademaster, Tuktuk Grunts, Oran-Rief Survivalist |
| 49 | keyword:ward | keyword | 0 | 97 | 8 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 50 | keyword:disguise | keyword | 0 | 43 | 8 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 51 | keyword:ninjutsu | keyword | 0 | 35 | 8 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 52 | keyword:warp | keyword | 0 | 31 | 8 | Starbreach Whale, Knight Luminary, Loading Zone |
| 53 | keyword:sneak | keyword | 0 | 27 | 8 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 54 | template:When ~ is put into a graveyard from the battlefield, return it to its owner's hand. | triggered | 0 | 20 | 8 | Spine of Ish Sah, Slow Motion, Fiery Mantle |
| 55 | keyword:living weapon | keyword | 0 | 19 | 8 | Nettlecyst, Lashwrithe, Skinwing |
| 56 | keyword:mentor | keyword | 0 | 19 | 8 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 57 | keyword:extort | keyword | 0 | 17 | 8 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 58 | keyword:retrace | keyword | 0 | 17 | 8 | Flame Jab, Monstrify, Waves of Aggression |
| 59 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |
| 60 | keyword:embalm | keyword | 0 | 15 | 8 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 4109 | 13812 | 0 | 0 |
| Artifact | 715 | 2878 | 0 | 0 |
| Enchantment | 362 | 3285 | 0 | 0 |
| Sorcery | 554 | 3014 | 0 | 0 |
| Instant | 859 | 2895 | 0 | 0 |
| Land | 469 | 743 | 0 | 0 |
| Planeswalker | 0 | 311 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14115, spell_effect 9123, activated 7358, continuous 4014, static 3069, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
