"""Wave 42A: the `static_other` family, second pass, commanders first (CR 2026-09-25), real Oracle text
(tests/fixtures/wave42a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 108.3, 110.2, 205.1b, 613.1d/f, 613.4c, 613.8: "Each creature you control but don't own gets +2/+2, has menace and deathtouch, and is a Pirate in
  addition to its other types." (Don Andres) - the subject "you control but don't own" is not cut at "don't", one static acts in layers 4, 6 and 7c, and a
  Pirate lord (Corsair Captain) sees the creature the type was added to (the type is there before the lord's bonus is worked out).
* 508.1c, 509.1b, 613.4: "Shauku can't attack if there's another creature on the battlefield." (whoever controls it), "Stature can't be blocked if her power is
  1 or less." (her power after layer 7: an anthem takes it away), "Medomai can't attack during extra turns." (500.7).
* 509.1a: "Tapped creatures you control can block as though they were untapped." (Masako).
* 702.52a, 702.185a, 113.6: "Land cards in your graveyard have dredge 2." (The Necrobloom), "Artifact cards and red creature cards in your hand have warp
  {2}{R}." (Tannuk) - a keyword a static gives a card in a hand or a graveyard works from there while the static applies.
* 604.3, 613.4a: "Adamaro's power and toughness are each equal to the number of cards in the hand of the opponent with the most cards in hand."
* 603.6a, 614.12, 702.123a, 702.98a, 702.155a: "Other nontoken creatures you control have fabricate 1." (Cayth), "Other Dogs you control have unleash." (Tesak),
  "Sagas you control have read ahead." (Barbara Wright): the permanent that enters has the keyword as it enters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, coverage, type_statics
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, next_turn, settle, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave42a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w42a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
DON = "Don Andres, the Renegade"
FULL = [DON, "Shauku, Endbringer", "Medomai the Ageless", "Stature, Size Shifter", "Masako the Humorless", "The Necrobloom",
        "Tannuk, Steadfast Second", "Adamaro, First to Desire", "Cayth, Famed Mechanist", "Tesak, Judith's Hellhound", "Barbara Wright",
        "Technodrome", "Wirecat"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


def power_toughness(s, name, pid="p1"):
    return ch(s, name, pid).pt


def ch_of(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def to_gy(s, name, pid="p1"):
    c = next(x for x in s.state.cards.values() if x.name == name and x.owner == pid and not x.zone.endswith(":graveyard"))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def attackers(s, *cs, turn=None):
    """Alice's declare-attackers step (of this turn, or of turn ``turn``) reached, and the attack declared on Bob."""
    to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in cs])


