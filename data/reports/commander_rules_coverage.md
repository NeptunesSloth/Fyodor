# Commander rules coverage

Card data: Scryfall `2026-09-28T21:01:54.353+00:00` · Comprehensive Rules 2026-09-25 · rules engine v2 · generated 2026-09-29 22:30

Only cards that are **legal in Commander today** count. Banned cards (83) are COMMANDER_BANNED and excluded.

## Commander coverage

Commander-legal cards: **32116**

| Level | Cards | Share |
|---|---|---|
| FULL | 9292 | 28.9% |
| PARTIAL | 22776 | 70.9% |
| REVIEW | 0 | 0.0% |
| MANUAL | 48 | 0.1% |

Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **3501** — FULL 391, PARTIAL 3110, REVIEW 0, MANUAL 0

## Pod coverage

No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by Commander-legal cards unlocked.

## Coverage quality

- Ability features (lines, keywords, play/cast/combat) across Commander-legal cards: 113346
- Automated: 80717 (71.2%) · unrecognized clauses: 32629
- Oracle text classified (automated, or sorted into a concrete missing capability): 97.4% · unclassified clauses: 2936
- Distinct missing-capability clusters: 8728

## Missing capabilities by category

| Category | Cards affected | Clauses |
|---|---|---|
| MISSING EFFECT | 12065 | 14212 |
| MISSING SELECTOR | 3635 | 3848 |
| MISSING CONTINUOUS EFFECT | 2815 | 2992 |
| MISSING TRIGGER EVENT | 2410 | 2524 |
| UNSUPPORTED ORACLE PATTERN | 2167 | 2936 |
| MISSING MECHANIC | 1816 | 1878 |
| MISSING REPLACEMENT PATTERN | 1362 | 1401 |
| MISSING RESTRICTION | 942 | 988 |
| MISSING COST / PERMISSION RULE | 935 | 955 |
| MISSING COST | 512 | 526 |
| MANA ABILITY WORDING | 367 | 369 |

## Highest-payoff clusters

Ranked by pod cards, pod commanders, possible commanders affected, cards it alone would unlock, then all Commander cards needing it.

