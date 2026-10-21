"""Wave 4C: "[effect] unless [a player] pays [cost]" (CR 118.12a), app/rules/unless_pays.py over
app/rules/optional_payment.py.

118.12a: "[Do something] unless [a player does something else]" means "[A player may do something
else]. If [that player doesn't], [do something]." The payer — the target spell's controller, the
player who cast the spell that triggered the ability, or you — decides privately; PAY is offered only
while they can pay all of it (118.3); the cost may be sized as it resolves (107.3a X, 608.2h);
"If they do" reads whether they chose to pay (118.12); "If that spell is countered this way, exile it
instead …" modifies the counter (608.2c). "You may draw a card unless that player pays {1}" asks the
payer first, then the controller (118.12a, 608.2c; 603.5: the "you may" is a choice made on
resolution). Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_attachments import ch
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

# Real Oracle wording (the local card database, current), one line per card.
EXTRA = [
    card("Rhystic Study", set_code="tst", number="X401", mana_cost="{2}{U}", cmc=3.0, type_line="Enchantment",
         oracle_text="Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
         colors=["U"], color_identity=["U"]),
    card("Mystic Remora", set_code="tst", number="X402", mana_cost="{U}", cmc=1.0, type_line="Enchantment",
         oracle_text="Cumulative upkeep {1} (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice "
                     "it unless you pay its upkeep cost for each age counter on it.)\nWhenever an opponent casts a noncreature "
                     "spell, you may draw a card unless that player pays {4}.",
         colors=["U"], color_identity=["U"], keywords=["Cumulative upkeep"]),
    card("Syncopate", set_code="tst", number="X403", mana_cost="{X}{U}", cmc=1.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {X}. If that spell is countered this way, exile it instead "
                     "of putting it into its owner's graveyard.", colors=["U"], color_identity=["U"]),
    card("No More Lies", set_code="tst", number="X404", mana_cost="{W}{U}", cmc=2.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {3}. If that spell is countered this way, exile it instead "
                     "of putting it into its owner's graveyard.", colors=["U", "W"], color_identity=["U", "W"]),
    card("Don't Make a Sound", set_code="tst", number="X405", mana_cost="{1}{U}", cmc=2.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {2}. If they do, surveil 2. (Look at the top two cards of "
                     "your library, then put any number of them into your graveyard and the rest on top of your library in any "
                     "order.)", colors=["U"], color_identity=["U"], keywords=["Surveil"]),
    card("Circular Logic", set_code="tst", number="X406", mana_cost="{2}{U}", cmc=3.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {1} for each card in your graveyard.\nMadness {U} (If you "
                     "discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your "
                     "graveyard.)", colors=["U"], color_identity=["U"], keywords=["Madness"]),
    card("Dazzling Denial", set_code="tst", number="X407", mana_cost="{1}{U}", cmc=2.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {2}. If you control a Bird, counter that spell unless its "
                     "controller pays {4} instead.", colors=["U"], color_identity=["U"]),
    card("Clash of Wills", set_code="tst", number="X408", mana_cost="{X}{U}", cmc=1.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {X}.", colors=["U"], color_identity=["U"]),
    card("Mausoleum Wanderer", set_code="tst", number="X409", mana_cost="{U}", cmc=1.0, type_line="Creature — Spirit",
         oracle_text="Flying\nWhenever another Spirit you control enters, this creature gets +1/+1 until end of turn.\nSacrifice "
                     "this creature: Counter target instant or sorcery spell unless its controller pays {X}, where X is this "
                     "creature's power.", power="1", toughness="1", colors=["U"], color_identity=["U"], keywords=["Flying"]),
    card("Nether Void", set_code="tst", number="X410", mana_cost="{3}{B}", cmc=4.0, type_line="World Enchantment",
         oracle_text="Whenever a player casts a spell, counter it unless that player pays {3}.", colors=["B"], color_identity=["B"]),
    card("Rethink", set_code="tst", number="X411", mana_cost="{2}{U}", cmc=3.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {X}, where X is its mana value.", colors=["U"],
         color_identity=["U"]),
    card("Spell Stutter", set_code="tst", number="X412", mana_cost="{1}{U}", cmc=2.0, type_line="Instant",
         oracle_text="Counter target spell unless its controller pays {2} plus an additional {1} for each Faerie you control.",
         colors=["U"], color_identity=["U"]),
    card("Esper Sentinel", set_code="tst", number="X413", mana_cost="{W}", cmc=1.0, type_line="Artifact Creature — Human Soldier",
         oracle_text="Whenever an opponent casts their first noncreature spell each turn, draw a card unless that player pays {X}, "
                     "where X is this creature's power.", power="1", toughness="1", colors=["W"], color_identity=["W"]),
]
COUNTERS = ("Syncopate", "No More Lies", "Don't Make a Sound", "Circular Logic", "Dazzling Denial", "Clash of Wills", "Rethink",
            "Spell Stutter")


@pytest.fixture()
def card_db(settings):
    """The fixture cards plus this module's real-Oracle cards."""
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
    return s


