"""Wave 9C: token-creation replacements for one kind of token that add a different token (614.1a, 614.16, 616.1),
researched against CR 2026-09-25: Queen Allenal of Ruadach ("creature tokens … plus a 1/1 white Soldier"), Stridehangar
Automaton ("artifact tokens … plus an additional 1/1 colorless Thopter … with flying"), Worldwalker Helm ("artifact
tokens … plus an additional Map token").

The added token is part of the same creation event (it never triggers another "plus" of the same kind: the satellite
rule of app/rules/extra_tokens.py); only tokens of the named card type are replaced; only tokens created under your
control (Queen Allenal, Stridehangar Automaton) / by you (Worldwalker Helm).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_attachments import build
from tests.test_rules_effects import replay_matches
from tests.test_rules_replacements2 import activate, permanent

QUEEN = ("If one or more creature tokens would be created under your control, those tokens plus a 1/1 white Soldier creature "
         "token are created instead.")
STRIDEHANGAR = ("If one or more artifact tokens would be created under your control, those tokens plus an additional 1/1 "
                "colorless Thopter artifact creature token with flying are created instead.")
HELM = "If you would create one or more artifact tokens, instead create those tokens plus an additional Map token."
ZOMBIES = "{1}: Create a 2/2 black Zombie creature token."
TREASURES = "{1}: Create a Treasure token."
THOPTER = "{1}: Create a 1/1 colorless Thopter artifact creature token with flying."


def count(s, name, pid="p1"):
    return len([c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone.endswith(":battlefield")])


def maker(s, text, pid="p1", name="Maker"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": "1",
                                                       "toughness": "1", "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


@pytest.mark.parametrize("line", [QUEEN, STRIDEHANGAR, HELM])
def test_the_lines_are_supported(line):
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics("Test", "Enchantment", line)).level == "FULL"


@pytest.mark.parametrize("line", [
    "If one or more land tokens would be created under your control, those tokens plus a 1/1 white Soldier creature token are "
    "created instead.",
    "If one or more creature tokens would be created, those tokens plus a 1/1 white Soldier creature token are created instead.",
    "If one or more creature tokens would be created under an opponent's control, those tokens plus a Food token are created "
    "instead.",
    "If you would create one or more creature tokens, instead create those tokens plus a 1/1 white Soldier creature token."])
def test_other_wordings_stay_manual(line):
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics("Test", "Enchantment", line)).level != "FULL"


def test_queen_allenal_adds_a_soldier_to_creature_tokens_only(cards):
    s = build(cards)
    permanent(s, "p1", "Queen Allenal of Ruadach", "Enchantment", QUEEN)
    activate(s, maker(s, ZOMBIES, name="Zombie Maker"))
    assert count(s, "Zombie") == 1 and count(s, "Soldier") == 1
    activate(s, maker(s, TREASURES, name="Treasure Maker"))
    assert count(s, "Treasure") == 1 and count(s, "Soldier") == 1  # (an artifact, not a creature token)
    replay_matches(s)


def test_stridehangar_automaton_adds_a_flying_thopter_to_artifact_tokens(cards):
    s = build(cards)
    permanent(s, "p1", "Stridehangar Automaton", "Enchantment", STRIDEHANGAR)
    activate(s, maker(s, TREASURES))
    assert count(s, "Treasure") == 1 and count(s, "Thopter") == 1
    thopter = next(c for c in s.state.cards.values() if c.name == "Thopter")
    from tests.test_rules_attachments import ch

    assert "Artifact" in ch(s, thopter).types and "flying" in {k.lower() for k in ch(s, thopter).keywords}
    replay_matches(s)


def test_the_added_artifact_creature_is_part_of_the_same_event(cards):
    """A Thopter is itself an artifact token, but what the automaton adds does not add another Thopter (614.5)."""
    s = build(cards)
    permanent(s, "p1", "Stridehangar Automaton", "Enchantment", STRIDEHANGAR)
    activate(s, maker(s, THOPTER, name="Thopter Maker"))
    assert count(s, "Thopter") == 2  # (the one it made and one added: not three)
    replay_matches(s)


def test_worldwalker_helm_adds_a_map_to_artifact_tokens_only(cards):
    s = build(cards)
    permanent(s, "p1", "Worldwalker Helm", "Enchantment", HELM)
    activate(s, maker(s, TREASURES, name="Treasure Maker"))
    assert count(s, "Treasure") == 1 and count(s, "Map") == 1
    activate(s, maker(s, ZOMBIES, name="Zombie Maker"))
    assert count(s, "Zombie") == 1 and count(s, "Map") == 1
    replay_matches(s)


def test_queen_and_helm_together_both_apply_to_an_artifact_creature_token(cards):
    """A Thopter is an artifact creature token: Queen Allenal adds a Soldier and the Helm a Map, each once to the event
    (the creating player orders them when it matters, 616.1)."""
    s = build(cards)
    permanent(s, "p1", "Queen Allenal of Ruadach", "Enchantment", QUEEN)
    permanent(s, "p1", "Worldwalker Helm", "Enchantment", HELM)
    activate(s, maker(s, THOPTER, name="Thopter Maker"))
    from tests.test_rules_replacements2 import answer, decision

    while decision(s) is not None:
        d = decision(s)
        answer(s, d.options[0].id)
    assert count(s, "Thopter") == 1 and count(s, "Soldier") == 1 and count(s, "Map") == 1
    replay_matches(s)


def test_a_creature_added_by_another_replacement_makes_the_event_one_of_creature_tokens(cards):
    """616.1: after the Automaton adds its Thopter the event creates a creature token, so Queen Allenal applies to it (once);
    the order the player picks doesn't change the result."""
    from tests.test_rules_replacements2 import answer, decision

    for pick in (0, 1):
        s = build(cards)
        permanent(s, "p1", "Queen Allenal of Ruadach", "Enchantment", QUEEN)
        permanent(s, "p1", "Stridehangar Automaton", "Enchantment", STRIDEHANGAR)
        activate(s, maker(s, TREASURES, name="Treasure Maker"))
        while decision(s) is not None:
            d = decision(s)
            answer(s, d.options[min(pick, len(d.options) - 1)].id)
        assert count(s, "Treasure") == 1 and count(s, "Thopter") == 1 and count(s, "Soldier") == 1, pick
        replay_matches(s)
