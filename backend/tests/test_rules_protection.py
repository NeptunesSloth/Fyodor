"""Protection (CR 702.16): DEBT — damage, enchanting/equipping, blocking, targeting."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import protection
from app.rules.characteristics import Characteristics
from tests.game_helpers import act
from tests.test_rules_combat import _blocks, _evasion_table, attack, automate, block
from tests.test_rules_mana_abilities import cast, named, table


def _ch(**kw) -> Characteristics:
    return Characteristics(name="X", **kw)


@pytest.mark.parametrize(("line", "source", "protected"), [
    ("Protection from red", _ch(colors=frozenset("R")), True),
    ("Protection from red", _ch(colors=frozenset("G")), False),
    ("Protection from black and from red", _ch(colors=frozenset("B")), True),
    ("Protection from multicolored", _ch(colors=frozenset("WU")), True),
    ("Protection from multicolored", _ch(colors=frozenset("W")), False),
    ("Protection from artifacts", _ch(types=frozenset({"Artifact", "Creature"})), True),
    ("Protection from Goblins", _ch(subtypes=frozenset({"Goblin"})), True),
    ("Protection from Elves", _ch(subtypes=frozenset({"Elf"})), True),
    ("Protection from everything", _ch(), True),
])
def test_qualities(line, source, protected):
    assert protection.supported(line)
    assert any(q(source) for q in protection.parse(line)) is protected


@pytest.mark.parametrize("line", ["Protection from mana value 3 or greater", "Protection from non-Spirit creatures",
                                  "Protection from the chosen player", "Protection from legendary creatures"])
def test_unknown_qualities_stay_manual(line):
    assert not protection.supported(line)


@pytest.mark.parametrize(("blocker_colors", "can_block"), [(("R",), False), (("G",), True), (("R", "G"), False)])
def test_cant_be_blocked_by_that_quality(cards, blocker_colors, can_block):
    s, sneak, guard = _evasion_table(cards, "Protection from red", blocker_colors=blocker_colors)
    assert _blocks(s, sneak, guard) is can_block


def test_combat_damage_from_that_quality_is_prevented(cards):
    s, sneak, guard = _evasion_table(cards, "", blocker_text="Protection from black", attacker_colors=("B",),
                                     blocker_colors=("W",))
    automate(s)
    attack(s, (sneak, "p2"))
    block(s, "p2", (guard, sneak))
    st = s.state
    assert st.cards[guard.id].damage == 0 and guard.id in st.cards  # the black Sneak's 2 damage is prevented
    assert sneak.id not in st.cards  # but the Guard's damage still kills the 2/2 Sneak


def test_cant_be_targeted_by_that_quality(cards):
    s = table(cards, "Mountain")
    act(s, "p2", type="create_token", player="p2", token={"name": "Knight", "type_line": "Token Creature — Knight",
                                                         "power": "2", "toughness": "2", "text": "Protection from red"})
    knight = next(c for c in s.state.cards.values() if c.name == "Knight")
    with pytest.raises(ActionError, match="legal target"):
        cast(s, "Lightning Bolt", targets=[knight.id])
    assert named(s, "Lightning Bolt").zone == "p1:hand"


@pytest.mark.parametrize(("color", "falls_off"), [("R", True), ("G", False)])
def test_aura_and_equipment_fall_off(cards, color, falls_off):
    s = table(cards)
    act(s, "p2", type="create_token", player="p2", token={"name": "Knight", "type_line": "Token Creature — Knight",
                                                         "power": "2", "toughness": "2", "text": "Protection from red"})
    act(s, "p1", type="create_token", player="p1", token={"name": "Red Aura", "type_line": "Token Enchantment — Aura",
                                                         "text": "Enchant creature", "colors": [color]})
    act(s, "p1", type="create_token", player="p1", token={"name": "Red Blade", "type_line": "Token Artifact — Equipment",
                                                         "text": "Equip {1}", "colors": [color]})
    st = s.state
    knight = next(c for c in st.cards.values() if c.name == "Knight")
    aura = next(c for c in st.cards.values() if c.name == "Red Aura")
    blade = next(c for c in st.cards.values() if c.name == "Red Blade")
    act(s, "p1", type="attach", card_ids=[aura.id, blade.id], to=knight.id)
    act(s, "p1", type="pass_priority")  # state-based actions are checked
    st = s.state
    aura_on = aura.id in st.cards and st.cards[aura.id].attached_to == knight.id
    assert aura_on is not falls_off
    assert (st.cards[blade.id].attached_to is None) is falls_off and st.cards[blade.id].zone == "p1:battlefield"


def test_noncombat_damage_from_that_quality_is_prevented(cards):
    from tests.test_rules_effects import pass_until_stack_empty

    s = table(cards, "Mountain", "Sol Ring")
    for name, text in (("Knight", "Protection from red"), ("Squire", "")):
        act(s, "p2", type="create_token", player="p2", token={"name": name, "type_line": "Token Creature — Knight",
                                                             "power": "2", "toughness": "2", "text": text})
    cast(s, "Pyroclasm")
    pass_until_stack_empty(s)
    st = s.state
    names = {c.name for c in st.cards.values() if c.zone == "p2:battlefield"}
    assert "Knight" in names and "Squire" not in names
    assert next(c for c in st.cards.values() if c.name == "Knight").damage == 0


def test_changeling_is_every_creature_type(cards):
    """702.73a: a changeling is a Goblin, an Elf, … — so protection from Goblins stops it blocking."""
    from app.rules import characteristics as chars

    s, sneak, guard = _evasion_table(cards, "Protection from Goblins", blocker_text="Changeling", blocker_colors=("G",))
    assert "Goblin" in chars.of(guard, cards).subtypes and "Time Lord" in chars.of(guard, cards).subtypes
    assert _blocks(s, sneak, guard) is False