def roundtrip(s):
    replay_matches(s)  # (the recorded history rebuilds the same table)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)  # a save, loaded
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def hand(s, pid):
    return zone(s.state, pid, "hand")


# -- the wording ------------------------------------------------------------------------------------
def test_wordings():
    rhystic = scripts.parse_effects("You may draw a card unless that player pays {1}.", event_player=True)
    assert rhystic is not None and rhystic[2] is False  # (the "you may" is asked after the payment, not first)
    assert [e["do"] for e in rhystic[0]] == ["optional_payment", "only_if", "may_rest", "draw"]
    assert rhystic[0][0]["who"] == "event_player" and rhystic[0][1]["skip"] == 2
    x = scripts.parse_effects("Counter target spell unless its controller pays {X}.")
    assert x is not None and x[0][0] == {"do": "optional_payment", "who": "target", "cost": "", "bind": "pay0", "per": "{1}",
                                         "n": {"x": 1}, "cost_has_x": True}
    each = scripts.parse_effects("Counter target spell unless its controller pays {1} for each card in your graveyard.")
    assert each is not None and each[0][0]["per"] == "{1}" and "graveyard" in each[0][0]["n"]["count"]
    plus = scripts.parse_effects("Counter target spell unless its controller pays {2} plus an additional {1} for each Faerie you control.")
    assert plus is not None and plus[0][0]["cost"] == "{2}" and plus[0][0]["per"] == "{1}"
    mv = scripts.parse_effects("Counter target spell unless its controller pays {X}, where X is its mana value.")
    assert mv is not None and mv[0][0]["n"] == {"mana_value": "target"}
    exiled = scripts.parse_effects("Counter target spell unless its controller pays {3}. If that spell is countered this way, exile "
                                   "it instead of putting it into its owner's graveyard.")
    assert exiled is not None and exiled[0][-1] == {"do": "counter", "who": "target", "exile": True}
    they = scripts.parse_effects("Counter target spell unless its controller pays {2}. If they do, surveil 2.")
    assert they is not None and they[0][3] == {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": 1}
    energy = scripts.parse_effects("Sacrifice it unless you pay {E}{E}.", "self")
    assert energy is not None and energy[0][0]["cost"] == "Pay {E}{E}"


@pytest.mark.parametrize("text", [
    "Each opponent loses 2 life unless they pay {2}.",  # several payers (each in turn: not read here)
    "Counter target spell unless its controller pays {3} for each card discarded this way.",  # (an earlier choice's count)
    "Counter target spell unless its controller pays {B} or {3}.",  # a choice of costs
    "Counter target spell unless its controller pays {1} for each {E} paid this way.",
])
def test_refused(text):
    assert scripts.parse_effects(text, event_player=True) is None


def test_a_triggered_ability_has_no_x():
    """107.3: X is chosen as a spell is cast or an ability activated; a trigger that doesn't define it stays manual."""
    def line_supported(cost):
        fake = card(f"Fake Study {cost}", set_code="tst", number="X499", mana_cost="{U}", cmc=1.0, type_line="Enchantment",
                    oracle_text=f"Whenever an opponent casts a spell, draw a card unless that player pays {cost}.")
        return next(f.supported for f in coverage.of_card_data({**fake, "faces": []}).features if f.id == "text:0")

    assert line_supported("{1}") and not line_supported("{X}")


@pytest.mark.parametrize("name", ["Rhystic Study", "Mystic Remora", "Nether Void", "Mausoleum Wanderer", "Esper Sentinel", *COUNTERS])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_first_kind_wordings():
    from app.rules import events

    sentinel = events.parse_condition("an opponent casts their first noncreature spell each turn")
    assert sentinel is not None and sentinel["first_kind"] and "not_types" in sentinel["spell"]
    either = events.parse_condition("you cast your first instant or sorcery spell each turn")
    assert either is not None and either["first_kind"]
    # (wave 22E: the kinds the marks can't answer are read from the turn's cast log instead: types, subtypes, colors, mana value …)
    for noted in ("a player casts their first multicolored spell each turn", "you cast your first Human creature spell each turn",
                  "you cast your first noncreature, nonland spell each turn"):
        found = events.parse_condition(noted)
        assert found is not None and found["first_note"] and "first_kind" not in found
    assert events.parse_condition("you cast your first spell with flying each turn") is None  # (keywords aren't recorded)


# -- Esper Sentinel: the first noncreature spell of each opponent each turn --------------------------------
def test_esper_sentinel(cards):
    s = build(cards, p1=("Esper Sentinel",), p2=("Giant Growth", "Grizzly Bears", "Lightning Bolt"))
    on_field(s, "Esper Sentinel")
    to_turn(s, 2)
    bears = to_hand(s, "Grizzly Bears", "p2")
    mana(s, "p2", G=2)
    act(s, "p2", type="cast_spell", card_id=bears.id)
    assert until_asked(s) is None  # (a creature spell)
    settle(s)
    growth = to_hand(s, "Giant Growth", "p2")
    mana(s, "p2", G=1, C=1)
    before = len(hand(s, "p1"))
    act(s, "p2", type="cast_spell", card_id=growth.id, targets=[bears.id])
    d = until_asked(s)
    assert d.player == "p2" and "{1}" in d.options[0].label  # (X: its power, 1)
    roundtrip(s)
    pick(s, "decline")
    settle(s)
    assert len(hand(s, "p1")) == before + 1  # (no "may": Alice draws)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1, C=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    assert until_asked(s) is None  # (his second noncreature spell this turn)
    settle(s)
    assert len(hand(s, "p1")) == before + 1
    roundtrip(s)


def test_esper_sentinel_counts_spells_cast_before_it_was_there(cards):
    s = build(cards, p1=("Esper Sentinel",), p2=("Giant Growth", "Lightning Bolt"))
    to_turn(s, 2)
    bear = creature(s, "p2", "Bear")
    growth = to_hand(s, "Giant Growth", "p2")
    mana(s, "p2", G=1)
    act(s, "p2", type="cast_spell", card_id=growth.id, targets=[bear.id])
    settle(s)
    on_field(s, "Esper Sentinel")
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1, C=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    assert until_asked(s) is None  # (not his first noncreature spell this turn)
    settle(s)
    roundtrip(s)


def test_first_enchantment_spell_each_turn(cards):
    """Tuvasa the Sunlit: "Whenever you cast your first enchantment spell each turn, draw a card." — the second one doesn't."""
    s = build(cards, p1=("Rhystic Study", "Mystic Remora"))
    creature(s, "p1", "Tuvasa", text="Whenever you cast your first enchantment spell each turn, draw a card.")
    study, remora = to_hand(s, "Rhystic Study"), to_hand(s, "Mystic Remora")
    mana(s, U=4, C=2)
    before = len(hand(s, "p1"))
    act(s, "p1", type="cast_spell", card_id=study.id)
    settle(s)
    assert len(hand(s, "p1")) == before  # (one card cast, one drawn)
    act(s, "p1", type="cast_spell", card_id=remora.id)
    settle(s)
    assert len(hand(s, "p1")) == before - 1
    roundtrip(s)


# -- Rhystic Study / Mystic Remora: the caster decides, then you --------------------------------------------
def bob_casts_growth(s, *, pay_mana=0):
    to_turn(s, 2)
    growth = to_hand(s, "Giant Growth", "p2")
    bear = creature(s, "p2", "Bear")
    mana(s, "p2", G=1)
    if pay_mana:
        mana(s, "p2", C=pay_mana)
    act(s, "p2", type="cast_spell", card_id=growth.id, targets=[bear.id])
    return growth


@pytest.mark.parametrize("answer", ["pay", "decline-yes", "decline-no"])
def test_rhystic_study(cards, answer):
    s = build(cards, p1=("Rhystic Study",), p2=("Giant Growth",))
    on_field(s, "Rhystic Study")
    bob_casts_growth(s, pay_mana=1)
    before = len(hand(s, "p1"))
    d = until_asked(s)
    assert d.player == "p2" and [o.id for o in d.options] == ["pay", "decline"]  # (Bob first: 118.12a)
    assert "options" not in s.view("p1")["rules"]["decision"]  # (his choice, privately)
    roundtrip(s)
    pick(s, "pay" if answer == "pay" else "decline")
    if answer == "pay":
        assert until_asked(s) is None or s.state.rules.decision.player != "p1"
        assert s.state.players["p2"].mana.get("C", 0) == 0 and len(hand(s, "p1")) == before
    else:
        d = until_asked(s)
        assert d.player == "p1" and d.kind == "confirm"  # (then Alice: "you may draw a card")
        pick(s, "yes" if answer == "decline-yes" else "no")
        assert len(hand(s, "p1")) == before + (1 if answer == "decline-yes" else 0)
        assert s.state.players["p2"].mana.get("C", 0) == 1
    settle(s)
    roundtrip(s)


def test_rhystic_study_an_opponent_who_cant_pay_isnt_asked(cards):
    """118.3: Bob has no mana left: PAY isn't offered — Alice is asked whether she draws."""
    s = build(cards, p1=("Rhystic Study",), p2=("Giant Growth",))
    on_field(s, "Rhystic Study")
    bob_casts_growth(s)
    d = until_asked(s)
    assert d.player == "p1" and d.kind == "confirm"
    before = len(hand(s, "p1"))
    pick(s, "yes")
    assert len(hand(s, "p1")) == before + 1
    roundtrip(s)


def test_mystic_remora_only_noncreature_spells_and_four(cards):
    s = build(cards, p1=("Mystic Remora",), p2=("Giant Growth", "Grizzly Bears"))
    on_field(s, "Mystic Remora")
    to_turn(s, 2)
    bears = to_hand(s, "Grizzly Bears", "p2")
    mana(s, "p2", G=2)
    act(s, "p2", type="cast_spell", card_id=bears.id)
    assert until_asked(s) is None  # (a creature spell: no trigger)
    growth = to_hand(s, "Giant Growth", "p2")
    mana(s, "p2", G=1, C=3)
    act(s, "p2", type="cast_spell", card_id=growth.id, targets=[bears.id])
    d = until_asked(s)
    assert d.player == "p1" and d.kind == "confirm"  # (Bob has only {3} for {4}: he can't pay)
    pick(s, "no")
    settle(s)
    roundtrip(s)


# -- counterspells: Alice's Lightning Bolt, Bob's answer -------------------------------------------------
def bolt_then(cards, answer, *, bob_mana, x=None, p1=(), extra_p2=(), alice_c=0):
    s = build(cards, p1=("Lightning Bolt", *p1), p2=(answer, *extra_p2))
    bolt = to_hand(s, "Lightning Bolt")
    counter = to_hand(s, answer, "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", **bob_mana)
    mana(s, R=1, **({"C": alice_c} if alice_c else {}))  # (what Alice has left to pay with)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    kw = {"x_value": x} if x is not None else {}
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[bolt.id], **kw)
    return s, bolt


