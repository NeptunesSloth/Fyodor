"""The generic selector (app/rules/selectors.py): parsing Oracle noun phrases, and matching."""

from __future__ import annotations

import pytest

from app.rules import selectors as S
from app.rules.plan import Plan
from tests.test_rules_attachments import build, named, token


@pytest.mark.parametrize(("phrase", "fields"), [
    ("creature", {"types": ("Creature",)}),
    ("nonland permanent an opponent controls", {"not_types": ("Land",), "controller": "opponent"}),
    ("creature card with mana value 3 or less from your graveyard",
     {"zones": ("graveyard",), "zone_owner": "you", "card": True, "types": ("Creature",), "compare": (("mv", "<=", 3),)}),
    ("another untapped Goblin you control", {"subtypes": ("Goblin",), "controller": "you", "other": True, "tapped": False}),
    ("artifact or enchantment", {"types": ("Enchantment", "Artifact")}),
    ("artifact creature", {"types": ("Creature", "Artifact"), "extras": ("all_types",)}),
    ("Goblin creature", {"types": ("Creature",), "subtypes": ("Goblin",)}),
    ("creature with power 2 or less", {"types": ("Creature",), "compare": (("power", "<=", 2),)}),
    ("instant or sorcery spell", {"zones": ("stack",), "types": ("Sorcery", "Instant")}),
    ("black or red permanent", {"colors": ("R", "B")}),
    ("non-Human creature", {"types": ("Creature",), "not_subtypes": ("Human",)}),
    ("nontoken creature", {"types": ("Creature",), "token": False}),
    ("Elves you control", {"subtypes": ("Elf",), "controller": "you"}),
    ("creature with flying", {"types": ("Creature",), "with_keywords": ("flying",)}),
    ("opponent", {"player": "opponent"}),
])
def test_parse(phrase, fields):
    sel = S.parse(phrase)
    assert sel is not None
    for k, v in fields.items():
        assert getattr(sel, k) == v, (phrase, k)


@pytest.mark.parametrize("phrase", ["foo creature", "artifact creature or enchantment", "white and blue creature", ""])
def test_unknown_phrases_are_refused(phrase):
    assert S.parse(phrase) is None


def test_keys_are_compact_and_round_trip():
    sel = S.parse("another untapped Goblin you control")
    assert sel.key() == 'sel:{"controller":"you","other":true,"subtypes":["Goblin"],"tapped":false}'
    assert S.from_key(sel.key()) == sel


def test_matching(cards):
    s = build(cards)
    elf = token(s, "p1", "Elf1")
    act_tap = token(s, "p1", "Tapped")
    theirs = token(s, "p2", "Theirs", "4/4")
    from tests.game_helpers import act

    act(s, "p1", type="tap", card_ids=[act_tap.id], tapped=True)
    forest = named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})
    plan = Plan(s.state, "p1", cards, None)
    assert set(S.candidates(plan, S.parse("untapped creature you control"), "p1")) == {elf.id}
    assert S.candidates(plan, S.parse("creature an opponent controls with power 3 or greater"), "p1") == [theirs.id]
    assert S.candidates(plan, S.parse("land card from your graveyard"), "p1") == [forest.id]
    assert S.candidates(plan, S.parse("land card from your graveyard"), "p2") == []  # Bob's graveyard is empty
    assert elf.id not in S.candidates(plan, S.parse("other creature you control"), "p1", source=elf.id)
