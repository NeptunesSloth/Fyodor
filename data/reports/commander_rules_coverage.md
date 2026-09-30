# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-30 13:40

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32068**

| Level | Cards | Share |
|---|---|---|
| FULL | 12431 | 38.8% |
| PARTIAL | 19637 | 61.2% |
| REVIEW | 0 | 0.0% |
| MANUAL | 0 | 0.0% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 651, PARTIAL 2850, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113154
- Automated: 85659 (75.7%) · unrecognized clauses: 27495
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.7% · unclassified clauses: 2622
- Distinct missing-capability clusters: 8025

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 10232 | 12007 |
| MISSING SELECTOR | 2927 | 3101 |
| MISSING TRIGGER EVENT | 2398 | 2509 |
| UNSUPPORTED ORACLE PATTERN | 1972 | 2622 |
| MISSING CONTINUOUS EFFECT | 1857 | 1966 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1021 | 1052 |
| MISSING COST / PERMISSION RULE | 800 | 810 |
| MISSING RESTRICTION | 653 | 687 |
| MISSING COST | 484 | 497 |
| MANA ABILITY WORDING | 364 | 366 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 65 | 50 | 512 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 2 | MISSING EFFECT | put a ±n/±n counter(s) … | 56 | 129 | 191 | Yorvo, Lord of Garenbrig, Ent-Draught Basin, Hired Claw |
| 3 | MISSING EFFECT | pay {m} … | 54 | 113 | 166 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 4 | MISSING EFFECT | draw n … | 51 | 197 | 491 | Errand-Rider of Gondor, Krovikan Sorcerer, Grip of Amnesia |
| 5 | MISSING MECHANIC | ward | 47 | 19 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING SELECTOR | target | 35 | 191 | 305 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 7 | MISSING EFFECT | look at the top … | 31 | 126 | 166 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 8 | MISSING EFFECT | create n … | 27 | 107 | 181 | Summon the School, Cogwork Assembler, Endless Evil |
| 9 | MISSING EFFECT | exile the top card … | 25 | 31 | 59 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 10 | MISSING SELECTOR | target creature card | 24 | 103 | 154 | Puppeteer Clique, Metamorphosis Fanatic, Sword of Light and Shadow |
| 11 | MISSING EFFECT | if n … | 24 | 65 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 12 | MISSING EFFECT | until end of turn … | 23 | 167 | 227 | Divergent Growth, Doorman, Strength of Will |
| 13 | MISSING EFFECT | transform ~ … | 23 | 29 | 70 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 14 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 9 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 15 | MISSING EFFECT | put n … | 19 | 83 | 118 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 16 | MISSING EFFECT | if ~ … | 19 | 78 | 130 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 17 | MISSING EFFECT | mill n … | 18 | 70 | 100 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 18 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 31 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 19 | MISSING EFFECT | exile ~ … | 17 | 9 | 55 | Woodland Guidance, Teferi's Protection, Vorinclex // The Grand Evolution |
| 20 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 21 | MISSING EFFECT | search your library for … | 15 | 180 | 258 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 22 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 23 | MISSING EFFECT | ~ deals n … | 14 | 201 | 303 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 24 | MISSING EFFECT | return ~ … | 14 | 94 | 130 | Summon the School, Dragon Fangs, Haunted Dead |
| 25 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 14 | 29 | 47 | Bedlam Reveler, Gargantuan Leech, Cryptic Serpent |
| 26 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 14 | 28 | 47 | Anya, Merciless Angel, Mutagen Connoisseur, Alrund, God of the Cosmos // Hakka, Whispering Raven |
| 27 | MISSING MECHANIC | sneak | 14 | 13 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 28 | MISSING MECHANIC | partner | 14 | 8 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 29 | MISSING MECHANIC | firebending | 14 | 8 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 30 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 31 | MISSING EFFECT | add {m} … | 13 | 44 | 70 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 32 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 33 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 34 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 12 | 1 | 12 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 35 | MISSING SELECTOR | target equipment | 11 | 19 | 25 | Stolen Uniform, Shagrat, Loot Bearer, Swordsman, Sharp Scoundrel |
| 36 | MISSING EFFECT | earthbend n … | 11 | 16 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 37 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 38 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 39 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 40 | MISSING EFFECT | reveal the top card … | 10 | 36 | 48 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 41 | MISSING SELECTOR | target creature card with mana value | 10 | 26 | 37 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 42 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 10 | 12 | 25 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 43 | MISSING EFFECT | return it to the … | 10 | 11 | 23 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 44 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 10 | 8 | 14 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 45 | MISSING EFFECT | choose target … | 9 | 65 | 77 | Arcbond, Wreck Hunter, Yenna, Redtooth Regent |
| 46 | MISSING EFFECT | create a n/n red … | 9 | 26 | 42 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 47 | MISSING SELECTOR | target instant or sorcery card | 9 | 16 | 28 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 48 | MISSING EFFECT | double the number of … | 9 | 12 | 24 | Fractal Harness, Primordial Hydra, The Millennium Calendar |
| 49 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 11 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 50 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 51 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 52 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 53 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 54 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 55 | MISSING SELECTOR | target creatures | 8 | 96 | 194 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 56 | MISSING EFFECT | you gain n … | 8 | 54 | 75 | Belladonna Took, Essence Pulse, Life Goes On |
| 57 | MISSING COST | {M}, Discard ~ | 8 | 40 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 58 | MISSING EFFECT | create a n/n white … | 8 | 29 | 45 | Empyrial Storm, Drag the Canal, Squad Commander |
| 59 | MISSING EFFECT | exile the top n … | 8 | 17 | 40 | Memorial Vault, Crossover Collaboration, Ral, Monsoon Mage // Ral, Leyline Prodigy |
| 60 | MISSING EFFECT | discard your hand … | 8 | 16 | 31 | Pyretic Charge, Bedlam Reveler, Balin, Loremaster |
| 61 | MISSING EFFECT | discard n … | 8 | 13 | 25 | Witch's Mark, Seasoned Pyromancer, Party Thrasher |
| 62 | UNSUPPORTED ORACLE PATTERN | You may play an additional land … | 8 | 7 | 17 | Exploration, Icetill Explorer, Case of the Locked Hothouse |
| 63 | UNSUPPORTED ORACLE PATTERN | Mayhem {M} | 8 | 7 | 11 | Swarm, Being of Bees, Chameleon, Master of Disguise, Spider-Islanders |
| 64 | MISSING CONTINUOUS EFFECT | During your turn, … | 8 | 6 | 17 | Long-Lost Lances, Miriam, Herd Whisperer, Yuna, Hope of Spira |
| 65 | MISSING EFFECT | you get an experience … | 8 | 2 | 8 | Meren of Clan Nel Toth, Katara, Waterbending Master, Ezuri, Claw of Progress |
| 66 | MISSING EFFECT | if you control n … | 7 | 40 | 63 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 67 | MISSING EFFECT | if you cast it … | 7 | 25 | 38 | Weftwalking, Marina Vendrell's Grimoire, Bringer of the Last Gift |
| 68 | MANA ABILITY WORDING | {M}: Add {M}. Spend this mana … | 7 | 24 | 27 | Guidelight Optimizer, Karfell Harbinger, Soldevi Machinist |
| 69 | MISSING EFFECT | for each opponent … | 7 | 21 | 37 | Bronzebeak Foragers, Nihiloor, Frenzied Gorespawn |
| 70 | MISSING TRIGGER EVENT | Magecraft — Whenever you cast or copy an instant or sorcery spell | 7 | 21 | 29 | Zaffai, Thunder Conductor, Karok Wrangler, Extus, Oriq Overlord // Awaken the Blood Avatar |
| 71 | MISSING EFFECT | you draw n … | 7 | 12 | 25 | Live Fast, Greed's Gambit, Helga, Skittish Seer |
| 72 | MISSING TRIGGER EVENT | Whenever you scry | 7 | 9 | 14 | Lost Isle Calling, Nimrodel Watcher, Elrond, Master of Healing |
| 73 | MISSING SELECTOR | target creature card in your graveyard | 7 | 8 | 11 | Meren of Clan Nel Toth, Moira, Urborg Haunt, Othelm, Sigardian Outcast |
| 74 | MISSING EFFECT | choose up to n … | 7 | 7 | 30 | Atomic Microsizer, Biblioplex Tomekeeper, The Ruinous Wrecking Crew |
| 75 | MISSING CONTINUOUS EFFECT | ~ has all activated abilities of … | 7 | 6 | 14 | Robaran Mercenaries, Marvin, Murderous Mimic, Thranduil, the Elvenking |
| 76 | MISSING REPLACEMENT PATTERN | If N or more tokens would be … | 7 | 5 | 10 | Adrix and Nev, Twincasters, Peregrin Took, Donatello, the Brains |
| 77 | MISSING MECHANIC | start your engines! | 7 | 0 | 40 | Momentum Breaker, Point the Way, Lightwheel Enhancements |
| 78 | UNSUPPORTED ORACLE PATTERN | • Draw N card(s) | 7 | 0 | 17 | Coliseum Behemoth, Demonic Pact, Elder Gargaroth |
| 79 | MANA ABILITY WORDING | {M}, … | 6 | 86 | 108 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 80 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 6 | 39 | 312 | Thunderherd Migration, Mind Extraction, Harvest Pyre |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | choose n … | 512 | 50 | 65 | Road of Return, Saheeli's Artistry, Dawnbringer Cleric |
| 2 | MISSING EFFECT | draw n … | 491 | 197 | 51 | Errand-Rider of Gondor, Krovikan Sorcerer, Grip of Amnesia |
| 3 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 39 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 4 | MISSING SELECTOR | target | 305 | 191 | 35 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 5 | MISSING EFFECT | ~ deals n … | 303 | 201 | 14 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 6 | MISSING EFFECT | search your library for … | 258 | 180 | 15 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 7 | MISSING EFFECT | until end of turn … | 227 | 167 | 23 | Divergent Growth, Doorman, Strength of Will |
| 8 | MISSING SELECTOR | target creatures | 194 | 96 | 8 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 9 | MISSING EFFECT | put a ±n/±n counter(s) … | 191 | 129 | 56 | Yorvo, Lord of Garenbrig, Ent-Draught Basin, Hired Claw |
| 10 | MISSING EFFECT | create n … | 181 | 107 | 27 | Summon the School, Cogwork Assembler, Endless Evil |
| 11 | MISSING EFFECT | destroy target … | 177 | 103 | 3 | Kalitas, Bloodchief of Ghet, Raze, Unliving Psychopath |
| 12 | MISSING EFFECT | pay {m} … | 166 | 113 | 54 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 13 | MISSING EFFECT | look at the top … | 166 | 126 | 31 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 14 | MISSING SELECTOR | target creature card | 154 | 103 | 24 | Puppeteer Clique, Metamorphosis Fanatic, Sword of Light and Shadow |
| 15 | MISSING EFFECT | if ~ … | 130 | 78 | 19 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 16 | MISSING EFFECT | return ~ … | 130 | 94 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 17 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 128 | 43 | 4 | Game Trail, Gideon's Intervention, Secluded Glen |
| 18 | MISSING EFFECT | target creature gets ±n/±n … | 122 | 67 | 2 | Spontaneous Flight, Defiant Stand, Sadistic Slash |
| 19 | MISSING EFFECT | put n … | 118 | 83 | 19 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 20 | MANA ABILITY WORDING | {M}, … | 108 | 86 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 21 | MISSING EFFECT | target creature you control … | 107 | 70 | 5 | Crowd of True Believers, Rabid Gnaw, Corporeal Projection |
| 22 | MISSING EFFECT | mill n … | 100 | 70 | 18 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 23 | MISSING MECHANIC | ward | 97 | 19 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 24 | MISSING EFFECT | if n … | 92 | 65 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 25 | MISSING EFFECT | exile target … | 89 | 58 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 26 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 27 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 31 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 28 | MISSING EFFECT | choose target … | 77 | 65 | 9 | Arcbond, Wreck Hunter, Yenna, Redtooth Regent |
| 29 | MISSING EFFECT | if there are n … | 76 | 36 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 30 | MISSING EFFECT | you gain n … | 75 | 54 | 8 | Belladonna Took, Essence Pulse, Life Goes On |
| 31 | MISSING EFFECT | tap target … | 75 | 44 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 32 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 33 | MISSING EFFECT | transform ~ … | 70 | 29 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 34 | MISSING EFFECT | add {m} … | 70 | 44 | 13 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 35 | MISSING EFFECT | it deals n … | 67 | 55 | 1 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 36 | MANA ABILITY WORDING | {M}: Add N mana of any … | 65 | 43 | 2 | Flywheel Racer, Pit of Offerings, Helga, Skittish Seer |
| 37 | MISSING EFFECT | if you control n … | 63 | 40 | 7 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 38 | MISSING EFFECT | you get an emblem … | 60 | 17 | 4 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 39 | MISSING EFFECT | exile the top card … | 59 | 31 | 25 | Mezzio Mugger, Etali, Primal Storm, Chandra, Torch of Defiance |
| 40 | MISSING COST | {M}, Discard ~ | 57 | 40 | 8 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 41 | MISSING EFFECT | exile ~ … | 55 | 9 | 17 | Woodland Guidance, Teferi's Protection, Vorinclex // The Grand Evolution |
| 42 | MISSING SELECTOR | target player controls | 54 | 32 | 5 | Requisition Raid, Liliana of the Veil, Dawnglare Invoker |
| 43 | MISSING SELECTOR | target player or planeswalker | 53 | 37 | 4 | Goblin Barrage, Nicol Bolas, Planeswalker, Cosi's Ravager |
| 44 | MISSING EFFECT | create a n/n green … | 50 | 25 | 6 | Rhonas's Last Stand, Fractal Harness, Baloth Cage Trap |
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
| 1 | mana:ability | engine | 0 | 364 | 271 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | keyword:bestow | keyword | 0 | 42 | 27 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 3 | template:~ enters prepared. | static | 0 | 40 | 24 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 4 | keyword:enchant | keyword | 0 | 67 | 21 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 5 | keyword:foretell | keyword | 0 | 51 | 21 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 6 | keyword:equip | keyword | 0 | 49 | 21 | Bloodthorn Flail, Strong Back, Team Pennant |
| 7 | template:Enchanted creature has “…” | continuous | 0 | 25 | 21 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 8 | keyword:ward | keyword | 0 | 97 | 19 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 9 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 19 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 10 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 11 | template:Commander creatures you own have “…” | continuous | 0 | 19 | 19 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 12 | keyword:backup | keyword | 0 | 25 | 18 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 13 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 17 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 14 | keyword:warp | keyword | 0 | 31 | 17 | Starbreach Whale, Knight Luminary, Loading Zone |
| 15 | keyword:encore | keyword | 0 | 26 | 17 | Impulsivity, Sliver Gravemother, Belonging |
| 16 | keyword:myriad | keyword | 0 | 23 | 17 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 17 | template:Equipped creature has “…” | continuous | 0 | 23 | 17 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 18 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 19 | template:Modular N | static | 0 | 23 | 16 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 20 | keyword:disturb | keyword | 0 | 25 | 15 | Lunarch Veteran // Luminous Phantom, Devoted Grafkeeper // Departed Soulkeeper, Overwhelmed Archivist // Archive Haunt |
| 21 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 15 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 22 | keyword:entwine | keyword | 0 | 32 | 14 | Road of Return, Rain of Rust, Blinding Beam |
| 23 | keyword:overload | keyword | 0 | 27 | 14 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 24 | keyword:cumulative upkeep | keyword | 0 | 23 | 14 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 25 | keyword:living weapon | keyword | 0 | 19 | 14 | Nettlecyst, Lashwrithe, Skinwing |
| 26 | keyword:ninjutsu | keyword | 0 | 35 | 13 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 27 | keyword:sneak | keyword | 0 | 27 | 13 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 28 | keyword:plot | keyword | 0 | 33 | 12 | Unscrupulous Contractor, Pyretic Charge, Freestrider Commando |
| 29 | keyword:offspring | keyword | 0 | 20 | 12 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 30 | keyword:mentor | keyword | 0 | 19 | 12 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 31 | keyword:unleash | keyword | 0 | 15 | 12 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 32 | template:Scavenge {M} | static | 0 | 14 | 12 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 33 | keyword:disguise | keyword | 0 | 43 | 11 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 34 | template:You have no maximum hand size. | continuous | 0 | 23 | 11 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 35 | template:{M}: Adapt N. | activated | 0 | 22 | 11 | Zegana, Utopian Speaker, Temperamental Oozewagg, Evolution Witness |
| 36 | keyword:prototype | keyword | 0 | 19 | 11 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 37 | keyword:replicate | keyword | 0 | 19 | 11 | Consign to Memory, Psionic Ritual, Lose Focus |
| 38 | keyword:retrace | keyword | 0 | 17 | 11 | Flame Jab, Monstrify, Waves of Aggression |
| 39 | keyword:embalm | keyword | 0 | 15 | 11 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 40 | keyword:umbra armor | keyword | 0 | 15 | 11 | Felidar Umbra, Drake Umbra, Hyena Umbra |
| 41 | keyword:rampage | keyword | 0 | 12 | 11 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 42 | template:All Slivers have “…” | continuous | 0 | 11 | 11 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 43 | keyword:evolve | keyword | 0 | 22 | 10 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 44 | keyword:vanishing | keyword | 0 | 20 | 10 | Soultether Golem, Deadly Grub, Reality Acid |
| 45 | template:Devour N | static | 0 | 19 | 10 | Ravenous Gigantotherium, Hellkite Hatchling, Preyseizer Dragon |
| 46 | keyword:fading | keyword | 0 | 17 | 10 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 47 | keyword:battle cry | keyword | 0 | 13 | 10 | Goblin Wardriver, Hero of Bladehold, Iraxxa, Empress of Mars |
| 48 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 49 | template:Enchanted land has “…” | continuous | 0 | 11 | 10 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 50 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 10 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 51 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 52 | keyword:kicker | keyword | 0 | 37 | 9 | Goblin Barrage, Archangel of Wrath, Anavolver |
| 53 | template:You control enchanted creature. | static | 0 | 28 | 9 | Spirit Away, Illusory Gains, Biting Tether |
| 54 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 55 | keyword:blitz | keyword | 0 | 16 | 9 | Mezzio Mugger, Workshop Warchief, Riveteers Decoy |
| 56 | keyword:enlist | keyword | 0 | 12 | 9 | Keldon Flamesage, Benalish Faithbonder, Aradesh, the Founder |
| 57 | template:You may have ~ assign its combat damage as though it weren't blocked. | continuous | 0 | 9 | 9 | Deathcoil Wurm, Pride of Lions, Tornado Elemental |
| 58 | keyword:partner | keyword | 0 | 24 | 8 | Lore Weaver, Blaring Captain, Rory Williams |
| 59 | keyword:firebending | keyword | 0 | 22 | 8 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 60 | template:Sunburst | static | 0 | 15 | 8 | Spinal Parasite, Sawtooth Thresher, Solarion |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 7557 | 10364 | 0 | 0 |
| Artifact | 1251 | 2342 | 0 | 0 |
| Enchantment | 1046 | 2601 | 0 | 0 |
| Sorcery | 1114 | 2454 | 0 | 0 |
| Instant | 1465 | 2289 | 0 | 0 |
| Land | 668 | 544 | 0 | 0 |
| Planeswalker | 29 | 282 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14139, spell_effect 9115, activated 7339, continuous 3999, static 2899, mana_ability 2035, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 206, alternative_cost 180
