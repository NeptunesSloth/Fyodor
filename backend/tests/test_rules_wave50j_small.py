"""Wave 50J: keyword soups (CR 2026-09-25), real Oracle text (tests/fixtures/wave50j_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 611.2c, 613.1f: "creatures you control gain first strike until end of turn if a creature you control has first strike. The same is true for flying, …" (Odric,
  Lunarch Marshal): one check per keyword as the ability resolves; the creatures affected are fixed then, and a variant ("hexproof from blue", 702.11d) is gained as
  the holder has it (the ruling of 2020-01-24).
* "each other creature you control gets +1/+1 if it has flying, +1/+1 if it has first strike, and so on for …" (Akroma, Vision of Ixidor): +1/+1 for each listed
  ability the creature has, a variant counting as the ability once; "partner" is partner and partner with, not "Partner—Character select".
* "the number of abilities from among flying, … found among creatures you control" (Odric, Blood-Cursed): each ability counts once, however many creatures have it.
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
from tests.test_rules_wave34b_activated import activate, attach, attack, block, next_turn, stops, to_phase
from tests.wave9c_kit import build, card_named, cast, check, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50j_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50j", number=f"J{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, answer="yes", target=None, limit=60):
    """Resolve everything: an optional ability is answered ``answer``, a target choice picks the option named ``target``, any other choice its first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for o in d.options if o.label == target]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else want or ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def keywords(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords


def combat(s):
    """To the beginning of combat; the triggers resolved."""
    stops(s)
    to_phase(s, "begin_combat")
    settle(s)


@pytest.mark.parametrize("name", ["Odric, Lunarch Marshal", "Akroma, Vision of Ixidor", "Odric, Blood-Cursed", "Bleeding Effect", "Majestic Myriarch",
                                  "Kaima, the Fractured Calm", "Havoc Eater", "Pia Nalaar, Chief Mechanic", "Rampaging Aetherhood", "Sensei Golden-Tail", "Kathril, Aspect Warper",
                                  "Concerted Effort", "Thunderous Orator", "Wonder Man, Hollywood Hero", "Kang the Conqueror"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_odric_gives_each_keyword_that_a_creature_has_to_all_creatures(cards):
    s = build(cards, mine=["Odric, Lunarch Marshal", "Serra Angel", "Sporeweb Weaver", "Grizzly Bears"], theirs=["Order of the White Shield"])
    for n in ("Odric, Lunarch Marshal", "Serra Angel", "Sporeweb Weaver", "Grizzly Bears"):
        put(s, n)
    put(s, "Order of the White Shield", "p2")
    combat(s)
    got = keywords(s, "Grizzly Bears")
    assert {"flying", "vigilance", "reach", "hexproof from"} <= got  # the variant is gained as the Weaver has it, not plain hexproof
    assert "hexproof" not in got and "first strike" not in got and "protection" not in got  # (an opponent's creature is no source)
    assert keywords(s, "Odric, Lunarch Marshal") >= {"flying", "vigilance", "reach"}
    ab = next(a for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, "Grizzly Bears").id]).abilities if "hexproof" in a.text.lower())
    assert ab.text.lower().startswith("hexproof from blue")
    check(s)


def test_odric_does_nothing_without_a_listed_keyword_and_fixes_the_creatures_when_it_resolves(cards):
    s = build(cards, mine=["Odric, Lunarch Marshal", "Grizzly Bears", "Serra Angel"])
    put(s, "Odric, Lunarch Marshal")
    put(s, "Grizzly Bears")
    combat(s)
    assert not keywords(s, "Grizzly Bears")
    put(s, "Serra Angel")  # (it came after: the creatures affected were fixed when the ability resolved, 611.2c)
    assert not keywords(s, "Grizzly Bears") and not keywords(s, "Odric, Lunarch Marshal")
    check(s)


def test_akroma_gives_plus_one_for_each_listed_ability(cards):
    s = build(cards, mine=["Akroma, Vision of Ixidor", "Serra Angel", "Sporeweb Weaver", "Grizzly Bears", "Thrasios, Triton Hero", "Donatello, the Brains",
                           "Order of the White Shield"])
    names = ["Akroma, Vision of Ixidor", "Serra Angel", "Sporeweb Weaver", "Grizzly Bears", "Thrasios, Triton Hero", "Donatello, the Brains", "Order of the White Shield"]
    for n in names:
        put(s, n)
    before = {n: pt(s, n) for n in names}
    combat(s)
    grew = {n: pt(s, n)[0] - before[n][0] for n in names}
    assert grew == {"Akroma, Vision of Ixidor": 0, "Serra Angel": 2, "Sporeweb Weaver": 2, "Grizzly Bears": 0, "Thrasios, Triton Hero": 1,
                    "Donatello, the Brains": 0, "Order of the White Shield": 1}
    check(s)


