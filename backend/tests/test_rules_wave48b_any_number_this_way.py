"""Wave 48B: "any number" as an additional cost, and the effect sized by how many were paid (CR 2026-09-25), real Oracle text (tests/fixtures/wave48b_cards.json).
Every scenario checks the replay and a save and a load.

* 601.2b: "As an additional cost to cast this spell, sacrifice any number of creatures." is announced with the cost; any number includes none ("You may choose to sacrifice no
  creatures", Corpse Cobble 2021-09-24). "You may sacrifice any number of Spirits" (Devouring Greed) is the same choice.
* 601.2h: the objects are sacrificed or tapped with the rest of the cost; "for each creature sacrificed this way" counts the ones paid, as they last existed (608.2h:
  Burn at the Stake 2012-05-01, the damage doesn't change if the creatures untap or leave before it resolves).
* 707.10: a copy of the spell uses the objects that paid for the original.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import settle
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of
from tests.wave9c_kit import reloaded as reloaded_session

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48b", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
CREW = ("Hill Giant", "Grizzly Bears", "Goblin Piker", "Gray Ogre", "Savannah Lions")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


FULL = ["Devouring Greed", "Devouring Rage", "Burn at the Stake", "Corpse Cobble", "Vicious Betrayal", "Plumb the Forbidden"]


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast_paying(s, name, chosen, **kw):
    """Cast ``name`` announcing its any-number cost, paid with these cards (none: paid with nothing)."""
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id, cost_choices=[{"component": 0, "cards": [x.id for x in chosen]}], **kw)
    settle(s)


def table(cards, spell, crew=CREW[:3]):
    s = build(cards, [spell, *crew])
    members = [put(s, n) for n in crew]
    to_hand(s, spell)
    return s, members


# ---- sacrifice, a creature pumped: Vicious Betrayal --------------------------------------------------------------------------------------------
def test_vicious_betrayal_with_nothing_sacrificed_gives_nothing(cards):
    s, crew = table(cards, "Vicious Betrayal", ("Gray Ogre", "Hill Giant"))
    mana(s, B=5)
    cast_paying(s, "Vicious Betrayal", [], targets=[crew[0].id])
    assert zone_of(s, "Gray Ogre") == "p1:battlefield" and zone_of(s, "Hill Giant") == "p1:battlefield"
    assert pt(s, "Gray Ogre") == (2, 2) and zone_of(s, "Vicious Betrayal") == "p1:graveyard"
    check(s)


def test_vicious_betrayal_gives_plus_two_plus_two_for_each_creature_sacrificed(cards):
    s, crew = table(cards, "Vicious Betrayal", ("Gray Ogre", "Hill Giant", "Goblin Piker", "Grizzly Bears"))
    mana(s, B=5)
    cast_paying(s, "Vicious Betrayal", crew[1:3], targets=[crew[0].id])  # (Hill Giant and Goblin Piker)
    assert [zone_of(s, n) for n in ("Hill Giant", "Goblin Piker", "Grizzly Bears")] == ["p1:graveyard", "p1:graveyard", "p1:battlefield"]
    assert pt(s, "Gray Ogre") == (6, 6)
    check(s)


def test_vicious_betrayal_can_sacrifice_its_own_target_and_the_spell_fizzles(cards):
    """601.2c, 608.2b: the target is chosen before the cost is paid; sacrificing it leaves the spell without a legal target."""
    s, crew = table(cards, "Vicious Betrayal", ("Gray Ogre", "Hill Giant"))
    mana(s, B=5)
    cast_paying(s, "Vicious Betrayal", crew, targets=[crew[0].id])
    assert zone_of(s, "Gray Ogre") == "p1:graveyard" and zone_of(s, "Hill Giant") == "p1:graveyard" and zone_of(s, "Vicious Betrayal") == "p1:graveyard"
    check(s)


def test_vicious_betrayal_asks_for_any_number_none_too(cards):
    """No ``cost_choices``: the caster is asked (any number of their creatures, none too); the other player only sees that they are choosing."""
    s, crew = table(cards, "Vicious Betrayal", ("Gray Ogre", "Hill Giant", "Goblin Piker"))
    mana(s, B=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Vicious Betrayal").id, targets=[crew[0].id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.min_choices == 0 and d.max_choices == 3
    assert sorted(o.card_id for o in d.options) == sorted(x.id for x in crew)
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting"
    s = reloaded_session(s)  # a save and a load in the middle of the question
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[crew[1].id, crew[2].id])
    settle(s)
    assert pt(s, "Gray Ogre") == (6, 6) and zone_of(s, "Hill Giant") == "p1:graveyard" and zone_of(s, "Goblin Piker") == "p1:graveyard"
    check(s)


def test_a_copy_of_vicious_betrayal_counts_the_creatures_that_paid_for_the_original(cards):
    """707.10: "If an effect of the copy refers to objects used to pay its costs, it uses the objects used to pay the costs of the original spell" (Bob copies Alice's
    spell with Reverberate): the copy gives +2/+2 for each of the two creatures Alice sacrificed, and so does the original."""
    s = build(cards, ["Vicious Betrayal", "Gray Ogre", "Hill Giant", "Goblin Piker"], ["Reverberate"])
    ogre, giant, piker = (put(s, n) for n in ("Gray Ogre", "Hill Giant", "Goblin Piker"))
    to_hand(s, "Vicious Betrayal")
    to_hand(s, "Reverberate", "p2")
    mana(s, B=5)
    mana(s, "p2", R=2)
    c = card_named(s, "Vicious Betrayal")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[ogre.id], cost_choices=[{"component": 0, "cards": [giant.id, piker.id]}])
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Reverberate", "p2").id, targets=[c.id])
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:graveyard" and zone_of(s, "Goblin Piker") == "p1:graveyard"
    assert pt(s, "Gray Ogre") == (10, 10)
    check(s)


# ---- tap: Burn at the Stake --------------------------------------------------------------------------------------------------------------------
def test_burn_at_the_stake_deals_three_damage_for_each_creature_tapped(cards):
    s, crew = table(cards, "Burn at the Stake")
    mana(s, R=5)
    cast_paying(s, "Burn at the Stake", crew[:2], targets=["p2"])
    assert all(s.state.cards[x.id].tapped for x in crew[:2]) and not s.state.cards[crew[2].id].tapped
    assert life(s, "p2") == 34
    check(s)


def test_burn_at_the_stake_with_no_creature_tapped_deals_no_damage(cards):
    s, crew = table(cards, "Burn at the Stake")
    mana(s, R=5)
    cast_paying(s, "Burn at the Stake", [], targets=["p2"])
    assert not any(s.state.cards[x.id].tapped for x in crew) and life(s, "p2") == 40 and zone_of(s, "Burn at the Stake") == "p1:graveyard"
    check(s)


def test_burn_at_the_stake_offers_only_untapped_creatures_and_can_tap_a_summoning_sick_one(cards):
    """Only untapped creatures you control can be tapped; tapping one to pay a cost isn't a {T} ability of its own (302.6), so one that just entered can be."""
    s, crew = table(cards, "Burn at the Stake")
    act(s, "p1", type="tap", card_ids=[crew[0].id], tapped=True)
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Burn at the Stake").id, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and sorted(o.card_id for o in d.options) == sorted(x.id for x in crew[1:])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    settle(s)
    assert life(s, "p2") == 34
    check(s)


