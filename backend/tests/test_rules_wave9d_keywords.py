"""Wave 9D: keyword mechanics - graft N (702.58a), ... Each scenario uses real Oracle text and checks the replay and a
save/load round trip."""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, counters, on_field, to_hand, to_turn
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=(), keywords=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"9D-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=list(keywords), **extra)


EXTRA = [
    real("Simic Initiate", "{G}", 1, "Creature — Human Mutant",
         "Graft 1 (This creature enters with a +1/+1 counter on it. Whenever another creature enters, you may move a +1/+1 "
         "counter from this creature onto it.)", ("0", "0"), "G", ["Graft"]),
    real("Vigean Graftmage", "{2}{U}", 3, "Creature — Vedalken Wizard Mutant",
         "Graft 2 (This creature enters with two +1/+1 counters on it. Whenever another creature enters, you may move a "
         "+1/+1 counter from this creature onto it.)\n{1}{U}: Untap target creature with a +1/+1 counter on it.", ("0", "0"),
         "U", ["Graft"]),
    real("Llanowar Reborn", "", 0, "Land",
         "This land enters tapped.\n{T}: Add {G}.\nGraft 1 (This land enters with a +1/+1 counter on it. Whenever a creature "
         "enters, you may move a +1/+1 counter from this land onto it.)", None, "", ["Graft"]),
    real("Weapon Rack", "{4}", 4, "Artifact",
         "This artifact enters with three +1/+1 counters on it.\n{T}: Move a +1/+1 counter from this artifact onto target "
         "creature. Activate only as a sorcery."),
    real("Suntouched Myr", "{3}", 3, "Artifact Creature — Myr",
         "Sunburst (This creature enters with a +1/+1 counter on it for each color of mana spent to cast it.)", ("0", "0"),
         "", ["Sunburst"]),
    real("Pentad Prism", "{2}", 2, "Artifact",
         "Sunburst (This artifact enters with a charge counter on it for each color of mana spent to cast it.)\nRemove a charge "
         "counter from this artifact: Add one mana of any color.", None, "", ["Sunburst"]),
    real("Heliophial", "{5}", 5, "Artifact",
         "Sunburst (This artifact enters with a charge counter on it for each color of mana spent to cast it.)\n{2}, Sacrifice "
         "this artifact: It deals damage equal to the number of charge counters on it to any target.", None, "", ["Sunburst"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def answer(s, option="yes", limit=30):
    """Resolve the stack; a yes/no confirmation is answered ``option``, any other choice with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [option] if d.kind == "confirm" else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def cast_with(s, name, option="yes", pid="p1", **m):
    c = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=c.id)
    answer(s, option)
    return s.state.cards[c.id]


def ability(s, c, start):
    return next(i for i, a in enumerate(s.cards.resolve(c.name).get("oracle_text", "").split("\n")) if a.startswith(start))


# -- graft (702.58a) --------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Simic Initiate", "Vigean Graftmage", "Llanowar Reborn", "Weapon Rack"])
def test_graft_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_graft_enters_with_counters_and_moves_one_onto_a_creature_that_enters(cards):
    s = build(cards, "Vigean Graftmage", "Grizzly Bears")
    mage = cast_with(s, "Vigean Graftmage", U=1, C=2)
    assert counters(s, mage) == 2  # graft 2: enters with two +1/+1 counters
    bears = cast_with(s, "Grizzly Bears", G=1, C=1)
    assert (counters(s, mage), counters(s, bears)) == (1, 1)  # one counter moved onto the creature that entered
    roundtrip(s)


def test_graft_may_decline(cards):
    s = build(cards, "Simic Initiate", "Grizzly Bears")
    init = cast_with(s, "Simic Initiate", G=1)
    bears = cast_with(s, "Grizzly Bears", option="no", G=1, C=1)
    assert (counters(s, init), counters(s, bears)) == (1, 0)
    roundtrip(s)


def test_graft_does_not_trigger_without_a_counter(cards):
    s = build(cards, "Simic Initiate", "Grizzly Bears")
    init = cast_with(s, "Simic Initiate", G=1)
    act(s, "p1", type="set_counter", card_id=init.id, kind="+1/+1", value=0)
    bears = cast_with(s, "Grizzly Bears", G=1, C=1)
    assert (counters(s, init), counters(s, bears)) == (0, 0)  # the intervening "if" (603.4)
    roundtrip(s)


def test_graft_triggers_for_an_opponents_creature(cards):
    s = build(cards, "Simic Initiate", p2=("Grizzly Bears",))
    init = cast_with(s, "Simic Initiate", G=1)
    to_turn(s, 2)
    bears = cast_with(s, "Grizzly Bears", "yes", "p2", G=1, C=1)
    answer(s)
    assert (counters(s, init), counters(s, bears)) == (0, 1)
    roundtrip(s)


def test_a_graft_land_moves_its_counter_onto_any_creature(cards):
    s = build(cards, "Llanowar Reborn", "Grizzly Bears")
    land = to_hand(s, "Llanowar Reborn")
    act(s, "p1", type="play_land", card_id=land.id)
    answer(s)
    assert counters(s, land) == 1
    bears = cast_with(s, "Grizzly Bears", G=1, C=1)
    assert (counters(s, land), counters(s, bears)) == (0, 1)
    roundtrip(s)


def test_weapon_rack_moves_one_counter(cards):
    s = build(cards, "Weapon Rack", "Grizzly Bears")
    rack = cast_with(s, "Weapon Rack", C=4)
    bears = on_field(s, "Grizzly Bears")
    assert counters(s, rack) == 3
    act(s, "p1", type="activate_ability", card_id=rack.id, ability=ability(s, rack, "{T}"), targets=[bears.id])
    answer(s)
    assert (counters(s, rack), counters(s, bears)) == (2, 1)
    roundtrip(s)


# -- sunburst (702.44a) -----------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Suntouched Myr", "Pentad Prism", "Heliophial"])
def test_sunburst_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_sunburst_creature_enters_with_a_plus_counter_for_each_color_spent(cards):
    s = build(cards, "Suntouched Myr")
    myr = cast_with(s, "Suntouched Myr", R=1, G=1, C=1)  # two colors, plus colorless
    assert counters(s, myr) == 2 and myr.zone == "p1:battlefield"
    roundtrip(s)


def test_sunburst_counts_a_color_once_however_much_of_it_was_spent(cards):
    s = build(cards, "Suntouched Myr")
    myr = cast_with(s, "Suntouched Myr", R=3)
    assert counters(s, myr) == 1
    roundtrip(s)


def test_sunburst_noncreature_gets_charge_counters_and_spends_them(cards):
    s = build(cards, "Pentad Prism")
    prism = cast_with(s, "Pentad Prism", U=1, B=1)
    assert counters(s, prism, "charge") == 2 and counters(s, prism) == 0
    act(s, "p1", type="activate_ability", card_id=prism.id, ability=ability(s, prism, "Remove"))
    answer(s)
    assert counters(s, prism, "charge") == 1
    roundtrip(s)


def test_sunburst_with_only_colorless_mana_adds_nothing(cards):
    s = build(cards, "Pentad Prism")
    prism = cast_with(s, "Pentad Prism", C=2)
    assert counters(s, prism, "charge") == 0  # 702.44b: only colored mana counts
    roundtrip(s)


def test_sunburst_charge_counters_count_as_it_is_sacrificed(cards):
    s = build(cards, "Heliophial")
    hel = cast_with(s, "Heliophial", W=1, U=1, B=1, R=1, G=1)
    assert counters(s, hel, "charge") == 5
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=hel.id, ability=ability(s, hel, "{2}"), targets=["p2"])
    answer(s)
    assert s.state.players["p2"].life == 40 - 5
    roundtrip(s)
