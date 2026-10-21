"""-- cast timing (wave 7A) -- "Cast this spell only during the declare attackers step and only if you've been attacked
this step." (Heavy Fog, Rally the Troops), "Cast this spell only during combat after blockers are declared." (Chaotic
Strike), "Cast this spell only if you control two or more Vampires." (Feast of Blood), "Cast this spell only during an
opponent's upkeep." (Festival). Researched against CR 2026-09-25.

* 601.3 / 117.1: a spell with such a sentence can only be cast when the timing and the condition it states hold (the
  sentence is a restriction of the card itself, on top of the usual timing for its type; an instant's flash is already
  enough for the rest). It is checked as the spell is begun (601.2: the player announces it), never again later.
* The steps are those of 500.1 / 506-511: "after blockers are declared" is the declare blockers step on (the blockers are
  declared as it begins, 509.1), "before blockers are declared" every moment up to the declare attackers step's end,
  "before attackers are declared" up to the beginning of combat's end (the same phases the activation restrictions read).
* "You've been attacked this step" is true when one or more creatures are attacking you, not only a planeswalker you control
  (506.3: a player, a planeswalker or a battle can each be attacked; the Heavy Fog ruling of 2009-10-01: "To cast it, a
  creature needs to have attacked you"); "fewer creatures than each opponent" compares your creature count with every
  opponent's (Even the Odds).
* 506.8d-f (wave 7R): "only before [attackers / blockers are declared, the combat damage step]" without "during combat" is about
  the turn's first combat phase only; "after blockers are declared" needs a declare blockers step (skipped when nobody attacks,
  508.8). The "during combat …" forms hold in any combat phase (506.8c).
* Read through the activation restrictions' clause grammar (app/rules/restrictions.py): the same steps, the same
  "only if" conditions; anything else stays manual.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import PHASES

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics

LINE = re.compile(r"^Cast this spell only (?P<rest>.+)\.$")
STATIC = "cast_restriction"


def _phases_before(phase: str) -> list[str]:
    return list(PHASES[: PHASES.index(phase)])


def _clause(clause: str) -> dict[str, Any] | None:
    from app.rules import restrictions

    # CR506.8c: an explicitly named player's combat means any combat on that
    # player's turn, including extra combats. These restrictions do not impose
    # the first-combat qualifier of the unqualified "before" wordings.
    m = re.fullmatch(r"during combat on (?P<whose>your|an opponent's) turn(?: before blockers are declared)?", clause)
    if m:
        phases = ["begin_combat", "declare_attackers"] if clause.endswith("before blockers are declared") else ["begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat"]
        return {"kind": "step", "phases": phases, "whose": "you" if m["whose"] == "your" else "opponent"}
    m = re.fullmatch(r"during (?:(?P<your>your) declare attackers step|the declare blockers step on an opponent's turn)", clause)
    if m:
        return {"kind": "step", "phases": ["declare_attackers" if m["your"] else "declare_blockers"],
                "whose": "you" if m["your"] else "opponent"}
    if clause == "during an opponent's turn, before attackers are declared":
        return {"kind": "step", "phases": _phases_before("declare_attackers"), "whose": "opponent", "first_combat": True}
    m = re.fullmatch(r"during combat (?P<when>after|before) blockers are declared", clause)
    if m:  # (declare blockers begins with the blockers declared, 509.1)
        phases = ["declare_blockers", "combat_damage", "end_combat"] if m["when"] == "after" else ["begin_combat", "declare_attackers"]
        return {"kind": "step", "phases": phases, "whose": None, **({"needs_blockers": True} if m["when"] == "after" else {})}
    if clause == "before combat or during combat before blockers are declared":
        return {"kind": "step", "phases": _phases_before("declare_blockers"), "whose": None}
    m = re.fullmatch(r"before (?P<what>blockers are declared|the combat damage step)", clause)
    if m:
        return {"kind": "step", "phases": _phases_before("declare_blockers" if m["what"].startswith("blockers") else "combat_damage"),
                "whose": None, "first_combat": True}  # (first_combat: wave 7R, see problem)
    if clause == "during an opponent's turn after their upkeep step":
        return {"kind": "step", "phases": list(PHASES[PHASES.index("upkeep") + 1:]), "whose": "opponent"}
    if clause == "during an opponent's upkeep":
        return {"kind": "step", "phases": ["upkeep"], "whose": "opponent"}
    if clause == "if you've been attacked this step":
        return {"kind": "if", "cond": {"attacked_now": True}, "text": "you've been attacked this step"}
    m = re.fullmatch(r"if you control fewer creatures than each opponent", clause)
    if m:
        return {"kind": "if", "text": clause, "cond": {"versus": {"value": {"count": 'sel:{"controller":"you","types":["Creature"]}'},
                                                                "op": ">", "every": True}}}
    return restrictions._clause(clause)


def definition(text: str) -> dict[str, Any] | None:
    """The restriction a "Cast this spell only …" line states, or None when a part isn't read."""
    m = LINE.match(text.strip())
    if m is None:
        return None
    found: list[dict[str, Any]] = []
    for clause in re.split(r" and (?:only )?(?=if |during |before )", m["rest"]):
        one = _clause(clause.strip())
        if one is None or one["kind"] in ("per_turn", "per_game", "sorcery", "instant"):
            return None
        found.append(one)
    return {"kind": "static", "static": STATIC, "restrictions": found, "effects": []}


def problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> str | None:
    """Why a "Cast this spell only …" sentence of this card stops ``player`` casting it now (None: it doesn't)."""
    from app.rules import restrictions, scripts
    from app.rules.plan import Plan

    if info is None or state.rules is None or state.rules.card_mode(card.id) == "manual":
        return None
    for index, d in scripts.definitions(ch).items():
        if d.get("kind") == "static" and d.get("static") == STATIC:
            why = restrictions.problem(state, player, card, index, d["restrictions"], Plan.view(state, player, info))
            if why:
                return why.replace("activated", "cast")
    return None