def test_odric_blood_cursed_counts_each_ability_once(cards):
    s = build(cards, mine=["Odric, Blood-Cursed", "Serra Angel", "Sporeweb Weaver", "Grizzly Bears"])
    for n in ("Serra Angel", "Sporeweb Weaver", "Grizzly Bears"):
        put(s, n)
    to_hand(s, "Odric, Blood-Cursed")
    mana(s, R=1, W=1, G=1)
    cast(s, "Odric, Blood-Cursed")
    settle(s)
    blood = [c for c in s.state.cards.values() if c.name == "Blood" and c.controller == "p1"]
    assert len(blood) == 4  # flying, vigilance, reach and hexproof (the variant counts as the ability)
    check(s)


def test_odric_blood_cursed_makes_none_without_abilities(cards):
    s = build(cards, mine=["Odric, Blood-Cursed", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    to_hand(s, "Odric, Blood-Cursed")
    mana(s, R=1, W=1, G=1)
    cast(s, "Odric, Blood-Cursed")
    settle(s)
    assert not [c for c in s.state.cards.values() if c.name == "Blood"]
    check(s)


# -- goad: "goaded this way" -------------------------------------------------------------------------------------------------------------------------
# 701.15a: the creatures a goad instruction goaded count for the sentence after it (Kaima: a +1/+1 counter for each, Havoc Eater: the total power).
def goaded(s, name, pid="p2"):
    from app.rules.keyword_actions import goaded_by

    return goaded_by(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]))


def to_graveyard(s, *names):
    for n in names:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})


def counters(s, name):
    return s.state.cards[card_named(s, name).id].counters


def test_kaima_counts_the_creatures_it_goaded(cards):
    s = build(cards, mine=["Kaima, the Fractured Calm", "Pacifism"], theirs=["Serra Angel", "Grizzly Bears"])
    put(s, "Kaima, the Fractured Calm")
    aura = put(s, "Pacifism")
    put(s, "Serra Angel", "p2")
    put(s, "Grizzly Bears", "p2")
    attach(s, aura, card_named(s, "Serra Angel", "p2"))
    stops(s)
    to_phase(s, "end")
    settle(s)
    assert goaded(s, "Serra Angel") == {"p1"} and not goaded(s, "Grizzly Bears")  # (only the enchanted creature)
    assert counters(s, "Kaima, the Fractured Calm") == {"+1/+1": 1}
    check(s)


def test_kaima_does_nothing_without_an_enchanted_creature(cards):
    s = build(cards, mine=["Kaima, the Fractured Calm"], theirs=["Grizzly Bears"])
    put(s, "Kaima, the Fractured Calm")
    put(s, "Grizzly Bears", "p2")
    stops(s)
    to_phase(s, "end")
    settle(s)
    assert not goaded(s, "Grizzly Bears") and not counters(s, "Kaima, the Fractured Calm")
    check(s)


def test_havoc_eater_counts_the_power_of_the_creature_it_goaded(cards):
    s = build(cards, mine=["Havoc Eater"], theirs=["Serra Angel", "Grizzly Bears"])
    put(s, "Serra Angel", "p2")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Havoc Eater")
    mana(s, R=2, G=5)
    cast(s, "Havoc Eater")
    settle(s, target="Serra Angel")
    assert goaded(s, "Serra Angel") == {"p1"} and counters(s, "Havoc Eater") == {"+1/+1": 4}  # (Serra Angel's power)
    check(s)


# -- bushido grant ------------------------------------------------------------------------------------------------------------------------------------
# 611.2a, 702.45a: "That creature gains bushido 1 and becomes a Samurai in addition to its other creature types." (Sensei Golden-Tail): no duration, so for good.
def test_sensei_golden_tail_gives_bushido_and_samurai_for_good(cards):
    s = build(cards, mine=["Sensei Golden-Tail", "Grizzly Bears"], theirs=["Grizzly Bears"])
    sensei = put(s, "Sensei Golden-Tail")
    bears = put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    next_turn(s)
    mana(s, W=2)
    activate(s, "p1", sensei, targets=[bears.id])
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id])
    assert "bushido" in ch.keywords and "Samurai" in ch.subtypes and s.state.cards[bears.id].counters == {"training": 1}
    attack(s, bears)
    block(s, (card_named(s, "Grizzly Bears", "p2"), bears))
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 3)  # (bushido 1: +1/+1 as it becomes blocked)
    check(s)