def alice_asked(s):
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]
    return d


@pytest.mark.parametrize("paid", [True, False])
def test_syncopate_x_and_exile(cards, paid):
    s, bolt = bolt_then(cards, "Syncopate", bob_mana={"U": 1, "C": 2}, x=2, alice_c=2)
    d = alice_asked(s)
    assert "{2}" in d.options[0].label  # (the X it was cast with, 107.3a)
    roundtrip(s)
    pick(s, "pay" if paid else "decline")
    settle(s)
    if paid:
        assert life(s, "p2") == 37 and s.state.cards[bolt.id].zone == "p1:graveyard" and s.state.players["p1"].mana == {}
    else:  # (countered this way: exiled instead, 608.2c)
        assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:exile"
    roundtrip(s)


def test_clash_of_wills_x_zero_costs_nothing(cards):
    """X = 0: Alice "pays {0}" — the spell isn't countered if she chooses to."""
    s, bolt = bolt_then(cards, "Clash of Wills", bob_mana={"U": 1}, x=0)
    d = alice_asked(s)
    assert "{0}" in d.options[0].label
    pick(s, "pay")
    settle(s)
    assert life(s, "p2") == 37
    roundtrip(s)


def test_no_more_lies_alice_cant_pay(cards):
    """118.3: Alice has no mana for {3}: nothing is asked, the Bolt is countered and exiled."""
    s, bolt = bolt_then(cards, "No More Lies", bob_mana={"W": 1, "U": 1})
    settle(s)
    assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("paid", [True, False])
