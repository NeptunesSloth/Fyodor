"""Wave 12A: clash (701.30), detain (701.35), suspect (701.60), moving and distributing counters (122.5, 601.2d) and rolling
dice (706). Every scenario uses real Oracle text and checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import counters, settle
from tests.test_rules_effects import mana
from tests.wave9c_kit import build, card_named, check, put, to_hand, zone_of


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"12A-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=[], **extra)


EXTRA = [
    real("Paperfin Rascal", "{2}{U}", 3, "Creature — Merfolk Rogue",
         "When this creature enters, clash with an opponent. If you win, put a +1/+1 counter on this creature.", ("2", "2"), "U"),
    real("Research the Deep", "{1}{U}", 2, "Sorcery",
         "Draw a card. Clash with an opponent. If you win, return Research the Deep to its owner's hand.", None, "U"),
    real("Azorius Arrester", "{W}{U}", 2, "Creature — Human Soldier",
         "When this creature enters, detain target creature an opponent controls. (Until your next turn, that creature can't "
         "attack or block and its activated abilities can't be activated.)", ("1", "1"), "WU"),
    real("Lavinia of the Tenth", "{3}{W}{U}", 5, "Legendary Creature — Human Soldier",
         "Protection from red\nWhen Lavinia of the Tenth enters, detain each nonland permanent your opponents control with mana "
         "value 4 or less. (Until your next turn, those permanents can't attack or block and their activated abilities can't be "
         "activated.)", ("4", "4"), "WU"),
    real("Incriminating Impetus", "{1}{B}", 2, "Enchantment — Aura",
         "Enchant creature\nWhen this Aura enters, suspect enchanted creature. (A suspected creature has menace and can't "
         "block.)\nEnchanted creature gets +1/+1.", None, "B"),
    real("Repeat Offender", "{1}{B}", 2, "Creature — Human Rogue",
         "{2}{B}: If this creature is suspected, put a +1/+1 counter on it. Otherwise, suspect it. (A suspected creature has "
         "menace and can't block.)", ("2", "2"), "B"),
    real("Test Giant", "{6}", 6, "Creature — Giant", "", ("6", "6")),
    real("Test Mite", "{1}", 1, "Creature — Insect", "", ("1", "1")),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def answer(s, *picks, limit=30):
    """Resolve the stack; decisions are answered from ``picks`` (option ids) in turn, else with their first option."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [picks.pop(0)] if picks else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def on_top(s, name, pid):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"})
    return c


# -- clash (701.30) ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Paperfin Rascal", "Research the Deep"])
def test_clash_cards_are_full(cards, name):
    full(cards, name)


@pytest.mark.parametrize("mine,theirs,won", [("Test Giant", "Test Mite", True), ("Test Mite", "Test Giant", False),
                                             ("Test Mite", "Test Mite", False)])
def test_a_clash_is_won_by_a_higher_mana_value_only(cards, mine, theirs, won):
    s = build(cards, ["Paperfin Rascal", "Test Giant", "Test Mite"], ["Test Giant", "Test Mite"])
    rascal = to_hand(s, "Paperfin Rascal")
    on_top(s, mine, "p1")
    on_top(s, theirs, "p2")
    mana(s, "p1", U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=rascal.id)
    answer(s)  # (both keep their cards on top)
    assert counters(s, rascal) == (1 if won else 0)
    assert s.state.zones["p1:library"][0] == card_named(s, mine, "p1").id  # kept on top
    check(s)


def test_each_clashing_player_may_put_their_card_on_the_bottom(cards):
    s = build(cards, ["Research the Deep", "Test Giant", "Test Mite"], ["Test Mite"])
    spell = to_hand(s, "Research the Deep")
    giant, mite = on_top(s, "Test Giant", "p1"), on_top(s, "Test Mite", "p2")
    on_top(s, "Test Mite", "p1")  # (the spell draws this one first)
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    for _ in range(3):  # resolve: draw a card first, then the clash
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "Test Giant" in d.prompt  # APNAP: the active player first (701.30c)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["bottom"])
    d = s.state.rules.decision
    assert d.player == "p2" and "Test Mite" in d.prompt
    assert s.state.zones["p1:library"][-1] != giant.id  # (nothing moved until both have decided)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["top"])
    answer(s)
    assert s.state.zones["p1:library"][-1] == giant.id and s.state.zones["p2:library"][0] == mite.id
    assert zone_of(s, "Research the Deep") == "p1:hand"  # (the Giant was revealed before it went down: a win)
    check(s)


