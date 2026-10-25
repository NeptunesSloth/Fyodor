"""-- "If you would lose the game, instead ..." (wave 110C) -- 614.1a, 104.3: a replacement of the loss itself.

Exquisite Archangel, The Golden Throne, Lich's Mirror. The loss is replaced where the engine decides it: a state-based loss
(sba.apply: life, poison, commander damage, empty library) and "loses the game" effects (win_game.lose_game). A concession
(104.3a) is not an event any effect can replace. When the reason to lose still holds afterwards (poison), the player loses
on the next check: the replacement source is gone or used up.
ponytail: several such permanents are applied in battlefield order, not the player's 616.1 choice.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STATIC = "lose_instead110c"
_EXILE = r"exile (?:this creature|~|The Golden Throne)"
_TEXTS = {
    rf"If you would lose the game, instead {_EXILE} and your life total becomes equal to your starting life total\.": "start",
    rf"If you would lose the game, instead {_EXILE} and your life total becomes 1\.": 1,
    "If you would lose the game, instead shuffle your hand, your graveyard, and all permanents you own into your library, then draw seven cards and "
    "your life total becomes 20.": "mirror",
}


def definition(text: str) -> dict[str, Any] | None:
    text = text.removeprefix("Arcane Life-support — ")
    for pattern, life in _TEXTS.items():
        if re.fullmatch(pattern, text):
            return {"kind": "static", "static": STATIC, "life": life}
    return None


def replace_loss(plan: Plan, pid: str) -> bool:
    """Apply the first "if you would lose the game" replacement of ``pid``'s permanents; True when the loss did not happen."""
    from app.rules import effects, scripts
    from app.rules.replace import conditional_lines

    for c in list(plan.state.cards.values()):
        if c.controller != pid or not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("static") != STATIC:
                continue
            life = d["life"]
            if life == "mirror":  # 701.24a: every card of the player's in those zones, tokens cease to exist (704.5d)
                owned = [x.id for x in plan.state.cards.values() if x.owner == pid and x.zone.endswith(":battlefield")]
                plan.do({"type": "move", "card_ids": owned, "to": {"player": pid, "zone": "library"}}, actor=pid)
                body: list[dict[str, Any]] = [{"do": "shuffle_library", "who": "you", "zones": ["hand", "graveyard"]},
                                              {"do": "draw", "who": "you", "n": 7}, {"do": "set_life", "who": "you", "n": 20}]
            else:
                body = [{"do": "exile", "who": "self"}, {"do": "set_life", "who": "you", "n": life}]
            plan.note(f"{plan.name(pid)} would lose the game, but {c.name} replaces it")
            plan.rules.drew_from_empty = [p for p in plan.rules.drew_from_empty if p != pid]  # (704.5b: checked, nothing happened)
            effects.run_body(plan, {"controller": pid, "source_card": c.id, "source_object": plan.oid(c), "name": c.name, "effects": body, "next": 0})
            return True
    return False
