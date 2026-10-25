"""-- wave 110G -- exact Oracle wordings of single cards, read as a wording the grammar reads or built from parts of it (as wave110b_cards)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def _exchange_power(d: Def) -> Def:
    """701.12g: exchanging two powers makes a continuous effect setting each (613.4b) to the other's previous value."""
    return {**d, "effects": [{"do": "exchange_power110g", "duration": "end_of_combat"}]}


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Portcullis: "two or more other creatures" is three or more with the entering one; the card returns when the artifact leaves (610.3)
    "Whenever a creature enters, if there are two or more other creatures on the battlefield, exile that creature. Return that card to the battlefield "
    "under its owner's control when this artifact leaves the battlefield.":
        "Whenever a creature enters, if there are three or more creatures on the battlefield, exile it until this artifact leaves the battlefield.",
}

# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # Serene Master
    "Whenever this creature blocks, exchange its power and the power of target creature it's blocking until end of combat.":
        ("Whenever this creature blocks, target creature it's blocking has base power 3 until end of combat.", _exchange_power),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (same := _AS.get(ability.text.strip())) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def exchange_power(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Both powers are read before either is set (701.12g)."""
    from app.rules import effects, values

    mine, theirs = (values.evaluate(plan, ctx, {"power": who}) for who in ("self", "target"))
    base = {"do": "become", "types": [], "duration": e["duration"]}
    effects.become(plan, ctx, {**base, "who": "self", "p": theirs})
    return effects.become(plan, ctx, {**base, "who": "target", "p": mine})


PRIMITIVES: dict[str, Any] = {"exchange_power110g": exchange_power}
