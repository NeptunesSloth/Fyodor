"""Wave 7A: "Cast this spell only …" timing sentences (601.3), researched against CR 2026-09-25.

* Steps and combat moments (Teleport, Blood Frenzy, Festival), "only if you've been attacked this step" (Heavy Fog:
  a creature attacking you, 506.3), "only if you control fewer creatures than each opponent" (Even the Odds).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, mana, reloaded, to_hand

EXTRA = [
    card('Teleport', set_code='tst', number='E01', mana_cost='{U}{U}{U}', cmc=3.0, type_line='Instant', oracle_text="Cast this spell only during the declare attackers step.\nTarget creature can't be blocked this turn.", colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Heavy Fog', set_code='tst', number='E02', mana_cost='{1}{G}', cmc=2.0, type_line='Instant', oracle_text="Cast this spell only during the declare attackers step and only if you've been attacked this step.\nPrevent all damage that would be dealt to you this turn by attacking creatures.", colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Hewed Stone Retainers', set_code='tst', number='E05', mana_cost='{3}', cmc=3.0, type_line='Artifact Creature — Golem', oracle_text="Cast this spell only if you've cast another spell this turn.", power='4', toughness='4', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Grim Wanderer', set_code='tst', number='E04', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Goblin Warlock', oracle_text='Flash\nTragic Backstory — Cast this spell only if a creature died this turn.', power='5', toughness='3', colors=['B'], color_identity=['B'], keywords=['Flash']),  # noqa: E501
    card('Even the Odds', set_code='tst', number='E03', mana_cost='{2}{W}', cmc=3.0, type_line='Instant', oracle_text='Cast this spell only if you control fewer creatures than each opponent.\nCreate three 1/1 white Soldier creature tokens.', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_the_timing_cards_are_full():
    from tests.test_rules_scripts import ch

    for c in EXTRA:
        chs = ch(c["name"], c["type_line"], c["oracle_text"])
        assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


def test_unknown_timing_stays_manual():
    from app.rules import cast_timing

    assert cast_timing.definition("Cast this spell only during the second main phase of your turn if the moon is full.") is None
    assert cast_timing.definition("Cast this spell only once each turn.") is None


def test_teleport_only_in_the_declare_attackers_step(cards):
    s = build(cards, "Teleport")
    act(s, "p1", type="set_prefs", full_control=True)
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2", "Haste")
    tele = to_hand(s, "Teleport")
    mana(s, U=3)
    with pytest.raises(ActionError, match="declare attackers step"):
        act(s, "p1", type="cast_spell", card_id=tele.id, targets=[bear.id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    assert s.state.turn.phase == "declare_attackers" and s.state.rules.priority == "p1"
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=tele.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[tele.id].zone == "p1:graveyard"
    replay_matches(reloaded(s))


def test_heavy_fog_needs_a_creature_attacking_you(cards):
    s = build(cards, "Heavy Fog")
    act(s, "p1", type="set_prefs", full_control=True)
    fog = to_hand(s, "Heavy Fog")
    token_of(s, "p2", "Raider", "Token Creature — Bear", "2/2", "Haste")
    mana(s, G=1, C=1)
    with pytest.raises(ActionError, match="declare attackers step"):
        act(s, "p1", type="cast_spell", card_id=fog.id)
    # p2's turn: the Raider attacks p1
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    raider = next(c for c in s.state.cards.values() if c.name == "Raider")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": raider.id, "target": "p1"}])
    until(s, lambda s: s.state.rules.priority == "p1" and s.state.turn.phase == "declare_attackers")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=fog.id)
    settle(s)
    assert s.state.cards[fog.id].zone == "p1:graveyard"
    replay_matches(reloaded(s))


def test_even_the_odds_needs_fewer_creatures_than_each_opponent(cards):
    s = build(cards, "Even the Odds")
    eto = to_hand(s, "Even the Odds")
    mana(s, W=1, C=2)
    with pytest.raises(ActionError, match="fewer creatures"):
        act(s, "p1", type="cast_spell", card_id=eto.id)
    token_of(s, "p2", "Opp Bear", "Token Creature — Bear", "2/2")
    act(s, "p1", type="cast_spell", card_id=eto.id)
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Soldier" and c.owner == "p1") == 3
    replay_matches(reloaded(s))


def test_hewed_stone_retainers_needs_another_spell_first(cards):
    s = build(cards, "Hewed Stone Retainers", "Lightning Bolt")
    retainers = to_hand(s, "Hewed Stone Retainers")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1, C=3)
    with pytest.raises(ActionError, match="cast another spell"):
        act(s, "p1", type="cast_spell", card_id=retainers.id)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=retainers.id)
    settle(s)
    assert s.state.cards[retainers.id].zone == "p1:battlefield"
    replay_matches(reloaded(s))
