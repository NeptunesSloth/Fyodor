"""Review 41: cards waves 48D-50A made FULL that played wrong (CR 2026-09-25), real Oracle text (tests/fixtures/review41_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 115.2, 707.10: "Creatures can't be the targets of spells." (Dense Foliage, Spectral Shield, Karplusan Strider, Lurker) bound a spell's single target only.
  A spell with several targets (Arc Lightning), a copy of a spell choosing new targets (Twincast; a copy of a spell is a spell), a spell whose target is
  changed, a mutating spell's target as it resolves, a modal spell's modes and the per-opponent groups all took the targeting for an ability's.
* 202.3e: "Whenever an opponent casts a spell with mana value, power, or toughness equal to the chosen number" (Talion, the Kindly Lord) read a spell's
  printed mana value: its ruling (2023-09-01) counts the X chosen for it ({X}{R} with X 3 is mana value 4).
* 118.6: "As long as you've discarded a card this turn, you may pay {B/R} to cast this spell." (Asmoranomardicadaistinaculdacar) has no mana cost: it is
  cast for that cost only. The guard was read in the hand only, and from the command zone (it is a commander) it was cast for nothing.
* 601.2f: "Spells you cast cost {1} less to cast for each target." (Hinata, Dawn-Crowned): the castability hint left the reduction out, so a spell only
  Hinata makes affordable read as uncastable and the player was passed for (can_act).
* Checked and pinned: Druid Class's level 3 (a land that becomes a creature with haste and the lands-you-control P/T ability).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import casting, sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave18d_merged import mutate_key
from tests.test_rules_wave34b_activated import ask, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review41_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r41", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
TALION, ASMO, HINATA = "Talion, the Kindly Lord", "Asmoranomardicadaistinaculdacar", "Hinata, Dawn-Crowned"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


# ---- 115.2: "can't be the target of spells" on every targeting path ------------------------------------------------------------------------------
def test_a_spell_with_several_targets_cannot_target_a_creature_spells_cannot_target(cards):
    s = build(cards, ["Dense Foliage", "Arc Lightning", "Grizzly Bears"])
    put(s, "Dense Foliage")
    bears = put(s, "Grizzly Bears")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Arc Lightning").id, targets=[bears.id, "p2"], target_counts=[2], division=[2, 1])
    check(s)


def test_a_copy_of_a_spell_cannot_choose_a_creature_spells_cannot_target(cards):
    s = build(cards, ["Dense Foliage", "Twincast", "Lightning Bolt", "Grizzly Bears"])
    put(s, "Dense Foliage")
    bears = put(s, "Grizzly Bears")
    mana(s, R=1, U=2)
    stops(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Twincast").id, targets=[bolt.id])
    d = ask(s)  # 707.10c: the copy keeps its target or chooses a new one
    assert "keep" in [o.id for o in d.options] and bears.id not in [o.id for o in d.options]  # (707.10: the copy is a spell)
    settle(s)
    assert s.state.cards[bears.id].damage == 0 and s.state.players["p2"].life == 34
    check(s)


def test_a_mutating_spell_whose_target_became_untargetable_enters_as_a_creature(cards):
    s = build(cards, ["Dense Foliage", "Gemrazer", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    gem = to_hand(s, "Gemrazer")
    mana(s, G=3)
    stops(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=gem.id, targets=[bears.id], alt_cost=mutate_key(s, gem))
    put(s, "Dense Foliage")  # now no spell may target the Bears (608.2b, 702.140b)
    settle(s)
    assert s.state.cards[gem.id].zone == "p1:battlefield" and not s.state.cards[gem.id].merged
    check(s)


# ---- 202.3e: Talion reads the X of the spell ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("number", "drains"), [(4, True), (1, False)])
def test_talion_counts_the_x_of_an_opponents_spell(cards, number, drains):
    s = build(cards, [TALION], ["Blaze"])
    stops(s)
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, TALION).id)
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[str(number)])
    settle(s)
    to_phase(s, "main1", turn=2)
    mana(s, "p2", R=1, C=3)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Blaze", "p2").id, targets=["p1"], x_value=3)  # {X}{R} with X 3: mana value 4
    settle(s)
    assert (s.state.players["p2"].life == 38) == drains
    check(s)


# ---- 118.6: Asmoranomardicadaistinaculdacar from the command zone ---------------------------------------------------------------------------------
def test_asmoranomardicadaistinaculdacar_as_commander_needs_its_alternative_cost(cards):
    alice = deck(cards, ASMO, [(1, "Grizzly Bears"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    asmo = card_named(s, ASMO)
    assert asmo.zone == "p1:command"
    with pytest.raises(ActionError):  # nothing discarded this turn: no cost it can be cast for
        act(s, "p1", type="cast_spell", card_id=asmo.id)
    act(s, "p1", type="move", card_ids=[to_hand(s, "Grizzly Bears").id], to={"zone": "graveyard"})  # discarded
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=asmo.id)  # {B/R}
    settle(s)
    assert s.state.cards[asmo.id].zone == "p1:battlefield" and not s.state.players["p1"].mana
    check(s)


# ---- 601.2f: Hinata in the castability hint -------------------------------------------------------------------------------------------------------
def test_hinata_makes_a_one_target_spell_castable_for_one_less_in_the_hint(cards):
    s = build(cards, [HINATA, "Staggershock"])
    put(s, HINATA)
    shock = to_hand(s, "Staggershock")
    mana(s, R=1, C=1)  # {2}{R} less {1}
    assert casting.castable(s.state, "p1", shock, s.cards) and casting.can_act(s.state, "p1", s.cards)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 38
    check(s)


# ---- checked: Druid Class level 3 -----------------------------------------------------------------------------------------------------------------
def test_druid_class_level_three_makes_a_land_a_creature_as_big_as_your_lands(cards):
    s = build(cards, ["Druid Class"])
    druid = put(s, "Druid Class")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:4]
    for f in forests[:3]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, G=2, C=5)
    act(s, "p1", type="activate_ability", card_id=druid.id, ability=1)  # {2}{G}: Level 2
    settle(s)
    act(s, "p1", type="activate_ability", card_id=druid.id, ability=3)  # {4}{G}: Level 3
    settle(s)  # (its trigger targets the first land)
    land = s.state.cards[forests[0].id]
    ch = chars(s, land)
    assert {"Creature", "Land"} <= ch.types and "haste" in ch.keywords and (sba.power(land, ch), sba.toughness(land, ch)) == (3, 3)
    act(s, "p1", type="move", card_ids=[forests[3].id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forests[3].id)  # (the extra land play of level 2 is not needed: none was played this turn)
    settle(s)
    ch = chars(s, land)
    assert (sba.power(land, ch), sba.toughness(land, ch)) == (4, 4) and s.state.players["p1"].life == 41  # (landfall: 1 life)
    check(s)