def blockers_asked(s, limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers were asked")


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_cards_are_full(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert cov.level == "FULL", (name, [f.label for f in cov.features if not f.supported])


def test_laughing_jasper_flint_static_is_read_but_its_upkeep_ability_is_not(cards):
    cov = coverage.of_card_data(cards.resolve("Laughing Jasper Flint"))
    missing = [f.label for f in cov.features if not f.supported]
    assert len(missing) == 1 and missing[0].startswith("At the beginning of your upkeep, exile the top X")  # (the Mercenaries line is read)
    found = type_statics.parse("Creatures you control but don't own are Mercenaries in addition to their other types.")
    assert found is not None and found["layer4"]["add_subtypes"] == ["Mercenary"]  # (the plural "Mercenaries" is the type Mercenary, 205.3m)


# -- Don Andres, the Renegade: "Each creature you control but don't own gets +2/+2, has menace and deathtouch, and is a Pirate in addition to its other types." --
def test_don_andres_pumps_arms_and_makes_pirates_of_creatures_you_control_but_dont_own(cards):
    s = build(cards, [DON, "Corsair Captain", "Grizzly Bears"], ["Walking Corpse"])
    don = put(s, DON)
    bears = put(s, "Grizzly Bears")
    corpse = card_named(s, "Walking Corpse", "p2")
    act(s, "p1", type="move", card_ids=[corpse.id], to={"player": "p1", "zone": "battlefield"})  # Alice controls a creature Bob owns
    assert s.state.cards[corpse.id].controller == "p1" and s.state.cards[corpse.id].owner == "p2"
    assert power_toughness(s, "Walking Corpse", "p2") == (4, 4)  # 613.4c: +2/+2
    assert {"menace", "deathtouch"} <= ch(s, "Walking Corpse", "p2").keywords  # 613.1f
    assert {"Zombie", "Pirate"} <= ch(s, "Walking Corpse", "p2").subtypes  # 613.1d, 205.1b: in addition to its other types
    assert power_toughness(s, "Grizzly Bears") == (2, 2) and "menace" not in ch(s, "Grizzly Bears").keywords  # Alice owns it
    assert power_toughness(s, DON) == (4, 3) and "menace" not in ch(s, DON).keywords  # nor does it name Don Andres (he is Alice's)
    put(s, "Corsair Captain")  # "Other Pirates you control get +1/+1": the Zombie became a Pirate in layer 4, before the lord's bonus (layer 7c) is read
    assert power_toughness(s, "Walking Corpse", "p2") == (5, 5) and power_toughness(s, DON) == (5, 4)
    assert power_toughness(s, "Grizzly Bears") == (2, 2)
    act(s, "p1", type="move", card_ids=[don.id], to={"zone": "graveyard"})  # the source left: the effect is gone (611.3b)
    assert power_toughness(s, "Walking Corpse", "p2") == (2, 2) and not ({"menace", "deathtouch"} & ch(s, "Walking Corpse", "p2").keywords)
    assert "Pirate" not in ch(s, "Walking Corpse", "p2").subtypes and bears.zone.endswith(":battlefield")
    check(s)


# -- Shauku, Endbringer: "Shauku can't attack if there's another creature on the battlefield." ---------------------------------------------------
def test_shauku_cannot_attack_while_any_other_creature_is_on_the_battlefield(cards):
    s = build(cards, ["Shauku, Endbringer", "Walking Corpse"], ["Grizzly Bears"])
    shauku = put(s, "Shauku, Endbringer")
    corpse = put(s, "Walking Corpse")
    assert "cant_attack" in ch(s, "Shauku, Endbringer").imposed and "cant_attack" not in ch(s, "Walking Corpse").imposed
    next_turn(s)
    to_phase(s, "declare_attackers")
    with pytest.raises(ActionError, match="can't attack"):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": shauku.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": corpse.id, "target": "p2"}])  # the other creature may
    check(s)


def test_shauku_attacks_once_no_other_creature_is_left_whoever_controlled_it(cards):
    s = build(cards, ["Shauku, Endbringer"], ["Grizzly Bears"])
    shauku = put(s, "Shauku, Endbringer")
    put(s, "Grizzly Bears", "p2")  # the other creature is Bob's
    assert "cant_attack" in ch(s, "Shauku, Endbringer").imposed
    to_gy(s, "Grizzly Bears", "p2")
    assert "cant_attack" not in ch(s, "Shauku, Endbringer").imposed
    next_turn(s)
    attackers(s, shauku)
    assert s.state.players["p2"].life == 35  # five flying damage: she attacked
    check(s)


# -- Medomai the Ageless: "Medomai can't attack during extra turns." -----------------------------------------------------------------------------
def test_medomai_cannot_attack_in_the_extra_turn_it_gives(cards):
    s = build(cards, ["Medomai the Ageless", "Walking Corpse"], forests=30)
    medomai = put(s, "Medomai the Ageless")
    corpse = put(s, "Walking Corpse")  # (so that an attack can be declared in the extra turn at all)
    next_turn(s)
    assert s.state.turn.number == 3 and "cant_attack" not in ch(s, "Medomai the Ageless").imposed
    attackers(s, medomai)
    settle(s)  # combat damage to Bob: "take an extra turn after this one" (500.7)
    to_phase(s, "main1", turn=4)
    assert s.state.turn.active_player == "p1" and s.state.rules.extra_turn  # Alice again: the extra turn
    assert "cant_attack" in ch(s, "Medomai the Ageless").imposed
    to_phase(s, "declare_attackers", turn=4)
    with pytest.raises(ActionError, match="can't attack"):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": medomai.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": corpse.id, "target": "p2"}])
    check(s)
    to_phase(s, "main1", turn=6)  # the turn after it is Bob's (5), then Alice's regular turn: she attacks again
    assert not s.state.rules.extra_turn and "cant_attack" not in ch(s, "Medomai the Ageless").imposed
    check(s)


