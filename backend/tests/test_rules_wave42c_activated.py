"""Wave 42C: activated abilities whose effect wasn't read (the `activated_other` family, second pass, commanders first; CR 2026-09-25), real Oracle text
(tests/fixtures/wave42c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

Ablating the ~340 non-FULL cards that still have an activated line: 296 fail in the EFFECT, 16 in the COST, 8 in the activation RESTRICTION, 24 are mana
abilities; of the commanders 46 / 2 / 0 / 4. Seven commanders and two more cards had one small effect piece unread:

* 702.16a protection / 205.2a card types: "gains protection from the card type of your choice until end of turn" (Pippin, Guard of the Citadel) offers the nine types
  a Commander deck holds; the choice is made as the ability resolves (608.2d), by its controller, and is public.
* 613.1f, 702.16, 702.21: "Permanents your opponents control lose hexproof, indestructible, protection, shroud, and ward until end of turn." (Shay Cormac) — an
  object that has lost ward has no ward trigger, one that has lost hexproof can be targeted, and so on; the permanents are fixed as it resolves (611.2c).
* 506.5: "Target creature that's attacking alone gets +1/+1 until end of turn." (Viper, Cruel Conspirator): an attacker while no other creature attacks.
* 113.6m: "Return this card from your graveyard or from exile to the battlefield tapped." (Mister Immortal) works in either zone; 400.7: a card that changed zones
  meanwhile is a new object, so the ability does nothing.
* 701.23a, 701.24: "Target player searches their library for a card, then shuffles and puts that card on top." (Varragoth's Boast, 702.142a): the target player is the
  searcher and chooses from their own library; nobody else sees the card.
* 701.17a: "target creature card in a graveyard that was milled this turn" (The Master, Transcendent; Tato Farmer) and "It's a green Mutant with base power and
  toughness 3/3." (611.2a: for as long as it exists; its colors and creature types are replaced).
* 509.1b: "can't be blocked by creatures with power 2 or less and/or Walls" (Doorman): either kind can't block it.
* 607.2a, 608.2d: "Put a creature card exiled with ~ onto the battlefield under your control." (Sisters of Stone Death, Yggdrasil, Northampton Farm): one of the cards the linked
  ability exiled, chosen as it resolves; the link outlives the source (608.2h).
* 400.7, 110.2a: "Choose a creature card at random from target opponent's graveyard. Put that card onto the battlefield under your control." (Tariel, Reckoner of
  Souls): the table picks (recorded, so a replay and a load pick the same), among the creature cards of the target opponent's graveyard only.
* 701.23a: "Target player searches their library for a basic land card, puts it onto the battlefield tapped, then shuffles." (Fertilid, Fertilid's Favor, Restorative
  Technique) is the same search by the target player, whose land enters under their control.
* 608.2h: "Destroy target artifact or creature. That permanent's controller gains control of Starke." (Starke of Rath): whoever controlled the permanent as it last existed.

Refused (manual, with the reason): Jegantha (the payment would have to know which part of a cost each mana pays), Shaun & Rebecca (a reflexive trigger of a mana ability),
Baba Lysaga ("up to three permanents" and the card types among them), Grenzo (a mill from the bottom with a condition on the card), Diaochan and the other
"of an opponent's choice" targets, Asmodeus (the exile link needs the replacement to be the exiling ability), Tetsuo Umezawa / Bartel Runeaxe ("can't be the target
of Aura spells" is another family's).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, protection, triggers
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import put_in, stack_top
from tests.test_rules_wave34b_activated import (
    activate,
    ask,
    attack,
    block,
    next_turn,
    priority_to,
    settle,
    stops,
)
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave42c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w42c", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
PIPPIN, SHAY, VIPER, IMMORTAL = "Pippin, Guard of the Citadel", "Shay Cormac", "Viper, Cruel Conspirator", "Mister Immortal"
VARRAGOTH, MASTER, STARKE = "Varragoth, Bloodsky Sire", "The Master, Transcendent", "Starke of Rath"
SISTERS, TARIEL = "Sisters of Stone Death", "Tariel, Reckoner of Souls"
FULL = [PIPPIN, SHAY, VIPER, IMMORTAL, VARRAGOTH, MASTER, "Doorman", STARKE, SISTERS, TARIEL, "Tato Farmer", "Crowd of True Believers", "Yggdrasil, Rebirth Engine", "Northampton Farm", "Fertilid",
        "Fertilid's Favor", "Restorative Technique", "Nautiloid Ship"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    """The characteristics of this card now (what a rules question about it reads)."""
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id])


def move(s, name, where="graveyard", pid="p1"):
    """This card (anyone's) into that zone of its owner, at once."""
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": where})


def stack_size(s):
    return len(s.state.zones.get("stack", []))


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# ---- Pippin, Guard of the Citadel: "{T}: Another target creature you control gains protection from the card type of your choice until end of turn." ---------
CARD_TYPES = ["Artifacts", "Battles", "Creatures", "Enchantments", "Instants", "Kindreds", "Lands", "Planeswalkers", "Sorceries"]


def test_pippin_gives_another_creature_protection_from_the_card_type_its_controller_names(cards):
    s = build(cards, [PIPPIN, "Grizzly Bears"], ["Hill Giant"])
    pippin, bears, giant = put(s, PIPPIN), put(s, "Grizzly Bears"), put(s, "Hill Giant", "p2")
    next_turn(s)
    with pytest.raises(ActionError):
        activate(s, "p1", pippin, targets=[pippin.id])  # 115.1: "another" target creature
    assert not s.state.cards[pippin.id].tapped and not stack_size(s)
    activate(s, "p1", pippin, targets=[bears.id])
    assert s.state.cards[pippin.id].tapped  # 602.2b: the cost is paid as it is activated
    d = ask(s)
    assert d.player == "p1" and [o.id for o in d.options] == CARD_TYPES  # 608.2d: its controller, as it resolves; 205.2a (the nine a Commander deck holds)
    assert not protection.protected_from(ch(s, bears), ch(s, giant))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Creatures"])
    settle(s)
    assert protection.protected_from(ch(s, bears), ch(s, giant))  # 702.16b: Hill Giant (a creature) can't damage, block or target it
    assert not protection.protected_from(ch(s, giant), ch(s, bears))
    check(s)


def test_pippin_cannot_use_a_tapped_pippin_and_the_ability_resolves_without_him(cards):
    s = build(cards, [PIPPIN, "Grizzly Bears", "Sol Ring"], ["Hill Giant"])
    pippin, bears = put(s, PIPPIN), put(s, "Grizzly Bears")
    ring = put(s, "Sol Ring")
    next_turn(s)
    act(s, "p1", type="tap", card_ids=[pippin.id], tapped=True)
    with pytest.raises(ActionError):
        activate(s, "p1", pippin, targets=[bears.id])  # 118.3: {T} can't be paid; nothing happens
    assert not stack_size(s) and "protection" not in ch(s, bears).keywords
    act(s, "p1", type="tap", card_ids=[pippin.id], tapped=False)
    activate(s, "p1", pippin, targets=[bears.id])
    move(s, PIPPIN)  # 113.7a: the ability is independent of its source once on the stack
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Artifacts"])
    settle(s)
    assert zone_of(s, PIPPIN) == "p1:graveyard" and protection.protected_from(ch(s, bears), ch(s, ring))
    check(s)


# ---- Shay Cormac: "{1}: Permanents your opponents control lose hexproof, indestructible, protection, shroud, and ward until end of turn." ----------------------
def shay_table(cards):
    s = build(cards, [SHAY, "Black Knight", "Shock", "Lightning Bolt"], ["Gladecover Scout", "Armored Armadillo", "Darksteel Gargoyle", "Black Knight"], forests=4)
    shay = put(s, SHAY)
    mine = put(s, "Black Knight")
    theirs = {n: put(s, n, "p2") for n in ("Gladecover Scout", "Armored Armadillo", "Darksteel Gargoyle", "Black Knight")}
    to_hand(s, "Shock"), to_hand(s, "Lightning Bolt")
    return s, shay, mine, theirs


def test_shay_cormac_strips_the_opponents_permanents_of_their_protections_until_end_of_turn(cards):
    s, shay, knight, theirs = shay_table(cards)
    scout, armadillo, gargoyle, their_knight = (theirs[n] for n in ("Gladecover Scout", "Armored Armadillo", "Darksteel Gargoyle", "Black Knight"))
    mana(s, R=2, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Shock").id, targets=[scout.id])  # hexproof: 702.11b
    assert triggers.ward_costs(ch(s, armadillo)) == ["{1}"] and "indestructible" in ch(s, gargoyle).keywords and "protection" in ch(s, their_knight).keywords
    activate(s, "p1", shay)
    settle(s)
    assert "hexproof" not in ch(s, scout).keywords and "indestructible" not in ch(s, gargoyle).keywords and "protection" not in ch(s, their_knight).keywords
    assert triggers.ward_costs(ch(s, armadillo)) == []  # 702.21a: nothing left to trigger
    assert "protection" in ch(s, knight).keywords  # "Permanents your opponents control": not Alice's own
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shock").id, targets=[scout.id])
    settle(s)
    assert zone_of(s, "Gladecover Scout", "p2") == "p2:graveyard"  # now a legal target, and 2 damage kills the 1/1
    seen = len(s.state.log)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[armadillo.id])
    said = [" ".join(p.t or p.name or "" for p in line.parts) for line in s.state.log[seen:]]
    assert any("Lightning Bolt → Armored Armadillo" in x for x in said) and not any("ability on the stack" in x and "Armored Armadillo" in x for x in said)  # 702.21a: no ward trigger
    check(s)


def test_shay_cormac_needs_its_mana_and_the_loss_ends_with_the_turn_even_if_shay_is_gone(cards):
    s, shay, knight, theirs = shay_table(cards)
    scout, armadillo = theirs["Gladecover Scout"], theirs["Armored Armadillo"]
    with pytest.raises(ActionError):
        activate(s, "p1", shay)  # nothing to pay {1} with: refused, nothing changes
    assert "hexproof" in ch(s, scout).keywords and not stack_size(s)
    mana(s, C=1)
    activate(s, "p1", shay)
    move(s, SHAY)  # 113.7a: it still resolves with Shay gone
    settle(s)
    assert "hexproof" not in ch(s, scout).keywords and triggers.ward_costs(ch(s, armadillo)) == []
    next_turn(s)
    assert "hexproof" in ch(s, scout).keywords and triggers.ward_costs(ch(s, armadillo)) == ["{1}"]  # 514.2: until end of turn
    check(s)


# ---- Viper, Cruel Conspirator: "{B}: Target creature that's attacking alone gets +1/+1 until end of turn." ---------------------------------------------------
def viper_table(cards):
    s = build(cards, [VIPER, "Grizzly Bears", "Hill Giant"], ["Wall of Omens"])
    viper, bears, giant = put(s, VIPER), put(s, "Grizzly Bears"), put(s, "Hill Giant")
    stops(s)
    next_turn(s)
    return s, viper, bears, giant


def test_viper_pumps_the_only_attacker(cards):
    s, viper, bears, giant = viper_table(cards)
    attack(s, bears)
    mana(s, B=2)
    activate(s, "p1", viper, "+1/+1", targets=[bears.id])
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 3)
    activate(s, "p1", viper, "deathtouch", targets=[bears.id])
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "eathtouch" in o.label)])
    settle(s)
    assert "deathtouch" in ch(s, bears).keywords and "lifelink" not in ch(s, bears).keywords
    check(s)


