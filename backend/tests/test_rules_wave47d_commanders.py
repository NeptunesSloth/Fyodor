"""Wave 47D: commanders with one blocking line (CR 2026-09-25), real Oracle text (tests/fixtures/wave47d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 111.4, 208.1, 604.3: "create Beau, a legendary blue Ox creature token with "Beau's power and toughness are each equal to the number of lands you control."" (Bonny Pall)
  and "Create a … Spirit enchantment creature token. It has "This creature's power and toughness are each equal to the number of experience counters you have."" (Daxos):
  nothing is printed for the token's power and toughness, its characteristic-defining ability sets both.
* 605.1a, 602.5d, 118.3: "Remove five +1/+1 counters from Ramos: Add {W}{W}{U}{U}{B}{B}{R}{R}{G}{G}. Activate only once each turn." — a mana ability named by the card's own name.
* 201.2, 701.23: "Dragon cards not named Tiamat that each have different names" (Tiamat).
* 701.27f: a delayed triggered ability transforms the permanent only if it hasn't transformed since the ability was created (Archangel Avacyn, Aang; the rulings of
  2016-04-08 and 2025-10-02: several creatures dying in one turn transform it once).
* 614.1c, 603.7c: "Whenever you cast a creature spell …, that creature enters with X additional +1/+1 counters on it, where X is its mana value minus 4" (Runadi),
  "… for each Dog and/or Wolf you control" (Torgal): counters the spell is cast with, counted as the trigger resolves (608.2h).
* 702.190, 701.53: "Whenever you cast a Phyrexian creature or artifact creature spell, incubate X, where X is that spell's mana value." (Brimaz, Blight of Oreskos).
* 205.3, 608.2c: "Return all creatures to their owners' hands except for Merfolk, Krakens, Leviathans, Octopuses, and Serpents." (Slinn Voda).
* 608.2c: "amass Orcs 5, mill five cards, then return a creature card from your graveyard to the battlefield" in order (Sauron, Lord of the Rings).
* 205.1b: "If he wasn't a Spirit, return this card to the battlefield … He's a Spirit in addition to his other types." (Fang, Roku's Companion).
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
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of
from tests.wave44c_kit import ch

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave47d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w47d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BONNY, DAXOS, RAMOS, TIAMAT = "Bonny Pall, Clearcutter", "Daxos the Returned", "Ramos, Dragon Engine", "Tiamat"
AANG, AVACYN, RUNADI, TORGAL = "Aang, at the Crossroads // Aang, Destined Savior", "Archangel Avacyn // Avacyn, the Purifier", "Runadi, Behemoth Caller", "Torgal, A Fine Hound"
BRIMAZ, SLINN, SAURON, FANG = "Brimaz, Blight of Oreskos", "Slinn Voda, the Rising Deep", "Sauron, Lord of the Rings", "Fang, Roku's Companion"
NAMES = [BONNY, DAXOS, RAMOS, TIAMAT, AANG, AVACYN, RUNADI, TORGAL, BRIMAZ, SLINN, SAURON, FANG]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_every_commander_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def lands(s, n, pid="p1", name="Forest"):
    """``n`` more basic lands of ``pid`` onto the battlefield."""
    ids = [c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "battlefield"})


def counters(s, name, kind="+1/+1", n=1, pid="p1"):
    act(s, pid, type="counter", card_ids=[card_named(s, name, pid).id], kind=kind, delta=n)


def n_counters(s, name, kind="+1/+1", pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get(kind, 0)


# ---- 111.4, 208.1: a token whose characteristic-defining ability sets its power and toughness (Bonny Pall, Daxos) ------------------------------------
def test_bonny_pall_makes_beau_whose_size_is_the_number_of_lands_its_controller_has(cards):
    s = build(cards, [BONNY], [])
    lands(s, 3)
    lands(s, 1, "p2", "Island")
    mana(s, G=1, U=2, R=3)
    cast(s, BONNY)
    beau = card_named(s, "Beau")
    assert beau.token is not None and "Legendary" in ch(s, beau).supertypes and pt(s, "Beau") == (3, 3)  # the opponent's land is not "lands you control"
    lands(s, 2)
    assert pt(s, "Beau") == (5, 5)  # not locked in
    check(s)


def cast(s, name, pid="p1", **kw):
    to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s)


def cast_from(s, name, pid="p1", **kw):
    """Cast the first copy of ``name`` still in the library (it is put into the hand first); the card."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    settle(s)
    return c


def test_daxos_spirit_is_as_big_as_the_experience_counters_its_controller_has(cards):
    s = build(cards, [DAXOS, "Test Rest", "Test Moat", "Hill Giant"], [])
    daxos = put(s, DAXOS)
    mana(s, W=2, B=2, G=2, R=4)
    cast(s, "Hill Giant")  # not an enchantment spell: no experience counter
    assert s.state.players["p1"].resources["experience"] == 0
    cast(s, "Test Rest")
    assert s.state.players["p1"].resources["experience"] == 1
    mana(s, W=1, B=1, G=1)
    activate(s, "p1", daxos, "Create")
    settle(s)
    assert pt(s, "Spirit") == (1, 1)
    mana(s, W=2)
    cast(s, "Test Moat")
    assert pt(s, "Spirit") == (2, 2)  # counted as it is now, not locked in
    check(s)