# -- Stature, Size Shifter: "Stature can't be blocked if her power is 1 or less." ----------------------------------------------------------------
def attacked_by_stature(cards, anthem):
    s = build(cards, ["Stature, Size Shifter", "Glorious Anthem"], ["Grizzly Bears"])
    stature = put(s, "Stature, Size Shifter")
    bears = put(s, "Grizzly Bears", "p2")
    anthem_card = put(s, "Glorious Anthem") if anthem else None
    next_turn(s)
    attackers(s, stature)
    blockers_asked(s)
    return s, stature, bears, anthem_card


def test_stature_with_power_one_cannot_be_blocked(cards):
    s, stature, bears, _ = attacked_by_stature(cards, anthem=False)
    assert power_toughness(s, "Stature, Size Shifter") == (1, 1) and "cant_be_blocked" in ch(s, "Stature, Size Shifter").imposed
    with pytest.raises(ActionError, match="can't be blocked"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": stature.id}])
    act(s, "p2", type="declare_blockers", blocks=[])
    check(s)


def test_an_anthem_lifts_stature_power_so_she_can_be_blocked_and_ends_with_its_source(cards):
    s, stature, bears, anthem = attacked_by_stature(cards, anthem=True)
    assert power_toughness(s, "Stature, Size Shifter") == (2, 2) and "cant_be_blocked" not in ch(s, "Stature, Size Shifter").imposed  # layer 7c first
    act(s, "p1", type="move", card_ids=[anthem.id], to={"zone": "graveyard"})  # the anthem leaves: power 1 again
    assert power_toughness(s, "Stature, Size Shifter") == (1, 1) and "cant_be_blocked" in ch(s, "Stature, Size Shifter").imposed
    with pytest.raises(ActionError, match="can't be blocked"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": stature.id}])
    act(s, "p1", type="move", card_ids=[card_named(s, "Glorious Anthem").id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": stature.id}])  # power 2 again: blocked
    check(s)


# -- Masako the Humorless: "Tapped creatures you control can block as though they were untapped." -------------------------------------------------
def masako_table(cards, masako=True):
    s = build(cards, ["Walking Corpse"], ["Masako the Humorless", "Grizzly Bears"], forests=20)
    corpse = put(s, "Walking Corpse")
    mas = put(s, "Masako the Humorless", "p2")
    bears = put(s, "Grizzly Bears", "p2")
    if not masako:
        act(s, "p2", type="move", card_ids=[mas.id], to={"zone": "graveyard"})  # she is gone
    next_turn(s)
    act(s, "p2", type="tap", card_ids=[bears.id])  # Bob's creature is tapped as Alice's turn goes on
    assert s.state.cards[bears.id].tapped
    attackers(s, corpse)
    return s, corpse, bears


def test_masako_lets_a_tapped_creature_block(cards):
    s, corpse, bears = masako_table(cards)
    d = blockers_asked(s)
    assert f"b:{bears.id}" in {o.id for o in d.options}  # a tapped creature is offered as a blocker
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": corpse.id}])
    assert zone_of(s, "Walking Corpse") == "p1:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"  # the 2/2s traded
    check(s)


def test_a_tapped_creature_cannot_block_once_masako_is_gone(cards):
    s, corpse, bears = masako_table(cards, masako=False)
    d = s.state.rules.decision
    assert d is None or d.kind != "declare_blockers"  # nobody can block: no question
    check(s)


# -- The Necrobloom: "Land cards in your graveyard have dredge 2." ------------------------------------------------------------------------------------
def divination_table(cards, necrobloom=True):
    s = build(cards, ["The Necrobloom", "Divination"], forests=30)
    if necrobloom:
        put(s, "The Necrobloom")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})
    div = to_hand(s, "Divination")
    mana(s, "p1", C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=div.id)
    return s, forest


def test_necrobloom_gives_a_land_card_in_your_graveyard_dredge_2(cards):
    s, forest = divination_table(cards)
    assert any(a.text == "Dredge 2" for a in ch_of(s, forest).abilities)  # 702.52a: the granted ability, numbered after the printed ones
    d = ask(s)  # the first of the two draws: replace it?
    assert d.player == "p1" and any("Dredge 2" in o.label for o in d.options)
    library, hand = len(s.state.zones["p1:library"]), len(s.state.zones["p1:hand"])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Dredge 2" in o.label)])
    settle(s, answer="decline")  # (the two milled Forests have dredge too, for the second draw: declined)
    assert s.state.cards[forest.id].zone == "p1:hand"  # returned to the hand
    assert len(s.state.zones["p1:library"]) == library - 2 - 1  # two milled, one card drawn for the second draw
    assert len(s.state.zones["p1:hand"]) == hand + 1 + 1
    check(s)


def test_a_land_in_the_graveyard_has_no_dredge_once_the_necrobloom_is_gone(cards):
    s, forest = divination_table(cards, necrobloom=False)
    assert not any("Dredge" in a.text for a in ch_of(s, forest).abilities)
    settle(s)
    assert s.state.cards[forest.id].zone == "p1:graveyard"  # no question was asked
    check(s)


# -- Tannuk, Steadfast Second: "Artifact cards and red creature cards in your hand have warp {2}{R}." --------------------------------------------------
def warp_offers(s, c):
    return alt_costs.offers(s.state, "p1", s.state.cards[c.id], ch_of(s, c), s.cards)


def test_tannuk_gives_warp_to_a_red_creature_card_in_hand_not_to_other_cards(cards):
    s = build(cards, ["Tannuk, Steadfast Second", "Shivan Dragon", "Grizzly Bears", "Sol Ring"], forests=20)
    tannuk = put(s, "Tannuk, Steadfast Second")
    dragon, bears, ring = (to_hand(s, n) for n in ("Shivan Dragon", "Grizzly Bears", "Sol Ring"))
    assert [o.alt.mana for o in warp_offers(s, dragon)] == ["{2}{R}"] and [o.tag for o in warp_offers(s, ring)] == ["warp"]  # a red creature card; an artifact card
    assert warp_offers(s, bears) == []  # a green creature: neither a red creature card nor an artifact
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=dragon.id, alt_cost=warp_offers(s, dragon)[0].key)  # 702.185a: its warp cost instead of {4}{R}{R}
    settle(s)
    assert zone_of(s, "Shivan Dragon") == "p1:battlefield"
    to_phase(s, "main1", turn=2)  # exiled at the beginning of the next end step (this turn's)
    assert zone_of(s, "Shivan Dragon") == "p1:exile"
    assert tannuk.zone == "p1:battlefield"
    check(s)


def test_a_red_creature_card_in_hand_has_no_warp_once_tannuk_is_gone(cards):
    s = build(cards, ["Tannuk, Steadfast Second", "Shivan Dragon"], forests=20)
    tannuk = put(s, "Tannuk, Steadfast Second")
    dragon = to_hand(s, "Shivan Dragon")
    key = warp_offers(s, dragon)[0].key
    act(s, "p1", type="move", card_ids=[tannuk.id], to={"zone": "graveyard"})
    assert warp_offers(s, dragon) == []
    mana(s, "p1", R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=dragon.id, alt_cost=key)
    check(s)


# -- Cayth, Famed Mechanist: "Other nontoken creatures you control have fabricate 1." -------------------------------------------------------------------
def cast_bears(cards, cayth=True):
    s = build(cards, ["Cayth, Famed Mechanist", "Grizzly Bears"], forests=20)
    if cayth:
        put(s, "Cayth, Famed Mechanist")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    return s, bears


def test_cayth_gives_a_creature_that_enters_fabricate_1(cards):
    s, bears = cast_bears(cards)
    d = ask(s)  # 702.123a: the enters trigger of the fabricate the creature has as it enters (603.6a)
    assert d.player == "p1" and len(d.options) == 2
    counter = next(o for o in d.options if "counter" in o.label.lower())
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[counter.id])
    settle(s)
    assert power_toughness(s, "Grizzly Bears") == (3, 3) and s.state.cards[bears.id].counters.get("+1/+1") == 1
    assert not any(c.name == "Servo" for c in s.state.cards.values())
    check(s)