def test_viper_cannot_target_a_creature_when_two_attack_or_none_does(cards):
    s, viper, bears, giant = viper_table(cards)
    mana(s, B=1)
    with pytest.raises(ActionError):
        activate(s, "p1", viper, "+1/+1", targets=[bears.id])  # 506.5: nobody is attacking
    attack(s, bears, giant)
    with pytest.raises(ActionError):
        activate(s, "p1", viper, "+1/+1", targets=[bears.id])  # two attackers: neither attacks alone
    assert pt(s, "Grizzly Bears") == (2, 2) and not stack_size(s)
    check(s)


def test_viper_still_pumps_after_viper_leaves(cards):
    s, viper, bears, giant = viper_table(cards)
    attack(s, bears)
    mana(s, B=1)
    activate(s, "p1", viper, "+1/+1", targets=[bears.id])
    move(s, VIPER)  # 113.7a
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 3)
    check(s)


# ---- Mister Immortal: "{2}{G}: Return this card from your graveyard or from exile to the battlefield tapped." --------------------------------------------------
@pytest.mark.parametrize("where", ["graveyard", "exile"])
def test_mister_immortal_returns_tapped_from_either_zone(cards, where):
    s = build(cards, [IMMORTAL], ["Hill Giant"])
    immortal = card_named(s, IMMORTAL)
    move(s, IMMORTAL, where)
    mana(s, G=3)
    activate(s, "p1", immortal)
    settle(s)
    c = s.state.cards[immortal.id]
    assert c.zone == "p1:battlefield" and c.tapped
    check(s)


