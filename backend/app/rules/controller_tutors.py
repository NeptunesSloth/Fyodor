"""Native tutor packets whose actor, recipient and preceding movement differ."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef
from app.rules import context, selectors
from app.rules import qualified_search_packets as queries

if TYPE_CHECKING:
    from app.rules.plan import Plan

BIND = 'ref:controller_tutor'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = ' '.join(body.lower().split()).rstrip('.')
    kinds: dict[str, tuple[str, Any]] = {
        "target artifact creature's controller sacrifices it. that player may search their library for a noncreature artifact card, put it onto the battlefield, then shuffle": ('arcum', 'artifact creature'),
        'destroy target nonbasic land an opponent controls. its controller searches their library for a basic land card, puts it onto the battlefield tapped with a stun counter on it, then shuffles': ('hellkite', 'nonbasic land an opponent controls'),
        'each opponent may search their library for up to three basic land cards. they each put one of those cards onto the battlefield tapped under your control and the rest onto the battlefield tapped under their control. then each player who searched their library this way shuffles': ('druid', None),
        'for each player, destroy up to one nonbasic land that player controls. for each land destroyed this way, its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle': ('buzzcrusher', None),
        'destroy all nonbasic lands. for each land destroyed this way, its controller may search their library for a basic land card and put it onto the battlefield. then each player who searched their library this way shuffles': ('ashes', None),
        'each player sacrifices all artifacts, enchantments, and nonbasic lands they control. for each land sacrificed this way, its controller may search their library for a basic land card and put it onto the battlefield tapped. then each player who searched their library this way shuffles': ('vitriol', None),
        'each player who controls six or more lands chooses five lands they control and sacrifices the rest. each player who controls four or fewer lands may search their library for up to x basic land cards and put them onto the battlefield, where x is five minus the number of lands they control. then each player who searched their library this way shuffles': ('balance', None),
        'any number of target players may each search their library for a basic land card, put it onto the battlefield under their control, then shuffle': ('tracks', {'what':'player','min':0,'max':999}),
        'you may search your library for a creature card with eternalize or embalm, put that card into your graveyard, then shuffle': ('vizier', None),
        "sacrifice an artifact. if you do, search your library for an artifact card. if that card's mana value is less than or equal to the sacrificed artifact's mana value, put it onto the battlefield. if it's greater, you may pay {x}, where x is the difference. if you do, put it onto the battlefield. if you don't, put it into its owner's graveyard. then shuffle": ('transmute', None),
    }
    if text not in kinds:
        return None
    kind, target = kinds[text]
    if kind == 'tracks':
        from app.rules import language

        target = [language.target_group('any number of target players')]
    if isinstance(target, str):
        target = _sel(target)
    return [{'do':'controller_tutor','kind':kind,'binding':BIND}], target, False


def insert(ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']] = es
    return True


def _sel(text: str) -> str:
    sel = selectors.parse(text)
    assert sel is not None, text
    return sel.key()


def _lands(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and c.controller == pid and 'Land' in plan.ch(c).types]


def _search_as(pid: str, search: dict[str, Any]) -> list[dict[str, Any]]:
    return [{'do':'as_player','player':pid},search,{'do':'as_player_end'}]


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    kind, bind = e['kind'], e['binding'].removeprefix(context.PREFIX)
    if kind in ('arcum','hellkite'):
        target = effects._cards(plan, ctx, 'target')
        if not target:
            return True
        pid = plan.state.cards[target[0]].controller
        context.bind_objects(plan, ctx, bind, target)
        search = queries.search('noncreature artifact card' if kind == 'arcum' else 'basic land card',
                                to='battlefield' if kind == 'arcum' else 'battlefield_tapped', may=kind == 'arcum')
        if kind == 'hellkite':
            search.update(counter='stun',counter_n=1)
        return insert(ctx,[{'do':'sacrifice' if kind == 'arcum' else 'destroy','who':e['binding'],'by':'controller'},*_search_as(pid,search)])
    if kind == 'vizier':
        search = queries.search('creature card',to='graveyard',may=True)
        search['controller_tutor_keyword_any'] = ['eternalize','embalm']
        return insert(ctx,[search])
    if kind == 'transmute':
        return insert(ctx,[{'do':'sacrifice_choice','who':'you','sel':_sel('artifacts'),'n':1,'as':bind},
                           {'do':'controller_tutor_after','kind':kind,'binding':e['binding']}])
    if kind == 'druid':
        players = [p for p in plan.apnap() if p != ctx['controller']]
        state = {'players':players,'searched':[],'original':ctx['controller'],'kind':kind}
        ctx.setdefault('controller_tutors',{})[bind] = state
        return next_player(plan,ctx,e)
    if kind == 'tracks':
        players = effects._players(plan,ctx,'target')
        return insert(ctx,[x for p in players for x in _search_as(p,queries.search('basic land card',to='battlefield',may=True))])
    if kind in ('buzzcrusher','balance'):
        state = {'players':list(plan.apnap()),'picked':[],'kind':kind}
        ctx.setdefault('controller_tutors',{})[bind] = state
        return choose_lands(plan,ctx,e)
    if kind in ('ashes','vitriol'):
        ids = []
        for card in plan.state.cards.values():
            if not card.zone.endswith(':battlefield'):
                continue
            ch = plan.ch(card)
            if ('Land' in ch.types and 'Basic' not in ch.supertypes) or (kind == 'vitriol' and ch.types & {'Artifact','Enchantment'}):
                ids.append(card.id)
        context.bind_objects(plan,ctx,bind,ids)
        return insert(ctx,[{'do':'sacrifice' if kind == 'vitriol' else 'destroy','who':e['binding'],'as':bind,'by':'controller'},
                           {'do':'controller_tutor_after','kind':kind,'binding':e['binding']}])
    return True


def choose_lands(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    bind = e['binding'].removeprefix(context.PREFIX)
    state = ctx['controller_tutors'][bind]
    while state['players']:
        pid = state['players'].pop(0)
        lands = _lands(plan,pid)
        if state['kind'] == 'buzzcrusher':
            lands = [c for c in lands if 'Basic' not in plan.ch(plan.state.cards[c]).supertypes]
            lo,hi,chooser = 0,min(1,len(lands)),ctx['controller']
        else:
            if len(lands) < 6:
                continue
            lo,hi,chooser = 5,5,pid
        if not hi:
            continue
        state['pool'] = lands
        decide(plan,player=chooser,kind='choose_cards',prompt='Choose a nonbasic land to destroy' if state['kind']=='buzzcrusher' else 'Choose five lands to keep',
               options=[DecisionOption(id=c,label=plan.ch(plan.state.cards[c]).name,card_id=c) for c in lands],
               min_choices=lo,max_choices=hi,resume={'step':'controller_tutor_lands','ctx':ctx,'e':e})
        return False
    context.bind_objects(plan,ctx,bind,state['picked'])
    return insert(ctx,[{'do':'destroy' if state['kind']=='buzzcrusher' else 'sacrifice','who':e['binding'],'as':bind,'by':'controller'},
                       {'do':'controller_tutor_after','kind':state['kind'],'binding':e['binding']}])


def resume_lands(plan: Plan,d: Any,chosen: list[str]) -> None:
    from app.rules import effects

    ctx,e = d.resume['ctx'],d.resume['e']
    state = ctx['controller_tutors'][e['binding'].removeprefix(context.PREFIX)]
    state['picked'].extend(chosen if state['kind']=='buzzcrusher' else [c for c in state['pool'] if c not in chosen])
    if choose_lands(plan,ctx,e):
        effects.continue_effects(plan,ctx)


def after(plan: Plan,ctx: dict[str, Any],e: dict[str, Any]) -> bool:
    from app.rules import this_way
    from app.rules.triggers import _snapshot_card

    kind,bind = e['kind'],e['binding'].removeprefix(context.PREFIX)
    if kind == 'transmute':
        pairs = this_way._matched(plan,ctx,{'this_way':'sacrificed','ref_count':bind})
        if not pairs:
            return True
        old = pairs[0][1]
        snap = context.snapshot(plan,ObjectRef.model_validate(old))
        assert snap is not None
        _,ch = _snapshot_card(plan,snap)
        ctx.setdefault('controller_tutors',{})[bind]={'mv':ch.mana_value}
        return insert(ctx,[queries.search('artifact card',to='battlefield',capture_only=True,shuffle=False,outcome=e['binding']),
                           {'do':'controller_tutor_transmute','binding':e['binding']}])
    counts: dict[str, int]
    if kind == 'balance':
        counts = {p:max(0,5-len(_lands(plan,p))) for p in plan.apnap() if len(_lands(plan,p))<=4}
    else:
        counts = {}
        verb = 'sacrificed' if kind == 'vitriol' else 'destroyed'
        for _,was in this_way._matched(plan,ctx,{'this_way':verb,'ref_count':bind}):
            snap = context.snapshot(plan,ObjectRef.model_validate(was))
            if snap is None:
                continue
            card,ch = _snapshot_card(plan,snap)
            if 'Land' in ch.types:
                counts[card.controller]=counts.get(card.controller,0)+1
    ctx.setdefault('controller_tutors',{})[bind]={'players':[p for p in plan.apnap() if counts.get(p,0)],
                                               'counts':counts,'searched':[],'kind':kind}
    return next_player(plan,ctx,e)


def next_player(plan: Plan,ctx: dict[str, Any],e: dict[str, Any]) -> bool:
    bind = e['binding'].removeprefix(context.PREFIX)
    state = ctx['controller_tutors'][bind]
    if not state['players']:
        return insert(ctx,[{'do':'shuffle_library','who':f'player:{p}','zones':[]} for p in state['searched']])
    pid = state['players'].pop(0)
    state['current']=pid
    ctx['search_performed']=False
    n = 3 if state['kind']=='druid' else state['counts'][pid]
    search=queries.search('basic land card',to='battlefield_tapped' if state['kind'] in ('druid','buzzcrusher','vitriol') else 'battlefield',
                          max=n,upto=True,may=True,shuffle=False)
    if state['kind']=='druid':
        search.update(partition={'n':1,'player':state['original'],'rest_to':'battlefield_tapped'})
        search['to']='hand'
    return insert(ctx,[*_search_as(pid,search),{'do':'controller_tutor_searched','binding':e['binding']}])


def searched(plan: Plan,ctx: dict[str, Any],e: dict[str, Any]) -> bool:
    state=ctx['controller_tutors'][e['binding'].removeprefix(context.PREFIX)]
    if ctx.get('search_performed'):
        state['searched'].append(state['current'])
    return next_player(plan,ctx,e)


def transmute(plan: Plan,ctx: dict[str, Any],e: dict[str, Any]) -> bool:
    bind=e['binding'].removeprefix(context.PREFIX)
    found=context.objects(plan,ctx,bind)
    if not found:
        return insert(ctx,[{'do':'shuffle_library','who':'you','zones':[]}])
    cid=found[0]
    n=max(0,int(plan.ch(plan.state.cards[cid]).mana_value-ctx['controller_tutors'][bind]['mv']))
    move={'do':'return_card','who':e['binding'],'to':'battlefield'}
    tail=[{'do':'shuffle_library','who':'you','zones':[]}]
    if not n:
        return insert(ctx,[move,*tail])
    return insert(ctx,[{'do':'optional_payment','who':'you','cost':f'{{{n}}}','bind':bind+'_paid'},
                       {'do':'only_if','cond':{'succeeded':bind+'_paid'},'skip':1},move,
                       {'do':'only_if','cond':{'succeeded':bind+'_paid','negate':True},'skip':1},
                       {'do':'return_card','who':e['binding'],'to':'graveyard'},*tail])


PRIMITIVES={'controller_tutor':prepare,'controller_tutor_after':after,'controller_tutor_searched':searched,'controller_tutor_transmute':transmute}
RESUME={'controller_tutor_lands':resume_lands}


def activation_kind(ch: Any, text: str) -> str | None:
    from app.rules import graveyard_keywords

    for ab in ch.abilities:
        generated = graveyard_keywords.ability(ch, ab.index)
        if generated is not None and generated.text == text:
            found = graveyard_keywords.parse(ab.text)
            if found is not None:
                return found[0]
    return None
