"""Wave 24A: copy effects with exceptions (CR 707.9, 707.2, 613.2) — "enters as a copy … except …".

* 707.9e: "except it enters with an additional +1/+1 counter on it" is an additional effect of the replacement, not a copiable value
  (Spark Double, Altered Ego); 707.9f: "if it's a creature" is judged on what the copy would be (Moritte of the Frost copying a land
  that is only a creature until end of turn gets none — here a plain noncreature permanent).
* 707.9b: "it's an artifact … loses all other card types" sets the card types (Imposter Mech, Machine God's Effigy); "it's legendary and
  snow in addition to its other types"; 707.9a: a quoted ability of the copy names itself (Sakashima the Impostor).
* 707.9c-d: "it doesn't copy that creature's color" (Vesuvan Doppelganger keeps its own).

Real Oracle text (tests/fixtures/wave24a_copy_cards.json, from data/cards.sqlite); each scenario replays and round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.state import GameState
from app.rules import copying, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, named, to_hand, token
from tests.test_rules_copy import cast_clone, choose, decision, on_battlefield, pay
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24a_copy_cards.json").read_text("utf-8"))
SKIP = {"Grizzly Bears", "Sol Ring"}
EXTRA = [card(c["name"], set_code="t24c", number=f"K{i:02d}", **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")})
         for i, c in enumerate(DATA) if c["name"] not in SKIP]
FODDER = [
    card("Probe Beast", set_code="t24c", number="K90", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Beast", oracle_text="", power="3",
         toughness="3", colors=["G"], color_identity=["G"]),
    card("Probe Legend", set_code="t24c", number="K91", mana_cost="{1}{R}", cmc=2.0, type_line="Legendary Creature — Human Wizard",
         oracle_text="", power="2", toughness="2", colors=["R"], color_identity=["R"]),
    card("Probe Cat", set_code="t24c", number="K93", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Cat", oracle_text="", power="2",
         toughness="2", colors=["R"], color_identity=["R"]),
    card("Probe Rock", set_code="t24c", number="K92", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text="{T}: Add {C}."),
]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FODDER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def counters(s, c):
    return dict(s.state.cards[c.id].counters)


def cast_copy(s, name, pick, **mana):
    """Cast ``name`` (to the hand first) and copy ``pick`` as it enters."""
    c = to_hand(s, name)
    pay(s, **mana)
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(8):
        d = decision(s)
        if d is not None and d.prompt.endswith("to copy"):
            choose(s, pick)
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pass_until_stack_empty(s)
    return s.state.cards[c.id]


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA if c["name"] in (
    "Sakashima the Impostor", "Spark Double", "Moritte of the Frost", "Altered Ego", "Imposter Mech", "Machine God's Effigy",
    "Vesuvan Doppelganger")])
def test_the_promoted_cards_are_full(name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [], "legalities": {"commander": "legal"}}).level == "FULL"


def test_spark_double_enters_with_an_additional_counter_and_is_not_legendary(cards):
    s = build(cards, "Spark Double", "Probe Legend")
    legend = on_battlefield(s, "Probe Legend")
    double = cast_copy(s, "Spark Double", legend.id, U=1, C=3)
    c = ch(s, double)
    assert c.name == "Probe Legend" and "Legendary" not in c.supertypes and c.pt == (3, 3)  # (a 2/2 with the +1/+1 counter)
    assert counters(s, double) == {"+1/+1": 1}
    assert counters(s, legend) == {}
    roundtrip(s)


def test_spark_double_of_a_planeswalker_enters_with_an_additional_loyalty_counter(cards):
    s = build(cards, "Spark Double", "Gideon, Ally of Zendikar")
    gideon = on_battlefield(s, "Gideon, Ally of Zendikar")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=4)  # (put there by hand: no loyalty counters yet, 306.5b)
    double = cast_copy(s, "Spark Double", gideon.id, U=1, C=3)
    assert ch(s, double).name == "Gideon, Ally of Zendikar" and counters(s, double) == {"loyalty": 5}  # 4 printed + 1 (707.9e, 306.5b)
    assert counters(s, gideon) == {"loyalty": 4}
    roundtrip(s)


def test_moritte_copies_a_creature_with_two_counters_changeling_legendary_and_snow(cards):
    s = build(cards, "Moritte of the Frost", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    moritte = cast_copy(s, "Moritte of the Frost", beast.id, G=1, U=2, C=2)
    c = ch(s, moritte)
    assert {"Legendary", "Snow"} <= set(c.supertypes) and "Changeling" in {k.capitalize() for k in c.keywords}
    assert counters(s, moritte) == {"+1/+1": 2} and c.pt == (5, 5)
    roundtrip(s)


def test_moritte_copying_a_noncreature_permanent_gets_no_counters_or_changeling(cards):
    s = build(cards, "Moritte of the Frost", "Probe Rock")
    rock = on_battlefield(s, "Probe Rock")
    moritte = cast_copy(s, "Moritte of the Frost", rock.id, G=1, U=2, C=2)  # 707.9f: it enters as a noncreature permanent
    c = ch(s, moritte)
    assert c.name == "Probe Rock" and {"Legendary", "Snow"} <= set(c.supertypes) and "changeling" not in c.keywords
    assert counters(s, moritte) == {}
    roundtrip(s)


def test_altered_ego_enters_with_x_additional_counters(cards):
    s = build(cards, "Altered Ego", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    ego = to_hand(s, "Altered Ego")
    pay(s, G=1, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=ego.id, x_value=2)
    for _ in range(8):
        d = decision(s)
        if d is not None and d.prompt.endswith("to copy"):
            choose(s, beast.id)
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert ch(s, s.state.cards[ego.id]).name == "Probe Beast" and counters(s, ego) == {"+1/+1": 2}
    roundtrip(s)


def test_sakashima_has_its_own_name_is_legendary_and_returns_itself(cards):
    s = build(cards, "Sakashima the Impostor", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    saka = cast_copy(s, "Sakashima the Impostor", beast.id, U=3, C=2)
    c = ch(s, saka)
    assert c.name == "Sakashima the Impostor" and "Legendary" in c.supertypes and "Beast" in c.subtypes and c.pt == (3, 3)
    abil = [a for a in c.abilities if a.kind == "activated"]
    assert abil and "Return" in abil[0].text and "‹granter›" not in abil[0].text
    roundtrip(s)


def test_imposter_mech_is_a_vehicle_artifact_with_crew_and_no_other_types(cards):
    s = build(cards, "Imposter Mech", "Probe Beast")
    beast = token(s, "p2", "Beast", "3/3")
    mech = cast_copy(s, "Imposter Mech", beast.id, U=1, C=3)
    c = ch(s, mech)
    assert c.types == {"Artifact"} and "Vehicle" in c.subtypes and "Beast" not in c.subtypes
    assert any(a.text.lower().startswith("crew 3") for a in c.abilities)
    roundtrip(s)


def test_machine_gods_effigy_is_an_artifact_that_taps_for_blue_and_is_no_creature(cards):
    s = build(cards, "Machine God's Effigy", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    effigy = cast_copy(s, "Machine God's Effigy", beast.id, C=4)
    c = ch(s, effigy)
    assert c.types == {"Artifact"} and c.name == "Probe Beast" and any("Add {U}" in a.text for a in c.abilities)
    roundtrip(s)


def test_vesuvan_doppelganger_keeps_its_own_color(cards):
    s = build(cards, "Vesuvan Doppelganger", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    dop = cast_copy(s, "Vesuvan Doppelganger", beast.id, U=2, C=3)
    c = ch(s, dop)
    assert c.name == "Probe Beast" and c.colors == {"U"} and c.pt == (3, 3)  # 707.9c: it doesn't copy the green
    assert any("become a copy of target creature" in a.text for a in c.abilities)
    roundtrip(s)


def test_vesuvan_doppelganger_becomes_a_copy_at_upkeep_keeping_its_color_and_the_ability(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, "Vesuvan Doppelganger", "Probe Beast", "Probe Cat")
    beast = on_battlefield(s, "Probe Beast")
    legend = on_battlefield(s, "Probe Cat")
    dop = cast_copy(s, "Vesuvan Doppelganger", beast.id, U=2, C=3)
    until(s, lambda s: s.state.turn.number == 3 and (bool(s.state.zones.get("stack")) or decision(s) is not None))
    for _ in range(12):
        d = decision(s)
        if d is not None:
            choose(s, legend.id if legend.id in {o.id for o in d.options} else d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    c = ch(s, s.state.cards[dop.id])
    assert c.name == "Probe Cat" and c.colors == {"U"} and c.pt == (2, 2) and any("become a copy of target creature" in a.text for a in c.abilities)
    replay_matches(s)


# -- grammar ----------------------------------------------------------------------------------------------------------------
def test_entering_counters_are_read_only_for_an_object_entering_as_a_copy():
    # 707.9e: a token copy or a permanent that becomes a copy has nothing to "enter with"
    assert copying.parse_excepts("it enters with an additional +1/+1 counter on it") is None
    ex = copying.parse_excepts("it enters with an additional +1/+1 counter on it if it's a creature", enters=True)
    assert ex is not None and ex.enter_counters == [{"counter": "+1/+1", "n": 1, "if_type": "Creature"}]


@pytest.mark.parametrize("text", [
    "it enters with a shield counter on it if you control that creature",  # (shield counters aren't automated)
    "it loses all other card types",  # (no type set by the exception: what would remain?)
    "it's a Vehicle artifact with crew 3 and it has frobnicate",
    "if it's a land, it has haste",  # (only creature / planeswalker conditions are read)
])
def test_other_exceptions_stay_manual(text):
    assert copying.parse_excepts(text, enters=True) is None