def test_mister_immortal_works_only_from_those_zones_and_only_when_paid(cards):
    s = build(cards, [IMMORTAL], ["Hill Giant"])
    immortal = card_named(s, IMMORTAL)
    move(s, IMMORTAL)
    mana(s, G=1)
    with pytest.raises(ActionError):
        activate(s, "p1", immortal)  # {2}{G} can't be paid: it stays where it is
    assert zone_of(s, IMMORTAL) == "p1:graveyard" and not stack_size(s)
    mana(s, G=2)
    for where in ("hand", "battlefield"):
        move(s, IMMORTAL, where)
        with pytest.raises(ActionError):
            activate(s, "p1", immortal)  # 113.6m: a return from the graveyard or exile works nowhere else
        assert zone_of(s, IMMORTAL) == f"p1:{where}" and not stack_size(s)
    check(s)


def test_mister_immortal_that_changed_zones_meanwhile_is_a_new_object_and_stays_put(cards):
    s = build(cards, [IMMORTAL], ["Hill Giant"])
    immortal = card_named(s, IMMORTAL)
    move(s, IMMORTAL)
    mana(s, G=3)
    activate(s, "p1", immortal)
    move(s, IMMORTAL, "exile")  # 400.7: the object the ability is about is gone
    settle(s)
    assert zone_of(s, IMMORTAL) == "p1:exile"
    check(s)