def test_sensei_golden_tail_does_not_give_bushido_to_another_creature(cards):
    s = build(cards, mine=["Sensei Golden-Tail", "Grizzly Bears", "Llanowar Elves"])
    sensei = put(s, "Sensei Golden-Tail")
    bears = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves")
    next_turn(s)
    mana(s, W=2)
    activate(s, "p1", sensei, targets=[bears.id])
    settle(s)
    assert "bushido" not in keywords(s, "Llanowar Elves") and "Samurai" not in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[elves.id]).subtypes
    check(s)


# -- power-up: "Each power-up ability of permanents you control can be activated an additional time." (Wonder Man) ----------------------------------------
# 702.193a: a power-up ability is activated only once; Wonder Man lets each one be activated one more time.
def test_wonder_man_lets_a_power_up_ability_be_activated_twice(cards):
    s = build(cards, mine=["Wonder Man, Hollywood Hero", "Serpent Specialist"])
    put(s, "Wonder Man, Hollywood Hero")
    snake = put(s, "Serpent Specialist")
    next_turn(s)
    for _ in range(2):
        mana(s, G=4)
        activate(s, "p1", snake)
        settle(s)
    assert counters(s, "Serpent Specialist") == {"+1/+1": 4}
    mana(s, G=4)
    with pytest.raises(ActionError, match="only twice"):
        activate(s, "p1", snake)
    check(s)


def test_kang_takes_an_extra_turn_in_which_no_power_up_ability_can_be_activated(cards):
    s = build(cards, mine=["Kang the Conqueror", "Serpent Specialist"])
    kang = put(s, "Kang the Conqueror")
    snake = put(s, "Serpent Specialist")
    next_turn(s)
    mana(s, U=8)
    activate(s, "p1", kang)
    settle(s)
    assert counters(s, "Kang the Conqueror") == {"+1/+1": 1}
    turn = s.state.turn.number
    to_phase(s, "main1", turn=turn + 1)  # the extra turn: Alice again
    assert s.state.turn.active_player == "p1"
    mana(s, G=4)
    with pytest.raises(ActionError, match="can't be activated this turn"):
        activate(s, "p1", snake)
    to_phase(s, "main1", turn=turn + 3)  # (Bob's turn came between; this is Alice's next one)
    mana(s, G=4)
    activate(s, "p1", snake)
    settle(s)
    assert counters(s, "Serpent Specialist") == {"+1/+1": 2}
    check(s)


def test_a_power_up_ability_is_activated_only_once_without_wonder_man(cards):
    s = build(cards, mine=["Serpent Specialist"])
    snake = put(s, "Serpent Specialist")
    next_turn(s)
    mana(s, G=8)
    activate(s, "p1", snake)
    settle(s)
    with pytest.raises(ActionError, match="activated once"):
        activate(s, "p1", snake)
    check(s)


# -- energy X: "pay one or more {E}" -----------------------------------------------------------------------------------------------------------------
# 107.14, 107.3f: the payer chooses how many {E} to pay (one or more) as they pay, and that number is the X of the instructions after it.
def energy(s, pid="p1"):
    return s.state.players[pid].resources.get("energy", 0)


def to_end_step(s):
    stops(s)
    to_phase(s, "end")


def test_pia_nalaar_makes_a_vehicle_as_big_as_the_energy_paid(cards):
    s = build(cards, mine=["Pia Nalaar, Chief Mechanic"])
    put(s, "Pia Nalaar, Chief Mechanic")
    act(s, "p1", type="resource", player="p1", key="energy", delta=5)
    to_end_step(s)
    d = s.state.rules.decision
    while d is None:  # (the trigger resolves, then asks how much to pay)
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert [o.label for o in d.options] == ["Pay 1 {E} (X = 1)", "Pay 2 {E} (X = 2)", "Pay 3 {E} (X = 3)", "Pay 4 {E} (X = 4)", "Pay 5 {E} (X = 5)", "Don't pay"]
    settle(s, answer="x:3")
    assert energy(s) == 2
    (jet,) = [c for c in s.state.cards.values() if c.name == "Nalaar Aetherjet"]
    assert pt(s, "Nalaar Aetherjet") == (3, 3) and keywords(s, "Nalaar Aetherjet") >= {"flying", "crew"}
    check(s)


def test_pia_nalaar_pays_nothing_and_makes_nothing_when_declined_or_without_energy(cards):
    s = build(cards, mine=["Pia Nalaar, Chief Mechanic"])
    put(s, "Pia Nalaar, Chief Mechanic")
    act(s, "p1", type="resource", player="p1", key="energy", delta=2)
    to_end_step(s)
    settle(s, answer="decline")
    assert energy(s) == 2 and not [c for c in s.state.cards.values() if c.name == "Nalaar Aetherjet"]
    check(s)
    s = build(cards, mine=["Pia Nalaar, Chief Mechanic"])
    put(s, "Pia Nalaar, Chief Mechanic")
    to_end_step(s)
    settle(s)  # (no energy: nothing is asked)
    assert energy(s) == 0 and not [c for c in s.state.cards.values() if c.name == "Nalaar Aetherjet"]
    check(s)


