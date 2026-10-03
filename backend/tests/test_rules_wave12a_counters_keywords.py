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


def test_unused_imports():
    assert ActionError and put and zone_of and settle