# ---- Varragoth, Bloodsky Sire: "Boast — {1}{B}: Target player searches their library for a card, then shuffles and puts that card on top." -----------------------
def varragoth_table(cards):
    s = build(cards, [VARRAGOTH, "Sol Ring"], ["Counterspell", "Hill Giant"], forests=6, islands=6)
    varragoth = put(s, VARRAGOTH)
    stops(s)
    next_turn(s)
    put_in(s, "Counterspell", "library", "p2")  # (after Bob's draw step)
    put_in(s, "Sol Ring", "library")
    return s, varragoth


def test_varragoth_lets_the_target_player_find_a_card_and_put_it_on_top(cards):
    s, varragoth = varragoth_table(cards)
    attack(s, varragoth)
    mana(s, B=1, C=1)
    activate(s, "p1", varragoth, targets=["p2"])
    d = ask(s)
    assert d.player == "p2" and d.kind in ("choose_cards", "choose_one")  # 701.23a: the target player searches their own library
    counterspell = card_named(s, "Counterspell", "p2")
    alice = s.view("p1")
    assert "options" not in alice["rules"]["decision"] and counterspell.id not in json.dumps(alice) and "Counterspell" not in json.dumps(alice)  # hidden from the rest
    pick = next(o.id for o in d.options if o.label == "Counterspell")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    assert s.state.zones["p2:library"][0] == card_named(s, "Counterspell", "p2").id  # 701.24: shuffled, then on top
    assert zone_of(s, "Counterspell", "p2") == "p2:library"
    check(s)


def test_varragoth_can_boast_only_after_attacking_and_once(cards):
    s, varragoth = varragoth_table(cards)
    mana(s, B=2, C=2)
    with pytest.raises(ActionError):
        activate(s, "p1", varragoth, targets=["p2"])  # 702.142a: only if it attacked this turn
    attack(s, varragoth)
    mana(s, B=2, C=2)
    activate(s, "p1", varragoth, targets=["p1"])
    move(s, VARRAGOTH)  # 113.7a: still resolves; Alice searches her own library
    d = ask(s)
    assert d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Sol Ring")])
    settle(s)
    assert s.state.zones["p1:library"][0] == card_named(s, "Sol Ring").id
    check(s)


