# Wave 110J refused

- Cannibalize: which creature is exiled is chosen on resolution among the legal targets; a fixed target order would guess the ruling for one illegal target.
- Arcum's Sleigh: "defending player controls a snow land" has no defending player outside an attack trigger in multiplayer (506.2); no ruling found.
- Ray of Frost: conditional "loses all abilities" static; layers (attached_types.wipe_key) read lose_all without its condition.
- Gaea's Liege: attacking/not attacking P/T from two Forest counts (no conditional CDA support); Crown of Convergence: color-sharing with top card.
- Corruption of Towashi: no "enters transformed" event.
- Jester's Mask: already "too large" in wave100-refused (hidden hand/library swap with a searching opponent library); not re-researched.
- Magnetic Web: forced-attack requirement for all magnet-counter creatures, set after attackers are declared; no foundation.
- Rasputin Dreamweaver: "started the turn untapped" has no turn-start snapshot and the untap-step ruling is unconfirmed; plus a counter cap.
- Livio, Oathsworn Sentinel: exiled-with-counter cards returned later (aegis); no exile-counter foundation.
- Simic Guildmage: Aura reattach to another permanent (303.4) not supported.
- Manor Gargoyle: "indestructible as long as it has defender" reads the source's own layer-6 keywords while deriving them (613.8 dependency), needs a keyword-aware static condition.
- Rumbling Ruin: selector compare has no "number of +1/+1 counters on creatures you control" right side, and the number must be fixed at resolution.
- Corruption of Towashi: no "enters transformed" event in the engine.
- Ray of Frost: promoted in s3 (line above is stale). The Oracle reads "As long as enchanted creature is red, it loses all abilities" with no colour change, so there is no self-reference; the colour is read in layer 5 before layer 6 (613.1e-f, 611.3a).
- Arcum's Sleigh: "defending player" outside combat events is undefined in multiplayer (no ruling found).
- Bone Shaman: "creatures dealt damage by this creature this turn can't be regenerated" needs a damage-linked regeneration shield.
- Jester's Mask: searching another player's library for a count tied to a hand move; no foundation.
- Simic Guildmage, Livio, Merseine, Rasputin, Crown of Convergence, Wiitigo: each needs a new foundation (see handoff_j).
- Wiitigo, Shape of the Wiitigo: promoted in s5 (stale line above): attack/block marks (Engaged110j choice) + previous own turn.
- Manor Gargoyle: "indestructible as long as it has defender" depends on its own layer-6 result (613.8); static conditions are read without the affected object.
- Corruption of Towashi: no "enters transformed" event (702.145b entry is a replacement, no zone-change fact carries it).
- Rock Hydra: per-1 damage prevention capped by counters; no partial-prevention-by-counters op (Polukranos prevents all).
- Animate Artifact: "isn't a creature, it's an artifact creature with P/T = mana value" (attached type + conditional base P/T) unread.
- Shuriken: needs the host's Ninja type as it was unattached (LKI at cost time).
- Echo Chamber, Magus of the Arena, Keeper of the Dead: "an opponent chooses target ..." / "as you activate" target conditions; no foundation in this branch.
- Apocalypse Chime, Golgothian Sylex: "name originally printed in the X expansion" needs set membership data.
- Bomb Squad: state trigger "a creature has four or more fuse counters" with "that creature"; no CR rule or ruling found for several creatures reaching four at once (603.8 covers one state, not one per object). Needs the ruling before building a per-object state trigger.
- Paliano, the High City: "chosen as you drafted cards named Paliano" depends on draft history that a Commander game does not have; stays manual (no CR rule, no ruling).
- Bomb Squad (demoted, s9): "Whenever a creature has four or more fuse counters on it" is a state trigger (603.8). A "counters put on" rewrite differs: no trigger if Bomb Squad enters while a creature already has 4+, and a second trigger for a 5th counter put while the first is on the stack. No ruling for two creatures at 4+ at once ("that creature"). Needs a per-creature state trigger plus that ruling.
- Bomb Squad: PROMOTED in s10 (stale lines above). Per-creature 603.8 state trigger (state_triggers._each); several creatures at four at once trigger once each (analogy: each creature is its own state, "that creature" binds it; no official ruling found).
- Equinox (s10): "if it would destroy a land you control" needs a look-ahead into the countered spell's effects and targets (forms: target land, all lands, modes, replacement); no ruling listing the cases, so a partial reading would guess.
- Guardian Beast (s10): needs "can't be enchanted" for all Auras and a "can't gain control" prohibition on every control-change path; neither exists.
- Paliano, the High City (s11): no draft precedes a game so no color is chosen (905.2b) and the mana ability adds nothing, but coverage needs mana.parse_mana_ability to return a ManaAbility; options=() is not handled by auto-payment. Foundation: zero-option ManaAbility. Not refused on rules.
- Volrath's Shapeshifter (s11): "full text of that card" needs borrowing triggered/static abilities too (abilities_of lends activated only). Foundation work, not a rules gap.
- Bludgeon Brawl (s11): needs per-object granted Equipment type + "equip {X}" + "+X/+0" with X = the artifact's own mana value (layers grants are static text). Foundation work.