def test_rampaging_aetherhood_puts_that_many_counters_on_itself(cards):
    s = build(cards, mine=["Rampaging Aetherhood"])
    put(s, "Rampaging Aetherhood")
    to_phase(s, "upkeep", turn=3)
    settle(s, answer="x:3")  # (it gets energy equal to its power, 4, then pays three)
    assert energy(s) == 1 and counters(s, "Rampaging Aetherhood") == {"+1/+1": 3}
    check(s)


def test_havoc_eater_without_a_creature_to_goad_gets_no_counters(cards):
    s = build(cards, mine=["Havoc Eater"])
    to_hand(s, "Havoc Eater")
    mana(s, R=2, G=5)
    cast(s, "Havoc Eater")
    settle(s)
    assert not counters(s, "Havoc Eater")
    check(s)


# -- keyword soups with lines and counters ------------------------------------------------------------------------------------------------------------
def test_concerted_effort_gives_the_landwalk_and_protection_lines_as_written(cards):
    s = build(cards, mine=["Concerted Effort", "Order of the White Shield", "Stonybrook Banneret", "Grizzly Bears"])
    for n in ("Concerted Effort", "Order of the White Shield", "Stonybrook Banneret", "Grizzly Bears"):
        put(s, n)
    stops(s)
    to_phase(s, "upkeep", turn=2)
    settle(s)
    got = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, "Grizzly Bears").id])
    assert got.keywords >= {"islandwalk", "protection"} and any(a.text.lower().startswith("protection from black") for a in got.abilities)
    check(s)


def pick(s, **by_kind):
    """Resolve everything; "put a <kind> counter on which creature?" is answered with the creature named in ``by_kind`` (flying="Grizzly Bears", …)."""
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None:
            want = next((v for k, v in by_kind.items() if f"put a {k.replace('_', ' ')} counter" in d.prompt), None)
            ids = [o.id for o in d.options if o.label == want] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast_kathril(s):
    to_hand(s, "Kathril, Aspect Warper")
    mana(s, W=1, B=1, G=1, R=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kathril, Aspect Warper").id)  # (not the kit's cast: it settles every choice by itself)


def test_kathril_puts_a_counter_for_each_keyword_in_the_graveyard_where_the_player_chooses(cards):
    s = build(cards, mine=["Kathril, Aspect Warper", "Serra Angel", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    to_graveyard(s, "Serra Angel")
    cast_kathril(s)
    pick(s, flying="Grizzly Bears", vigilance="Llanowar Elves")
    assert counters(s, "Grizzly Bears") == {"flying": 1} and counters(s, "Llanowar Elves") == {"vigilance": 1}
    assert counters(s, "Kathril, Aspect Warper") == {"+1/+1": 2}  # (a counter for each counter put on a creature this way)
    assert {"flying"} <= keywords(s, "Grizzly Bears") and {"vigilance"} <= keywords(s, "Llanowar Elves")
    check(s)


def test_kathril_alone_puts_them_on_itself_and_counts_the_graveyard_once(cards):
    s = build(cards, mine=["Kathril, Aspect Warper", "Serra Angel", "Thrasios, Triton Hero"])
    to_graveyard(s, "Serra Angel", "Thrasios, Triton Hero")  # (Thrasios has only partner, which is not in her list)
    cast_kathril(s)
    pick(s)
    assert counters(s, "Kathril, Aspect Warper") == {"flying": 1, "vigilance": 1, "+1/+1": 2}
    check(s)


def test_kathril_does_nothing_without_a_listed_keyword_in_the_graveyard(cards):
    s = build(cards, mine=["Kathril, Aspect Warper", "Grizzly Bears"])
    to_graveyard(s, "Grizzly Bears")
    cast_kathril(s)
    pick(s)
    assert not counters(s, "Kathril, Aspect Warper")
    check(s)


def test_kathril_leaves_a_variant_of_hexproof_to_the_players(cards):
    s = build(cards, mine=["Kathril, Aspect Warper", "Sporeweb Weaver"])
    to_graveyard(s, "Sporeweb Weaver")  # (reach and hexproof from blue: the variant's counter isn't modeled, 122.1b)
    cast_kathril(s)
    for _ in range(10):
        if (d := s.state.rules.decision) is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.kind == "manual_resolution"
    check(s)
