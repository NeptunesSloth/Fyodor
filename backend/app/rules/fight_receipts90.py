"""Native actual-fight receipts: zero or prevented damage is still a fight (701.14)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

NEYITH = (
    "Whenever one or more creatures you control fight or become blocked, draw a card."
)
REGENT = "Whenever a creature you control fights, put two +1/+1 counters on it at the beginning of the next end step."
RING = "{T}: Create a Treasure token. Activate only if you control a creature that fought this turn."


def record(plan: Any, ids: list[str]) -> None:
    from app.game.rules_state import copy_recipe_of, emit, snapshot

    ids = list(dict.fromkeys(ids))
    layered = plan._battlefield_lki({"card_ids": ids})
    fighters = []
    for cid in ids:
        snap = snapshot(plan.state, cid)
        snap.copy_recipe = copy_recipe_of(plan.rules, snap.object_id)
        if (facts := layered.get(snap.object_id)) is not None:
            pt, abilities, keywords, traits, base, goaded = facts
            if pt is not None:
                snap.power, snap.toughness = pt
            if base is not None:
                snap.base_power, snap.base_toughness = base
            snap.abilities, snap.keywords, snap.traits = abilities, keywords, traits
            snap.goaded = sorted(goaded)
        fighters.append(snap)
    emit(plan.state, "fought", fighters90=fighters)


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import delayed, scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == NEYITH:
        native = scripts.define(
            replace(
                ability,
                text="Whenever one or more creatures you control die, draw a card.",
            ),
            ch,
        )
        if native:
            base = native["cond"]
            return {
                **native,
                "cond": {
                    "event": "either",
                    "conds": [{**base, "event": "fight"}, {**base, "event": "blocked"}],
                    "aggregate": True,
                },
            }
    if text == REGENT:
        native = scripts.define(
            replace(ability, text="Whenever a creature you control dies, draw a card."),
            ch,
        )
        if native:
            return {
                **native,
                "cond": {**native["cond"], "event": "fight"},
                "effects": delayed.wrap_when(
                    [{"do": "add_counters", "who": "event", "kind": "+1/+1", "n": 2}],
                    {"kind": "step", "step": "end", "whose": "next"},
                ),
            }
    if (
        text
        == "Whenever a creature you control enters, it fights up to one target creature you don't control with the same mana value."
    ):
        from app.rules import selectors

        native = scripts.define(
            replace(ability, text=text.replace(" with the same mana value", "")), ch
        )
        if native:

            def group(g: dict[str, Any]) -> dict[str, Any]:
                sel = selectors.from_key(g["what"])
                return {
                    **g,
                    "what": replace(
                        sel, compare=(*sel.compare, ("mv", "==", "fight90:unbound"))
                    ).key(),
                }

            return {
                **native,
                "fight_same_mv90": True,
                **(
                    {"targets": [group(g) for g in native["targets"]]}
                    if native.get("targets")
                    else {"target": group(native["target"])}
                ),
            }
    if text == RING:
        native = scripts.define(
            replace(
                ability,
                text="{T}: Create a Treasure token. Activate only if you attacked this turn.",
            ),
            ch,
        )
        if native:
            return {
                **native,
                "restriction": [
                    {
                        "kind": "if",
                        "cond": {"fought_creature90": True},
                        "text": "you control a creature that fought this turn",
                    }
                ],
            }
    if (
        text
        == "At the beginning of combat on your turn, you may pay {2}{R/G}. If you do, double target creature's power until end of turn. That creature must be blocked this combat if able."
    ):
        native = scripts.define(
            replace(
                ability, text=text.replace("blocked this combat", "blocked this turn")
            ),
            ch,
        )
        if native:
            return {
                **native,
                "effects": [
                    {**e, "duration": "end_of_combat"}
                    if e.get("do") == "restrict"
                    else e
                    for e in native["effects"]
                ],
            }
    return None


def fought_creature(plan: Any, player: str) -> bool:
    if plan.rules.turn_log.turn != plan.state.turn.number:
        return False
    fought = set(plan.rules.turn_log.fought90)
    return any(
        c.controller == player
        and plan.in_game(c)
        and c.zone.endswith(":battlefield")
        and plan.oid(c) in fought
        and plan.ch(c).is_creature
        for c in plan.state.cards.values()
    )


def bind(plan: Any, pending: Any) -> None:
    import base64
    import json

    from app.rules import selectors

    if (
        not pending.ability.get("fight_same_mv90")
        or pending.event is None
        or len(pending.event.objects) != 1
    ):
        return
    ref = pending.event.objects[0]
    marker = (
        "fight90:"
        + base64.urlsafe_b64encode(
            json.dumps({"card": ref.card, "object_id": ref.object_id}).encode()
        ).decode()
    )

    def group(g: dict[str, Any]) -> dict[str, Any]:
        sel = selectors.from_key(g["what"])
        return {
            **g,
            "what": replace(
                sel,
                compare=tuple(
                    (w, op, marker if n == "fight90:unbound" else n)
                    for w, op, n in sel.compare
                ),
            ).key(),
        }

    pending.ability = {
        **pending.ability,
        **(
            {"targets": [group(g) for g in pending.ability["targets"]]}
            if pending.ability.get("targets")
            else {"target": group(pending.ability["target"])}
        ),
    }


def same_mv(plan: Any, marker: str) -> int | None:
    import base64
    import json

    from app.rules import selectors
    from app.rules.triggers import _lki_characteristics

    if marker == "fight90:unbound":
        return None
    ref = json.loads(base64.urlsafe_b64decode(marker.partition(":")[2]))
    card = plan.state.cards.get(ref["card"])
    if (
        card is not None
        and plan.oid(card) == ref["object_id"]
        and card.zone.endswith(":battlefield")
    ):
        return selectors._stat(plan.ch(card), "mv")
    snap = plan.rules.lki.get(ref["object_id"])
    return (
        selectors._stat(_lki_characteristics(plan, snap), "mv")
        if snap is not None
        else None
    )


def restriction_problem(plan: Any, player: str) -> str | None:
    if fought_creature(plan, player):
        return None
    log = plan.rules.turn_log
    if log.turn != plan.state.turn.number or log.fight_history90_known is not True:
        return "Fight history for this turn is unavailable in this save. Resolve this activation manually with the table tools."
    return None
