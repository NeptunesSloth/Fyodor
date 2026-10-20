"""Exact immediate bodies that still happen on unpreventable damage."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'prevention_unpreventable44'
ANGEL = 'If damage would be dealt to you, prevent that damage and mill twice that many cards.'
GATTA = ('When ~ enters, choose target creature you control. If damage would be dealt to that creature this turn, '
         'prevent that damage and put that many +1/+1 counters on it.')
QUOTE = ('If this creature would deal combat damage to a player, prevent that damage. '
         "This creature's controller and that player each draw half that many cards, rounded down.")


def _text(text: str, name: str) -> str:
    from app.rules import scripts

    return scripts.self_text(text, name).replace('this creature', '~').replace('This creature', '~').replace('this permanent', '~').replace('This permanent', '~')


def _quoted_definition() -> dict[str, Any]:
    return {'kind': 'static', 'static': 'replace', 'event': 'damage',
            'match': {'combat': True, 'source': {'self': True}, 'to': {'players': 'any'}},
            'op': {'do': 'prevent_all', 'prevention': True, 'rider': {
                'aggregation': 'batch', 'effects': [{'do': 'draw', 'who': 'ref:to', 'also': 'ref:from_ctrl',
                                                    'n': {'half': {'ref_amount': 'that_damage'}, 'round': 'down'}}]}},
            'effects': []}


def supported_quote(text: str, definition: dict[str, Any]) -> bool:
    return _text(text, '\0') == _text(QUOTE, '\0') and definition == _quoted_definition()


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import selectors

    text = _text(ability.text, ch.name)
    if ability.kind == 'static' and text == ANGEL:
        return {'kind': 'static', 'static': 'replace', 'event': 'damage',
                'match': {'to': {'players': 'you'}},
                'op': {'do': 'prevent_all', 'prevention': True, 'rider': {
                    'aggregation': 'batch', 'effects': [{'do': 'mill', 'who': 'you',
                                                        'n': {'times': [2, {'ref_amount': 'that_damage'}]}}]}},
                'effects': []}
    if ability.kind == 'triggered' and text == GATTA:
        return {'kind': 'triggered', 'trigger': 'enters_self',
                'target': {'what': selectors.Selector(types=('Creature',), controller='you').key()},
                'effects': [{'do': STEP, 'mode': 'gatta'}]}
    if ability.kind == 'static' and text == _text(QUOTE, '\0'):
        return _quoted_definition()
    if ability.kind == 'activated':
        body = text.partition(':')[2].strip()
        if body == f'Until end of turn, target creature gains "{QUOTE}"' or body == f'Until end of turn, target creature gains "{QUOTE}".':
            return {'kind': 'activated', 'target': {'what': 'creature'},
                    'effects': [{'do': 'grant', 'who': 'target', 'keywords': [],
                                 'abilities': [QUOTE], 'duration': 'end_of_turn'}]}
        # _text normalizes the quoted creature references as well as the holder.
        raw = ability.text.partition(':')[2].strip()
        if raw.rstrip('.') == f'Until end of turn, target creature gains "{QUOTE}"':
            return {'kind': 'activated', 'target': {'what': 'creature'},
                    'effects': [{'do': 'grant', 'who': 'target', 'keywords': [],
                                 'abilities': [QUOTE], 'duration': 'end_of_turn'}]}
    return None


def run(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, prevention_outcomes, replace

    if effect.get('mode') != 'gatta':
        raise ValueError('Unknown unconditional prevention body')
    targets = effects._cards(plan, ctx, 'target')
    if not targets:
        return True
    rider = prevention_outcomes._rider(ctx, [{'do': 'add_counters', 'who': 'ref:to', 'kind': '+1/+1',
                                             'n': {'ref_amount': 'that_damage'}}])
    rider['if'] = False
    replace.add_record(plan, controller=ctx['controller'], label=ctx.get('name') or 'Gatta and Luzzu', event='damage',
                       source=ctx.get('source_object'), source_card=ctx.get('source_card'),
                       match={'to': {'objects': {'oids': [plan.oid(targets[0])]}}},
                       op={'do': 'prevent_all', 'prevention': True, 'consume_unpreventable': True, 'rider': rider}, until='eot')
    return True


PRIMITIVES = {STEP: run}
