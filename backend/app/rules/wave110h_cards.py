"""Wave 110H one-card ability rewrites (exact Oracle text -> wording the grammar already reads)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

# Unscythe, Killer of Kings: the Scythe of the Wretched trigger (damage_death104) with another rider (702.6, 120.3, 603.10a).
_UNSCYTHE = ("Whenever a creature dealt damage by equipped creature this turn dies, you may exile that card. "
             "If you do, create a 2/2 black Zombie creature token.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == _UNSCYTHE:
        native = scripts.define(replace(ability, text=text.replace("equipped creature", "~")), ch)
        if native is None or "damaged_by_self" not in native.get("cond", {}):
            return None
        cond = {**native["cond"], "damaged_by_host104": True}
        cond.pop("damaged_by_self")
        return {**native, "cond": cond}
    return None


# -- spell bodies -------------------------------------------------------------------------------------
def _binding_negotiation() -> Any:
    from app.rules import scripts
    from app.rules import static_spell100c as S

    base = scripts.parse_effects("Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it.")
    if base is None:
        return None
    effects, target, flag = base
    did = next(e["did"] for e in effects if e.get("did"))
    # "Otherwise" (608.2c): you didn't choose a card. Your choice of one or none of the face-up exiled cards that player owns (406.3), to their graveyard (400.3).
    yard = {"do": "return_choice", "who": f"{S.OWNED}target|{S._key(card=True, extras=('face_up',), zones=('exile',))}", "to": "graveyard",
            "n": 1, "upto": True, "random": False, "label": "face-up exiled card"}
    return [*effects, {"do": "only_if", "cond": {"not": {"succeeded": did}}, "skip": 1}, yard], target, flag


BUILDERS = {
    "Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a face-up "
    "exiled card they own into their graveyard.": _binding_negotiation,
}


def parse(body: str) -> Any:
    build = BUILDERS.get(body.strip())
    return build() if build is not None else None
