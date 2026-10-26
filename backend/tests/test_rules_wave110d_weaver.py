"""Wave 110D: Shelob, Dread Weaver, real Oracle text (tests/fixtures/wave110d_cards.json).

* 607.2a: the creatures the dies trigger exiled are linked to it; the cost "Put a creature card exiled with Shelob into its owner's graveyard" pays
  with one of them (602.2b), then +2 counters and a card.
* 107.3a: {X}{1}{B} announces X first; only a linked creature card with mana value X is a legal target; it returns tapped under your control.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build, mana
from tests.wave110d_kit import ability, card_db, check, full, now, put_new, settle, to_phase  # noqa: F401

NAME = "Shelob, Dread Weaver"
GIANT = "Bonecrusher Giant // Stomp"


def _scene(cards):
    s = build(cards, [NAME, "Ambush Viper", "Ambush Viper", "Grizzly Bears"], ["Grizzly Bears", GIANT])
    shelob = put_new(s, NAME)
    vipers = [put_new(s, "Ambush Viper"), put_new(s, "Ambush Viper")]  # deathtouch
    bears, giant = put_new(s, "Grizzly Bears", "p2"), put_new(s, GIANT, "p2")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": v.id, "target": "p2"} for v in vipers])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": v.id} for b, v in zip((bears, giant), vipers, strict=True)])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase in ("main2", "end") and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, shelob, bears, giant


def test_weaver_is_full():
    assert full(NAME)


def test_x_returns_only_the_creature_with_that_value(cards):
    s, shelob, bears, giant = _scene(cards)
    assert now(s, bears).zone == now(s, giant).zone == "p2:exile"  # exiled with Shelob, not put into the graveyard
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="activate_ability", card_id=shelob.id, ability=ability(s, shelob, "{X}{1}{B}"), x_value=2, sources=[])
    d = s.state.rules.decision
    while d is not None and {o.id for o in d.options} & {bears.id, giant.id} == set():
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {bears.id}  # mana value 2; the Giant (3) is not a legal target
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    back = now(s, bears)
    assert back.zone == "p1:battlefield" and back.tapped and back.controller == "p1"
    check(s)


def test_cost_puts_a_linked_creature_into_its_owners_graveyard(cards):
    s, shelob, bears, giant = _scene(cards)
    mana(s, "p1", B=1, C=2)
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    act(s, "p1", type="activate_ability", card_id=shelob.id, ability=ability(s, shelob, "{2}{B}, Put"), sources=[])
    d = s.state.rules.decision
    while d is not None and {o.id for o in d.options} & {bears.id, giant.id} == set():
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
    settle(s)
    assert now(s, giant).zone == "p2:graveyard" and now(s, bears).zone == "p2:exile"
    assert now(s, shelob).counters.get("+1/+1") == 2 and len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 1
    check(s)


def test_nothing_exiled_cannot_pay(cards):
    s = build(cards, [NAME])
    shelob = put_new(s, NAME)
    to_phase(s, "main1", turn=3)
    mana(s, "p1", B=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=shelob.id, ability=ability(s, shelob, "{2}{B}, Put"), sources=[])
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
