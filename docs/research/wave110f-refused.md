# Wave 110F refused / deferred
- Zombie Scavengers: "top creature card of your graveyard" cost needs graveyard-order cost machinery (fixed_top_graveyard_cost46) generalised.
- Oath of Kaya, Rigo: "attacks a planeswalker/player ... with creatures" once-per-what unclear (no rulings in repo).
- Gather Specimens: control-changing entry replacement must cover every entry path (spell, token, move).
- Peace Talks: two-turn global duration plus player targeting prohibition (activated only, not triggered).
- Ogre Enforcer: damage is not tracked per source.
- Circling Vultures: discard is a special action, not an activated ability.
- Medomai's Prophecy, Homura (flip), Faces of the Past: multi-piece foundations.
- Steamcore Scholar: 'unless you discard an instant or sorcery card or a creature card with flying': optional_payment.parse refuses CostComponent.alt (activation_only); needs alt-aware optional discard.
- Profaner of the Dead: 'toughness less than the exploited creature's toughness': exploit event objects = exploiter, evt: stat binds wrong object.
- Fires of Mount Doom: 2nd ability 'When you play a card this way' reflexive on play of exiled card.
- Thunderblade Charge: gy-trigger + pay then cast free from graveyard.
- Fatal Lore / Bane: 'opponent chooses one' modal / 'target opponent may have you draw' foundations.
- Ogre Enforcer: needs damage marked per source (no per-source tally on cards).
- Oath of Kaya, Rigo: trigger once per attacked planeswalker/defender, not once per attack declaration (existing your_pw fires once); ruling unverified locally.
- Taste of Paradise: multikicker rewrite would make it a "kicked" spell for other cards (wrong); needs a plain pay-N-times additional cost.
- Fblthp (Impossibly Lost), Worms of the Earth, Overblaze, Melira, Mangara's Equity: batch-opponent damage trigger / second upkeep ability / doubling / poison cap / chosen-color recipient: each a new foundation. (Parnesse: built in wave 110J.)
- Thunderblade Charge: graveyard trigger "if this card is in your graveyard, you may pay ... cast it without paying" needs graveyard batch-damage trigger and free cast from graveyard.
- Gather Specimens: replaces every creature entry (reanimation, put-onto, tokens) under an opponent; no single entry hook.
- Dance of Many: "the token" link needs a trigger on a specific linked object leaving (no created-with leave watcher).
- Cemetery Desecrator: exiled card's MV bound into reflexive modes (cost:exiled reads payment records only).
- Faceless One / The Prismatic Piper: chosen color applies in deck construction (903.4b), foundation spans deck builder and pregame.
- Null Chamber: two chosen names, one by an opponent (card_names stores one name per source).
- Glyph of Reincarnation, Camouflage, Noxious Vapors (multicolor choice ruling unchecked), Malik (secret choices), Zevlor: not attempted.
- s8: Vengeful Pharaoh: trigger "combat damage is dealt to you or a planeswalker you control" needs a two-subject damage event (only Pharaoh has it). Fires of Mount Doom: "When you play a card this way" reflexive trigger on a played exiled card (no machinery). Dance of Many: token<->enchantment linked leave triggers. Liquid Fire: number chosen as additional cost (cast-time number choice; pick110e is creature-type only). Brutal Suppression/Drought: extra non-mana cost on activated abilities. Fatal Lore/Misfortune: opponent picks the mode at resolution with targets.
- s9: Peace Talks: "this turn and next turn" two-turn duration plus a global "players and permanents can't be targeted" prohibition; neither exists.
- s9: Extrapolate the Impossible: cards from outside the game (no sideboard in Commander); left PARTIAL, not decided.
- s9: Drought / Brutal Suppression: "cost an additional 'Sacrifice a Swamp'" per symbol / per activation needs sacrifice components in the cost-change table.
- s10: Peace Talks: needs a "this turn and next turn" duration plus a global "can't be the target of spells or activated abilities" prohibition that spares triggered abilities; Characteristics.is_ability does not tell triggered from activated (about 10 source_of call sites).
- s10: Dance of Many: "the token leaves the battlefield" needs a look-back selector on the token created with this permanent (rules.created_with oids) in leave events.
- s10: Cemetery Desecrator: "When you do, choose one -" reflexive modal trigger with bullet modes and X from the exiled card's mana value; nothing parses it.
- s10: Worms of the Earth: "any player may sacrifice two lands or have it deal 5 damage to that player" order and simultaneity across players is unspecified in the rules text; left manual.
- s10: Noxious Vapors: "chooses one card of each color" for a multicolored card (counts for several colors?) has no ruling in the local data.
- s10: Mangara's Equity: "choose black or red" two-color choice, chosen-color source filter and "or a white creature you control" recipient are three missing pieces for one card.
- s10: Drought / Brutal Suppression: unchanged (sacrifice components in the cost-change table).
- s11: Mangara's Equity / Noxious Vapors / Null Chamber / Worms / Peace Talks: still open (see s9-s10 notes).
- s13: Noxious Vapors multicolored cards: no CR rule or ruling in the local data on one card serving several colors; a hand holding one goes to manual_resolution (tested). Drought/Brutal Suppression: activated-ability tax not automated (mana abilities, cycling, unearth, equip have own cost routes); cards PARTIAL, activations never refused (s15).
- Zevlor, Camouflage, Glyph of Reincarnation: not done wave 110F s15 (see handoff_f.md next).

## Final pass (wave 110F, 20 cards not FULL on the lead branch)

Promoted (each with a scenario test on real Oracle text, tests/test_rules_wave110f_fin.py and test_rules_wave110f_fin_piles.py): Idris, Soul of the TARDIS; The Book of Vile Darkness; Diabolic Servitude; Mimeoplasm,
Revered One; Tahngarth, First Mate; Riku of Many Paths; Indominus Rex, Alpha; Animate Artifact; The Master, Gallifrey's End; Retriever Phoenix; The Seventh Doctor; Land Equilibrium; Stand or Fall (802.2: every
opponent is a defending player as the combat phase starts); General Jarkeld; Kylox's Voltstrider; Taster of Wares; Gather Specimens; North Star; Arcum's Sleigh (802.2a / 508.5a: with several defending players
the controller chooses one, so any opponent of the active player controlling a snow land satisfies it). The older notes above for these cards are superseded.

- Ertai's Meddling: final pass: unsettled because "puts it onto the stack as a copy of the original spell" has no CR rule (no "delay counter", no card put onto the stack as a copy), and the rulings disagree: 2004-10-04 (a copy
  of a morph spell is a face-up 2/2; a copy with no card ceases to exist when exiled) read it as a copy spell, 2011-01-22 (the card still remembers the flashback cost and is exiled when it resolves) as the physical card on
  the stack; whether a permanent spell then makes a token or the card is not settled.