## Session 12 (promoted: Paliano, Takklemaggot, Volrath's Curse, Last Voyage of the _____, Equinox; earlier lines about them are stale)
- Spy Kit: "all names of nonlegendary creature cards" needs an index of every such card name (the engine's CardInfo only has get(card_id)); card_names.has_name/share would need that index (ruling 2016-08-23: Oracle reference incl. back faces, no tokens).
- Bludgeon Brawl: per-artifact layer-4 Equipment subtype plus a per-artifact "Equip {X}" and "Equipped creature gets +X/+0" grant with X = that artifact's mana value; statics grant fixed texts, no per-object grant foundation; dependency with "becomes a creature" (2011-06-01 ruling).
- Volrath's Shapeshifter: dynamic text-changing effect (2008-08-01 ruling) following the top card of the graveyard; copy recipes are stored per object, not derived from a changing zone.
- Guardian Beast: unchanged (see above).

## Session 13 (promoted: Guardian Beast, Spy Kit, Bludgeon Brawl, Volrath's Shapeshifter; the earlier lines about them are stale)
- Spy Kit: CR 612.7 settles it ("all names of nonlegendary creature cards", Oracle reference). Built as a name_test on Characteristics (card_names.has_name asks the card DB); `names_of`/`share` (201.2 comparisons) do not see the extra names, only legendary-rule-irrelevant name checks matter (named-card effects).
- Volrath's Shapeshifter: CR 612.6 settles it (layer 3 full text); derived in copying.layer1, followed live by the graveyard.
- Bludgeon Brawl: per-recipient "‹mv›" placeholder in grants (layers.py).
- Guardian Beast: rules cant_be_enchanted110j / cant_gain_control110j (attachments, targets, effects._control_effect).

## Final pass (wave 110 final, agent J)

- Contractual Safeguard: built in wave 110J (last cards): the player picks a creature and a kind of counter on it, each other creature gets one; the addendum's shield counter may be chosen (ruling 2022-04-29).
- Psychic Battle: final pass: unsettled because "chooses one or more targets" has a settled meaning only for a spell cast, an ability activated and a triggered ability put on the stack (601.2c, 602.2b, 603.3d); whether a copy whose controller chooses new targets (707.10c) or another effect that changes targets counts has no CR rule and no ruling (the four Scryfall rulings are about the change itself; the card's own "changing targets this way doesn't trigger" sentence only hints that changes may count).
- Captain America, First Avenger: built in wave 110J (last cards): the Equipment is chosen first (601.2b: a value defined by a later choice is chosen at announcement), then targets and division (Gatherer rulings 2026-06-19, 608.2b).
