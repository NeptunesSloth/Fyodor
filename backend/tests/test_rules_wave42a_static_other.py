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
from app.rules import alt_costs, coverage, statics, type_statics
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, next_turn, priority_to, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave42a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w42a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
DON = "Don Andres, the Renegade"
YAMAZAKI = "Brothers Yamazaki"
FULL = [DON, "Shauku, Endbringer", "Medomai the Ageless", "Stature, Size Shifter", "Masako the Humorless", "The Necrobloom",
        "Tannuk, Steadfast Second", "Adamaro, First to Desire", "Cayth, Famed Mechanist", "Tesak, Judith's Hellhound", "Barbara Wright",
        "Dosan the Falling Leaf", "Jasmine Boreal of the Seven", "Karn, Argent Defender", "Doorkeeper Thrull", "Mm'menon, the Right Hand", YAMAZAKI, "Sekki, Seasons' Guide", "Aeve, Progenitor Ooze", "Technodrome", "Wirecat", "Glacial Crasher",
        "Karsus Depthguard"]


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


def test_laughing_jasper_flint_static_and_upkeep_are_supported(cards):
    cov = coverage.of_card_data(cards.resolve("Laughing Jasper Flint"))
    assert cov.level == "FULL"
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


# -- Jasmine Boreal of the Seven: "Creatures you control with no abilities can't be blocked by creatures with abilities." -------------------------------
def jasmine_attack(cards, cayth=False):
    s = build(cards, ["Jasmine Boreal of the Seven", "Grizzly Bears", "Cayth, Famed Mechanist"], ["Walking Corpse", "Elvish Mystic"], forests=20)
    put(s, "Jasmine Boreal of the Seven")
    bears = put(s, "Grizzly Bears")
    if cayth:
        put(s, "Cayth, Famed Mechanist")  # "Other nontoken creatures you control have fabricate 1": the Bears have an ability now (layer 6)
    corpse, mystic = put(s, "Walking Corpse", "p2"), put(s, "Elvish Mystic", "p2")
    next_turn(s)
    attackers(s, bears)
    blockers_asked(s)
    return s, bears, corpse, mystic


def test_a_creature_with_no_abilities_cannot_be_blocked_by_one_with_abilities(cards):
    s, bears, corpse, mystic = jasmine_attack(cards)
    with pytest.raises(ActionError, match="can't be blocked"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": mystic.id, "attacker_id": bears.id}])  # a mana ability is an ability
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": corpse.id, "attacker_id": bears.id}])  # a vanilla creature may
    check(s)


def test_an_ability_another_static_grants_ends_the_evasion_of_a_creature_with_no_abilities(cards):
    s, bears, corpse, mystic = jasmine_attack(cards, cayth=True)
    assert any("Fabricate" in a.text for a in ch(s, "Grizzly Bears").abilities)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": mystic.id, "attacker_id": bears.id}])  # Jasmine's rule no longer names the Bears (613.8)
    check(s)


# -- Pure layer-7 subjects read completed layer 6; ability-sensitive layer-6 grants remain refused. --
def test_ability_sensitive_pt_and_rules_are_read_but_keyword_grants_are_not():
    assert statics.parse("Creatures with no abilities get +2/+2.") is not None
    assert statics.parse("Creatures you control with no abilities have flying.") is None
    assert statics.parse("Creatures you control with no abilities can't be blocked by creatures with abilities.") is not None


# -- Karn, Argent Defender: "Artifacts and creatures entering the battlefield don't cause abilities to trigger." ---------------------------------------
def karn_table(cards, karn=True):
    s = build(cards, ["Karn, Argent Defender", "Elvish Visionary", "Staff of the Storyteller", "Scoured Barrens"], forests=30)
    if karn:
        put(s, "Karn, Argent Defender")
    return s


def test_karn_stops_the_enters_triggers_of_creatures_and_artifacts_but_not_lands(cards):
    s = karn_table(cards)
    hand = len(s.state.zones["p1:hand"])
    visionary, staff = to_hand(s, "Elvish Visionary"), to_hand(s, "Staff of the Storyteller")
    mana(s, "p1", G=2, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=staff.id)
    settle(s)
    assert zone_of(s, "Elvish Visionary") == "p1:battlefield" and zone_of(s, "Staff of the Storyteller") == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == hand  # 603.2d: no card was drawn (the two cards came from the hand and back)
    assert not any(c.is_token and c.zone == "p1:battlefield" for c in s.state.cards.values())  # no Spirit
    barrens = to_hand(s, "Scoured Barrens")
    life = s.state.players["p1"].life
    act(s, "p1", type="play_land", card_id=barrens.id)
    settle(s)
    assert s.state.players["p1"].life == life + 1  # a land entering still causes its trigger
    check(s)


def test_the_enters_triggers_work_again_when_karn_leaves(cards):
    s = karn_table(cards)
    karn = card_named(s, "Karn, Argent Defender")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="move", card_ids=[karn.id], to={"zone": "graveyard"})
    visionary = to_hand(s, "Elvish Visionary")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # drew a card (the cast one left the hand again)
    check(s)


