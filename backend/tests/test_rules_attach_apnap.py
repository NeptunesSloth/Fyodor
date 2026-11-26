"""613.7e / 613.7m: Auras and Equipment that become attached at the same time get their new timestamps in APNAP order — the active player's
first, then each other player's in turn order — not in the order the table lists them. Open the Vaults returning each player's Aura onto the
same creature (303.4f: each enters attached), Frogify against Kenrith's Transformation (layer 7b: the later base power and toughness wins,
613.7), on either player's turn. Real Oracle text (Scryfall); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.rules import coverage, layers
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

EXTRA = [
    real("Open the Vaults", "{4}{W}{W}", 6, "Sorcery", "Return all artifact and enchantment cards from all graveyards to the battlefield under "
         "their owners' control. (Auras with nothing to enchant remain in graveyards.)", None, "W"),
    real("Frogify", "{1}{U}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature loses all abilities and is a blue Frog creature with "
         "base power and toughness 1/1. (It loses all other card types and creature types.)", None, "U"),
    real("Kenrith's Transformation", "{1}{G}", 2, "Enchantment — Aura", "Enchant creature\nWhen this Aura enters, draw a card.\nEnchanted creature "
         "loses all abilities and is a green Elk creature with base power and toughness 3/3. (It loses all other card types and creature types.)",
         None, "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    for name in ("Open the Vaults", "Frogify", "Kenrith's Transformation"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def _settle(s):
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize("active", ["p1", "p2"])
def test_auras_entering_together_are_timestamped_apnap(cards, active):
    s = build(cards, ["Frogify", "Grizzly Bears", "Open the Vaults"], ["Open the Vaults", "Kenrith's Transformation"])
    bears = put(s, "Grizzly Bears")
    frog, elk = card_named(s, "Frogify", "p1"), card_named(s, "Kenrith's Transformation", "p2")
    for pid, c in (("p1", frog), ("p2", elk)):
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    vaults = to_hand(s, "Open the Vaults", active)
    if active == "p2":
        stops(s, "main1")
        to_phase(s, "main1", turn=4)  # Bob's turn
        if s.state.rules.priority == "p1":
            act(s, "p1", type="pass_priority")
    assert s.state.turn.active_player == active and s.state.rules.priority == active
    mana(s, active, W=2, C=4)
    act(s, active, type="cast_spell", card_id=vaults.id)
    _settle(s)
    assert s.state.cards[frog.id].attached_to == bears.id and s.state.cards[elk.id].attached_to == bears.id
    # the active player's Aura is timestamped first, the other's after it, and the later one's base power and toughness wins (613.7)
    first, second = (frog, elk) if active == "p1" else (elk, frog)
    assert layers.timestamp(s.state, first.id) < layers.timestamp(s.state, second.id)
    assert pt(s, "Grizzly Bears") == ((3, 3) if active == "p1" else (1, 1))
    check(s)