def test_dont_make_a_sound_surveils_if_they_pay(cards, paid):
    s, bolt = bolt_then(cards, "Don't Make a Sound", bob_mana={"U": 1, "C": 1}, alice_c=2)
    alice_asked(s)
    pick(s, "pay" if paid else "decline")
    d = until_asked(s)
    if paid:  # (118.12: Alice chose to pay — Bob surveils 2)
        assert d is not None and d.player == "p2"
    settle(s)
    assert (life(s, "p2") == 37) == paid
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    roundtrip(s)


def test_circular_logic_counts_bobs_graveyard(cards):
    s, bolt = bolt_then(cards, "Circular Logic", bob_mana={"U": 1, "C": 2})
    # (608.2h: counted as it resolves — Bob's graveyard is empty: {0}, which Alice can pay; she's still asked)
    d = alice_asked(s)
    assert "{0}" in d.options[0].label
    pick(s, "decline")
    settle(s)
    assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:graveyard"
    roundtrip(s)


def test_circular_logic_with_cards_in_the_graveyard(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Circular Logic",))
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:3]
    act(s, "p2", type="move", card_ids=islands, to={"zone": "graveyard"})
    bolt = to_hand(s, "Lightning Bolt")
    logic = to_hand(s, "Circular Logic", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", U=1, C=2)
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=logic.id, targets=[bolt.id])
    d = alice_asked(s)
    assert "{3}" in d.options[0].label
    pick(s, "pay")
    settle(s)
    assert life(s, "p2") == 37 and s.state.players["p1"].mana.get("C", 0) == 0
    roundtrip(s)


