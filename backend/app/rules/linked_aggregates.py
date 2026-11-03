"""Exact source-incarnation linked-pool projections (CR 607.2a)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def source_context(plan: Plan, source: Any, definition: dict[str, Any]) -> dict[str, Any]:
    """Only live-static callers construct current context; triggers retain their saved ctx."""
    ctx: dict[str, Any] = {
        "controller": source.controller,
        "source_card": source.id,
        "source_object": plan.oid(source.id),
    }
    for instruction in definition.get("effects") or []:
        if instruction.get("do") == "borrowed_link_scope":
            ctx["borrowed_link_scope"] = instruction["scope"]
    return ctx


def current_pool(plan: Plan, ctx: dict[str, Any], spec: dict[str, Any]) -> list[Any]:
    from app.rules import exiled_with, selectors

    if not ctx.get("source_object"):
        return []  # Do not attribute an unknown old context to today's new incarnation.
    selected = [plan.state.cards[cid] for cid in exiled_with.cards(plan, ctx)]
    if spec.get("selector"):
        selector = selectors.from_key(spec["selector"])
        selected = [
            card
            for card in selected
            if selectors.matches(
                plan, selector, card, plan.ch(card), ctx["controller"], ctx.get("source_card")
            )
        ]
    return selected


def aggregate(plan: Plan, ctx: dict[str, Any], spec: dict[str, Any]) -> Any:
    from app.rules import sba
    from app.rules.creature_types import CREATURE_TYPES

    cards = current_pool(plan, ctx, spec)
    projection = spec.get("projection", "count")
    if projection == "count":
        return len(cards)
    if projection == "total_mv110f":  # -- wave 110F -- Idris: the mana value of the exiled card (X is 0 in exile, 202.3e)
        return sum(plan.ch(card).mana_value for card in cards)
    if projection == "mana_values":
        # Derive actual zone characteristics; a face-down object's missing mana
        # cost gives MV0 by202.3a, never its hidden printed cost.
        return len({plan.ch(card).mana_value for card in cards})
    if projection == "card_types":
        return set().union(*(plan.ch(card).types for card in cards))
    if projection == "share_type112t":  # -- Star Trek one-offs (wave 112T) -- All Good Things...: 1 if all the cards share a card type (205.2a); with
        # one card or none, they do (the Star Trek release notes: "You'll gain 10 life if there's only one exiled card … If there are no exiled cards, you
        # will also gain 10 life.")
        return int(len(cards) < 2 or bool(set.intersection(*(set(plan.ch(card).types) for card in cards))))
    if projection == "power":
        latest = aggregate(plan, ctx, {"projection": "last_creature"})
        return latest["power"] if latest is not None else 0
    if projection == "toughness":  # -- wave 110G -- Phyrexian Ingester: the imprinted creature card's toughness
        latest = aggregate(plan, ctx, {"projection": "last_creature"})
        return latest["toughness"] if latest is not None else 0
    if projection == "last_creature":
        # Admitted only by definitions whose exiling half exiles at most one
        # creature per resolution. Do not resolve simultaneous-last ambiguity
        # by inventing an arbitrary ordering of a generic pool.
        latest = next((card for card in reversed(cards) if plan.ch(card).is_creature), None)
        if latest is None:
            return None
        ch = plan.ch(latest)
        return {
            "power": sba.power(latest, ch),
            "toughness": sba.toughness(latest, ch),
            "creature_types": set(ch.subtypes) & CREATURE_TYPES,
            "all_creature_types": set(ch.subtypes) >= CREATURE_TYPES,
        }
    raise ValueError("Unrecognized linked-pool projection")


def parse_value(text: str) -> dict[str, Any] | None:
    import re

    t = text.strip().rstrip(".").lower()
    m = re.fullmatch(
        r"(?:the number of )?(?P<kind>creature )?cards?(?: that have been)? exiled with (?:~|it)", t
    )
    if m:
        spec: dict[str, Any] = {"projection": "count"}
        if m["kind"]:
            from app.rules import selectors

            sel = selectors.parse("creature card")
            assert sel is not None
            spec["selector"] = sel.key()
        return {"linked_pool": spec}
    return None


def parse_condition(text: str) -> dict[str, Any] | None:
    import re

    from app.rules import values

    t = text.strip().rstrip(",").lower()
    m = re.fullmatch(
        r"(?:there (?:are|is) )?(?P<n>\w+)(?: or more)? (?P<kind>creature )?cards? (?:have been |is |are )?exiled with (?:~|it)",
        t,
    )
    if m:
        n = (
            int(m["n"])
            if m["n"].isdigit()
            else values.NUMBERS.get(m["n"], 1 if m["n"] in ("a", "an") else None)
        )
        value = parse_value((m["kind"] or "") + "cards exiled with ~")
        if n is not None and value is not None:
            return {"value": value, "op": ">=", "n": n}
    if re.fullmatch(r"all cards exiled with (?:~|it) share a card type", t):  # -- Star Trek one-offs (wave 112T) -- (All Good Things...)
        return {"value": {"linked_pool": {"projection": "share_type112t"}}, "op": ">=", "n": 1}
    m = re.fullmatch(
        r"(?:there are )?cards with (?P<n>\w+) or more different mana values (?:are )?exiled with ~", t
    )
    if m:
        n = int(m["n"]) if m["n"].isdigit() else values.NUMBERS.get(m["n"])
        if n is not None:
            return {"value": {"linked_pool": {"projection": "mana_values"}}, "op": ">=", "n": n}
    return None


def parse_effects(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Bounded native instruction recipes for linked-pool consumers."""
    import re

    from app.rules import scripts, selectors

    text = re.sub(r"\s+", " ", body).strip().rstrip(".").lower()
    if text == "sacrifice it. if you do, return those cards to the battlefield under their owner's control":
        return [{"do": "linked_sacrifice_return"}], None, False
    if (
        text
        == "flip a coin. if you lose the flip, sacrifice ~ and return a card exiled with it at random to its owner's hand"
    ):
        found = scripts.parse_effects("Flip a coin. If you lose the flip, sacrifice ~.")
        if found is not None:
            effects = found[0]
            # The loss branch also contains the return; failing to sacrifice does
            # not stop it (608.2c, no conditional payment in the Oracle text).
            effects = [{**e, "skip": e["skip"] + 1} if e.get("do") == "only_if" else e for e in effects]
            return (
                [
                    *effects,
                    {
                        "do": "return_choice",
                        "who": "exiled_with",
                        "n": 1,
                        "upto": False,
                        "random": True,
                        "label": "card",
                        "to": "hand",
                    },
                ],
                None,
                False,
            )
    if text == "exile target creature. then if there are three or more cards exiled with ~, transform it":
        return (
            [
                {"do": "exile", "who": "target", "link": True},
                {"do": "only_if", "cond": parse_condition("three or more cards exiled with ~"), "skip": 1},
                {"do": "transform", "who": "self"},
            ],
            "creature",
            False,
        )
    if text == "exile any number of other nontoken creatures you control until it leaves the battlefield":
        sel = selectors.parse("other nontoken creature you control")
        assert sel is not None
        return (
            [
                {
                    "do": "sacrifice_choice",
                    "who": "you",
                    "sel": sel.key(),
                    "n": 250,
                    "upto": True,
                    "exile": "until",
                    "link": True,
                }
            ],
            None,
            False,
        )
    if (
        text
        == "draw a card, then exile a card from your hand. if cards with five or more different mana values are exiled with ~, you gain 5 life, untap ~, and transform it"
    ):
        sel = selectors.parse("card in your hand")
        assert sel is not None
        return (
            [
                {"do": "draw", "who": "you", "n": 1},
                {
                    "do": "return_choice",
                    "sel": sel.key(),
                    "to": "exile",
                    "n": 1,
                    "upto": False,
                    "random": False,
                    "label": "card",
                    "link": True,
                },
                {
                    "do": "only_if",
                    "cond": parse_condition(
                        "cards with five or more different mana values are exiled with ~"
                    ),
                    "skip": 3,
                },
                {"do": "gain_life", "who": "you", "n": 5},
                {"do": "untap", "who": "self"},
                {"do": "transform", "who": "self"},
            ],
            None,
            False,
        )
    if (
        text
        == "put a soul counter on ~. then if there are three or more soul counters on ~, remove all soul counters from ~, transform it, then untap it"
    ):
        return scripts.parse_effects(
            "Put a soul counter on ~. If there are three or more soul counters on ~, remove all soul counters from ~, transform ~, and untap ~."
        )
    if (
        text
        == "exile up to two target legendary creature cards from your graveyard. you draw x cards and you lose x life, where x is the greatest mana value among cards exiled this way"
    ):
        found = scripts.parse_effects("Exile up to two target legendary creature cards from your graveyard.")
        assert found is not None
        return (
            [
                {**found[0][0], "as": "funeral_exiled", "link": True},
                {"do": "linked_exiled_max", "ref": "ref:funeral_exiled", "as": "funeral_max"},
                {"do": "draw", "who": "you", "n": {"ref_amount": "funeral_max"}},
                {"do": "lose_life", "who": "you", "n": {"ref_amount": "funeral_max"}},
            ],
            found[1],
            False,
        )
    if text == "exile a card from a graveyard":
        return [{"do": "linked_graveyard_choice"}], None, False
    if text == "choose one of them at random. you may cast it without paying its mana cost":
        return [{"do": "linked_random_cast"}], None, False
    return None


