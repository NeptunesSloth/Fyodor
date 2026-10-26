"""-- can't lose life (wave 29D) -- "Your life total can't change." (Platinum Emperion), "Until end of turn, your life total can't change, and
permanents you control gain hexproof and indestructible." (Flare of Fortitude), "Until your next turn, your life total can't change and you gain
protection from everything." (Teferi's Protection). Researched against CR 2026-09-25.

* 119.7 / 119.8: a player whose life total can't change can neither gain nor lose life: an exchange of life totals that would raise or lower it
  doesn't happen, and "a cost that involves having that player pay life can't be paid"; 119.4b: 0 life can always be paid, even then.
* 614.17: such an effect isn't a replacement effect but follows similar rules: it must exist before the event (614.17a); a player can't choose to
  pay a cost that includes the event (614.17b); and the event, if it can't happen, can't be modified by a replacement or prevention effect other than
  a self-replacement (614.17c) - Bloodletter of Aclazotz doesn't double a loss that can't happen.
* 120.3a: damage dealt to the player is still dealt (the damage events, "was dealt damage this turn", bloodthirst, "whenever ~ is dealt damage" all
  happen); the life loss it would cause is the event that can't. Poison counters (120.3b) and the lifelink gain (120.3f, its own gain event) are
  other results: lifelink gains nothing for a player whose life total can't change (119.7).
* A static ability's lock applies while its source is on the battlefield (611.3a); a resolved effect's for its stated duration: "until end of turn"
  ends at the cleanup step (514.2), "until your next turn" as the controller's next turn begins (611.2b, 500.4).

``why_not`` is read at every place a player would lose or gain life (``replace.lose_life``, ``gain_life``, the damage planner, the life lost to damage
of a mana ability) and at every place life is paid (``pay_problem``: spells' additional costs, Phyrexian mana, activation costs, mana abilities,
effect payments, entering choices); ``app/rules/cant_gain.py`` asks it for the gain half.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.state import GameState

if TYPE_CHECKING:
    from app.rules.characteristics import CardInfo
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

_STATIC = "Your life total can't change."
_WHEN = r"(?:until end of turn|until your next turn)"
_EFFECT = re.compile(rf"^(?:(?P<lead>{_WHEN}), )?your life total can't change(?: (?P<tail>{_WHEN}))?$")


def static_definition(text: str) -> Definition | None:
    if text.strip() != _STATIC:
        return None
    return {"kind": "static", "static": "life_lock", "who": "you", "gain": True, "lose": True, "effects": []}


def _effect(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    when = m["lead"] or m["tail"]
    if bool(m["lead"]) == bool(m["tail"]):
        raise ValueError("one duration")
    return [{"do": "life_lock", "who": "you", "until": "turn" if when == "until end of turn" else "next_turn"}], None


def _template(m: re.Match[str]) -> Any:
    from app.rules.scripts import _NoMatch

    try:
        return _effect(m)
    except ValueError as exc:
        raise _NoMatch from exc


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (_EFFECT, _template),
    # -- can't lose life (wave 51C) -- "Players can't lose life this turn." (Everybody Lives!): no player loses life until end of turn (119.8); gaining is unaffected
    (re.compile(r"^players can't lose life this turn$"), lambda m: ([{"do": "life_lock", "who": "each", "lose_only": True, "until": "turn"}], None))]

# "Until end of turn, your life total can't change, and permanents you control gain hexproof and indestructible." is two instructions with one
# duration (608.2c); "… your life total can't change and you gain protection from everything." likewise (the shield's own wording ends with
# the duration: player_shields). (Perch Protection's "If the gift was promised, … and until your next turn, your life total can't change and you
# gain protection from everything." stays unread: its gift of an extra turn, 702.174g, is manual — app/rules/gift.py.)
_AND = re.compile(r"(?P<d>Until end of turn|Until your next turn), your life total can't change, and (?P<rest>[^.]+?)\.")
_SHIELD = re.compile(r"Until your next turn, your life total can't change and you gain protection from everything\.")


def rewrite(body: str) -> str:
    body = _AND.sub(lambda m: f"{m['d']}, your life total can't change. {m['d']}, {m['rest']}.", body)
    body = re.sub(r"\b(Players can't lose life this turn) and players (can't lose the game or win the game this turn)", r"\1. Players \2", body)  # (wave 51C: Everybody Lives!, two instructions of one sentence)
    body = _SHIELD.sub("Until your next turn, your life total can't change. You gain protection from everything until your next turn.", body)
    return body


# -- effects ---------------------------------------------------------------------------------------
def life_lock(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import live_players

    pid = ctx["controller"]
    r = plan.rules
    turn = plan.state.turn.number
    if e.get("who") == "target":  # -- target player (wave 110E) -- Teferi's Reproach: the target's life total; the lock ends with that player's turn (611.2b)
        from app.rules.effects import _players

        for t in _players(plan, ctx, "target"):
            r.life_locks.append({"id": secrets.token_hex(4), "player": t, "controller": pid, "ends_for": t, "gain": True, "lose": True, "until": e["until"],
                                 "turn": turn, "label": ctx.get("name") or "An effect"})
            plan.note(f"{plan.name(t)}'s life total can't change until their next turn ({ctx.get('name') or 'An effect'})", actor=pid)
        return True
    r.life_locks = [x for x in r.life_locks if not (x.get("until") == "turn" and x.get("turn") != turn)]
    label = ctx.get("name") or "An effect"
    if e.get("who") == "each":  # -- can't lose life (wave 51C) -- "Players can't lose life this turn.": one lock for each player, losing only
        for p in live_players(plan.state):
            r.life_locks.append({"id": secrets.token_hex(4), "player": p, "controller": pid, "gain": False, "lose": True, "until": e["until"], "turn": turn,
                                 "label": label})
        plan.note(f"Players can't lose life until end of turn ({label})", actor=pid)
        return True
    lose_only = bool(e.get("lose_only"))
    r.life_locks.append({"id": secrets.token_hex(4), "player": pid, "controller": pid, "gain": not lose_only, "lose": True, "until": e["until"], "turn": turn,
                         "label": label})
    restriction = f"{plan.name(pid)} can't lose life" if lose_only else f"{plan.name(pid)}'s life total can't change"
    plan.note(f"{restriction} {'until end of turn' if e['until'] == 'turn' else 'until their next turn'} ({label})",
              actor=pid)
    return True


PRIMITIVES = {"life_lock": life_lock}


def turn_began(plan: Plan, ended: set[tuple[str, int]]) -> None:
    """500.4 / 800.4m: "until your next turn" locks end as that player's next turn begins (or would have); "until end of turn" ones at the end of their turn."""
    r = plan.rules
    turn = plan.state.turn.number
    r.life_locks = [x for x in r.life_locks if not (x.get("until") == "next_turn" and any(
        x.get("ends_for", x.get("controller")) == p and n > int(x.get("turn") or 0) for p, n in ended))
        and not (x.get("until") == "turn" and x.get("turn") != turn)]


