"""Exact42 continuations with explicit production recipe admission."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from app.rules import exile_packet_continuations as packets


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    if ability.kind=='spell' and (parsed:=parse(scripts.self_text(ability.text,ch.name))) is not None:
        return {'kind':'spell','effects':parsed[0],**scripts.target_fields(parsed[1])}
    if text=='whenever you cast an instant or sorcery spell from your hand, you may cast up to one target card of the other type from your graveyard. if a spell cast from your graveyard this way would be put into your graveyard, exile it instead':
        from app.rules import selectors

        native=scripts.define(replace(ability,text='Whenever you cast an instant or sorcery spell, you gain 1 life.'),ch)
        assert native is not None
        target=selectors.Selector(card=True,zones=('graveyard',),zone_owner='you',types=('Instant','Sorcery')).key()
        return {**native,'trigger':'event','cond':{'event':'cast','subject':'player','player':'you',
                'spell':selectors.Selector(zones=('stack',),types=('Instant','Sorcery')).key(),
                'from':'hand','from_owner':'you'},'target_other_is_type':True,
                'target':None,'targets':[{'what':target,'min':0,'max':1}],
                'effects':[{'do':'free_cast','zone':'target','optional':True,'paid':True,'n':1,
                            'exile_gy':True,'exile_own':True}]}
    if text=="at the beginning of your end step, exile target noncreature, nonland card from your graveyard. create a 3/2 red and white spirit creature token":
        native=scripts.define(replace(ability,text='At the beginning of your end step, exile target noncreature, nonland card from your graveyard.'),ch)
        token=scripts.parse_effects('Create a 3/2 red and white Spirit creature token.')
        assert native is not None and token is not None
        return {**native,'effects':[{**effect,'link':True} for effect in native['effects']]+token[0]}
    if text=="{1}{r}{w}, {t}, sacrifice a spirit: choose target card exiled with ~. you may cast that card this turn without paying its mana cost. if that spell would be put into a graveyard, put it on the bottom of its owner's library instead":
        native=scripts.define(replace(ability,text="{1}{R}{W}, {T}, Sacrifice a Spirit: Return target card exiled with ~ to the battlefield under your control."),ch)
        assert native is not None
        return {**native,'effects':[{'do':'exile_outcomes44_quintorius','binding':'ref:quintorius44'}]}
    if text=="at the beginning of your upkeep, choose an opponent at random. exile the top card of that player's library. until end of turn, you may play that card and you may spend mana as though it were mana of any color to cast it. when you cast a spell this way, its owner loses life equal to its mana value":
        native=scripts.define(replace(ability,text='At the beginning of your upkeep, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'choose_random','pool':'opponent','as':'ruinous_player'},
                {'do':'exile_top','player':'ref:ruinous_player','n':1,'as':'ruinous_packet'},
                {'do':'grant_play','who':'ref:ruinous_packet','from_exile':True,'play':True,'cast':True,
                 'until':'end_of_turn','spend':'color','use_trigger':{'kind':'owner_loses_mv','index':ability.index}}]}
    if text=="when ~ enters and whenever an opponent loses the game, exile the top card of each player's library":
        return {'kind':'triggered','trigger':'event','optional':False,
                'cond':{'event':'either','conds':[{'event':'enter','subject':'self'},
                         {'event':'lose_game','subject':'player','player':'opponent'}]},
                'effects':[{'do':'exile_top','player':'each_player','n':1,'link':True,'as':'spoils_packet'}]}
    if text=="during each player's turn, that player may play a land or cast a spell from among cards exiled with ~, and they may spend mana as though it were mana of any color to cast that spell. when they do, exile the top card of their library":
        return {'kind':'static','static':'permission','zone':'exile','linked':True,'filter':None,
                'self':False,'play':True,'cast':True,'once':True,'once_per_player':True,'any_player':True,
                'during':'your_turn','flash':False,'spend':'color','use_trigger':'replenish_top','effects':[]}
    if text=='draw x cards, where x is the greatest power among creatures you controlled as you cast this spell. if this spell was cast from exile, you gain twice x life':
        native=scripts.define(replace(ability,text='Draw X cards. If this spell was cast from exile, you gain twice X life.'),ch)
        assert native is not None
        return {**native,'x_as_cast':'greatest_own_power'}
    if text=='{4}, {t}: roll a d20. each opponent exiles cards from the top of their library until they exile an instant or sorcery card, then shuffles the rest into their library. you may cast up to x instant and/or sorcery spells from among cards exiled this way without paying their mana costs. 1—9 | x is one. 10—19 | x is two. 20 | x is three':
        return {'kind':'activated','cost':ability.cost,
                'effects':[{'do':'roll','sides':20,'count':1},
                           {'do':'exile_outcomes42_wand','binding':'ref:wand42'}]}
    if text=='at the beginning of your upkeep, exile the top card of your library. for as long as it remains exiled, it has "you may cast this card from exile as long as you\'ve cast another spell this turn."':
        native=scripts.define(replace(ability,text='At the beginning of your upkeep, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'exile_outcomes42_monk','binding':'ref:monk42'}]}
    if text=='when ~ enters, each opponent exiles a card from their hand until ~ leaves the battlefield':
        return {'kind':'triggered','trigger':'enters_self','optional':False,
                'effects':[{'do':'exile_outcomes42_intellect','binding':'ref:intellect42'}]}
    if text=='you may play lands and cast spells from among cards exiled with ~. if you cast a spell this way, you may spend mana as though it were mana of any color to cast it':
        return {'kind':'static','static':'permission','zone':'exile','linked':True,'filter':None,
                'self':False,'play':True,'cast':True,'once':False,'flash':False,'spend':'color','effects':[]}
    if text=="when ~ enters, look at the top card of each opponent's library and exile those cards face down":
        native=scripts.define(replace(ability,text='When ~ enters, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'exile_outcomes42_lobelia_enter','binding':'ref:lobelia42'}]}
    if text=='you may play lands and cast spells from among cards you own in exile with croak counters on them':
        return {'kind':'static','static':'permission','zone':'exile','filter':None,'self':False,
                'play':True,'cast':True,'once':False,'flash':False,'own':True,
                'exile_counter':'croak','effects':[]}
    if text=='whenever a permanent card is put into your graveyard from your library, exile it with a croak counter on it':
        native=scripts.define(replace(ability,text='Whenever a permanent card is put into your graveyard from your library, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'exile_outcomes42_stash','binding':'ref:croak42','counter':'croak','event_binding':'event'}]}
    if text=="during your turn, you may play cards you don't own with stash counters on them from exile, and mana of any type can be spent to cast those spells":
        return {'kind':'static','static':'permission','zone':'exile','filter':None,'self':False,
                'play':True,'cast':True,'once':False,'flash':False,'foreign':True,
                'exile_counter':'stash','during':'your_turn','spend':'type','effects':[]}
    if text=='whenever an opponent discards a card, exile it from their graveyard with a stash counter on it':
        native=scripts.define(replace(ability,text='Whenever an opponent discards a card, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'exile_outcomes42_stash','binding':'ref:stash42'}]}
    if text=='whenever one or more opponents each lose exactly 1 life, put a +1/+1 counter on ~. exile the top card of your library. until your next end step, you may play that card':
        native=scripts.define(replace(ability,text='Whenever one or more opponents lose life, put a +1/+1 counter on ~.'),ch)
        assert native is not None
        return {**native,'cond':{**native['cond'],'life_loss_exact':1},
                'effects':[*native['effects'],{'do':'exile_outcomes42_kingpin','binding':'ref:kingpin42'}]}
    if text=='whenever you discard one or more nonland cards, you may exile one of them from your graveyard. if you do, you may cast it this turn':
        native=scripts.define(replace(ability,text='Whenever you discard one or more nonland cards, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'exile_outcomes42_discard','binding':'ref:theorist42'}]}
    if text=='whenever you cast a dragon creature spell from your graveyard, it gains "when ~ dies, exile it."':
        native=scripts.define(replace(ability,text='Whenever you cast a Dragon creature spell from your graveyard, you gain 1 life.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'spell_rider','who':'event_spell',
                                   'riders':[{'kind':'granted_ability','ability':'dies_exile_self'}]}]}
    return None


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    text=packets.normalize(body)
    if text=="until the end of your next turn, whenever you cast a spell, ~ deals 2 damage to up to one target creature":
        from app.rules import events, selectors

        condition=events.parse_condition('you cast a spell')
        assert condition is not None
        return [{'do':'delayed','when':{'kind':'watch','cond':condition,
                    'text':'Whenever you cast a spell'},'n':1,'once':False,'end_of_next_turn':True,
                 'targets':[{'what':selectors.Selector(types=('Creature',),zones=('battlefield',)).key(),'min':0,'max':1}]},
                {'do':'deferred:damage','who':'watch_target:0','n':2}],None,False
    if text=="each opponent faces a villainous choice — they exile cards from the top of their library until they exile a nonland card, then you may cast that card without paying its mana cost, or that player exiles the top four cards of their library and ~ deals damage equal to the total mana value of those exiled cards to that player":
        return [{'do':'exile_outcomes44_mara','binding':'ref:mara44'}],None,False
    if text in ('each player with exactly 13 life loses the game, then each player gains 1 life',
                'each player with exactly 13 life loses the game, then each player loses 1 life'):
        from app.rules import scripts

        native=scripts.parse_effects('Each player with exactly 13 life loses the game.')
        assert native is not None
        return [*native[0],{'do':'gain_life' if 'gains 1 life' in text else 'lose_life','who':'each_player','n':1}],native[1],native[2]
    if text=='each player mills four cards. then you may exile a creature or planeswalker card from each graveyard':
        return [{'do':'mill','who':'each_player','n':4},
                {'do':'exile_outcomes42_narfi','binding':'ref:narfi42'}],None,False
    if text=='until end of turn, you may cast spells from among cards exiled with ~, and you may spend mana as though it were mana of any color to cast those spells':
        return [{'do':'exile_outcomes42_linked_grant','binding':'ref:narfi42','spend':'color'}],None,False
    if text=='until end of turn, you may play a card exiled with ~ without paying its mana cost':
        return [{'do':'exile_outcomes42_lobelia','binding':'ref:lobelia42'}],None,False
    if text=='shuffle your library. as many times as you choose, you may exile the top card of your library. if the total mana value of the cards exiled this way is 13 or less, you may cast any number of spells from among those cards without paying their mana costs':
        return [{'do':'shuffle_library','who':'you'}, {'do':'exile_outcomes42_dance','binding':'ref:dance42','total_mv':0}],None,False
    return None


def dance_next(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects

    if not plan.state.zones.get(ctx['controller']+':library',[]):
        return dance_stop(plan,ctx,e)
    effects.decide(plan,player=ctx['controller'],kind='confirm',prompt='Exile the next card, or stop?',
                   options=[DecisionOption(id='yes',label='Exile the top card'),DecisionOption(id='no',label='Stop')],
                   resume={'step':'exile_outcomes42_dance','ctx':ctx,'e':e})
    return False


def dance_stop(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    if e['total_mv']>13:
        return True
    return packets.insert(ctx,[packets.offer(e,'_all',**{'all':True})])


def resume_dance(plan: Any,d: Any,chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx,e=d.resume['ctx'],d.resume['e']
    if chosen==['no']:
        dance_stop(plan,ctx,e)
    else:
        old=packets.remaining(plan,ctx,e,'_all')
        actual=packets.top_packet(plan,ctx,e,[ctx['controller']])
        total=e['total_mv']+sum(plan.ch(plan.state.cards[cid]).mana_value for cid in actual)
        context.bind_objects(plan,ctx,packets.bind(e,'_all'),[*old,*actual])
        packets.insert(ctx,[{**e,'total_mv':total}])
    effects.continue_effects(plan,ctx)


def discarded_choice(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects

    cards=[cid for cid in context.objects(plan,ctx,'event.new')
           if plan.state.cards[cid].zone==ctx['controller']+':graveyard'
           and 'Land' not in plan.ch(plan.state.cards[cid]).types]
    if not cards:
        return True
    context.bind_objects(plan,ctx,packets.bind(e,'_eligible'),cards)
    effects.decide(plan,player=ctx['controller'],kind='choose_cards',prompt='Exile up to one discarded nonland card',
                   options=[DecisionOption(id=cid,label=plan.state.cards[cid].name,card_id=cid) for cid in cards],
                   min_choices=0,max_choices=1,
                   resume={'step':'exile_outcomes42_discard','ctx':ctx,'e':e})
    return False


def resume_discard(plan: Any,d: Any,chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx,e=d.resume['ctx'],d.resume['e']
    eligible=set(context.objects(plan,ctx,packets.bind(e,'_eligible')))
    cards=[cid for cid in chosen if cid in eligible and plan.state.cards[cid].zone==ctx['controller']+':graveyard']
    if cards:
        effects.exile_cards(plan,ctx,{'as':packets.bind(e,'_packet')},cards)
        packets.insert(ctx,[packets.grant(e)])
    effects.continue_effects(plan,ctx)


def stash_packet(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, effects

    cards=[cid for cid in context.objects(plan,ctx,e.get('event_binding','event.new'))
           if plan.state.cards[cid].zone.endswith(':graveyard')]
    if cards:
        effects.exile_cards(plan,ctx,{'as':packets.bind(e,'_packet')},cards)
        packets.insert(ctx,[{'do':'add_counters','who':packets.ref(e,'_packet'),'kind':e.get('counter','stash'),'n':1}])
    return True


def wand_packet(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, effects, selectors

    key=selectors.Selector(card=True,zones=('library',),types=('Instant','Sorcery')).key()
    found: list[str]=[]
    for player in plan.apnap():
        if player==ctx['controller']:
            continue
        packet={**e,'binding':e['binding']+'_'+player}
        packets.until_packet(plan,ctx,packet,player,key)
        chosen=packets.remaining(plan,ctx,packet,'_found')
        rest=[cid for cid in packets.remaining(plan,ctx,packet) if cid not in chosen]
        found.extend(chosen)
        if rest:
            plan.do({'type':'move','card_ids':rest,'to':{'player':player,'zone':'library'}},actor=player)
        effects.shuffle_library(plan,ctx,{'who':'player:'+player})
    context.bind_objects(plan,ctx,packets.bind(e,'_packet'),found)
    result=int(ctx.get('die') or 0)
    n=1 if 1<=result<=9 else 2 if 10<=result<=19 else 3 if result==20 else 0
    if not n:
        return True
    selected=selectors.Selector(zones=('stack',),types=('Instant','Sorcery')).key()
    return packets.insert(ctx,[packets.offer(e,n=n,filter=selected)])


def narfi_next(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects

    players=e.get('players',plan.apnap())
    for i,player in enumerate(players):
        cards=[cid for cid in plan.state.zones.get(player+':graveyard',[])
               if {'Creature','Planeswalker'} & set(plan.ch(plan.state.cards[cid]).types)]
        if not cards:
            continue
        effects.decide(plan,player=ctx['controller'],kind='choose_cards',prompt='Exile up to one creature or planeswalker card from '+plan.name(player)+"'s graveyard",
                       options=[DecisionOption(id=cid,label=plan.state.cards[cid].name,card_id=cid) for cid in cards],
                       min_choices=0,max_choices=1,
                       resume={'step':'exile_outcomes42_narfi','ctx':ctx,'e':{**e,'players':players[i+1:]}})
        return False
    cards=context.objects(plan,ctx,packets.bind(e,'_chosen'))
    return effects.exile_cards(plan,ctx,{'as':packets.bind(e,'_packet'),'link':True},cards)


def resume_narfi(plan: Any,d: Any,chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx,e=d.resume['ctx'],d.resume['e']
    old=context.objects(plan,ctx,packets.bind(e,'_chosen'))
    actual=[cid for cid in chosen if plan.state.cards[cid].zone.endswith(':graveyard')]
    context.bind_objects(plan,ctx,packets.bind(e,'_chosen'),[*old,*actual])
    packets.insert(ctx,[e])
    effects.continue_effects(plan,ctx)


def linked_grant(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, exiled_with

    context.bind_objects(plan,ctx,packets.bind(e,'_packet'),exiled_with.cards(plan,ctx))
    return packets.insert(ctx,[packets.grant(e,spend=e.get('spend',''))])


MONK_ABILITY="You may cast this card from exile as long as you've cast another spell this turn."


def monk_packet(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import layers

    for cid in packets.top_packet(plan,ctx,e,[ctx['controller']]):
        layers.add_effect(plan,affected=[plan.oid(cid)],layer='6',source=ctx.get('source_object'),
                          controller=ctx['controller'],duration='permanent',add_abilities=[MONK_ABILITY],
                          ability_zone='exile',label='Monk Class: ability while this card remains exiled')
    return True


def intellect_next(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects

    if not effects._cards(plan,ctx,'self'):
        return True
    players=e.get('players',[p for p in plan.apnap() if p!=ctx['controller']])
    for i,player in enumerate(players):
        cards=list(plan.state.zones.get(player+':hand',[]))
        if not cards:
            continue
        effects.decide(plan,player=player,kind='choose_cards',prompt='Exile a card from your hand until Intellect Devourer leaves',
                       options=[DecisionOption(id=cid,label=plan.state.cards[cid].name,card_id=cid) for cid in cards],
                       min_choices=1,max_choices=1,
                       resume={'step':'exile_outcomes42_intellect','ctx':ctx,'e':{**e,'players':players[i+1:]}})
        return False
    return packets.insert(ctx,[{'do':'exile_until','who':packets.ref(e,'_chosen'),'hand_origin':True,'link':True}])


def resume_intellect(plan: Any,d: Any,chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx,e=d.resume['ctx'],d.resume['e']
    old=context.objects(plan,ctx,packets.bind(e,'_chosen'))
    actual=[cid for cid in chosen if plan.state.cards[cid].zone==d.player+':hand']
    context.bind_objects(plan,ctx,packets.bind(e,'_chosen'),[*old,*actual])
    packets.insert(ctx,[e])
    effects.continue_effects(plan,ctx)


def lobelia_enter(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import effects

    cards: list[str]=[]
    for player in plan.live():
        if player==ctx['controller']:
            continue
        effects.look_top(plan,ctx,{'n':1,'player':'player:'+player,'reveal':False,'exact_look':True})
        cards.extend(ctx.get('looked') or [])
    return effects.exile_cards(plan,ctx,{'as':packets.bind(e,'_packet'),'face_down':True,'link':True},cards)


def lobelia_packet(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, exiled_with

    cards=exiled_with.cards(plan,ctx)
    context.bind_objects(plan,ctx,packets.bind(e,'_packet'),cards)
    return packets.insert(ctx,[packets.grant(e,play=True,free=True,limit=1)])


def mara_next(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects

    players=e.get('players',[p for p in plan.apnap() if p!=ctx['controller']])
    if not players:
        return True
    effects.decide(plan,player=players[0],kind='choose_one',prompt='Face a villainous choice',
        options=[DecisionOption(id='cast',label='Exile until a nonland card; it may be cast for free'),
                 DecisionOption(id='damage',label='Exile four cards and take damage equal to their total mana value')],
        min_choices=1,max_choices=1,resume={'step':'exile_outcomes44_mara','ctx':ctx,'e':{**e,'players':players[1:]},'player':players[0]})
    return False


def resume_mara(plan: Any,d: Any,chosen: list[str]) -> None:
    from app.rules import effects, stack_interaction

    ctx,e,player=d.resume['ctx'],d.resume['e'],d.resume['player']
    if chosen==['cast']:
        packets.until_packet(plan,ctx,e,player,packets.selector('nonland card',zones=('library',)))
        es=[packets.offer(e,'_found',n=1),e]
    else:
        cards=packets.top_packet(plan,ctx,e,[player],n=4)
        amount=sum(stack_interaction.mana_value(plan.state.cards[cid],plan.ch(plan.state.cards[cid])) for cid in cards)
        es=[{'do':'damage','who':'player:'+player,'n':amount},e]
    packets.insert(ctx,es)
    effects.continue_effects(plan,ctx)


def quintorius_packet(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, effects

    cards=[cid for cid in effects._cards(plan,ctx,'target') if plan.state.cards[cid].zone.endswith(':exile')]
    context.bind_objects(plan,ctx,packets.bind(e,'_packet'),cards)
    return packets.insert(ctx,[packets.grant(e,free=True,graveyard_destination='library_bottom')])


def kingpin_packet(plan: Any,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    packets.top_packet(plan,ctx,e,[ctx['controller']])
    return packets.insert(ctx,[packets.grant(e,play=True,until='next_end_step',until_player=ctx['controller'])])


PRIMITIVES={'exile_outcomes44_mara':mara_next,'exile_outcomes44_quintorius':quintorius_packet,'exile_outcomes42_wand':wand_packet,'exile_outcomes42_narfi':narfi_next,'exile_outcomes42_linked_grant':linked_grant,'exile_outcomes42_monk':monk_packet,'exile_outcomes42_intellect':intellect_next,'exile_outcomes42_lobelia_enter':lobelia_enter,'exile_outcomes42_dance':dance_next,'exile_outcomes42_discard':discarded_choice,
            'exile_outcomes42_lobelia':lobelia_packet,'exile_outcomes42_kingpin':kingpin_packet,'exile_outcomes42_stash':stash_packet}
RESUME: dict[str, Callable[[Any, Any, list[str]], None]]={'exile_outcomes44_mara':resume_mara,'exile_outcomes42_narfi':resume_narfi,'exile_outcomes42_intellect':resume_intellect,'exile_outcomes42_dance':resume_dance,'exile_outcomes42_discard':resume_discard}


LIVE_RECIPES: frozenset[str]=frozenset({"lifestream", "rivaz", "dance", "theorist", "monk", "intellect", "gale", "wand", "kingpin", "trisk", "tinybones", "grolnok", "lobelia", "narfi", "ruinous", "share", "mara", "quintorius", "season"})
_DEFINITION_RECIPES={
    'at the beginning of your end step, exile target noncreature, nonland card from your graveyard. create a 3/2 red and white spirit creature token':'quintorius',
    "{1}{r}{w}, {t}, sacrifice a spirit: choose target card exiled with ~. you may cast that card this turn without paying its mana cost. if that spell would be put into a graveyard, put it on the bottom of its owner's library instead":'quintorius',

    "when ~ enters and whenever an opponent loses the game, exile the top card of each player's library":'share',
    "during each player's turn, that player may play a land or cast a spell from among cards exiled with ~, and they may spend mana as though it were mana of any color to cast that spell. when they do, exile the top card of their library":'share',

    "at the beginning of your upkeep, choose an opponent at random. exile the top card of that player's library. until end of turn, you may play that card and you may spend mana as though it were mana of any color to cast it. when you cast a spell this way, its owner loses life equal to its mana value":'ruinous',
    'whenever you cast an instant or sorcery spell from your hand, you may cast up to one target card of the other type from your graveyard. if a spell cast from your graveyard this way would be put into your graveyard, exile it instead':'gale',
    'draw x cards, where x is the greatest power among creatures you controlled as you cast this spell. if this spell was cast from exile, you gain twice x life':'lifestream',
    '{4}, {t}: roll a d20. each opponent exiles cards from the top of their library until they exile an instant or sorcery card, then shuffles the rest into their library. you may cast up to x instant and/or sorcery spells from among cards exiled this way without paying their mana costs. 1—9 | x is one. 10—19 | x is two. 20 | x is three':'wand',
    'at the beginning of your upkeep, exile the top card of your library. for as long as it remains exiled, it has "you may cast this card from exile as long as you\'ve cast another spell this turn."':'monk',
    'when ~ enters, each opponent exiles a card from their hand until ~ leaves the battlefield':'intellect',
    'you may play lands and cast spells from among cards exiled with ~. if you cast a spell this way, you may spend mana as though it were mana of any color to cast it':'intellect',
    "when ~ enters, look at the top card of each opponent's library and exile those cards face down":'lobelia',
    'you may play lands and cast spells from among cards you own in exile with croak counters on them':'grolnok',
    'whenever a permanent card is put into your graveyard from your library, exile it with a croak counter on it':'grolnok',
    "during your turn, you may play cards you don't own with stash counters on them from exile, and mana of any type can be spent to cast those spells":'tinybones',
    'whenever an opponent discards a card, exile it from their graveyard with a stash counter on it':'tinybones',
    'whenever one or more opponents each lose exactly 1 life, put a +1/+1 counter on ~. exile the top card of your library. until your next end step, you may play that card':'kingpin',
    'whenever you discard one or more nonland cards, you may exile one of them from your graveyard. if you do, you may cast it this turn':'theorist',
    'whenever you cast a dragon creature spell from your graveyard, it gains "when ~ dies, exile it."':'rivaz',
}
_PARSE_RECIPES={
    'until the end of your next turn, whenever you cast a spell, ~ deals 2 damage to up to one target creature':'season',
    'each opponent faces a villainous choice — they exile cards from the top of their library until they exile a nonland card, then you may cast that card without paying its mana cost, or that player exiles the top four cards of their library and ~ deals damage equal to the total mana value of those exiled cards to that player':'mara',
    'each player with exactly 13 life loses the game, then each player gains 1 life':'trisk',
    'each player with exactly 13 life loses the game, then each player loses 1 life':'trisk',
    'each player mills four cards. then you may exile a creature or planeswalker card from each graveyard':'narfi',
    'until end of turn, you may cast spells from among cards exiled with ~, and you may spend mana as though it were mana of any color to cast those spells':'narfi',
    'until end of turn, you may play a card exiled with ~ without paying its mana cost':'lobelia',
    'shuffle your library. as many times as you choose, you may exile the top card of your library. if the total mana value of the cards exiled this way is 13 or less, you may cast any number of spells from among those cards without paying their mana costs':'dance',
}

def production_definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    return definition(ability,ch) if _DEFINITION_RECIPES.get(text) in LIVE_RECIPES else None


def production_parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    return parse(body) if _PARSE_RECIPES.get(packets.normalize(body)) in LIVE_RECIPES else None
