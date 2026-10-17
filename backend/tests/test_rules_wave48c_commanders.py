"""Wave 48C: commanders with one blocking line (CR 2026-09-25), real Oracle text (tests/fixtures/wave48c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 106.4, 608.2c: "Destroy target artifact if its mana value is equal to the amount of unspent mana you have." (Glissa Sunseeker): the mana in the pool as the ability resolves.
* 406.3, 701.26a: "exile the top card of your library face down. You may look at and play that card this turn." (Headliner Scarlett): only its owner may look at it.
* 607.2a, 608.2g: "you may cast a card exiled with Krang & Shredder without paying its mana cost" (a card cast from exile is a spell).
* 701.26a: "untap each creature you control, then tap any number of creatures you control" (Augusta, Dean of Order: only an untapped creature can be tapped).
* 611.2a, 613.1d, 613.4c: "target creature you control gets +3/+1 and becomes a Dinosaur in addition to its other types" until end of turn (Stegron, Thran Forge).
* 602.2, 118.3: "Tap another untapped creature you control with flying: ~ gains protection from the color of your choice" (Radiant, Serra Archangel).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, attack, next_turn, settle, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of
from tests.wave44c_kit import ch

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
GLISSA, SCARLETT, KRANG, PLARGG = "Glissa Sunseeker", "Headliner Scarlett", "Krang & Shredder", "Plargg, Dean of Chaos // Augusta, Dean of Order"
STEGRON, RADIANT, FORGE = "Stegron the Dinosaur Man", "Radiant, Serra Archangel", "Thran Forge"
NAMES = [GLISSA, SCARLETT, KRANG, PLARGG, STEGRON, RADIANT]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [*NAMES, FORGE])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# ---- 106.4: Glissa Sunseeker --------------------------------------------------------------------------------------------------------------------
def test_glissa_destroys_an_artifact_whose_mana_value_is_the_unspent_mana(cards):
    s = build(cards, [GLISSA, "Sol Ring", "Arcane Signet"], [])
    glissa = put(s, GLISSA)
    next_turn(s)
    ring, signet = put(s, "Sol Ring"), put(s, "Arcane Signet")
    mana(s, R=1)
    activate(s, "p1", glissa, "Destroy", targets=[signet.id])  # mana value 2, one mana unspent: nothing happens
    settle(s)
    assert zone_of(s, "Arcane Signet") == "p1:battlefield" and s.state.cards[glissa.id].tapped
    act(s, "p1", type="tap", card_ids=[glissa.id], tapped=False)
    activate(s, "p1", glissa, "Destroy", targets=[ring.id])  # mana value 1, one mana unspent
    settle(s)
    assert zone_of(s, "Sol Ring") == "p1:graveyard" and zone_of(s, "Arcane Signet") == "p1:battlefield"
    check(s)


def on_top(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


# ---- 406.3: Headliner Scarlett ------------------------------------------------------------------------------------------------------------------
def test_headliner_scarlett_exiles_the_top_card_face_down_and_its_owner_may_play_it_this_turn(cards):
    s = build(cards, [SCARLETT, "Lightning Bolt"], [], forests=30, islands=30)
    put(s, SCARLETT)
    bolt = on_top(s, "Lightning Bolt")
    to_phase(s, "upkeep", turn=3)
    settle(s)
    exiled = s.state.cards[bolt.id]
    assert exiled.zone == "p1:exile" and exiled.face_down
    assert s.view("p1")["cards"][bolt.id].get("name") == "Lightning Bolt"  # "You may look at": its owner does
    for viewer in ("p2", SPECTATOR):  # nobody else learns what it is (406.3a)
        seen = json.dumps(s.view(viewer))
        assert "Lightning Bolt" not in seen and bolt.card_id not in seen
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # "and play that card this turn"
    settle(s)
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and s.state.players["p2"].life == 37
    check(s)


def test_headliner_scarlett_card_can_no_longer_be_played_on_a_later_turn(cards):
    s = build(cards, [SCARLETT, "Lightning Bolt"], [], forests=30, islands=30)
    put(s, SCARLETT)
    bolt = on_top(s, "Lightning Bolt")
    to_phase(s, "upkeep", turn=3)
    settle(s)
    to_phase(s, "main1", turn=3)  # not cast: the turn ends and the permission with it
    to_phase(s, "main1", turn=5)
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert s.state.players["p2"].life == 40
    check(s)


