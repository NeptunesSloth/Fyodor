"""A return instruction records the new object that actually entered before reflexive targeting."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.game.rules_state import ObjectRef, TriggerEvent, copy_recipe_of, snapshot
from app.rules import characteristics, context, granted

if TYPE_CHECKING:
    from app.rules.plan import Plan


class EntryReceipt(BaseModel):
    turn: int
    start: int
    selected: list[ObjectRef]
    source_object: str | None = None


def begin(plan: Plan, ctx: dict[str, Any], name: str, cards: list[str]) -> None:
    selected = [ref for cid in cards if (ref := context.ref_of(plan, cid)) is not None]
    receipt = EntryReceipt(turn=plan.state.turn.number, start=len(plan.rules.turn_log.entered), selected=selected, source_object=ctx.get("source_object"))
    context.refs(ctx)[name] = {'kind': 'entry_receipt56', 'receipt': receipt.model_dump(mode='json')}


def finish(plan: Plan, ctx: dict[str, Any], name: str) -> None:
    binding = context.refs(ctx).get(name) or {}
    if binding.get('kind') != 'entry_receipt56':
        return
    receipt = EntryReceipt.model_validate(binding['receipt'])
    entered = plan.rules.turn_log.entered[receipt.start:] if receipt.turn == plan.state.turn.number else []
    found = []
    for old in receipt.selected:
        matches = [entry for entry in entered if entry.card == old.card and entry.from_zone == old.zone and entry.object_id != old.object_id and entry.via == receipt.source_object]
        if len(matches) != 1:
            continue
        entry = matches[0]
        card = plan.state.cards.get(entry.card)
        # A committed entry, rather than merely a successor object or chosen card, is the receipt.
        snap = plan.rules.lki.get(entry.object_id)
        if card is not None and plan.oid(card) == entry.object_id:
            snap = snapshot(plan.state, card.id)
            snap.copy_recipe = copy_recipe_of(plan.rules, entry.object_id)
            ch = plan.ch(card)
            snap.abilities, snap.keywords, snap.traits = granted.last_existed(characteristics.of(card, plan.info), ch)
            snap.name = ch.name
            snap.power, snap.toughness = ch.pt or (None, None)
        found.append(ObjectRef(card=entry.card, object_id=entry.object_id, zone=f'{entry.controller}:battlefield', snapshot=snap).model_dump(mode='json'))
    context.refs(ctx)[name] = {'kind': 'objects', 'objects': found}
    context.bind_payment(ctx, name + ':paid', bool(found))


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    recipes = {
        "Return target creature card from your graveyard to the battlefield. When you do, it fights up to one target creature you don't control.": (
            'Return target creature card from your graveyard to the battlefield.',
            "It fights up to one target creature you don't control."),
        "Return target permanent card in an opponent's graveyard to the battlefield under their control. When that permanent enters, return up to one target permanent card with equal or lesser mana value from your graveyard to the battlefield.": (
            "Return target permanent card from an opponent's graveyard to the battlefield under its owner's control.",
            'Return up to one target permanent card with equal or lesser mana value from your graveyard to the battlefield.'),
    }
    recipe = recipes.get(body)
    if recipe is None:
        return None
    first = scripts.parse_effects(recipe[0])
    second = scripts.parse_effects(recipe[1], 'event')
    if first is None or second is None or len(first[0]) != 1 or first[0][0].get('do') != 'return_card':
        return None
    name = 'entered56'
    first[0][0]['entry_receipt56'] = name
    ability = {'kind': 'triggered', 'trigger': 'reflexive', 'effects': second[0], 'optional': second[2], **scripts.target_fields(second[1])}
    return [*first[0], {'do': 'reflexive', 'entry_receipt56': name, **({'entry_cause56': True} if 'When that permanent enters,' in body else {}), 'cond': {'succeeded': name + ':paid'}, 'lki': name, 'ability': ability}], first[1], first[2]


def object_deferred(effects: list[dict[str, Any]]) -> set[int]:
    """Only an actual preceding entry receipt can provide this child its one-object event."""
    from app.rules import scripts

    out = set()
    for i, effect in enumerate(effects):
        name = effect.get('entry_receipt56')
        if i == 0 or not name or effect.get('do') != 'reflexive' or effect.get('lki') != name:
            continue
        previous = effects[i - 1]
        if previous.get('do') != 'return_card' or previous.get('to') != 'battlefield' or previous.get('entry_receipt56') != name:
            continue
        ability = effect.get('ability')
        if isinstance(ability, dict) and scripts._event_refs_ok({**ability, 'trigger': 'event', 'cond': {'event': 'enter', 'subject': 'sel'}}):
            out.add(i)
    return out


def suppressed(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    """Jailbreak explicitly waits for entering; a 'When you do' instruction trigger is distinct."""
    if not effect.get('entry_cause56'):
        return False
    from app.rules import trigger_multipliers

    binding = context.refs(ctx).get(effect['entry_receipt56']) or {}
    objects = [ObjectRef.model_validate(ref) for ref in binding.get('objects') or []]
    return trigger_multipliers.suppressed(plan, TriggerEvent(kind='enter', objects=objects, count=len(objects)), ctx['controller'], permanent=False)