# -- Brothers Yamazaki: "If there are exactly two permanents named Brothers Yamazaki on the battlefield, the "legend rule" doesn't apply to them." ----------


def test_two_brothers_yamazaki_both_stay(cards):
    s = build(cards, [YAMAZAKI, YAMAZAKI], [YAMAZAKI], forests=20)
    first, second = copies_in(s, YAMAZAKI, 2)
    act(s, "p1", type="pass_priority")  # state-based actions are checked as a player would get priority (704.3)
    d = s.state.rules.decision
    assert d is None or "Legend rule" not in d.prompt  # 704.5j: the rule doesn't apply to them
    assert s.state.cards[first.id].zone == s.state.cards[second.id].zone == "p1:battlefield"
    assert power_toughness(s, YAMAZAKI) == (4, 3)  # 2/1, +2/+2 for the other creature named Brothers Yamazaki
    check(s)


def test_a_third_brothers_yamazaki_brings_the_legend_rule_back_for_its_controller(cards):
    s = build(cards, [YAMAZAKI, YAMAZAKI], [YAMAZAKI], forests=20)
    first, second = copies_in(s, YAMAZAKI, 2)
    (third,) = copies_in(s, YAMAZAKI, 1, "p2")  # three on the battlefield: not "exactly two"
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "Legend rule" in d.prompt and len(d.options) == 2  # Alice's two; Bob's one is alone
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert sum(1 for c in s.state.cards.values() if c.name == YAMAZAKI and c.zone.endswith(":battlefield") and c.controller == "p1") == 1
    assert s.state.cards[third.id].zone == "p2:battlefield"
    check(s)


# -- Sekki, Seasons' Guide: "If damage would be dealt to Sekki, prevent that damage, remove that many +1/+1 counters from Sekki, and create that many 1/1 colorless
# Spirit creature tokens." -----------------------------------------------------------------------------------------------------------------------------
def test_sekki_prevents_damage_and_turns_that_many_counters_into_spirits(cards):
    s = build(cards, ["Sekki, Seasons' Guide", "Lightning Bolt", "Glorious Anthem"], forests=30)
    sekki = to_hand(s, "Sekki, Seasons' Guide")
    mana(s, "p1", G=8)
    act(s, "p1", type="cast_spell", card_id=sekki.id)
    settle(s)
    assert s.state.cards[sekki.id].counters.get("+1/+1") == 8 and power_toughness(s, "Sekki, Seasons' Guide") == (8, 8)
    put(s, "Glorious Anthem")  # a layer 7c bonus on top of the counters
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[sekki.id])
    settle(s)
    assert s.state.cards[sekki.id].damage == 0 and s.state.cards[sekki.id].counters.get("+1/+1") == 5  # 615.5: prevented, three counters removed
    spirits = [c for c in s.state.cards.values() if c.is_token and c.name == "Spirit" and c.zone == "p1:battlefield"]
    assert len(spirits) == 3 and all(power_toughness(s, "Spirit") == (2, 2) for _ in spirits)  # 1/1 each, +1/+1 from the anthem
    assert power_toughness(s, "Sekki, Seasons' Guide") == (6, 6)
    check(s)


