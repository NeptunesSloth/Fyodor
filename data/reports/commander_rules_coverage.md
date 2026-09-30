# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-30 13:29

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32068**

| Level | Cards | Share |
|---|---|---|
| FULL | 12091 | 37.7% |
| PARTIAL | 19977 | 62.3% |
| REVIEW | 0 | 0.0% |
| MANUAL | 0 | 0.0% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 619, PARTIAL 2882, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113154
- Automated: 85197 (75.3%) · unrecognized clauses: 27957
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.7% · unclassified clauses: 2622
- Distinct missing-capability clusters: 8073

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 10576 | 12403 |
| MISSING SELECTOR | 2981 | 3160 |
| MISSING TRIGGER EVENT | 2398 | 2509 |
| UNSUPPORTED ORACLE PATTERN | 1972 | 2622 |
| MISSING CONTINUOUS EFFECT | 1859 | 1968 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1021 | 1052 |
| MISSING COST / PERMISSION RULE | 800 | 810 |
| MISSING RESTRICTION | 658 | 692 |
| MISSING COST | 484 | 497 |
| MANA ABILITY WORDING | 364 | 366 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 65 | 50 | 520 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 2 | MISSING EFFECT | put a ±n/±n counter(s) … | 57 | 134 | 199 | Yorvo, Lord of Garenbrig, Ent-Draught Basin, Hired Claw |
| 3 | MISSING EFFECT | draw n … | 54 | 200 | 502 | Errand-Rider of Gondor, Krovikan Sorcerer, Grip of Amnesia |
| 4 | MISSING EFFECT | pay {m} … | 54 | 114 | 167 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 5 | MISSING MECHANIC | ward | 47 | 17 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING SELECTOR | target | 35 | 193 | 308 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 7 | MISSING EFFECT | look at the top … | 31 | 125 | 167 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 8 | MISSING EFFECT | create n … | 27 | 108 | 183 | Summon the School, Cogwork Assembler, Endless Evil |
| 9 | MISSING EFFECT | exile the top card … | 25 | 31 | 59 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 10 | MISSING SELECTOR | target creature card | 24 | 102 | 155 | Puppeteer Clique, Metamorphosis Fanatic, Sword of Light and Shadow |
| 11 | MISSING EFFECT | if n … | 24 | 64 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 12 | MISSING EFFECT | until end of turn … | 23 | 167 | 227 | Divergent Growth, Doorman, Strength of Will |
| 13 | MISSING EFFECT | transform ~ … | 23 | 29 | 70 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 14 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 9 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 15 | MISSING EFFECT | put n … | 21 | 88 | 125 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 16 | MISSING EFFECT | if ~ … | 19 | 78 | 130 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 17 | MISSING EFFECT | mill n … | 18 | 69 | 100 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 18 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 31 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 19 | MISSING EFFECT | exile ~ … | 17 | 9 | 55 | Woodland Guidance, Teferi's Protection, Vorinclex // The Grand Evolution |
| 20 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 21 | MISSING EFFECT | search your library for … | 15 | 178 | 258 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 22 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 23 | MISSING EFFECT | ~ deals n … | 14 | 202 | 305 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 24 | MISSING EFFECT | return ~ … | 14 | 94 | 130 | Summon the School, Dragon Fangs, Haunted Dead |
| 25 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 14 | 29 | 47 | Bedlam Reveler, Gargantuan Leech, Cryptic Serpent |
| 26 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 14 | 28 | 47 | Anya, Merciless Angel, Mutagen Connoisseur, Alrund, God of the Cosmos // Hakka, Whispering Raven |
| 27 | MISSING MECHANIC | sneak | 14 | 13 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 28 | MISSING MECHANIC | firebending | 14 | 8 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 29 | MISSING MECHANIC | partner | 14 | 7 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 30 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 31 | MISSING EFFECT | add {m} … | 13 | 43 | 70 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 32 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 33 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 34 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 12 | 1 | 12 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 35 | MISSING SELECTOR | target equipment | 11 | 19 | 25 | Stolen Uniform, Shagrat, Loot Bearer, Swordsman, Sharp Scoundrel |
| 36 | MISSING EFFECT | earthbend n … | 11 | 16 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 37 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 38 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 39 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 40 | MISSING EFFECT | reveal the top card … | 10 | 36 | 48 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 41 | MISSING SELECTOR | target creature card with mana value | 10 | 26 | 38 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 42 | MISSING EFFECT | another target … | 10 | 13 | 21 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 43 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 10 | 12 | 25 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 44 | MISSING EFFECT | return it to the … | 10 | 11 | 23 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 45 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 10 | 8 | 14 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 46 | MISSING EFFECT | choose target … | 9 | 71 | 83 | Arcbond, Deglamer, Wreck Hunter |
| 47 | MISSING EFFECT | create a n/n red … | 9 | 26 | 42 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 48 | MISSING SELECTOR | target instant or sorcery card | 9 | 16 | 28 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 49 | MISSING EFFECT | double the number of … | 9 | 12 | 24 | Fractal Harness, Primordial Hydra, The Millennium Calendar |
| 50 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 11 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 51 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 52 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 53 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 54 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 55 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 56 | MISSING EFFECT | target creature you control … | 8 | 112 | 162 | Hard-Hitting Question, Crowd of True Believers, Rabid Gnaw |
| 57 | MISSING SELECTOR | target creatures | 8 | 99 | 197 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 58 | MISSING EFFECT | you gain n … | 8 | 54 | 76 | Belladonna Took, Essence Pulse, Life Goes On |
| 59 | MISSING COST | {M}, Discard ~ | 8 | 39 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 60 | MISSING EFFECT | create a n/n white … | 8 | 29 | 45 | Empyrial Storm, Drag the Canal, Squad Commander |
| 61 | MISSING EFFECT | exile the top n … | 8 | 16 | 40 | Memorial Vault, Crossover Collaboration, Ral, Monsoon Mage // Ral, Leyline Prodigy |
| 62 | MISSING EFFECT | discard your hand … | 8 | 16 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 63 | MISSING EFFECT | discard n … | 8 | 14 | 26 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 64 | UNSUPPORTED ORACLE PATTERN | You may play an additional land … | 8 | 7 | 17 | Exploration, Icetill Explorer, Case of the Locked Hothouse |
| 65 | UNSUPPORTED ORACLE PATTERN | Mayhem {M} | 8 | 7 | 11 | Swarm, Being of Bees, Chameleon, Master of Disguise, Spider-Islanders |
| 66 | MISSING CONTINUOUS EFFECT | During your turn, … | 8 | 6 | 17 | Long-Lost Lances, Miriam, Herd Whisperer, Yuna, Hope of Spira |
| 67 | MISSING EFFECT | you get an experience … | 8 | 2 | 8 | Meren of Clan Nel Toth, Katara, Waterbending Master, Ezuri, Claw of Progress |
| 68 | MISSING EFFECT | if you control n … | 7 | 40 | 63 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 69 | MISSING EFFECT | if you cast it … | 7 | 25 | 38 | Weftwalking, Marina Vendrell's Grimoire, Bringer of the Last Gift |
| 70 | MANA ABILITY WORDING | {M}: Add {M}. Spend this mana … | 7 | 24 | 27 | Guidelight Optimizer, Karfell Harbinger, Soldevi Machinist |
| 71 | MISSING EFFECT | for each opponent … | 7 | 21 | 37 | Bronzebeak Foragers, Nihiloor, Frenzied Gorespawn |
| 72 | MISSING TRIGGER EVENT | Magecraft — Whenever you cast or copy an instant or sorcery spell | 7 | 21 | 29 | Zaffai, Thunder Conductor, Karok Wrangler, Extus, Oriq Overlord // Awaken the Blood Avatar |
| 73 | MISSING EFFECT | you draw n … | 7 | 12 | 26 | Live Fast, Greed's Gambit, Helga, Skittish Seer |
| 74 | MISSING TRIGGER EVENT | Whenever you scry | 7 | 9 | 14 | Lost Isle Calling, Nimrodel Watcher, Elrond, Master of Healing |
| 75 | MISSING SELECTOR | target creature card in your graveyard | 7 | 8 | 11 | Meren of Clan Nel Toth, Moira, Urborg Haunt, Othelm, Sigardian Outcast |
| 76 | MISSING EFFECT | choose up to n … | 7 | 7 | 30 | Atomic Microsizer, Biblioplex Tomekeeper, The Ruinous Wrecking Crew |
| 77 | MISSING CONTINUOUS EFFECT | ~ has all activated abilities of … | 7 | 6 | 14 | Robaran Mercenaries, Marvin, Murderous Mimic, Thranduil, the Elvenking |
| 78 | MISSING REPLACEMENT PATTERN | If N or more tokens would be … | 7 | 5 | 10 | Adrix and Nev, Twincasters, Peregrin Took, Donatello, the Brains |
| 79 | MISSING MECHANIC | start your engines! | 7 | 0 | 40 | Momentum Breaker, Point the Way, Lightwheel Enhancements |
| 80 | UNSUPPORTED ORACLE PATTERN | • Draw N card(s) | 7 | 0 | 17 | Coliseum Behemoth, Demonic Pact, Elder Gargaroth |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 520 | 50 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 2 | MISSING EFFECT | draw n … | 502 | 200 | 54 | Errand-Rider of Gondor, Krovikan Sorcerer, Grip of Amnesia |
| 3 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 38 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 4 | MISSING SELECTOR | target | 308 | 193 | 35 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 5 | MISSING EFFECT | ~ deals n … | 305 | 202 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 258 | 178 | 15 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING EFFECT | until end of turn … | 227 | 167 | 23 | Divergent Growth, Doorman, Strength of Will |
| 8 | MISSING EFFECT | put a ±n/±n counter(s) … | 199 | 134 | 57 | Yorvo, Lord of Garenbrig, Ent-Draught Basin, Hired Claw |
| 9 | MISSING SELECTOR | target creatures | 197 | 99 | 8 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 10 | MISSING EFFECT | create n … | 183 | 108 | 27 | Summon the School, Cogwork Assembler, Endless Evil |
| 11 | MISSING EFFECT | destroy target … | 178 | 104 | 3 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 12 | MISSING EFFECT | pay {m} … | 167 | 114 | 54 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 13 | MISSING EFFECT | look at the top … | 167 | 125 | 31 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 14 | MISSING EFFECT | target creature you control … | 162 | 112 | 8 | Hard-Hitting Question, Crowd of True Believers, Rabid Gnaw |
| 15 | MISSING SELECTOR | target creature card | 155 | 102 | 24 | Puppeteer Clique, Metamorphosis Fanatic, Sword of Light and Shadow |
| 16 | MISSING EFFECT | target creature gets ±n/±n … | 146 | 87 | 3 | Spontaneous Flight, Rig for War, Defiant Stand |
| 17 | MISSING EFFECT | if ~ … | 130 | 78 | 19 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 18 | MISSING EFFECT | return ~ … | 130 | 94 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 19 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 128 | 42 | 4 | Game Trail, Gideon's Intervention, Secluded Glen |
| 20 | MISSING EFFECT | put n … | 125 | 88 | 21 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 21 | MANA ABILITY WORDING | {M}, … | 108 | 86 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 22 | MISSING EFFECT | mill n … | 100 | 69 | 18 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 23 | MISSING MECHANIC | ward | 97 | 17 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 24 | MISSING EFFECT | if n … | 92 | 64 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 25 | MISSING EFFECT | exile target … | 89 | 58 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 26 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 27 | MISSING EFFECT | choose target … | 83 | 71 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 28 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 31 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 29 | MISSING EFFECT | you gain n … | 76 | 54 | 8 | Belladonna Took, Essence Pulse, Life Goes On |
| 30 | MISSING EFFECT | if there are n … | 76 | 35 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 31 | MISSING EFFECT | tap target … | 75 | 44 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 32 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 33 | MISSING EFFECT | transform ~ … | 70 | 29 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 34 | MISSING EFFECT | add {m} … | 70 | 43 | 13 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 35 | MISSING EFFECT | it deals n … | 68 | 54 | 2 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 36 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 42 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |
| 37 | MISSING EFFECT | if you control n … | 63 | 40 | 7 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 38 | MISSING EFFECT | you get an emblem … | 60 | 16 | 4 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 39 | MISSING EFFECT | exile the top card … | 59 | 31 | 25 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 40 | MISSING COST | {M}, Discard ~ | 57 | 39 | 8 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 41 | MISSING EFFECT | exile ~ … | 55 | 9 | 17 | Woodland Guidance, Teferi's Protection, Vorinclex // The Grand Evolution |
| 42 | MISSING SELECTOR | target player controls | 54 | 32 | 5 | Requisition Raid, Liliana of the Veil, Dawnglare Invoker |
| 43 | MISSING SELECTOR | target player or planeswalker | 53 | 37 | 4 | Goblin Barrage, Nicol Bolas, Planeswalker, Cosi's Ravager |
| 44 | MISSING EFFECT | create a n/n green … | 50 | 24 | 6 | Rhonas's Last Stand, Fractal Harness, Baloth Cage Trap |
| 45 | MISSING MECHANIC | equip | 49 | 21 | 2 | Bloodthorn Flail, Strong Back, Team Pennant |
| 46 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 49 | 45 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 47 | MISSING EFFECT | reveal the top card … | 48 | 36 | 10 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 48 | MISSING CONTINUOUS EFFECT | You may have ~ enter as … | 48 | 37 | 5 | Mercurial Pretender, Pirated Copy, The Fourteenth Doctor |
| 49 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 47 | 29 | 14 | Bedlam Reveler, Gargantuan Leech, Cryptic Serpent |
| 50 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 47 | 28 | 14 | Anya, Merciless Angel, Mutagen Connoisseur, Alrund, God of the Cosmos // Hakka, Whispering Raven |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 364 | 270 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | keyword:bestow | keyword | 0 | 42 | 27 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 3 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 4 | keyword:enchant | keyword | 0 | 67 | 21 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 5 | keyword:foretell | keyword | 0 | 51 | 21 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 6 | keyword:equip | keyword | 0 | 49 | 21 | Bloodthorn Flail, Strong Back, Team Pennant |
| 7 | template:Enchanted creature has “…” | continuous | 0 | 25 | 21 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 8 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 19 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 9 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 10 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 11 | keyword:backup | keyword | 0 | 25 | 18 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 12 | keyword:ward | keyword | 0 | 97 | 17 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 13 | keyword:warp | keyword | 0 | 31 | 17 | Starbreach Whale, Knight Luminary, Loading Zone |
| 14 | template:Equipped creature has “…” | continuous | 0 | 24 | 17 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 15 | keyword:myriad | keyword | 0 | 23 | 17 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 16 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 16 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 17 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 18 | keyword:encore | keyword | 0 | 26 | 16 | Impulsivity, Sliver Gravemother, Belonging |
| 19 | template:Modular N | static | 0 | 23 | 16 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 20 | keyword:disturb | keyword | 0 | 25 | 15 | Lunarch Veteran // Luminous Phantom, Devoted Grafkeeper // Departed Soulkeeper, Overwhelmed Archivist // Archive Haunt |
| 21 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 15 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 22 | keyword:entwine | keyword | 0 | 32 | 14 | Road of Return, Rain of Rust, Blinding Beam |
| 23 | keyword:living weapon | keyword | 0 | 19 | 14 | Nettlecyst, Lashwrithe, Skinwing |
| 24 | keyword:overload | keyword | 0 | 27 | 13 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 25 | keyword:sneak | keyword | 0 | 27 | 13 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 26 | keyword:ninjutsu | keyword | 0 | 35 | 12 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 27 | keyword:cumulative upkeep | keyword | 0 | 23 | 12 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 28 | keyword:offspring | keyword | 0 | 20 | 12 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 29 | keyword:mentor | keyword | 0 | 19 | 12 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 30 | keyword:unleash | keyword | 0 | 15 | 12 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 31 | template:Scavenge {M} | static | 0 | 14 | 12 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 32 | keyword:disguise | keyword | 0 | 43 | 11 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 33 | keyword:plot | keyword | 0 | 33 | 11 | Unscrupulous Contractor, Pyretic Charge, Freestrider Commando |
| 34 | template:You have no maximum hand size. | continuous | 0 | 23 | 11 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 35 | template:{M}: Adapt N. | activated | 0 | 22 | 11 | Zegana, Utopian Speaker, Temperamental Oozewagg, Evolution Witness |
| 36 | keyword:retrace | keyword | 0 | 17 | 11 | Flame Jab, Monstrify, Waves of Aggression |
| 37 | keyword:umbra armor | keyword | 0 | 15 | 11 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 38 | keyword:rampage | keyword | 0 | 12 | 11 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 39 | template:Enchanted land has “…” | continuous | 0 | 12 | 11 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 40 | template:All Slivers have “…” | continuous | 0 | 11 | 11 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 41 | keyword:evolve | keyword | 0 | 22 | 10 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 42 | keyword:vanishing | keyword | 0 | 20 | 10 | Soultether Golem, Deadly Grub, Reality Acid |
| 43 | keyword:prototype | keyword | 0 | 19 | 10 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 44 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 45 | keyword:embalm | keyword | 0 | 15 | 10 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 46 | keyword:battle cry | keyword | 0 | 13 | 10 | Goblin Wardriver, Hero of Bladehold, Iraxxa, Empress of Mars |
| 47 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 48 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 10 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 49 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 50 | keyword:kicker | keyword | 0 | 37 | 9 | Goblin Barrage, Archangel of Wrath, Anavolver |
| 51 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 52 | keyword:replicate | keyword | 0 | 19 | 9 | Consign to Memory, Psionic Ritual, Lose Focus |
| 53 | template:Devour N | static | 0 | 19 | 9 | Ravenous Gigantotherium, Hellkite Hatchling, Preyseizer Dragon |
| 54 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 55 | keyword:blitz | keyword | 0 | 16 | 9 | Mezzio Mugger, Workshop Warchief, Riveteers Decoy |
| 56 | keyword:enlist | keyword | 0 | 12 | 9 | Keldon Flamesage, Benalish Faithbonder, Aradesh, the Founder |
| 57 | keyword:firebending | keyword | 0 | 22 | 8 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 58 | template:Sunburst | static | 0 | 15 | 8 | Spinal Parasite, Sawtooth Thresher, Solarion |
| 59 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 14 | 8 | Giant's Amulet, Dire Flail // Dire Blunderbuss, Citizen's Crowbar |
| 60 | keyword:for mirrodin! | keyword | 0 | 13 | 8 | Mirran Bardiche, Sylvok Battle-Chair, Goldwarden's Helm |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 7401 | 10520 | 0 | 0 |
| Artifact | 1231 | 2362 | 0 | 0 |
| Enchantment | 1030 | 2617 | 0 | 0 |
| Sorcery | 1063 | 2505 | 0 | 0 |
| Instant | 1365 | 2389 | 0 | 0 |
| Land | 658 | 554 | 0 | 0 |
| Planeswalker | 24 | 287 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14139, spell_effect 9115, activated 7339, continuous 3999, static 2899, mana_ability 2035, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 206, alternative_cost 180
