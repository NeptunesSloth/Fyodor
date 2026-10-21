"""Exact variable-life instructions using native costs, targets and movement receipts."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def queue(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, values

    mode = e['mode']
    if mode == 'restoration':
        n = values.evaluate(plan, ctx, {'mana_value': 'target'})
        payment = plan.rules.payments.get(ctx.get('source_object') or '')
        return queue(ctx, [
            {'do': 'return_card', 'who': 'target', 'to': 'battlefield', 'tapped': False, 'under': 'you'},
            {'do': 'gain_life' if payment and payment.kicked else 'lose_life', 'who': 'you', 'n': n},
        ])
    if mode == 'vortex':
        n = max(0, values.evaluate(plan, ctx, {'toughness': 'target'}))
        return queue(ctx, [
            {'do': 'optional_payment', 'who': 'target', 'cost': f'Pay {n} life', 'bind': 'life41_vortex'},
            {'do': 'only_if', 'cond': {'not': {'succeeded': 'life41_vortex'}}, 'skip': 1},
            {'do': 'destroy', 'who': 'target'},
            {'do': 'no_regen'},
        ])
    if mode == 'orzhov_destroy':
        n = max(0, values.evaluate(plan, ctx, {'toughness': 'target'}))
        return queue(ctx, [
            {'do': 'destroy', 'who': 'target'},
            {'do': 'lose_life', 'who': 'you', 'n': n},
        ])
    if mode == 'kaya_first':
        return queue(ctx, [
            {'do': 'exile', 'who': 'target:0', 'as': 'life41_kaya_exiled'},
            {'do': 'life_card_outcome41', 'mode': 'kaya_first_finish'},
        ])
    if mode == 'kaya_first_finish':
        from app.rules import selectors, this_way

        creatures = this_way.count(plan, ctx, {'this_way': 'exiled',
            'of': selectors.Selector(card=True, types=('Creature',), zones=()).key(), 'ref_count': 'life41_kaya_exiled'})
        return queue(ctx, [{'do': 'gain_life', 'who': 'you', 'n': 2}]) if creatures else True
    if mode == 'kaya_last':
        players = effects._players(plan, ctx, 'target')
        if not players:
            return True
        n = sum(c.owner == players[0] and c.zone.endswith(':exile') and not c.is_token for c in plan.state.cards.values())
        return queue(ctx, [
            {'do': 'damage', 'who': 'target', 'n': n},
            {'do': 'gain_life', 'who': 'you', 'n': n},
        ])
    if mode == 'archfiend':
        from app.rules import scripts

        native = scripts.parse_effects('Each opponent sacrifices a creature with the greatest power among creatures they control.')
        assert native is not None
        return queue(ctx, [{**native[0][0], 'as': 'life41_archfiend_sacrificed'},
                           {'do': 'life_card_outcome41', 'mode': 'archfiend_finish'}])
    if mode == 'archfiend_finish':
        from app.rules import context, this_way

        powers = []
        for i, (_, old) in enumerate(this_way._matched(plan, ctx, {
            'this_way': 'sacrificed', 'of': None, 'ref_count': 'life41_archfiend_sacrificed'})):
            key = f'life41_archfiend_{i}'
            context.refs(ctx)[key] = {'kind': 'objects', 'objects': [old]}
            powers.append(values.evaluate(plan, ctx, {'power': 'ref:' + key}))
        return queue(ctx, [{'do': 'gain_life', 'who': 'you', 'n': max(powers, default=0)}])
    if mode == 'elixir':
        from app.rules import selectors

        sel = selectors.Selector(card=True, not_types=('Land',), zone_owner='you', zones=('graveyard',)).key()
        return queue(ctx, [
            {'do': 'shuffle_library', 'who': 'you', 'zones': ['graveyard'], 'sel': sel, 'bind': 'life41_elixir_shuffled'},
            {'do': 'life_card_outcome41', 'mode': 'elixir_finish'},
        ])
    if mode == 'elixir_finish':
        n = values.evaluate(plan, ctx, {'ref_amount': 'life41_elixir_shuffled'})
        return queue(ctx, [{'do': 'gain_life', 'who': 'you', 'n': n}])
    if mode == 'orzhov_bounce':
        from app.rules import context

        targets = effects._cards(plan, ctx, 'target')
        if not targets:
            return True
        host = targets[0]
        auras = [c.id for c in plan.state.cards.values()
                 if c.zone.endswith(':battlefield') and c.controller == ctx['controller']
                 and c.attached_to == host and 'Aura' in plan.ch(c).subtypes]
        context.bind_objects(plan, ctx, 'life41_orzhov_return', [host, *auras])
        return queue(ctx, [{'do': 'bounce', 'who': 'ref:life41_orzhov_return'}])
    if mode == 'pact_draw':
        from app.rules import context, history

        context.bind_objects(plan, ctx, 'life41_pact_host', effects._cards(plan, ctx, 'event'))
        before = list(history.log_for(plan).drawn.get(ctx['controller'], []))
        return queue(ctx, [{'do': 'draw', 'who': 'you', 'n': 1},
                           {'do': 'life_card_outcome41', 'mode': 'pact_draw_finish', 'before': before}])
    if mode == 'pact_draw_finish':
        from app.rules import context, history

        log = history.log_for(plan)
        me = ctx['controller']
        excluded = set(e['before']) | set(log.drawn_replaced.get(me, [])) | set(log.drawn_counted.get(me, []))
        ids = [oid.rsplit('.', 1)[0] for oid in log.drawn.get(me, []) if oid not in excluded
               and (card := plan.state.cards.get(oid.rsplit('.', 1)[0])) is not None
               and plan.oid(card) == oid and card.zone == me + ':hand']
        if not ids:
            return True
        plan.do({'type': 'reveal', 'card_ids': ids}, actor=me)
        n = sum(int(plan.ch(plan.state.cards[c]).mana_value) for c in ids)
        context.bind_objects(plan, ctx, 'life41_pact_drawn', ids)
        return queue(ctx, [
            {'do': 'pump', 'who': 'ref:life41_pact_host', 'p': n, 't': n},
            {'do': 'lose_life', 'who': 'you', 'n': n},
            {'do': 'hide_revealed', 'refs': 'life41_pact_drawn', 'zone': 'hand'},
        ])
    if mode == 'niv_pairs':
        pairs = {tuple(sorted(plan.ch(c).colors)) for c in plan.state.cards.values()
                 if c.zone.endswith(':battlefield') and c.controller == ctx['controller']
                 and len(plan.ch(c).colors) == 2}
        n = len(pairs)
        return queue(ctx, [
            {'do': 'damage', 'who': 'target:0', 'n': n},
            {'do': 'draw', 'who': 'target:1', 'n': n},
            {'do': 'gain_life', 'who': 'you', 'n': n},
        ])
    raise ValueError(f'Unknown life outcome: {mode}')


BODIES = {
    'Shuffle all nonland cards from your graveyard into your library. You gain life equal to the number of cards shuffled into your library this way':
        ('elixir', 'Shuffle your library.'),

    "Return target creature card from your graveyard to the battlefield. If this spell was kicked, you gain life equal to that card's mana value. Otherwise, you lose that much life":
        ('restoration', 'Return target creature card from your graveyard to the battlefield.'),

    'Exile up to two target cards from a single graveyard. You gain 2 life if at least one creature card was exiled this way':
        ('kaya_first', 'Exile up to two target cards from a single graveyard.'),

    "Return target creature you control and all Auras you control attached to it to their owner's hand":
        ('orzhov_bounce', 'Return target creature you control to its owner\'s hand.'),

    "Return target creature card from your graveyard to the battlefield. If this spell was kicked, you gain life equal to that card's mana value. Otherwise, you lose that much life. Exile ~":
        ('restoration', 'Return target creature card from your graveyard to the battlefield.'),
    "Destroy target creature unless its controller pays life equal to its toughness. A creature destroyed this way can't be regenerated":
        ('vortex', 'Destroy target creature.'),
    'Destroy target creature and you lose life equal to its toughness':
        ('orzhov_destroy', 'Destroy target creature.'),
    '~ deals damage to target player equal to the number of cards that player owns in exile and you gain that much life':
        ('kaya_last', '~ deals 1 damage to target player.'),
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    item = BODIES.get(body.strip().rstrip('.'))
    if item is None:
        return None
    native = scripts.parse_effects(item[1])
    return ([{'do': 'life_card_outcome41', 'mode': item[0]}], native[1], False) if native else None


PRIMITIVES = {'life_card_outcome41': run}



def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == "As long as ~ is attached to a creature, you don't lose the game for having 0 or less life.":
        return {'kind': 'static', 'static': 'game_result', 'you': None, 'opponents': None, 'zero_life_when_attached': True, 'effects': []}
    prototypes = {
        'When ~ enters, each opponent sacrifices a creature with the greatest power among creatures they control. You gain life equal to the greatest power among creatures sacrificed this way.':
            ('archfiend', 'When ~ enters, each opponent sacrifices a creature with the greatest power among creatures they control.'),

        "Whenever equipped creature attacks, draw a card and reveal it. The creature gets +X/+X until end of turn and you lose X life, where X is that card's mana value.":
            ('pact_draw', 'Whenever equipped creature attacks, draw a card.'),
        'Whenever ~ deals combat damage to a player, it deals X damage to any target, target player draws X cards, and you gain X life, where X is the number of different color pairs among permanents you control that are exactly two colors.':
            ('niv_pairs', 'Whenever ~ deals combat damage to a player, it deals 1 damage to any target and target player draws a card.'),
    }
    item = prototypes.get(text)
    if item is None:
        return None
    native = scripts.define(replace(ability, text=item[1]), ch)
    return {**native, 'effects': [{'do': 'life_card_outcome41', 'mode': item[0]}]} if native else None