def test_burn_at_the_stake_damage_does_not_change_when_a_tapped_creature_dies(cards):
    """2012-05-01 ruling: "The amount of damage Burn at the Stake deals won't change if any creatures tapped to cast it become untapped or leave the battlefield before it resolves.\""""
    s = build(cards, ["Burn at the Stake", "Hill Giant", "Gray Ogre", "Goblin Piker"], ["Murder"])
    crew = [put(s, n) for n in ("Hill Giant", "Gray Ogre", "Goblin Piker")]
    to_hand(s, "Burn at the Stake")
    to_hand(s, "Murder", "p2")
    mana(s, R=5)
    mana(s, "p2", B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Burn at the Stake").id, targets=["p2"], cost_choices=[{"component": 0, "cards": [x.id for x in crew]}])
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Murder", "p2").id, targets=[crew[0].id])
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:graveyard" and life(s, "p2") == 31
    check(s)


# ---- sacrifice "you may": Devouring Greed, Devouring Rage ---------------------------------------------------------------------------------------
def spirits_table(cards, spell):
    s = build(cards, [spell, "Wandering Ones", "Ageless Guardian", "Hill Giant"])
    spirits = [put(s, "Wandering Ones"), put(s, "Ageless Guardian")]
    giant = put(s, "Hill Giant")
    to_hand(s, spell)
    return s, spirits, giant


def test_devouring_greed_with_no_spirit_sacrificed_drains_two(cards):
    s, spirits, giant = spirits_table(cards, "Devouring Greed")
    mana(s, B=4)
    cast_paying(s, "Devouring Greed", [], targets=["p2"])
    assert life(s, "p2") == 38 and life(s, "p1") == 42
    check(s)


def test_devouring_greed_drains_two_plus_two_for_each_spirit_sacrificed_and_you_gain_that_much(cards):
    s, spirits, giant = spirits_table(cards, "Devouring Greed")
    mana(s, B=4)
    cast_paying(s, "Devouring Greed", spirits, targets=["p2"])
    assert zone_of(s, "Wandering Ones") == "p1:graveyard" and zone_of(s, "Ageless Guardian") == "p1:graveyard" and zone_of(s, "Hill Giant") == "p1:battlefield"
    assert life(s, "p2") == 34 and life(s, "p1") == 46
    check(s)


def test_devouring_greed_offers_the_spirits_only(cards):
    s, spirits, giant = spirits_table(cards, "Devouring Greed")
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Devouring Greed").id, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and sorted(o.card_id for o in d.options) == sorted(x.id for x in spirits)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[spirits[0].id])
    settle(s)
    assert life(s, "p2") == 36 and life(s, "p1") == 44
    check(s)


def test_devouring_rage_gives_three_power_and_three_more_for_each_spirit(cards):
    s, spirits, giant = spirits_table(cards, "Devouring Rage")
    mana(s, R=5)
    cast_paying(s, "Devouring Rage", spirits, targets=[giant.id])
    assert pt(s, "Hill Giant") == (12, 3)
    check(s)


def test_devouring_rage_with_no_spirit_sacrificed_gives_just_three_power(cards):
    s, spirits, giant = spirits_table(cards, "Devouring Rage")
    mana(s, R=5)
    cast_paying(s, "Devouring Rage", [], targets=[giant.id])
    assert pt(s, "Hill Giant") == (6, 3)
    check(s)


# ---- sacrifice, the total power: Corpse Cobble ---------------------------------------------------------------------------------------------------
def test_corpse_cobble_makes_a_zombie_as_big_as_the_total_power_sacrificed(cards):
    s, crew = table(cards, "Corpse Cobble", ("Hill Giant", "Gray Ogre", "Goblin Piker"))
    mana(s, U=1, B=1)
    cast_paying(s, "Corpse Cobble", crew)
    zombie = next(x for x in s.state.cards.values() if x.name == "Zombie" and x.zone == "p1:battlefield")
    ch = Plan(s.state, "p1", s.cards, None).ch(zombie)
    assert (sba.power(zombie, ch), sba.toughness(zombie, ch)) == (7, 7) and "menace" in ch.keywords
    assert all(zone_of(s, n) == "p1:graveyard" for n in ("Hill Giant", "Gray Ogre", "Goblin Piker"))
    check(s)


def test_corpse_cobble_with_no_creature_sacrificed_makes_a_zombie_that_dies(cards):
    """Ruling 2021-09-24: "You may choose to sacrifice no creatures to pay the additional cost. If you do, you'll create a 0/0 Zombie token. Unless something else is raising
    its toughness, the token will subsequently die.\""""
    s, crew = table(cards, "Corpse Cobble")
    mana(s, U=1, B=1)
    cast_paying(s, "Corpse Cobble", [])
    assert not any(x.name == "Zombie" and x.zone == "p1:battlefield" for x in s.state.cards.values())
    assert all(x.zone == "p1:battlefield" for x in s.state.cards.values() if x.name in CREW)
    check(s)


def test_corpse_cobble_cast_with_flashback_still_pays_the_additional_cost(cards):
    """Ruling 2021-09-24: "If you cast Corpse Cobble using flashback, you still pay its additional cost of sacrificing any number of creatures.\""""
    s, crew = table(cards, "Corpse Cobble", ("Hill Giant", "Gray Ogre"))
    act(s, "p1", type="move", card_ids=[card_named(s, "Corpse Cobble").id], to={"zone": "graveyard"})
    mana(s, U=1, B=1, C=3)
    cast_paying(s, "Corpse Cobble", crew)
    zombie = next(x for x in s.state.cards.values() if x.name == "Zombie" and x.zone == "p1:battlefield")
    assert zombie.is_token and zone_of(s, "Corpse Cobble") == "p1:exile" and zone_of(s, "Hill Giant") == "p1:graveyard"
    check(s)


# ---- "When you do, copy this spell for each creature sacrificed this way": Plumb the Forbidden ------------------------------------------------
def plumb_cast(cards, n, deck_extra=()):
    s = build(cards, ["Plumb the Forbidden", *CREW[:3], *deck_extra])
    crew = [put(s, x) for x in CREW[:3]]
    to_hand(s, "Plumb the Forbidden")
    mana(s, B=2)
    hand = len(s.state.zones["p1:hand"]) - 1  # (without Plumb the Forbidden itself)
    cast_paying(s, "Plumb the Forbidden", crew[:n])
    return s, crew, len(s.state.zones["p1:hand"]) - hand  # (the cards drawn)


def test_plumb_the_forbidden_with_nothing_sacrificed_is_one_draw_and_no_trigger(cards):
    s, crew, drawn = plumb_cast(cards, 0)
    assert life(s) == 39 and drawn == 1 and all(zone_of(s, x.name) == "p1:battlefield" for x in crew)
    check(s)


def test_plumb_the_forbidden_copies_itself_for_each_creature_sacrificed(cards):
    """Two creatures sacrificed: two copies, so three resolutions in all; each draws a card and loses 1 life."""
    s, crew, drawn = plumb_cast(cards, 2)
    assert [zone_of(s, x.name) for x in crew] == ["p1:graveyard", "p1:graveyard", "p1:battlefield"]
    assert life(s) == 40 - 3 and drawn == 3
    check(s)


def test_plumb_the_forbidden_is_a_spell_not_cast_when_copied_so_its_copies_do_not_copy(cards):
    """707.10: a copy isn't cast, so "when you cast this spell" doesn't trigger for it: one creature gives exactly one copy."""
    s, crew, drawn = plumb_cast(cards, 1)
    assert life(s) == 40 - 2 and drawn == 2
    check(s)
