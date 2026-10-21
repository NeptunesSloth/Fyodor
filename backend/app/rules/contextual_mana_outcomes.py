"""Contextual mana outputs compose existing costs, effects and saved continuations."""

from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules import mana as M
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


def native(text: str) -> list[dict[str, Any]]:
    from app.rules import scripts

    parsed = scripts.parse_effects(text)
    assert parsed is not None and parsed[1] is None and not parsed[2], text
    return parsed[0]


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    from app.rules import conditions, scripts
    from app.rules import mana as M

    t = scripts.self_text(text, name)
    if t == '{T}: Choose a color. Add one mana of that color unless any player pays {1}. Activate only as an instant.':
        return M.ManaAbility(tap=True, sacrifice_self=False, options=((),), chooses=True, native_body=True,
            immediate_effects=({'do': 'choose_value', 'who': 'you', 'what': 'color', 'as': 'cave_color'},
                               {'do': 'rhystic_mana_payment'}))
    cache_tail = ' Any player may activate this ability but only during their turn before the end step.'
    if text.endswith(cache_tail):
        base = M.parse_mana_ability(text[:-len(cache_tail)], identity, card_name=name)
        return replace(base, chooses=True) if base is not None else None
    copy_tail = (' When you spend this mana to cast a spell or activate an ability, copy that spell or ability. '
                 'You may choose new targets for the copy.')
    if text.endswith(copy_tail):
        from app.rules import mana_units

        base = M.parse_mana_ability(text[:-len(copy_tail)], identity, card_name=name)
        rider = mana_units.rider(copy_tail.strip())
        return replace(base, on_spend=(*base.on_spend, rider)) if base is not None and rider is not None else None
    if (
        t
        == "{T}: Add one mana of any color. If you control a God, a Demigod, or a legendary enchantment, you gain 1 life."
    ):
        cond = {
            "any": [
                conditions.parse("you control " + x, objects=True)
                for x in ["a God", "a Demigod", "a legendary enchantment"]
            ]
        }
        base = M.parse_mana_ability("{T}: Add one mana of any color.", identity, card_name=name)
        return (
            replace(
                base,
                immediate_effects=(
                    {"do": "only_if", "cond": cond, "skip": 1},
                    {"do": "gain_life", "who": "you", "n": 1},
                ),
            )
            if base
            else None
        )
    if t == "{T}: Add {U}. Put a time counter on ~.":
        base = M.parse_mana_ability("{T}: Add {U}.", identity, card_name=name)
        return (
            replace(base, immediate_effects=({"do": "add_counters", "who": "self", "kind": "time", "n": 1},))
            if base
            else None
        )
    if (
        t
        == "{T}: Add one mana of any color. During your next untap step, as you untap your permanents, return ~ to its owner's hand."
    ):
        base = M.parse_mana_ability("{T}: Add one mana of any color.", identity, card_name=name)
        return replace(base, immediate_effects=({"do": "return_next_untap"},)) if base else None
    if t == "{1}, {T}: For each color among monocolored permanents you control, add one mana of that color.":
        return M.ManaAbility(
            tap=True,
            sacrifice_self=False,
            options=((),),
            extra_cost="{1}",
            chooses=True,
            native_body=True,
            immediate_effects=({"do": "represented_mana"},),
        )
    return None


def restriction(s: str) -> dict[str, Any] | None:
    forms: dict[str, dict[str, Any]] = {
        "Spend this mana only to pay cumulative upkeep costs": {"special": ["cumulative_upkeep"]},
        "Spend this mana only to cast Room spells and unlock doors": {
            "cast": [{"subtypes": ["Room"]}],
            "special": ["unlock"],
        },
        "Spend this mana only to foretell cards or cast spells that have foretell": {
            "cast": [{"foretell": True}],
            "special": ["foretell"],
        },
        "Spend this mana only to cast a spell that's one or more colors without {X} in its mana cost": {
            "cast": [{"colored_without_x": True}]
        },
    }
    return forms.get(s.strip().rstrip("."))


