"""Exact45 immediate casts; unadmitted recipes remain behind native proof gates."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import exile_packet_continuations as packets


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts, selectors

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    if text=='whenever ~ deals combat damage to a player, you may cast your commander from the command zone without paying its mana cost':
        native=scripts.define(replace(ability,text='Whenever ~ deals combat damage to a player, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[step('commander')]}
    if text=="when ~ enters, for each opponent, you may cast up to one target instant or sorcery card from that player's graveyard without paying its mana cost. if a spell cast this way would be put into a graveyard, exile it instead":
        native=scripts.define(replace(ability,text="When ~ enters, for each opponent, exile up to one target instant or sorcery card from that player's graveyard."),ch)
        assert native is not None
        return {**native,'effects':[step('target_cards',who='target')]}
    if text=='when ~ enters, target opponent reveals their hand. you may cast an instant or sorcery spell from among those cards without paying its mana cost':
        native=scripts.define(replace(ability,text='When ~ enters, target opponent reveals their hand.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'reveal_hand','who':'target','as':'cast45_revealed'},
            {'do':'free_cast','zone':'that','who':'ref:cast45_revealed','exact_refs':True,'optional':True,'n':1,
             'source_zone':'hand','source_owner':'target','filter':selectors.Selector(types=('Instant','Sorcery'),zones=('stack',)).key()}]}
    if text=='whenever ~ attacks, you may cast an artifact spell from your hand or graveyard by paying life equal to its mana value rather than paying its mana cost':
        native=scripts.define(replace(ability,text='Whenever ~ attacks, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'free_cast','zone':'hand_graveyard','optional':True,'n':1,
            'filter':selectors.Selector(types=('Artifact',),zones=('stack',)).key(),'effect_alternative':'life_mv'}]}
    if text=="at the beginning of your upkeep, you may cast a permanent spell from your hand with mana value equal to 1 plus the greatest mana value among other permanents you control without paying its mana cost. if you don't, scry 1":
        native=scripts.define(replace(ability,text='At the beginning of your upkeep, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[step('greatness')]}
    combat_recipes={
        "whenever ~ deals combat damage to a player, exile the top card of that player's library. then you may sacrifice another creature or artifact. if you do, you may play the exiled card this turn, and mana of any type can be spent to cast it": 'reno',
        "whenever ~ deals combat damage to a player, that player exiles cards from the top of their library until they exile a nonland card. you may put a +1/+1 counter on ~. if you don't, you may cast the exiled nonland card until end of turn and mana of any type can be spent to cast that spell": 'widow',
    }
    if text in combat_recipes:
        native=scripts.define(replace(ability,text='Whenever ~ deals combat damage to a player, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[step(combat_recipes[text])]}
    return None


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts

    text=packets.normalize(body)
    if text=="return target spell or nonland permanent an opponent controls to its owner's hand. you may cast an instant or sorcery spell with equal or lesser mana value from your hand without paying its mana cost":
        native=scripts.parse_effects("Return target spell or nonland permanent an opponent controls to its owner's hand.")
        assert native is not None
        return [step('target_mv',action='bounce',instant_sorcery=True)],native[1],False
    if text=='counter target spell. you may cast a spell with equal or lesser mana value from your hand without paying its mana cost':
        native=scripts.parse_effects('Counter target spell.')
        assert native is not None
        return [step('target_mv',action='counter')],native[1],False
    if text=='draw three cards. then target opponent faces a villainous choice — they discard three cards, or you may cast a spell from your hand without paying its mana cost':
        native=scripts.parse_effects('Target opponent discards three cards.')
        assert native is not None
        return [{'do':'draw','who':'you','n':3},step('villainous')],native[1],False
    if text=="target opponent mills nine cards, then you may cast an instant or sorcery spell from that player's graveyard without paying its mana cost. if that spell would be put into a graveyard, exile it instead":
        native=scripts.parse_effects('Target opponent mills nine cards.')
        assert native is not None
        return [*native[0],step('target_graveyard')],native[1],False
    if text=="each opponent mills three cards, then you may cast a spell from each opponent's graveyard without paying its mana cost. if a spell cast this way would be put into a graveyard, exile it instead":
        native=scripts.parse_effects('Each opponent mills three cards.')
        assert native is not None
        return [*native[0],step('opponent_graveyards')],native[1],False
    if text=='you may cast an instant or sorcery spell with mana value 1 or 2 from your hand without paying its mana cost':
        key=packets.selector('instant or sorcery spells with mana value 1 or 2')
        return [{'do':'free_cast','zone':'hand','optional':True,'n':1,'filter':key}],None,False
    if text=='exile target instant or sorcery card from your graveyard. copy it. you may cast the copy':
        native=scripts.parse_effects('Exile target instant or sorcery card from your graveyard. Copy it. You may cast the copy without paying its mana cost.')
        assert native is not None and native[0][-1]['do']=='free_cast'
        return [*native[0][:-1],{**native[0][-1],'paid':True}],native[1],False
    talent='target opponent reveals the top seven cards of their library. you may cast an instant or sorcery spell from among them without paying its mana cost. then that player puts the rest into their graveyard'
    mastery='if there are two or more instant and/or sorcery cards in your graveyard, you may cast up to two instant and/or sorcery spells from among the revealed cards instead of one'
    if text in (talent,talent+'. '+mastery):
        # Native _merge_instead_lines binds the printed mastery replacement to
        # its preceding instruction, rather than resolving a second action.
        return [{'do':'look_top','n':7,'player':'target','reveal':True},step('talent',mastery=text!=talent),
                {'do':'rest_looked','to':'graveyard'}],'opponent',False
    if text=='target opponent chooses x cards from their hand. look at those cards. you may cast a spell from among them without paying its mana cost':
        return [step('extract')],'opponent',False
    return None


def step(mode: str,**fields: Any) -> dict[str,Any]:
    return {'do':'exile_cast_outcome45','mode':mode,'binding':'ref:cast45',**fields}


def run(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects, scripts, selectors, stack_interaction

    mode=e['mode']
    if mode in {'reno','widow'}:
        players=ctx.get('event',{}).get('players',[])
        if not players:
            return True
        if mode=='reno':
            packets.top_packet(plan,ctx,e,[players[0]])
            source=plan.state.cards.get(ctx.get('source_card',''))
            same=source is not None and plan.oid(source)==ctx.get('source_object')
            cost='Sacrifice another creature or artifact' if same else 'Sacrifice a creature or artifact'
            tail=scripts.parse_effects('You may '+cost.lower()+'. If you do, you gain 1 life.')
            grant=packets.grant(e,play=True,spend='type')
        else:
            packets.until_packet(plan,ctx,e,players[0],packets.selector('nonland card',zones=('library',)))
            tail=scripts.parse_effects("You may put a +1/+1 counter on ~. If you don't, you gain 1 life.")
            grant=packets.grant(e,suffix='_found',spend='type')
        assert tail is not None
        return packets.insert(ctx,[*tail[0][:-1],grant])
    if mode=='extract':
        players=effects._players(plan,ctx,'target')
        if not players:
            return True
        player=players[0]
        cards=list(plan.state.zones.get(player+':hand',[]))
        count=min(effects._amount(plan,ctx,{'x':1}),len(cards))
        if count==0:
            return True
        context.bind_objects(plan,ctx,packets.bind(e,'_hand'),cards)
        effects.decide(plan,player=player,kind='choose_cards',prompt=f'Choose {count} cards for the caster to look at',
            options=[DecisionOption(id=cid,label=plan.state.cards[cid].name or 'Card',card_id=cid) for cid in cards],
            min_choices=count,max_choices=count,
            resume={'step':'exile_cast_extract45','stage':'owner','ctx':ctx,'e':e,'owner':player})
        return False
    if mode=='extract_cleanup':
        cards=[cid for cid in context.objects(plan,ctx,packets.bind(e,'_shown')) if plan.state.cards[cid].zone.endswith(':hand')]
        if cards:
            plan.do({'type':'hide','card_ids':cards,'viewers':[ctx['controller']]},actor=ctx['controller'])
        return True
    if mode=='talent':
        graveyard=plan.state.zones.get(ctx['controller']+':graveyard',[])
        mastery=e.get('mastery') and sum(bool(set(plan.ch(plan.state.cards[cid]).types)&{'Instant','Sorcery'}) for cid in graveyard)>=2
        return packets.insert(ctx,[{'do':'free_cast','zone':'looked','optional':True,'n':2 if mastery else 1,
            'source_zone':'library','source_owner':'target',
            'filter':selectors.Selector(types=('Instant','Sorcery'),zones=('stack',)).key()}])
    if mode=='greatness':
        cards=[card for card in plan.state.cards.values() if card.zone.endswith(':battlefield')
               and card.controller==ctx['controller'] and plan.oid(card)!=ctx.get('source_object') and plan.in_game(card)]
        amount=1+max((stack_interaction.mana_value(card,plan.ch(card)) for card in cards),default=0)
        return packets.insert(ctx,[{'do':'free_cast','zone':'hand','optional':True,'n':1,'mv':amount,'mv_eq':True,
            'filter':selectors.Selector(types=('Artifact','Battle','Creature','Enchantment','Planeswalker'),zones=('stack',)).key(),
            'did':packets.bind(e,'_cast')},
            {'do':'only_if','cond':{'succeeded':packets.bind(e,'_cast'),'negate':True},'skip':1},
            {'do':'scry','who':'you','n':1}])
    if mode=='target_mv':
        cards=effects._cards(plan,ctx,'target')
        if not cards:
            return True
        card=plan.state.cards[cards[0]]
        amount=stack_interaction.mana_value(card,plan.ch(card))
        offer={'do':'free_cast','zone':'hand','optional':True,'n':1,'mv':amount}
        if e.get('instant_sorcery'):
            offer['filter']=selectors.Selector(types=('Instant','Sorcery'),zones=('stack',)).key()
        return packets.insert(ctx,[{'do':e['action'],'who':'target'},offer])
    if mode=='commander':
        cards=[cid for cid in plan.state.zones.get(ctx['controller']+':command',[]) if plan.state.cards[cid].commander_key and plan.state.cards[cid].owner==ctx['controller']]
        context.bind_objects(plan,ctx,packets.bind(e,'_packet'),cards)
        return packets.insert(ctx,[packets.offer(e,n=1,source_zone='command')])
    if mode=='target_cards':
        cards=[cid for cid in effects._cards(plan,ctx,e['who']) if plan.state.cards[cid].zone.endswith(':graveyard')]
        context.bind_objects(plan,ctx,packets.bind(e,'_packet'),cards)
        return packets.insert(ctx,[packets.offer(e,n=1,exile_gy=True)])
    if mode=='opponent_graveyards':
        return packets.insert(ctx,[step('one_opponent_graveyard',player=p) for p in plan.apnap() if p!=ctx['controller']])
    if mode=='one_opponent_graveyard':
        player=e['player']
        if player not in plan.live():
            return True
        cards=list(plan.state.zones.get(player+':graveyard',[]))
        context.bind_objects(plan,ctx,packets.bind(e,'_packet'),cards)
        return packets.insert(ctx,[packets.offer(e,n=1,exile_gy=True,source_zone='graveyard',source_owner='player:'+player)])
    if mode=='target_graveyard':
        players=effects._players(plan,ctx,'target')
        cards=[cid for player in players for cid in plan.state.zones.get(player+':graveyard',[])]
        context.bind_objects(plan,ctx,packets.bind(e,'_packet'),cards)
        return packets.insert(ctx,[packets.offer(e,n=1,exile_gy=True,
            filter=selectors.Selector(types=('Instant','Sorcery'),zones=('stack',)).key())])
    if mode=='villainous':
        players=effects._players(plan,ctx,'target')
        if not players:
            return True
        effects.decide(plan,player=players[0],kind='choose_one',prompt='Face a villainous choice',
            options=[DecisionOption(id='discard',label='Discard three cards'),DecisionOption(id='cast',label='The caster may cast a spell for free')],
            min_choices=1,max_choices=1,resume={'step':'exile_cast_outcome45','ctx':ctx,'player':players[0]})
        return False
    raise AssertionError('Unknown exact45 continuation')


def resume(plan: Any,d: Any,chosen: list[str]) -> None:
    from app.rules import effects

    ctx=d.resume['ctx']
    following=({'do':'discard','who':'player:'+d.resume['player'],'n':3} if chosen==['discard'] else
        {'do':'free_cast','zone':'hand','optional':True,'n':1})
    packets.insert(ctx,[following])
    effects.continue_effects(plan,ctx)


def resume_extract(plan: Any,d: Any,chosen: list[str]) -> None:
    from app.game.state import ALL
    from app.rules import context, effects

    ctx,e=d.resume['ctx'],d.resume['e']
    if d.resume['stage']=='owner':
        eligible=set(context.objects(plan,ctx,packets.bind(e,'_hand')))
        cards=[cid for cid in chosen if cid in eligible and plan.state.cards[cid].zone==d.player+':hand']
        context.bind_objects(plan,ctx,packets.bind(e,'_packet'),cards)
        added=[cid for cid in cards if ctx['controller'] not in plan.state.cards[cid].revealed_to and ALL not in plan.state.cards[cid].revealed_to]
        context.bind_objects(plan,ctx,packets.bind(e,'_shown'),added)
        if added:
            plan.do({'type':'reveal','card_ids':added,'to':[ctx['controller']]},actor=ctx['controller'])
        if cards:
            from app.game.rules_state import DecisionOption

            effects.decide(plan,player=ctx['controller'],kind='confirm',prompt='Look at the chosen cards',
                options=[DecisionOption(id='ok',label='Done looking')],
                resume={'step':'exile_cast_extract45','stage':'view','ctx':ctx,'e':e,'owner':d.player})
            return
    else:
        packets.insert(ctx,[packets.offer(e,n=1,source_zone='hand',source_owner='player:'+d.resume['owner']),
                            {**e,'mode':'extract_cleanup'}])
    effects.continue_effects(plan,ctx)


PRIMITIVES={'exile_cast_outcome45':run}
RESUME={'exile_cast_outcome45':resume,'exile_cast_extract45':resume_extract}


LIVE_DEFINITIONS: frozenset[str]=frozenset({
    "when ~ enters, for each opponent, you may cast up to one target instant or sorcery card from that player's graveyard without paying its mana cost. if a spell cast this way would be put into a graveyard, exile it instead",
    "whenever ~ deals combat damage to a player, exile the top card of that player's library. then you may sacrifice another creature or artifact. if you do, you may play the exiled card this turn, and mana of any type can be spent to cast it",
    'whenever ~ attacks, you may cast an artifact spell from your hand or graveyard by paying life equal to its mana value rather than paying its mana cost',
    "whenever ~ deals combat damage to a player, that player exiles cards from the top of their library until they exile a nonland card. you may put a +1/+1 counter on ~. if you don't, you may cast the exiled nonland card until end of turn and mana of any type can be spent to cast that spell",
    'when ~ enters, target opponent reveals their hand. you may cast an instant or sorcery spell from among those cards without paying its mana cost',
    'whenever ~ deals combat damage to a player, you may cast your commander from the command zone without paying its mana cost',
    "at the beginning of your upkeep, you may cast a permanent spell from your hand with mana value equal to 1 plus the greatest mana value among other permanents you control without paying its mana cost. if you don't, scry 1",
})

LIVE_BODIES: frozenset[str]=frozenset({
    'you may cast an instant or sorcery spell with mana value 1 or 2 from your hand without paying its mana cost',
    'exile target instant or sorcery card from your graveyard. copy it. you may cast the copy',
    "each opponent mills three cards, then you may cast a spell from each opponent's graveyard without paying its mana cost. if a spell cast this way would be put into a graveyard, exile it instead",
    'target opponent reveals the top seven cards of their library. you may cast an instant or sorcery spell from among them without paying its mana cost. then that player puts the rest into their graveyard',
    'target opponent reveals the top seven cards of their library. you may cast an instant or sorcery spell from among them without paying its mana cost. then that player puts the rest into their graveyard. if there are two or more instant and/or sorcery cards in your graveyard, you may cast up to two instant and/or sorcery spells from among the revealed cards instead of one',
    "target opponent mills nine cards, then you may cast an instant or sorcery spell from that player's graveyard without paying its mana cost. if that spell would be put into a graveyard, exile it instead",
    'draw three cards. then target opponent faces a villainous choice — they discard three cards, or you may cast a spell from your hand without paying its mana cost',
    "return target spell or nonland permanent an opponent controls to its owner's hand. you may cast an instant or sorcery spell with equal or lesser mana value from your hand without paying its mana cost",
    'counter target spell. you may cast a spell with equal or lesser mana value from your hand without paying its mana cost',
    'target opponent chooses x cards from their hand. look at those cards. you may cast a spell from among them without paying its mana cost',
})


def production_definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    return definition(ability,ch) if text in LIVE_DEFINITIONS else None


def production_parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    return parse(body) if packets.normalize(body) in LIVE_BODIES else None