def graveyard_choice(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    choices = [card for card in plan.state.cards.values() if card.zone.endswith(":graveyard")]
    if not choices:
        return True
    decide(
        plan,
        player=ctx["controller"],
        kind="choose_cards",
        prompt="Exile a card from a graveyard",
        options=[DecisionOption(id=c.id, label=plan.ch(c).name or "Card", card_id=c.id) for c in choices],
        min_choices=1,
        max_choices=1,
        resume={"step": "linked_graveyard_choice", "ctx": ctx},
    )
    return False


def resume_graveyard(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    cards = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone.endswith(":graveyard")]
    if effects.exile_cards(plan, ctx, {"link": True}, cards):
        effects.continue_effects(plan, ctx)


def random_cast(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import granted_casts

    cards = current_pool(plan, ctx, {})
    if not cards:
        return True
    card = (plan.rng or secrets.SystemRandom()).choice(cards)
    plan.note(f"{ctx.get('name') or 'It'}: chosen at random", [card.id], actor=ctx["controller"])
    return granted_casts.ask(
        plan,
        ctx,
        player=ctx["controller"],
        cid=card.id,
        head=ctx.get("name") or "Cast",
        no="Leave it exiled",
        object_id=plan.oid(card.id),
    )


PRIMITIVES = {"linked_graveyard_choice": graveyard_choice, "linked_random_cast": random_cast}
RESUME = {"linked_graveyard_choice": resume_graveyard}


def sacrifice_return(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, prohibitions

    cards = effects._cards(plan, ctx, "self")
    eligible = [
        c
        for c in cards
        if plan.state.cards[c].controller == ctx["controller"]
        and not prohibitions.sacrifice_forbidden(plan, plan.state.cards[c])
        and not prohibitions.cant_cause_sacrifice(plan, ctx["controller"], ctx["controller"])
    ]
    if not eligible:
        return True
    effects.sacrifice(plan, ctx, {"who": "self"})
    return effects.return_card(plan, ctx, {"who": "exiled_with", "to": "battlefield", "under": "owner"})


PRIMITIVES["linked_sacrifice_return"] = sacrifice_return


def definition(text: str, kind: str) -> dict[str, Any] | None:
    import re

    t = re.sub(r"\s+", " ", text).strip().rstrip(".").lower()
    if (
        kind == "triggered"
        and t
        == "whenever ~ attacks, if a card is exiled with it, it gets +x/+x until end of turn, where x is the power of the exiled card"
    ):
        return {
            "kind": "triggered",
            "trigger": "attacks_self",
            "optional": False,
            "target": None,
            "if": parse_condition("a card is exiled with it"),
            "effects": [
                {
                    "do": "pump",
                    "who": "self",
                    "p": {"linked_pool": {"projection": "power"}},
                    "t": {"linked_pool": {"projection": "power"}},
                }
            ],
        }
    if (
        kind == "triggered"
        and t
        == "at the beginning of the end step, if three or more cards have been exiled with ~, sacrifice it. if you do, return those cards to the battlefield under their owner's control"
    ):
        cond = parse_condition("three or more cards have been exiled with ~")
        return {
            "kind": "triggered",
            "trigger": "step:end:each",
            "effects": [{"do": "linked_sacrifice_return"}],
            "optional": False,
            "target": None,
            "if": cond,
        }
    if kind != "static":
        return None
    if t == "spells you cast cost {1} less to cast for each card type they share with cards exiled with ~":
        return {
            "kind": "static",
            "static": "cost_modifier",
            "caster": "you",
            "filter": None,
            "delta": 0,
            "linked_type_reduction": True,
            "effects": [],
        }
    if (
        t
        == "once each turn, you may cast a spell from the top of your library if it shares a card type with a card exiled with ~"
    ):
        return {
            "kind": "static",
            "static": "permission",
            "zone": "library_top",
            "once": True,
            "once_any": True,
            "flash": False,
            "self": False,
            "play": False,
            "cast": True,
            "filter": None,
            "effects": [],
            "linked_type_union": True,
        }
    if (
        t
        == "as long as a card exiled with ~ is a creature card, ~ has the power, toughness, and creature types of the last creature card exiled with it. it's still a shapeshifter"
    ):
        return {
            "kind": "static",
            "static": "grant",
            "who": "self",
            "attached_kind": None,
            "conditions": [],
            "p": 0,
            "t": 0,
            "base": None,
            "keywords": [],
            "grants": [],
            "rules": [],
            "effects": [],
            "linked_traits": True,
        }
    return None


def exiled_max(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    cards = context.objects(plan, ctx, e["ref"].removeprefix("ref:"))
    context.bind_amount(
        ctx,
        e["as"],
        max(
            (
                int(plan.ch(plan.state.cards[c]).mana_value)
                for c in cards
                if plan.state.cards[c].zone.endswith(":exile")
            ),
            default=0,
        ),
    )
    return True


PRIMITIVES["linked_exiled_max"] = exiled_max


def traits_layer4(state: Any, card: Any, info: Any) -> list[tuple[float, dict[str, Any]]]:
    """The multi-layer effect starts in layer four and continues through seven."""
    from app.rules import layers, scripts

    if info is None or state.rules is None or not card.zone.endswith(":battlefield"):
        return []
    view = layers._view(state, info)
    out = []
    for d in scripts.definitions(layers.copiable(state, card, info)).values():
        if not d.get("linked_traits"):
            continue
        traits = aggregate(view, source_context(view, card, d), {"projection": "last_creature"})
        if traits is None:
            continue
        out.append(
            (
                float(layers.timestamp(state, card.id)),
                {
                    "linked_traits_values": traits,
                    "layer4": {
                        "set_creature_types": sorted(traits["creature_types"] | {"Shapeshifter"}),
                        "all_creature_types": traits["all_creature_types"],
                    },
                },
            )
        )
    return out
