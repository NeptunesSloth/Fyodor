"""-- controlling another player (wave 18H) -- "You control target player during that player's next turn." (Mindslaver,
Worst Fears, Sorin Markov's -7, The Dominion Bracelet, Construct a Cosmic Cube) and Emrakul, the Promised End's "you gain
control of target opponent during that player's next turn. After that turn, that player takes an extra turn."
Researched against CR 2026-09-25 (723).

* 723.1: the effect applies to the next turn the affected player actually takes (so a skipped turn, 723.1b, waits) and
  lasts the whole turn, ending as the next turn begins. 723.1a: effects on the same player overwrite each other, the last
  created one wins (a pending effect is replaced; Emrakul's extra turn is kept, as it is a separate instruction).
* 723.3: only the player is controlled: objects stay with their controllers; the controlled player is still the active
  player. 723.5: the controller makes every choice (``game/control.py`` routes the intents and ``rules/view.py`` the
  prompts); 723.4: they see what the controlled player sees (``game/visibility.can_see``, never a sideboard); 723.6: only
  a player concedes for themselves; 723.9: controlling yourself changes nothing.
* Refused (manual): Word of Command, Cruel Entertainment, Secret of Bloodbending (a combat phase / waterbend) and
  Opposition Agent are not read here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import PlayerControl

if TYPE_CHECKING:
    from app.rules.plan import Plan

_HEAD = r"(?:you control|you gain control of) target (?P<who>player|opponent) during (?:that player's|their) next turn"


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "control_player", "who": "target"}], m["who"]


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(f"^{_HEAD}$"), _build),
    # Emrakul's second sentence: the same player (the target of the first) takes an extra turn after the controlled one
    (re.compile(r"^after that turn, that player takes an extra turn$"), lambda m: ([{"do": "control_extra"}], None)),
]


def control_player(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import _players

    name = ctx.get("name") or "An effect"
    me = ctx["controller"]
    r = plan.rules
    ctx["controlled_now"] = []
    for pid in _players(plan, ctx, e["who"]):
        ctx["controlled_now"].append(pid)
        old = [c for c in r.player_control if c.controlled == pid and c.status == "pending" and not c.obj]  # 723.1a: the last one works
        r.player_control = [c for c in r.player_control if c not in old]
        r.player_control.append(PlayerControl(controlled=pid, controller=me, label=name,
                                              extra_after=sum(c.extra_after for c in old)))
        plan.note(f"{plan.name(me)} will control {plan.name(pid)} during their next turn ({name}, 723.1)", actor=me)
    return True


def control_extra(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"After that turn, that player takes an extra turn.": noted on the effect this resolution just made (kept if a later
    effect overwrites it, 723.1a: it is a separate instruction)."""
    for pid in ctx.get("controlled_now", []):
        mine = [c for c in plan.rules.player_control if c.controlled == pid and c.controller == ctx["controller"] and c.status == "pending"]
        if mine:
            mine[-1].extra_after += 1
    return True


def turn_began(plan: Plan) -> None:
    """723.1: the effect that applied to the turn that just ended is over; a pending one for the player whose turn this is
    begins (the others wait, 723.1b)."""
    r = plan.rules
    if not r.player_control:
        return
    live = plan.live()
    r.player_control = [c for c in r.player_control if c.status == "pending" and not c.obj and c.controlled in live]  # (wave 110E: obj windows end with their object)
    for c in r.player_control:
        if c.controlled != plan.active:
            continue
        c.status, c.turn = "active", plan.state.turn.number
        for _ in range(c.extra_after):  # 500.7: "after that turn" (the latest created is taken first)
            r.extra_turns.append({"player": c.controlled, "label": c.label})
        if c.controller in live:
            plan.note(f"{plan.name(c.controller)} controls {plan.name(c.controlled)} this turn ({c.label}, 723.1)", actor=plan.active)


# -- Opposition Agent -- "You control your opponents while they're searching their libraries." (a static ability: the
# controller makes the searcher's choices only while they search, 723.2) and its second sentence, which exiles each card found
# and lets the Agent's controller play it (any color of mana for casting, 609.4b)
_SEARCH_CONTROL = "you control your opponents while they're searching their libraries."
_SEARCH_EXILE = ("while an opponent is searching their library, they exile each card they find. you may play those cards for as "
                 "long as they remain exiled, and you may spend mana as though it were mana of any color to cast them.")


def static_definition(text: str) -> dict[str, Any] | None:
    t = text.strip().replace("’", "'").lower()
    if t == _SEARCH_CONTROL:
        return {"kind": "static", "static": "control_searchers", "effects": []}
    if t == _SEARCH_EXILE:
        return {"kind": "static", "static": "search_exile", "effects": []}
    return None


def _searching_static(plan: Plan, player: str, static: str) -> list[Any]:
    """The permanents an opponent of ``player`` controls with this static ability, oldest first (613.7)."""
    from app.rules import scripts
    from app.rules.layers import timestamp
    from app.rules.replace import conditional_lines

    found = []
    for c in sorted(plan.state.cards.values(), key=lambda c: timestamp(plan.state, c.id)):
        if not c.zone.endswith(":battlefield") or c.face_down or c.controller == player or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)
        if any(i not in skip and d.get("kind") == "static" and d.get("static") == static for i, d in scripts.definitions(ch).items()):
            found.append(c)
    return found


def search_controller(plan: Plan, player: str) -> str | None:
    """Who makes ``player``'s choices while they search their library (723.2): the controller of their opponents' latest
    "you control your opponents while they're searching" permanent."""
    found = _searching_static(plan, player, "control_searchers")
    return found[-1].controller if found else None


def search_exile(plan: Plan, player: str) -> list[Any]:
    """The permanents whose controllers may play the cards ``player`` finds in their library (they exile each one)."""
    return _searching_static(plan, player, "search_exile")


def permit_exiled(plan: Plan, agents: list[Any], exiled: list[str]) -> None:
    """Each Agent's controller may play the cards just exiled, for as long as they remain exiled (400.7: that object)."""
    import secrets

    from app.game.rules_state import Permission

    for src in agents:
        for cid in exiled:
            card = plan.state.cards.get(cid)
            if card is None or not card.zone.endswith(":exile"):
                continue
            plan.rules.permissions.append(Permission(
                id=secrets.token_hex(4), player=src.controller, play=True, cast=True, zone="any", object_id=plan.oid(card), card=cid,
                until="permanent", turn=plan.state.turn.number, spend="color", source=plan.oid(src),
                label=f"{src.name}: play it for as long as it remains exiled"))
            plan.note(f"{plan.name(src.controller)} may play {card.name} for as long as it remains exiled ({src.name})", [cid])


PRIMITIVES = {"control_player": control_player, "control_extra": control_extra}
