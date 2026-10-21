"""Bound object redirection uses the native damage replacement pipeline (614.9)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = "bound_redirection"


def key(words: str) -> str:
    sel = selectors.parse(words)
    assert sel is not None
    return sel.key()


def old_any() -> str:
    return "creature_planeswalker_or_player"


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:] if not text.startswith("~") else text
    if (
        text
        == "The next X damage that would be dealt to target creature, planeswalker, or player this turn is dealt to another target creature, planeswalker, or player instead."
    ):
        return (
            [{"do": STEP, "mode": "finite", "origin": "target:0", "destination": "target:1", "n": {"x": 1}}],
            [{"what": old_any()}, {"what": old_any(), "distinct_from": [0]}],
            False,
        )
    if (
        text
        == "The next 3 damage that would be dealt to target creature you control this turn is dealt to another target creature instead."
    ):
        return (
            [{"do": STEP, "mode": "finite", "origin": "target:0", "destination": "target:1", "n": 3}],
            [{"what": key("creature you control")}, {"what": key("creature"), "distinct_from": [0]}],
            False,
        )
    if (
        text
        == "The next X damage that would be dealt this turn to target white creature you control is dealt to ~ instead."
    ):
        return (
            [{"do": STEP, "mode": "finite", "origin": "target", "destination": "self", "n": {"x": 1}}],
            key("white creature you control"),
            False,
        )
    if (
        text
        == "All combat damage that would be dealt to you this turn by target unblocked creature is dealt to its controller instead."
    ):
        return (
            [
                {
                    "do": "source_shield",
                    "src": "target",
                    "props": {},
                    "to": "you",
                    "redirect": "src_ctrl",
                    "redirect_once": False,
                    "combat": True,
                }
            ],
            key("unblocked creature"),
            False,
        )
    if (
        text
        == "Choose a creature you control. Until your next turn, all damage that would be dealt to creatures you control is dealt to that creature instead."
    ):
        return (
            [
                {
                    "do": "return_choice",
                    "sel": key("creature you control"),
                    "n": 1,
                    "to": "choose",
                    "as": "redirect_destination",
                },
                {"do": STEP, "mode": "ascent"},
            ],
            None,
            False,
        )
    if (
        text
        == 'Until end of turn, target creature you control gains "{0}: The next 1 damage that would be dealt to target creature, planeswalker, or player this turn is dealt to ~ instead." Only you may activate this ability.'
    ):
        return (
            [
                {
                    "do": "grant",
                    "who": "target",
                    "abilities": [
                        "{0}: The next 1 damage that would be dealt to target creature, planeswalker, or player this turn is dealt to this creature instead."
                    ],
                    "activation_player": "you",
                }
            ],
            key("creature you control"),
            False,
        )
    if (
        text
        == "The next 1 damage that would be dealt to target creature, planeswalker, or player this turn is dealt to ~ instead."
    ):
        return (
            [{"do": "redirect_damage", "from": "target", "to": "self", "limit": 1, "allocate": True}],
            old_any(),
            False,
        )
    if (
        text
        == "All damage that would be dealt this turn to target creature you control by a source of your choice is dealt to another target creature instead."
    ):
        groups = [{"what": key("creature you control")}, {"what": key("creature"), "distinct_from": [0]}]
        return (
            [
                {
                    "do": "source_shield",
                    "props": {},
                    "to": "target:0",
                    "redirect": "target:1",
                    "redirect_once": False,
                }
            ],
            groups,
            False,
        )
    if (
        text
        == "All combat damage that would be dealt to you this turn is dealt to target attacking creature instead."
    ):
        return ([{"do": STEP, "mode": "tables"}], key("attacking creature"), False)
    if (
        text
        == "All combat damage that would be dealt to you by unblocked creatures this turn is dealt to ~ instead."
    ):
        return ([{"do": STEP, "mode": "unblocked"}], None, False)
    if (
        text
        == "All damage that would be dealt this turn by target sorcery spell is dealt to that spell's controller instead."
    ):
        return (
            [
                {
                    "do": "source_shield",
                    "src": "target",
                    "props": {},
                    "to": None,
                    "redirect": "src_ctrl",
                    "redirect_once": False,
                }
            ],
            key("sorcery spell"),
            False,
        )
    if (
        text
        == "All damage that would be dealt to target creature this turn by a source of your choice is dealt to ~ instead."
    ):
        return (
            [
                {
                    "do": "source_shield",
                    "props": {},
                    "to": "target",
                    "redirect": "self",
                    "redirect_once": False,
                }
            ],
            key("creature"),
            False,
        )
    if (
        text
        == "All damage that would be dealt to you this turn by target attacking creature is dealt to ~ instead."
    ):
        return (
            [
                {
                    "do": "source_shield",
                    "src": "target",
                    "props": {},
                    "to": "you",
                    "redirect": "self",
                    "redirect_once": False,
                }
            ],
            key("attacking creature"),
            False,
        )
    if (
        text
        == "The next 1 damage that would be dealt to ~ this turn is dealt to its owner instead. Only ~'s owner may activate this ability."
    ):
        return ([{"do": STEP, "mode": "incarnation"}], None, False)
    if (
        text
        == "~ deals X damage to target player or planeswalker. That player or that planeswalker's controller may choose a creature they control and have ~ deal that damage to it instead."
    ):
        return ([{"do": STEP, "mode": "gambit"}], "player_or_planeswalker", False)
    return None


def record(
    plan: Plan, ctx: dict[str, Any], match: dict[str, Any], destination: dict[str, Any], **extra: Any
) -> None:
    from app.rules import replace

    replace.add_record(
        plan,
        event="damage",
        match=match,
        op={"do": "redirect", **destination},
        controller=ctx["controller"],
        source=ctx.get("source_object"),
        source_card=ctx.get("source_card"),
        label=ctx.get("name") or "Redirection",
        **extra,
    )


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, source_shields

    mode = e["mode"]
    if mode == "gambit":
        players = effects._players(plan, ctx, "target")
        targets = effects._cards(plan, ctx, "target")
        pid = players[0] if players else plan.state.cards[targets[0]].controller if targets else None
        if pid is None or pid not in plan.live():
            return True
        context.bind_players(ctx, "gambit_chooser", [pid])
        sel = selectors.Selector(types=("Creature",), controller="you").key()
        at = ctx["next"]
        # return_choice accepts a player-relative selector and independent chooser.
        ctx["effects"][at:at] = [
            {
                "do": "return_choice",
                "sel": sel,
                "chooser": "ref:gambit_chooser",
                "n": 1,
                "upto": True,
                "to": "choose",
                "as": "gambit_recipient",
            },
            {"do": STEP, "mode": "gambit_damage"},
        ]
        return True
    if mode == "gambit_damage":
        chosen = context.objects(plan, ctx, "gambit_recipient")
        at = ctx["next"]
        ctx["effects"][at:at] = [
            {"do": "damage", "who": "ref:gambit_recipient" if chosen else "target", "n": {"x": 1}}
        ]
        return True
    if mode == "finite":
        origin = source_shields._recipient(plan, ctx, {"to": e["origin"]})
        destination = source_shields._destination(plan, ctx, e["destination"])
        n = effects._amount(plan, ctx, e["n"])
        if origin is not None and destination is not None and n > 0:
            record(plan, ctx, {"to": origin}, {**destination, "limit": n, "allocate": True})
        return True
    if mode == "incarnation":
        source = effects._cards(plan, ctx, "self")
        if source:
            pid = plan.state.cards[source[0]].owner
            record(
                plan,
                ctx,
                {"to": {"objects": {"oids": [plan.oid(source[0])]}}},
                {"to": "pid", "pid": pid, "limit": 1, "allocate": True},
            )
        return True
    dest = source_shields._destination(
        plan,
        ctx,
        "ref:redirect_destination" if mode == "ascent" else "target" if mode == "tables" else "self",
    )
    if dest is None:
        return True
    if mode == "ascent":
        record(
            plan,
            ctx,
            {"to": {"objects": {"sel": key("creatures you control")}}},
            dest,
            until="next_turn",
            until_player=ctx["controller"],
        )
    elif mode == "tables":
        record(plan, ctx, {"to": {"players": "you"}, "combat": True}, dest)
    elif mode == "unblocked":
        record(
            plan,
            ctx,
            {"to": {"players": "you"}, "combat": True, "source": {"sel": key("unblocked creatures")}},
            dest,
        )
    else:
        raise ValueError(mode)
    return True


PRIMITIVES = {STEP: run}
