"""-- wave 110B -- Mystic Reflection: "Choose target nonlegendary creature. The next time one or more creatures or planeswalkers enter this
turn, they enter as copies of the chosen creature."

614.1c, 614.12, 707.5: a one-shot replacement effect kept in the turn log (``TurnLog.mirror110b``, the chosen creatures, oldest first). The first
entry event with a creature or planeswalker uses it up (614.5), and every such object of that event (a ``move_together`` batch, a token creation,
or one spell resolving) enters as a copy of the chosen creature, as it is when they enter (707.2). A card with its own "may enter as a copy"
replacement applies that one last (616.1), like Essence of the Wild (copying.entering). Two effects waiting for one event all apply to it (614.5);
if they chose different creatures the order (616.1: the affected object's controller picks, the last copy wins) is left to manual play, with a note.
"""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

TEXT = ("Choose target nonlegendary creature. The next time one or more creatures or planeswalkers enter this turn, "
        "they enter as copies of the chosen creature.")


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() != TEXT:
        return None
    got = scripts.parse_effects("Target nonlegendary creature gains haste until end of turn.")
    return None if got is None else ([{"do": "mirror110b", "who": "target"}], got[1], got[2])


def mirror(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import turn_log_now
    from app.rules import effects

    log = turn_log_now(plan.state)
    ids = effects._cards(plan, ctx, e["who"])
    if log is not None and ids:
        log.mirror110b.append(ids[0])
    return True


def _qualifies(plan: Plan, card: Any, controller: str) -> bool:
    from app.game.state import zone_key

    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    return ch.is_creature or "Planeswalker" in ch.types


def _copy(plan: Plan, card: Any, controller: str, chosen: str) -> None:
    from app.game.rules_state import CopyEntrySource
    from app.rules import copying

    source = plan.state.cards.get(chosen)
    if copying.entering_as_copy(plan, card):
        return
    if source is None or not source.zone.endswith(":battlefield"):  # (its last known copiable values aren't kept: it enters as itself)
        plan.note(f"Mystic Reflection: the chosen creature is gone, so {card.name or 'it'} enters as itself", actor=controller)
        return
    copying.add_copy_effect(plan, [plan.oid(card)], copying.recipe_of(plan, source), controller, source=copying.ENTERING + card.id,
                            entry_source=CopyEntrySource(card=source.id, object_id=plan.oid(source), controller=source.controller))


def apply(plan: Plan, cards: list[tuple[Any, str]]) -> None:
    """The cards (with their controllers) entering in one event: the first waiting effect is used up if any of them is a creature or planeswalker."""
    from app.game.rules_state import turn_log_now
    from app.rules import copying

    log = turn_log_now(plan.state)
    if log is None:
        return
    hit = [(c, p) for c, p in cards if _qualifies(plan, c, p)]
    batch, _, chosen = log.mirror_open110b.partition("|")
    if not hit:
        return
    if batch != str(plan.rules.batch):  # a new entry event: the oldest waiting effect is used up (614.5); until the next step it covers the whole event
        if not log.mirror110b:
            return
        waiting, log.mirror110b = log.mirror110b[:], []  # every waiting effect applies to this event (614.5)
        chosen = waiting[0] if len(set(waiting)) == 1 else ""  # (different creatures: 616.1, the order is the controller's choice — by hand)
        log.mirror_open110b = f"{plan.rules.batch}|{chosen}"
    for c, p in hit:
        if not chosen:
            plan.note(f"Mystic Reflection: two effects want {c.name or 'it'} to enter as different copies; its controller picks the order "
                      "(616.1) — copy by hand", actor=p)
        elif copying.enter_definition(plan, c) is not None:
            log.mirror_late110b.append(f"{c.id}|{chosen}")
        else:
            _copy(plan, c, p, chosen)


def late(plan: Plan, card: Any, controller: str) -> None:
    """The card's own "may enter as a copy" did not apply (declined): the used-up effect's copy stays."""
    from app.game.rules_state import turn_log_now

    log = turn_log_now(plan.state)
    for w in list(log.mirror_late110b) if log is not None else []:
        cid, _, chosen = w.partition("|")
        if cid == card.id:
            log.mirror_late110b.remove(w)  # type: ignore[union-attr]
            _copy(plan, card, controller, chosen)


PRIMITIVES: dict[str, Any] = {"mirror110b": mirror}