| # | Category | Cluster | Commanders | Only missing piece for | Commander cards | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | pay {m} … | 70 | 207 | 285 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 2 | MISSING EFFECT | put a ±n/±n counter(s) … | 67 | 170 | 247 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 3 | MISSING EFFECT | draw n … | 66 | 220 | 596 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 4 | MISSING EFFECT | choose n … | 65 | 50 | 570 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 5 | MISSING MECHANIC | ward | 47 | 13 | 97 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 6 | MISSING EFFECT | look at the top … | 39 | 157 | 217 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 7 | MISSING EFFECT | create n … | 38 | 149 | 259 | Summon the School, Cogwork Assembler, Endless Evil |
| 8 | MISSING SELECTOR | target | 36 | 214 | 346 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 9 | MISSING EFFECT | exile the top card … | 36 | 54 | 115 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 10 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 32 | 57 | 115 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 11 | MISSING EFFECT | put n … | 28 | 97 | 152 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 12 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 28 | 64 | 127 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 13 | MISSING SELECTOR | target creature card | 26 | 123 | 183 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 14 | MISSING EFFECT | if n … | 24 | 59 | 92 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 15 | MISSING EFFECT | until end of turn … | 23 | 151 | 227 | Divergent Growth, Doorman, Strength of Will |
| 16 | MISSING EFFECT | transform ~ … | 23 | 23 | 69 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 17 | UNSUPPORTED ORACLE PATTERN | As long as your devotion to … | 22 | 5 | 22 | Phenax, God of Deception, Erebos, God of the Dead, Thassa, Deep-Dwelling |
| 18 | UNSUPPORTED ORACLE PATTERN | You may look at the top … | 22 | 2 | 45 | One with the Multiverse, The Lunar Whale, Cemetery Illuminator |
| 19 | MISSING CONTINUOUS EFFECT | During your turn, … | 21 | 37 | 74 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 20 | MISSING EFFECT | exile ~ … | 20 | 15 | 63 | Stenn, Paranoid Partisan, Woodland Guidance, Teferi's Protection |
| 21 | MISSING EFFECT | if ~ … | 19 | 72 | 130 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 22 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 19 | 38 | 71 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 23 | MISSING EFFECT | mill n … | 18 | 65 | 103 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 24 | MISSING EFFECT | discard n … | 18 | 46 | 81 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 25 | MISSING TRIGGER EVENT | When you cast ~ | 18 | 29 | 80 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 26 | MISSING EFFECT | create a n/n red … | 17 | 31 | 61 | Prosperity Tycoon, Ertha Jo, Frontier Mentor, Nesting Dragon |
| 27 | MISSING EFFECT | search your library for … | 16 | 170 | 263 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 28 | MISSING EFFECT | create a n/n black … | 16 | 37 | 60 | Queen Brahne, Grist, the Hunger Tide, Mysidian Elder |
| 29 | MISSING CONTINUOUS EFFECT | Commander creatures you own have “…” | 16 | 16 | 16 | Dungeon Delver, Noble Heritage, Acolyte of Bahamut |
| 30 | MISSING EFFECT | ~ deals n … | 15 | 217 | 332 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 31 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 15 | 29 | 67 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |
| 32 | UNSUPPORTED ORACLE PATTERN | As ~ enters, … | 15 | 1 | 19 | Stenn, Paranoid Partisan, Arachne, Psionic Weaver, Pramikon, Sky Rampart |
| 33 | UNSUPPORTED ORACLE PATTERN | More Than Meets the Eye {M} | 15 | 0 | 15 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 34 | MISSING EFFECT | return ~ … | 14 | 83 | 128 | Summon the School, Dragon Fangs, Haunted Dead |
| 35 | MISSING EFFECT | create a n/n white … | 14 | 39 | 66 | Empyrial Storm, Drag the Canal, Ajani Resolute |
| 36 | MISSING MECHANIC | sneak | 14 | 11 | 27 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 37 | MISSING MECHANIC | firebending | 14 | 6 | 22 | Fire Sages, Loyal Fire Sage, Jeong Jeong, the Deserter |
| 38 | MISSING MECHANIC | partner | 14 | 5 | 24 | Lore Weaver, Blaring Captain, Rory Williams |
| 39 | UNSUPPORTED ORACLE PATTERN | • Put a ±N/±N counter(s) on … | 14 | 0 | 38 | Bejeweled Warg, Trusty Retriever, Inspired Inventor |
| 40 | MISSING EFFECT | add {m} … | 13 | 42 | 70 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 41 | UNSUPPORTED ORACLE PATTERN | Living metal | 13 | 0 | 13 | Optimus Prime, Hero // Optimus Prime, Autobot Leader, Megatron, Tyrant // Megatron, Destructive Force, Jetfire, Ingenious Scientist // Jetfire, Air Guardian |
| 42 | MISSING RESTRICTION | ~ can't be blocked by creatures … | 12 | 27 | 56 | Lydia Frye, Pompous Gadabout, Ghost of Ramirez DePietro |
| 43 | MISSING EFFECT | exile the top n … | 12 | 21 | 59 | Duplicity, Memorial Vault, Crossover Collaboration |
| 44 | MISSING EFFECT | exile up to n … | 12 | 19 | 31 | Salvation Swan, Liminal Hold, S.H.I.E.L.D. Flying Car |
| 45 | MISSING SELECTOR | target equipment | 12 | 17 | 26 | Stolen Uniform, Shagrat, Loot Bearer, Thor, God of Thunder |
| 46 | UNSUPPORTED ORACLE PATTERN | Power-up — {M}: Put N ±N/±N … | 12 | 12 | 19 | Thanos, the Mad Titan, Shang-Chi, Martial Mentor, Hulk, Gamma Goliath |
| 47 | MISSING EFFECT | target creature you control … | 11 | 123 | 179 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 48 | MISSING SELECTOR | target instant or sorcery card | 11 | 20 | 36 | Ogre Battlecaster, Flood of Recollection, Impulsivity |
| 49 | MISSING TRIGGER EVENT | Whenever you cast a historic spell | 11 | 15 | 19 | Serra Disciple, Cabal Paladin, Glóin, Dwarf Emissary |
| 50 | MISSING EFFECT | another target … | 11 | 14 | 23 | Hemosymbic Mite, Syr Faren, the Hengehammer, Pippin, Guard of the Citadel |
| 51 | MISSING COST / PERMISSION RULE | You may cast ~ from your … | 11 | 10 | 27 | Marang River Prowler, Quilled Greatwurm, Gravecrawler |
| 52 | MISSING EFFECT | earthbend n … | 11 | 10 | 27 | Earth Village Ruffians, Bumi, Unleashed, Badgermole |
| 53 | MISSING COST / PERMISSION RULE | Once during each of your turns, … | 11 | 7 | 15 | Kotis, Sibsig Champion, One with the Multiverse, Jacob Hauken, Inspector // Hauken's Insight |
| 54 | MISSING EFFECT | if you've cast a … | 11 | 5 | 12 | H.E.R.B.I.E., Lovable Robot, Invisible Woman, Alicia Masters, Skilled Sculptor |
| 55 | MISSING EFFECT | gain control of target … | 10 | 58 | 85 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 56 | MISSING EFFECT | create a n/n green … | 10 | 47 | 88 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 57 | MISSING EFFECT | reveal the top card … | 10 | 34 | 48 | Rashmi, Eternities Crafter, Counterbalance, Sorin, Grim Nemesis |
| 58 | MISSING SELECTOR | target creature card with mana value | 10 | 26 | 39 | General Leo Cristophe, Yathan Roadwatcher, Lazotep Quarry |
| 59 | MISSING RESTRICTION | ~ can't attack or block unless … | 10 | 16 | 23 | Sab-Sunen, Luxa Embodied, Relic Golem, Hollow Warrior |
| 60 | MISSING EFFECT | return it to the … | 10 | 10 | 23 | Bronzehide Lion, Optimus Prime, Hero // Optimus Prime, Autobot Leader, Yedora, Grave Gardener |
| 61 | MISSING SELECTOR | target creatures | 9 | 105 | 208 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 62 | MISSING EFFECT | choose target … | 9 | 70 | 83 | Arcbond, Deglamer, Wreck Hunter |
| 63 | MISSING EFFECT | you gain n … | 9 | 68 | 95 | Belladonna Took, Shu Farmer, Essence Pulse |
| 64 | MISSING EFFECT | reveal the top n … | 9 | 56 | 75 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 65 | MISSING EFFECT | reveal cards from the … | 9 | 25 | 32 | Treasure Hunt, Hei Bai, Forest Guardian, Hermit Druid |
| 66 | MISSING EFFECT | sacrifice another creature … | 9 | 14 | 25 | Rhovanion Rampager, Brawl-Bash Ogre, Ragefire Hellkite |
| 67 | MISSING EFFECT | double the number of … | 9 | 12 | 24 | Fractal Harness, Primordial Hydra, The Millennium Calendar |
| 68 | MISSING CONTINUOUS EFFECT | You have no maximum hand size | 9 | 8 | 23 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 69 | UNSUPPORTED ORACLE PATTERN | Web-slinging {M} | 9 | 4 | 9 | Scarlet Spider, Ben Reilly, Arachne, Psionic Weaver, Spider-Man, Brooklyn Visionary |
| 70 | MISSING CONTINUOUS EFFECT | ~ has indestructible as long as … | 9 | 2 | 12 | Crew Captain, War Historian, Havi, the All-Father |
| 71 | MISSING TRIGGER EVENT | When ~ enters | 9 | 2 | 9 | Niv-Mizzet Reborn, Lobelia Sackville-Baggins, Drizzt Do'Urden |
| 72 | MISSING MECHANIC | companion | 9 | 1 | 9 | Lutri, the Spellchaser, Gyruda, Doom of Depths, Lurrus of the Dream-Den |
| 73 | UNSUPPORTED ORACLE PATTERN | • ~ deals N damage to … | 9 | 0 | 18 | Arbalest Engineers, Tectonic Giant, Umaro, Raging Yeti |
| 74 | UNSUPPORTED ORACLE PATTERN | Storied | 9 | 0 | 9 | Balin, Loremaster, Dáin, Lord of the Iron Hills, Ori, Keeper of Songs |
| 75 | MISSING EFFECT | if you control n … | 8 | 41 | 67 | Dawnhart Wardens, Boundary Lands Ranger, Dispatch |
| 76 | MISSING COST | {M}, Discard ~ | 8 | 34 | 57 | Jiwari, the Earth Aflame, Favor of Jukai, Radiant Solar |
| 77 | MISSING SELECTOR | target creature defending player controls | 8 | 31 | 41 | Fear of Falling, Impetuous Devils, Fiend Binder |
| 78 | MISSING REPLACEMENT PATTERN | ~ enters with a ±N/±N counter(s) on … | 8 | 17 | 37 | Callous Sell-Sword // Burn Together, Avatar of the Resolute, The Duke, Rebel Sentry |
| 79 | MISSING EFFECT | you draw n … | 8 | 16 | 35 | Fang, Fearless l'Cie, Live Fast, Greed's Gambit |
| 80 | MISSING EFFECT | up to n … | 8 | 16 | 34 | Wasp, Shrinking Savior, Restless Vinestalk, Kaito, Dancing Shadow |

