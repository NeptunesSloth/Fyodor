"""Wave 18A: hidden exile and face-down objects (CR 2026-09-25), real Oracle text.

* Foretell 702.143: the special action (any time you have priority during your turn: pay {2}, exile the card from your hand
  face down), casting it for its foretell cost after the turn has ended, and who may look at it.
Every scenario checks the replay and a save/load round trip; the privacy checks build each player's and a spectator's view.
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, mana, put, reloaded, to_hand, token_of

EXTRA = [
    card('Demon Bolt', set_code='tst', number='Y00', mana_cost='{2}{R}', cmc=3.0, type_line='Instant', oracle_text='Demon Bolt deals 4 damage to target creature or planeswalker.\nForetell {R} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=['Foretell']),  # noqa: E501
    card('Doomskar', set_code='tst', number='Y01', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Sorcery', oracle_text='Destroy all creatures.\nForetell {1}{W}{W} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=['Foretell']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def to_own_turn(s, n):
    until(s, lambda s: s.state.turn.number >= n and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")


def blob(s, pid):
    return json.dumps(s.view(pid))


def test_foretell_then_cast_for_the_foretell_cost_on_a_later_turn(cards):
    s = build(cards, "Demon Bolt")
    bolt = to_hand(s, "Demon Bolt")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)  # the foretell special action (702.143b)
    assert s.state.cards[bolt.id].zone == "p1:foretell"
    # 702.143a: its owner alone may look at it; nobody else's view (or a spectator's) names it
    for viewer in ("p2", SPECTATOR):
        assert "Demon Bolt" not in blob(s, viewer) and bolt.card_id not in blob(s, viewer)
    assert "Demon Bolt" in blob(s, "p1")
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # 702.143a: not the turn it was foretold
    to_own_turn(s, 3)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # for {R}, not {2}{R}
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and bear.id not in s.state.zones["p2:battlefield"]
    assert bolt.id not in s.state.rules.foretold
    check(s)


def test_foretold_card_costs_its_foretell_cost_only(cards):
    s = build(cards, "Doomskar")
    doom = to_hand(s, "Doomskar")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=doom.id, ability=1)
    to_own_turn(s, 3)
    mana(s, W=2)  # {1}{W}{W} needs three mana
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=doom.id)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=doom.id)
    settle(s)
    assert s.state.cards[doom.id].zone == "p1:graveyard"
    check(s)


def test_foretell_only_during_your_turn(cards):
    s = build(cards, "Demon Bolt")
    bolt = to_hand(s, "Demon Bolt")
    mana(s, C=2)
    until(s, lambda s: s.state.turn.active_player == "p2")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)