# -- reading them ----------------------------------------------------------------------------------
def why_not_state(state: GameState, info: CardInfo | None, player: str, what: str) -> str | None:
    """The effect that keeps ``player`` from losing (``what`` "lose") or gaining ("gain") life now, or None."""
    r = state.rules
    if r is None:
        return None
    from app.rules.plan import live_players

    turn = state.turn.number
    if r.life_locks:
        live = live_players(state)
        for rec in r.life_locks:
            if rec.get("player") == player and rec.get(what) and (rec.get("until") != "turn" or rec.get("turn") == turn) \
                    and rec.get("controller") in live:
                return str(rec.get("label") or "an effect")
    if info is None:
        return None
    from app.rules import cast_limits

    for src, d in cast_limits._statics(state, info, "life_lock"):
        if d.get(what) and d.get("who") == "you" and src.controller == player:
            return src.name or "a permanent"
    return None


def why_not(plan: Plan, player: str, what: str) -> str | None:
    return why_not_state(plan.state, plan.info, player, what)


def keep(plan: Plan, losses: list[tuple[str, int]], *, actor: str | None = None) -> list[tuple[str, int]]:
    """614.17c: the life losses that can happen; the others are not events at all (nothing replaces them, nothing triggers: 603.2g) - said in the log."""
    out = []
    for pid, n in losses:
        why = why_not(plan, pid, "lose") if n > 0 else None
        if why is None:
            out.append((pid, n))
        else:
            plan.note(f"{why}: {plan.name(pid)} can't lose life", actor=actor or pid)
    return out


def pay_problem(state: GameState, info: CardInfo | None, player: str, amount: int | None) -> str | None:
    """119.8, 614.17b: why ``player`` can't pay ``amount`` life (paying it is losing it), or None. 119.4b: 0 life can always be paid."""
    if not amount or amount <= 0:
        return None
    why = why_not_state(state, info, player, "lose")
    return f"{why}: {state.players[player].name} can't lose life, so they can't pay life" if why else None