# ---- 605.1a, 602.5d: a mana ability named by the card's own name (Ramos) ---------------------------------------------------------------------------
def test_ramos_removes_five_counters_for_ten_mana_once_each_turn(cards):
    s = build(cards, [RAMOS], [])
    ramos = put(s, RAMOS)
    counters(s, RAMOS, n=4)
    with pytest.raises(ActionError):  # four counters: the cost can't be paid
        activate(s, "p1", ramos, "Remove five")
    assert n_counters(s, RAMOS) == 4
    counters(s, RAMOS, n=6)
    activate(s, "p1", ramos, "Remove five")
    assert n_counters(s, RAMOS) == 5 and s.state.players["p1"].mana == {"W": 2, "U": 2, "B": 2, "R": 2, "G": 2}
    with pytest.raises(ActionError):  # once each turn
        activate(s, "p1", ramos, "Remove five")
    assert n_counters(s, RAMOS) == 5
    check(s)


# ---- 201.2, 701.23: "not named Tiamat" and "different names" (Tiamat) --------------------------------------------------------------------------
def test_tiamat_finds_up_to_five_dragons_not_named_tiamat_with_different_names(cards):
    s = build(cards, [TIAMAT, "Shivan Dragon", "Shivan Dragon", "Dragon Whelp", "Furnace Whelp", "Grizzly Bears"], [])
    tiamat = to_hand(s, TIAMAT)
    mana(s, W=1, U=1, B=1, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=tiamat.id)
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1"
    names = sorted(s.state.cards[o.id].name for o in d.options)
    assert names == ["Dragon Whelp", "Furnace Whelp", "Shivan Dragon", "Shivan Dragon"]  # no Tiamat, no Bears
    both = [o.id for o in d.options if s.state.cards[o.id].name == "Shivan Dragon"]
    with pytest.raises(ActionError):  # different names
        act(s, "p1", type="choose", decision_id=d.id, option_ids=both)
    pick = [next(o.id for o in d.options if s.state.cards[o.id].name == n) for n in ("Shivan Dragon", "Dragon Whelp", "Furnace Whelp")]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=pick)
    settle(s)
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p1:hand") == ["Dragon Whelp", "Furnace Whelp", "Shivan Dragon"]
    check(s)


# ---- 701.27f: a delayed triggered ability transforms the permanent once (Archangel Avacyn, Aang) ---------------------------------------------------
def kill(s, victim, spell="Lightning Bolt", **m):
    """Alice casts one more ``spell`` at her own permanent ``victim`` (Bolt: R)."""
    mana(s, **(m or {"R": 1}))
    cast_from(s, spell, targets=[victim.id])


def face(s, name):
    return s.state.cards[card_named(s, name).id].face


def test_archangel_avacyn_transforms_at_the_next_upkeep_when_a_non_angel_creature_dies(cards):
    s = build(cards, [AVACYN, "Grizzly Bears", "Lightning Bolt"], [])
    put(s, AVACYN)
    bears = put(s, "Grizzly Bears")
    kill(s, bears)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and face(s, AVACYN) == 0  # not yet: the next upkeep
    to_phase(s, "main1", turn=2)
    settle(s)
    assert face(s, AVACYN) == 1 and s.state.players["p2"].life == 37  # "deals 3 damage to each other creature and each opponent"
    check(s)


def test_archangel_avacyn_does_not_transform_back_when_several_creatures_died(cards):
    """The ruling of 2016-04-08: the second delayed ability finds it already transformed, so it does nothing."""
    s = build(cards, [AVACYN, "Grizzly Bears", "Hill Giant", "Lightning Bolt", "Lightning Bolt"], [])
    put(s, AVACYN)
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    kill(s, bears)
    kill(s, giant)
    to_phase(s, "main1", turn=2)
    settle(s)
    assert face(s, AVACYN) == 1 and s.state.players["p2"].life == 37  # transformed once, not twice
    check(s)


def test_archangel_avacyn_ignores_an_angel_dying(cards):
    s = build(cards, [AVACYN, "Serra Angel", "Murder"], [])
    put(s, AVACYN)
    angel = put(s, "Serra Angel")
    kill(s, angel, "Murder", B=2, C=1)
    assert zone_of(s, "Serra Angel") == "p1:graveyard"
    to_phase(s, "main1", turn=2)
    settle(s)
    assert face(s, AVACYN) == 0
    check(s)


def test_aang_transforms_at_the_next_upkeep_when_another_creature_you_control_leaves(cards):
    s = build(cards, [AANG, "Grizzly Bears", "Lightning Bolt"], [])
    put(s, AANG)
    bears = put(s, "Grizzly Bears")
    kill(s, bears)
    assert face(s, AANG) == 0
    to_phase(s, "main1", turn=2)
    settle(s)
    assert face(s, AANG) == 1
    check(s)


