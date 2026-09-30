# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-30 03:09

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32068**

| Level | Cards | Share |
|---|---|---|
| FULL | 10950 | 34.1% |
| PARTIAL | 21118 | 65.9% |
| REVIEW | 0 | 0.0% |
| MANUAL | 0 | 0.0% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 530, PARTIAL 2971, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113154
- Automated: 83378 (73.7%) · unrecognized clauses: 29776
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.7% · unclassified clauses: 2630
- Distinct missing-capability clusters: 8216

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 11157 | 13104 |
| MISSING SELECTOR | 3391 | 3591 |
| MISSING TRIGGER EVENT | 2403 | 2515 |
| MISSING CONTINUOUS EFFECT | 2167 | 2290 |
| UNSUPPORTED ORACLE PATTERN | 1978 | 2630 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1362 | 1401 |
| MISSING COST / PERMISSION RULE | 800 | 810 |
| MISSING RESTRICTION | 659 | 693 |
| MISSING COST | 485 | 498 |
| MANA ABILITY WORDING | 364 | 366 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 66 | 226 | 576 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 65 | 50 | 553 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING EFFECT | put a ±n/±n counter(s) … | 61 | 161 | 231 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 4 | MISSING EFFECT | pay {m} … | 54 | 113 | 169 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 5 | MISSING MECHANIC | ward | 47 | 13 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING SELECTOR | target | 36 | 198 | 321 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 7 | MISSING EFFECT | look at the top … | 33 | 139 | 185 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 8 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 59 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 9 | MISSING EFFECT | put n … | 28 | 100 | 150 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 10 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 68 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 11 | MISSING EFFECT | create n … | 27 | 123 | 206 | Summon the School, Cogwork Assembler, Endless Evil |
| 12 | MISSING SELECTOR | target creature card | 25 | 114 | 169 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 13 | MISSING EFFECT | exile the top card … | 25 | 31 | 60 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 14 | MISSING EFFECT | if n … | 24 | 61 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 15 | MISSING EFFECT | until end of turn … | 23 | 161 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 27 | 70 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 7 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | MISSING EFFECT | exile ~ … | 20 | 13 | 61 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 19 | MISSING EFFECT | if ~ … | 19 | 77 | 130 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 20 | MISSING EFFECT | mill n … | 18 | 67 | 101 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 21 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 30 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 22 | MISSING EFFECT | search your library for … | 16 | 171 | 261 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 23 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 24 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 31 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 25 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 26 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 27 | MISSING EFFECT | ~ deals n … | 14 | 209 | 317 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 28 | MISSING EFFECT | return ~ … | 14 | 90 | 130 | Summon the School, Dragon Fangs, Haunted Dead |
| 29 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 14 | 28 | 47 | Bedlam Reveler, Gargantuan Leech, Cryptic Serpent |
| 30 | MISSING MECHANIC | sneak | 14 | 12 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 31 | MISSING MECHANIC | firebending | 14 | 8 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 32 | MISSING MECHANIC | partner | 14 | 6 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 33 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 34 | MISSING EFFECT | add {m} … | 13 | 42 | 70 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 35 | MISSING EFFECT | create a n/n red … | 13 | 29 | 50 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 36 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 37 | MISSING SELECTOR | target equipment | 12 | 19 | 26 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 38 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 39 | MISSING EFFECT | create a n/n white … | 11 | 33 | 54 | Empyrial Storm, Drag the Canal, Experimental Synthesizer |
| 40 | MISSING EFFECT | another target … | 11 | 15 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 41 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 42 | MISSING EFFECT | earthbend n … | 11 | 14 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 43 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 44 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 45 | MISSING EFFECT | reveal the top card … | 10 | 36 | 48 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 46 | MISSING SELECTOR | target creature card with mana value | 10 | 27 | 39 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 47 | MISSING SELECTOR | target instant or sorcery card | 10 | 18 | 30 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 48 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 10 | 12 | 25 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 49 | MISSING EFFECT | return it to the … | 10 | 11 | 23 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 50 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 10 | 8 | 14 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 51 | MISSING EFFECT | target creature you control … | 9 | 122 | 176 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 52 | MISSING SELECTOR | target creatures | 9 | 107 | 207 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 53 | MISSING EFFECT | choose target … | 9 | 71 | 83 | Arcbond, Deglamer, Wreck Hunter |
| 54 | MISSING EFFECT | you gain n … | 9 | 65 | 90 | Belladonna Took, Shu Farmer, Essence Pulse |
| 55 | MISSING EFFECT | exile the top n … | 9 | 17 | 41 | Memorial Vault, Crossover Collaboration, Ral, Monsoon Mage // Ral, Leyline Prodigy |
| 56 | MISSING EFFECT | exile up to n … | 9 | 17 | 26 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 57 | MISSING EFFECT | double the number of … | 9 | 12 | 24 | Fractal Harness, Primordial Hydra, The Millennium Calendar |
| 58 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 8 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 59 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 60 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 61 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 62 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 63 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 64 | MISSING COST | {M}, Discard ~ | 8 | 35 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 65 | MISSING EFFECT | create a n/n colorless … | 8 | 34 | 54 | Karn, Scion of Urza, Serpent Generator, Command the Stage |
| 66 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 18 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 67 | MISSING EFFECT | you draw n … | 8 | 17 | 31 | Fang, Fearless l'Cie, Live Fast, Greed's Gambit |
| 68 | MISSING EFFECT | up to n … | 8 | 15 | 32 | Wasp, Shrinking Savior, Restless Vinestalk, Kaito, Dancing Shadow |
| 69 | MISSING EFFECT | discard your hand … | 8 | 15 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 70 | MISSING EFFECT | discard n … | 8 | 14 | 26 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 71 | UNSUPPORTED ORACLE PATTERN | Mayhem {M} | 8 | 7 | 11 | Swarm, Being of Bees, Chameleon, Master of Disguise, Spider-Islanders |
| 72 | MISSING CONTINUOUS EFFECT | During your turn, … | 8 | 6 | 17 | Long-Lost Lances, Miriam, Herd Whisperer, Yuna, Hope of Spira |
| 73 | UNSUPPORTED ORACLE PATTERN | You may play an additional land … | 8 | 6 | 17 | Exploration, Icetill Explorer, Case of the Locked Hothouse |
| 74 | MISSING EFFECT | you get an experience … | 8 | 0 | 8 | Meren of Clan Nel Toth, Katara, Waterbending Master, Ezuri, Claw of Progress |
| 75 | MISSING EFFECT | if you control n … | 7 | 39 | 63 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 76 | MISSING SELECTOR | target artifact or creature | 7 | 30 | 51 | Tamiyo, Compleated Sage, Starke of Rath, Mind Transfer Protocol |
| 77 | MISSING EFFECT | each opponent loses n … | 7 | 28 | 40 | Subversion, Faerie Bladecrafter, Scholar of Athreos |
| 78 | MISSING EFFECT | if you cast it … | 7 | 24 | 38 | Weftwalking, Marina Vendrell's Grimoire, Bringer of the Last Gift |
| 79 | MISSING EFFECT | create a n/n black … | 7 | 23 | 38 | Grist, the Hunger Tide, Ghoulcaller's Accomplice, Balduvian Dead |
| 80 | MANA ABILITY WORDING | {M}: Add {M}. Spend this mana … | 7 | 23 | 27 | Guidelight Optimizer, Karfell Harbinger, Soldevi Machinist |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 576 | 226 | 66 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 553 | 50 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 3 | MISSING SELECTOR | target | 321 | 198 | 36 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING EFFECT | ~ deals n … | 317 | 209 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 36 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 261 | 171 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 8 | MISSING EFFECT | put a ±n/±n counter(s) … | 231 | 161 | 61 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 9 | MISSING EFFECT | until end of turn … | 227 | 161 | 23 | Divergent Growth, Doorman, Strength of Will |
| 10 | MISSING SELECTOR | target creatures | 207 | 107 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 11 | MISSING EFFECT | create n … | 206 | 123 | 27 | Summon the School, Cogwork Assembler, Endless Evil |
| 12 | MISSING EFFECT | destroy target … | 187 | 112 | 4 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 13 | MISSING EFFECT | look at the top … | 185 | 139 | 33 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 14 | MISSING EFFECT | target creature you control … | 176 | 122 | 9 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 15 | MISSING EFFECT | pay {m} … | 169 | 113 | 54 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 16 | MISSING SELECTOR | target creature card | 169 | 114 | 25 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 169 | 102 | 4 | Stern Marshal, Spontaneous Flight, Rig for War |
| 18 | MISSING EFFECT | put n … | 150 | 100 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING EFFECT | if ~ … | 130 | 77 | 19 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 20 | MISSING EFFECT | return ~ … | 130 | 90 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 21 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 68 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 22 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 59 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 23 | MISSING SELECTOR | target player or planeswalker | 111 | 79 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 24 | MANA ABILITY WORDING | {M}, … | 108 | 78 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 25 | MISSING EFFECT | mill n … | 101 | 67 | 18 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 26 | MISSING EFFECT | exile target … | 99 | 66 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 27 | MISSING MECHANIC | ward | 97 | 13 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 28 | MISSING EFFECT | if n … | 92 | 61 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 29 | MISSING EFFECT | you gain n … | 90 | 65 | 9 | Belladonna Took, Shu Farmer, Essence Pulse |
| 30 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 31 | MISSING EFFECT | choose target … | 83 | 71 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 32 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 30 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 33 | MISSING SELECTOR | target opponent reveals their hand | 79 | 53 | 1 | Gix's Caress, Mindclaw Shaman, Grief |
| 34 | MISSING EFFECT | tap target … | 78 | 45 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 35 | MISSING EFFECT | if there are n … | 76 | 32 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 36 | MISSING EFFECT | it deals n … | 75 | 60 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 37 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 38 | MISSING EFFECT | transform ~ … | 70 | 27 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 39 | MISSING EFFECT | add {m} … | 70 | 42 | 13 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 40 | MISSING EFFECT | return target … | 69 | 42 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 41 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 31 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 42 | MISSING EFFECT | create a n/n green … | 67 | 35 | 6 | Rhonas's Last Stand, Fractal Harness, Baloth Cage Trap |
| 43 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 37 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |
| 44 | MISSING EFFECT | if you control n … | 63 | 39 | 7 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 45 | MISSING EFFECT | exile ~ … | 61 | 13 | 20 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 46 | MISSING EFFECT | exile the top card … | 60 | 31 | 25 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 47 | MISSING EFFECT | you get an emblem … | 60 | 14 | 4 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 48 | MISSING REPLACEMENT PATTERN | Prevent all damage that would be dealt … | 59 | 38 | 6 | Comeuppance, Gideon's Intervention, Ethereal Haze |
| 49 | MISSING COST | {M}, Discard ~ | 57 | 35 | 8 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 50 | MISSING REPLACEMENT PATTERN | Prevent all combat damage that would be … | 57 | 41 | 2 | Candletrap, Armored Transport, Sandskin |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 364 | 253 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | keyword:bestow | keyword | 0 | 42 | 25 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 3 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 4 | keyword:foretell | keyword | 0 | 51 | 21 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 5 | template:Enchanted creature has “…” | continuous | 0 | 25 | 21 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 6 | keyword:enchant | keyword | 0 | 67 | 20 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 7 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 19 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 8 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 9 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 10 | keyword:equip | keyword | 0 | 49 | 18 | Bloodthorn Flail, Strong Back, Team Pennant |
| 11 | keyword:backup | keyword | 0 | 25 | 18 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 12 | template:Equipped creature has “…” | continuous | 0 | 24 | 17 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 13 | keyword:warp | keyword | 0 | 31 | 16 | Starbreach Whale, Knight Luminary, Loading Zone |
| 14 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 15 | template:Modular N | static | 0 | 23 | 16 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 16 | keyword:encore | keyword | 0 | 26 | 15 | Impulsivity, Sliver Gravemother, Belonging |
| 17 | keyword:myriad | keyword | 0 | 23 | 14 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 18 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 19 | keyword:ward | keyword | 0 | 97 | 13 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 20 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 13 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 21 | keyword:entwine | keyword | 0 | 32 | 13 | Road of Return, Rain of Rust, Blinding Beam |
| 22 | keyword:ninjutsu | keyword | 0 | 35 | 12 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 23 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 24 | keyword:sneak | keyword | 0 | 27 | 12 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 25 | keyword:offspring | keyword | 0 | 20 | 12 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 26 | keyword:unleash | keyword | 0 | 15 | 12 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 27 | keyword:disguise | keyword | 0 | 43 | 11 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 28 | template:{M}: Adapt N. | activated | 0 | 22 | 11 | Zegana, Utopian Speaker, Temperamental Oozewagg, Evolution Witness |
| 29 | keyword:living weapon | keyword | 0 | 19 | 11 | Nettlecyst, Lashwrithe, Skinwing |
| 30 | keyword:mentor | keyword | 0 | 19 | 11 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 31 | keyword:retrace | keyword | 0 | 17 | 11 | Flame Jab, Monstrify, Waves of Aggression |
| 32 | keyword:umbra armor | keyword | 0 | 15 | 11 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 33 | keyword:rampage | keyword | 0 | 12 | 11 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 34 | template:Enchanted land has “…” | continuous | 0 | 12 | 11 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 35 | template:All Slivers have “…” | continuous | 0 | 11 | 11 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 36 | keyword:evolve | keyword | 0 | 22 | 10 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 37 | keyword:prototype | keyword | 0 | 19 | 10 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 38 | keyword:embalm | keyword | 0 | 15 | 10 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 39 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 40 | keyword:battle cry | keyword | 0 | 13 | 10 | Goblin Wardriver, Hero of Bladehold, Iraxxa, Empress of Mars |
| 41 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 42 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 43 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 44 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 45 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 46 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 47 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 48 | keyword:plot | keyword | 0 | 33 | 9 | Unscrupulous Contractor, Pyretic Charge, Freestrider Commando |
| 49 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 50 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 51 | keyword:vanishing | keyword | 0 | 20 | 9 | Soultether Golem, Deadly Grub, Reality Acid |
| 52 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 53 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 54 | keyword:blitz | keyword | 0 | 16 | 9 | Mezzio Mugger, Workshop Warchief, Riveteers Decoy |
| 55 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 56 | keyword:enlist | keyword | 0 | 12 | 9 | Keldon Flamesage, Benalish Faithbonder, Aradesh, the Founder |
| 57 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 58 | keyword:kicker | keyword | 0 | 37 | 8 | Goblin Barrage, Archangel of Wrath, Anavolver |
| 59 | template:You have no maximum hand size. | continuous | 0 | 23 | 8 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 60 | keyword:firebending | keyword | 0 | 22 | 8 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 6866 | 11055 | 0 | 0 |
| Artifact | 1102 | 2491 | 0 | 0 |
| Enchantment | 923 | 2724 | 0 | 0 |
| Sorcery | 928 | 2640 | 0 | 0 |
| Instant | 1205 | 2549 | 0 | 0 |
| Land | 538 | 674 | 0 | 0 |
| Planeswalker | 17 | 294 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14139, spell_effect 9115, activated 7339, continuous 3999, static 2899, mana_ability 2035, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 206, alternative_cost 180
