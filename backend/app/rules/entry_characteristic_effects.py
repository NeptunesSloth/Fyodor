"""Exact Oracle entry-form sentences; all moves/counters/choices use native effects."""

from __future__ import annotations

from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def parse(body: str) -> Parsed | None:
    from app.rules import delayed, scripts, selectors

    text = body.strip()
    if text:
        text = text[0].upper() + text[1:]
    if (
        text
        == "Return target artifact or non-Aura enchantment card from your graveyard to the battlefield with X additional +1/+1 counters on it. It's a 1/1 Spirit creature with flying in addition to its other types."
    ):
        a = selectors.Selector(types=("Artifact",), card=True, zones=("graveyard",), zone_owner="you")
        b = selectors.Selector(
            types=("Enchantment",), not_subtypes=("Aura",), card=True, zones=("graveyard",), zone_owner="you"
        )
        union = selectors.Selector(
            either=(a.key(), b.key()), card=True, zones=("graveyard",), zone_owner="you"
        )
        group = {"what": union.key(), "min": 1, "max": 1}
        if group is not None:
            return (
                [
                    {
                        "do": "return_card",
                        "who": "target",
                        "to": "battlefield",
                        "under": "you",
                        "tapped": False,
                        "counter": "+1/+1",
                        "counter_n": {"x": 1},
                        "entry_characteristics": {
                            "add_types": ["Creature"],
                            "set_creature_types": ["Spirit"],
                            "power": 1,
                            "toughness": 1,
                            "add_keywords": ["flying"],
                        },
                    }
                ],
                [group],
                False,
            )
    if (
        text
        == "For each player, choose a creature card in that player's graveyard. Put those cards onto the battlefield under your control. They're black Zombies in addition to their other colors and types and they gain decayed."
    ):
        key = selectors.Selector(types=("Creature",), card=True, zones=("graveyard",)).key()
        return (
            [
                {
                    "do": "player_chooses",
                    "who": "each_player",
                    "by": "you",
                    "sel": key,
                    "zone": "graveyard",
                    "n": 1,
                    "label": "creature card",
                    "as": "chosen_reanimation",
                },
                {
                    "do": "return_card",
                    "who": "ref:chosen_reanimation",
                    "as": "returned_group",
                    "to": "battlefield",
                    "under": "you",
                    "tapped": False,
                    "entry_characteristics": {"add_colors": ["B"], "add_subtypes": ["Zombie"]},
                },
                {
                    "do": "grant",
                    "who": "ref:returned_group",
                    "keywords": ["decayed"],
                    "duration": "permanent",
                },
            ],
            None,
            False,
        )
    if (
        text
        == "Reveal the top card of your library. If it's an artifact, creature, or land card, you may put it onto the battlefield with a manifestation counter on it. That permanent is an enchantment in addition to its other types."
    ):
        key = selectors.Selector(
            types=("Artifact", "Creature", "Land"), union=True, card=True, zones=("library",)
        ).key()
        return (
            [
                {"do": "look_top", "n": 1, "player": "you", "reveal": True},
                {
                    "do": "pick_looked",
                    "which": "that",
                    "optional": True,
                    "sel": key,
                    "to": "battlefield",
                    "counter": "manifestation",
                    "n": 1,
                    "entry_characteristics": {"add_types": ["Enchantment"]},
                },
            ],
            None,
            False,
        )
    zombie = {"add_colors": ["B"], "add_subtypes": ["Zombie"]}
    spirit = {
        "add_types": ["Creature"],
        "set_creature_types": ["Spirit"],
        "power": 1,
        "toughness": 1,
        "add_keywords": ["flying"],
    }

    def returning(who: str, form: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return {
            "do": "return_card",
            "who": who,
            "to": "battlefield",
            "under": "you",
            "tapped": False,
            "entry_characteristics": form,
            **extra,
        }

    if (
        text
        == "Put all creature cards from all graveyards onto the battlefield under your control. They're black Zombies in addition to their other colors and types."
    ):
        key = selectors.Selector(types=("Creature",), card=True, zones=("graveyard",)).key()
        return [returning(key, zombie)], None, False
    if (
        text
        == "Return up to X target artifact and/or non-Aura enchantment cards each with mana value X or less from your graveyard to the battlefield. If X is 6 or more, those permanents are 4/4 creatures in addition to their other types."
    ):
        dance_artifact = selectors.parse("artifact card with mana value X or less in your graveyard")
        dance_enchantment = selectors.parse(
            "non-Aura enchantment card with mana value X or less in your graveyard"
        )
        assert dance_artifact is not None and dance_enchantment is not None
        key = selectors.Selector(
            either=(dance_artifact.key(), dance_enchantment.key()),
            card=True,
            zones=("graveyard",),
            zone_owner="you",
        ).key()
        # The existing X condition reads the announced value, not an entering permanent.
        return (
            [
                returning(
                    "target",
                    {"add_types": ["Creature"], "power": 4, "toughness": 4},
                    entry_characteristics_if={"value": {"x": 1}, "op": ">=", "n": 6},
                )
            ],
            [{"what": key, "min": 0, "max": 1, "x_count": "upto"}],
            False,
        )
    if (
        text
        == "Return up to one target artifact, creature, or non-Aura enchantment card with mana value 3 or less from your graveyard to the battlefield with a finality counter on it. It's a 1/1 Spirit creature with flying in addition to its other types."
    ):
        branches = [
            selectors.parse(f"{kind} card with mana value 3 or less from your graveyard")
            for kind in ("artifact", "creature", "non-Aura enchantment")
        ]
        assert all(b is not None for b in branches)
        key = selectors.Selector(
            either=tuple(b.key() for b in branches if b is not None),
            card=True,
            zones=("graveyard",),
            zone_owner="you",
        ).key()
        return [returning("target", spirit, counter="finality")], [{"what": key, "min": 0, "max": 1}], False
    if (
        text
        == "Choose up to three target creature cards with total mana value 8 or less in your graveyard. Return each of them to the battlefield with a necrodermis counter on it. They're artifacts in addition to their other types."
    ):
        prefix = text.split(" They're", 1)[0]
        found = scripts.parse_effects(prefix)
        assert found is not None
        for effect in found[0]:
            if effect["do"] == "return_card":
                effect["entry_characteristics"] = {"add_types": ["Artifact"]}
        return found
    if (
        text
        == "Return up to one target artifact card, up to one target land card, and up to one target non-Aura enchantment card from your graveyard to the battlefield. They are 5/5 Elemental creatures in addition to their other types."
    ):
        found = scripts.parse_effects(text.split(" They are", 1)[0])
        assert found is not None
        # One instruction returns all groups simultaneously, including an object selected in two groups.
        return (
            [
                returning(
                    "union:target:0+target:1+target:2",
                    {
                        "add_types": ["Creature"],
                        "set_creature_types": ["Elemental"],
                        "power": 5,
                        "toughness": 5,
                    },
                )
            ],
            found[1],
            False,
        )
    if (
        text
        == "Return it to the battlefield under your control with an additional +1/+1 counter on it at the beginning of the next end step. That creature is a black Zombie in addition to its other colors and types."
    ):
        return (
            delayed.wrap_when(
                [returning("event.new", zombie, counter="+1/+1")],
                delayed.WHEN["the next end step"],
                who="event.new",
            ),
            None,
            False,
        )
    if (
        text
        == "Defending player chooses a nonlegendary creature card in your graveyard. You return that card to the battlefield with an additional +1/+1 counter on it. The creature is a Vampire in addition to its other types."
    ):
        drana_choice = selectors.parse("nonlegendary creature card in your graveyard")
        assert drana_choice is not None
        return (
            [
                {
                    "do": "return_choice",
                    "chooser": "defending_player",
                    "who": drana_choice.key(),
                    "n": 1,
                    "upto": False,
                    "random": False,
                    "label": "nonlegendary creature card",
                    "to": "battlefield",
                    "under": "you",
                    "tapped": False,
                    "counter": "+1/+1",
                    "entry_characteristics": {"add_subtypes": ["Vampire"]},
                }
            ],
            None,
            False,
        )
    if (
        text
        == "Return it to the battlefield under its owner's control with four charge counters on it. It's a Spirit Detective."
    ):
        return (
            [
                returning(
                    "it",
                    {"set_creature_types": ["Spirit", "Detective"]},
                    under="owner",
                    counter="charge",
                    counter_n=4,
                )
            ],
            None,
            False,
        )
    if text == "Return them to the battlefield. They're an artifact.":
        return [returning("it", {"set_types": ["Artifact"]})], None, False
    return None


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    if text == "When ~ die, if they were a creature, return them to the battlefield. They're an artifact.":
        cond = {"object": "self", "is": selectors.Selector(types=("Creature",)).key()}
        effect = {
            "do": "return_card",
            "who": "event.new",
            "to": "battlefield",
            "under": "you",
            "tapped": False,
            "entry_characteristics": {"set_types": ["Artifact"]},
        }
    elif (
        text
        == "When ~ dies, if it's not a Spirit, return it to the battlefield under its owner's control with four charge counters on it. It's a Spirit Detective."
    ):
        cond = {"object": "self", "is": selectors.Selector(not_subtypes=("Spirit",)).key()}
        effect = {
            "do": "return_card",
            "who": "event.new",
            "to": "battlefield",
            "under": "owner",
            "tapped": False,
            "counter": "charge",
            "counter_n": 4,
            "entry_characteristics": {"set_creature_types": ["Spirit", "Detective"]},
        }
    else:
        return None
    return {
        "kind": "triggered",
        "trigger": "dies_self",
        "optional": False,
        "target": None,
        "if": cond,
        "effects": [{"do": "only_if", "cond": cond, "skip": 1}, effect],
    }
