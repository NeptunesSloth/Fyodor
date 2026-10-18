"""Wave 45C: a creature spell becomes a target; combat damage "is dealt to you" (CR 2026-09-25, real Oracle text, tests/fixtures/wave45c_cards.json).
Every scenario checks the replay and a save and a load.

* 115.1, 603.2e: "Whenever a creature you control or a creature spell you control becomes the target of a spell or ability an opponent controls" (Surrak): a
  creature on the battlefield or a creature spell on the stack; a spell or ability you control doesn't count.
* 120.1: "Whenever combat damage is dealt to you" (Risona) is "you're dealt combat damage": not noncombat damage, not damage to another player.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until
from tests.test_rules_wave38a_trailing_ifs import hand, table
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave36a_kit import attack_as, ready, resolve_stack, to_turn_of
from tests.wave45c_kit import hold, make_repo


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Surrak, Elusive Hunter", "Risona, Asari Commander"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_surrak_draws_when_an_opponent_targets_a_creature_you_control(cards):
    s = table(cards, ["Surrak, Elusive Hunter", "Grizzly Bears"], ["Lightning Bolt"])
    put(s, "Surrak, Elusive Hunter")
    bears = put(s, "Grizzly Bears")
    to_turn_of(s, "p2")
    to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    before = hand(s)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=[bears.id])
    resolve_stack(s)
    assert hand(s) == before + 1
    check(s)


def test_surrak_draws_when_an_opponent_targets_your_creature_spell(cards):
    s = table(cards, ["Surrak, Elusive Hunter", "Grizzly Bears"], ["Counterspell"])
    put(s, "Surrak, Elusive Hunter")
    spell = to_hand(s, "Grizzly Bears")
    to_hand(s, "Counterspell", "p2")
    hold(s)
    mana(s, G=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    act(s, "p1", type="pass_priority")  # (Bob responds)
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Counterspell", "p2").id, targets=[spell.id])
    settle(s)
    resolve_stack(s)
    assert hand(s) == before - 1 + 1  # (the Bears were cast and countered; Surrak's card was drawn)
    check(s)


def test_surrak_ignores_what_you_target_yourself_and_an_opponents_creature(cards):
    s = table(cards, ["Surrak, Elusive Hunter", "Grizzly Bears", "Giant Growth"], ["Grizzly Bears"])
    put(s, "Surrak, Elusive Hunter")
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Giant Growth")
    mana(s, G=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Giant Growth").id, targets=[mine.id])
    resolve_stack(s)
    assert hand(s) == before - 1  # (your own spell: no card)
    to_hand(s, "Giant Growth")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Giant Growth").id, targets=[theirs.id])
    resolve_stack(s)
    assert hand(s) == before - 1  # (an opponent's creature: no card)
    check(s)


def risona_table(cards):
    s = table(cards, ["Risona, Asari Commander", "Lightning Bolt"], ["Grizzly Bears"])
    risona = put(s, "Risona, Asari Commander")
    act(s, "p1", type="counter", card_ids=[risona.id], kind="indestructible", delta=1)
    return s, risona


def test_risona_loses_its_counter_when_combat_damage_is_dealt_to_you(cards):
    s, risona = risona_table(cards)
    theirs = put(s, "Grizzly Bears", "p2")
    to_turn_of(s, "p2")
    ready(s, "Grizzly Bears", pid="p2")
    attack_as(s, "p2", [theirs], "p1")
    until(s, lambda s: s.state.turn.phase == "end_combat")
    resolve_stack(s)
    assert s.state.players["p1"].life == 38
    assert s.state.cards[risona.id].counters.get("indestructible", 0) == 0
    check(s)


def test_risona_keeps_its_counter_for_noncombat_damage(cards):
    s, risona = risona_table(cards)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p1"])
    resolve_stack(s)
    assert s.state.players["p1"].life == 37
    assert s.state.cards[risona.id].counters.get("indestructible", 0) == 1
    check(s)
