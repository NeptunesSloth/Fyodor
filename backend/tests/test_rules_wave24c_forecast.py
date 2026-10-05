"""Wave 24C: forecast (CR 702.57) — "Forecast — {W}, Reveal this card from your hand: Target creature gets +1/+1 until end of turn." (Steeling Stance).

* 702.57a: a forecast ability is an activated ability of a card in its owner's hand that can be activated only during its controller's upkeep and
  only once each turn; revealing the card is part of its cost (701.20a: shown to everyone as the cost is paid, and not for longer: the card stays in
  the hand, nobody keeps seeing it).
* 113.6m: the ability functions only from the hand.

Every scenario uses real Oracle text (tests/fixtures/wave24c_forecast_cards.json, from data/cards.sqlite) and checks that replaying the recorded
history reproduces the table and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand, token_of
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_wave7b_activation import ability_index

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24c_forecast_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24p", number=f"P{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def check(s):
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def to_upkeep(s, number=3):
    """Alice's upkeep of her turn ``number`` with priority (she asks the engine to stop there)."""
    act(s, "p1", type="set_prefs", stops_my_turn=["upkeep"])
    for _ in range(300):
        t = s.state.turn
        if t.number == number and t.active_player == "p1" and t.phase == "upkeep" and s.state.rules.priority == "p1" and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the upkeep")


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def test_forecast_works_from_the_hand_in_your_upkeep_once_each_turn(cards):
    s = build(cards, "Steeling Stance")
    bear = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    stance = to_hand(s, "Steeling Stance")
    idx = ability_index(s, stance, "Forecast")
    mana(s, "p1", W=1)
    with pytest.raises(ActionError, match="upkeep"):  # (not your upkeep: it's your main phase)
        act(s, "p1", type="activate_ability", card_id=stance.id, ability=idx, targets=[bear.id], target_counts=[1])
    to_upkeep(s)
    mana(s, "p1", W=1)
    act(s, "p1", type="activate_ability", card_id=stance.id, ability=idx, targets=[bear.id], target_counts=[1])
    assert s.state.cards[stance.id].zone == "p1:hand" and not s.state.cards[stance.id].revealed_to  # revealed as a cost, hidden again
    assert any("revealed" in str(e) for e in s.state.log[-6:])
    settle(s)
    assert ch(s, bear).pt == (3, 3)
    mana(s, "p1", W=1)
    with pytest.raises(ActionError):  # 702.57a: only once each turn
        act(s, "p1", type="activate_ability", card_id=stance.id, ability=idx, targets=[bear.id], target_counts=[1])
    check(s)


def test_the_spell_itself_is_not_the_forecast_ability(cards):
    s = build(cards, "Steeling Stance")
    bear = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    stance = to_hand(s, "Steeling Stance")
    mana(s, "p1", W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=stance.id)  # the sorcery: creatures you control get +1/+1
    settle(s)
    assert ch(s, bear).pt == (3, 3)
    check(s)
