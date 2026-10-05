"""Wave 22E: event history and batched triggers (CR 2026-09-25). Real Oracle text (tests/fixtures/wave22e_cards.json);
every scenario checks the replay and a save and a load.

* 500.4 / 603.4: werewolves - "At the beginning of each upkeep, if no spells were cast last turn, transform this creature"
  and "... if a player cast two or more spells last turn, transform ..." read the turn before this one, any player's casts;
  the second is ONE player's own count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave5j_token_copies import ch, drive, find, game, mana, put, roundtrip

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave22e_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t22e", number=f"E{i:02d}", **({"image_uris": None} if c.get("card_faces") else {}),
              **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
EXTRA.append(card("Probe Cantrip", set_code="t22e", number="E90", mana_cost="{U}", cmc=1.0, type_line="Instant", colors=["U"],
                  color_identity=["U"], oracle_text="Scry 1."))
NAMES = [c["name"] for c in EXTRA if c["name"] != "Probe Cantrip"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(name):
    assert level(name) == "FULL", name


def to_turn(s, n, phase="main1"):
    until(s, lambda s: s.state.turn.number == n and s.state.turn.phase == phase, limit=400)


def front(s, c):
    return ch(s, c).name


def test_werewolf_transforms_on_a_quiet_turn_and_back_when_one_player_cast_two(cards):
    s = game(cards, ["Mayor of Avabruck // Howlpack Alpha"], ["Probe Cantrip", "Probe Cantrip"])
    mayor = put(s, "Mayor of Avabruck // Howlpack Alpha")
    assert front(s, mayor) == "Mayor of Avabruck"
    to_turn(s, 2)  # nobody cast a spell on turn 1: Bob's upkeep transformed it
    drive(s)
    assert front(s, mayor) == "Howlpack Alpha"
    roundtrip(s)
    for c in [c for c in s.state.cards.values() if c.name == "Probe Cantrip" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
        mana(s, "p2", U=1)
        act(s, "p2", type="cast_spell", card_id=c.id)
        drive(s)
    to_turn(s, 3)  # Bob alone cast two on turn 2: Alice's upkeep transforms it back
    drive(s)
    assert front(s, mayor) == "Mayor of Avabruck"
    roundtrip(s)
    to_turn(s, 4)  # turn 3 was quiet: it turns over again
    drive(s)
    assert front(s, mayor) == "Howlpack Alpha"
    to_turn(s, 5)  # (turn 4 had no spells, but the night side only turns back for two by one player)
    drive(s)
    assert front(s, mayor) == "Howlpack Alpha"
    roundtrip(s)


def test_two_spells_by_two_players_are_not_two_by_one(cards):
    s = game(cards, ["Mayor of Avabruck // Howlpack Alpha", "Probe Cantrip"], ["Probe Cantrip"])
    mayor = put(s, "Mayor of Avabruck // Howlpack Alpha")
    mine = put(s, "Probe Cantrip", "hand")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=mine.id)  # turn 1: one spell
    drive(s)
    to_turn(s, 2)
    drive(s)
    assert front(s, mayor) == "Mayor of Avabruck"
    theirs = put(s, "Probe Cantrip", "hand", "p2")
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=theirs.id)
    drive(s)
    to_turn(s, 3)
    drive(s)
    assert front(s, mayor) == "Mayor of Avabruck"
    roundtrip(s)
    assert find(s, "Probe Cantrip", "p2")
