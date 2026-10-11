"""Wave 36A: the other cards the graveyard-history selectors and the new trigger wordings turned FULL (CR 2026-09-25, real Oracle text,
tests/fixtures/wave36a_cards.json from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2b: a target is checked again as the spell or ability resolves; 115.4: "up to two target" chooses zero, one or two; 400.7: the card in the graveyard
  is the object that was put there this turn.
* 701.21a, 603.10a, 700.4: sacrificing / dying looks back in time; 707.12: a copy of a card cast without paying its mana cost; 707.9: copy effects.
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
from tests.test_rules_conditionals import creature, settle, until
from tests.wave9c_kit import build, card_named, cast, check, mana, pt, put, to_hand
from tests.wave36a_kit import (
    attack,
    block,
    mill,
    next_own_turn,
    offered,
    pick,
    ready,
    to_gy,
    to_turn_of,
    zone,
)

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave36a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w36a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Brought Back", "Continue?", "Faith's Reward", "Grim Return", "Reenact the Crime", "Gerrard, Weatherlight Hero", "Lobelia Sackville-Baggins",
        "No Rest for the Wicked", "Othelm, Sigardian Outcast", "Salvager of Ruin", "Activated Sleeper", "Skyfire Kirin", "Kiora, Master of the Depths",
        "Bartered Cow", "Aang and Katara", "Serra Inquisitors", "Thor, Guardian of Midgard", "Feldon, Ronom Excavator", "Rakdos, the Muscle"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_gained_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


def dead_and_old(cards, spells, *, theirs=(), **kw):
    """Alice's turn 3: the Elves and the Ring went to the graveyard on an earlier turn, then this turn the Bears died, the Finks was milled."""
    s = build(cards, [*spells, "Grizzly Bears", "Llanowar Elves", "Sol Ring", "Kitchen Finks"], theirs=theirs, forests=20, **kw)
    put(s, "Llanowar Elves")
    to_gy(s, "Llanowar Elves")
    put(s, "Sol Ring")
    to_gy(s, "Sol Ring")
    next_own_turn(s)
    return s


def die(s, name, pid="p1"):
    put(s, name, pid)
    to_gy(s, name, pid)


# -- Brought Back / Continue? -------------------------------------------------------------------------------------------------------------
def test_brought_back_returns_up_to_two_permanents_that_were_put_there_from_the_battlefield_tapped(cards):
    s = dead_and_old(cards, ["Brought Back"])
    die(s, "Grizzly Bears")
    mill(s, "Kitchen Finks")
    to_hand(s, "Brought Back")
    mana(s, W=2)
    bears, elves, ring, finks = (card_named(s, n) for n in ("Grizzly Bears", "Llanowar Elves", "Sol Ring", "Kitchen Finks"))
    with pytest.raises(ActionError):  # (the Elves was put there last turn)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Brought Back").id, targets=[bears.id, elves.id], target_counts=[2])
    with pytest.raises(ActionError):  # (the Finks was milled: from a library)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Brought Back").id, targets=[bears.id, finks.id], target_counts=[2])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Brought Back").id, targets=[bears.id], target_counts=[1])  # ("up to two": one is enough)
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:battlefield" and s.state.cards[bears.id].tapped
    assert s.state.cards[elves.id].zone == "p1:graveyard" and s.state.cards[ring.id].zone == "p1:graveyard"
    check(s)


def test_brought_back_returns_two(cards):
    s = dead_and_old(cards, ["Brought Back"])
    die(s, "Grizzly Bears")
    die(s, "Kitchen Finks")
    to_hand(s, "Brought Back")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Brought Back").id,
        targets=[card_named(s, "Grizzly Bears").id, card_named(s, "Kitchen Finks").id], target_counts=[2])
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:battlefield" and zone(s, "Kitchen Finks") == "p1:battlefield"
    check(s)


def test_continue_returns_creatures_that_died_this_turn(cards):
    s = dead_and_old(cards, ["Continue?"])
    die(s, "Grizzly Bears")
    to_hand(s, "Continue?")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Continue?").id, targets=[card_named(s, "Grizzly Bears").id], target_counts=[1])
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:battlefield" and not s.state.cards[card_named(s, "Grizzly Bears").id].tapped
    check(s)