# -- Aeve, Progenitor Ooze: "Aeve isn't legendary if it's a token." -------------------------------------------------------------------------------------
def test_aeve_is_legendary_as_a_card_but_not_as_a_token_so_the_legend_rule_leaves_a_copy_alone(cards):
    s = build(cards, ["Aeve, Progenitor Ooze", "Glorious Anthem"], forests=20)
    aeve = put(s, "Aeve, Progenitor Ooze")
    assert "Legendary" in ch(s, "Aeve, Progenitor Ooze").supertypes
    act(s, "p1", type="copy_card", card_id=aeve.id)  # a token copy of it
    act(s, "p1", type="pass_priority")  # 704.3: state-based actions
    d = s.state.rules.decision
    assert d is None or "Legend rule" not in d.prompt  # 205.4, 704.5j: the token isn't legendary
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == "Aeve, Progenitor Ooze")
    assert "Legendary" not in ch_of(s, token).supertypes and "Legendary" in ch(s, "Aeve, Progenitor Ooze").supertypes
    assert s.state.cards[aeve.id].zone == "p1:battlefield" and token.zone == "p1:battlefield"
    check(s)


# -- Mm'menon, the Right Hand: "Artifacts you control have "{T}: Add {U}. Spend this mana only to cast a spell from anywhere other than your hand."" --------
@pytest.mark.parametrize(("zone", "ok"), [("p1:hand", False), ("p1:graveyard", True), ("p1:exile", True), ("p1:library", True), ("p2:graveyard", True)])
def test_mana_for_a_spell_from_anywhere_other_than_your_hand(cards, zone, ok):
    from app.rules import casting
    from app.rules import mana as M

    kind = M.parse_spend("Spend this mana only to cast a spell from anywhere other than your hand.")
    assert kind is not None
    spell = ch(build(cards, ["Lightning Bolt"]), "Lightning Bolt")
    assert casting.spend_allowed(kind, casting.Purpose(spell=spell, zone=zone, player="p1")) is ok  # 601.2a: the zone it is cast from
    assert casting.spend_allowed(kind, None) is False  # (not for a cost that is no spell's)


def test_mmenon_gives_an_artifact_mana_that_cannot_pay_for_a_spell_cast_from_the_hand(cards):
    s = build(cards, ["Mm'menon, the Right Hand", "Sol Ring", "Divination"], forests=30)
    put(s, "Mm'menon, the Right Hand")
    ring = put(s, "Sol Ring")
    index = next(a.index for a in ch(s, "Sol Ring").abilities if "Add {U}" in a.text)  # the granted mana ability (layer 6)
    div = to_hand(s, "Divination")
    act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
    mana(s, "p1", C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=div.id)  # {2}{U}: the {U} may not be spent on a spell cast from the hand (601.2a)
    assert zone_of(s, "Divination") == "p1:hand"
    check(s)


# -- "creature card with no abilities" (Fang-Druid Summoner, Rise from the Wreck, Ruxa): a card in a zone other than the battlefield has the abilities of its rules text
def test_a_creature_card_with_no_abilities_is_found_among_the_cards_with_abilities(cards):
    from app.rules import selectors

    s = build(cards, ["Grizzly Bears", "Elvish Mystic"], forests=20)
    sel = selectors.parse("creature card with no abilities in your library")
    assert sel is not None
    view = Plan(s.state, "p1", s.cards, None)
    bears, mystic = card_named(s, "Grizzly Bears"), card_named(s, "Elvish Mystic")
    assert selectors.matches(view, sel, bears, view.ch(bears), "p1", None) and not selectors.matches(view, sel, mystic, view.ch(mystic), "p1", None)
    check(s)


# -- Wirecat / Technodrome: "This creature can't attack or block if an enchantment is on the battlefield." / "... unless its power is 6 or greater." ---------
def copies_in(s, name, n, pid="p1"):
    cs = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield")][:n]
    assert len(cs) == n
    act(s, pid, type="move", card_ids=[c.id for c in cs], to={"player": pid, "zone": "battlefield"})
    return cs


