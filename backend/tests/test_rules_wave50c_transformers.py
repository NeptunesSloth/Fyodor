"""Wave 50C: the Transformers (CR 2026-09-25), real Oracle text (tests/fixtures/wave50c_transformers.json, from data/cards.sqlite). Every scenario checks the replay
and a save and a load.

* 701.28a: to convert a permanent is to turn it over as transforming does (rulings 2022-10-14: "convert" and "transform" are the same action; a counter, an Aura, a
  continuous effect stay).
* 702.162a / 712.8c: "More Than Meets the Eye {cost}" - cast the card converted by paying that rather than its mana cost: the spell is the back face (its mana value
  is the front face's), and it enters with the back face up; an alternative cost, from any zone the card may be cast from.
* 702.161a: "Living metal" - during your turn the permanent is an artifact creature in addition to its other types.
* Starscream (a combat-damage-to-you trigger), Goldbug (the second spell each turn), Ratchet ("you may convert … When you do, return target artifact card with mana
  value less than or equal to the life you gained this turn").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import alt_costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50c_transformers.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50c", number=f"T{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SALVE = card("Healing Salve", set_code="w50c", number="P07", mana_cost="{W}", cmc=1.0, type_line="Instant", oracle_text="You gain 1 life.", colors=["W"],
             color_identity=["W"])
STARSCREAM, GOLDBUG, RATCHET = (c["name"] for c in DATA)


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, SALVE], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [STARSCREAM, GOLDBUG, RATCHET])
def test_the_transformers_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def types_of(s, name, pid="p1"):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])
    return ch.types | ch.subtypes


def converted_cast(cards):
    """Starscream is cast converted from the hand for {2}{B} (the printed cost is {3}{B})."""
    s = build(cards, [STARSCREAM], forests=30, islands=30)
    c = to_hand(s, STARSCREAM)
    offers = alt_costs.converted_offers(s.state, "p1", c, s.cards)
    assert [o.label for o in offers] == ["Starscream, Power Hungry: pay {2}{B} (converted)"]
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, alt_cost=offers[0].key)
    settle(s)
    return s, c


def test_more_than_meets_the_eye_casts_the_back_face_for_the_alternative_cost(cards):
    s, c = converted_cast(cards)
    now = s.state.cards[c.id]
    assert now.zone == "p1:battlefield" and now.face == 1  # the back face (Starscream, Seeker Leader) entered
    assert "Vehicle" in types_of(s, STARSCREAM) and "Creature" in types_of(s, STARSCREAM)  # living metal: on Alice's turn a creature
    assert Plan(s.state, "p1", s.cards, None).ch(now).mana_value == 4  # the front face's mana value, whichever face is up (712.8e)
    check(s)
    s = reloaded(s)
    assert s.state.cards[c.id].face == 1


def test_living_metal_makes_it_a_creature_on_your_turn_only(cards):
    s, c = converted_cast(cards)
    assert "Creature" in types_of(s, STARSCREAM)
    to_phase(s, "main1", turn=2)  # Bob's turn
    assert "Creature" not in types_of(s, STARSCREAM) and "Vehicle" in types_of(s, STARSCREAM)
    to_phase(s, "main1", turn=3)
    assert "Creature" in types_of(s, STARSCREAM)
    check(s)


def test_the_printed_cost_casts_the_front_face(cards):
    s = build(cards, [STARSCREAM], forests=30, islands=30)
    c = to_hand(s, STARSCREAM)
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].face == 0
    check(s)


def test_the_converted_cost_is_not_offered_from_the_battlefield_or_for_another_player(cards):
    s = build(cards, [STARSCREAM], forests=30, islands=30)
    c = put(s, STARSCREAM)
    assert alt_costs.converted_offers(s.state, "p1", c, s.cards) == []
    c2 = to_hand(s, STARSCREAM)
    assert alt_costs.converted_offers(s.state, "p2", c2, s.cards) == []


def test_starscream_converts_when_creatures_deal_combat_damage_to_you(cards):
    s = build(cards, [STARSCREAM], ["Grizzly Bears"], forests=30, islands=30)
    c = put(s, STARSCREAM)
    bears = put(s, "Grizzly Bears", "p2")
    stops(s)
    to_phase(s, "main1", turn=4)  # (the Bears have been there since Bob's turn began)
    attack_p2 = [bears]
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": b.id, "target": "p1"} for b in attack_p2])
    settle(s)
    to_phase(s, "end", turn=4)
    assert life(s) == 38 and s.state.cards[c.id].face == 1
    check(s)


def test_goldbug_converts_on_the_second_spell_each_turn_only(cards):
    s = build(cards, [GOLDBUG, "Lightning Bolt", "Lightning Bolt"], forests=30, islands=30)
    c = put(s, GOLDBUG)
    for _ in range(2):
        to_hand(s, "Lightning Bolt")
        mana(s, R=1)
        assert s.state.cards[c.id].face == 0
        act(s, "p1", type="cast_spell", card_id=[x for x in s.state.cards.values() if x.name == "Lightning Bolt" and x.zone == "p1:hand"][0].id, targets=["p2"])
        settle(s)
    assert s.state.cards[c.id].face == 1  # the second spell
    check(s)
    s = reloaded(s)
    assert s.state.cards[c.id].face == 1


def test_ratchet_converts_and_returns_an_artifact_with_value_up_to_the_life_gained(cards):
    s = build(cards, [RATCHET, "Healing Salve", "Sol Ring", "Arcane Signet"], forests=30, islands=30)
    c = put(s, RATCHET)
    ring, signet = (card_named(s, n) for n in ("Sol Ring", "Arcane Signet"))
    for x in (ring, signet):
        act(s, "p1", type="move", card_ids=[x.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Healing Salve")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Healing Salve").id)
    settle(s, "yes")  # you may convert: yes; then the target is the one legal artifact (mana value 1 or less)
    assert s.state.cards[c.id].face == 1
    assert s.state.cards[ring.id].zone == "p1:battlefield" and s.state.cards[ring.id].tapped
    assert s.state.cards[signet.id].zone == "p1:graveyard"  # mana value 2: more than the 1 life gained
    check(s)


def test_ratchet_may_decline_to_convert(cards):
    s = build(cards, [RATCHET, "Healing Salve", "Sol Ring"], forests=30, islands=30)
    c = put(s, RATCHET)
    ring = card_named(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[ring.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Healing Salve")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Healing Salve").id)
    settle(s, "no")
    assert s.state.cards[c.id].face == 0 and s.state.cards[ring.id].zone == "p1:graveyard"
    check(s)


def test_a_transformers_commander_is_cast_converted_from_the_command_zone(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, STARSCREAM, [(30, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    c = card_named(s, STARSCREAM)
    assert c.zone == "p1:command"
    offers = alt_costs.converted_offers(s.state, "p1", c, s.cards)
    assert len(offers) == 1
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, alt_cost=offers[0].key)
    settle(s)
    assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].face == 1
    check(s)
