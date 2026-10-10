"""Wave 30E: keyword completion, real Oracle text (tests/fixtures/wave30e_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 702.74a evoke: "Evoke—Exile a white card from your hand." (Solitude, Fury, Grief …) is an alternative cost (118.9) of non-mana parts, "if this
  spell's evoke cost was paid, its controller sacrifices it when it enters"; the exiled card is public (406.3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30e_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30e", number=f"K{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_pitch_evoke_exiles_a_card_and_sacrifices_the_creature_when_it_enters(cards):
    s = build(cards, ["Solitude", "Swords to Plowshares"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    solitude, swords = to_hand(s, "Solitude"), to_hand(s, "Swords to Plowshares")
    (alt,) = hints(s.state, "p1", cards)["alt_castable"][solitude.id]
    assert alt["label"].endswith("exile a white card from your hand (evoke)")
    act(s, "p1", type="cast_spell", card_id=solitude.id, alt_cost=alt["id"])
    settle(s)  # the pitched card is the only white card in hand; the enters trigger exiles the bear; the evoke trigger sacrifices Solitude
    assert zone_of(s, "Swords to Plowshares") == "p1:exile" and zone_of(s, "Solitude") == "p1:graveyard"
    assert s.state.cards[bear.id].zone == "p2:exile"
    assert life(s, "p2") == 40 + 2  # Grizzly Bears' power: the controller of the exiled creature gains that much life
    assert s.state.cards[swords.id].zone == "p1:exile"
    check(s)


def test_pitch_evoke_needs_another_card_of_that_colour(cards):
    s = build(cards, ["Solitude", "Grizzly Bears"], [])
    solitude = to_hand(s, "Solitude")
    to_hand(s, "Grizzly Bears")  # green: not a white card
    assert solitude.id not in hints(s.state, "p1", cards).get("alt_castable", {})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=solitude.id, alt_cost=f"{solitude.id}:3")
    check(s)


def test_spree_pays_the_cost_of_every_chosen_mode(cards):
    # 702.172a: Requisition Raid {W} with "+ {1} — Destroy target artifact." and "+ {1} — Put a +1/+1 counter on each creature target player controls."
    s = build(cards, ["Requisition Raid", "Grizzly Bears"], ["Sol Ring"])
    put(s, "Grizzly Bears")
    ring, raid = put(s, "Sol Ring", "p2"), to_hand(s, "Requisition Raid")
    mana(s, W=1)
    assert raid.id not in hints(s.state, "p1", cards)["castable"]  # {W} + at least one mode's {1}
    mana(s, C=1)
    assert raid.id in hints(s.state, "p1", cards)["castable"]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=raid.id, modes=[0, 2], targets=[ring.id, "p1"])  # {W}{1}{1}: one short
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=raid.id, modes=[0, 2], targets=[ring.id, "p1"])
    settle(s)
    assert zone_of(s, "Sol Ring", "p2") == "p2:graveyard" and pt(s, "Grizzly Bears") == (3, 3)
    check(s)


def test_buyback_with_a_cost_that_is_not_mana(cards):
    # 702.27a: "Buyback—Sacrifice a land." (Constant Mists {1}{G}) and "Buyback—Pay 4 life." (Slaughter {2}{B}{B}) are additional costs (118.8)
    s = build(cards, ["Constant Mists", "Slaughter", "Grizzly Bears"], ["Grizzly Bears"])
    forest, bear = put(s, "Forest"), put(s, "Grizzly Bears", "p2")
    mists, slaughter = to_hand(s, "Constant Mists"), to_hand(s, "Slaughter")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=mists.id, buyback=True)
    settle(s)  # the only land is sacrificed to pay; the spell returns to its owner's hand as it resolves
    assert s.state.cards[forest.id].zone == "p1:graveyard" and s.state.cards[mists.id].zone == "p1:hand"
    mana(s, B=2, C=2)
    act(s, "p1", type="set_life", player="p1", value=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=slaughter.id, buyback=True, targets=[bear.id])  # 4 life
    act(s, "p1", type="set_life", player="p1", value=40)
    act(s, "p1", type="cast_spell", card_id=slaughter.id, buyback=True, targets=[bear.id])
    settle(s)
    assert life(s) == 36 and s.state.cards[bear.id].zone == "p2:graveyard" and s.state.cards[slaughter.id].zone == "p1:hand"
    check(s)


def test_spree_cast_without_paying_its_mana_cost_still_pays_the_modes(cards):
    # 118.9d: a mode's cost is an additional cost, still paid on a spell cast without paying its mana cost (Omniscience)
    s = build(cards, ["Omniscience", "Requisition Raid"], ["Sol Ring"])
    put(s, "Omniscience")
    ring, raid = put(s, "Sol Ring", "p2"), to_hand(s, "Requisition Raid")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=raid.id, free=True, modes=[0], targets=[ring.id])  # the mode's {1}
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=raid.id, free=True, modes=[0], targets=[ring.id])
    settle(s)
    assert zone_of(s, "Sol Ring", "p2") == "p2:graveyard" and s.state.players["p1"].mana == {}
    check(s)


@pytest.mark.parametrize("bargain", [True, False])
def test_bargain_is_an_optional_sacrifice_that_the_spell_remembers(cards, bargain):
    # 702.166a-b: "As an additional cost to cast this spell, you may sacrifice an artifact, enchantment, or token." High Fae Negotiator:
    # "When this creature enters, if it was bargained, each opponent loses 3 life and you gain 3 life."
    s = build(cards, ["High Fae Negotiator", "Sol Ring"], [])
    put(s, "Sol Ring")
    fae = to_hand(s, "High Fae Negotiator")
    mana(s, B=2, C=3)
    (opt,) = hints(s.state, "p1", cards)["optional_costs"][fae.id]
    assert opt["label"] == "Bargain: sacrifice an artifact, enchantment, or token"
    act(s, "p1", type="cast_spell", card_id=fae.id, optional_costs=[opt["id"]] if bargain else [])
    settle(s)
    assert zone_of(s, "High Fae Negotiator") == "p1:battlefield"
    assert (zone_of(s, "Sol Ring") == "p1:graveyard") is bargain
    assert (life(s, "p1"), life(s, "p2")) == ((43, 37) if bargain else (40, 40))
    check(s)


def test_tiered_pays_the_cost_of_the_one_chosen_mode(cards):
    # 702.183a: Restoration Magic {W}: "• Cura — {1} — Target permanent gains hexproof and indestructible until end of turn. You gain 3 life."
    s = build(cards, ["Restoration Magic", "Grizzly Bears"], [])
    bear, magic = put(s, "Grizzly Bears"), to_hand(s, "Restoration Magic")
    mana(s, W=1)
    assert magic.id in hints(s.state, "p1", cards)["castable"]  # Cure costs {0}
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=magic.id, modes=[0, 1], targets=[bear.id, bear.id])  # choose one
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=magic.id, modes=[1], targets=[bear.id])  # Cura's {1} is not there
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=magic.id, modes=[1], targets=[bear.id])
    settle(s)
    assert life(s) == 43
    check(s)