# -- Faith's Reward / Grim Return -------------------------------------------------------------------------------------------------------
def test_faiths_reward_returns_every_permanent_card_put_there_from_the_battlefield(cards):
    s = dead_and_old(cards, ["Faith's Reward"])
    die(s, "Grizzly Bears")
    mill(s, "Kitchen Finks")
    to_hand(s, "Faith's Reward")
    mana(s, W=1, G=3)
    cast(s, "Faith's Reward")
    assert zone(s, "Grizzly Bears") == "p1:battlefield"
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and zone(s, "Sol Ring") == "p1:graveyard" and zone(s, "Kitchen Finks") == "p1:graveyard"
    check(s)


def test_grim_return_takes_a_creature_that_died_this_turn_from_any_graveyard(cards):
    s = dead_and_old(cards, ["Grim Return"], theirs=["Grizzly Bears", "Young Wolf"])
    die(s, "Grizzly Bears", "p2")
    to_gy(s, "Young Wolf", "p2")  # (from the library, not the battlefield)
    to_hand(s, "Grim Return")
    mana(s, B=1, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grim Return").id)
    assert offered(s) == ["Grizzly Bears"]
    pick(s, "Grizzly Bears")
    settle(s)
    bears = card_named(s, "Grizzly Bears", "p2")
    assert bears.zone == "p1:battlefield" and bears.controller == "p1" and bears.owner == "p2"
    check(s)


# -- Gerrard, Weatherlight Hero --------------------------------------------------------------------------------------------------------------
def test_gerrard_exiles_itself_and_returns_the_artifacts_and_creatures_that_died_this_turn(cards):
    s = dead_and_old(cards, ["Gerrard, Weatherlight Hero"])
    put(s, "Gerrard, Weatherlight Hero")
    die(s, "Grizzly Bears")
    put(s, "Kitchen Finks")
    act(s, "p1", type="move", card_ids=[card_named(s, "Kitchen Finks").id], to={"zone": "exile"})  # (not a graveyard card at all)
    act(s, "p1", type="set_damage", card_ids=[card_named(s, "Gerrard, Weatherlight Hero").id], value=9)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert zone(s, "Gerrard, Weatherlight Hero") == "p1:exile"  # ("exile it" first: Gerrard isn't one of the cards returned)
    assert zone(s, "Grizzly Bears") == "p1:battlefield"
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and zone(s, "Sol Ring") == "p1:graveyard"  # (put there on an earlier turn)
    check(s)


# -- Lobelia Sackville-Baggins -----------------------------------------------------------------------------------------------------------------
def test_lobelia_exiles_a_creature_that_died_in_an_opponents_graveyard_and_makes_treasures_by_its_power(cards):
    s = dead_and_old(cards, ["Lobelia Sackville-Baggins"], theirs=["Grizzly Bears", "Llanowar Elves"])
    die(s, "Grizzly Bears", "p2")
    die(s, "Llanowar Elves")  # (your own graveyard: not "an opponent's")
    to_hand(s, "Lobelia Sackville-Baggins")
    mana(s, B=1, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lobelia Sackville-Baggins").id)
    settle(s)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert zone(s, "Grizzly Bears", "p2") == "p2:exile" and len(treasures) == 2  # (the Bears' power, 2)
    check(s)


# -- No Rest for the Wicked / Salvager of Ruin / Othelm -----------------------------------------------------------------------------------------
def test_no_rest_for_the_wicked_returns_the_creatures_that_died_this_turn(cards):
    s = dead_and_old(cards, ["No Rest for the Wicked"])
    put(s, "No Rest for the Wicked")
    die(s, "Grizzly Bears")
    act(s, "p1", type="activate_ability", card_id=card_named(s, "No Rest for the Wicked").id, ability=0)
    settle(s)
    assert zone(s, "No Rest for the Wicked") == "p1:graveyard"  # (sacrificed as the cost)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Llanowar Elves") == "p1:graveyard"
    check(s)


def test_salvager_of_ruin_returns_a_permanent_that_died_this_turn(cards):
    s = dead_and_old(cards, ["Salvager of Ruin"])
    put(s, "Salvager of Ruin")
    ready(s, "Salvager of Ruin")
    die(s, "Grizzly Bears")
    mill(s, "Kitchen Finks")
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Salvager of Ruin").id, ability=0)
    assert offered(s) == ["Grizzly Bears"]  # (601.2c: targets are chosen before the cost is paid, so the Salvager, still on the battlefield, is no target)
    pick(s, "Grizzly Bears")
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Kitchen Finks") == "p1:graveyard"
    check(s)


def test_othelm_returns_a_creature_that_died_this_turn_tapped(cards):
    s = dead_and_old(cards, ["Othelm, Sigardian Outcast"])
    put(s, "Othelm, Sigardian Outcast")
    ready(s, "Othelm, Sigardian Outcast")
    die(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Othelm, Sigardian Outcast").id, ability=0)
    assert offered(s) == ["Grizzly Bears"]
    pick(s, "Grizzly Bears")
    settle(s)
    bears = card_named(s, "Grizzly Bears")
    assert bears.zone == "p1:battlefield" and s.state.cards[bears.id].tapped
    check(s)


# -- Reenact the Crime / Activated Sleeper --------------------------------------------------------------------------------------------------------
def test_reenact_the_crime_copies_a_card_put_into_a_graveyard_this_turn_from_anywhere(cards):
    s = dead_and_old(cards, ["Reenact the Crime", "Lightning Bolt"])
    mill(s, "Lightning Bolt")
    mill(s, "Kitchen Finks")
    to_hand(s, "Reenact the Crime")
    mana(s, U=3, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Reenact the Crime").id)
    assert offered(s) == ["Kitchen Finks", "Lightning Bolt"]  # (nonland cards put there this turn: not the Elves and the Ring, put there last turn)
    pick(s, "Lightning Bolt")
    d = s.state.rules.decision
    assert "without paying its mana cost" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert offered(s) == ["Alice", "Bob"]
    pick(s, "Bob")
    settle(s)
    assert s.state.players["p2"].life == 37 and zone(s, "Lightning Bolt") == "p1:exile"
    check(s)


def test_activated_sleeper_may_enter_as_a_copy_of_a_creature_that_died_this_turn(cards):
    from app.rules.plan import Plan

    s = dead_and_old(cards, ["Activated Sleeper"])
    die(s, "Grizzly Bears")
    mill(s, "Kitchen Finks")
    to_hand(s, "Activated Sleeper")
    mana(s, B=1, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Activated Sleeper").id)
    assert offered(s) == ["Don't copy anything (it enters as itself)", "Grizzly Bears (Alice)"]  # (not the Elves of last turn, nor the milled Finks)
    pick(s, "Grizzly Bears (Alice)")
    settle(s)
    sleeper = card_named(s, "Activated Sleeper")
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[sleeper.id])
    assert sleeper.zone == "p1:battlefield" and ch.name == "Grizzly Bears" and {"Phyrexian", "Bear"} <= set(ch.subtypes)
    assert pt(s, "Activated Sleeper") == (2, 2)  # (707.9b: a Phyrexian in addition)
    check(s)


# -- Skyfire Kirin -------------------------------------------------------------------------------------------------------------------------------
def answer_all(s, limit=6):
    """Answer what comes up: a "may" with yes, a choice with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            return
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else [o.id for o in d.options][: max(1, d.min_choices)])


def test_skyfire_kirin_steals_a_creature_with_the_mana_value_of_the_spell_until_end_of_turn(cards):
    s = build(cards, ["Skyfire Kirin", "Reach Through Mists"], theirs=["Llanowar Elves", "Grizzly Bears"], forests=20)
    put(s, "Skyfire Kirin")
    put(s, "Llanowar Elves", "p2")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Reach Through Mists")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Reach Through Mists").id)
    assert offered(s) == ["Llanowar Elves"]  # (mana value 1, as the spell's: not the Bears, 2, nor the Kirin, 4)
    pick(s, "Llanowar Elves")
    answer_all(s)
    settle(s)
    elves = card_named(s, "Llanowar Elves", "p2")
    assert s.state.cards[elves.id].controller == "p1"
    until(s, lambda s: s.state.turn.number > 1 and s.state.turn.phase == "main1")
    assert s.state.cards[elves.id].controller == "p2"  # (until end of turn)
    check(s)


# -- Kiora, Master of the Depths: the emblem's "you may have it fight target creature" ----------------------------------------------------------------
def emblem_table(cards):
    s = build(cards, ["Grizzly Bears"], theirs=["Llanowar Elves"], forests=20)
    creature(s, "p1", "Emblem of Kiora", "0/0", "Token Enchantment — Emblem",
             "Whenever a creature you control enters, you may have it fight target creature.")
    put(s, "Llanowar Elves", "p2")
    to_hand(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    assert offered(s) == ["Grizzly Bears", "Llanowar Elves"]  # ("target creature": any, the one that entered too)
    pick(s, "Llanowar Elves")
    return s


def test_the_emblem_may_have_the_creature_that_entered_fight_a_target_creature(cards):
    s = emblem_table(cards)
    d = s.state.rules.decision
    assert d.kind == "confirm"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert zone(s, "Llanowar Elves", "p2") == "p2:graveyard" and zone(s, "Grizzly Bears") == "p1:battlefield"  # (the Bears it fought, not the emblem's controller's choice)
    check(s)


def test_the_emblem_does_nothing_when_you_decline(cards):
    s = emblem_table(cards)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["no"])
    settle(s)
    assert zone(s, "Llanowar Elves", "p2") == "p2:battlefield" and zone(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


# -- Bartered Cow ---------------------------------------------------------------------------------------------------------------------------------
def foods(s):
    return [c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield"]


def test_bartered_cow_makes_a_food_when_it_dies(cards):
    s = build(cards, ["Bartered Cow"], forests=20)
    put(s, "Bartered Cow")
    act(s, "p1", type="set_damage", card_ids=[card_named(s, "Bartered Cow").id], value=9)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert len(foods(s)) == 1
    check(s)


def test_bartered_cow_makes_a_food_when_you_discard_it(cards):
    s = build(cards, ["Bartered Cow", "Faithless Looting"], forests=20)
    to_hand(s, "Bartered Cow")
    to_hand(s, "Faithless Looting")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Faithless Looting").id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Bartered Cow"), next(o.id for o in d.options if o.label == "Forest")])
    settle(s)
    assert zone(s, "Bartered Cow") == "p1:graveyard" and len(foods(s)) == 1
    check(s)


def test_bartered_cow_makes_no_food_when_it_is_milled(cards):
    s = build(cards, ["Bartered Cow"], forests=20)
    mill(s, "Bartered Cow")
    settle(s)
    assert zone(s, "Bartered Cow") == "p1:graveyard" and foods(s) == []
    check(s)


# -- Aang and Katara / Serra Inquisitors -------------------------------------------------------------------------------------------------------------
def allies(s):
    return [c for c in s.state.cards.values() if c.name == "Ally" and c.zone == "p1:battlefield"]


def test_aang_and_katara_attacking_makes_an_ally_for_each_tapped_creature(cards):
    s = build(cards, ["Aang and Katara", "Grizzly Bears"], forests=20)
    put(s, "Aang and Katara")
    put(s, "Grizzly Bears")
    ready(s, "Aang and Katara", "Grizzly Bears")
    attack(s, card_named(s, "Aang and Katara"), card_named(s, "Grizzly Bears"))
    settle(s)
    assert len(allies(s)) == 2  # (the two attackers are tapped)
    check(s)


def test_aang_and_katara_entering_counts_the_tapped_creatures_then(cards):
    s = build(cards, ["Aang and Katara", "Grizzly Bears"], forests=20)
    put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[card_named(s, "Grizzly Bears").id])
    to_hand(s, "Aang and Katara")
    mana(s, G=2, W=1, U=1, R=2)
    cast(s, "Aang and Katara")
    assert len(allies(s)) == 1  # (the tapped Bears; Aang and Katara itself entered untapped)
    check(s)


def test_serra_inquisitors_gets_plus_two_power_blocking_a_black_creature(cards):
    from tests.wave36a_kit import attack_as

    s = build(cards, ["Serra Inquisitors"], theirs=["Dregscape Zombie"], forests=20)
    put(s, "Serra Inquisitors")
    put(s, "Dregscape Zombie", "p2")
    ready(s, "Dregscape Zombie", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Dregscape Zombie", "p2")], "p1")
    block(s, "p1", (card_named(s, "Serra Inquisitors"), card_named(s, "Dregscape Zombie", "p2")))
    settle(s)
    assert pt(s, "Serra Inquisitors") == (5, 3)
    check(s)


def test_serra_inquisitors_gets_plus_two_power_when_a_black_creature_blocks_it(cards):
    s = build(cards, ["Serra Inquisitors"], theirs=["Dregscape Zombie", "Grizzly Bears"], forests=20)
    put(s, "Serra Inquisitors")
    ready(s, "Serra Inquisitors")
    put(s, "Dregscape Zombie", "p2")
    attack(s, card_named(s, "Serra Inquisitors"))
    block(s, "p2", (card_named(s, "Dregscape Zombie", "p2"), card_named(s, "Serra Inquisitors")))
    settle(s)
    assert pt(s, "Serra Inquisitors") == (5, 3)
    check(s)


def test_serra_inquisitors_is_unchanged_blocked_by_a_creature_that_is_not_black(cards):
    s = build(cards, ["Serra Inquisitors"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Serra Inquisitors")
    ready(s, "Serra Inquisitors")
    put(s, "Grizzly Bears", "p2")
    attack(s, card_named(s, "Serra Inquisitors"))
    block(s, "p2", (card_named(s, "Grizzly Bears", "p2"), card_named(s, "Serra Inquisitors")))
    settle(s)
    assert pt(s, "Serra Inquisitors") == (3, 3)
    check(s)


# -- Thor / Feldon / Rakdos, the Muscle: "exile that many cards from the top of your library" ---------------------------------------------------
def permissions(s):
    return [p for p in s.state.rules.permissions]


def test_thor_exiles_that_many_cards_and_lets_you_play_them_this_turn(cards):
    s = build(cards, ["Thor, Guardian of Midgard", "Lightning Bolt"], forests=20)
    put(s, "Thor, Guardian of Midgard")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    d = s.state.rules.decision
    assert d.kind == "confirm"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert s.state.players["p2"].life == 37 and len(s.state.zones["p1:library"]) == library - 3  # (the Bolt's 3 damage: 3 cards)
    assert len(permissions(s)) == 3 and all(p.until == "end_of_turn" for p in permissions(s))
    check(s)


def test_thor_may_decline(cards):
    s = build(cards, ["Thor, Guardian of Midgard", "Lightning Bolt"], forests=20)
    put(s, "Thor, Guardian of Midgard")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["no"])
    settle(s)
    assert len(s.state.zones["p1:library"]) == library and permissions(s) == []
    check(s)


def test_thor_ignores_noncombat_damage_to_a_creature(cards):
    s = build(cards, ["Thor, Guardian of Midgard", "Lightning Bolt"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Thor, Guardian of Midgard")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[card_named(s, "Grizzly Bears", "p2").id])
    settle(s)
    assert zone(s, "Grizzly Bears", "p2") == "p2:graveyard" and len(s.state.zones["p1:library"]) == library and permissions(s) == []
    check(s)


def test_feldon_exiles_as_many_cards_as_the_damage_and_you_may_play_one_of_them(cards):
    s = build(cards, ["Feldon, Ronom Excavator", "Lightning Bolt"], forests=20)
    put(s, "Feldon, Ronom Excavator")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[card_named(s, "Feldon, Ronom Excavator").id])
    d = s.state.rules.decision
    assert d.prompt == "Choose one of them" and len(d.options) == 3  # (3 damage: three cards, one chosen)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[1].id])
    settle(s)
    assert len(s.state.zones["p1:library"]) == library - 3 and len(permissions(s)) == 1 and permissions(s)[0].until == "end_of_next_turn"
    check(s)


def test_rakdos_the_muscle_exiles_cards_equal_to_the_mana_value_of_the_sacrificed_creature(cards):
    s = build(cards, ["Rakdos, the Muscle", "Village Rites", "Grizzly Bears"], theirs=["Llanowar Elves"], forests=20)
    put(s, "Rakdos, the Muscle")
    put(s, "Grizzly Bears")
    to_hand(s, "Village Rites")
    mana(s, B=1)
    library = len(s.state.zones["p2:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Village Rites").id)
    pick(s, "Grizzly Bears")
    assert offered(s) == ["Alice", "Bob"]  # (target player)
    pick(s, "Bob")
    settle(s)
    assert len(s.state.zones["p2:library"]) == library - 2 and len(s.state.zones["p2:exile"]) == 2  # (Grizzly Bears: mana value 2)
    assert len(permissions(s)) == 2
    check(s)


def test_rakdos_the_muscle_ignores_its_own_sacrifice(cards):
    s = build(cards, ["Rakdos, the Muscle", "Village Rites"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Rakdos, the Muscle")
    to_hand(s, "Village Rites")
    mana(s, B=1)
    library = len(s.state.zones["p2:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Village Rites").id)
    settle(s)
    assert zone(s, "Rakdos, the Muscle") == "p1:graveyard" and len(s.state.zones["p2:library"]) == library
    check(s)
