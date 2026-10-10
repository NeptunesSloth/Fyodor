"""Wave 28A: "You may play a land from the top of your library or cast a spell with mana value less than or equal to the damage dealt from the top of
your library without paying its mana cost. If you don't, put that card into your hand." (Ziatora's Envoy; CR 2026-09-25)

* 608.2g: a card looked at is played as the ability resolves; 305.2a-b: a land only with a land play left; "the damage dealt" limits the spell, not the land.
* 701.20: the card is looked at, not revealed: nobody else sees it, and whether a choice is offered mustn't tell them (a spell too big is asked all the same).
"""

from __future__ import annotations

import json

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import through_combat
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.wave9c_kit import build, card_named, put, reloaded

REAL = [
    card("Ziatora's Envoy", set_code="t28a", number="B1", mana_cost="{1}{B}{R}{G}", cmc=4.0, type_line="Creature — Lizard Warrior", colors=["B", "R", "G"],
         color_identity=["B", "R", "G"], power="5", toughness="4", keywords=["Trample", "Blitz"],
         oracle_text="Trample\nWhenever this creature deals combat damage to a player, look at the top card of your library. You may play a land from "
         "the top of your library or cast a spell with mana value less than or equal to the damage dealt from the top of your library without "
         "paying its mana cost. If you don't, put that card into your hand.\nBlitz {2}{B}{R}{G} (If you cast this spell for its blitz cost, it gains "
         "haste and \"When this creature dies, draw a card.\" Sacrifice it at the beginning of the next end step.)"),
    card("Craterhoof Probe", set_code="t28a", number="B2", mana_cost="{7}{G}", cmc=8.0, type_line="Creature — Beast", colors=["G"], color_identity=["G"],
         power="8", toughness="8", oracle_text=""),
    card("Grizzly Probe", set_code="t28a", number="B3", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Bear", colors=["G"], color_identity=["G"],
         power="2", toughness="2", oracle_text=""),
]
OURS = [c["name"] for c in REAL]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def decision(s):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    return d


def swing(s, top):
    """Alice attacks with the Envoy (5 damage, trample, no blockers) with ``top`` on her library; the trigger resolves to its choice."""
    envoy = put(s, "Ziatora's Envoy")
    s.state.rules.controlled_since[envoy.id].turn = 0
    card = card_named(s, top)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": envoy.id, "target": "p2"}])
    for _ in range(30):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_cards":
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return card


def test_coverage(cards):
    assert coverage.of_card_data(cards.resolve("Ziatora's Envoy")).level == "FULL"


def test_plays_the_land_on_top(cards):
    s = build(cards, OURS)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "library"}, position="top")
    envoy = put(s, "Ziatora's Envoy")
    s.state.rules.controlled_since[envoy.id].turn = 0
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": envoy.id, "target": "p2"}])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert [o.card_id for o in decision(s).options] == [forest.id]
    other = reloaded(s)  # (a save and a load, paused on the choice)
    assert decision(other).id == decision(s).id
    act(other, "p1", type="choose", decision_id=decision(other).id, option_ids=[forest.id])
    through_combat(other)
    assert other.state.cards[forest.id].zone == "p1:battlefield"
    assert other.state.rules.lands_this_turn("p1", other.state.turn.number) == 1
    assert other.state.rules.decision is None
    replay_matches(other)
    assert reloaded(other).state.model_dump(mode="json") == other.state.model_dump(mode="json")


def test_a_spell_over_the_damage_goes_to_hand_and_nothing_is_leaked(cards):
    s = build(cards, OURS)
    big = swing(s, "Craterhoof Probe")
    assert decision(s).options == []  # mana value 8 > 5: asked all the same (the other players can't tell why)
    for session in (s, reloaded(s)):  # looked at, not revealed: Bob learns nothing of it
        assert "Craterhoof" not in json.dumps(session.view("p2"), default=str)
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[])
    through_combat(s)
    assert s.state.cards[big.id].zone == "p1:hand"  # "If you don't, put that card into your hand."
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_a_spell_within_the_damage_is_cast_free(cards):
    s = build(cards, OURS)
    bear = swing(s, "Grizzly Probe")
    assert [o.card_id for o in decision(s).options] == [bear.id]
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[bear.id])
    pass_until_stack_empty(s)
    through_combat(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert s.state.players["p1"].mana == {}
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")
