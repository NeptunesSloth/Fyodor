"""-- playtest (nov 18) -- Terrasymbiosis ("Whenever you put one or more +1/+1 counters on a creature you control, you may draw that
many cards. Do this only once each turn."): 603.2h — each placement triggers it until the draw has been taken this turn; a later instance
that turn (one that triggered alongside the first) does nothing and asks nothing; declining leaves the draw open; the question names the number."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable

TERRA = ("Whenever you put one or more +1/+1 counters on a creature you control, you may draw that many cards. "
         "Do this only once each turn.")


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    base["Terrasymbiosis"] = card("Terrasymbiosis", set_code="tsy", number="1", type_line="Enchantment", mana_cost="{2}{G}",
                                  oracle_text=TERRA)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def _table(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Terrasymbiosis"), (2, "Grizzly Bears"), (20, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    on = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name in ("Terrasymbiosis", "Grizzly Bears")]
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="move", card_ids=on, to={"zone": "battlefield"})
    bears = [c.id for c in s.state.cards.values() if c.name == "Grizzly Bears"]
    return s, bears


def _hand(s):
    return sum(1 for c in s.state.cards.values() if c.zone == "p1:hand")


def _until_asked(s):
    """Pass priority until a decision is asked or the stack is empty."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None or not s.state.zones.get("stack"):
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("stack never emptied")


def _pump(s, target, n):
    """A {0} ability that puts n +1/+1 counters on target creature: the engine's counter event (a manual counter doesn't trigger)."""
    words = {1: "a +1/+1 counter", 2: "two +1/+1 counters", 3: "three +1/+1 counters"}[n]
    act(s, "p1", type="create_token", player="p1", token={"name": f"Pump{n}", "type_line": "Token Artifact", "text": f"{{0}}: Put {words} on target creature you control."})
    pump = next(c for c in s.state.cards.values() if c.name == f"Pump{n}")
    act(s, "p1", type="activate_ability", card_id=pump.id, ability=0)
    d = s.state.rules.decision
    if d is not None and d.kind == "choose_one":
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == target)])
    act(s, "p1", type="pass_priority")  # (both pass: the pump resolves, Terrasymbiosis triggers)


def _two_triggers(s):
    """One event putting counters on both Bears (a {0} ability: "two +1/+1 counters on each creature you control"): it triggers for each
    (the ruling: one trigger per creature), both triggers on the stack together; the first question."""
    act(s, "p1", type="create_token", player="p1", token={"name": "Pumpall", "type_line": "Token Artifact",
                                                           "text": "{0}: Put two +1/+1 counters on each creature you control."})
    pump = next(c for c in s.state.cards.values() if c.name == "Pumpall")
    act(s, "p1", type="activate_ability", card_id=pump.id, ability=0)
    act(s, "p1", type="pass_priority")
    d = _until_asked(s)
    while d is not None and d.kind != "confirm":  # (the order of the two triggers, 603.3b)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min or 1)] if d.kind != "order_triggers" else [o.id for o in d.options])
        d = _until_asked(s)
    return d


def test_the_question_names_the_number(cards):
    s, bears = _table(cards)
    _pump(s, bears[0], 3)
    d = _until_asked(s)
    assert d is not None and d.kind == "confirm" and d.prompt == "Terrasymbiosis: Draw 3 card(s)?"
    hand = _hand(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    assert _hand(s) == hand + 3


def test_after_drawing_a_later_trigger_that_turn_asks_nothing(cards):
    s, bears = _table(cards)
    _pump(s, bears[0], 3)
    d = _until_asked(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    hand = _hand(s)
    _pump(s, bears[1], 2)
    d = _until_asked(s)
    assert d is None  # it didn't trigger: the draw was taken this turn (603.2h)
    assert _hand(s) == hand


def test_two_at_once_draw_once_and_the_second_asks_nothing(cards):
    s, bears = _table(cards)
    d = _two_triggers(s)
    assert d is not None and d.prompt == "Terrasymbiosis: Draw 2 card(s)?"
    assert len(s.state.zones["stack"]) == 2  # (this one, resolving, and the other under it)
    hand = _hand(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    assert _until_asked(s) is None  # the second resolves without a question: the draw was taken this turn (603.2h)
    assert _hand(s) == hand + 2
    assert any("already done this turn" in (p.t or "") for e in s.state.log[-6:] for p in e.parts)


def test_declining_the_first_leaves_the_draw_for_the_second(cards):
    s, bears = _table(cards)
    d = _two_triggers(s)
    hand = _hand(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    d = _until_asked(s)
    assert d is not None and d.prompt == "Terrasymbiosis: Draw 2 card(s)?"  # the limit is on drawing, not on triggering
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    assert _until_asked(s) is None and _hand(s) == hand + 2