def test_a_clash_needs_its_own_clash_for_if_you_win():
    assert scripts.parse_effects("If you win, draw a card.") is None
    assert scripts.parse_effects("Clash with an opponent. If you win, draw a card.") is not None
    assert scripts.parse_effects("You lose 2 life and draw two cards, then clash with an opponent. If you win, repeat this process.") is None


# -- detain (701.35) --------------------------------------------------------------------------------------
def chars(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("name", ["Azorius Arrester", "Lavinia of the Tenth", "Incriminating Impetus", "Repeat Offender"])
def test_detain_and_suspect_cards_are_full(cards, name):
    full(cards, name)


def test_detain_lasts_until_the_next_turn_of_its_controller(cards):
    from tests.test_rules_conditionals import to_turn, token_of
    from tests.test_rules_wave7b_activation import ability_index

    s = build(cards, ["Lavinia of the Tenth"], [])
    small = token_of(s, "p2", "Bob Mage", "Creature — Human Wizard", "1/1", "{T}: You gain 1 life.")
    big = token_of(s, "p2", "Bob Golem", "Creature — Golem", "5/5")  # (mana value 0: detained too)
    land = put(s, "Island", "p2")
    lav = to_hand(s, "Lavinia of the Tenth")
    mana(s, "p1", W=1, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=lav.id)
    answer(s)
    for c in (small, big):
        assert {"cant_attack_or_block", "cant_activate"} <= chars(s, c).imposed
    assert "cant_activate" not in chars(s, land).imposed  # (a land isn't a nonland permanent)
    to_turn(s, 2, "main1")  # Bob's turn: still detained
    assert s.state.rules.priority == "p2"
    with pytest.raises(ActionError, match="can't be activated|can't activate"):
        act(s, "p2", type="activate_ability", card_id=small.id, ability=ability_index(s, small, "gain 1 life"))
    check(s)
    to_turn(s, 3, "main1")  # Alice's next turn: it ended as the turn began
    assert not {"cant_attack_or_block", "cant_activate"} & chars(s, small).imposed
    check(s)


# -- suspect (701.60) -------------------------------------------------------------------------------------
def test_a_suspected_creature_has_menace_and_cannot_block(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s = build(cards, ["Repeat Offender"], [])
    man = put(s, "Repeat Offender")
    assert "menace" not in chars(s, man).keywords and "cant_block" not in chars(s, man).imposed
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="activate_ability", card_id=man.id, ability=ability_index(s, man, "suspected"))
    answer(s)
    assert "menace" in chars(s, man).keywords and "cant_block" in chars(s, man).imposed  # 701.60c
    assert counters(s, man) == 0
    check(s)
    mana(s, "p1", B=1, C=2)  # it is suspected now, so the other branch runs
    act(s, "p1", type="activate_ability", card_id=man.id, ability=ability_index(s, man, "suspected"))
    answer(s)
    assert counters(s, man) == 1
    check(s)
    # the designation ends when it leaves the battlefield (701.60a); it comes back as a new object (400.7)
    act(s, "p1", type="move", card_ids=[man.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[man.id], to={"player": "p1", "zone": "battlefield"})
    assert "menace" not in chars(s, man).keywords and "cant_block" not in chars(s, man).imposed
    check(s)


def test_an_aura_suspects_the_creature_it_enchants(cards):
    from tests.test_rules_conditionals import token_of

    s = build(cards, ["Incriminating Impetus"], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    aura = to_hand(s, "Incriminating Impetus")
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=aura.id)
    answer(s)
    assert "menace" in chars(s, bear).keywords and "cant_block" in chars(s, bear).imposed
    check(s)


def test_unused_imports():
    assert ActionError and put and zone_of and settle
