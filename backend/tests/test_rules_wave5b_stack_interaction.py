"""Wave 5B: spells and abilities that act on other spells on the stack (app/rules/stack_interaction.py).

* "Counter target spell. Its controller …": the countered spell's controller as it last existed on the
  stack (608.2h, 701.6a); a spell that can't be countered still gives its controller the rider (608.2c,
  An Offer You Can't Refuse's ruling). "its mana value" counts X on the stack (202.3e).
* Mana Drain: a delayed trigger (603.7) at the beginning of your next main phase (505.1), its amount the
  countered spell's mana value as it last existed (X included).
* Changing targets (115.7a-b, 115.7e, 115.10): "Change the target of target spell with a single target"
  (a new legal target must be chosen if there is one, by the changing spell's controller as it
  resolves), "Change a target of target spell or ability to this creature" (only if legal), the new
  target "becomes the target" (ward, 702.21a).
Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import (
    creature,
    life,
    on_field,
    pick,
    settle,
    to_hand,
    to_turn,
    until_asked,
)
from tests.test_rules_effects import mana, replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card("An Offer You Can't Refuse", set_code="tst", number="Y501", mana_cost="{U}", cmc=1.0, type_line="Instant",
         oracle_text="Counter target noncreature spell. Its controller creates two Treasure tokens. (They're artifacts with "
                     "\"{T}, Sacrifice this token: Add one mana of any color.\")", colors=["U"], color_identity=["U"],
         keywords=["Treasure"]),
    card("Swan Song", set_code="tst", number="Y502", mana_cost="{U}", cmc=1.0, type_line="Instant",
         oracle_text="Counter target enchantment, instant, or sorcery spell. Its controller creates a 2/2 blue Bird creature "
                     "token with flying.", colors=["U"], color_identity=["U"]),
    card("Countersquall", set_code="tst", number="Y503", mana_cost="{U}{B}", cmc=2.0, type_line="Instant",
         oracle_text="Counter target noncreature spell. Its controller loses 2 life.", colors=["B", "U"], color_identity=["B", "U"]),
    card("Punish Ignorance", set_code="tst", number="Y504", mana_cost="{W}{U}{U}{B}", cmc=4.0, type_line="Instant",
         oracle_text="Counter target spell. Its controller loses 3 life and you gain 3 life.", colors=["B", "U", "W"],
         color_identity=["B", "U", "W"]),
    card("Illumination", set_code="tst", number="Y505", mana_cost="{W}{W}", cmc=2.0, type_line="Instant",
         oracle_text="Counter target artifact or enchantment spell. Its controller gains life equal to its mana value.",
         colors=["W"], color_identity=["W"]),
    card("Didn't Say Please", set_code="tst", number="Y506", mana_cost="{1}{U}{U}", cmc=3.0, type_line="Instant",
         oracle_text="Counter target spell. Its controller mills three cards.", colors=["U"], color_identity=["U"], keywords=["Mill"]),
    card("Dismal Failure", set_code="tst", number="Y507", mana_cost="{2}{U}{U}", cmc=4.0, type_line="Instant",
         oracle_text="Counter target spell. Its controller discards a card.", colors=["U"], color_identity=["U"]),
    card("Deny the Witch", set_code="tst", number="Y508", mana_cost="{1}{W}{U}{B}", cmc=4.0, type_line="Instant",
         oracle_text="Counter target spell, activated ability, or triggered ability. Its controller loses life equal to the number "
                     "of creatures you control.", colors=["B", "U", "W"], color_identity=["B", "U", "W"]),
    card("Mana Drain", set_code="tst", number="Y509", mana_cost="{U}{U}", cmc=2.0, type_line="Instant",
         oracle_text="Counter target spell. At the beginning of your next main phase, add an amount of {C} equal to that spell's "
                     "mana value.", colors=["U"], color_identity=["U"]),
    card("Essence Backlash", set_code="tst", number="Y510", mana_cost="{2}{U}{R}", cmc=4.0, type_line="Instant",
         oracle_text="Counter target creature spell. Essence Backlash deals damage equal to that spell's power to its controller.",
         colors=["R", "U"], color_identity=["R", "U"]),
    card("Imp's Mischief", set_code="tst", number="Y511", mana_cost="{1}{B}", cmc=2.0, type_line="Instant",
         oracle_text="Change the target of target spell with a single target. You lose life equal to that spell's mana value.",
         colors=["B"], color_identity=["B"]),
    card("Shunt", set_code="tst", number="Y512", mana_cost="{1}{R}{R}", cmc=3.0, type_line="Instant",
         oracle_text="Change the target of target spell with a single target.", colors=["R"], color_identity=["R"]),
    card("Spellskite", set_code="tst", number="Y513", mana_cost="{2}", cmc=2.0, type_line="Artifact Creature — Phyrexian Horror",
         oracle_text="{U/P}: Change a target of target spell or ability to this creature. ({U/P} can be paid with either {U} or 2 "
                     "life.)", power="0", toughness="4"),
    card("Mizzium Meddler", set_code="tst", number="Y514", mana_cost="{2}{U}", cmc=3.0, type_line="Creature — Vedalken Wizard",
         oracle_text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, you may "
                     "change a target of target spell or ability to this creature.", power="1", toughness="4", colors=["U"],
         color_identity=["U"], keywords=["Flash"]),
    card("Mirrorshell Crab", set_code="tst", number="Y515", mana_cost="{5}{U}{U}", cmc=7.0, type_line="Artifact Creature — Crab",
         oracle_text="Ward {3} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it "
                     "unless that player pays {3}.)\nChannel — {2}{U}, Discard this card: Counter target spell or ability unless "
                     "its controller pays {3}.", power="5", toughness="7", colors=["U"], color_identity=["U"],
         keywords=["Ward", "Channel"]),
    card("Abrupt Decay", set_code="tst", number="Y516", mana_cost="{B}{G}", cmc=2.0, type_line="Instant",
         oracle_text="This spell can't be countered.\nDestroy target nonland permanent with mana value 3 or less.",
         colors=["B", "G"], color_identity=["B", "G"]),
    card("Blaze", set_code="tst", number="Y517", mana_cost="{X}{R}", cmc=1.0, type_line="Sorcery",
         oracle_text="Blaze deals X damage to any target.", colors=["R"], color_identity=["R"]),
    card("Hangarback Walker", set_code="tst", number="Y518", mana_cost="{X}{X}", cmc=0.0, type_line="Artifact Creature — Construct",
         oracle_text="This creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a 1/1 colorless Thopter "
                     "artifact creature token with flying for each +1/+1 counter on this creature.\n{1}, {T}: Put a +1/+1 counter "
                     "on this creature.", power="0", toughness="0"),
    card("Arc Trail", set_code="tst", number="Y519", mana_cost="{1}{R}", cmc=2.0, type_line="Sorcery",
         oracle_text="Arc Trail deals 2 damage to any target and 1 damage to any other target.", colors=["R"], color_identity=["R"]),
    card("Rebuff the Wicked", set_code="tst", number="Y521", mana_cost="{W}", cmc=1.0, type_line="Instant",
         oracle_text="Counter target spell that targets a permanent you control.", colors=["W"], color_identity=["W"]),
    card("Siren Stormtamer", set_code="tst", number="Y522", mana_cost="{U}", cmc=1.0, type_line="Creature — Siren Pirate Wizard",
         oracle_text="Flying\n{U}, Sacrifice this creature: Counter target spell or ability that targets you or a creature you "
                     "control.", power="1", toughness="1", colors=["U"], color_identity=["U"], keywords=["Flying"]),
    card("Reparations", set_code="tst", number="Y523", mana_cost="{1}{W}{U}", cmc=3.0, type_line="Enchantment",
         oracle_text="Whenever an opponent casts a spell that targets you or a creature you control, you may draw a card.",
         colors=["U", "W"], color_identity=["U", "W"]),
    card("Mirror Sheen", set_code="tst", number="Y524", mana_cost="{1}{U/R}{U/R}", cmc=3.0, type_line="Enchantment",
         oracle_text="{1}{U/R}{U/R}: Copy target instant or sorcery spell that targets you. You may choose new targets for the "
                     "copy.", colors=["R", "U"], color_identity=["R", "U"]),
    card("Lava Spike", set_code="tst", number="Y520", mana_cost="{R}", cmc=1.0, type_line="Sorcery — Arcane",
         oracle_text="Lava Spike deals 3 damage to target player or planeswalker.", colors=["R"], color_identity=["R"]),
]
FULL = ["An Offer You Can't Refuse", "Swan Song", "Countersquall", "Punish Ignorance", "Illumination", "Didn't Say Please",
        "Dismal Failure", "Deny the Witch", "Mana Drain", "Essence Backlash", "Imp's Mischief", "Shunt", "Spellskite",
        "Mizzium Meddler", "Mirrorshell Crab", "Rebuff the Wicked", "Siren Stormtamer", "Reparations", "Mirror Sheen"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    act(s, "p2", type="set_prefs", response="on")
    return s


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def alice_casts(s, name, *, targets=(), x=None, counts=None, **pay):
    c = to_hand(s, name)
    mana(s, **pay)
    kw = {**({"x_value": x} if x is not None else {}), **({"target_counts": counts} if counts else {})}
    act(s, "p1", type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    return c


def bob_answers(s, name, target, **pay):
    c = to_hand(s, name, "p2")
    mana(s, "p2", **pay)
    act(s, "p2", type="cast_spell", card_id=c.id, targets=[target])
    return c


def named(s, name, pid):
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone.endswith(":battlefield")]


# -- the wording ------------------------------------------------------------------------------------
def test_wordings():
    offer = scripts.parse_effects("Counter target noncreature spell. Its controller creates two Treasure tokens.")
    assert offer is not None and offer[0][0] == {"do": "counter", "who": "target", "as": "e0"}
    assert offer[0][1]["who"] == "ref:e0.controller" and offer[0][1]["n"] == 2
    lumen = scripts.parse_effects("Counter target artifact or enchantment spell. Its controller gains life equal to its mana value.")
    assert lumen is not None and lumen[0][1]["n"] == {"mana_value": "ref:e0"}
    drain = scripts.parse_effects("Counter target spell. At the beginning of your next main phase, add an amount of {C} equal to "
                                  "that spell's mana value.")
    assert drain is not None and drain[0][1]["when"] == {"kind": "step", "step": "main", "whose": "you"}
    assert drain[0][2] == {"do": "deferred:add_mana", "sym": "C", "n": {"mana_value": "ref:e0"}}
    imp = scripts.parse_effects("Change the target of target spell with a single target. You lose life equal to that spell's mana "
                                "value.")
    assert imp is not None and imp[0][0] == {"do": "change_target", "who": "target", "to": None}
    assert imp[0][1]["n"] == {"mana_value": "target"} and "single_target" in imp[1]
    skite = scripts.parse_effects("Change a target of target spell or ability to this creature.")
    assert skite is not None and skite[0][0]["to"] == "self" and "spell_or_ability" in skite[1]
    hydro = scripts.parse_effects("You may change the target of target instant or sorcery spell with a single target to this creature.")
    assert hydro is not None and hydro[2] is True


@pytest.mark.parametrize("text", [
    "Change the target of target spell.",  # (several targets: which? not "with a single target")
    "Change a target of target spell or ability.",  # (to what, and which one?)
    "Change the target of target spell that targets only a single creature to this creature.",  # Muck Drubb
    "Change the target of target spell that targets only a player. The new target must be a player.",  # Rebound
    "Change the target of target spell or ability that targets only this creature. The new target must be a creature.",
    "Counter target spell. Its controller can't cast spells this turn.",  # (a cast restriction: not this family)
    "Copy target spell or ability.",  # (the copy grammar doesn't read "spell or ability")
    "Add an amount of {C} equal to that spell's mana value.",  # (no spell to bind "that spell" to)
])
def test_refused(text):
    assert scripts.parse_effects(text) is None


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- "Its controller …" ------------------------------------------------------------------------------
def test_offer_gives_the_treasures_to_the_bolts_controller(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("An Offer You Can't Refuse",))
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    bob_answers(s, "An Offer You Can't Refuse", bolt.id, U=1)
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and life(s, "p2") == 40
    assert len(named(s, "Treasure", "p1")) == 2 and not named(s, "Treasure", "p2")
    roundtrip(s)


def test_offer_on_a_spell_that_cant_be_countered_still_gives_treasures(cards):
    """608.2c (and the card's ruling): the target is legal, it just isn't countered — the rest still happens."""
    s = build(cards, p1=("Abrupt Decay",), p2=("An Offer You Can't Refuse", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears", "p2")
    decay = alice_casts(s, "Abrupt Decay", targets=[bears.id], B=1, G=1)
    bob_answers(s, "An Offer You Can't Refuse", decay.id, U=1)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[decay.id].zone == "p1:graveyard"
    assert len(named(s, "Treasure", "p1")) == 2
    roundtrip(s)


def test_swan_song_bird_for_its_controller(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Swan Song",))
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    bob_answers(s, "Swan Song", bolt.id, U=1)
    settle(s)
    birds = named(s, "Bird", "p1")
    assert len(birds) == 1 and "Flying" in s.state.cards[birds[0].id].token.text and life(s, "p2") == 40
    roundtrip(s)


@pytest.mark.parametrize("answer,alice,bob", [("Countersquall", 38, 40), ("Punish Ignorance", 37, 43)])
def test_life_riders(cards, answer, alice, bob):
    s = build(cards, p1=("Lightning Bolt",), p2=(answer,))
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    bob_answers(s, answer, bolt.id, W=1, U=2, B=1)
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (alice, bob)
    roundtrip(s)


def test_illumination_counts_x_on_the_stack(cards):
    """202.3e: Hangarback Walker cast with X=2 has mana value 4 on the stack, and as it last existed there (608.2h)."""
    s = build(cards, p1=("Hangarback Walker",), p2=("Illumination",))
    walker = alice_casts(s, "Hangarback Walker", x=2, C=4)
    bob_answers(s, "Illumination", walker.id, W=2)
    settle(s)
    assert s.state.cards[walker.id].zone == "p1:graveyard" and life(s, "p1") == 44
    roundtrip(s)


def test_didnt_say_please_mills_the_caster(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Didn't Say Please",))
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    before = len(zone(s.state, "p1", "library"))
    bob_answers(s, "Didn't Say Please", bolt.id, U=3)
    settle(s)
    assert len(zone(s.state, "p1", "library")) == before - 3 and len(zone(s.state, "p1", "graveyard")) == 4
    roundtrip(s)


def test_dismal_failure_the_caster_chooses_privately(cards):
    s = build(cards, p1=("Lightning Bolt", "Opt", "Giant Growth"), p2=("Dismal Failure",))
    to_hand(s, "Opt")
    to_hand(s, "Giant Growth")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    bob_answers(s, "Dismal Failure", bolt.id, U=4)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    assert "options" not in s.view("p2")["rules"]["decision"]
    opt = next(o.id for o in d.options if s.state.cards[o.id].name == "Opt")
    pick(s, opt)
    settle(s)
    assert s.state.cards[opt].zone == "p1:graveyard" and [s.state.cards[c].name for c in zone(s.state, "p1", "hand")] == ["Giant Growth"]
    roundtrip(s)


def test_essence_backlash_power_of_the_countered_spell(cards):
    s = build(cards, p1=("Grizzly Bears",), p2=("Essence Backlash",))
    bears = alice_casts(s, "Grizzly Bears", G=2)
    bob_answers(s, "Essence Backlash", bears.id, U=1, R=1, C=2)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and life(s, "p1") == 38
    roundtrip(s)


def test_deny_the_witch_counters_a_triggered_ability(cards):
    """"Counter target spell, activated ability, or triggered ability": Soul Warden's trigger; its controller (Alice) loses
    life equal to the creatures Bob controls."""
    s = build(cards, p1=("Soul Warden", "Grizzly Bears"), p2=("Deny the Witch",))
    on_field(s, "Soul Warden")
    creature(s, "p2", "Guard")
    creature(s, "p2", "Guard Two")
    alice_casts(s, "Grizzly Bears", G=2)
    act(s, "p2", type="pass_priority")  # (the Bears resolve; Soul Warden triggers)
    trigger = s.state.zones["stack"][-1]
    assert s.state.cards[trigger].ability is not None
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    bob_answers(s, "Deny the Witch", trigger, W=1, U=1, B=1, C=1)
    settle(s)
    assert life(s, "p1") == 38 and trigger not in s.state.cards
    roundtrip(s)


# -- Mana Drain --------------------------------------------------------------------------------------
def test_mana_drain_adds_the_mana_at_bobs_next_main_phase(cards):
    s = build(cards, p1=("Blaze",), p2=("Mana Drain",))
    blaze = alice_casts(s, "Blaze", targets=["p2"], x=3, R=4)
    bob_answers(s, "Mana Drain", blaze.id, U=2)
    settle(s)
    assert life(s, "p2") == 40 and len(s.state.rules.delayed) == 1
    roundtrip(s)
    to_turn(s, 2, "upkeep")
    assert s.state.players["p2"].mana.get("C", 0) == 0  # (not yet: his upkeep)
    to_turn(s, 2, "main1")
    assert s.state.players["p2"].mana.get("C", 0) == 4 and not s.state.rules.delayed  # (X=3 counted: 202.3e)
    roundtrip(s)


# -- changing targets ----------------------------------------------------------------------------------
def test_imps_mischief_redirects_the_bolt(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Imp's Mischief", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    imp = bob_answers(s, "Imp's Mischief", bolt.id, B=1, C=1)
    d = until_asked(s)
    assert d is not None and d.player == "p2"
    ids = {o.id for o in d.options}
    assert "p1" in ids and bears.id in ids and "p2" not in ids and bolt.id not in ids and imp.id not in ids
    roundtrip(s)
    pick(s, "p1")
    assert [t.id for t in s.state.rules.stack[bolt.id].targets] == ["p1"]
    assert any(a.source == bolt.id and a.targets == ["p1"] for a in s.state.arrows)
    settle(s)
    assert life(s, "p2") == 39 and life(s, "p1") == 37  # (Bob loses the Bolt's mana value; the Bolt hits Alice)
    roundtrip(s)


def test_redirected_onto_a_ward_creature_triggers_ward(cards):
    """115.10 / 702.21a: the new target becomes the target of Alice's spell; Mirrorshell Crab's ward triggers."""
    s = build(cards, p1=("Lightning Bolt",), p2=("Shunt", "Mirrorshell Crab"))
    crab = on_field(s, "Mirrorshell Crab", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    bob_answers(s, "Shunt", bolt.id, R=2, C=1)
    d = until_asked(s)
    mana(s, C=3)  # (Alice could pay the ward)
    pick(s, crab.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
    pick(s, "decline")
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and s.state.cards[crab.id].damage == 0 and life(s, "p2") == 40
    roundtrip(s)


def test_no_other_legal_target_leaves_it_unchanged(cards):
    """115.7a: Murder on the only creature on the table — there's no other legal target, so it stays put."""
    s = build(cards, p1=("Murder",), p2=("Shunt", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears", "p2")
    murder = alice_casts(s, "Murder", targets=[bears.id], B=2, C=1)
    bob_answers(s, "Shunt", murder.id, R=2, C=1)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    roundtrip(s)


def test_shunt_cant_target_a_spell_with_two_targets(cards):
    s = build(cards, p1=("Arc Trail", "Grizzly Bears"), p2=("Shunt",))
    bears = on_field(s, "Grizzly Bears")
    trail = alice_casts(s, "Arc Trail", targets=["p2", bears.id], counts=[1, 1], R=1, C=1)
    shunt = to_hand(s, "Shunt", "p2")
    mana(s, "p2", R=2, C=1)
    with pytest.raises(ActionError) as err:
        act(s, "p2", type="cast_spell", card_id=shunt.id, targets=[trail.id])
    assert "legal target" in str(err.value)


def test_spellskite_takes_the_bolt(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Spellskite", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears", "p2")
    skite = on_field(s, "Spellskite", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=[bears.id], R=1)
    mana(s, "p2", U=1)
    act(s, "p2", type="activate_ability", card_id=skite.id, ability=0, targets=[bolt.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[skite.id].damage == 3
    roundtrip(s)


def test_spellskite_chooses_which_of_two_targets(cards):
    """115.7b and Spellskite's ruling: with two words "target", the ability's controller chooses which one changes; Arc Trail's
    2 damage (the first target, Bob) goes to Spellskite, its 1 damage still to the Bears."""
    s = build(cards, p1=("Arc Trail",), p2=("Spellskite", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears", "p2")
    skite = on_field(s, "Spellskite", "p2")
    trail = alice_casts(s, "Arc Trail", targets=["p2", bears.id], counts=[1, 1], R=1, C=1)
    mana(s, "p2", U=1)
    act(s, "p2", type="activate_ability", card_id=skite.id, ability=0, targets=[trail.id], life_symbols=[])
    d = until_asked(s)
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["0", "1"]
    roundtrip(s)
    pick(s, "0")
    assert [t.id for t in s.state.rules.stack[trail.id].targets] == [skite.id, bears.id]
    settle(s)
    assert life(s, "p2") == 40 and s.state.cards[skite.id].damage == 2 and s.state.cards[bears.id].damage == 1
    roundtrip(s)


def test_spellskite_isnt_a_legal_target_for_lava_spike(cards):
    s = build(cards, p1=("Lava Spike",), p2=("Spellskite",))
    skite = on_field(s, "Spellskite", "p2")
    spike = alice_casts(s, "Lava Spike", targets=["p2"], R=1)
    mana(s, "p2", U=1)
    act(s, "p2", type="activate_ability", card_id=skite.id, ability=0, targets=[spike.id])
    settle(s)
    assert life(s, "p2") == 37 and s.state.cards[skite.id].damage == 0
    roundtrip(s)


@pytest.mark.parametrize("yes", [True, False])
def test_mizzium_meddler_may_take_it(cards, yes):
    s = build(cards, p1=("Lightning Bolt",), p2=("Mizzium Meddler",))
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    meddler = to_hand(s, "Mizzium Meddler", "p2")
    mana(s, "p2", U=1, C=2)
    act(s, "p2", type="cast_spell", card_id=meddler.id)
    d = until_asked(s)  # (the Meddler resolves; its trigger targets the Bolt)
    assert d is not None and d.player == "p2" and bolt.id in {o.id for o in d.options}
    pick(s, bolt.id)
    d = until_asked(s)
    assert d is not None and d.player == "p2"
    pick(s, "yes" if yes else "no")
    settle(s)
    assert life(s, "p2") == (40 if yes else 37) and s.state.cards[meddler.id].damage == (3 if yes else 0)
    roundtrip(s)


# -- "target spell that targets …" ---------------------------------------------------------------------
def test_that_targets_wordings():
    from app.rules import selectors

    sel = selectors.parse("spell or ability that targets you or a creature you control")
    assert sel is not None and sel.ability == "spell_or_ability" and sel.extras[0].startswith("targets:you|")
    for refused in ("spell that targets only a single creature", "spell that targets a creature card in a graveyard"):
        assert selectors.parse(refused) is None


def test_rebuff_the_wicked_needs_a_permanent_bob_controls(cards):
    s = build(cards, p1=("Murder", "Lightning Bolt"), p2=("Rebuff the Wicked", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    rebuff = to_hand(s, "Rebuff the Wicked", "p2")
    mana(s, "p2", W=1)
    with pytest.raises(ActionError):  # (the Bolt targets Bob, not a permanent he controls)
        act(s, "p2", type="cast_spell", card_id=rebuff.id, targets=[bolt.id])
    settle(s)
    murder = alice_casts(s, "Murder", targets=[bears.id], B=2, C=1)
    act(s, "p2", type="cast_spell", card_id=rebuff.id, targets=[murder.id])
    settle(s)
    assert s.state.cards[murder.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield"
    roundtrip(s)


def test_rebuff_fizzles_if_the_permanent_left(cards):
    """The ruling: if the targeted permanent leaves the battlefield, the spell is no longer a legal target (608.2b)."""
    s = build(cards, p1=("Murder",), p2=("Rebuff the Wicked", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears", "p2")
    murder = alice_casts(s, "Murder", targets=[bears.id], B=2, C=1)
    rebuff = bob_answers(s, "Rebuff the Wicked", murder.id, W=1)
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "hand"})  # (by hand: the Bears leave)
    settle(s)
    assert s.state.cards[rebuff.id].zone == "p2:graveyard" and s.state.cards[murder.id].zone == "p1:graveyard"
    roundtrip(s)


def test_siren_stormtamer_counters_a_bolt_at_bob(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Siren Stormtamer",))
    siren = on_field(s, "Siren Stormtamer", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    mana(s, "p2", U=1)
    act(s, "p2", type="activate_ability", card_id=siren.id, ability=1, targets=[bolt.id])
    settle(s)
    assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:graveyard" and s.state.cards[siren.id].zone == "p2:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("at_bob", [True, False])
def test_reparations_draws_when_an_opponent_targets_bob(cards, at_bob):
    s = build(cards, p1=("Lightning Bolt",), p2=("Reparations",))
    on_field(s, "Reparations", "p2")
    hand_before = len(zone(s.state, "p2", "hand"))
    alice_casts(s, "Lightning Bolt", targets=["p2" if at_bob else "p1"], R=1)
    d = until_asked(s)
    if at_bob:
        assert d is not None and d.player == "p2"
        pick(s, "yes")
    else:
        assert d is None
    settle(s)
    assert len(zone(s.state, "p2", "hand")) == hand_before + (1 if at_bob else 0)
    roundtrip(s)


def test_mirror_sheen_copies_a_spell_that_targets_bob(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Mirror Sheen",))
    sheen = on_field(s, "Mirror Sheen", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    mana(s, "p2", U=2, C=1)
    act(s, "p2", type="activate_ability", card_id=sheen.id, ability=0, targets=[bolt.id])
    d = until_asked(s)
    assert d is not None and d.player == "p2"
    if d.kind == "choose_one" and "choose" in {o.id for o in d.options}:
        pick(s, "choose")
        d = until_asked(s)
    pick(s, "p1")
    settle(s)
    assert life(s, "p1") == 37 and life(s, "p2") == 37
    roundtrip(s)