def has_foretell(ch: Characteristics) -> bool:
    return (
        any(re.match(r"Foretell\b", a.text, re.IGNORECASE) for a in ch.abilities) or "foretell" in ch.keywords
    )


def definition(a: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    t = scripts.self_text(a.text, ch.name)
    if t == "Your devotion to each color and each combination of colors is increased by one.":
        return {"kind": "static", "static": "devotion_bonus", "n": 1, "effects": []}
    if (
        t
        == "{1}{U}, {T}, Remove twelve time counters from ~ and exile it: Shuffle your graveyard and hand into your library, then draw seven cards. Activate only if you control a Time Lord."
    ):
        d = scripts.define(
            replace(
                a,
                text="{1}{U}, {T}, Remove 12 time counters from ~, Exile ~: Shuffle your hand and graveyard into your library, then draw seven cards.",
            ),
            ch,
        )
        if d is not None:
            d = copy.deepcopy(d)
            d["restriction"] = [
                {
                    "kind": "if",
                    "cond": {
                        "value": {
                            "count": selectors.Selector(controller="you", subtypes=("Time Lord",)).key()
                        },
                        "op": ">=",
                        "n": 1,
                    },
                }
            ]
        return d
    if (
        t
        == "At the beginning of your first main phase, add {R}{R}. Spend this mana only to cast Room spells and unlock doors."
    ):
        d = scripts.define(replace(a, text="At the beginning of your first main phase, add {R}{R}."), ch)
        if d is not None:
            from app.rules import mana as M

            d = copy.deepcopy(d)
            d["effects"].append(
                {
                    "do": "restrict_mana",
                    "only": M.parse_spend("Spend this mana only to cast Room spells and unlock doors"),
                }
            )
        return d
    if (
        t
        == "When you unlock this door, create an X/X blue Spirit creature token with flying, where X is the number of unlocked doors among Rooms you control."
    ):
        d = scripts.define(
            replace(
                a, text="When you unlock this door, create a 1/1 blue Spirit creature token with flying."
            ),
            ch,
        )
        if d is not None:
            d = copy.deepcopy(d)
            d["effects"] = [{"do": "room_spirit"}]
        return d
    if t == "I — You gain 2 life for each foretold card you own in exile.":
        d = scripts.define(replace(a, text="I — You gain 2 life."), ch)
        if d is not None:
            d = copy.deepcopy(d)
            d["effects"] = [{"do": "foretold_life"}]
        return d
    if t == "II — Add {W}{U}. Spend this mana only to foretell cards or cast spells that have foretell.":
        d = scripts.define(replace(a, text="II — Add {W}{U}."), ch)
        if d is not None:
            from app.rules import mana as M

            d = copy.deepcopy(d)
            d["effects"].append(
                {
                    "do": "restrict_mana",
                    "only": M.parse_spend(
                        "Spend this mana only to foretell cards or cast spells that have foretell"
                    ),
                }
            )
        return d
    if t == "III — Return target card with foretell from your graveyard to your hand.":
        d = scripts.define(replace(a, text="III — Return target card from your graveyard to your hand."), ch)
        if d is not None:
            d = copy.deepcopy(d)
            target = selectors.Selector(
                card=True, zones=("graveyard",), zone_owner="you", extras=("has_foretell",)
            ).key()
            d["target"] = {"what": target}
        return d
    m = re.fullmatch(
        r"Whenever (?:this creature|~) attacks, add (?P<m>(?:\{[RC]\})+) at the beginning of your next main phase this turn\.",
        t,
    )
    if m:
        d = scripts.define(replace(a, text="Whenever this creature attacks, add {R}."), ch)
        if d is not None:
            d = copy.deepcopy(d)
            from app.rules import delayed

            d["effects"] = delayed.wrap_when(
                [{"do": "add_mana", "mana": re.findall(r"\{([RC])\}", m["m"])}],
                {"kind": "step", "step": "main", "whose": "you"},
                this_turn=True,
            )
        return d
    return None


def clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    from app.rules import scripts

    t = text.strip().rstrip(".").lower()
    if t == "tap all lands target player controls and that player loses all unspent mana":
        parsed = scripts.parse_effects("Tap all lands target player controls.")
        if parsed is not None:
            return [*parsed[0], {"do": "gc_lose_mana", "who": "target"}], parsed[1]
    if (
        t
        == "counter target spell unless its controller pays {X}. If that player doesn't, they tap all lands with mana abilities they control and lose all unspent mana".lower()
    ):
        parsed = scripts.parse_effects("Counter target spell unless its controller pays {X}.")
        if parsed is not None:
            es = copy.deepcopy(parsed[0])
            es[-2]["skip"] += 1
            es.insert(0, {"do": "remember_spell_controller"})
            es.append({"do": "drain_land_pool"})
            return es, parsed[1]
    if (
        t
        == "tap target untapped creature you control. If you do, add an amount of {C} equal to that creature's mana value".lower()
    ):
        parsed = scripts.parse_effects("Tap target untapped creature you control.")
        if parsed is not None:
            es = copy.deepcopy(parsed[0])
            es[0]["as"] = "energy_tapped"
            es.append({"do": "add_mana", "sym": "C", "n": {"mana_value": "ref:energy_tapped"}})
            return es, parsed[1]
    if (
        t
        == "counter target spell. At the beginning of your next first main phase, add X mana in any combination of colors, where X is that spell's mana value".lower()
    ):
        parsed = scripts.parse_effects(
            "Counter target spell. At the beginning of your next main phase, add an amount of {C} equal to that spell's mana value."
        )
        if parsed is not None:
            es = copy.deepcopy(parsed[0])
            es[1]["when"]["step"] = "main1"
            es[2] = {"do": "deferred:add_mana", "of": list("WUBRG"), "n": es[2]["n"]}
            return es, parsed[1]
    if (
        t
        == "add two mana of any one color and two mana of any other color. Spend this mana only to cast creature or enchantment spells".lower()
    ):
        return [{"do": "two_different_mana"}], None
    if (
        t.removeprefix("then ")
        == "return a creature or planeswalker card with mana value X or less from your graveyard to the battlefield, where X is the amount of {S} spent to cast this spell".lower()
    ):
        es = native("Return a creature or planeswalker card from your graveyard to the battlefield.")
        return [{"do": "snow_return", "effect": es[0]}], None
    return None


def spell(ch: Characteristics, lines: list[AbilityText]) -> dict[str, Any] | None:
    from app.rules import scripts

    tail = "Then return a creature or planeswalker card with mana value X or less from your graveyard to the battlefield, where X is the amount of {S} spent to cast this spell."
    if len(lines) == 4 and lines[-1].text == tail and lines[0].text == "Choose one —":
        changed = [lines[0], *[replace(a, text=a.text + " " + tail) for a in lines[1:-1]]]
        return scripts.modal_definition(changed, ch.name)
    return None


def represented(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import immediate_mana_resolutions

    colors: set[str] = set()
    for c in plan.state.cards.values():
        if c.controller == ctx["controller"] and c.zone.endswith(":battlefield") and plan.in_game(c):
            cs = plan.ch(c).colors
            if len(cs) == 1:
                colors.update(cs)
    immediate_mana_resolutions.produce_chosen(
        plan, ctx, ctx["controller"], [c for c in "WUBRG" if c in colors]
    )
    return False


def remember_controller(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = effects._cards(plan, ctx, "target")
    ctx["_drained_controller"] = plan.state.cards[cards[0]].controller if cards else None
    return True


def drain(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import group_choice, selectors

    pid = ctx.get("_drained_controller")
    if pid:
        sel = selectors.Selector(types=("Land",), controller="player:" + pid, extras=("mana_ability",))
        for c in list(plan.state.cards.values()):
            if selectors.matches(plan, sel, c, plan.ch(c), ctx["controller"], None):
                plan.do({"type": "tap", "card_ids": [c.id], "tapped": True}, actor=ctx["controller"])
        group_choice.lose_mana(plan, ctx, {"who": "player:" + pid})
    return True


def room_spirit(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, rooms

    n = sum(
        len(rooms.doors_of(plan, c.id))
        for c in plan.state.cards.values()
        if c.controller == ctx["controller"] and c.zone.endswith(":battlefield") and plan.in_game(c)
    )
    token = native("Create a 1/1 blue Spirit creature token with flying.")[0]
    # Native token creation accepts independently computed power/toughness.
    token["token"]["power"] = str(n)
    token["token"]["toughness"] = str(n)
    return effects.PRIMITIVES[token["do"]](plan, ctx, token)


def foretold_life(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    n = sum(c.owner == ctx["controller"] and c.zone.endswith(":foretell") for c in plan.state.cards.values())
    return effects.gain_life(plan, ctx, {"who": "you", "n": n * 2})


def snow_return(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import selectors, values

    amount = values.evaluate(plan, ctx, {"mana_from": "Snow"})
    eff = copy.deepcopy(e["effect"])
    sel = selectors.from_key(eff["sel"])
    eff["sel"] = replace(sel, compare=(*sel.compare, ("mv", "<=", amount))).key()
    i = ctx["next"]
    ctx["effects"][i:i] = [eff]
    return True


def two_colors(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    chosen = ctx.get("_omen_first")
    options = [c for c in "WUBRG" if c != chosen]
    decide(
        plan,
        player=ctx["controller"],
        kind="choose_one",
        prompt="Choose a different second color" if chosen else "Choose the first color",
        options=[DecisionOption(id=c, label="{" + c + "}") for c in options],
        resume={"step": "two_different_mana", "ctx": ctx},
    )
    return False


def resume_two(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects
    from app.rules import mana as M

    ctx = d.resume["ctx"]
    if "_omen_first" not in ctx:
        ctx["_omen_first"] = chosen[0]
        two_colors(plan, ctx, {})
    else:
        first = ctx.pop("_omen_first")
        i = ctx["next"]
        ctx["effects"][i:i] = [
            {"do": "add_mana", "mana": [first] * 2 + [chosen[0]] * 2},
            {
                "do": "restrict_mana",
                "only": M.parse_spend("Spend this mana only to cast creature or enchantment spells"),
            },
        ]
        effects.continue_effects(plan, ctx)


PRIMITIVES = {
    "represented_mana": represented,
    "remember_spell_controller": remember_controller,
    "drain_land_pool": drain,
    "room_spirit": room_spirit,
    "foretold_life": foretold_life,
    "snow_return": snow_return,
    "two_different_mana": two_colors,
}
RESUME = {"two_different_mana": resume_two}


def return_next_untap(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import UntapOperation

    source = ctx.get("source_card")
    oid = ctx.get("source_object")
    if source and oid:
        plan.rules.untap_operations.append(
            UntapOperation(card=source, object_id=oid, player=ctx["controller"])
        )
    return True


def untap_operations(plan: Plan, player: str) -> None:
    from app.rules import effects

    due = [x for x in plan.rules.untap_operations if x.player == player]
    plan.rules.untap_operations = [x for x in plan.rules.untap_operations if x.player != player]
    for rec in due:
        c = plan.state.cards.get(rec.card)
        if (
            c is not None
            and c.zone.endswith(":battlefield")
            and plan.oid(c) == rec.object_id
            and plan.in_game(c)
        ):
            effects.bounce(
                plan,
                {
                    "controller": player,
                    "source_card": c.id,
                    "source_object": rec.object_id,
                    "effects": [],
                    "next": 0,
                    "kind": "mana",
                },
                {"who": "self"},
            )


PRIMITIVES["return_next_untap"] = return_next_untap