## Largest clusters (Commander cards affected)

| # | Category | Cluster | Commander cards | Only missing piece for | Commanders | Examples |
|---|---|---|---|---|---|---|
| 1 | MISSING EFFECT | draw n … | 596 | 220 | 66 | Errand-Rider of Gondor, Krovikan Sorcerer, Heal |
| 2 | MISSING EFFECT | choose n … | 570 | 50 | 65 | Road of Return, Saheeli's Artistry, Eldrazi Confluence |
| 3 | MISSING SELECTOR | target | 346 | 214 | 36 | Cinder Elemental, Archangel of Wrath, Chain of Plasma |
| 4 | MISSING EFFECT | ~ deals n … | 332 | 217 | 15 | Deem Worthy, End-Blaze Epiphany, Harvest Pyre |
| 5 | MISSING COST / PERMISSION RULE | As an additional cost to cast … | 312 | 35 | 6 | Thunderherd Migration, Mind Extraction, Harvest Pyre |
| 6 | MISSING EFFECT | pay {m} … | 285 | 207 | 70 | Labyrinth Adversary, Minion Reflector, Giant's Amulet |
| 7 | MISSING EFFECT | search your library for … | 263 | 170 | 16 | Safewright Quest, Thunderherd Migration, Squadron Hawk |
| 8 | MISSING EFFECT | create n … | 259 | 149 | 38 | Summon the School, Cogwork Assembler, Endless Evil |
| 9 | MISSING EFFECT | put a ±n/±n counter(s) … | 247 | 170 | 67 | Greta, Sweettooth Scourge, Yorvo, Lord of Garenbrig, Ent-Draught Basin |
| 10 | MISSING REPLACEMENT PATTERN | As ~ enters, … | 237 | 47 | 4 | Kindred Discovery, Utopia Sprawl, Game Trail |
| 11 | MISSING EFFECT | until end of turn … | 227 | 151 | 23 | Divergent Growth, Doorman, Strength of Will |
| 12 | MISSING EFFECT | destroy target … | 221 | 138 | 4 | Kalitas, Bloodchief of Ghet, Misfortune's Gain, Raze |
| 13 | MISSING EFFECT | look at the top … | 217 | 157 | 39 | Harald, King of Skemfar, Lantern of Revealing, Puresight Merrow |
| 14 | MISSING SELECTOR | target creatures | 208 | 105 | 9 | Ravenous Gigantotherium, Fire Covenant, Amazing Acrobatics |
| 15 | MISSING SELECTOR | target creature card | 183 | 123 | 26 | Hua Tuo, Honored Physician, Puppeteer Clique, Metamorphosis Fanatic |
| 16 | MISSING EFFECT | target creature you control … | 179 | 123 | 11 | Blessed Defiance, Hard-Hitting Question, Crowd of True Believers |
| 17 | MISSING EFFECT | target creature gets ±n/±n … | 171 | 102 | 4 | Stern Marshal, Spontaneous Flight, Rig for War |
| 18 | MISSING EFFECT | put n … | 152 | 97 | 28 | Black Sun's Zenith, Breaking // Entering, Mind Raker |
| 19 | MISSING EFFECT | if ~ … | 130 | 72 | 19 | Warden of the First Tree, Hixus, Prison Warden, Blinkmoth Urn |
| 20 | MISSING EFFECT | return ~ … | 128 | 83 | 14 | Summon the School, Dragon Fangs, Haunted Dead |
| 21 | MISSING CONTINUOUS EFFECT | ~'s power and toughness are each … | 127 | 64 | 28 | Eluge, the Shoreless Sea, Flora Colossus, Revenant |
| 22 | MISSING EFFECT | exile target … | 118 | 80 | 5 | Astarion's Thirst, Deadly Rollick, Tawnos's Coffin |
| 23 | MISSING EFFECT | exile the top card … | 115 | 54 | 36 | Moonring Mirror, Professional Face-Breaker, Mezzio Mugger |
| 24 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N for each … | 115 | 57 | 32 | Nim Lasher, Benalish Honor Guard, Anya, Merciless Angel |
| 25 | MISSING SELECTOR | target player or planeswalker | 111 | 77 | 5 | Goblin Barrage, Scorching Missile, Consuming Sinkhole |
| 26 | MANA ABILITY WORDING | {M}, … | 108 | 76 | 6 | Saltcrusted Steppe, Cabal Stronghold, Interplanar Beacon |
| 27 | MISSING EFFECT | mill n … | 103 | 65 | 18 | Sparring Dummy, Loafing Giant, Beluna Grandsquall // Seek Thrills |
| 28 | MISSING CONTINUOUS EFFECT | ~ gets ±N/±N as long as … | 98 | 92 | 1 | Sulam Djinn, Zanam Djinn, Isleback Spawn |
| 29 | MISSING MECHANIC | ward | 97 | 13 | 47 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 30 | MISSING EFFECT | you gain n … | 95 | 68 | 9 | Belladonna Took, Shu Farmer, Essence Pulse |
| 31 | MISSING EFFECT | if n … | 92 | 59 | 24 | Airdrop Aeronauts, Hot Pursuit, Kotis, Sibsig Champion |
| 32 | MISSING EFFECT | create a n/n green … | 88 | 47 | 10 | Rhonas's Last Stand, Kasmina, Enigma Sage, Choco-Comet |
| 33 | MISSING EFFECT | gain control of target … | 85 | 58 | 10 | Sauron, the Lidless Eye, New Blood, Unwilling Recruit |
| 34 | MISSING EFFECT | choose target … | 83 | 70 | 9 | Arcbond, Deglamer, Wreck Hunter |
| 35 | MISSING EFFECT | discard n … | 81 | 46 | 18 | Keldon Raider, Witch's Mark, Seasoned Pyromancer |
| 36 | MISSING EFFECT | tap target … | 81 | 47 | 4 | Spider-Woman, Secret Agent, Guardian of Tazeem, Gilded Scuttler |
| 37 | MISSING TRIGGER EVENT | When you cast ~ | 80 | 29 | 18 | Empyrial Storm, The Fourteenth Doctor, Ulamog, the Ceaseless Hunger |
| 38 | MISSING SELECTOR | target opponent reveals their hand | 79 | 53 | 1 | Gix's Caress, Mindclaw Shaman, Grief |
| 39 | MISSING EFFECT | it deals n … | 77 | 62 | 3 | Goblin Chainwhirler, Festering Evil, Unsparing Boltcaster |
| 40 | MISSING SELECTOR | target card | 77 | 43 | 3 | Funeral Pyre, Barkform Harvester, Carrion Locust |
| 41 | MISSING EFFECT | return target … | 77 | 47 | 1 | Surging Aether, Perilous Voyage, Geistwave |
| 42 | MISSING EFFECT | if there are n … | 76 | 31 | 6 | Locked in the Cemetery, Sanguine Spy, Extricator of Sin // Extricator of Flesh |
| 43 | MISSING EFFECT | reveal the top n … | 75 | 56 | 9 | Green Sun's Twilight, Benefaction of Rhonas, Karn, Scion of Urza |
| 44 | MISSING CONTINUOUS EFFECT | During your turn, … | 74 | 37 | 21 | Pompous Gadabout, Long-Lost Lances, Fresh-Faced Recruit |
| 45 | MISSING EFFECT | cast ~ … | 72 | 0 | 1 | Twice Upon a Time // Unlikely Meeting, Defiant Stand, Asinine Antics |
| 46 | UNSUPPORTED ORACLE PATTERN | ~ costs {M} less to cast … | 71 | 38 | 19 | Bedlam Reveler, Gargantuan Leech, Hamza, Guardian of Arashin |
| 47 | MISSING EFFECT | add {m} … | 70 | 42 | 13 | Waste Not, Akki Rockspeaker, Brightstone Ritual |
| 48 | MISSING EFFECT | transform ~ … | 69 | 23 | 23 | Ulvenwald Captive // Ulvenwald Abomination, Westvale Abbey // Ormendahl, Profane Prince, Seraph of New Capenna // Seraph of New Phyrexia |
| 49 | MISSING EFFECT | create a n/n colorless … | 69 | 38 | 7 | Karn, Scion of Urza, Stalactite Dagger, Serpent Generator |
| 50 | MISSING CONTINUOUS EFFECT | ~'s power is equal to the … | 67 | 29 | 15 | Uurg, Spawn of Turg, Snow Villiers, Nethergoyf |

