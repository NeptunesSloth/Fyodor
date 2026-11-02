"""The public choice wheel (docs/TABLETOP_QOL_MILESTONE.md): the chooser's view of a pending decision says ``public_choice`` when the
choice is among public values (a color, a type, a number, a player, heads or tails, a public option), so the client may offer its quick
radial picker. The flag is derived from the server-only ``resume`` step (app/rules/view.py ``public_choice``): no new state, nothing for
any other viewer, and never for a target, a cost, a secret choice or a choice about hidden cards. The answer is the same ``choose`` action."""

from __future__ import annotations

import pytest

from app.game.rules_state import Decision, DecisionOption
from app.game.session import GameSession
from app.rules.engine import RESUME
from app.rules.view import PUBLIC_CHOICE_STEPS, public_choice
from tests.game_helpers import act
from tests.test_rules_effects import build, mana, pass_until_stack_empty, replay_matches, token

COLORS = [DecisionOption(id=c, label=c) for c in ("White", "Blue", "Black", "Red", "Green")]


def decision(step: str | None, options=COLORS, **kw) -> Decision:
    fields = {"id": "d1", "player": "p1", "kind": "choose_one", "prompt": "Choose", "options": options,
              "resume": None if step is None else {"step": step, **kw.pop("resume", {})}}
    return Decision(**{**fields, **kw})


def activate(s, card):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0)
    pass_until_stack_empty(s)


def test_color_choice_is_flagged_for_its_chooser_only(cards):
    s = build(cards)
    prism = token(s, "p1", "Prism", "1/1", text="{1}: Choose a color.")
    activate(s, prism)
    mine = s.view("p1")["rules"]["decision"]
    assert mine["kind"] == "choose_one" and mine["public_choice"] is True
    assert [o["id"] for o in mine["options"]] == ["White", "Blue", "Black", "Red", "Green"]
    theirs = s.view("p2")["rules"]["decision"]
    assert "public_choice" not in theirs and "options" not in theirs and theirs["kind"] == "waiting"
    again = GameSession(s.history.rebuild(), cards=s.cards)  # a reload mid-decision: the same flag, nothing stored for it
    assert again.view("p1")["rules"]["decision"]["public_choice"] is True
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Red"])  # the wheel sends the list's own answer
    assert s.state.rules.decision is None
    replay_matches(s)


def test_player_choice_is_flagged_and_secret_one_is_not(cards):
    """"Choose a player" (choose_value) gets the flag; the same players chosen secretly (group_choice "gc_secret") don't."""
    s = build(cards)
    players = [DecisionOption(id="p1", label="Alice"), DecisionOption(id="p2", label="Bob")]
    s.state.rules.decision = decision("choose_value", players)
    assert s.view("p1")["rules"]["decision"]["public_choice"] is True
    s.state.rules.decision = decision("gc_secret", players)
    assert "public_choice" not in s.view("p1")["rules"]["decision"]


@pytest.mark.parametrize(("d", "expected"), [
    (decision("choose_value"), True),
    (decision("mana_ability", [DecisionOption(id="0", label="{G}"), DecisionOption(id="1", label="{U}")]), True),
    (decision("coin_group", [DecisionOption(id="0", label="Heads"), DecisionOption(id="1", label="Tails")], resume={"phase": "ignore"}), True),
    # which coin replacement applies next is a rules ordering, not a public value
    (decision("coin_group", [DecisionOption(id="a", label="Krark's Thumb"), DecisionOption(id="b", label="Edgar")], resume={"phase": "replace"}), False),
    # "secretly choose an opponent" / a secret bid: the answer is hidden until revealed
    (decision("gc_secret", [DecisionOption(id="p2", label="Bob"), DecisionOption(id="p3", label="Cara")]), False),
    (decision("gc_bid", [DecisionOption(id="__number__", label="Type a number ≥ 0", group="number")]), False),
    # a target, a search, a cost: not on the list of public steps
    (decision("trigger_target", [DecisionOption(id="p2", label="Bob"), DecisionOption(id="p1", label="Alice")]), False),
    (decision("search_zones"), False),
    (decision(None), False),
    # options that name cards (a copy's choice of creature) or are typed (a card name) keep the list
    (decision("choose_value", [DecisionOption(id="c1", label="Bear", card_id="c1"), DecisionOption(id="c2", label="Elf", card_id="c2")]), False),
    (decision("choose_value", [DecisionOption(id="__name__", label="Type a card name", group="card name")]), False),
    # several answers, a payment's presentation
    (decision("choose_value", kind="choose_cards"), False),
    (decision("choose_value", max_choices=2), False),
    (decision("mana_ability", display={"kind": "payment"}), False),
])
def test_public_choice(d, expected):
    assert public_choice(d) is expected


def test_every_public_step_is_a_real_resume_step():
    assert PUBLIC_CHOICE_STEPS.issubset(RESUME) and "coin_group" in RESUME
    assert not {"gc_secret", "gc_bid", "cast_target", "trigger_target", "cast_modes"} & PUBLIC_CHOICE_STEPS
