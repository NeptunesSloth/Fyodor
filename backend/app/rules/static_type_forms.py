"""Canonical static type forms composed from native layer definitions."""

from __future__ import annotations

from typing import Any


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors, statics, type_statics

    def attached(
        layer4: dict[str, Any], *, base: list[int] | None = None, grants: list[str] | None = None
    ) -> dict[str, Any]:
        return {
            **statics._definition("attached", "permanent", [], base=base, grants=grants),
            "layer4": layer4,
        }

    if text == "Enchanted permanent is a Vehicle artifact with crew 5 and it loses all other card types.":
        return attached({"set_types": ["Artifact"], "set_artifact_types": ["Vehicle"]}, grants=["Crew 5"])
    if text == "Enchanted permanent is an enchantment and loses all other card types.":
        return attached({"set_types": ["Enchantment"]})
    if (
        text
        == "Enchanted permanent is a Construct creature with base power and toughness 5/5 in addition to its other types."
    ):
        return attached({"add_types": ["Creature"], "add_subtypes": ["Construct"]}, base=[5, 5])
    if (
        text
        == "Equipped creature gets +2/+0, has menace, and is a Pirate in addition to its other creature types."
    ):
        return statics.parse(text.replace("other creature types", "other types"))
    if text == "All Goblins are black and are Zombies in addition to their other creature types.":
        return type_statics._definition("Goblins", {"add_subtypes": ["Zombie"]}, set_colors=["B"])
    if (
        text
        == 'Each creature you control is a Vampire in addition to its other creature types and has "Whenever ~ deals damage to a creature, put a +1/+1 counter on ~."'
    ):
        return type_statics._definition(
            "creatures you control",
            {"add_subtypes": ["Vampire"]},
            grants=[
                "Whenever this creature deals damage to a creature, put a +1/+1 counter on this creature."
            ],
        )
    if (
        text
        == "Lands you control and land cards you own that aren't on the battlefield are Deserts in addition to their other types."
    ):
        return type_statics._definition(
            "lands you control",
            {"add_subtypes": ["Desert"]},
            everywhere={"own": True, "types": ["Land"], "not_types": [], "permanent": False},
        )
    if (
        text
        == "Nonland permanents you control and permanent spells you control are enchantments in addition to their other types."
    ):
        return type_statics._definition(
            "nonland permanents you control",
            {"add_types": ["Enchantment"]},
            everywhere={
                "own": True,
                "types": [],
                "not_types": ["Land"],
                "permanent": True,
                "zones": ["stack"],
            },
        )
    if text == "As long as ~ is on the battlefield, it's a land in addition to its other types.":
        return {**statics._definition("self", None, []), "add_types": ["Land"]}
    if (
        text
        == 'During your turn, each non-Equipment artifact and non-Aura enchantment you control with mana value 4 or greater is a 4/4 Elemental creature in addition to its other types and has indestructible, haste, and "Whenever ~ deals combat damage to a player, draw a card."'
    ):
        branches = [
            selectors.parse(t + " you control with mana value 4 or greater")
            for t in ["non-Equipment artifact", "non-Aura enchantment"]
        ]
        assert all(b is not None for b in branches)
        key = selectors.Selector(either=tuple(b.key() for b in branches if b is not None)).key()
        return type_statics._definition(
            "",
            {"add_types": ["Creature"], "add_subtypes": ["Elemental"]},
            who_key=key,
            during=True,
            base=[4, 4],
            keywords=["indestructible", "haste"],
            grants=["Whenever this creature deals combat damage to a player, draw a card."],
        )
    if text == "As long as enchanted permanent is a Vehicle, it's a creature in addition to its other types.":
        # Native group membership evaluates the current host and Vehicle type
        # without recursive conditional attached-characteristic derivation.
        key = selectors.Selector(subtypes=("Vehicle",), extras=("host_of_source",)).key()
        return type_statics._definition("", {"add_types": ["Creature"]}, who_key=key)
    return None
