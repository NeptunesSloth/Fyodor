"""Kept read passes (Plan.reading, read_pass.adopted): on a big table, read-only checks reuse what an earlier check derived, and only
while the table is exactly as it was. Every change must end the reuse: a table action (``Plan.do``) and a change made straight to the
rules state alike. A long REPEAT of a token maker plays out as it would one step at a time."""

from __future__ import annotations

import pytest

from app.game.rules_state import ContinuousEffect
from app.rules import read_pass
from app.rules.plan import READ_REUSE_FROM, Plan
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_permissions import build


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database(fixture_cards(), settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def big_table(cards):
    s = build(cards, [(10, "Forest")])
    act(s, "p1", type="create_token", player="p1", count=READ_REUSE_FROM, stacked=False,
        token={"name": "Insect", "type_line": "Token Artifact Creature — Insect", "power": "1", "toughness": "1", "colors": []})
    return s


def insect(plan):
    return next(c for c in plan.state.cards.values() if c.name == "Insect")


def toughness(plan, card):
    with plan.reading():
        return plan.ch(card).toughness


def test_a_table_action_ends_the_kept_pass(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug = insect(plan)
    assert toughness(plan, bug) == "1"
    with plan.reading() as first:
        pass
    with plan.reading() as again:
        assert again is first  # nothing changed: the same pass, its answers kept
    plan.do({"type": "set_life", "player": "p2", "value": 39})
    with plan.reading() as after:
        assert after is not first


def test_a_change_straight_to_the_rules_state_ends_the_kept_pass(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug = insect(plan)
    assert toughness(plan, bug) == "1"
    plan.rules.effects.append(ContinuousEffect(id="test-pump", affected=[plan.oid(bug)], layer="7c", controller="p1", power=2, toughness=2))
    with plan.reading():
        from app.rules import sba

        assert sba.toughness(bug, plan.ch(bug)) == 3  # read afresh: not the 1/1 the kept pass had derived


def test_a_reader_handed_only_the_table_uses_the_owning_plans_pass(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    with plan.reading() as kept:
        pass
    with read_pass.adopted(plan.state, plan.info) as sc:
        assert sc is kept


def test_a_small_table_keeps_nothing_between_checks(cards):
    s = build(cards, [(10, "Forest")])
    plan = Plan(s.state, "p1", s.cards, None)
    with plan.reading() as first:
        pass
    with plan.reading() as again:
        assert again is not first


def test_a_long_repeat_of_a_token_maker_matches_its_replay(cards):
    s = build(cards, [(10, "Forest")])
    act(s, "p1", type="create_token", player="p1", token={"name": "Hive", "type_line": "Token Artifact — Test",
                                                          "text": "{1}: Create a 1/1 colorless Insect artifact creature token.", "colors": []})
    hive = next(c for c in s.state.cards.values() if c.name == "Hive")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 61})
    act(s, "p1", type="activate_ability", card_id=hive.id, ability=0)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="repeat_sequence", count=1, times=60)
    assert sum(1 for c in s.state.cards.values() if c.name.startswith("Insect")) == 61
    replay_matches(s)
