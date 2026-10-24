"""Resolution-time creature choices compose the native public group-choice pipeline."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP='creature_choice_setup'


def key(text: str) -> str:
    from app.rules import selectors
    parsed=selectors.parse(text)
    assert parsed is not None,text
    return parsed.key()


def choose(sel: str='creature', **flags: Any) -> dict[str, Any]:
    return {'do':'player_chooses','who':'you','sel':key(sel),'n':1,'label':sel,**flags}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts
    text=body.strip()
    text=text[:1].upper()+text[1:]
    if text=='Choose up to one creature. Destroy the rest.':
        return ([choose(any=True,upto=True,optional=True,rest='destroy')],None,False)
    if text=='For each opponent, choose a creature with the greatest power among creatures that player controls. Destroy those creatures.':
        return ([choose(who='each_opponent',by='you',greatest_power=True,**{'as':'choice_group'}),
                 {'do':'destroy','who':'ref:choice_group'}],None,False)
    if text in ('Choose any number of creatures with different powers. Those creatures gain double strike until end of turn.',
                "Choose any number of creatures with different powers. Each of them gets +X/+X and gains vigilance until end of turn, where X is ~'s power."):
        action=({'do':'grant','who':'ref:choice_group','keywords':['double strike']} if 'double strike' in text else
                {'do':'pump','who':'ref:choice_group','p':{'power':'self'},'t':{'power':'self'}})
        actions=[action] if 'double strike' in text else [action,{'do':'grant','who':'ref:choice_group','keywords':['vigilance']}]
        return ([{'do':STEP,'mode':'distinct'},*actions],None,False)
    if text=='For each different power among creatures on the battlefield, choose a creature with that power. Destroy each creature not chosen this way.':
        return ([{'do':STEP,'mode':'partition'}],None,False)
    if text=='Choose a creature card with mana value 1 in your graveyard, then do the same for creature cards with mana value 2 and 3. Return those cards to the battlefield.':
        sels=[key(f'creature card with mana value {n} in your graveyard') for n in (1,2,3)]
        return ([choose('creature card',zone='graveyard',sels=sels,**{'as':'choice_group'}),
                 {'do':'return_card','who':'ref:choice_group','to':'battlefield','under':'owner'}],None,False)
    if text=="Choose a creature card in an opponent's graveyard, then that player chooses a creature card in your graveyard. You may return those cards to the battlefield under their owners' control.":
        return ([choose("creature card in an opponent's graveyard",any=True,zone='graveyard',**{'as':'choice_first'}),
                 {'do':STEP,'mode':'reclaimer_second'},
                 {'do':STEP,'mode':'reclaimer_return'}],None,False)
    if text=='You may discard a card. If you do, choose a creature. Whenever that creature deals combat damage to a player this turn, you draw two cards.':
        parsed=scripts.parse_effects(text.replace('choose a creature.','choose a creature you control.'))
        assert parsed is not None
        es,target,may=parsed
        for e in es:
            if e['do']=='player_chooses':
                e['any']=True
        return es,target,may
    if text=="Choose a creature or planeswalker you control. All damage that would be dealt this turn to you and permanents you control is dealt to the chosen permanent instead.":
        return ([choose('creature or planeswalker you control',**{'as':'choice_group'}),
                 {'do':'redirect_damage','from':'you_perms','to':'ref:choice_group','limit':None}],None,False)
    if text=="Target attacking creature can't be blocked this turn. It connives. Then choose another attacking creature with lesser power. That creature gains double strike until end of turn.":
        parsed=scripts.parse_effects(text.replace('choose another attacking creature with lesser power.','choose an attacking creature you control.'))
        assert parsed is not None
        es,target,may=parsed
        es.insert(1,{'do':STEP,'mode':'capture','who':'target','as':'choice_first_attacker'})
        for e in es:
            if e['do']=='player_chooses':
                e.update(any=True,lesser_power_than='choice_first_attacker')
        return es,target,may
    if text=="For each player, you choose a creature that player controls. Then each player sacrifices all other creatures they control that don't share a creature type with the chosen creature they control.":
        return ([choose(who='each_player',by='you',rest='sacrifice',rest_not_shared=True)],None,False)
    return None


def candidates(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], cards: list[str]) -> list[str]:
    from app.rules import context, effects, sba
    if e.get('greatest_power') and cards:
        powers={cid:effects._power_of(plan,cid) for cid in cards}
        highest=max(powers.values())
        cards=[cid for cid in cards if powers[cid]==highest]
    if e.get('lesser_power_than'):
        binding=e['lesser_power_than']
        first=context.info(plan,ctx,binding)
        power=sba.power(*first) if first else None
        refs=context._object_refs(ctx,binding)
        original={ref.object_id for ref in refs}
        cards=[cid for cid in cards if power is not None and effects._power_of(plan,cid)<power and plan.oid(plan.state.cards[cid]) not in original]
    if e.get('distinct_names'):
        from app.rules.card_names import names_of
        cards = [cid for cid in cards if names_of(plan.ch(plan.state.cards[cid]))]
    if e.get('except_ref'):  # -- attached (wave 100F) -- "other than enchanted creature": not that object, bound as the ability resolves (608.2h; attached100f.bind_host)
        gone = {ref.object_id for ref in context._object_refs(ctx, e['except_ref'])}
        cards = [cid for cid in cards if plan.oid(plan.state.cards[cid]) not in gone]
    if e.get('exclude'):  # -- static spells (wave 100C) -- "sacrifices another land" (Feast of Worms): not the object the binding still names
        gone = set(context.objects(plan, ctx, e['exclude']))
        cards = [cid for cid in cards if cid not in gone]
    return cards


def validate(plan: Plan, e: dict[str, Any], chosen: list[str]) -> None:
    if e.get('distinct_names'):
        from app.game.errors import ActionError
        from app.rules.card_names import names_of
        names: set[str] = set()
        for cid in chosen:
            current = {n.casefold() for n in names_of(plan.ch(plan.state.cards[cid]))}
            if not current or names & current:
                raise ActionError('Choose tokens with different names')
            names |= current
    if e.get('distinct_power'):
        from app.game.errors import ActionError
        from app.rules import effects
        powers=[effects._power_of(plan,cid) for cid in chosen]
        if len(powers)!=len(set(powers)):
            raise ActionError('Choose creatures with different powers')


def rest(plan: Plan, e: dict[str, Any], cards: list[str], picked: list[str]) -> list[str]:
    if not e.get('rest_not_shared'):
        return cards
    from app.rules.creature_types import CREATURE_TYPES

    spared={plan.state.cards[cid].controller:plan.ch(plan.state.cards[cid]).subtypes & CREATURE_TYPES for cid in picked}
    return [cid for cid in cards if not (plan.ch(plan.state.cards[cid]).subtypes & spared.get(plan.state.cards[cid].controller,frozenset()))]


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, selectors
    mode=e['mode']
    if mode=='capture':
        context.bind_objects(plan,ctx,e['as'],effects._cards(plan,ctx,e['who']))
        return True
    if mode in ('distinct','partition'):
        creatures=selectors.candidates(plan,selectors.from_key(key('creature')),ctx['controller'],ctx.get('source_card'))
        if mode=='distinct':
            effect=choose(any=True,n=len(creatures),upto=True,optional=True,distinct_power=True,**{'as':'choice_group'})
        else:
            powers=sorted({effects._power_of(plan,cid) for cid in creatures})
            if not powers:
                return True
            sels=[key(f'creature with power {p}') for p in powers]
            effect=choose(any=True,sels=sels,rest='destroy')
        return effects.player_chooses(plan,ctx,effect)
    if mode=='reclaimer_second':
        first=context.objects(plan,ctx,'choice_first')
        tail:list[dict[str,Any]]=[]
        if first:
            context.bind_players(ctx,'choice_opponent',[plan.state.cards[first[0]].owner])
        else:
            tail.append({'do':'choose_opponent','as':'choice_opponent'})
        tail.append(choose('creature card in your graveyard',who='ref:choice_opponent',any=True,zone='graveyard',**{'as':'choice_second'}))
    elif mode=='reclaimer_return':
        chosen=[*context.objects(plan,ctx,'choice_first'),*context.objects(plan,ctx,'choice_second')]
        context.bind_objects(plan,ctx,'choice_group',chosen)
        tail=[{'do':'optional_payment','who':'you','cost':'','bind':'choice_return','ask':'return the chosen creatures'},
              {'do':'only_if','cond':{'succeeded':'choice_return'},'skip':1},
              {'do':'return_card','who':'ref:choice_group','to':'battlefield','under':'owner'}] if chosen else []
    else:
        raise AssertionError(mode)
    at=int(ctx.get('next') or 0)
    ctx['effects'][at:at]=tail
    return True


PRIMITIVES={STEP:run}
