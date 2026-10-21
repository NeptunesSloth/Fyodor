"""CR 614.12: exile creatures entering without having been cast."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.state import CardInstance, zone_key

if TYPE_CHECKING:
    from app.rules.plan import Plan

CLAUSE = "If a nontoken creature would enter and it wasn't cast, exile it instead."
TIMED = "Until end of turn, if a creature would enter and it wasn't cast, exile it instead."


def definition(text: str) -> dict[str, Any] | None:
    if text != CLAUSE:
        return None
    return {'kind': 'static', 'static': 'replace', 'event': 'creature_entry',
            'match': {'nontoken': True}, 'op': {'do': 'exile'}}


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    if body not in (TIMED, TIMED + ' Draw a card.'):
        return None
    effects: list[dict[str, Any]] = [{'do': 'replace_record', 'event': 'creature_entry', 'match': {}, 'op': {'do': 'exile'}}]
    if body != TIMED:
        effects.append({'do': 'draw', 'who': 'you', 'n': 1})
    return effects, None, False


def exiles(plan: Plan, card: CardInstance, controller: str) -> bool:
    from app.rules import replace

    found = replace.candidates(plan, 'creature_entry')
    if not found:
        return False
    # Only the current spell's cast matters. A formerly cast permanent blinked
    # from exile/graveyard is a new object, not the spell that became it.
    paid = plan.rules.payments.get(plan.oid(card)) if card.id in plan.state.zones.get('stack', []) else None
    if paid is not None and paid.cast_from is not None:
        return False
    if not any(not c.match.get('nontoken') or not card.is_token for c in found):
        return False
    probe = card.model_copy(update={'zone': zone_key(controller, 'battlefield'), 'controller': controller})
    return 'Creature' in plan.ch(probe).types


def token_exiles(plan: Plan, controller: str, spec: dict[str, Any]) -> bool:
    from app.game.rules_state import CopyRecipe
    from app.rules import copying, replacements

    if spec.get('_copy') is not None:
        ch = copying.characteristics(CopyRecipe.model_validate(spec['_copy']), plan.info)
        spec = {'name': ch.name, 'power': ch.power, 'toughness': ch.toughness,
                'colors': sorted(ch.colors), 'type_line': copying.type_line(ch), 'text': ch.oracle_text}
    probe = replacements._token_probe(controller, spec)
    from app.rules import entry_payment_diversion

    definitions = list(replacements._definitions(plan, probe).values())
    return entry_payment_diversion.applies(plan, probe, definitions) or exiles(plan, probe, controller)


def move(plan: Plan, payload: dict[str, Any]) -> dict[str, Any]:
    """Prepare every destination against the same pre-entry environment."""
    routes = dict(payload.get('routes') or {})
    changed = False
    for cid in payload.get('card_ids') or []:
        dest = routes.get(cid, payload.get('to') or {})
        card = plan.state.cards.get(cid)
        if card is None or dest.get('zone') != 'battlefield' or card.zone.endswith((':battlefield', ':phased')):
            continue
        controller = (payload.get('controllers') or {}).get(cid) or dest.get('player') or card.controller
        from app.rules import entry_characteristics

        probe = entry_characteristics.probe(card, (payload.get('entry_characteristics') or {}).get(cid))
        if cid in (payload.get('back_ids') or []):
            probe = probe.model_copy(update={'face': 1})
        if exiles(plan, probe, controller):
            routes[cid] = {'player': card.owner, 'zone': 'exile'}
            changed = True
    if changed:
        for cid in payload.get('card_ids') or []:
            routes.setdefault(cid, payload.get('to') or {})
        return {**payload, 'routes': routes}
    return payload
