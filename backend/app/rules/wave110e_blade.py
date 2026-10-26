"""-- wave 110E -- "As this Equipment becomes attached to a creature, choose a color." (Sanctuary Blade).

701.3a: attaching moves the Equipment; the color is chosen by its controller as it becomes attached (it is no trigger, nothing can respond), and
"the last chosen color" is the most recent such choice, kept on the Equipment like an entering choice ("Chosen color"). Every way to attach goes
through attachments.attach (one decision slot, possibly busy): it queues the Equipment, engine.settle asks before anyone gets priority.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STATIC = "attach_choice110e"
LINE = "As this Equipment becomes attached to a creature, choose a color."
CRAFT_LINE = "As this Equipment becomes attached to a creature, choose an exiled creature card used to craft this Equipment."  # Dinosaur Headdress
LINES = (LINE, CRAFT_LINE)


def kind(plan: Plan, card: Any) -> str | None:
    texts = {ab.text for ab in plan.ch(card).abilities}
    from app.rules import wave110a_paper  # -- (wave 110A) -- Psychic Paper asks for a name and a type

    return "color" if LINE in texts else "craft" if CRAFT_LINE in texts else "paper" if wave110a_paper.ASK in texts else None


def craft_options(plan: Plan, card: Any) -> list[Any]:
    """702.167a: the exiled creature cards used to craft it that are still in exile (the same objects, 400.7)."""
    out = []
    for ref in plan.rules.crafted_materials.get(plan.oid(card), []):
        mat = plan.state.cards.get(ref.card)
        if mat is not None and plan.oid(mat) == ref.object_id and mat.zone.endswith(":exile") and not mat.is_token and "Creature" in plan.ch(mat).types:
            out.append(mat)
    return out


def queue(plan: Plan, card_id: str) -> None:

    card = plan.state.cards.get(card_id)
    if card is not None and card.zone.endswith(":battlefield") and kind(plan, card) and card_id not in plan.rules.attach_asks110e:
        plan.rules.attach_asks110e.append(card_id)


def ask(plan: Plan, queued: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide
    from app.rules.protection_grants import COLORS

    src = plan.state.cards.get(queued[0])
    if src is None or not src.zone.endswith(":battlefield") or src.attached_to is None:
        queued.pop(0)  # it left or came unattached before it was asked: nothing to choose
        return ask(plan, queued) if queued else None
    if kind(plan, src) == "paper":
        from app.rules import wave110a_paper

        return wave110a_paper.ask(plan, src)
    if kind(plan, src) == "craft":
        found = craft_options(plan, src)
        options = [DecisionOption(id=c.id, label=c.name) for c in found]
        if len(options) < 2:  # nothing or one card to choose: no question
            queued.pop(0)
            if options:
                _copy(plan, src, found[0])
            return ask(plan, queued) if queued else None
        prompt = f"{src.name}: choose an exiled creature card used to craft it"
    else:
        options, prompt = [DecisionOption(id=c, label=c) for c in COLORS], f"{src.name}: choose a color"
    decide(plan, player=src.controller, kind="choose_one", prompt=prompt, source=src, options=options, resume={"step": "attach_choice110e", "card": src.id})


def _copy(plan: Plan, src: Any, chosen: Any) -> None:
    """613.2a: the equipped creature is a copy of the chosen card (its printed copiable values, 707.2) for as long as this Equipment stays attached (611.2b)."""
    from app.rules import copying

    host = plan.state.cards.get(src.attached_to or "")
    problem = copying.supported_source(plan, chosen)
    if host is None or problem is not None:
        plan.note(f"{src.name}: {host.name if host else 'the creature'} can't become a copy of {chosen.name} automatically ({problem}); set it by hand", [src.id])
        return
    plan.do({"type": "set_choice", "card_id": src.id, "key": "Chosen card", "value": chosen.name}, actor=src.controller)
    copying.add_copy_effect(plan, [plan.oid(host)], copying.recipe_of(plan, chosen), src.controller)
    made = plan.rules.effects[-1]
    made.duration, made.source_card, made.source = "while_attached110l", src.id, plan.oid(src)
    plan.note(f"{host.name} becomes a copy of {chosen.name} while {src.name} stays attached", [host.id, chosen.id])


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules.protection_grants import COLORS

    card = d.resume["card"]
    src = plan.state.cards[card]
    if card in plan.rules.attach_asks110e:
        plan.rules.attach_asks110e.remove(card)
    if kind(plan, src) == "craft":
        pick = next((c for c in craft_options(plan, src) if len(chosen) == 1 and c.id == chosen[0]), None)
        if pick is None:
            raise ActionError("Choose one of the exiled cards")
        plan.note(f"{plan.name(d.player)} chooses {pick.name}", [pick.id], actor=d.player)
        return _copy(plan, src, pick)
    if len(chosen) != 1 or chosen[0] not in COLORS:
        raise ActionError("Choose one of the colors")
    plan.note(f"{plan.name(d.player)} chooses {chosen[0].lower()}", actor=d.player)
    plan.do({"type": "set_choice", "card_id": card, "key": "Chosen color", "value": chosen[0]}, actor=d.player)


PRIMITIVES: dict[str, Any] = {}
from app.rules import wave110a_paper as _paper  # noqa: E402  -- wave 110A --

RESUME: dict[str, Any] = {"attach_choice110e": resume, **_paper.RESUME}
