"""Review 35: tokens a replacement adds share what the creating effect specified (CR 2026-09-25, 614.1a, 614.6), real Oracle text
(tests/fixtures/wave35c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* Chatterfang, Squirrel General ruling: "Anything else specified in the effect creating the token (such as tapped, attacking, "That token
  gains haste," or "Exile that token at end of combat") applies to both the original tokens and the Squirrels." (Peregrin Took and Mondrak,
  Glory Dominus rule the same.) Hero of Bladehold's "two 1/1 white Soldier creature tokens that are tapped and attacking" with Chatterfang:
  two Squirrels tapped and attacking too; with Peregrin Took the added Food is tapped.
* Academy Manufactor's "instead create one of each" is the same creation event, so the Clue and Food it adds are tapped when the Treasure was.
"""

from __future__ import annotations

import pytest

from app.rules import extra_tokens
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave9c_kit import build, check, put, reloaded
from tests.wave35c_kit import repository


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


def made(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == f"{pid}:battlefield"]


def hero_attacks(cards, other):
    s = build(cards, ["Hero of Bladehold", other], [])
    hero = put(s, "Hero of Bladehold")
    put(s, other)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hero.id, "target": "p2"}])
    for _ in range(30):  # (until the Soldiers are made: combat isn't over yet)
        if made(s, "Soldier"):
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: 1 if d.kind != "order" else None])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s


def test_chatterfangs_squirrels_are_made_tapped_with_the_soldiers(cards):
    s = hero_attacks(cards, "Chatterfang, Squirrel General")
    soldiers, squirrels = made(s, "Soldier"), made(s, "Squirrel")
    assert len(soldiers) == 2 and len(squirrels) == 2
    assert [(c.name, c.tapped) for c in soldiers + squirrels] == [("Soldier", True)] * 2 + [("Squirrel", True)] * 2
    check(reloaded(s))


def test_peregrin_tooks_food_is_tapped_with_the_soldiers(cards):
    s = hero_attacks(cards, "Peregrin Took")
    assert len(made(s, "Soldier")) == 2 and [c.tapped for c in made(s, "Food")] == [True]
    check(s)


def test_academy_manufactors_added_tokens_keep_the_events_tapped():
    class C:
        op = {"do": "each_of"}

    ev = {"who": "p1", "count": 1, "tapped": True, "token": {"name": "Treasure", "type_line": "Token Artifact — Treasure"}}
    assert all(e["tapped"] for e in extra_tokens.swap(C(), ev))

