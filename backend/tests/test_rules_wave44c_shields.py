"""Wave 44C (player protection from a static): "You and permanents you control have protection from Salamanders." (Gor Muldrak, Amphinologist [14000]), real Oracle text
(tests/fixtures/wave44c_cards.json). The replay and a save and a load are checked.

* 702.16b, 702.16c, 702.16e: a player with protection from a quality can't be damaged by sources with it (the damage is prevented); the permanents have it too (613.1f).
* 611.3a: a static ability's grant applies while its source is on the battlefield.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, to_phase
from tests.wave44c_kit import DATA, ch, life, open_cards
from tests.wave9c_kit import build, card_named, check, put


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def test_coverage_full(cards):
    data = next(c for c in DATA if c["name"] == "Gor Muldrak, Amphinologist")
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [data], "oracle_id": "gm"}).level == "FULL"


def bob_attacks(s, *names):
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": card_named(s, n, "p2").id, "target": "p1"} for n in names])
    to_phase(s, "main2")


def table(cards):
    s = build(cards, ["Gor Muldrak, Amphinologist"], ["Grizzly Bears"])
    put(s, "Gor Muldrak, Amphinologist")
    put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="create_token", player="p2", token={"name": "Fire Lizard", "type_line": "Token Creature — Salamander", "power": "3", "toughness": "3", "colors": ["R"]})
    settle(s)
    return s


def test_gor_muldrak_protects_its_controller_from_salamander_damage_only(cards):
    s = table(cards)
    bob_attacks(s, "Fire Lizard", "Grizzly Bears")
    assert life(s, "p1") == 40 - 2  # the Bears' 2; the Salamander's 3 is prevented
    check(s)


def test_gor_muldrak_gives_its_controllers_permanents_protection_and_only_while_it_is_there(cards):
    s = table(cards)
    gm = card_named(s, "Gor Muldrak, Amphinologist")
    assert "protection" in ch(s, gm).keywords
    act(s, "p1", type="move", card_ids=[gm.id], to={"zone": "graveyard"})
    bob_attacks(s, "Fire Lizard")
    assert life(s, "p1") == 40 - 3  # without it the Salamander connects
    check(s)
