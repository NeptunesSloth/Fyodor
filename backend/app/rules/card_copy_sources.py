"""Exact original-card selection followed by native 707.12 copy/cast continuations."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

ORIGINAL = 'card_copy_originals'
COPIES = 'card_copy_results'


def key(text: str) -> str:
    from app.rules import selectors

    sel = selectors.parse(text)
    assert sel is not None, text
    return sel.key()


def select(*, who: str | None = None, sel: str | None = None, n: Any = 1, **kw: Any) -> dict[str, Any]:
    return {'do': 'select_copy_originals', 'n': n, 'as': ORIGINAL,
            **({'who': who} if who else {}), **({'sel': sel} if sel else {}), **kw}


def copy_cast(*, paid: bool = False, fixed: str | None = None, required: bool = False) -> list[dict[str, Any]]:
    return [{'do': 'copy_cards', 'who': 'ref:' + ORIGINAL, 'as': COPIES, 'source_zone': 'exile'},
            {'do': 'free_cast', 'zone': 'that', 'who': 'ref:' + COPIES, 'exact_refs': True,
             'all': True, 'n': 1, 'optional': not required, 'required': required,
             **({'paid': True} if paid or fixed is not None else {}),
             **({'effect_mana_cost': fixed} if fixed is not None else {})}]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    t = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    if t == 'you may exile an instant or sorcery card with mana value x from your hand':
        return [select(sel=key('instant or sorcery card in your hand'), upto=True, mv={'x': 1}),
                {'do': 'exile', 'who': 'ref:' + ORIGINAL, 'as': ORIGINAL, 'link': True}], None, False
    if t == 'you may copy a card exiled with ~. if you do, you may cast the copy without paying its mana cost':
        return [select(who='exiled_with', upto=True), *copy_cast()], None, False
    if t == 'copy each exiled card you own with a kick counter on it. you may cast the copies':
        return [select(sel=key('card you own in exile with a kick counter on it'), n='all'), *copy_cast(paid=True)], None, False
    if t == "exile target instant or sorcery card from your graveyard and target instant or sorcery card from an opponent's graveyard. copy those cards. cast the copies if able without paying their mana costs. exile ~":
        found = scripts.parse_effects("Exile target instant or sorcery card from your graveyard and target instant or sorcery card from an opponent's graveyard.")
        assert found is not None
        return ([{**found[0][0], 'as': 'spelltwine_first'}, {**found[0][1], 'as': 'spelltwine_second'},
                 {'do': 'merge_copy_originals', 'who': 'ref:spelltwine_first', 'with': 'ref:spelltwine_second', 'as': ORIGINAL},
                 *copy_cast(required=True), {'do': 'exile', 'who': 'self'}], found[1], False)
    if t == 'exile three cards at random from your graveyard. choose a noncreature, nonland card from among them and copy it. you may cast the copy without paying its mana cost':
        return [select(sel=key('card in your graveyard'), n=3, random=True),
                {'do': 'exile', 'who': 'ref:' + ORIGINAL, 'as': ORIGINAL},
                select(who='ref:' + ORIGINAL, filter=key('noncreature nonland card')), *copy_cast()], None, False
    if t == 'choose a player at random. that player exiles an instant or sorcery card from their graveyard. copy that card. you may cast the copy without paying its mana cost':
        return [{'do': 'choose_random', 'pool': 'player', 'as': 'copy_random_player'},
                select(sel=key('instant or sorcery card in your graveyard'), player='ref:copy_random_player'),
                {'do': 'exile', 'who': 'ref:' + ORIGINAL, 'as': ORIGINAL}, *copy_cast()], None, False
    if t == "exile it. then that player copies each instant or sorcery card exiled with ~. for each copy, the player may cast the copy without paying its mana cost":
        return [{'do': 'exile', 'who': 'event_spell', 'link': True}, {'do': 'copy_resolution_player'},
                select(who='exiled_with:' + key('instant or sorcery card'), n='all'), *copy_cast()], None, False
    if t == ("exile target instant or sorcery card from a graveyard. roll a d20. "
             "1—9 | copy that card. you may cast the copy. "
             "10—19 | copy that card. you may cast the copy by paying {1} rather than paying its mana cost. "
             "20 | copy each card exiled with ~. you may cast any number of the copies without paying their mana costs"):
        from app.rules import dice

        target = key('instant or sorcery card in a graveyard')
        out = [{'do': 'exile', 'who': 'target', 'as': ORIGINAL, 'link': True}, {'do': 'roll', 'sides': 20, 'count': 1}]
        for lo, hi, row in [(1, 9, copy_cast(paid=True)), (10, 19, copy_cast(fixed='{1}')),
                            (20, 20, [select(who='exiled_with', n='all'), *copy_cast()])]:
            cond = dice.condition(f'the result is {lo} to {hi}')
            assert cond is not None
            out += [{'do': 'only_if', 'cond': cond, 'skip': len(row)}, *row]
        return out, {'what': target}, False
    if t == 'copy that card. you may cast the copy':
        return [{'do': 'copy_cards', 'who': 'it:card', 'as': COPIES, 'source_zone': 'exile'}, copy_cast(paid=True)[1]], None, False
    if t == 'copy that card. you may cast the copy by paying {1} rather than paying its mana cost':
        return [{'do': 'copy_cards', 'who': 'it:card', 'as': COPIES, 'source_zone': 'exile'}, copy_cast(fixed='{1}')[1]], None, False
    if t == 'copy each card exiled with ~. you may cast any number of the copies without paying their mana costs':
        return [select(who='exiled_with', n='all'), *copy_cast()], None, False
    if t == 'exile up to one target assassin card or card with freerunning from your graveyard. if you do, copy it. you may cast the copy':
        left = key('Assassin card in your graveyard')
        right = selectors.Selector(card=True, zones=('graveyard',), zone_owner='you', with_keywords=('freerunning',)).key()
        group = {'what': selectors.Selector(card=True, zones=('graveyard',), zone_owner='you', either=(left, right)).key(), 'min': 0, 'max': 1}
        return [{'do': 'exile', 'who': 'target', 'as': ORIGINAL}, *copy_cast(paid=True)], [group], False
    if t == "exile up to one target instant or sorcery card from defending player's graveyard. if you do, copy it. you may cast the copy by paying {3} rather than paying its mana cost":
        group = {'what': selectors.Selector(card=True, zones=('graveyard',), zone_owner=selectors.DEFENDED,
                                           types=('Instant', 'Sorcery')).key(), 'min': 0, 'max': 1}
        return [{'do': 'exile', 'who': 'target', 'as': ORIGINAL}, *copy_cast(fixed='{3}')], [group], False
    if t == "exile target instant or sorcery card from your graveyard. creatures you control get +x/+0 until end of turn, where x is that card's mana value. whenever a creature you control deals combat damage to a player this turn, copy the exiled card. you may cast the copy without paying its mana cost":
        found = scripts.parse_effects('Exile target instant or sorcery card from your graveyard.')
        assert found is not None
        from app.rules import delayed, events

        cond = events.parse_condition('a creature you control deals combat damage to a player')
        assert cond is not None
        watched = delayed.wrap_when(copy_cast(), {'kind': 'watch', 'cond': cond, 'text': 'a creature you control deals combat damage to a player'}, this_turn=True)
        watched[0]['once'] = False
        return [{**found[0][0], 'as': ORIGINAL},
                {'do': 'pump', 'who': key('creature you control'), 'p': {'mana_value': 'ref:' + ORIGINAL}, 't': 0}, *watched], found[1], False
    return None


def definition(text: str, kind: str) -> dict[str, Any] | None:
    from app.rules import events

    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    if kind == 'activated' and t.startswith('{t}: exile target instant or sorcery card from a graveyard. roll a d20. ') and t.endswith(' activate only as a sorcery'):
        got = parse(text.split(': ', 1)[1].removesuffix(' Activate only as a sorcery.'))
        if got is not None:
            return {'kind': 'activated', 'cost': '{T}', 'effects': got[0], 'target': got[1],
                    'restriction': [{'kind': 'sorcery'}], 'accumulating_link': True}
    if kind == 'triggered' and t == 'whenever a player casts an instant or sorcery card, exile it. then that player copies each instant or sorcery card exiled with ~. for each copy, the player may cast the copy without paying its mana cost':
        cond = events.parse_condition('a player casts a nontoken instant or sorcery spell')
        got = parse('Exile it. Then that player copies each instant or sorcery card exiled with ~. For each copy, the player may cast the copy without paying its mana cost.')
        assert cond is not None and got is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'effects': got[0], 'target': None,
                'optional': False, 'accumulating_link': True}
    return None


def _pool(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], player: str) -> list[str]:
    from app.rules import effects, selectors, values

    pool = (effects._cards(plan, ctx, e['who']) if e.get('who') else
            selectors.candidates(plan, selectors.from_key(e['sel']), player, ctx.get('source_card')))
    if e.get('filter'):
        sel = selectors.from_key(e['filter'])
        pool = [cid for cid in pool if selectors.matches(plan, sel, plan.state.cards[cid], plan.ch(plan.state.cards[cid]), player, ctx.get('source_card'))]
    if e.get('mv') is not None:
        mv = values.evaluate(plan, ctx, e['mv'])
        pool = [cid for cid in pool if plan.ch(plan.state.cards[cid]).mana_value == mv]
    return sorted(set(pool))


def select_originals(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import effects, selectors, values
    from app.rules.plan import decide

    players = effects._players(plan, ctx, e.get('player', 'you'))
    if not players:
        return effects._return_cards(plan, ctx, {**e, 'to': 'choose'}, [])
    player = players[0]
    pool = _pool(plan, ctx, e, player)
    want = len(pool) if e['n'] == 'all' else max(0, values.evaluate(plan, ctx, e['n']))
    most = min(want, len(pool))
    if e.get('random'):
        return effects._return_cards(plan, ctx, {**e, 'to': 'choose'}, (plan.rng or secrets.SystemRandom()).sample(pool, most))
    hidden = e.get('sel') and 'hand' in selectors.from_key(e['sel']).zones and bool(plan.state.zones.get(f'{player}:hand'))
    if not hidden and (most == 0 or (most == len(pool) and not e.get('upto'))):
        return effects._return_cards(plan, ctx, {**e, 'to': 'choose'}, pool[:most])
    decide(plan, player=player, kind='choose_cards', prompt=e.get('prompt', 'Choose original cards to copy') + (' (or none)' if e.get('upto') else ''),
           options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Card', card_id=cid) for cid in pool],
           min_choices=0 if e.get('upto') else most, max_choices=max(most, 1) if hidden else most,
           resume={'step': 'select_copy_originals', 'ctx': ctx, 'e': e,
                   'objects': {cid: plan.oid(plan.state.cards[cid]) for cid in pool}})
    return False


def resume_select(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume['ctx'], d.resume['e']
    pool = set(_pool(plan, ctx, e, d.player))
    selected = [cid for cid in chosen if cid in pool and plan.oid(plan.state.cards[cid]) == d.resume['objects'].get(cid)]
    if effects._return_cards(plan, ctx, {**e, 'to': 'choose'}, selected):
        effects.continue_effects(plan, ctx)


def merge(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    context.bind_objects(plan, ctx, e['as'], list(dict.fromkeys(effects._cards(plan, ctx, e['who']) + effects._cards(plan, ctx, e['with']))))
    return True


def resolution_player(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    players = effects._players(plan, ctx, 'event_player')
    if players:
        ctx['controller'] = players[0]
    else:
        ctx['next'] = len(ctx['effects'])
    return True



PRIMITIVES = {'select_copy_originals': select_originals, 'merge_copy_originals': merge,
              'copy_resolution_player': resolution_player}
RESUME = {'select_copy_originals': resume_select}
