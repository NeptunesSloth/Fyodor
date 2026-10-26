"""Wave 110C: Cosima, God of the Voyage // The Omenkeel. 603.5 (may exile), 611.2a/400.7 (the granted trigger lasts while it stays exiled), 603.4 (intervening if),
122.1/122.6 (voyage counters, +1/+1 counters on return), 510.2 (Vehicle damage), 305.1 (play lands from exile), 701.13 (exile from the top)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real
from tests.wave110d_kit import ability

COSIMA = ('At the beginning of your upkeep, you may exile Cosima. If you do, it gains "Whenever a land you control enters, if Cosima is exiled, you may put a voyage '
          'counter on it. If you don\'t, return Cosima to the battlefield with X +1/+1 counters on it and draw X cards, where X is the number of voyage counters on it."')
OMEN = ("Whenever a Vehicle you control deals combat damage to a player, that player exiles that many cards from the top of their library. You may play lands from "
        "among those cards for as long as they remain exiled.\nCrew 1")
FACES = [{"object": "card_face", "name": "Cosima, God of the Voyage", "mana_cost": "{2}{U}", "type_line": "Legendary Creature — God", "oracle_text": COSIMA,
          "power": "2", "toughness": "4", "colors": ["U"]},
         {"object": "card_face", "name": "The Omenkeel", "mana_cost": "{1}{U}", "type_line": "Legendary Artifact — Vehicle", "oracle_text": OMEN,
          "power": "3", "toughness": "3", "colors": ["U"]}]
NAME = "Cosima, God of the Voyage // The Omenkeel"
EXTRA = [card(NAME, set_code="tst", number="C1", layout="modal_dfc", mana_cost=None, cmc=3.0, type_line="Legendary Creature — God // Legendary Artifact — Vehicle",
              colors=["U"], color_identity=["U"], image_uris=None, card_faces=FACES),
         real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def cosima_exiled(cards):
    s = build(cards, [NAME], [], forests=30, islands=30)
    c = put(s, "Cosima, God of the Voyage // The Omenkeel")
    to_phase(s, "upkeep", 3)
    answer(s, "yes")  # (603.5: the "may")
    assert s.state.cards[c.id].zone == "p1:exile"
    return s, c


def play_land(s):
    land = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:hand")
    act(s, "p1", type="play_land", card_id=land.id)


def test_declining_the_upkeep_exile_keeps_her_on_the_battlefield(cards):
    s = build(cards, [NAME], [], forests=30, islands=30)
    c = put(s, "Cosima, God of the Voyage // The Omenkeel")
    to_phase(s, "upkeep", 3)
    answer(s, "no")
    assert s.state.cards[c.id].zone == "p1:battlefield"
    check(s)


def test_voyage_counters_then_return_with_that_many_counters_and_cards(cards):
    s, c = cosima_exiled(cards)
    to_phase(s, "main1", 3)
    play_land(s)
    answer(s, "yes")
    assert s.state.cards[c.id].counters.get("voyage") == 1
    to_phase(s, "main1", 5)
    play_land(s)
    answer(s, "yes")
    assert s.state.cards[c.id].counters.get("voyage") == 2
    to_phase(s, "main1", 7)
    hand = len(s.state.zones["p1:hand"])
    play_land(s)
    answer(s, "no")
    back = s.state.cards[c.id]
    assert back.zone == "p1:battlefield" and back.counters.get("+1/+1") == 2 and back.counters.get("voyage", 0) == 0
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2  # (the land played, two cards drawn)
    check(s)


def test_exiled_by_something_else_does_not_ask(cards):
    s = build(cards, [NAME], [], forests=30, islands=30)
    c = put(s, "Cosima, God of the Voyage // The Omenkeel")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "exile"})
    to_phase(s, "main1", 3)
    play_land(s)
    assert s.state.rules.decision is None and s.state.cards[c.id].zone == "p1:exile" and not s.state.cards[c.id].counters.get("voyage")
    check(s)


def test_omenkeel_exiles_that_many_and_lets_you_play_the_lands(cards):
    s = build(cards, [NAME, "Test Bear"], [], forests=30, islands=30)
    vehicle = put(s, NAME)
    s.state.cards[vehicle.id].zone  # noqa: B018
    mana(s, U=1, C=1)
    act(s, "p1", type="move", card_ids=[vehicle.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=vehicle.id, face=1)
    answer(s)
    crew = put(s, "Test Bear")
    to_phase(s, "main1", 3)
    act(s, "p1", type="activate_ability", card_id=vehicle.id, ability=ability(s, vehicle, "Crew"), crew=[crew.id])
    answer(s)
    to_phase(s, "declare_attackers", 3)
    top = list(s.state.zones["p2:library"][:3])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": vehicle.id, "target": "p2"}])
    for _ in range(30):
        if all(s.state.cards[c].zone == "p2:exile" for c in top):
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert all(s.state.cards[c].zone == "p2:exile" for c in top)  # (3 damage: 3 cards)
    assert s.state.turn.number == 3 and s.state.players["p2"].life == 37
    to_phase(s, "main2", 3)
    land = next(c for c in top if s.state.cards[c].name == "Island")  # (p2's deck: Islands)
    act(s, "p1", type="play_land", card_id=land)
    assert s.state.cards[land].zone == "p1:battlefield"
    check(s)