# ---- The Master, Transcendent / Tato Farmer: "Put target creature card in a graveyard that was milled this turn onto the battlefield under your control." -------
def master_table(cards):
    s = build(cards, [MASTER, "Grizzly Bears", "Thought Scour", "Hill Giant"], ["Wall of Omens"])
    master = put(s, MASTER)
    next_turn(s)
    stack_top(s, ["Grizzly Bears", "Hill Giant"])
    to_hand(s, "Thought Scour")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Thought Scour").id, targets=["p1"])
    settle(s)  # Alice mills Grizzly Bears and Hill Giant (701.17a), then draws a card
    return s, master


def test_the_master_reanimates_a_milled_creature_as_a_green_mutant_3_3(cards):
    s, master = master_table(cards)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Hill Giant") == "p1:graveyard"
    bears = card_named(s, "Grizzly Bears")
    activate(s, "p1", master, targets=[bears.id])
    settle(s)
    c = s.state.cards[bears.id]
    assert c.zone == "p1:battlefield" and c.controller == "p1"
    chars_ = ch(s, c)
    assert chars_.colors == {"G"} and "Mutant" in chars_.subtypes and "Bear" not in chars_.subtypes  # 205.3m, 105.3: replaced
    assert pt(s, "Grizzly Bears") == (3, 3)  # 613.4b: base power and toughness 3/3
    check(s)


def test_the_master_cannot_take_a_creature_card_that_was_not_milled_and_pays_nothing(cards):
    s, master = master_table(cards)
    other = card_named(s, "Wall of Omens", "p2")
    act(s, "p2", type="move", card_ids=[other.id], to={"player": "p2", "zone": "graveyard"})  # put there by a move, not milled
    with pytest.raises(ActionError):
        activate(s, "p1", master, targets=[other.id])
    assert not s.state.cards[master.id].tapped and not stack_size(s)
    activate(s, "p1", master, targets=[card_named(s, "Hill Giant").id])
    move(s, MASTER)  # 113.7a
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:battlefield" and pt(s, "Hill Giant") == (3, 3)
    check(s)


def test_tato_farmer_puts_a_milled_land_onto_the_battlefield_tapped(cards):
    s = build(cards, ["Tato Farmer", "Thought Scour"], ["Wall of Omens"], forests=9)
    farmer = put(s, "Tato Farmer")
    next_turn(s)
    to_hand(s, "Thought Scour")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Thought Scour").id, targets=["p1"])
    settle(s)
    milled = [c for c in s.state.zones["p1:graveyard"] if s.state.cards[c].name == "Forest"]
    assert len(milled) == 2
    activate(s, "p1", farmer, targets=[milled[0]])
    settle(s)
    land = s.state.cards[milled[0]]
    assert land.zone == "p1:battlefield" and land.tapped
    check(s)


# ---- Doorman: "{T}: Until end of turn, target creature can't be blocked by creatures with power 2 or less and/or Walls." ----------------------------------------
def test_doorman_keeps_small_creatures_and_walls_from_blocking_but_not_a_big_one(cards):
    s = build(cards, ["Doorman", "Grizzly Bears"], ["Hill Giant", "Wall of Omens"])
    doorman, bears = put(s, "Doorman"), put(s, "Grizzly Bears")
    wall = put(s, "Wall of Omens", "p2")
    stops(s)
    next_turn(s)
    activate(s, "p1", doorman, targets=[bears.id])
    settle(s)
    assert s.state.cards[doorman.id].tapped
    attack(s, bears)
    with pytest.raises(ActionError):
        block(s, (wall, bears))  # 509.1b: a Wall can't block it
    check(s)


def test_doorman_lets_a_creature_with_power_three_block(cards):
    s = build(cards, ["Doorman", "Grizzly Bears"], ["Hill Giant", "Wall of Omens"])
    doorman, bears = put(s, "Doorman"), put(s, "Grizzly Bears")
    giant = put(s, "Hill Giant", "p2")
    put(s, "Wall of Omens", "p2")
    stops(s)
    next_turn(s)
    activate(s, "p1", doorman, targets=[bears.id])
    move(s, "Doorman")  # 113.7a
    settle(s)
    attack(s, bears)
    block(s, (giant, bears))
    assert s.state.cards[giant.id].blocking == bears.id
    check(s)


