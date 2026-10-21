"""Native immediate effects and chosen production bodies of activated mana abilities."""
from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules import mana as M
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


def beneficiary_spec(text: str) -> tuple[str, tuple[str, ...] | None, int] | None:
    if ': ' not in text:
        return None
    cost, body = text.split(': ', 1)
    fixed = re.fullmatch(r'A player of your choice adds (?P<mana>(?:\{[WUBRGC]\})+)\.', body)
    chosen = re.fullmatch(r'Choose a player\. That player adds (?P<mana>(?:\{[WUBRGC]\})+)\.', body)
    if fixed or chosen:
        match = fixed or chosen
        assert match is not None
        return cost, tuple(re.findall(r'\{([WUBRGC])\}', match['mana'])), 0
    if body == 'Choose a player. That player adds one mana of any color they choose.':
        return cost, None, 1
    return None


def parse(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    from app.rules import mana as M
    from app.rules import scripts
    own=scripts.self_text(text,name) if name else text
    if (benefit := beneficiary_spec(own)) is not None:
        cost, output, n = benefit
        base = M.parse_mana_ability(cost + ': Add {C}.', identity, card_name=name)
        if base is None:
            return None
        add = {'do': 'immediate_mana_production', 'who': 'ref:mana_recipient',
               **({'mana': list(output)} if output is not None else {'of': list(M.COLORS), 'n': n})}
        return replace(base, chooses=True, native_body=True,
                       options=(output,) if output is not None else tuple((c,) for c in M.COLORS),
                       immediate_effects=({'do': 'choose_value', 'who': 'you', 'what': 'player', 'as': 'mana_recipient'}, add))
    if own == '{T}, Sacrifice X Goats: Add X mana of any one color. You gain X life.':
        return M.ManaAbility(tap=True,sacrifice_self=False,options=tuple((c,) for c in M.COLORS),
                             extra_cost='Sacrifice X Goats',chooses=True,count='paid_sacrifice_count',
                             immediate_effects=({'do':'gain_life','who':'you','n':{'x':1}},))
    first,sep,tail=own.partition('. ')
    if not sep or ': Add ' not in first:
        return None
    effect_text=tail
    restriction=''
    if ' Activate ' in effect_text:
        effect_text,restriction=effect_text.split(' Activate ',1)
        restriction=' Activate '+restriction
    allowed=(effect_text=='Each player loses 1 life.' or
             bool(re.fullmatch(r'~ deals 1 damage to you if you don\'t control an Ogre\.',effect_text)) or
             effect_text in ('This creature becomes that color until end of turn.','~ becomes that color until end of turn.') or
             effect_text=='Put an unlock counter on ~.' or
             bool(re.fullmatch(r'If this ability has been activated four or more times this turn, sacrifice (?:~|this creature) at the beginning of the next end step\.',effect_text)))
    if not allowed:
        return None
    base=M.parse_mana_ability(first+'.'+restriction,identity,card_name=name)
    if base is None:
        return None
    if 'becomes that color' in effect_text:
        es=[{'do':'immediate_mana_color'}]
    else:
        got=scripts.parse_effects(effect_text)
        if got is None or got[1] is not None or got[2]:
            return None
        es=got[0]
    return replace(base,immediate_effects=tuple(es))


def run(plan: Plan, card: CardInstance, index: int, ability: M.ManaAbility, player: str,
        oid: str, option: tuple[str, ...], then: dict[str, Any] | None,
        mana_context: dict[str, Any] | None = None) -> bool:
    from app.rules import effects, history
    from app.rules import payment_continuations as pc
    data=copy.deepcopy(list(ability.immediate_effects))
    data=history.counting_activations(data,f'{oid}:{index}')
    ctx: dict[str, Any]={'kind':'mana','controller':player,'source_card':card.id,'source_object':oid,
                         'borrowed_link_scope': ability.borrowed_link_scope,
                         'name':card.name,'effects':data,'next':0,'mana_option':list(option),
                         'targets':[],'stack_id':None,'event':None,'x':0,
                         'mana_context':mana_context or {},'mana_index':index,'mana_tap':ability.tap,
                         'mana_source_snapshot':(mana_context or {}).get('source_snapshot') or card.model_dump(mode='json'),
                         'body_done':{'do':'immediate_mana_done','then':then,
                                      'frame':pc._RIDER.dump_python(pc.ManaRiderFrame(
                                          card.model_dump(mode='json'),oid,player,list(ability.riders),
                                          then or {'do':'immediate_mana_noop'},plan.actor,plan.reserved_life),mode='json')}}
    if mana_context is not None and mana_context.get('x') is not None:
        ctx['x']=mana_context['x']
    effects.continue_effects(plan,ctx)
    # This native body owns its terminal, including synchronous completion.
    return False


def done(plan: Plan, then: dict[str, Any]) -> None:
    from app.rules import replace as replacements
    replacements.run_then(plan,{'do':'mana_riders','frame':then['frame']})


def color(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    option=ctx.get('mana_option') or []
    if option:
        effects.PRIMITIVES['become'](plan,ctx,{'do':'become','who':'self','types':[],
                                             'colors':[option[0]],'duration':'end_of_turn'})
    return True


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts
    text=scripts.self_text(ability.text,ch.name)
    if ability.kind == 'triggered' and text == 'When ~ enters, choose a player. That player adds two mana of any one color they choose.':
        return scripts.define(replace(ability, text=text.replace(' any one color they choose.', ' any one color.')), ch)
    if ability.kind == 'activated' and text == '{T}, Sacrifice one or more artifacts: Choose a color. Target player adds three mana of the chosen color for each artifact sacrificed this way.':
        base = scripts.define(replace(ability, text='{T}, Sacrifice one or more artifacts: Target player adds three mana of any one color.'), ch)
        if base is not None:
            base['effects'] = [{'do': 'choose_value', 'who': 'you', 'what': 'color', 'as': 'radiant_mana_color'},
                               {'do': 'paid_artifact_mana', 'ref': 'radiant_mana_color'}]
        return base
    if ability.kind=='triggered' and text=='At the beginning of your upkeep, if each player has 10 or less life, transform ~.':
        base=scripts.define(replace(ability,text='At the beginning of your upkeep, transform ~.'),ch)
        assert base is not None
        condition={'as':'any','every':True,'cond':{'value':{'life':'you'},'op':'<=','n':10}}
        return {**base,'if':condition,'effects':[{'do':'only_if','cond':condition,'skip':1},*base['effects']]}
    return None


PRIMITIVES={'immediate_mana_color':color}


def noop(plan: Plan, then: dict[str, Any]) -> None:
    pass


from app.rules import replace as _replace  # noqa: E402, I001

_replace.THEN['immediate_mana_done']=done
_replace.THEN['immediate_mana_noop']=noop


def production(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide
    recipients = effects._players(plan, ctx, e['who'])
    if not recipients:
        return True
    if 'mana' in e:
        produce_chosen(plan, ctx, recipients[0], e['mana'])
    else:
        decide(plan, player=recipients[0], kind='choose_one', prompt='Choose the mana to add',
               options=[DecisionOption(id=c, label='{'+c+'}') for c in e['of']],
               resume={'step':'immediate_mana_production','ctx':ctx,'e':e,'player':recipients[0]})
    return False


def produce_chosen(plan: Plan, ctx: dict[str, Any], recipient: str, option: list[str]) -> None:
    from app.game.state import CardInstance
    from app.rules import mana_replace, reveal_mana
    card = CardInstance.model_validate(ctx['mana_source_snapshot'])
    data = {'source': ctx['mana_source_snapshot'], 'oid':ctx['source_object'], 'controller':ctx['controller'],
            'beneficiary':recipient,'index':ctx['mana_index'],'option':option,
            'mana_context': {**ctx['mana_context'], 'source_card':card.id,'source_object':ctx['source_object']},
            'tap':ctx['mana_tap'],'then':{'do':'continue','ctx':ctx},
            'replacements':[d for owner,d in mana_replace._statics(plan.state,plan.info)
                            if ctx['mana_tap'] and mana_replace._applies(plan.state,plan.info,card,owner,d)]}
    reveal_mana._replace(plan,data)


def resume_production(plan: Plan, d: Any, chosen: list[str]) -> None:
    r=d.resume
    produce_chosen(plan,r['ctx'],r['player'],[chosen[0]]*r['e']['n'])


def paid_artifact_mana(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context
    stack_id=ctx.get('stack_id')
    record=plan.rules.payments.get(plan.oid(stack_id)) if stack_id in plan.state.cards else None
    value=context.refs(ctx).get(e['ref'],{}).get('value')
    sym={'White':'W','Blue':'U','Black':'B','Red':'R','Green':'G'}.get(value or '')
    if record is not None and sym is not None:
        n=len(record.sacrificed_objects)*3
        i=ctx['next']
        ctx['effects'][i:i]=[{'do':'add_mana','who':'target','sym':sym,'n':n}]
    return True


PRIMITIVES.update({'immediate_mana_production':production,'paid_artifact_mana':paid_artifact_mana})
RESUME={'immediate_mana_production':resume_production}
