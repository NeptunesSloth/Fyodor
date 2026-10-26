"""CR 107.3c, 607.3: activation costs whose X is defined by the ability text."""

from __future__ import annotations

import re
from typing import Any

from app.game.state import CardInstance
from app.rules.oracle import AbilityText
from app.rules.plan import Plan

_END = re.compile(r"\s+X is the (?:(?P<mv>mana value of (?:that card|the exiled card))|(?P<hand>number of cards in an opponent's hand)|number of (?P<counter>[\w+/\-]+) counters on (?:~|this \w+))\.\s*$")


def counter_cost(cost: str) -> str | None:
    m = re.fullmatch(r"Pay \{1\} for each (?P<counter>[\w+/\-]+) counter on (?:~|this \w+)", cost.strip())
    return m["counter"] if m is not None else None


def split(body: str) -> tuple[str, dict[str, Any] | None]:
    m = _END.search(body)
    if m is None:
        return body, None
    head = body[:m.start()].rstrip()
    # 107.3c: X in an effect could change while the ability is on the stack.
    # Only cost-only X is enabled here; don't freeze a resolution-time amount.
    if re.search(r"\bX\b", head):
        return body, None
    if m["hand"]:  # -- cards (wave 110H) -- Bargaining Table
        return head, {"opp_hand110h": True}
    if m["mv"]:
        return (head, {"linked_mana_value": True}) if "the exiled card" in head else (body, None)
    return head, {"source_counters": m["counter"]}


_MIRROR = "X is twice the mana value of that spell."  # -- cards (wave 110I) -- Reflecting Mirror: defined by the chosen target (107.3c)


def spec(ability: AbilityText, name: str) -> dict[str, Any] | None:
    from app.rules import abilities_of

    if ability.kind == "activated" and ability.text.endswith(_MIRROR) and ability.text.startswith("{X}"):
        return {"twice_target_mv110i": True}

    if ability.kind == "activated" and (counter := counter_cost((ability.cost or "").replace(name, "~"))) is not None:
        return {"source_counters": counter}
    if ability.kind != "activated" or "{X}" not in (ability.cost or "") or ":" not in ability.text:
        return None
    if abilities_of.manual(ability):
        return None  # 607.5: never price a borrowed linked ability from unrelated exile records.
    value = split(ability.text.split(":", 1)[1].replace(name, "~"))[1]
    scope = abilities_of.link_scope(ability)
    return {**value, "borrowed_link_scope": scope} if value is not None and value.get('linked_mana_value') and scope else value


def evaluate(plan: Plan, source: CardInstance, value: dict[str, Any], targets: list[str] | None = None, announced: int | None = None) -> int:
    if "opp_hand110h" in value:  # -- cards (wave 110H) -- "an opponent's hand": X is one opponent's hand size (107.3c); several differ, the announced X must match one
        from app.game.errors import ActionError
        from app.rules import effects

        sizes = {len(plan.state.zones.get(f"{p}:hand", [])) for p in effects._players(plan, {"controller": source.controller}, "each_opponent")}
        if announced is None:
            return min(sizes, default=0)
        if announced not in sizes:
            raise ActionError(f"X must be the number of cards in an opponent's hand: {sorted(sizes)}")
        return announced
    if "twice_target_mv110i" in value:
        from app.game.errors import ActionError

        if targets is None:
            return 0  # (can it be activated at all: the cheapest case, before a target is chosen)
        spell = plan.state.cards.get((targets or [""])[0])
        if spell is None or spell.zone != "stack":
            raise ActionError("Choose the target spell first: X is twice its mana value")
        return 2 * max(0, int(plan.ch(spell).mana_value))
    if "source_counters" in value:
        return max(0, source.counters.get(value["source_counters"], 0))
    from app.rules import exiled_with

    cards = exiled_with.cards(plan, {"source_object": plan.oid(source), "controller": source.controller, "borrowed_link_scope": value.get("borrowed_link_scope")})
    # 607.3: copied imprint triggers may exile several cards; their mana values
    # are summed when they determine one variable. No linked cards means zero.
    return sum(max(0, int(plan.ch(plan.state.cards[c]).mana_value)) for c in cards)