@pytest.mark.parametrize("bird", [True, False])
def test_dazzling_denial_four_with_a_bird(cards, bird):
    s = build(cards, p1=("Lightning Bolt",), p2=("Dazzling Denial",))
    if bird:
        creature(s, "p2", "Owl", type_line="Token Creature — Bird")
    bolt = to_hand(s, "Lightning Bolt")
    denial = to_hand(s, "Dazzling Denial", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", U=1, C=1)
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=denial.id, targets=[bolt.id])
    d = alice_asked(s)
    assert ("{4}" if bird else "{2}") in d.options[0].label
    pick(s, "pay")
    settle(s)
    assert life(s, "p2") == 37 and s.state.players["p1"].mana.get("C", 0) == (0 if bird else 2)
    roundtrip(s)


def test_rethink_its_mana_value(cards):
    s = build(cards, p1=("Grizzly Bears",), p2=("Rethink",))
    bears = to_hand(s, "Grizzly Bears")
    rethink = to_hand(s, "Rethink", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", U=1, C=2)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=rethink.id, targets=[bears.id])
    settle(s)  # (Alice has nothing left for {2}: 118.3)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    roundtrip(s)


def test_mausoleum_wanderer_reads_its_power_as_it_last_existed(cards):
    """Sacrificed as the cost: X is its power as it last existed on the battlefield (608.2h) — 1."""
    s = build(cards, p1=("Lightning Bolt",), p2=("Mausoleum Wanderer",))
    wanderer = on_field(s, "Mausoleum Wanderer", "p2")
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=wanderer.id, ability=2, targets=[bolt.id])
    d = alice_asked(s)
    assert "{1}" in d.options[0].label
    pick(s, "pay")
    settle(s)
    assert life(s, "p2") == 37 and s.state.cards[wanderer.id].zone == "p2:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("paid", [True, False])
def test_nether_void_the_caster_pays(cards, paid):
    s = build(cards, p1=("Nether Void",), p2=("Giant Growth",))
    on_field(s, "Nether Void")
    growth = bob_casts_growth(s, pay_mana=3 if paid else 0)
    bear = next(c for c in s.state.cards.values() if c.name == "Bear")
    d = until_asked(s)
    if paid:  # (Bob, who cast it, decides; he can't when he has no mana: 118.3)
        assert d.player == "p2" and [o.id for o in d.options] == ["pay", "decline"]
        pick(s, "pay")
    else:
        assert d is None
        assert ch(s, bear).pt[0] == 2  # (countered as the trigger resolved)
    settle(s)
    assert s.state.cards[growth.id].zone == "p2:graveyard"
    assert ch(s, bear).pt[0] == (5 if paid else 2) and s.state.players["p2"].mana.get("C", 0) == 0
    roundtrip(s)
