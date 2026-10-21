"""Resolved characteristic changes composed from native, noncopiable effects."""

from __future__ import annotations

from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def parse(body: str, *, it: str | None = None) -> Parsed | None:
    from app.rules import language, scripts, selectors

    text = body.strip()
    text = text[:1].upper() + text[1:]
    text = text.replace("You may ~ becomes ", "You may have ~ become ")

    def result(
        effect: dict[str, Any],
        target: str | None = None,
        *,
        before: list[dict[str, Any]] | None = None,
        after: list[dict[str, Any]] | None = None,
    ) -> Parsed:
        groups = [language.target_group(target)] if target else None
        return [*(before or []), effect, *(after or [])], groups, False

    def form(who: str = "target", **kw: Any) -> dict[str, Any]:
        return {"do": "become", "who": who, **kw}

    if text == "Until end of turn, target artifact creature becomes blue and isn't an artifact.":
        return result(form(colors=["U"], remove_types=["Artifact"]), "target artifact creature")

    control_prefix = "Gain control of target creature until end of turn. Untap that creature. "
    if text.startswith(control_prefix):
        rest = parse(text[len(control_prefix) :], it="target")
        if rest is not None:
            return (
                [
                    {"do": "gain_control", "who": "target", "duration": "end_of_turn"},
                    {"do": "untap", "who": "target"},
                    *rest[0],
                ],
                [language.target_group("target creature")],
                False,
            )
    if text == "Until end of turn, it gains haste and becomes a Pirate in addition to its other types.":
        return result(form(it or "target", add_creature_types=["Pirate"], keywords=["haste"]))
    if (
        text
        == "Put two +1/+1 counters on ~. Then you may have it become a 0/0 Elemental creature until end of turn. It's still a land."
    ):
        prefix = scripts.parse_effects("Put two +1/+1 counters on ~.")
        assert prefix is not None
        return result(
            form("self", types=["Creature"], retain=True, creature_types=["Elemental"], p=0, t=0),
            before=[*prefix[0], {"do": "may_rest", "label": "Become an Elemental creature"}],
        )
    if (
        text
        == 'Target artifact you control becomes a 9/9 Construct artifact creature and gains vigilance, indestructible, and "~ can\'t be blocked."'
    ):
        return result(
            form(
                types=["Artifact", "Creature"],
                retain=True,
                creature_types=["Construct"],
                p=9,
                t=9,
                keywords=["vigilance", "indestructible"],
                abilities=["This creature can't be blocked."],
                duration="permanent",
            ),
            "target artifact you control",
        )
    if text == "Until end of turn, ~ has base power and toughness 5/3, gains trample, and isn't a Human.":
        return result(form("self", p=5, t=3, keywords=["trample"], remove_subtypes=["Human"]))
    if text == "Target creature gets +1/+0, becomes black, and gains shadow until end of turn.":
        return result(
            form(colors=["B"], keywords=["shadow"]),
            "target creature",
            after=[{"do": "pump", "who": "target", "p": 1, "t": 0}],
        )
    if text == 'Until end of turn, target creature becomes black, gets +1/-1, and gains "{B}: Regenerate ~."':
        return result(
            form(colors=["B"], abilities=["{B}: Regenerate this creature."]),
            "target creature",
            after=[{"do": "pump", "who": "target", "p": 1, "t": -1}],
        )
    if (
        text
        == "Until end of turn, up to two target creatures each have base power and toughness 3/3, gain flying, and become blue Illusions in addition to their other colors and types."
    ):
        return result(
            form(p=3, t=3, add_colors=["U"], add_creature_types=["Illusion"], keywords=["flying"]),
            "up to two target creatures",
        )
    if (
        text
        == "Until end of turn, target creature gets +2/+2, gains flying, and becomes a Horror enchantment creature in addition to its other types."
    ):
        return result(
            form(
                types=["Creature", "Enchantment"],
                retain=True,
                add_creature_types=["Horror"],
                keywords=["flying"],
            ),
            "target creature",
            after=[{"do": "pump", "who": "target", "p": 2, "t": 2}],
        )
    if (
        text
        == "Up to two target Swamps each become 3/5 Treefolk Warrior creatures in addition to their other types until end of turn."
    ):
        return result(
            form(types=["Creature"], retain=True, creature_types=["Treefolk", "Warrior"], p=3, t=5),
            "up to two target Swamps",
        )
    if (
        text
        == "Up to three target lands you control each become 2/2 Warrior creatures until end of turn. They're still lands."
    ):
        return result(
            form(types=["Creature"], retain=True, creature_types=["Warrior"], p=2, t=2),
            "up to three target lands you control",
        )
    if (
        text
        == 'Until end of turn, ~ becomes a 2/1 blue and red Elemental creature with "During your turn, ~ has first strike." It\'s still a land.'
    ):
        return result(
            form(
                "self",
                types=["Creature"],
                retain=True,
                creature_types=["Elemental"],
                p=2,
                t=1,
                colors=["U", "R"],
                abilities=["During your turn, this creature has first strike."],
            )
        )
    if (
        text
        == 'Until end of turn, enchanted Plains becomes a 2/5 white Spirit creature with "Whenever ~ deals damage, its controller gains that much life." It\'s still a land.'
    ):
        return result(
            form(
                "host",
                types=["Creature"],
                retain=True,
                creature_types=["Spirit"],
                p=2,
                t=5,
                colors=["W"],
                abilities=["Whenever this creature deals damage, its controller gains that much life."],
            )
        )
    if text == "Until end of turn, all creatures become black and all lands become Swamps.":
        return result(
            form("each_creature", colors=["B"]),
            after=[form(selectors.Selector(types=("Land",)).key(), land_types=["Swamp"])],
        )
    if (
        text
        == "Until end of turn, it has base power and toughness 10/10 and gains trample, annihilator 2, and haste."
    ):
        return result(
            form(it or "target", p=10, t=10, keywords=["trample", "haste"], abilities=["Annihilator 2."])
        )
    if text == "It becomes a Bird Giant, and it loses defender.":
        return result(
            form("self", creature_types=["Bird", "Giant"], duration="permanent"),
            after=[{"do": "grant", "who": "self", "remove": ["defender"], "duration": "permanent"}],
        )
    if text == "Until end of turn, ~ becomes a 4/4 Spirit artifact creature that's no longer an Equipment.":
        return result(
            form(
                "self",
                types=["Artifact", "Creature"],
                retain=True,
                creature_types=["Spirit"],
                p=4,
                t=4,
                remove_subtypes=["Equipment"],
            )
        )
    if (
        text
        == "You may have ~ become a 2/1 Construct artifact creature with flying and ward {1}. If you do, it isn't an Equipment."
    ):
        return result(
            form(
                "self",
                types=["Artifact", "Creature"],
                retain=True,
                creature_types=["Construct"],
                p=2,
                t=1,
                keywords=["flying"],
                abilities=["Ward {1}."],
                remove_subtypes=["Equipment"],
                duration="permanent",
            ),
            before=[{"do": "may_rest", "label": "Become a Construct creature"}],
        )
    return None


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import statics

    if text == "During your turn, ~ is a Bear with base power and toughness 4/2.":
        return {
            **statics._definition("self", None, [{"static": "your_turn"}], base=[4, 2]),
            "layered": True,
            "layer4": {"set_creature_types": ["Bear"]},
        }
    if text == "Whenever ~ deals damage, its controller gains that much life.":
        return {
            "kind": "triggered",
            "trigger": "event",
            "effects": [{"do": "gain_life", "who": "source_controller", "n": {"event_amount": 1}}],
            "optional": False,
            "target": None,
            "cond": {"subject": "self", "event": "deal_damage", "to": "any", "combat": None},
        }
    if (
        text
        == "During your turn, as long as ~ has one or more loyalty counters on ~, he's a 3/4 Ninja creature and has hexproof."
    ):
        return {
            **statics._definition(
                "self",
                None,
                [
                    {"static": "your_turn"},
                    {"static": "self_counter", "counter": "loyalty", "op": ">=", "n": 1},
                ],
                base=[3, 4],
                keywords=["hexproof"],
            ),
            "layered": True,
            "layer4": {"set_types": ["Creature"], "set_creature_types": ["Ninja"]},
        }
    if text == "During turns other than yours, ~ is a 2/3 Gargoyle artifact creature with flying.":
        return {
            **statics._definition(
                "self",
                None,
                [{"static": "not", "cond": {"static": "your_turn"}}],
                base=[2, 3],
                keywords=["flying"],
            ),
            "layered": True,
            "layer4": {"add_types": ["Artifact", "Creature"], "set_creature_types": ["Gargoyle"]},
        }
    return None
