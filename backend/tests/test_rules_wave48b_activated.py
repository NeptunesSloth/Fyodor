"""Wave 48B: "any number" / "one or more" in an activation cost, and the effect sized by how many were paid (CR 2026-09-25), real Oracle text
(tests/fixtures/wave48b_cards.json). Every scenario checks the replay and a save and a load.

* 602.2b, 601.2h: the objects are chosen and paid with the rest of the cost, all at once; "exiled this way" / "sacrificed this way" count the ones paid (Corpseweft 2015-02-25: "refers
  to that activation of the ability, not any creature cards that have been previously exiled").
* Emrakul's Evangel 2016-07-13: "You may choose to sacrifice no other non-Eldrazi creatures this way. Emrakul's Evangel's ability counts itself, so you'll get one Eldrazi Horror token."
* "One or more" needs at least one: with none to pay with, the ability can't be activated (118.3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import to_turn
from tests.test_rules_wave30h_linked_exile import settle
from tests.wave9c_kit import build, card_named, check, mana, put, zone_of
from tests.wave9c_kit import reloaded as reloaded_session

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48b", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Painbringer", "Emrakul's Evangel", "Corpseweft", "Swashbuckler Extraordinaire"])  # (Swashbuckler: "you may sacrifice any number of Treasures" of an optional payment stays its own instruction, not an activation cost)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def ability(s, name, start):
    c = card_named(s, name)
    return c, next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(c).abilities if a.text.startswith(start))


def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def tokens(s, name):
    return [x for x in s.state.cards.values() if x.name == name and x.zone == "p1:battlefield"]


def stats(s, c):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return sba.power(s.state.cards[c.id], ch), sba.toughness(s.state.cards[c.id], ch)


# ---- exile any number from the graveyard: Painbringer --------------------------------------------------------------------------------------
def painbringer_table(cards):
    s = build(cards, ["Painbringer", "Hill Giant", "Gray Ogre", "Goblin Piker"], ["Hill Giant"])
    pain = put(s, "Painbringer")
    victim = put(s, "Hill Giant", "p2")
    dead = [to_graveyard(s, n) for n in ("Hill Giant", "Gray Ogre", "Goblin Piker")]
    to_turn(s, 3)  # (no longer summoning sick)
    return s, pain, victim, dead


def test_painbringer_exiles_the_cards_chosen_and_the_target_gets_minus_that_many(cards):
    s, pain, victim, dead = painbringer_table(cards)
    c, idx = ability(s, "Painbringer", "{T}, Exile any number")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, targets=[victim.id], cost_choices=[{"component": 1, "cards": [x.id for x in dead[:2]]}])
    settle(s)
    assert [zone_of(s, n) for n in ("Hill Giant", "Gray Ogre", "Goblin Piker")] == ["p1:exile", "p1:exile", "p1:graveyard"]
    assert stats(s, victim) == (1, 1) and s.state.cards[pain.id].tapped
    check(s)


def test_painbringer_with_no_card_exiled_gives_nothing_but_the_ability_is_used(cards):
    s, pain, victim, dead = painbringer_table(cards)
    c, idx = ability(s, "Painbringer", "{T}, Exile any number")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, targets=[victim.id], cost_choices=[{"component": 1, "cards": []}])
    settle(s)
    assert all(zone_of(s, n) == "p1:graveyard" for n in ("Hill Giant", "Gray Ogre", "Goblin Piker")) and stats(s, victim) == (3, 3)
    check(s)


def test_painbringer_asks_which_cards_none_too_and_survives_a_save_in_the_question(cards):
    s, pain, victim, dead = painbringer_table(cards)
    c, idx = ability(s, "Painbringer", "{T}, Exile any number")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, targets=[victim.id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.min_choices == 0 and sorted(o.card_id for o in d.options) == sorted(x.id for x in dead)
    s = reloaded_session(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[x.id for x in dead])
    settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and all(zone_of(s, x.name) == "p1:exile" for x in dead)  # (-3/-3 on a 3/3)
    check(s)


# ---- sacrifice itself and any number of others, counted with itself: Emrakul's Evangel -------------------------------------------------------
def test_emrakuls_evangel_makes_a_horror_for_each_creature_sacrificed_itself_included(cards):
    s = build(cards, ["Emrakul's Evangel", "Hill Giant", "Gray Ogre"])
    put(s, "Emrakul's Evangel")
    crew = [put(s, "Hill Giant"), put(s, "Gray Ogre")]
    to_turn(s, 3)
    c, idx = ability(s, "Emrakul's Evangel", "{T}, Sacrifice")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, cost_choices=[{"component": 2, "cards": [x.id for x in crew]}])
    settle(s)
    assert zone_of(s, "Emrakul's Evangel") == "p1:graveyard" and all(zone_of(s, x.name) == "p1:graveyard" for x in crew)
    assert len(tokens(s, "Eldrazi Horror")) == 3
    check(s)


def test_emrakuls_evangel_alone_counts_itself_and_gives_one_horror(cards):
    s = build(cards, ["Emrakul's Evangel", "Hill Giant"])
    put(s, "Emrakul's Evangel")
    put(s, "Hill Giant")
    to_turn(s, 3)
    c, idx = ability(s, "Emrakul's Evangel", "{T}, Sacrifice")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, cost_choices=[{"component": 2, "cards": []}])
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:battlefield" and len(tokens(s, "Eldrazi Horror")) == 1
    check(s)


# ---- exile one or more: Corpseweft ---------------------------------------------------------------------------------------------------------
def corpseweft_table(cards):
    s = build(cards, ["Corpseweft", "Hill Giant", "Gray Ogre", "Goblin Piker"])
    put(s, "Corpseweft")
    dead = [to_graveyard(s, n) for n in ("Hill Giant", "Gray Ogre", "Goblin Piker")]
    return s, dead


def test_corpseweft_makes_a_zombie_horror_as_big_as_twice_the_cards_exiled(cards):
    s, dead = corpseweft_table(cards)
    mana(s, B=2)
    c, idx = ability(s, "Corpseweft", "{1}{B}, Exile")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, cost_choices=[{"component": 1, "cards": [x.id for x in dead[:2]]}])
    settle(s)
    horror = tokens(s, "Zombie Horror")
    assert len(horror) == 1 and stats(s, horror[0]) == (4, 4) and s.state.cards[horror[0].id].tapped
    assert zone_of(s, "Goblin Piker") == "p1:graveyard" and zone_of(s, "Hill Giant") == "p1:exile"
    check(s)


def test_corpseweft_counts_only_the_cards_of_this_activation(cards):
    """2015-02-25 ruling: "'Exiled this way' refers to that activation of the ability, not any creature cards that have been previously exiled.\""""
    s, dead = corpseweft_table(cards)
    mana(s, B=4)
    c, idx = ability(s, "Corpseweft", "{1}{B}, Exile")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, cost_choices=[{"component": 1, "cards": [dead[0].id]}])
    settle(s)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, cost_choices=[{"component": 1, "cards": [dead[1].id]}])
    settle(s)
    assert sorted(stats(s, h) for h in tokens(s, "Zombie Horror")) == [(2, 2), (2, 2)]
    check(s)


def test_corpseweft_with_no_creature_card_in_the_graveyard_cannot_be_activated(cards):
    s = build(cards, ["Corpseweft"])
    put(s, "Corpseweft")
    mana(s, B=2)
    c, idx = ability(s, "Corpseweft", "{1}{B}, Exile")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=c.id, ability=idx)
    assert not tokens(s, "Zombie Horror")


def test_corpseweft_cannot_be_paid_with_none_chosen(cards):
    s, dead = corpseweft_table(cards)
    mana(s, B=2)
    c, idx = ability(s, "Corpseweft", "{1}{B}, Exile")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=c.id, ability=idx, cost_choices=[{"component": 1, "cards": []}])
    assert all(zone_of(s, n) == "p1:graveyard" for n in ("Hill Giant", "Gray Ogre", "Goblin Piker")) and not tokens(s, "Zombie Horror")
