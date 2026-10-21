"""CR 122.1b, 613.7c, 702.83, 702.147: keyword counters grant each complete ability."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_wave34b_activated import attack, next_turn, stops, to_phase
from tests.wave9c_kit import pt


@pytest.fixture()
def cards(settings):
    base = {c["name"]:c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "decayed_grants_cards.json").read_text())):
        base[c["name"]] = card(c["name"], set_code="tkc", number=str(i), **{k:v for k,v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_gisa_returns_only_linked_cards_and_the_decayed_grant_survives_her_departure(cards):
    assert coverage.of_card_data(cards.resolve("Gisa, Glorious Resurrector")).level == "FULL"
    s = build(cards, ["Gisa, Glorious Resurrector", "Lightning Bolt", "Grizzly Bears", "Swords to Plowshares"], bob=((1, "Grizzly Bears"), (1, "Akrasan Squire"), (10, "Island")))
    gisa = put(s, "Gisa, Glorious Resurrector", "hand")
    own = put(s, "Grizzly Bears", "graveyard")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 2})
    act(s, "p1", type="cast_spell", card_id=gisa.id)
    settle(s)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Lightning Bolt", "hand").id, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:exile"
    unrelated = put(s, "Akrasan Squire", "battlefield", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Swords to Plowshares", "hand").id, targets=[unrelated.id])
    settle(s)
    roundtrip(s)
    next_turn(s)
    assert s.state.cards[unrelated.id].zone == "p2:exile"
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    assert s.state.cards[own.id].zone == "p1:graveyard"
    assert "decayed" in Plan(s.state, "p1", cards, None).ch(s.state.cards[victim.id]).keywords
    act(s, "p1", type="move", card_ids=[gisa.id], to={"player": "p1", "zone": "hand"})
    next_turn(s)
    stops(s)
    roundtrip(s)
    attack(s, victim)
    settle(s)
    to_phase(s, "end_combat")
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard"
    roundtrip(s)

def test_gisa_new_object_does_not_return_cards_linked_to_her_previous_object(cards):
    assert coverage.of_card_data(cards.resolve("Gisa, Glorious Resurrector")).level == "FULL"
    s = build(cards, ["Gisa, Glorious Resurrector", "Lightning Bolt"], bob=((1, "Grizzly Bears"), (10, "Island")))
    gisa = put(s, "Gisa, Glorious Resurrector", "hand")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 2})
    act(s, "p1", type="cast_spell", card_id=gisa.id)
    settle(s)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Lightning Bolt", "hand").id, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:exile"
    act(s, "p1", type="move", card_ids=[gisa.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 2})
    act(s, "p1", type="cast_spell", card_id=gisa.id)
    settle(s)
    next_turn(s)
    assert s.state.cards[victim.id].zone == "p2:exile"
    roundtrip(s)

def test_unbound_plural_decayed_grant_stays_unsupported():
    from app.rules import scripts

    assert scripts.parse_effects("They gain decayed.") is None


@pytest.mark.parametrize("spell,mana,zone", [("Lightning Bolt", {"R": 1}, "graveyard"), ("Swords to Plowshares", {"W": 1}, "exile")])
def test_skullbriar_retains_keyword_counter_abilities_in_other_public_zones(cards, spell, mana, zone):
    s = build(cards, ["Skullbriar, the Walking Grave", spell])
    skull = put(s, "Skullbriar, the Walking Grave", "battlefield")
    for kind in ("flying", "exalted", "decayed"):
        act(s, "p1", type="counter", card_ids=[skull.id], kind=kind, delta=1)
    act(s, "p1", type="add_mana", player="p1", mana=mana)
    act(s, "p1", type="cast_spell", card_id=put(s, spell, "hand").id, targets=[skull.id])
    settle(s)
    assert s.state.cards[skull.id].zone == f"p1:{zone}"
    assert all(s.state.cards[skull.id].counters.get(kind) == 1 for kind in ("flying", "exalted", "decayed"))
    assert {"flying", "exalted", "decayed"} <= Plan(s.state, "p1", cards, None).ch(s.state.cards[skull.id]).keywords
    roundtrip(s)

def test_retained_exalted_does_not_trigger_from_the_graveyard_and_counters_clear_in_hand(cards):
    s = build(cards, ["Skullbriar, the Walking Grave", "Lightning Bolt", "Raise Dead", "Grizzly Bears"])
    skull = put(s, "Skullbriar, the Walking Grave", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    next_turn(s)
    act(s, "p1", type="counter", card_ids=[skull.id], kind="exalted", delta=1)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Lightning Bolt", "hand").id, targets=[skull.id])
    settle(s)
    assert "exalted" in Plan(s.state, "p1", cards, None).ch(s.state.cards[skull.id]).keywords
    stops(s)
    attack(s, bear)
    settle(s)
    assert pt(s, "Grizzly Bears") == (2, 2)
    to_phase(s, "main2")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Raise Dead", "hand").id, targets=[skull.id])
    settle(s)
    assert s.state.cards[skull.id].zone == "p1:hand" and not s.state.cards[skull.id].counters
    assert "exalted" not in Plan(s.state, "p1", cards, None).ch(s.state.cards[skull.id]).keywords
    roundtrip(s)