def test_fabricate_servo_instead_and_a_token_creature_is_not_given_it(cards):
    s, bears = cast_bears(cards)
    d = ask(s)
    servo = next(o for o in d.options if "servo" in o.label.lower())
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[servo.id])
    settle(s)
    assert power_toughness(s, "Grizzly Bears") == (2, 2) and sum(1 for c in s.state.cards.values() if c.name == "Servo" and c.zone == "p1:battlefield") == 1
    assert not any("Fabricate" in a.text for a in ch(s, "Servo").abilities)  # a token: "nontoken creatures"
    assert any("Fabricate" in a.text for a in ch(s, "Grizzly Bears").abilities)
    check(s)


def test_no_fabricate_question_without_cayth(cards):
    s, bears = cast_bears(cards, cayth=False)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and not s.state.cards[bears.id].counters
    check(s)


# -- Tesak, Judith's Hellhound: "Other Dogs you control have unleash." --------------------------------------------------------------------------------
def cast_pack(cards, tesak=True):
    s = build(cards, ["Tesak, Judith's Hellhound", "Mongrel Pack"], forests=20)
    if tesak:
        put(s, "Tesak, Judith's Hellhound")
    pack = to_hand(s, "Mongrel Pack")
    mana(s, "p1", G=5)
    act(s, "p1", type="cast_spell", card_id=pack.id)
    return s, pack


