"""The Oracle template library: exact matches become definitions, anything else stays manual."""

from __future__ import annotations

import pytest

from app.rules import oracle, scripts
from app.rules.characteristics import Characteristics, parse_type_line


def ch(name, type_line, text):
    sup, types, sub = parse_type_line(type_line)
    return Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                           abilities=tuple(oracle.parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"}))))


@pytest.mark.parametrize(("name", "type_line", "text", "expected"), [
    ("Elvish Visionary", "Creature — Elf", "When this creature enters, draw a card.",
     {"kind": "triggered", "trigger": "enters_self", "effects": [{"do": "draw", "who": "you", "n": 1}], "optional": False, "target": None}),
    ("Wall", "Creature — Wall", "When Wall enters, you gain 3 life.",
     {"kind": "triggered", "trigger": "enters_self", "effects": [{"do": "gain_life", "who": "you", "n": 3}], "optional": False, "target": None}),
    ("Merchant", "Creature", "When this creature enters, each opponent loses 2 life and you gain 2 life.",
     {"kind": "triggered", "trigger": "enters_self", "effects": [{"do": "lose_life", "who": "each_opponent", "n": 2},
                                                                  {"do": "gain_life", "who": "you", "n": 2}], "optional": False, "target": None}),
    ("Myr", "Artifact Creature", "When this creature dies, it deals 2 damage to any target.",
     {"kind": "triggered", "trigger": "dies_self", "effects": [{"do": "damage", "who": "target", "n": 2}], "optional": False,
      "target": {"what": "any"}}),
    ("Scholar", "Creature", "When this creature dies, you may draw a card.",
     {"kind": "triggered", "trigger": "dies_self", "effects": [{"do": "draw", "who": "you", "n": 1}], "optional": True, "target": None}),
    ("Healer", "Creature", "At the beginning of your upkeep, you gain 1 life.",
     {"kind": "triggered", "trigger": "upkeep_you", "effects": [{"do": "gain_life", "who": "you", "n": 1}], "optional": False, "target": None}),
    ("Battery", "Creature", "When this creature enters, you get {E}{E}{E}.",
     {"kind": "triggered", "trigger": "enters_self", "effects": [{"do": "player_counter", "who": "you", "counter": "energy", "n": 3}],
      "optional": False, "target": None}),
    ("Lightning Bolt", "Instant", "Lightning Bolt deals 3 damage to any target.",
     {"kind": "spell", "effects": [{"do": "damage", "who": "target", "n": 3}], "target": {"what": "any"}}),
    ("Murder", "Instant", "Destroy target creature.", {"kind": "spell", "effects": [{"do": "destroy", "who": "target"}], "target": {"what": "creature"}}),
    ("Unsummon", "Instant", "Return target creature to its owner's hand.",
     {"kind": "spell", "effects": [{"do": "bounce", "who": "target"}], "target": {"what": "creature"}}),
    ("Rally", "Instant", "Creatures you control get +1/+1 until end of turn.",
     {"kind": "spell", "effects": [{"do": "pump", "who": "creatures_you_control", "p": 1, "t": 1}], "target": None}),
    ("Soul Warden", "Creature", "Whenever another creature enters, you gain 1 life.",
     {"kind": "triggered", "trigger": "enters_other", "effects": [{"do": "gain_life", "who": "you", "n": 1}], "optional": False,
      "target": None, "filter": "another creature"}),
    ("Falls", "Land", "This land enters tapped.", {"kind": "replacement", "replacement": "enters_tapped", "effects": []}),
    ("Firebreather", "Creature", "{R}: This creature gets +1/+0 until end of turn.",
     {"kind": "activated", "cost": "{R}", "effects": [{"do": "pump", "who": "self", "p": 1, "t": 0}], "target": None}),
])
def test_templates(name, type_line, text, expected):
    assert scripts.definitions(ch(name, type_line, text)) == {0: expected}


@pytest.mark.parametrize("text", [
    "Destroy target creature of the chosen type.",  # a selector the engine doesn't know: never guessed
    "Whenever you commit a crime, you gain 1 life.",  # a trigger event the engine doesn't model yet
    "When this creature enters, draw a card for each foo you control.",
    "Counter target spell.",
    "When this creature enters, if you gained life this turn, draw a card.",  # (a condition not read yet)
])
def test_unknown_wordings_stay_manual(text):
    assert scripts.definitions(ch("X", "Creature", text)) == {} or \
        scripts.definitions(ch("X", "Instant", text)) == {}


def test_generic_grammar_now_reads_these():
    assert scripts.definitions(ch("X", "Instant", "Destroy target nonblack creature."))
    assert scripts.definitions(ch("X", "Creature", "Whenever another creature dies, you gain 1 life."))[0]["cond"]["event"] == "die"
    assert scripts.definitions(ch("X", "Creature", "When this creature enters, draw a card for each opponent you have."))


def test_a_spell_is_automated_only_as_a_whole():
    opt = ch("Opt", "Instant", "Scry 1.\nDraw a card.")
    assert [e["do"] for e in scripts.spell_definition(opt)["effects"]] == ["scry", "draw"]
    half = ch("Half", "Instant", "Draw a card.\nTarget player reveals their hand.")
    assert scripts.spell_definition(half) is None  # one manual line: the whole spell is resolved by hand


@pytest.mark.parametrize(("text", "type_line", "ok"), [
    # "it" after a target is that target
    ("Untap target creature. It gets +1/+4 and gains reach until end of turn.", "Instant", True),
    # "it" in a trigger about this object is this object
    ("When this creature dies, it deals 2 damage to any target.", "Creature", True),
    # "it" naming the object the event happened to: bound when it triggers (not self!)
    ("Whenever another creature you control enters, put a +1/+1 counter on it.", "Creature", True),
    ("Whenever a creature you control attacks, it gets +1/+0 until end of turn.", "Creature", True),
    # … but not one that left (a new object, 400.7), nor a spell just cast: manual
    ("Whenever another creature you control dies, return it to its owner's hand.", "Creature", False),
    ("Whenever you cast a creature spell, it gains haste until end of turn.", "Creature", False),
    ("At the beginning of your upkeep, put a +1/+1 counter on it.", "Creature", False),
])
def test_pronoun_it_is_resolved_or_refused(text, type_line, ok):
    defs = scripts.definitions(ch("X", type_line, text))
    assert bool(defs) == ok, text
    if ok:
        assert all(e.get("who") not in ("it", "self") for d in defs.values() for e in d["effects"]) \
            or "this creature" in text  # (resolved to the target / the event object, not the source)
        assert all(e.get("who") != "it" and "src" not in e for d in defs.values() for e in d["effects"])
    if "Untap target" in text:
        assert [e["who"] for e in defs[0]["effects"]] == ["target", "target", "target"]


@pytest.mark.parametrize(("text", "name", "expected"), [
    # 207.2c: an ability word has no rules meaning
    ("Landfall — Whenever a land you control enters, you gain 1 life.", "X",
     "Whenever a land you control enters, you gain 1 life."),
    ("Council’s dilemma — Draw a card.", "X", "Draw a card."),
    # Oracle's short names for a card
    ("Whenever Sharuum attacks, draw a card.", "Sharuum the Hegemon", "Whenever ~ attacks, draw a card."),
    ("Whenever Kiora attacks, draw a card.", "Kiora, the Rising Tide", "Whenever ~ attacks, draw a card."),
    # … but not a creature type that happens to start the name
    ("Other Soldier creatures you control get +1/+1.", "Soldier of the Pantheon",
     "Other Soldier creatures you control get +1/+1."),
])
def test_self_text(text, name, expected):
    assert scripts.self_text(text, name) == expected