# ---- 614.1c, 603.7c: "that creature enters with … additional +1/+1 counters" (Runadi, Torgal) -----------------------------------------------------
def test_runadi_gives_a_big_creature_spell_counters_for_its_mana_value_above_four(cards):
    s = build(cards, [RUNADI, "Serra Angel", "Shivan Dragon", "Hill Giant"], [])
    put(s, RUNADI)
    mana(s, W=2, R=3, C=14)
    five = cast_from(s, "Serra Angel")  # mana value 5: X = 1
    six = cast_from(s, "Shivan Dragon")  # mana value 6: X = 2
    four = cast_from(s, "Hill Giant")  # mana value 4: the trigger needs 5 or greater
    assert [s.state.cards[c.id].counters.get("+1/+1", 0) for c in (five, six, four)] == [1, 2, 0]
    check(s)


def test_torgal_counts_the_dogs_and_wolves_for_the_first_human_spell_each_turn(cards):
    s = build(cards, [TORGAL, "Watchwolf", "Elite Vanguard", "Soldier of the Pantheon", "Grizzly Bears"], [])
    put(s, TORGAL)
    put(s, "Watchwolf")
    mana(s, W=3, G=3)
    first = cast_from(s, "Elite Vanguard")
    second = cast_from(s, "Soldier of the Pantheon")  # not the first this turn
    bear = cast_from(s, "Grizzly Bears")  # not a Human
    assert [s.state.cards[c.id].counters.get("+1/+1", 0) for c in (first, second, bear)] == [2, 0, 0]  # Torgal and Watchwolf
    check(s)


# ---- 702.190: incubate X, X the spell's mana value (Brimaz, Blight of Oreskos) -------------------------------------------------------------------
def test_brimaz_incubates_for_a_phyrexian_creature_spell_only(cards):
    s = build(cards, [BRIMAZ, "Phyrexian Rager", "Grizzly Bears"], [])
    put(s, BRIMAZ)
    mana(s, B=1, G=1, C=3)
    cast_from(s, "Grizzly Bears")
    assert not [c for c in s.state.cards.values() if c.name == "Incubator"]
    cast_from(s, "Phyrexian Rager")
    inc = [c for c in s.state.cards.values() if c.name == "Incubator"]
    assert len(inc) == 1 and inc[0].counters.get("+1/+1") == 3  # mana value 3
    check(s)


# ---- 205.3: "except for Merfolk, Krakens, Leviathans, Octopuses, and Serpents" (Slinn Voda) -------------------------------------------------------
def test_slinn_voda_kicked_returns_every_creature_but_the_listed_kinds(cards):
    s = build(cards, [SLINN, "Grizzly Bears"], ["Merfolk of the Pearl Trident", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    put(s, "Merfolk of the Pearl Trident", "p2")
    put(s, "Grizzly Bears", "p2")
    mana(s, U=3, R=7)
    cast_from(s, SLINN, kicker=1)
    assert zone_of(s, "Grizzly Bears") == "p1:hand" and zone_of(s, "Grizzly Bears", "p2") == "p2:hand"
    assert zone_of(s, "Merfolk of the Pearl Trident", "p2") == "p2:battlefield" and zone_of(s, SLINN) == "p1:battlefield"
    check(s)


def test_slinn_voda_not_kicked_returns_nothing(cards):
    s = build(cards, [SLINN, "Grizzly Bears"], [])
    put(s, "Grizzly Bears")
    mana(s, U=2, R=6)
    cast_from(s, SLINN)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


# ---- 608.2c: "amass Orcs 5, mill five cards, then return a creature card from your graveyard to the battlefield" (Sauron, Lord of the Rings) ------
def test_sauron_amasses_mills_then_returns_a_creature_card(cards):
    s = build(cards, [SAURON, "Grizzly Bears"], [])
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    before = len(s.state.zones["p1:library"])
    mana(s, U=1, B=1, R=1, C=5)
    cast_from(s, SAURON)
    army = next(c for c in s.state.cards.values() if "Army" in (c.token.type_line if c.token else ""))
    assert army.counters.get("+1/+1") == 5
    assert len(s.state.zones["p1:library"]) == before - 1 - 5  # Sauron left it, five were milled
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, SAURON) == "p1:battlefield"
    check(s)


# ---- 205.1b: "If he wasn't a Spirit, return this card … He's a Spirit in addition to his other types." (Fang, Roku's Companion) ---------------------
def test_fang_returns_once_as_a_spirit(cards):
    s = build(cards, [FANG, "Murder", "Murder"], [])
    fang = put(s, FANG)
    kill(s, fang, "Murder", B=2, C=1)
    now = card_named(s, FANG)
    assert now.zone == "p1:battlefield" and "Spirit" in ch(s, now).subtypes and "Dragon" in ch(s, now).subtypes
    kill(s, now, "Murder", B=2, C=1)
    assert zone_of(s, FANG) == "p1:graveyard"  # a Spirit now: it stays dead
    check(s)