def test_tesak_gives_another_dog_unleash_as_it_enters(cards):
    s, pack = cast_pack(cards)
    d = ask(s)  # 702.98a: "You may have this creature enter with a +1/+1 counter on it."
    assert d.player == "p1" and any("counter" in o.label.lower() for o in d.options)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "counter" in o.label.lower() and "not" not in o.label.lower())])
    settle(s)
    assert s.state.cards[pack.id].counters.get("+1/+1") == 1 and power_toughness(s, "Mongrel Pack") == (5, 2)
    assert "cant_block" in ch(s, "Mongrel Pack").imposed  # 702.98a: it can't block as long as it has a +1/+1 counter
    check(s)


def test_a_dog_enters_plainly_without_tesak(cards):
    s, pack = cast_pack(cards, tesak=False)
    settle(s)
    assert s.state.cards[pack.id].zone == "p1:battlefield" and not s.state.cards[pack.id].counters
    assert "cant_block" not in ch(s, "Mongrel Pack").imposed
    check(s)


# -- Barbara Wright: "Sagas you control have read ahead." ---------------------------------------------------------------------------------------------
def test_barbara_gives_a_saga_read_ahead_so_it_starts_at_the_chapter_chosen(cards):
    fable = "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
    s = build(cards, ["Barbara Wright", fable], forests=20)
    put(s, "Barbara Wright")
    saga = to_hand(s, fable)
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    d = ask(s)  # 702.155a: choose a chapter as it enters
    assert d.player == "p1" and "chapter" in d.prompt.lower()
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["2"])
    settle(s)
    assert s.state.cards[saga.id].zone == "p1:battlefield" and s.state.cards[saga.id].counters.get("lore") == 2  # starts with that many lore counters (714.3b)
    assert not any(c.is_token and "Goblin" in (c.name or "") for c in s.state.cards.values())  # chapter I was skipped: no Goblin Shaman (702.155a)
    check(s)


def test_a_saga_has_no_read_ahead_choice_without_barbara(cards):
    fable = "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
    s = build(cards, ["Barbara Wright", fable], forests=20)
    saga = to_hand(s, fable)
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    settle(s)
    assert s.state.cards[saga.id].counters.get("lore") == 1 and any(c.is_token and "Goblin" in (c.name or "") for c in s.state.cards.values())  # chapter I
    check(s)


# -- Adamaro, First to Desire: "Adamaro's power and toughness are each equal to the number of cards in the hand of the opponent with the most cards in hand." --
def test_adamaro_is_as_big_as_the_largest_opposing_hand_before_an_anthem_adds_to_it(cards):
    s = build(cards, ["Adamaro, First to Desire", "Glorious Anthem"], forests=20)
    act(s, "p2", type="move", card_ids=s.state.zones["p2:library"][:3], to={"zone": "hand"})
    put(s, "Adamaro, First to Desire")
    n = len(s.state.zones["p2:hand"])
    assert n == 3 and power_toughness(s, "Adamaro, First to Desire") == (n, n)  # 604.3, 613.4a: a characteristic-defining ability
    act(s, "p2", type="move", card_ids=s.state.zones["p2:library"][:2], to={"zone": "hand"})
    assert power_toughness(s, "Adamaro, First to Desire") == (n + 2, n + 2)
    put(s, "Glorious Anthem")  # layer 7c after the 7a CDA
    assert power_toughness(s, "Adamaro, First to Desire") == (n + 3, n + 3)
    act(s, "p1", type="move", card_ids=s.state.zones["p1:library"][:3], to={"zone": "hand"})  # only the opponent's hand counts
    assert power_toughness(s, "Adamaro, First to Desire") == (n + 3, n + 3)
    check(s)
