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


# Don't Blink: creatures entering from exile, or as a spell cast from exile, are shuffled into their owners' libraries instead (614.1a, 701.24).
SHUFFLE = "Until end of turn, if one or more creatures would enter from exile or after being cast from exile, their owners shuffle them into their libraries instead."


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    if body.strip() == SHUFFLE:
        return [{'do': 'replace_record', 'event': 'creature_entry_exile110h', 'match': {}, 'op': {'do': 'shuffle_in'}}], None, False
    if body.strip() == TIMED.replace('a creature', 'a nontoken creature'):  # -- as long as (wave 100K) -- Mistcaller: tokens still enter (its 2018-07-13 ruling)
        return [{'do': 'replace_record', 'event': 'creature_entry', 'match': {'nontoken': True}, 'op': {'do': 'exile'}}], None, False
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


def shuffles(plan: Plan, card: CardInstance, controller: str, *, both: bool = False) -> bool:
    """-- cards (wave 110H) -- Don't Blink: a creature entering from exile, or a creature spell cast from exile. When an exile replacement applies
    too, ``conflict`` holds the creature for its controller's 616.1 choice (``both``: ignore that second effect here)."""
    from app.rules import replace

    if not replace.candidates(plan, 'creature_entry_exile110h'):
        return False
    if card.id in plan.state.zones.get('stack', []):
        paid = plan.rules.payments.get(plan.oid(card))
        if paid is None or paid.cast_from != 'exile':
            return False
    elif not card.zone.endswith(':exile') or (exiles(plan, card, controller) and not both):
        return False
    probe = card.model_copy(update={'zone': zone_key(controller, 'battlefield'), 'controller': controller})
    return 'Creature' in plan.ch(probe).types


def conflict(plan: Plan, card: CardInstance, controller: str) -> bool:
    """616.1: an exile-instead replacement and Don't Blink's shuffle both apply to this entry."""
    return shuffles(plan, card, controller, both=True) and exiles(plan, card, controller)


def hold(plan: Plan, card: CardInstance) -> None:
    """Park the creature for the 616.1 question of its controller (its owner if it has no controller): exile it, or reveal and shuffle it in (offer_616)."""
    from app.rules import replacements

    replacements._pick(plan, card, [replacements.Cand("Exile replacement", "exile"), replacements.Cand("Don't Blink", "library:shuffle")], "exile")
    plan.rules.pending_616[card.id]["entry110h"] = True


def shuffle_in(plan: Plan, card_id: str) -> None:
    card = plan.state.cards[card_id]
    owner = card.owner
    plan.do({"type": "move", "card_ids": [card_id], "to": {"player": owner, "zone": "library"}}, actor=owner)
    plan.do({"type": "shuffle", "player": owner, "zone": "library"}, actor=owner)


def token_exiles(plan: Plan, controller: str, spec: dict[str, Any]) -> bool:
    from app.game.rules_state import CopyRecipe
    from app.rules import copying, replacements

    if spec.get('_copy') is not None:
        ch = copying.characteristics(CopyRecipe.model_validate(spec['_copy']), plan.info)
        spec = {'name': ch.name, 'power': ch.power, 'toughness': ch.toughness,
                'colors': sorted(ch.colors), 'type_line': copying.type_line(ch), 'text': ch.oracle_text}
    probe = replacements._token_probe(controller, spec)
    from app.rules import entry_payment_diversion

    with plan.reading():  # (big boards: the probe's field is worked out in a read pass, token_copy_entry.prospect; this only reads)
        definitions = list(replacements._definitions(plan, probe).values())
    return entry_payment_diversion.applies(plan, probe, definitions) or exiles(plan, probe, controller)


def move(plan: Plan, payload: dict[str, Any]) -> dict[str, Any]:
    """Prepare every destination against the same pre-entry environment."""
    routes = dict(payload.get('routes') or {})
    changed = False
    shuffled: list[str] = []
    for cid in payload.get('card_ids') or []:
        dest = routes.get(cid, payload.get('to') or {})
        card = plan.state.cards.get(cid)
        if card is None or dest.get('zone') != 'battlefield' or card.zone.endswith((':battlefield', ':phased')):
            continue
        controller = (payload.get('controllers') or {}).get(cid) or dest.get('player') or card.controller
        from app.rules import entry_characteristics

        if plan.rules.specimens110f and dest.get('player'):  # -- wave 110F -- Gather Specimens (backstop: a path that didn't redirect before asking its questions)
            from app.rules import wave110f_fin

            taken110f = wave110f_fin.entering_player(plan, dest['player'])
            if taken110f != dest['player'] and wave110f_fin.creature_entering(plan, card, taken110f):
                routes[cid] = {**dest, 'player': taken110f}
                controller = taken110f
                changed = True

        probe = entry_characteristics.probe(card, (payload.get('entry_characteristics') or {}).get(cid))
        if cid in (payload.get('back_ids') or []):
            probe = probe.model_copy(update={'face': 1})
        if conflict(plan, probe, controller):  # -- cards (wave 110H) -- 616.1: its controller chooses which of the two replacements applies
            hold(plan, card)
            shuffled.append(cid)
            changed = True
        elif exiles(plan, probe, controller):
            routes[cid] = {'player': card.owner, 'zone': 'exile'}
            changed = True
        elif shuffles(plan, probe, controller):  # -- cards (wave 110H) -- Don't Blink: shuffled in instead of entering
            shuffle_in(plan, cid)
            shuffled.append(cid)
            changed = True
    if shuffled:  # (the rest move as asked; none left: a log line, as replace_move does)
        rest = [c for c in payload.get('card_ids') or [] if c not in shuffled]
        if not rest:
            return {'type': 'rules_log', 'text': "Shuffled into its owner's library instead", 'card_ids': shuffled[:20]}
        payload = {**payload, 'card_ids': rest}
    if changed:
        for cid in payload.get('card_ids') or []:
            routes.setdefault(cid, payload.get('to') or {})
        return {**payload, 'routes': routes}
    return payload