# ---- Starke of Rath: "{T}: Destroy target artifact or creature. That permanent's controller gains control of Starke." --------------------------------------------
def test_starke_goes_to_the_controller_of_the_permanent_it_destroyed(cards):
    s = build(cards, [STARKE], ["Hill Giant"])
    starke, giant = put(s, STARKE), put(s, "Hill Giant", "p2")
    next_turn(s)
    activate(s, "p1", starke, targets=[giant.id])
    settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard"
    assert s.state.cards[starke.id].controller == "p2" and s.state.cards[starke.id].owner == "p1"  # 608.2h: the controller as it last existed; Alice still owns it
    check(s)


def test_starke_stays_when_its_controller_destroys_their_own_artifact(cards):
    s = build(cards, [STARKE, "Sol Ring"], ["Hill Giant"])
    starke, ring = put(s, STARKE), put(s, "Sol Ring")
    next_turn(s)
    activate(s, "p1", starke, targets=[ring.id])
    settle(s)
    assert zone_of(s, "Sol Ring") == "p1:graveyard" and s.state.cards[starke.id].controller == "p1"
    check(s)


def test_starke_cannot_be_activated_tapped_and_gives_nothing_when_it_is_gone(cards):
    s = build(cards, [STARKE], ["Hill Giant"])
    starke, giant = put(s, STARKE), put(s, "Hill Giant", "p2")
    next_turn(s)
    act(s, "p1", type="tap", card_ids=[starke.id], tapped=True)
    with pytest.raises(ActionError):
        activate(s, "p1", starke, targets=[giant.id])
    assert zone_of(s, "Hill Giant", "p2") == "p2:battlefield" and not stack_size(s)
    act(s, "p1", type="tap", card_ids=[starke.id], tapped=False)
    activate(s, "p1", starke, targets=[giant.id])
    move(s, STARKE)  # 113.7a: the destroy still happens; there is no Starke to hand over
    settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and zone_of(s, STARKE) == "p1:graveyard"
    check(s)


# ---- Sisters of Stone Death: "{B}{G}: Exile target creature blocking or blocked by Sisters of Stone Death." / "{2}{B}: Put a creature card exiled with Sisters of Stone Death onto the
# battlefield under your control." --------------------------------------------------------------------------------------------------------------------------------------
def sisters_table(cards):
    s = build(cards, [SISTERS], ["Hill Giant", "Grizzly Bears"])
    sisters, giant, bears = put(s, SISTERS), put(s, "Hill Giant", "p2"), put(s, "Grizzly Bears", "p2")
    stops(s)
    next_turn(s)
    attack(s, sisters)
    block(s, (giant, sisters), (bears, sisters))
    priority_to(s, "p1")
    for victim in (giant, bears):
        mana(s, B=1, G=1)
        activate(s, "p1", sisters, "Exile target", targets=[victim.id])
        settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:exile" and zone_of(s, "Grizzly Bears", "p2") == "p2:exile"
    return s, sisters, giant, bears


def test_sisters_of_stone_death_puts_the_creature_card_its_controller_chooses_onto_the_battlefield(cards):
    s, sisters, giant, bears = sisters_table(cards)
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):
        activate(s, "p1", sisters, "Put a creature card")  # {2}{B}: one mana short, nothing is chosen or moved
    assert not stack_size(s) and zone_of(s, "Hill Giant", "p2") == "p2:exile"
    mana(s, C=1)
    activate(s, "p1", sisters, "Put a creature card")
    d = ask(s)
    assert d.player == "p1" and sorted(o.label for o in d.options) == ["Grizzly Bears", "Hill Giant"]  # 607.2a: the cards it exiled, 608.2d: chosen as it resolves
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
    settle(s)
    assert s.state.cards[giant.id].zone == "p1:battlefield" and s.state.cards[giant.id].controller == "p1" and s.state.cards[giant.id].owner == "p2"
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile"
    check(s)


def test_sisters_of_stone_death_link_outlives_sisters(cards):
    s, sisters, giant, bears = sisters_table(cards)
    mana(s, B=1, C=2)
    activate(s, "p1", sisters, "Put a creature card")
    move(s, SISTERS)  # 113.7a, 608.2h: the ability still resolves, with the cards its source exiled
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and zone_of(s, "Hill Giant", "p2") == "p2:exile"
    check(s)


