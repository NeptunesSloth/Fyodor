"""Wave 22C: "reveal ~ and shuffle it into its owner's library instead" vs "exile instead" (CR 614.1a, 614.6, 616.1).

Real Oracle text (tests/fixtures/wave22c_cards.json, from data/cards.sqlite). The 616.1 choice is tried both ways: a wrong
order would be silent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.state import zone_key
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_replacements2 import permanent, reload
from tests.test_rules_wave5j_token_copies import drive, game, mana, put, roundtrip

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave22c_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t22c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def zone_of(s, c):
    """Where the card is now (by name: a card entering a library gets a new opaque id)."""
    return next(x.zone for x in s.state.cards.values() if x.name == c.name and not x.is_token and x.owner == c.owner)


def graveyard(s, pid="p1"):
    return s.state.zones.get(zone_key(pid, "graveyard"), [])


def sacrifice(s):
    """A permanent whose ability makes its controller sacrifice a creature (Blightsteel is the only one)."""
    t = permanent(s, "p1", "Sacrificer", "Enchantment", "{1}: Sacrifice a creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0)


def order_question(pick):
    return lambda d: [pick] if d.resume.get("step") == "zone_replace_order" else None


def test_blightsteel_is_shuffled_into_its_owners_library_not_put_into_the_graveyard(cards):
    s = game(cards, ["Blightsteel Colossus"])
    blight = put(s, "Blightsteel Colossus")
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature dies, you gain 1 life.")
    before = len(s.state.zones[zone_key("p1", "library")])
    sacrifice(s)
    drive(s)
    assert zone_of(s, blight) == "p1:library" and len(s.state.zones[zone_key("p1", "library")]) == before + 1
    assert not graveyard(s) and s.state.players["p1"].life == 40  # (614.6: it never died)
    roundtrip(s)


@pytest.mark.parametrize("pick, where", [("exile", "p1:exile"), ("library:shuffle", "p1:library")])
def test_blightsteel_with_rest_in_peace_the_controller_chooses_616_1_both_orders(cards, pick, where):
    s = game(cards, ["Blightsteel Colossus"], bob=["Rest in Peace"])
    blight = put(s, "Blightsteel Colossus")
    put(s, "Rest in Peace", pid="p2")
    sacrifice(s)
    drive(s, order_question(pick))
    assert zone_of(s, blight) == where and not graveyard(s)
    roundtrip(s)


def test_the_616_1_question_is_the_controllers_survives_reload_and_changes_nothing_until_answered(cards):
    s = game(cards, ["Blightsteel Colossus"], bob=["Rest in Peace"])
    blight = put(s, "Blightsteel Colossus")
    put(s, "Rest in Peace", pid="p2")
    sacrifice(s)
    d = s.state.rules.decision
    for _ in range(5):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.resume["step"] == "zone_replace_order"
    assert {o.id for o in d.options} == {"exile", "library:shuffle"} and zone_of(s, blight) == "p1:battlefield"
    other = s.view("p2")["rules"]["decision"]
    assert not other or not other.get("options")
    s2 = reload(s, cards)
    act(s2, "p1", type="choose", decision_id=d.id, option_ids=["library:shuffle"])
    assert zone_of(s2, blight) == "p1:library"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["exile"])
    assert zone_of(s, blight) == "p1:exile" and s.state.rules.decision is None
    replay_matches(s)


@pytest.mark.parametrize("pick, where", [("library:shuffle", "p1:library"), ("exile", "p1:exile")])
def test_nexus_of_fate_resolves_and_is_shuffled_in_or_exiled_by_choice(cards, pick, where):
    s = game(cards, ["Nexus of Fate"], bob=["Rest in Peace"])
    put(s, "Rest in Peace", pid="p2")
    nexus = put(s, "Nexus of Fate", "hand")
    mana(s, U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=nexus.id)
    drive(s, order_question(pick))
    assert zone_of(s, nexus) == where
    replay_matches(s)


def test_nexus_of_fate_alone_is_shuffled_in_without_a_question(cards):
    s = game(cards, ["Nexus of Fate"])
    nexus = put(s, "Nexus of Fate", "hand")
    mana(s, U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=nexus.id)
    drive(s)
    assert zone_of(s, nexus) == "p1:library" and s.state.rules.decision is None
    roundtrip(s)


def test_a_milled_blightsteel_is_shuffled_back_instead(cards):
    s = game(cards, ["Blightsteel Colossus"])
    blight = put(s, "Blightsteel Colossus", "library")
    act(s, "p1", type="move", card_ids=[blight.id], to={"player": "p1", "zone": "library"}, position="top")
    miller = permanent(s, "p1", "Miller", "Enchantment", "{1}: Target player mills a card.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=miller.id, ability=0, targets=["p1"])
    drive(s)
    assert zone_of(s, blight) == "p1:library" and not graveyard(s)
    roundtrip(s)