def test_wirecat_cannot_attack_while_any_enchantment_is_on_the_battlefield(cards):
    s = build(cards, ["Wirecat", "Glorious Anthem", "Walking Corpse"], forests=20)
    wirecat = put(s, "Wirecat")
    corpse = put(s, "Walking Corpse")
    put(s, "Glorious Anthem")  # an enchantment, whoever controls it
    assert "cant_attack_or_block" in ch(s, "Wirecat").imposed and "cant_attack_or_block" not in ch(s, "Walking Corpse").imposed
    next_turn(s)
    to_phase(s, "declare_attackers")
    with pytest.raises(ActionError, match="can't attack"):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": wirecat.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": corpse.id, "target": "p2"}])
    check(s)


def test_wirecat_attacks_again_once_the_last_enchantment_is_gone(cards):
    s = build(cards, ["Wirecat", "Glorious Anthem"], forests=20)
    wirecat = put(s, "Wirecat")
    anthem = put(s, "Glorious Anthem")
    assert "cant_attack_or_block" in ch(s, "Wirecat").imposed
    act(s, "p1", type="move", card_ids=[anthem.id], to={"zone": "graveyard"})  # no enchantment left
    assert "cant_attack_or_block" not in ch(s, "Wirecat").imposed
    next_turn(s)
    attackers(s, wirecat)
    assert s.state.players["p2"].life == 36  # four damage
    check(s)


def test_technodrome_attacks_only_with_power_six_or_greater_after_the_anthems(cards):
    s = build(cards, ["Technodrome", "Glorious Anthem", "Glorious Anthem", "Glorious Anthem"], forests=20)
    put(s, "Technodrome")
    anthems = copies_in(s, "Glorious Anthem", 2)
    assert power_toughness(s, "Technodrome") == (5, 5) and "cant_attack_or_block" in ch(s, "Technodrome").imposed  # layer 7c: 3 + 2
    copies_in(s, "Glorious Anthem", 1)
    assert power_toughness(s, "Technodrome") == (6, 6) and "cant_attack_or_block" not in ch(s, "Technodrome").imposed  # six: the unless is met
    act(s, "p1", type="move", card_ids=[anthems[0].id], to={"zone": "graveyard"})  # an anthem leaves: back to five
    assert power_toughness(s, "Technodrome") == (5, 5) and "cant_attack_or_block" in ch(s, "Technodrome").imposed
    check(s)


# -- Dosan the Falling Leaf: "Players can cast spells only during their own turns." -------------------------------------------------------------------
def test_dosan_stops_a_player_casting_on_a_turn_that_is_not_theirs_until_he_leaves(cards):
    s = build(cards, ["Dosan the Falling Leaf", "Lightning Bolt"], ["Lightning Bolt"], forests=20)
    dosan = put(s, "Dosan the Falling Leaf")
    stops(s)
    mine = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p2"])  # her own turn
    settle(s)
    assert s.state.players["p2"].life == 37
    bolt = to_hand(s, "Lightning Bolt", "p2")  # an instant: flash isn't enough
    mana(s, "p2", R=1)
    priority_to(s, "p2")  # Bob has priority in Alice's main phase
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])  # Alice's turn (601.3)
    act(s, "p1", type="move", card_ids=[dosan.id], to={"zone": "graveyard"})  # the source left: Bob may cast on her turn
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 37
    check(s)


def test_with_dosan_each_player_casts_on_their_own_turn_only(cards):
    s = build(cards, ["Dosan the Falling Leaf", "Lightning Bolt"], ["Lightning Bolt"], forests=20)
    put(s, "Dosan the Falling Leaf")
    stops(s)
    to_phase(s, "main1", turn=2)  # Bob's turn
    theirs = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=theirs.id, targets=["p1"])  # Bob on his own
    settle(s)
    assert s.state.players["p1"].life == 37
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    priority_to(s, "p1")
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # Alice on Bob's turn
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
