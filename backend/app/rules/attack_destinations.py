"""Typed destinations for attack requirements; the declaration solver remains authoritative."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.effects import Context
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    body = body.strip()

    m = re.fullmatch(r'For each opponent, create (?P<n>one|two|three|\d+) (?P<token>.+? creature tokens?) with (?P<keywords>[a-z ,]+) that attack that opponent this turn if able\. They gain haste until end of turn\.',body,re.I)
    if m:
        from app.rules import scripts

        created = scripts.parse_effects(f"Create {m['n']} {m['token']} with {m['keywords']}.")
        if created is not None and created[1] is None and not created[2] and len(created[0]) == 1 and created[0][0].get('do') == 'create_token':
            return ([{'do':'attack_tokens_each','create':created[0][0]}],None,False)
    if body.lower() == 'target creature attacks target opponent this turn if able.':
        creature = language.target_group('target creature')
        player = language.target_group('target opponent')
        if creature is not None and player is not None:
            return ([{'do':'restrict','who':'target:0','player':'target:1',
                      'rules':['attack_player:@that']}], [creature,player], False)
    if body.lower() == "target creature an opponent controls attacks during its controller's next combat phase if able.":
        group = language.target_group('target creature an opponent controls')
        if group is not None:
            return ([{'do':'attack_window','who':'target','window':'next_combat'}],[group],False)
    if body.lower() == "during target opponent's next turn, creatures that player controls attack ~ if able.":
        group = language.target_group('target opponent')
        if group is not None:
            return ([{'do':'attack_window','player':'target','window':'next_turn'}],[group],False)
    m = re.fullmatch(r'Until the end of your next turn, target creature attacks that player each combat if able\.',body,re.I)
    if m:
        creature = language.target_group('target creature')
        if creature is not None:
            return ([{'do':'until','duration':'end_of_next_turn','n':1},
                     {'do':'restrict','who':'target','player':'event_player',
                      'rules':['attack_player:@that']}],[creature],False)
    if body == 'Choose two target players. Until your next turn, each creature they control attacks the other chosen player each combat if able.':
        from app.rules import selectors

        group = language.target_group('target player')
        if group is not None:
            key = selectors.Selector(types=('Creature',)).key()
            return ([{'do':'until','duration':'next_turn','n':2},
                     *[{'do':'restrict','who':f'controlled:target:{i}|{key}',
                        'player':f'target:{1-i}','rules':['attack_player:@that']} for i in range(2)]],
                    [group,{**group,'distinct_from':[0]}],False)
    m = re.fullmatch(r'Mill a card and choose an opponent at random\. (?:~|This creature) attacks that player this combat if able\. (?P<rest>Until end of turn, .+)',body,re.I)
    if m:
        from app.rules import scripts

        rest = scripts.parse_effects(m['rest'])
        if rest is not None and rest[1] is None and not rest[2]:
            return ([{'do':'mill','who':'you','n':1},
                     {'do':'choose_random','pool':'opponent','as':'attack_destination'},
                     {'do':'restrict','who':'self','player':'ref:attack_destination',
                      'rules':['attack_player:@that'],'duration':'end_of_combat'},*rest[0]],None,False)
    return None


def static_definition(text: str) -> dict[str, Any] | None:
    from app.rules import statics

    if text == "All creatures attack enchanted creature's controller each combat if able.":
        who, _ = statics._subject('All creatures')
        if who is not None:
            return statics._definition(who,None,[],rules=['attack_host_controller:@src'])
    m = re.fullmatch(r"~ attacks an opponent with the most life among your opponents each combat if able unless you control a creature named (?P<name>[^.]+)\.",text)
    if m:
        return statics._definition('self',None,[],rules=['attack_most_life:@src|' + m['name']])
    return None


def attack_window(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A continuous rule begins at the named phase; it is not a delayed triggered ability."""
    from app.rules import effects, layers, selectors

    if e['window'] == 'next_combat':
        for cid in effects._cards(plan,ctx,e['who']):
            card = plan.state.cards[cid]
            layers.add_effect(plan,affected=[plan.oid(cid)],layer='6',source=ctx.get('source_object'),
                              controller=ctx['controller'],duration='permanent',imposes=('must_attack',),
                              declaration_window='next_combat',declaration_player=card.controller)
    else:
        for pid in effects._players(plan,ctx,e['player']):
            key = selectors.Selector(types=('Creature',),controller=f'player:{pid}').key()
            source = ctx.get('source_object') or ''
            layers.add_effect(plan,affected=[],who=key,layer='6',source=source,
                              controller=ctx['controller'],duration='permanent',
                              imposes=(f'attack_object:{source}',),
                              declaration_window='next_turn',declaration_player=pid)
    return True


def begin_window(plan: Plan, kind: str) -> None:
    for effect in plan.rules.effects:
        if effect.declaration_window == kind and effect.declaration_player == plan.active:
            effect.declaration_window = None
            effect.duration = 'end_of_combat' if kind == 'next_combat' else 'end_of_turn'


def attack_tokens_each(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    block: list[dict[str, Any]] = []
    for index, pid in enumerate(p for p in plan.live() if p != ctx['controller']):
        key = f'attack_tokens_{ctx["next"]}_{index}'
        block.extend([{**e['create'],'who':'you','as':key},
                      {'do':'restrict','who':f'ref:{key}','player':f'player:{pid}',
                       'rules':['attack_player:@that'],'locked':True},
                      {'do':'grant','who':f'ref:{key}','keywords':['haste']}])
    ctx['effects'][ctx['next']:ctx['next']] = block
    return True


PRIMITIVES = {'attack_window': attack_window, 'attack_tokens_each': attack_tokens_each}
