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
from tests.test_rules_keywords3f import REAL as FACE_DOWN_CARDS
from tests.test_rules_keywords3f import build as build3, ch, hidden_from, named
from tests.test_rules_keywords3f import mana as mana3
from tests.test_rules_keywords3f import to_hand as to_hand3
from tests.test_rules_wave6c_tokens_pumps import build, mana, reloaded, to_hand, token_of

EXTRA = [
    card('Demon Bolt', set_code='tst', number='Y00', mana_cost='{2}{R}', cmc=3.0, type_line='Instant', oracle_text='Demon Bolt deals 4 damage to target creature or planeswalker.\nForetell {R} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=['Foretell']),  # noqa: E501
    card('Break Open', set_code='tst', number='Y02', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text='Turn target face-down creature an opponent controls face up.', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Wall of Deceit', set_code='tst', number='Y03', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Wall', oracle_text="Defender (This creature can't attack.)\n{3}: Turn this creature face down.\nMorph {U} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)", power='0', toughness='5', colors=['U'], color_identity=['U'], keywords=['Morph', 'Defender']),  # noqa: E501
    card('Skirk Alarmist', set_code='tst', number='Y04', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Wizard', oracle_text='Haste\n{T}: Turn target face-down creature you control face up. At the beginning of the next end step, sacrifice it.', power='1', toughness='2', colors=['R'], color_identity=['R'], keywords=['Haste']),  # noqa: E501
    card('Backslide', set_code='tst', number='Y05', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Turn target creature with a morph ability face down.\nCycling {U}', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=['Cycling']),  # noqa: E501
    card('Doomskar', set_code='tst', number='Y01', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Sorcery', oracle_text='Destroy all creatures.\nForetell {1}{W}{W} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=['Foretell']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]
HERMIT = [c for c in FACE_DOWN_CARDS if c["name"] == "Thelonite Hermit"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *HERMIT], settings.cards_db_path, meta={"bulk_type": "test"})
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


def test_break_open_turns_an_opponents_face_down_creature_up_and_it_triggers(cards):
    s = build3(cards, "Break Open", bob=("Thelonite Hermit",), players=2)
    act(s, "p1", type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")  # Bob's turn
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    hermit = to_hand3(s, "Thelonite Hermit", "p2")
    mana3(s, "p2", C=3)
    act(s, "p2", type="cast_spell", card_id=hermit.id, face_down=True)
    settle(s)
    assert s.state.cards[hermit.id].face_down and s.state.cards[hermit.id].zone == "p2:battlefield"
    for viewer in ("p1", SPECTATOR):  # 708.5: only its controller may look at it
        assert hidden_from(s, viewer, hermit)
    assert not hidden_from(s, "p2", hermit)
    brk = to_hand3(s, "Break Open", "p1")
    act(s, "p2", type="pass_priority")  # (Alice gets priority in Bob's main phase)
    mana3(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=brk.id, targets=[hermit.id])
    settle(s)
    assert not s.state.cards[hermit.id].face_down and ch(s, hermit).name == "Thelonite Hermit"
    assert "Thelonite Hermit" in blob(s, "p1")  # now face up: public
    assert sum(1 for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p2:battlefield") == 4  # 702.37e: turned face up
    check(s)


def test_turn_face_down_then_up_with_the_morph_cost(cards):
    s = build(cards, "Wall of Deceit")
    wall = to_hand(s, "Wall of Deceit")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    settle(s)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=1)  # {3}: Turn this creature face down.
    settle(s)
    c = s.state.cards[wall.id]
    assert c.face_down and c.face_down_kind == "generic"
    assert hidden_from_session(s, "p2", wall)
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=1) if False else None
    mana(s, U=1)
    act(s, "p1", type="turn_face_up", card_id=wall.id)  # 702.37e: its morph cost {U}
    assert not s.state.cards[wall.id].face_down
    check(s)


def hidden_from_session(s, pid, c):
    """The card's own entry in the view (a log line may keep naming it: it was face up and public when it was turned over)."""
    entry = json.dumps(s.view(pid)["cards"].get(c.id, {}))
    return c.name not in entry and c.card_id not in entry


def test_backslide_turns_a_creature_with_a_morph_ability_face_down(cards):
    s = build(cards, "Wall of Deceit", "Backslide")
    wall = to_hand(s, "Wall of Deceit")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    settle(s)
    slide = to_hand(s, "Backslide")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=slide.id, targets=[wall.id])
    settle(s)
    assert s.state.cards[wall.id].face_down and hidden_from_session(s, "p2", wall)
    check(s)
