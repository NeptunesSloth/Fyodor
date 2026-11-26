"""-- loss sources -- which card made a player lose the game, recorded with the loss (``RulesState.lost_source``) for the table's ending
screen (frontend game/TestEnding.tsx) instead of a guess from the log.

Only public facts: a card every player can see when it acts (its name and printing; a token's name), never a face-down or hidden one.

* "lose the game" (104.3e: Final Fortune's delayed trigger, win_game.finish_loss): the spell or ability's source card;
* another player wins (104.2b, replace._win): the source of the effect that won;
* 0 or less life (704.5a): the last source that lowered the player's life (``harm``, kept as it happens: a damage step's source, else the
  spell or ability resolving), if nothing changed the life total since — a hand-made change, or harm with no source, leaves none;
* ten poison counters (704.5c): likewise for the last poison counters;
* 21 combat damage from one commander (903.10a): that commander;
* a draw from an empty library (704.5b): the spell or ability that made the player draw (none for the draw step's draw).

The harm marks and the losses are rules state, synced with the rest of it (rules_sync), so replays and saves agree; old saves have none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import LossSource

if TYPE_CHECKING:
    from app.game import actions as A
    from app.rules.plan import Plan

# table steps that can lower a life total or add poison counters
HARM_STEPS = frozenset({"life", "set_life", "rules_damage", "rules_life_changes", "rules_mana", "resource", "set_resource"})
POISON = "poison"


def of_card(plan: Plan, card_id: str | None) -> LossSource | None:
    """The public name (and printing) of a card every player can see now; None for anything else."""
    from app.game import ops

    card = plan.state.cards.get(card_id or "")
    if card is None or card.face_down or card.ability is not None or not ops.visible_to_all_players(plan.state, card):
        return None
    try:
        name = plan.ch(card).name or card.name
    except Exception:  # noqa: BLE001 - a name for a screen: the card's own when its characteristics can't be read
        name = card.name
    return LossSource(name=(name or "")[:200], card_id=card.card_id) if name else None


def of_object(plan: Plan, oid: str | None) -> LossSource | None:
    """A source named by its rules object (a damage event's): the card while it's that object, else its last known information as it was
    on the battlefield face up (608.2h)."""
    if not oid:
        return None
    card = next((c for c in plan.state.cards.values() if plan.oid(c) == oid), None)
    if card is not None:
        return of_card(plan, card.id)
    snap = plan.rules.lki.get(oid)
    if snap is None or snap.face_down or not snap.name:
        return None
    return LossSource(name=snap.name[:200], card_id=snap.printing)


def before(plan: Plan) -> dict[str, tuple[int, int]]:
    return {pid: (p.life, p.resources.get(POISON, 0)) for pid, p in plan.state.players.items()}


def after(plan: Plan, step: A.Action, was: dict[str, tuple[int, int]]) -> None:
    """After a step that may harm a player: mark who lowered a life total or added poison counters (or that nothing known did)."""
    dealt = getattr(step, "dealt", None) or []
    for pid, (life, poison) in was.items():
        p = plan.state.players.get(pid)
        if p is None:
            continue
        for kind, old, new in (("life", life, p.life), (POISON, poison, p.resources.get(POISON, 0))):
            if (new >= old) if kind == "life" else (new <= old):
                continue
            hits = [d for d in dealt if d.target == pid and d.amount > 0]
            src = of_object(plan, hits[-1].source) if hits else of_card(plan, plan.effect_source)
            mark(plan, pid, kind, src, new)


def mark(plan: Plan, pid: str, kind: str, src: LossSource | None, at: int | None = None) -> None:
    key = f"{pid}:{kind}"
    if src is None:
        plan.rules.harm_sources.pop(key, None)
    else:
        plan.rules.harm_sources[key] = src.model_copy(update={"at": at})


def drew_from_empty(plan: Plan, pid: str) -> None:
    """704.5b: the draw from an empty library — the spell or ability that made the player draw (none: the draw step's own draw)."""
    mark(plan, pid, "draw", of_card(plan, plan.effect_source))


def for_sba(plan: Plan, pid: str, reason: str) -> LossSource | None:
    """The source of a state-based loss (sba.find's reasons), if one is known."""
    p = plan.state.players[pid]
    harm = plan.rules.harm_sources
    if reason.endswith("life"):
        got = harm.get(f"{pid}:life")
        return got if got is not None and got.at == p.life else None
    if reason.endswith("poison counters"):
        got = harm.get(f"{pid}:{POISON}")
        return got if got is not None and got.at == p.resources.get(POISON, 0) else None
    if "from one commander" in reason:
        from app.rules.sba import COMMANDER_LETHAL

        return _commander(plan, next((k for k, v in p.commander_damage.items() if v >= COMMANDER_LETHAL), None))
    if "empty library" in reason:
        return harm.get(f"{pid}:draw")
    return None


def _commander(plan: Plan, key: str | None) -> LossSource | None:
    """903.10a: the commander that dealt the damage (who a player's commander is is public, 903.3)."""
    card = next((c for c in plan.state.cards.values() if key and c.commander_key == key), None)
    return LossSource(name=card.name[:200], card_id=card.card_id) if card is not None and card.name else None


def lost(plan: Plan, pid: str, src: LossSource | None) -> None:
    """Record the loss's source (or that none is known), and forget the player's harm marks."""
    r = plan.rules
    if src is not None:
        r.lost_source[pid] = src.model_copy(update={"at": None})
    else:
        r.lost_source.pop(pid, None)
    for kind in ("life", POISON, "draw"):
        r.harm_sources.pop(f"{pid}:{kind}", None)


def view(rules: Any) -> dict[str, dict[str, Any]]:
    """For every viewer (public): player -> {name, card_id} of what made them lose."""
    return {pid: {"name": s.name, "card_id": s.card_id} for pid, s in rules.lost_source.items() if pid in rules.lost}
