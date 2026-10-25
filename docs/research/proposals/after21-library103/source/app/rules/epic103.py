"""Epic's independent public spell memory and perpetual native upkeep copies (702.50)."""
from __future__ import annotations

import secrets
from typing import Any

NAMES = {'Enduring Ideal', 'Endless Swarm', 'Eternal Dominion', 'Neverending Torment', 'Undying Flames'}
DOMINION = ("Search target opponent's library for an artifact, creature, enchantment, or land card. Put that card onto the "
            'battlefield under your control. Then that player shuffles.')
TORMENT = ("Search target player's library for X cards, where X is the number of cards in your hand, and exile them. "
           'Then that player shuffles.')
FLAMES = ('Exile cards from the top of your library until you exile a nonland card. ~ deals damage to any target equal '
          "to that card's mana value.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ch.name not in NAMES:
        return None
    text = scripts.self_text(ability.text, ch.name)
    if text == 'Epic':
        return {'kind': 'spell', 'target': None, 'effects': [{'do': 'epic_setup103'}]}
    if text not in (DOMINION, TORMENT, FLAMES):
        return None
    native = scripts.parse_effects(('Target opponent' if text == DOMINION else 'Target player') + ' draws a card.'
                                  if text != FLAMES else '~ deals 1 damage to any target.')
    assert native is not None
    if text == DOMINION:
        sel = selectors.parse('artifact, creature, enchantment, or land card')
        assert sel is not None
        body = [{'do': 'search', 'who': 'you', 'library': 'target', 'sel': sel.key(), 'to': 'battlefield',
                 'reveal': False, 'label': 'artifact, creature, enchantment, or land card'}]
    elif text == TORMENT:
        body = [{'do': 'search', 'who': 'you', 'library': 'target', 'filter': 'any', 'max': {'hand': 'you'},
                 'upto': False, 'to': 'exile', 'reveal': False}]
    else:
        sel = selectors.parse('nonland card')
        assert sel is not None
        body = [{'do': 'library_packet101', 'mode': 'exile', 'as': 'epic_packet103', 'hits': 'ref:epic_hit103',
                 'sel': sel.key(), 'need': 1}, {'do': 'epic_flames103', 'who': 'ref:epic_hit103'}]
    return {'kind': 'spell', **scripts.target_fields(native[1]), 'effects': body}


def preserve(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import CopyExcept, StackMemory, snapshot
    from app.rules import copying

    source = plan.state.cards.get(ctx.get('stack_id') or ctx.get('source_card'))
    if source is None or source.zone != 'stack':
        return True
    entry = plan.rules.stack.get(source.id)
    if entry is None:
        return True
    snap = snapshot(plan.state, source.id)
    # This is the public stack object now, not a lookup in a later hidden zone or prunable LKI.
    snap.copy_recipe = copying.with_excepts(copying.recipe_of(plan, source), [CopyExcept(remove_keywords=['epic'])])
    saved_entry = entry.model_copy(deep=True)
    saved_entry.effects = [x for x in saved_entry.effects if x['do'] not in {'epic_setup103', 'epic_snapshot103'}]
    memory = StackMemory(card=source.id, entry=saved_entry,
                         info=source.stack_info.model_dump(mode='json') if source.stack_info else {},
                         evoked=source.id in plan.rules.evoked, dashed=source.id in plan.rules.dashed)
    payment = plan.rules.payments.get(snap.object_id)
    saved = {'snapshot': snap.model_dump(mode='json'), 'memory': memory.model_dump(mode='json'),
             'card': source.model_dump(mode='json'), 'payment': payment.model_dump(mode='json') if payment else None}
    ctx['epic_saved103'] = saved
    return True


def setup(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DelayedTrigger
    from app.rules import cast_limits

    saved = ctx.get('epic_saved103')
    if saved is None:
        return True
    snap = saved['snapshot']
    cast_limits.cast_limit(plan, ctx, {'who': 'you', 'until': 'game'})
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx['controller'], source_card=snap['card'], source_object=snap['object_id'],
        name=ctx.get('name') or snap['name'] or 'Epic', when={'kind': 'step', 'step': 'upkeep', 'whose': 'you'},
        effects=[{'do': 'epic_copy103', 'saved_stack': saved}], turn=plan.state.turn.number,
        step=plan.state.turn.phase, created_step=plan.rules.step_serial, once=False))
    return True


def copy(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import copying

    saved = e['saved_stack']
    snap = saved['snapshot']
    job = copying.new_job(ctx, controller=ctx['controller'], objects=[(snap['card'], snap['object_id'], 1)],
                          retarget=True, label=ctx.get('name') or 'Epic')
    job['queue'][0]['saved_stack'] = saved
    return copying.run(plan, job)


def flames(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    hits = effects._cards(plan, ctx, e['who'])
    n = int(plan.ch(plan.state.cards[hits[0]]).mana_value) if hits else 0
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'damage', 'who': 'target', 'n': n}]
    return True


PRIMITIVES = {'epic_snapshot103': preserve, 'epic_setup103': setup, 'epic_copy103': copy, 'epic_flames103': flames}
