"""Native life sequences with fixed object packets and ordinary event receipts."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def queue(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, scripts, selectors, values

    mode = e['mode']
    if mode == 'blim':
        counts={p:sum(c.controller==p and c.owner!=p and c.zone.endswith(':battlefield') for c in plan.state.cards.values()) for p in plan.live()}
        return queue(ctx,[{'do':'lose_life','who':'each_player','n':0,'counts':counts},
                          {'do':'discard','who':'each_player','n':0,'counts':counts}])
    if mode == 'sengir':
        amount=(ctx.get('event') or {}).get('turn_start_life')
        if amount is None:
            from app.game.rules_state import DecisionOption
            from app.rules.plan import decide

            decide(plan,player=ctx['controller'],kind='manual_resolution',
                   prompt="This older save has no record of that player's life at turn start. Resolve this life gain by hand, then press Done.",
                   options=[DecisionOption(id='done',label='Done')],resume={'step':'life_sequence_unknown42','ctx':ctx})
            return False
        return queue(ctx,[{'do':'gain_life','who':'you','n':max(0,int(amount))}])
    if mode == 'curse_vengeance':
        n=values.evaluate(plan,ctx,{'counters':'spite','on':'self'})
        return queue(ctx,[{'do':'gain_life','who':'you','n':n},{'do':'draw','who':'you','n':n}])
    if mode == 'expel':
        ids = effects._cards(plan,ctx,e['who'])
        if not ids:
            return True
        victim = plan.state.cards[ids[0]]
        controller = victim.controller
        n = int(plan.ch(victim).mana_value)
        context.bind_objects(plan,ctx,'life42_expel',ids)
        return queue(ctx,[{'do':'exile','who':'ref:life42_expel'},
                          {'do':'gain_life','who':'player:'+controller,'n':n}])
    if mode == 'tenacity':
        pool = selectors.candidates(plan, selectors.Selector(types=('Creature',), controller='you'), ctx['controller'])
        context.bind_objects(plan, ctx, 'life42_tenacity', pool)
        return queue(ctx, [
            {'do': 'pump', 'who': 'ref:life42_tenacity', 'p': 1, 't': 1},
            {'do': 'grant', 'who': 'ref:life42_tenacity', 'keywords': ['lifelink']},
            {'do': 'untap', 'who': 'ref:life42_tenacity'},
        ])
    if mode == 'floorboards':
        payment = plan.rules.payments.get(ctx.get('source_object') or '')
        n = int(ctx.get('x') or 0) if payment and payment.alternative == 'madness' else 3
        native = scripts.parse_effects('Create three tapped 2/2 black Zombie creature tokens.')
        assert native is not None
        return queue(ctx, [{**native[0][0], 'n': n}, {'do': 'gain_life', 'who': 'you', 'n': n}])
    if mode == 'courageous':
        native = scripts.parse_effects('Up to one target creature you control gains protection from each of your opponents until end of turn. Draw a card.')
        assert native is not None
        return queue(ctx, [*native[0], {'do': 'life_receipt_sequence42', 'mode': 'courageous_check'}])
    if mode == 'courageous_check':
        steps: list[dict[str, Any]] = []
        # Fateful hour is tested once as this instruction resolves; later life
        # gain does not undo the independent effects it creates.
        if plan.state.players[ctx['controller']].life <= 5:
            steps += [
                {'do': 'life_lock', 'who': 'you', 'lose_only': True, 'until': 'turn'},
                {'do': 'cant_result', 'who': 'you', 'what': 'lose'},
                {'do': 'cant_result', 'who': 'each_opponent', 'what': 'win'},
            ]
        return queue(ctx, steps)
    if mode == 'talus':
        grant = scripts.parse_effects('Allies you control gain lifelink until end of turn.')
        assert grant is not None
        return queue(ctx, [
            {'do': 'optional_payment', 'who': 'you', 'cost': '', 'bind': 'talus_lifelink', 'ask': 'have Allies you control gain lifelink'},
            {'do': 'only_if', 'cond': {'succeeded': 'talus_lifelink'}, 'skip': len(grant[0])},
            *grant[0],
            {'do': 'optional_payment', 'who': 'you', 'cost': '', 'bind': 'talus_counter', 'ask': 'put a +1/+1 counter on this creature'},
            {'do': 'only_if', 'cond': {'succeeded': 'talus_counter'}, 'skip': 1},
            {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1},
        ])
    raise ValueError(f'Unknown staged life sequence: {mode}')


BODIES = {
    'Creatures you control get +1/+1 and gain lifelink until end of turn. Untap those creatures':
        ('tenacity', 'Creatures you control get +1/+1 until end of turn.'),
    "Create three tapped 2/2 black Zombie creature tokens and you gain 3 life. If this spell's madness cost was paid, instead create X of those tokens and you gain X life":
        ('floorboards', 'Create three tapped 2/2 black Zombie creature tokens.'),
}

COURAGEOUS = 'Up to one target creature you control gains protection from each of your opponents until end of turn. Draw a card. '


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, watches

    text = body.strip().rstrip('.')
    if text == 'Target creature gains trample until end of turn. Whenever that creature deals combat damage this turn, if this spell was kicked, you gain life equal to that damage':
        # Kicked is an immutable fact of the creating spell, not of the
        # watched creature or a later source incarnation.
        return scripts.parse_effects('Target creature gains trample until end of turn. If this spell was kicked, whenever that creature deals combat damage this turn, you gain that much life.')
    if text == 'Choose target creature with mana value 3 or less. If this spell was kicked, instead choose target creature. Exile the chosen creature, then its controller gains life equal to its mana value':
        native_expel = scripts.parse_effects('Exile target creature with mana value 3 or less. If this spell was kicked, exile target creature instead.')
        assert native_expel is not None
        steps = [{**e,'do':'life_receipt_sequence42','mode':'expel'} if e['do']=='exile' else e for e in native_expel[0]]
        return steps,native_expel[1],False
    if text == 'Until end of turn, whenever a player gains life, that player loses 2 life for each 1 life they gained':
        native_watch = watches.parse('a player gains life', 'that player loses twice that much life')
        assert native_watch is not None
        return (*native_watch, False)
    if text.startswith(COURAGEOUS) and text[len(COURAGEOUS):] == "If you have 5 or less life, you can't lose life this turn, you can't lose the game this turn, and your opponents can't win the game this turn":
        native = scripts.parse_effects(COURAGEOUS.strip())
        assert native is not None
        return ([{'do': 'life_receipt_sequence42', 'mode': 'courageous'}], native[1], False)
    item = BODIES.get(text)
    if item is None:
        return None
    native = scripts.parse_effects(item[1])
    return ([{'do': 'life_receipt_sequence42', 'mode': item[0]}], native[1], False) if native else None


PRIMITIVES = {'life_receipt_sequence42': run}


def resume_unknown(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen!=['done']:
        raise ActionError('Press Done after resolving the unknown life gain manually')
    effects.continue_effects(plan,decision.resume['ctx'])


RESUME={'life_sequence_unknown42':resume_unknown}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text,ch.name)
    if text == "Whenever ~ deals combat damage to a player, that player gains control of target permanent you control. Then each player loses life and discards cards equal to the number of permanents they control but don't own.":
        base=scripts.define(replace(ability,text='Whenever ~ deals combat damage to a player, that player gains control of target permanent you control.'),ch)
        return {**base,'effects':[*base['effects'],{'do':'life_receipt_sequence42','mode':'blim'}]} if base else None
    if text == "Whenever another player loses the game, you gain life equal to that player's life total as the turn began.":
        return {'kind':'triggered','trigger':'event','cond':{'event':'lose_game','subject':'player','player':'other'},
                'effects':[{'do':'life_receipt_sequence42','mode':'sengir'}]}
    if text == 'Whenever you gain life, choose up to that many target creatures you control. Put a +1/+1 counter on each of them.':
        from app.rules import selectors

        base=scripts.define(replace(ability,text='Whenever you gain life, put a +1/+1 counter on up to one target creature you control.'),ch)
        if base is None:
            return None
        base=dict(base)
        base.pop('target',None)
        return {**base,'targets':[{'what':selectors.Selector(types=('Creature',),controller='you').key(),
                                  'min':0,'x_count':'upto','x_value':{'event_amount':1}}]}
    if text == "Players can't draw cards or gain life.":
        from app.rules import cant_gain, prohibitions

        draw=prohibitions.static_definition("Players can't draw cards.")
        gain=cant_gain.static_definition("Players can't gain life.")
        assert draw is not None and gain is not None
        return {**draw,'also':[gain]}
    if text == 'When enchanted player loses the game, you gain X life and draw X cards, where X is the number of spite counters on ~.':
        return {'kind':'triggered','trigger':'event',
                'cond':{'event':'lose_game','subject':'player','player':'enchanted'},
                'effects':[{'do':'life_receipt_sequence42','mode':'curse_vengeance'}]}
    if text == 'Whenever you lose life, sacrifice a permanent for each 1 life you lost.':
        return scripts.define(replace(ability,text='Whenever you lose life, sacrifice that many permanents.'),ch)
    if text == 'Whenever ~ or another Ally you control enters, you may have Allies you control gain lifelink until end of turn, and you may put a +1/+1 counter on ~.':
        base = scripts.define(replace(ability,text='Whenever this creature or another Ally you control enters, you gain 1 life.'),ch)
        return {**base,'effects':[{'do':'life_receipt_sequence42','mode':'talus'}]} if base else None
    return None