# ---- Tariel, Reckoner of Souls: "{T}: Choose a creature card at random from target opponent's graveyard. Put that card onto the battlefield under your control." ---------------
def tariel_table(cards):
    s = build(cards, [TARIEL], ["Hill Giant", "Grizzly Bears", "Sol Ring"])
    tariel = put(s, TARIEL)
    next_turn(s)
    for name in ("Hill Giant", "Grizzly Bears", "Sol Ring"):
        move(s, name, "graveyard", "p2")
    return s, tariel


def test_tariel_takes_a_random_creature_card_of_the_target_opponents_graveyard(cards):
    s, tariel = tariel_table(cards)
    activate(s, "p1", tariel, targets=["p2"])
    settle(s)
    taken = [n for n in ("Hill Giant", "Grizzly Bears") if zone_of(s, n, "p2") == "p1:battlefield"]
    assert len(taken) == 1 and s.state.cards[card_named(s, taken[0], "p2").id].controller == "p1"  # under Alice's control
    other = "Grizzly Bears" if taken == ["Hill Giant"] else "Hill Giant"
    assert zone_of(s, other, "p2") == "p2:graveyard" and zone_of(s, "Sol Ring", "p2") == "p2:graveyard"  # only creature cards are in the pool
    check(s)


def test_tariel_needs_to_be_untapped_does_nothing_without_creature_cards_and_resolves_without_tariel(cards):
    s, tariel = tariel_table(cards)
    act(s, "p1", type="tap", card_ids=[tariel.id], tapped=True)
    with pytest.raises(ActionError):
        activate(s, "p1", tariel, targets=["p2"])  # {T} can't be paid: nothing moves
    assert not stack_size(s) and zone_of(s, "Hill Giant", "p2") == "p2:graveyard"
    act(s, "p1", type="tap", card_ids=[tariel.id], tapped=False)
    activate(s, "p1", tariel, targets=["p2"])
    move(s, TARIEL)  # 113.7a
    settle(s)
    assert sum(zone_of(s, n, "p2") == "p1:battlefield" for n in ("Hill Giant", "Grizzly Bears")) == 1
    check(s)


# ---- Fertilid: "{1}{G}, Remove a +1/+1 counter from this creature: Target player searches their library for a basic land card, puts it onto the battlefield tapped, then shuffles." --
def fertilid_table(cards):
    s = build(cards, ["Fertilid"], ["Hill Giant"], islands=12)
    fertilid = put(s, "Fertilid")
    if have := s.state.cards[fertilid.id].counters.get("+1/+1", 0) - 1:  # (it may have come in with its two counters; a 0/0 with none would die)
        act(s, "p1", type="counter", card_ids=[fertilid.id], kind="+1/+1", delta=-have)
    next_turn(s)
    return s, fertilid


def test_fertilid_lets_the_target_player_put_a_basic_land_onto_their_own_battlefield_tapped(cards):
    s, fertilid = fertilid_table(cards)
    assert s.state.cards[fertilid.id].counters.get("+1/+1", 0) == 1
    mana(s, G=1, C=1)
    activate(s, "p1", fertilid, targets=["p2"])
    assert zone_of(s, "Fertilid") == "p1:graveyard"  # 602.2b: the last counter was removed as a cost, the 0/0 died; 113.7a: the ability resolves anyway
    d = ask(s)
    assert d.player == "p2"  # the target player searches (701.23a) and chooses
    island = next(o.id for o in d.options if o.label == "Island")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[island])
    settle(s)
    land = s.state.cards[island]
    assert land.zone == "p2:battlefield" and land.controller == "p2" and land.tapped  # their land, under their control
    assert not any(c.name == "Island" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)


def test_fertilid_cannot_be_activated_without_the_mana_and_keeps_its_counter(cards):
    s, fertilid = fertilid_table(cards)
    mana(s, G=1)
    with pytest.raises(ActionError):
        activate(s, "p1", fertilid, targets=["p1"])  # {1}{G} can't be paid, so the counter is not removed either (118.3)
    assert s.state.cards[fertilid.id].counters.get("+1/+1", 0) == 1 and not stack_size(s)
    check(s)


# ---- still manual ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Jegantha, the Wellspring", "Shaun & Rebecca, Agents", "Baba Lysaga, Night Witch", "Grenzo, Dungeon Warden", "Diaochan, Artful Beauty",
                                  "Tetsuo Umezawa", "Bartel Runeaxe"])
def test_still_manual(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "PARTIAL", name
