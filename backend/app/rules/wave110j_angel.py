"""Wave 110J final pass: Enduring Angel's life-total replacement.

"If your life total would be reduced to 0 or less, instead transform this creature and your life total becomes 3. Then if this creature
didn't transform this way, you lose the game." It is a replacement effect (614.1a), not a trigger: no stack, no response (ruling 2015-06-22),
so it is applied where the engine reduces a life total: ``Plan.do`` calls ``rewrite`` for a "life" loss and for damage dealt to players.
119.5: a life total that "becomes 3" is a gain or loss of the difference, here one set_life. A token or a copy that is not a double-faced
card cannot transform, so its controller loses the game (ruling 2015-06-22).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

TEXT = ("If your life total would be reduced to 0 or less, instead transform this creature and your life total becomes 3. "
        "Then if this creature didn't transform this way, you lose the game.")
KIND = "life_floor110j"


def definition(text: str) -> dict[str, Any] | None:
    if text.replace("~", "this creature") != TEXT:
        return None
    return {"kind": "replacement", "replacement": KIND, "effects": []}


def _watcher(plan: Plan, pid: str) -> CardInstance | None:
    from app.rules import scripts

    for cid in plan.state.zones.get(f"{pid}:battlefield", []):
        card = plan.state.cards[cid]
        if card.face_down or not plan.in_game(card) or plan.manual(card):
            continue
        if any(d.get("replacement") == KIND for d in scripts.definitions(plan.ch(card)).values() if d.get("kind") == "replacement"):
            return card
    return None


def rewrite(plan: Plan, payload: dict[str, Any], actor: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(payload, actions to apply after it): a reduction of a watching player's life total to 0 or less becomes "transform, life total 3"."""
    if payload["type"] == "life":
        losses = {payload["player"]: -int(payload["delta"])} if int(payload["delta"]) < 0 and payload.get("player") in plan.state.players else {}
    else:
        losses = {p: int(n) for p, n in (payload.get("players") or {}).items() if int(n) > 0 and p in plan.state.players}
    hit = [p for p, n in losses.items() if 0 < plan.state.players[p].life <= n and plan.state.players[p].life - n <= 0 and _watcher(plan, p) is not None]
    if not hit:
        return payload, []
    after: list[dict[str, Any]] = []
    for pid in hit:
        angel = _watcher(plan, pid)
        assert angel is not None
        before = (angel.face, plan.oid(angel))
        from app.rules import keyword_actions

        keyword_actions.transform(plan, {"controller": pid, "source_card": angel.id, "source_object": plan.oid(angel), "effects": [], "next": 0},
                                  {"do": "transform", "who": "self"})  # 701.28; 614.1a: instead of the reduction
        plan.note(f"{plan.name(pid)}'s life total would be reduced to 0 or less: {plan.state.cards[angel.id].name} replaces it, life total becomes 3")
        after.append({"type": "set_life", "player": pid, "value": 3})
        if plan.state.cards[angel.id].face == before[0]:  # didn't transform this way: the controller loses the game (after the life total is 3)
            after.append({"type": "lose110j", "player": pid})
    if payload["type"] == "life":
        return after[0], after[1:]
    players = {p: (0 if p in hit else n) for p, n in payload["players"].items()}
    return {**payload, "players": players}, after


def run_after(plan: Plan, after: list[dict[str, Any]], actor: str | None) -> None:
    from app.rules import win_game

    for f in after:
        if f["type"] == "lose110j":
            win_game.lose_game(plan, {"controller": f["player"], "effects": [], "next": 0}, {"do": "lose_game", "who": "you"})
        else:
            plan.do(f, actor=actor)
