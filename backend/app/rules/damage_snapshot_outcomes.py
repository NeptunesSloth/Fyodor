"""Printed damage sequences with values captured at their specified instruction."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODIES = {
    'Exile target creature card from a graveyard. That card deals damage equal to its power to ~': ('exorcist', 'gravecreature'),
    'Create an X/X black Nightmare Horror creature token, where X is half your life total, rounded up. It deals X damage to you': ('chainer', None),
    '~ deals X damage to target creature, where X is 2 plus the number of cards in your graveyard that are instant cards, sorcery cards, and/or have an Adventure': ('frantic', 'creature'),
    '~ deals X damage to target creature or planeswalker and you gain X life. X is the number of creatures you control': ('lantern', 'creaturepw'),
    "Choose target creature you control. Turn it face up if it's face down. Then it deals damage equal to its power to each other creature": ('show', 'owncreature'),
    "Target creature you control gets +1/+1 until end of turn. Put a +1/+1 counter on it instead if it's a Mount. Then it deals damage equal to its power to target creature you don't control": ('saddle', 'pair'),
    'Destroy all artifacts, then ~ deals damage to each creature equal to the number of artifacts that were put into graveyards from the battlefield this turn': ('structural', None),
    'Target player loses all poison counters. ~ deals that much damage to that player': ('leeches', 'player'),
    'Choose any number of target creature and/or planeswalker cards in graveyards. ~ deals damage to you equal to the total mana value of those cards. Put them onto the battlefield under your control': ('command', 'gravecards'),
    '~ deals damage to target creature equal to the number of nonbasic lands that creature\'s controller controls': ('weight', 'creature'),
    'Target player draws two cards, then ~ deals damage to that player equal to the number of cards they\'ve drawn this turn': ('vortex', 'player'),
    'For each player, ~ deals damage to that player and each creature that player controls equal to the number of creatures they control': ('incite', None),
    'Damage can\'t be prevented this turn. ~ deals X damage to target creature and 1 damage to each other creature with the same controller': ('fear', 'creature'),
    'Choose target creature you control and target creature an opponent controls. Each of those creatures deals damage equal to its toughness to the other': ('grim', 'pair'),
    'Destroy target land, then ~ deals damage to that land\'s controller equal to the number of land cards in that player\'s graveyard': ('roiling', 'land'),
    'Destroy target Wall. It can\'t be regenerated. ~ deals damage equal to that Wall\'s mana value to the Wall\'s controller': ('word', 'wall'),
    'Destroy target artifact. That artifact deals damage equal to its mana value to ~': ('tinkerer', 'artifact'),
    'Destroy target creature. If a white creature dies this way, ~ deals damage to that creature\'s controller equal to the creature\'s power': ('cinder', 'creature'),
    'Destroy target creature with mana value X. If that creature dies this way, ~ deals damage equal to the creature\'s power to the creature\'s controller': ('purge', 'xcreature'),
    '~ deals damage to target spell\'s controller equal to that spell\'s mana value': ('feedback', 'spell'),
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:] if not text.startswith('~') else text
    item = BODIES.get(text)
    if item is None:
        return None
    mode, target = item
    sel = {'creature': selectors.Selector(types=('Creature',)).key(),
           'artifact': selectors.Selector(types=('Artifact',)).key(),
           'land': selectors.Selector(types=('Land',)).key(),
           'wall': selectors.Selector(subtypes=('Wall',)).key(),
           'xcreature': selectors.Selector(types=('Creature',), compare=(('mv', '==', -1),)).key(),
           'player': 'player', 'spell': 'spell',
           'owncreature': selectors.Selector(types=('Creature',), controller='you').key(),
           'creaturepw': selectors.Selector(types=('Creature', 'Planeswalker')).key()}
    targets: Any = sel.get(target or '')
    if target == 'pair':
        targets = [{'what': selectors.Selector(types=('Creature',), controller='you').key()},
                   {'what': selectors.Selector(types=('Creature',), controller='opponent').key()}]
    if target == 'gravecreature':
        targets = selectors.Selector(zones=('graveyard',), card=True, types=('Creature',)).key()
    if target == 'gravecards':
        targets = [{'what': selectors.Selector(zones=('graveyard',), card=True, types=('Creature', 'Planeswalker')).key(), 'min': 0, 'max': 250}]
    return [{'do': 'damage_snapshot', 'mode': mode}], targets, False


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


def batch(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    for step in steps[:-1]:
        step['with_next'] = True
    return insert(ctx, steps)


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, stack_interaction, values
    mode = e['mode']
    targets = effects._cards(plan, ctx, 'target')
    creatures = [c for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and 'Creature' in plan.ch(c).types]
    if mode == 'incite':
        steps = []
        for pid in plan.live():
            controlled = [c.id for c in creatures if c.controller == pid]
            context.bind_objects(plan, ctx, 'damage_incite_' + pid, controlled)
            steps.extend([{'do': 'damage', 'who': 'player:' + pid, 'n': len(controlled)},
                          {'do': 'damage', 'who': 'ref:damage_incite_' + pid, 'n': len(controlled)}])
        return batch(ctx, steps)
    if mode == 'chainer':
        n = max(0, (plan.state.players[ctx['controller']].life + 1) // 2)
        return insert(ctx, [{'do': 'create_token', 'who': 'you', 'n': 1, 'as': 'damage_nightmares',
            'token': {'name': 'Nightmare Horror', 'type_line': 'Token Creature — Nightmare Horror', 'colors': ['B'], 'power': str(n), 'toughness': str(n)}},
            {'do': 'damage_snapshot_finish', 'mode': mode, 'amount': n}])
    if mode == 'exorcist':
        context.bind_objects(plan, ctx, 'damage_exorcist_original', targets)
        return insert(ctx, [{'do': 'exile', 'who': 'target', 'as': 'damage_exiled'}, {'do': 'damage_snapshot_finish', 'mode': mode}])
    if mode == 'command':
        context.bind_objects(plan, ctx, 'damage_command', targets)
        n = sum(stack_interaction.mana_value(plan.state.cards[c], plan.ch(plan.state.cards[c])) for c in targets)
        return insert(ctx, [{'do': 'damage', 'who': 'you', 'n': n}, {'do': 'return_card', 'who': 'ref:damage_command', 'to': 'battlefield', 'under': 'you', 'tapped': False}])
    if mode == 'structural':
        return insert(ctx, [{'do': 'destroy_all', 'who': 'all', 'types': ['Artifact']}, {'do': 'damage_snapshot_finish', 'mode': mode}])
    if mode == 'leeches':
        steps = []
        for pid in effects._players(plan, ctx, 'target'):
            n = plan.state.players[pid].resources.get('poison', 0)
            if n:
                plan.do({'type': 'resource', 'player': pid, 'key': 'poison', 'delta': -n}, actor=ctx['controller'])
            steps.append({'do': 'damage', 'who': 'player:' + pid, 'n': n})
        return insert(ctx, steps)
    if mode == 'lantern':
        n = sum(c.controller == ctx['controller'] for c in creatures)
        return insert(ctx, [{'do': 'damage', 'who': 'target', 'n': n}, {'do': 'gain_life', 'who': 'you', 'n': n}])
    if mode == 'frantic':
        adv = selectors.Selector(zones=('graveyard',), card=True, extras=('has_adventure',))
        adventure_cards = set(selectors.candidates(plan, adv, ctx['controller'], ctx.get('source_card')))
        n = 2 + sum(c.zone == ctx['controller'] + ':graveyard' and (bool(plan.ch(c).types & {'Instant', 'Sorcery'}) or c.id in adventure_cards) for c in plan.state.cards.values())
        return insert(ctx, [{'do': 'damage', 'who': 'target', 'n': n}])
    if mode == 'show':
        return insert(ctx, [{'do': 'turn_face_up', 'who': 'target'}, {'do': 'damage_snapshot_finish', 'mode': mode}])
    if mode == 'saddle':
        first = effects._cards(plan, ctx, 'target:0')
        if not first:
            return True
        step = {'do': 'add_counters', 'who': 'target:0', 'kind': '+1/+1', 'n': 1} if 'Mount' in plan.ch(plan.state.cards[first[0]]).subtypes else {'do': 'pump', 'who': 'target:0', 'p': 1, 't': 1}
        return insert(ctx, [step, {'do': 'damage', 'src': 'target:0', 'who': 'target:1', 'n': {'power': 'target:0'}}])
    if mode == 'vortex':
        return insert(ctx, [{'do': 'draw', 'who': 'target', 'n': 2}, {'do': 'damage_snapshot_finish', 'mode': mode}])
    if mode == 'feedback':
        context.bind_objects(plan, ctx, 'damage_original', targets)
        return insert(ctx, [{'do': 'damage', 'who': 'ref:damage_original.controller', 'n': {'mana_value': 'ref:damage_original'}}])
    if mode == 'grim':
        left = effects._cards(plan, ctx, 'target:0')
        right = effects._cards(plan, ctx, 'target:1')
        if not left or not right:
            return True
        return batch(ctx, [{'do': 'damage', 'src': 'target:0', 'who': 'target:1', 'n': {'toughness': 'target:0'}},
                           {'do': 'damage', 'src': 'target:1', 'who': 'target:0', 'n': {'toughness': 'target:1'}}])
    if not targets:
        return True
    card = plan.state.cards[targets[0]]
    context.bind_objects(plan, ctx, 'damage_original', [card.id])
    if mode == 'weight':
        n = sum(c.zone.endswith(':battlefield') and c.controller == card.controller and 'Land' in plan.ch(c).types and 'Basic' not in plan.ch(c).supertypes for c in plan.state.cards.values())
        return insert(ctx, [{'do': 'damage', 'who': 'target', 'n': n}])
    if mode == 'fear':
        context.bind_objects(plan, ctx, 'damage_others', [c.id for c in creatures if c.controller == card.controller and c.id != card.id])
        return insert(ctx, [{'do': 'unpreventable_turn'}, {'do': 'damage', 'who': 'target', 'n': {'x': 1}, 'with_next': True}, {'do': 'damage', 'who': 'ref:damage_others', 'n': 1}])
    finish: dict[str, Any] = {'do': 'damage_snapshot_finish', 'mode': mode, 'player': card.controller,
        'amount': values.evaluate(plan, ctx, {'power' if mode in ('cinder', 'purge') else 'mana_value': 'ref:damage_original'}),
        'white': 'W' in plan.ch(card).colors}
    return insert(ctx, [{'do': 'destroy', 'who': 'target', 'as': 'damage_destroyed'}, *([{'do': 'no_regen'}] if mode == 'word' else []), finish])


def finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, history, this_way
    mode = e['mode']
    if mode == 'chainer':
        steps = []
        for i, cid in enumerate(context.objects(plan, ctx, 'damage_nightmares')):
            name = 'damage_nightmare_' + str(i)
            context.bind_objects(plan, ctx, name, [cid])
            steps.append({'do': 'damage', 'src': 'ref:' + name, 'who': 'you', 'n': e['amount']})
        return batch(ctx, steps)
    if mode == 'exorcist':
        ids = context.objects(plan, ctx, 'damage_exiled') or context.objects(plan, ctx, 'damage_exorcist_original')
        context.bind_objects(plan, ctx, 'damage_exorcist_arrival', ids)
        return insert(ctx, [{'do': 'damage', 'src': 'ref:damage_exorcist_arrival', 'public_card_source': True, 'who': 'self', 'n': {'power': 'ref:damage_exorcist_arrival'}}])
    if mode == 'structural':
        n = sum(d.to == 'graveyard' and 'Artifact' in (d.types or []) for d in history.log_for(plan).left)
        return insert(ctx, [{'do': 'damage', 'who': selectors.Selector(types=('Creature',)).key(), 'n': n}])
    if mode == 'show':
        targets = effects._cards(plan, ctx, 'target')
        if not targets:
            return True
        context.bind_objects(plan, ctx, 'damage_show_others', [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and c.id != targets[0] and 'Creature' in plan.ch(c).types])
        return insert(ctx, [{'do': 'damage', 'src': 'target', 'who': 'ref:damage_show_others', 'n': {'power': 'target'}}])
    if mode == 'vortex':
        return insert(ctx, [{'do': 'damage', 'who': 'player:' + pid, 'n': history.log_for(plan).drew.get(pid, 0)} for pid in effects._players(plan, ctx, 'target')])
    if mode in ('cinder', 'purge') and (not this_way.count(plan, ctx, {'this_way': 'died', 'of': None, 'ref_count': 'damage_destroyed'}) or (mode == 'cinder' and not e['white'])):
        return True
    if mode == 'tinkerer':
        return insert(ctx, [{'do': 'damage', 'src': 'ref:damage_original', 'who': 'self', 'n': e['amount']}])
    n = e['amount']
    if mode == 'roiling':
        n = sum(c.zone == e['player'] + ':graveyard' and 'Land' in plan.ch(c).types for c in plan.state.cards.values())
    return insert(ctx, [{'do': 'damage', 'who': 'player:' + e['player'], 'n': n}])

PRIMITIVES = {'damage_snapshot': run, 'damage_snapshot_finish': finish}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts
    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != "When enchanted creature dies, ~ deals damage equal to that creature's toughness to the creature's controller.":
        return None
    native = scripts.define(replace(ability, text='When enchanted creature dies, you gain 1 life.'), ch)
    return {**native, 'effects': [{'do': 'damage', 'who': 'ref:event.controller', 'n': {'toughness': 'ref:event'}}]} if native else None
