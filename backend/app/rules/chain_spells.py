"""-- chain spells (wave 52C) -- "Then that player or that permanent's controller may pay {R}{R}. If the player does, they may copy this spell and may choose a new target
for that copy." (Chain Lightning, Chain of Vapor, Chain of Smog, String of Disappearances ...).

CR 707.10: a copy of a spell is put on the stack under the control of the player who copies it (here the one the spell's single target names, or the controller of the target
object as it last existed, 608.2h), and 707.10c lets that player choose new targets for it. 118.12: "may [pay]. If the player does, ..." is the optional payment and its gate; the
copy is asked as its own "may" (nothing to pay), so declining it is allowed. The copy is a copy of the spell that is resolving (still on the stack, 608.2: it leaves it last), so it
carries the same instructions and the chain goes on with the new controller as "that player".
"""

from __future__ import annotations

import re
from typing import Any

_WHO = "target_player_or_controller"  # effects._players: the target player, or the target permanent's controller (as it last existed: 608.2h)
_PAYER = r"(?:that player or that (?:permanent|creature)'s controller|that (?:permanent|creature)'s controller|that player)"
_COPY = r"copy this spell and may choose a new target for that copy"
_COST = re.compile(rf"{_PAYER} may (?P<cost>pay (?:\{{[^}}]+\}})+|sacrifice a land of their choice|discard a card)")
_BARE = re.compile(rf"{_PAYER} may {_COPY}")
_DOES = re.compile(rf"if the player does, they may {_COPY}")


def _copy(bind: str) -> list[dict[str, Any]]:
    """The question (nothing to pay), then the copy and its marker for the new targets (gated on the answer)."""
    return [{"do": "optional_payment", "who": _WHO, "ask": "copy this spell", "cost": "", "bind": bind},
            {"do": "only_if", "cond": {"succeeded": bind}, "skip": 2},
            {"do": "copy_spell", "who": "this_spell", "by": _WHO},
            {"do": "copy_new_targets", "optional": True}]



def self_copy_sentence(text: str, effects: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """A conditional optional copy of the resolving spell; copies themselves were not cast."""
    from app.rules import conditions

    m = re.fullmatch(r"if (?P<cond>this spell was cast from (?:a graveyard|your hand)), you may copy this spell and may choose (?:a new target|new targets) for the copy", text)
    if m is None:
        return None
    cond = conditions.parse(m["cond"], objects=True)
    if cond is None:
        return None
    bind = f"pay{sum(e['do'] == 'optional_payment' for e in effects)}"
    return [{"do": "only_if", "cond": cond, "skip": 4},
            {"do": "optional_payment", "who": "you", "ask": "copy this spell", "cost": "", "bind": bind},
            {"do": "only_if", "cond": {"succeeded": bind}, "skip": 2},
            {"do": "copy_spell", "who": "this_spell"},
            {"do": "copy_new_targets", "optional": True}]


def sentence(texts: list[str], i: int, text: str, effects: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The effects of sentence ``i`` (``text``: it, first letter lowered) when it is a chain tail's, or None. Only after instructions that have the spell's one target
    ("that player" / "that permanent's controller" is whoever it names)."""
    from app.rules import optional_payment

    if not effects or len(groups) != 1 or (groups[0].get("min"), groups[0].get("max")) != (1, 1):
        return None
    k = sum(e["do"] == "optional_payment" for e in effects)
    if _BARE.fullmatch(text):
        return _copy(f"pay{k}")
    pay = _COST.fullmatch(text)
    if pay is not None and i + 1 < len(texts) and _DOES.fullmatch(texts[i + 1].rstrip(".").strip().lower()):
        cost = optional_payment.cost_text(pay["cost"])
        return [{"do": "optional_payment", "who": _WHO, "cost": cost, "bind": f"pay{k}"}] if cost is not None else None
    last = effects[-1]
    if _DOES.fullmatch(text) and last["do"] == "optional_payment" and last["who"] == _WHO and "ask" not in last:
        return [{"do": "only_if", "cond": {"succeeded": last["bind"]}, "skip": 4}, *_copy(f"pay{k}")]
    return None


def is_tail(sentence: str) -> bool:
    """Is this sentence (as printed) one of a chain tail's? (scripts._may_first_only: they read the spell's target, not what an optional first instruction did)"""
    t = re.sub(r"^then ", "", sentence.rstrip(".").strip().lower())
    return bool(_COST.fullmatch(t) or _BARE.fullmatch(t) or _DOES.fullmatch(t))