## Top Commander features to implement next

Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.

| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |
|---|---|---|---|---|---|---|
| 1 | mana:ability | engine | 0 | 367 | 239 | Saltcrusted Steppe, Flywheel Racer, The Emperor of Palamecia // The Lord Master of Hell |
| 2 | template:Enchanted creature has “…” | continuous | 0 | 28 | 22 | Ghostly Touch, Mark of Sakiko, Unquenchable Fury |
| 3 | template:Enchanted creature gets ±N/±N and has “…” | continuous | 0 | 25 | 21 | Arcane Teachings, Lunarch Mantle, Deviant Glee |
| 4 | keyword:foretell | keyword | 0 | 51 | 20 | The Foretold Soldier, Rise of the Dread Marn, Green Slime |
| 5 | template:Commander creatures you own have “…” | continuous | 0 | 20 | 20 | Dungeon Delver, Scion of Halaster, Noble Heritage |
| 6 | keyword:enchant | keyword | 0 | 67 | 19 | Utopia Sprawl, One with the Stars, Corrupted Roots |
| 7 | keyword:banding | keyword | 0 | 24 | 19 | Nalathni Dragon, Mishra's War Machine, Kjeldoran Escort |
| 8 | keyword:bestow | keyword | 0 | 42 | 18 | Leafcrown Dryad, Baleful Eidolon, Observant Alseid |
| 9 | template:~ enters prepared. | static | 0 | 40 | 16 | Adventurous Eater // Have a Bite, Maelstrom Artisan // Rocket Volley, Fatehold Chronologist // Peer Review |
| 10 | keyword:splice | keyword | 0 | 30 | 16 | Evermind, Horobi's Whisper, Desperate Ritual |
| 11 | keyword:backup | keyword | 0 | 25 | 16 | Saiba Cryptomancer, Chomping Kavu, Consuming Aetherborn |
| 12 | template:Equipped creature has “…” | continuous | 0 | 24 | 16 | Field-Tested Frying Pan, Sorcerer's Wand, Fishing Pole |
| 13 | template:Equipped creature gets ±N/±N and has “…” | continuous | 0 | 25 | 15 | Giant's Amulet, Iconic Shield, Candlestick |
| 14 | template:Modular N | static | 0 | 23 | 15 | Arcbound Whelp, Arcbound Javelineer, Arcbound Hybrid |
| 15 | keyword:equip | keyword | 0 | 49 | 14 | Bloodthorn Flail, Strong Back, Team Pennant |
| 16 | template:~ can't be blocked by creatures with power N or less. | restriction | 0 | 32 | 14 | Glinting Creeper, Dread Linnorm // Scale Deflection, Chomping Kavu |
| 17 | template:{M}: Return ~ from your graveyard to your hand. | activated | 0 | 22 | 14 | The Sound of Drums, Merchant of Many Hats, Convenient Target |
| 18 | keyword:ward | keyword | 0 | 97 | 13 | Tyranid Harridan, Grey Host Reinforcements, Kwia Vigorbloom |
| 19 | keyword:warp | keyword | 0 | 31 | 13 | Starbreach Whale, Knight Luminary, Loading Zone |
| 20 | template:When ~ enters, attach it to target creature you control. | triggered | 0 | 30 | 13 | Maul of the Skyclaves, Meltstrider's Gear, Bramble Armor |
| 21 | keyword:encore | keyword | 0 | 26 | 13 | Impulsivity, Sliver Gravemother, Belonging |
| 22 | keyword:myriad | keyword | 0 | 23 | 13 | The Master, Multiplied, Sumala Rumblers, Conclave Evangelist |
| 23 | keyword:ninjutsu | keyword | 0 | 35 | 12 | Higure, the Still Wind, Moonblade Shinobi, Mist-Syndicate Naga |
| 24 | keyword:overload | keyword | 0 | 27 | 12 | Mizzium Skin, Corporeal Projection, Mind Rake |
| 25 | template:−N: You get an emblem with “…” | loyalty | 0 | 64 | 11 | Zariel, Archduke of Avernus, Elspeth, Sun's Champion, Teferi, Temporal Archmage |
| 26 | keyword:sneak | keyword | 0 | 27 | 11 | Turncoat Kunoichi, Michelangelo, Improviser, Donatello's Technique |
| 27 | keyword:offspring | keyword | 0 | 20 | 11 | Splash Lasher, Rust-Shield Rampager, Prosperous Bandit |
| 28 | keyword:living weapon | keyword | 0 | 19 | 11 | Nettlecyst, Lashwrithe, Skinwing |
| 29 | keyword:unleash | keyword | 0 | 15 | 11 | Rakdos Drake, Grim Roustabout, Chaos Imps |
| 30 | template:When ~ enters, you may discard N card(s). If you do, draw N card(s). | triggered | 0 | 15 | 11 | Keldon Raider, Bitter Reunion, Viashino Racketeer |
| 31 | template:All Slivers have “…” | continuous | 0 | 11 | 11 | Magma Sliver, Basal Sliver, Mesmeric Sliver |
| 32 | keyword:disguise | keyword | 0 | 43 | 10 | Boltbender, Nightdrinker Moroii, Concealed Weapon |
| 33 | keyword:entwine | keyword | 0 | 32 | 10 | Road of Return, Rain of Rust, Blinding Beam |
| 34 | keyword:evolve | keyword | 0 | 22 | 10 | Adaptive Snapjaw, Shambleshark, Tyranid Prime |
| 35 | keyword:mentor | keyword | 0 | 19 | 10 | Hammer Dropper, Legion Warboss, Tributary Instructor |
| 36 | keyword:prototype | keyword | 0 | 19 | 10 | Goring Warplow, Combat Thresher, Woodcaller Automaton |
| 37 | keyword:embalm | keyword | 0 | 15 | 10 | Heart-Piercer Manticore, Angel of Sanctions, Anointer Priest |
| 38 | template:Scavenge {M} | static | 0 | 14 | 10 | Terrus Wurm, Deadbridge Goliath, Dodgy Jalopy |
| 39 | keyword:rampage | keyword | 0 | 12 | 10 | Craw Giant, Balduvian War-Makers, Varchild's War-Riders |
| 40 | template:Threshold — ~ gets ±N/±N as long as there are N or more cards in your graveyard. | continuous | 0 | 12 | 10 | Krosan Beast, Nimble Mongoose, Anurid Barkripper |
| 41 | template:{M}, Sacrifice ~: It deals N damage to any target. | activated | 0 | 12 | 10 | Fireforger's Puzzleknot, Lightning Spear, Pyrite Spellbomb |
| 42 | template:Enchanted land has “…” | continuous | 0 | 11 | 10 | Chamber of Manipulation, Discreet Retreat, Farmstead |
| 43 | template:~ enters tapped unless you control N or fewer other lands. | replacement | 0 | 11 | 10 | Concealed Courtyard, Inspiring Vantage, Blackcleave Cliffs |
| 44 | template:~ enters tapped unless a player has N or less life. | replacement | 0 | 10 | 10 | Abandoned Campground, Raucous Carnival, Strangled Cemetery |
| 45 | template:~ enters tapped unless you control N or more basic lands. | replacement | 0 | 10 | 10 | Sodden Verdure, Smoldering Marsh, Vernal Fen |
| 46 | template:~ enters tapped unless you control N or more other lands. | replacement | 0 | 10 | 10 | Rockfall Vale, Stormcarved Coast, Sundown Pass |
| 47 | template:~ enters tapped unless you control a planeswalker. | replacement | 0 | 10 | 10 | Theorix Annex, Stingerquill Annex, Konstrari Annex |
| 48 | template:~ enters tapped unless you have N or more opponents. | replacement | 0 | 10 | 10 | Spire Garden, Sea of Clouds, Bountiful Promenade |
| 49 | keyword:cumulative upkeep | keyword | 0 | 23 | 9 | Varchild's War-Riders, Aboroth, Inner Sanctum |
| 50 | keyword:vanishing | keyword | 0 | 20 | 9 | Soultether Golem, Deadly Grub, Reality Acid |
| 51 | keyword:extort | keyword | 0 | 17 | 9 | Syndicate Heavy, Tithe Drinker, Kingpin's Pet |
| 52 | keyword:fading | keyword | 0 | 17 | 9 | Parallax Wave, Phyrexian Prowler, Skyshroud Ridgeback |
| 53 | keyword:retrace | keyword | 0 | 17 | 9 | Flame Jab, Monstrify, Waves of Aggression |
| 54 | template:Prevent all combat damage that would be dealt this turn. | prevention | 0 | 14 | 9 | Jaheira's Respite, Fog, Darkness |
| 55 | template:{M}, {M}, Sacrifice ~: It deals N damage to target creature. | activated | 0 | 11 | 9 | Vial of Dragonfire, Flamecast Wheel, Mouth of Ronom |
| 56 | template:You control enchanted creature. | static | 0 | 28 | 8 | Spirit Away, Illusory Gains, Biting Tether |
| 57 | template:You have no maximum hand size. | continuous | 0 | 23 | 8 | Nyssa of Traken, Curiosity Crafter, Wizard Class |
| 58 | template:{M}: Adapt N. | activated | 0 | 22 | 8 | Zegana, Utopian Speaker, Temperamental Oozewagg, Evolution Witness |
| 59 | template:During your turn, ~ has first strike. | continuous | 0 | 17 | 8 | Fresh-Faced Recruit, Duelist of Deep Faith, Null Group Biological Assets |
| 60 | template:~'s power and toughness are each equal to the number of lands you control. | characteristic_defining | 0 | 17 | 8 | Flora Colossus, Rubblehulk, Harmonious Grovestrider |

## Coverage by card type

| Type | FULL | PARTIAL | REVIEW | MANUAL |
|---|---|---|---|---|
| Creature | 5839 | 12082 | 0 | 0 |
| Artifact | 899 | 2694 | 0 | 0 |
| Enchantment | 703 | 2944 | 0 | 0 |
| Sorcery | 794 | 2774 | 0 | 0 |
| Instant | 1058 | 2696 | 0 | 0 |
| Land | 516 | 696 | 0 | 0 |
| Planeswalker | 9 | 302 | 0 | 0 |
| Battle | 0 | 36 | 0 | 0 |

## Rules features in the pool (ability lines)

triggered 14909, keyword 14134, spell_effect 9120, activated 7358, continuous 4014, static 3053, mana_ability 2038, replacement 1966, restriction 1474, loyalty 882, prevention 320, additional_cost 307, cost_modifier 261, characteristic_defining 247, permission 207, alternative_cost 180
