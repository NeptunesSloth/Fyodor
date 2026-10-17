"""Wave 49C: single-wording gaps of cards ranked 25,000 and up (CR 2026-09-25), real Oracle text (tests/fixtures/wave49c_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 613.1f, 613.7: "All creatures lose flying." (Gravity Sphere), "All creatures lose flying and islandwalk." (Mystic Decree) - a static loss in timestamp order.
* 105.2, 509.1: "White creatures and blue creatures can't block." (Magistrate's Veto), "Green creatures and white creatures can't block this turn." (Flash of Defiance).
* 115.2: "… can't be the target of spells" (Spectral Shield), "… of blue or black spells" (Karplusan Strider), "… unless it attacked or blocked this turn" (Lurker) - abilities still may.
* 702.129a: "Eternalize—{2}{W}{W}, Discard a card." (Sunscourge Champion, Sinuous Striker) - the keyword's cost has a second part, a discard from the hand (the card with
  eternalize is in the graveyard, so it cannot discard itself); with no other card in hand the ability cannot be activated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import attach, attack, settle, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49c_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49c", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def eternalize(s, name="Sunscourge Champion", hand_left=1):
    """The card in the graveyard and (``hand_left``) a Forest in hand to discard; returns the card."""
    champ = card_named(s, name)
    act(s, "p1", type="move", card_ids=[champ.id], to={"zone": "graveyard"})
    if hand_left:
        to_hand(s, "Forest")
    mana(s, W=2, C=2)
    return champ


def test_eternalize_with_a_discard_makes_the_token_and_discards_a_card(cards):
    s = build(cards, ["Sunscourge Champion"])
    champ = eternalize(s)
    discarded = s.state.zones["p1:hand"][0]
    act(s, "p1", type="activate_ability", card_id=champ.id, ability=1)
    settle(s)
    assert s.state.cards[champ.id].zone == "p1:exile" and s.state.cards[discarded].zone == "p1:graveyard" and not s.state.zones["p1:hand"]
    (token,) = [c for c in s.state.cards.values() if c.token is not None and c.name == "Sunscourge Champion"]
    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert ch.colors == {"B"} and "Zombie" in ch.subtypes and ch.pt == (4, 4)  # 702.129a
    assert life(s) == 44  # its enters trigger gains life equal to its power
    check(s)


def test_eternalize_with_a_discard_needs_a_card_in_hand(cards):
    s = build(cards, ["Sunscourge Champion"])
    champ = eternalize(s, hand_left=0)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=champ.id, ability=1)
    check(s)


def chars(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


@pytest.mark.parametrize("sphere", ["Gravity Sphere", "Mystic Decree"])
def test_a_world_enchantment_takes_flying_from_every_creature(cards, sphere):
    s = build(cards, [sphere, "Mulldrifter"], ["Mulldrifter"])
    put(s, "Mulldrifter")
    put(s, "Mulldrifter", "p2")
    assert "flying" in chars(s, "Mulldrifter").keywords
    put(s, sphere)
    assert "flying" not in chars(s, "Mulldrifter").keywords and "flying" not in chars(s, "Mulldrifter", "p2").keywords
    check(s)


def test_a_creature_keeps_flying_without_the_sphere(cards):
    s = build(cards, ["Mulldrifter"])
    put(s, "Mulldrifter")
    assert "flying" in chars(s, "Mulldrifter").keywords
    check(s)


def test_magistrates_veto_stops_white_and_blue_creatures_blocking_but_not_green(cards):
    s = build(cards, ["Magistrate's Veto", "Soul Warden", "Merfolk Looter", "Llanowar Elves"])
    for name in ("Magistrate's Veto", "Soul Warden", "Merfolk Looter", "Llanowar Elves"):
        put(s, name)
    assert "cant_block" in chars(s, "Soul Warden").imposed and "cant_block" in chars(s, "Merfolk Looter").imposed
    assert "cant_block" not in chars(s, "Llanowar Elves").imposed
    check(s)


def test_flash_of_defiance_stops_green_and_white_creatures_blocking_this_turn(cards):
    s = build(cards, ["Flash of Defiance", "Soul Warden", "Merfolk Looter", "Llanowar Elves"])
    for name in ("Soul Warden", "Merfolk Looter", "Llanowar Elves"):
        put(s, name)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Flash of Defiance").id)
    settle(s)
    assert "cant_block" in chars(s, "Soul Warden").imposed and "cant_block" in chars(s, "Llanowar Elves").imposed
    assert "cant_block" not in chars(s, "Merfolk Looter").imposed
    check(s)


def test_spectral_shield_stops_spells_targeting_the_creature(cards):
    s = build(cards, ["Spectral Shield", "Grizzly Bears", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    attach(s, put(s, "Spectral Shield"), bears)
    assert chars(s, "Grizzly Bears").pt == (2, 4)
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])
    check(s)


def test_karplusan_strider_stops_blue_and_black_spells_only(cards):
    s = build(cards, ["Karplusan Strider", "Lightning Bolt", "Capsize"])
    strider = put(s, "Karplusan Strider")
    mana(s, U=3, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Capsize").id, targets=[strider.id])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[strider.id])  # a red spell may
    settle(s)
    assert s.state.cards[strider.id].damage == 3
    check(s)


def test_lurker_can_be_targeted_by_spells_only_after_it_attacked(cards):
    s = build(cards, ["Lurker", "Lightning Bolt"])
    lurker = put(s, "Lurker")
    to_phase(s, "main1", turn=3)  # (no longer summoning sick)
    mana(s, R=1)
    bolt = to_hand(s, "Lightning Bolt")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[lurker.id])
    attack(s, lurker)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[lurker.id])  # it attacked this turn
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)
