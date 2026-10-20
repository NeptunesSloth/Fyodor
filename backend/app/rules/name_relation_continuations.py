"""Typed name relations, public historical receipts, and exact linked continuations."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.context import Context
    from app.rules.plan import Plan

HISTORY_NAMES = 'historical spell names'


def historical_names_answer(plan: Plan, typed: str | None) -> str:
    """An explicit restoration of missing PUBLIC old-save information, not a current-card guess."""
    from app.game.errors import ActionError
    from app.rules import card_names

    names = [n.strip() for n in (typed or '').split(' // ')]
    if not 1 <= len(names) <= 2 or not all(names):
        raise ActionError('Type the public name of that previously cast spell (both names for a fused spell)')
    resolved = [card_names.canonical(plan, 'card name', n) for n in names]
    if len(resolved) == 2:
        resolve = getattr(plan.info, 'resolve', None)
        left = resolve(resolved[0]) if resolve is not None else None
        right = resolve(resolved[1]) if resolve is not None else None
        if left is None or right is None or left.get('id') != right.get('id') or left.get('layout') != 'split':
            raise ActionError('Two names must be the two faces of one fused split spell')
    return ' // '.join(dict.fromkeys(resolved))


def ensure_history(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Old saves alone may need an explicit restoration of already-public spell names."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects, history
    from app.rules.plan import decide

    players = effects._players(plan, ctx, e.get('who', 'each_player'))
    for index, note in enumerate(history.log_for(plan).casts):
        if note.player not in players or note.names is not None:
            continue
        if note.face_down:
            note.names = []
            continue
        player = note.player if note.player in plan.live() else ctx['controller']
        decide(plan, player=player, kind='choose_one',
               prompt='Restore public history from this older save: name the spell previously cast by ' + plan.name(note.player),
               options=[DecisionOption(id='__name__', label='Type the historical spell name', group=HISTORY_NAMES)],
               resume={'step': 'name_history_restore', 'ctx': ctx, 'e': e, 'index': index,
                       'object': note.object_id, 'player': note.player, 'turn': plan.state.turn.number})
        return False
    return True


def resume_history(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects, history

    frame = d.resume
    casts = history.log_for(plan).casts
    index = frame['index']
    if plan.state.turn.number != frame['turn'] or index >= len(casts) or casts[index].object_id != frame['object'] or casts[index].player != frame['player']:
        raise ActionError('That public cast-history receipt has changed')
    casts[index].names = [n.strip() for n in chosen[0].split(' // ')]
    plan.note('Restored public cast history: ' + ' // '.join(casts[index].names), actor=d.player)
    if ensure_history(plan, frame['ctx'], frame['e']):
        effects.continue_effects(plan, frame['ctx'])


PRIMITIVES = {'ensure_cast_names': ensure_history}
RESUME = {'name_history_restore': resume_history}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = ' '.join(body.split())
    text = text[:1].upper() + text[1:]
    if text == "Choose target enchantment you control that doesn't have the same name as another permanent you control. Create a token that's a copy of it, except it isn't legendary. If the token is an Aura, untap ~, then scry 2.":
        from app.rules import scripts

        parsed = scripts.parse_effects("Create a token that's a copy of target enchantment you control that doesn't have the same name as another permanent you control, except it isn't legendary.")
        assert parsed is not None
        return ([{**parsed[0][0], 'as': 'relation_token'}, {'do': 'name_relation', 'kind': 'aura_token', 'who': 'ref:relation_token'}], parsed[1], False)
    if text == 'Exile all tokens with the same name as that creature.':
        return ([{'do': 'name_relation', 'kind': 'exile_name_tokens'}], None, False)
    if text == 'Exile all tokens created with ~.':
        return ([{'do': 'name_relation', 'kind': 'exile_created_tokens'}], None, False)
    if text == 'Counter target spell if it has the same name as that card.':
        return ([{'do': 'name_relation', 'kind': 'counter_paid_exile', 'linked_cards': True}], 'spell', False)
    if text == "Exile target card other than a basic land card from an opponent's graveyard. Search that player's graveyard, hand, and library for any number of cards with the same name as that card and exile them. Then that player shuffles. For as long as you control ~, you may play one of the exiled cards, and you may spend mana as though it were mana of any color to cast it.":
        from app.rules import selectors

        target = selectors.Selector(card=True, zones=('graveyard',), zone_owner='opponent', extras=('foreign_not_basic_land',))
        return ([{'do': 'name_relation', 'kind': 'kotose'}], target.key(), False)
    if text == 'Counter target spell with the same name as a card exiled with ~.':
        return ([{'do': 'counter', 'who': 'target'}], 'spell_name_exiled_with', False)
    if text == 'You may cast a spell from your hand without paying its mana cost if it has the same name as a spell that was cast this turn.':
        return ([{'do': 'ensure_cast_names', 'who': 'each_player'}, {'do': 'name_relation', 'kind': 'twinning'}], None, False)
    if text == 'Reveal a card in your hand, then put that card onto the battlefield if it has the same name as a permanent.':
        return ([{'do': 'reveal_some', 'who': 'you', 'n': 1}, {'do': 'name_relation', 'kind': 'image'}], None, False)
    if text == 'Target player reveals their hand. That player discards all nonland cards with the same name as another card in their hand.':
        return ([{'do': 'reveal_hand', 'who': 'target'}, {'do': 'name_relation', 'kind': 'duplicate_discard'}], 'player', False)
    if text == 'Look at the top seven cards of your library. You may put one of those cards onto the battlefield if it has the same name as a permanent. Put the rest on the bottom of your library in any order.':
        from app.rules import selectors

        other = selectors.Selector().key()
        selector = selectors.Selector(card=True, zones=('library',), extras=('samename_among:' + other,))
        return ([{'do': 'look_top', 'n': 7}, {'do': 'pick_looked', 'n': 1, 'sel': selector.key(), 'optional': True, 'to': 'battlefield'},
                 {'do': 'rest_looked', 'to': 'bottom_any'}], None, False)
    if text == 'That player exiles the top four cards of their library. If two or more of those cards have the same name, repeat this process.':
        return ([{'do': 'exile_top', 'n': 4, 'player': 'event_player', 'as': 'name_exile_batch'},
                 {'do': 'name_pair_again', 'who': 'ref:name_exile_batch', 'rewind': 2}], None, False)
    return None


def execute(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import card_names, context, history, selectors

    if e['kind'] == 'kotose':
        from app.rules import effects

        targets = effects._cards(plan, ctx, 'target')
        if targets:
            target = plan.state.cards[targets[0]]
            names = card_names.names_of(plan.ch(target))
            context.bind_players(ctx, 'kotose_player', [target.owner])
            at = ctx['next']
            ctx['effects'] = [*ctx['effects'][:at], {'do': 'exile', 'who': 'target', 'as': 'kotose_original'},
                {'do': 'name_search', 'by': 'bound', 'player': 'kotose_player', 'names': names, 'all': False, 'as': 'kotose_found'},
                {'do': 'name_relation', 'kind': 'grant_kotose', 'who': 'union:ref:kotose_original+ref:kotose_found'}, *ctx['effects'][at:]]
    elif e['kind'] == 'grant_kotose':
        from app.rules import effects

        context.bind_objects(plan, ctx, 'kotose_cards', effects._cards(plan, ctx, e['who']))
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], {'do': 'grant_play', 'who': 'ref:kotose_cards', 'play': True, 'cast': True,
            'until': 'source_controlled', 'spend': 'color', 'limit': 1, 'from_exile': True}, *ctx['effects'][at:]]
    elif e['kind'] == 'helix':
        from app.rules import exiled_with

        linked = exiled_with.cards(plan, ctx)
        event = context.info(plan, ctx, 'event')
        eligible = [c for c in linked if any(other != c and event is not None and card_names.share(plan.ch(plan.state.cards[other]), event[1]) for other in linked)]
        if len(linked) == 2 and eligible:
            context.bind_objects(plan, ctx, 'helix_pool', eligible)
            at = ctx['next']
            ctx['effects'] = [*ctx['effects'][:at],
                {'do': 'return_choice', 'who': 'ref:helix_pool', 'to': 'choose', 'n': 1, 'upto': True, 'random': False, 'label': 'other imprinted card to copy', 'as': 'helix_selected'},
                {'do': 'copy_cards', 'who': 'ref:helix_selected', 'source_zone': 'exile', 'n': 1, 'as': 'helix_copy'},
                {'do': 'free_cast', 'zone': 'that', 'who': 'ref:helix_copy', 'filter': None, 'n': 1, 'optional': True}, *ctx['effects'][at:]]
    elif e['kind'] == 'counter_paid_exile':
        from app.rules import effects

        paid = plan.rules.payments.get(plan.oid(ctx['stack_id']))
        paid_names = paid.moved_exile_names if paid is not None else None
        targets = effects._cards(plan, ctx, 'target')
        if paid_names and any(card_names.has_name(plan.ch(plan.state.cards[c]), n) for c in targets for n in paid_names):
            at = ctx['next']
            ctx['effects'] = [*ctx['effects'][:at], {'do': 'counter', 'who': 'target'}, *ctx['effects'][at:]]
    elif e['kind'] == 'aura_token':
        from app.rules import effects

        if any('Aura' in plan.ch(plan.state.cards[c]).subtypes for c in effects._cards(plan, ctx, e['who'])):
            at = ctx['next']
            ctx['effects'] = [*ctx['effects'][:at], {'do': 'untap', 'who': 'self'}, {'do': 'scry', 'who': 'you', 'n': 2}, *ctx['effects'][at:]]
    elif e['kind'] == 'record_created_tokens':
        from app.rules import effects, exiled_with

        key = exiled_with.link_key(ctx)
        old = plan.rules.created_with.get(key, [])
        plan.rules.created_with[key] = list(dict.fromkeys([*old, *(plan.oid(c) for c in effects._cards(plan, ctx, e['who']))]))
    elif e['kind'] in ('exile_name_tokens', 'exile_created_tokens'):
        from app.rules import exiled_with

        if e['kind'] == 'exile_name_tokens':
            event = context.info(plan, ctx, 'event')
            ids = [c.id for c in plan.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')
                   and event is not None and card_names.share(plan.ch(c), event[1])]
        else:
            saved = plan.rules.created_with.get(exiled_with.link_key(ctx), [])
            ids = [oid.rsplit('.', 1)[0] for oid in saved if (card := plan.state.cards.get(oid.rsplit('.', 1)[0])) is not None
                   and card.zone.endswith(':battlefield') and plan.oid(card) == oid]
        context.bind_objects(plan, ctx, 'relation_tokens', ids)
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], {'do': 'exile', 'who': 'ref:relation_tokens'}, *ctx['effects'][at:]]
    elif e['kind'] == 'image':
        revealed = [c for c in ctx.get('revealed') or [] if c in plan.state.cards and plan.state.cards[c].zone == ctx['controller'] + ':hand']
        battlefield = [c for c in plan.state.cards.values() if c.zone.endswith(':battlefield')]
        matching = [cid for cid in revealed if any(card_names.share(plan.ch(plan.state.cards[cid]), plan.ch(c)) for c in battlefield)]
        context.bind_objects(plan, ctx, 'image_selected', matching)
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], {'do': 'return_card', 'who': 'ref:image_selected', 'to': 'battlefield', 'under': 'you'}, *ctx['effects'][at:]]
    elif e['kind'] == 'duplicate_discard':
        cards = [c for c in ctx.get('revealed') or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(':hand')]
        duplicates = [c for c in cards if 'Land' not in plan.ch(plan.state.cards[c]).types
                      and any(c != other and card_names.share(plan.ch(plan.state.cards[c]), plan.ch(plan.state.cards[other])) for other in cards)]
        context.bind_objects(plan, ctx, 'name_discarded', duplicates)
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], {'do': 'name_discard_group', 'who': 'ref:name_discarded'}, *ctx['effects'][at:]]
    elif e['kind'] == 'twinning':
        cast_names, unknown = history.cast_names_this_turn(plan)
        assert not unknown  # the preceding native public-history restoration handled legacy receipts
        branches = tuple(selectors.Selector(zones=('stack',), extras=('name:' + n,)).key() for n in sorted(cast_names))
        selector = selectors.Selector(either=branches) if branches else selectors.Selector(zones=('stack',), compare=(('mv', '<', 0),))
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], {'do': 'free_cast', 'zone': 'hand', 'filter': selector.key(),
                         'optional': True, 'n': 1}, *ctx['effects'][at:]]
    return True


PRIMITIVES['name_relation'] = execute


def discard_group(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects, grouped_discard

    return grouped_discard.begin_cards(plan, ctx, effects._cards(plan, ctx, e['who']))


PRIMITIVES['name_discard_group'] = discard_group


def definition(text: str) -> dict[str, Any] | None:
    if text == 'Whenever a player casts a card, if it has the same name as one of the cards exiled with ~, you may copy the other. If you do, you may cast the copy without paying its mana cost.':
        from app.rules import events

        cond = events.parse_condition('a player casts a spell')
        assert cond is not None
        cond = {**cond, 'card_only': True}
        test = {'event_linked_name': True}
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'if': test, 'optional': False, 'target': None,
                'effects': [{'do': 'only_if', 'cond': test, 'skip': 1}, {'do': 'name_relation', 'kind': 'helix', 'linked_cards': True}]}
    if text == "Whenever a nontoken creature enters, its controller creates a token that's a copy of that creature.":
        from app.rules import events

        cond = events.parse_condition('a nontoken creature enters')
        assert cond is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False, 'target': None,
                'effects': [{'do': 'token_copy', 'n': 1, 'who': 'event', 'their': True, 'as': 'relation_token'},
                            {'do': 'name_relation', 'kind': 'record_created_tokens', 'who': 'ref:relation_token'}]}
    if text != 'Whenever you cast an instant or sorcery spell from your hand, you may cast target card with the same name as that spell from your graveyard.':
        return None
    from app.rules import events, selectors

    cond = events.parse_condition('you cast an instant or sorcery spell from your hand')
    if cond is None:
        return None
    selector = selectors.Selector(card=True, zones=('graveyard',), zone_owner='you')
    return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False,
            'target': {'what': selector.key(), 'name_event': True},
            'effects': [{'do': 'free_cast', 'zone': 'target', 'optional': True, 'n': 1, 'filter': None, 'paid': True}]}


def bind_trigger_reference(plan: Plan, trigger: Any) -> None:
    """Bind identity, not a frozen name: target checks read this exact event object/LKI."""
    import json

    from app.rules import selectors

    target = trigger.ability.get('target')
    if not target or not target.get('name_event'):
        return
    refs = trigger.event.objects if trigger.event is not None else []
    base = selectors.from_key(target['what'])
    reference = refs[0].model_dump(mode='json') if refs else None
    extra = 'samename_object:' + json.dumps(reference, sort_keys=True, separators=(',', ':'))
    trigger.ability = {**trigger.ability, 'target': {'what': selectors.replace(base, extras=(*base.extras, extra)).key()}}


def pair_again(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import card_names, effects
    from app.rules.plan import decide

    found = [c for c in effects._cards(plan, ctx, e['who']) if plan.state.cards[c].zone.endswith(':exile') and not plan.state.cards[c].is_token]
    pair = any(card_names.share(plan.ch(plan.state.cards[c]), plan.ch(plan.state.cards[other]))
               for index, c in enumerate(found) for other in found[index + 1:])
    if not pair:
        ctx.pop('name_repeat_budget', None)
        return True
    ctx['next'] -= e['rewind']
    count = int(ctx.get('name_repeat_budget', 0)) + 1
    ctx['name_repeat_budget'] = count
    if count >= 32:
        ctx['name_repeat_budget'] = 0
        decide(plan, player=ctx['controller'], kind='choose_one', prompt='Continue processing the mandatory repeated exile',
               options=[DecisionOption(id='continue', label='Continue processing')],
               resume={'step': 'name_pair_continue', 'ctx': ctx})
        return False
    return True


def resume_pair(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


PRIMITIVES['name_pair_again'] = pair_again
RESUME['name_pair_continue'] = resume_pair


def event_linked_name(plan: Plan, ctx: Context) -> bool:
    from app.rules import card_names, context, exiled_with

    event = context.info(plan, ctx, 'event')
    return event is not None and any(card_names.share(event[1], plan.ch(plan.state.cards[c])) for c in exiled_with.cards(plan, ctx))
