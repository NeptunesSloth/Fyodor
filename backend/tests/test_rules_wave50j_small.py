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
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import attach, stops, to_phase
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


@pytest.mark.parametrize("name", ["Odric, Lunarch Marshal", "Akroma, Vision of Ixidor", "Odric, Blood-Cursed", "Bleeding Effect", "Majestic Myriarch"])
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


def test_havoc_eater_without_a_creature_to_goad_gets_no_counters(cards):
    s = build(cards, mine=["Havoc Eater"])
    to_hand(s, "Havoc Eater")
    mana(s, R=2, G=5)
    cast(s, "Havoc Eater")
    settle(s)
    assert not counters(s, "Havoc Eater")
    check(s)
