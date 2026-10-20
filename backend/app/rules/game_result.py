"""-- game result statics (wave 10B) -- "You can't lose the game and your opponents can't win the game." (Platinum Angel,
Herald of Eternal Dawn) and "You can't win the game and your opponents can't lose the game." (Abyssal Persecutor).
Researched against CR 2026-09-25.

* 104.3: a player loses when a state-based action says so (704.5a: 0 or less life, 704.5b: a draw from an empty library,
  704.5c: ten poison counters, 903.10a: commander damage) or an effect says so; a player who "can't lose the game" stays in
  it: the state-based action does nothing to them, and as nothing is checked again until something changes (704.3), a
  draw from an empty library is no longer pending once the check has passed (704.5b: "since the last time state-based
  actions were checked"), while a life total of 0 or less, or the poison counters, are still there when the permanent
  leaves and the player then loses at the next check. A player who concedes still leaves the game (104.3a).
* 104.2: a player who "can't win the game" doesn't win by an effect (104.2b); being the last player left (104.2a)
  overrides it: they win at once.
* Both statics apply while their source is on the battlefield (611.3a): "you" is its controller, "your opponents" the
  other players. Not read: the same effect from a spell ("players can't lose the game this turn": Everybody Lives!).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

KIND = "game_result"
_TEXT = re.compile(r"^You can't (?P<a>lose|win) the game and your opponents can't (?P<b>win|lose) the game\.$")


def static_definition(text: str) -> dict[str, Any] | None:
    if text.strip() == "You don't lose the game for having 0 or less life.":  # -- most-played cards III (wave 46C) -- read by ``zero_life_ok``
        return {"kind": "static", "static": KIND, "you": "zero_life", "opponents": None, "effects": []}
    if text.strip() == "You can't lose the game.":  # -- prohibitions (wave 22B) -- Lich's Mastery: only its controller
        return {"kind": "static", "static": KIND, "you": "lose", "opponents": None, "effects": []}
    m = _TEXT.match(text.strip())
    if m is None or m["a"] == m["b"]:
        return None
    return {"kind": "static", "static": KIND, "you": m["a"], "opponents": m["b"], "effects": []}


def _stops(plan: Plan, player: str, what: str) -> bool:
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or d.get("static") != KIND:
                continue
            if d["you" if c.controller == player else "opponents"] == what:
                return True
    # -- prohibitions (wave 22B) -- 611.2a: a resolved "can't lose the game this turn" (a record of the turn it was made)
    turn = plan.state.turn.number
    return any(x["player"] == player and x["what"] == what and x["turn"] == turn for x in plan.rules.results)


def cannot_lose(plan: Plan, player: str) -> bool:
    return _stops(plan, player, "lose")


def cannot_win(plan: Plan, player: str) -> bool:
    return _stops(plan, player, "win")


def zero_life_ok(plan: Plan, player: str) -> bool:
    """-- most-played cards III (wave 46C) -- 704.5a: "You don't lose the game for having 0 or less life." (Marina Vendrell's Grimoire): the state-based action does
    nothing to the controller of the permanent (any other reason to lose still does)."""
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    for c in plan.state.cards.values():
        if c.controller != player or not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)
        if any(i not in skip and d.get("kind") == "static" and d.get("zero_life_when_attached")
               for i, d in scripts.definitions(ch).items()):
            host = plan.state.cards.get(c.attached_to or "")
            if host is not None and host.zone.endswith(":battlefield") and "Creature" in plan.ch(host).types:
                return True
        if any(i not in skip and d.get("kind") == "static" and (d.get("zero_life") or (d.get("static") == KIND and d.get("you") == "zero_life"))
               for i, d in scripts.definitions(ch).items()):
            return True
    return False


# -- resolved effects (wave 22B) -- "You can't lose the game this turn and your opponents can't win the game this turn." (Angel's Grace),
# "Players can't lose the game or win the game this turn." (Everybody Lives!): 611.2a: it affects the players it names as it resolves, until the
# turn ends (the cleanup step's state-based check still sees it, 514.3a); 104.2a: the last player left wins anyway.
_CLAUSE = r"(?:you|your opponents|players) can't (?:lose|win) the game(?: or (?:win|lose) the game)? this turn"
_ONE = re.compile(r"(?P<who>you|your opponents|players) can't (?P<a>lose|win) the game(?: or (?P<b>win|lose) the game)? this turn")
_SENTENCE = re.compile(rf"^(?P<c1>{_CLAUSE})(?:,? and (?P<c2>{_CLAUSE}))?$")
_WHO = {"you": "you", "your opponents": "each_opponent", "players": "each_player"}


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    out: list[dict[str, Any]] = []
    for clause in filter(None, (m["c1"], m["c2"])):
        c = _ONE.fullmatch(clause)
        assert c is not None
        out += [{"do": "cant_result", "who": _WHO[c["who"]], "what": w} for w in (c["a"], c["b"]) if w]
    return out, None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_SENTENCE, _build)]


def cant_result(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import _players

    r = plan.rules
    turn = plan.state.turn.number
    r.results = [x for x in r.results if x["turn"] == turn]
    for pid in _players(plan, ctx, e["who"]):
        r.results.append({"player": pid, "what": e["what"], "turn": turn})
        plan.note(f"{plan.name(pid)} can't {e['what']} the game this turn", actor=ctx["controller"])
    return True


PRIMITIVES = {"cant_result": cant_result}
