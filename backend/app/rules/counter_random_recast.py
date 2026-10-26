"""CR 608.2c/h, 201.2a: counter, random mill, then cast a differently named card.

Tibalt's Trickery's official rulings (2021-02-05):
https://api.scryfall.com/cards/dd921e27-3e08-438c-bec2-723226d35175/rulings
The original spell's name/controller are captured before countering. Counter failure
is independent of the remaining instructions. Cleanup follows the optional casting.
"""
from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ("Counter target spell. Choose 1, 2, or 3 at random. Its controller mills that many cards, then exiles cards "
         "from the top of their library until they exile a nonland card with a different name than that spell. "
         "They may cast that card without paying its mana cost. Then they put the exiled cards on the bottom of their library in a random order.")
_KEY = 'counter_random_recast'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() != _TEXT:
        return None
    return ([{'do': _KEY}, {'do': _KEY + '_scan'}, {'do': _KEY + '_bottom'}], 'spell', False)


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import card_names, context, effects

    spells = effects._stack_targets(plan, ctx, {'who': 'target'})
    if not spells:
        return True
    spell = spells[0]
    entry = plan.rules.stack.get(spell)
    card = plan.state.cards.get(spell)
    if card is None:
        return True
    pid = entry.controller if entry is not None else card.controller
    names = card_names.reference_names(plan.ch(card))  # (Spy Kit, wave 110J: a rule-named spell also carries the ANY_CREATURE sentinel)
    n = (plan.rng or secrets.SystemRandom()).randint(1, 3)
    ctx[_KEY] = {'player': pid, 'names': names, 'exiled': []}
    context.bind_players(ctx, _KEY, [pid])
    effects.counter_object(plan, spell, ctx['controller'], by=ctx['controller'])
    plan.note(f"Choose 1, 2, or 3 at random: {n}")
    # Milling may pause for replacement choices. Keep its existing resumable primitive,
    # after the already completed counter/random choice, so neither is repeated.
    at = int(ctx.get('next') or 0)
    ctx['effects'] = [*ctx['effects'][:at], {'do': 'mill', 'who': 'ref:' + _KEY, 'n': n}, *ctx['effects'][at:]]
    return True


def scan(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import card_names, granted_casts
    from app.rules import characteristics as chars

    data = ctx.get(_KEY)
    if data is None or data['player'] not in plan.live():
        return True
    pid = data['player']
    for _ in range(len(plan.state.zones.get(zone_key(pid, 'library'), []))):
        library = plan.state.zones.get(zone_key(pid, 'library'), [])
        if not library:
            break
        cid = library[0]
        plan.do({'type': 'move', 'card_ids': [cid], 'to': {'player': pid, 'zone': 'exile'}}, actor=pid)
        card = plan.state.cards.get(cid)
        if card is None or not card.zone.endswith(':exile'):
            continue
        data['exiled'].append({'card': cid, 'object': plan.oid(card)})
        ch = chars.of(card, plan.info)
        if not ch.is_land and not any(card_names.has_name(ch, n) for n in data['names']):
            # "ripple" means leave the declined card exiled and continue this resolution
            # after casting, declining, or abandoning the optional cast (608.2g).
            return granted_casts.ask(plan, ctx, player=pid, cid=cid, head="A differently named nonland card",
                                     no="Put the exiled cards on the bottom", decline='ripple')
    return True


def bottom(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    data = ctx.pop(_KEY, None)
    if data is None or data['player'] not in plan.live():
        return True
    cards = [r['card'] for r in data['exiled'] if (card := plan.state.cards.get(r['card'])) is not None
             and card.zone.endswith(':exile') and plan.oid(card) == r['object']]
    effects.bottom_at_random(plan, data['player'], cards)
    return True


PRIMITIVES = {_KEY: prepare, _KEY + '_scan': scan, _KEY + '_bottom': bottom}
