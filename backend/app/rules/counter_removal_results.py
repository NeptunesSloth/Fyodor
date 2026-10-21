"""Actual counter-removal quantities feed ordinary native resolution effects."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language, scripts, selectors

    body = body.strip()
    text = (body[:1].upper() + body[1:]).rstrip('.')
    binding = 'removed_counters'
    amount = {'ref_amount':binding}
    if text == 'Remove all counters from all permanents and exile all tokens':
        sel = selectors.Selector().key()
        return ([{'do':'remove_counters', 'who':sel, 'kind':'*', 'n':{'counters_among':None, 'of':sel}},
                 {'do':'exile', 'who':selectors.Selector(token=True).key()}], None, False)
    take = re.fullmatch(r'Remove all \+1/\+1 counters from (?P<who>target creature you control)\. Draw that many cards', text)
    if take is not None:
        return ([{'do':'remove_counters', 'who':'target', 'kind':'+1/+1', 'n':{'counters':'+1/+1', 'on':'target'}, 'bind':binding},
                 {'do':'draw', 'who':'you', 'n':amount}], language._target_key(take['who']), False)
    parasite = re.fullmatch(r'Remove up to X counters from target permanent\. For each counter removed this way, ~ gets \+1/\+0 until end of turn', text)
    if parasite is not None:
        first = scripts.parse_effects('Remove up to X counters from target permanent.')
        assert first is not None
        return ([{**first[0][0], 'bind':binding, 'numeric':True}, {'do':'pump', 'who':'self', 'p':amount, 't':0}], first[1], False)
    if text == 'Remove up to five counters from target artifact, creature, planeswalker, or opponent':
        return ([{'do':'remove_any_counters', 'who':'target', 'n':5, 'upto':True, 'numeric':True}],
                'artifact_creature_planeswalker_or_opponent', False)
    cultist = re.fullmatch(r'Remove all counters from up to one target permanent or opponent\. The next spell you cast this turn costs \{1\} less to cast for each counter removed this way', text)
    if cultist is not None:
        return ([{'do':'remove_any_counters', 'who':'target', 'all':True, 'bind':binding},
                 {'do':'next_spell_grant', 'grants':[{'keyword':'cost', 'n':amount, 'filter':None}]}],
                [{'what':'permanent_or_opponent', 'min':0, 'max':1}], False)
    return None


def remove(plan: Plan, obj: str, kind: str, n: int, *, by: str) -> int:
    """Use native counter actions without treating their manual-input bounds as an all-removal cap."""
    from app.rules import prohibitions

    if prohibitions.cant_remove_counters(plan, obj, kind):
        return 0
    card = plan.state.cards.get(obj)
    player = obj in plan.state.players and obj in plan.live()
    if card is None and not player:
        return 0
    have = (card.counters if card is not None else plan.state.players[obj].resources).get(kind, 0)
    actual = min(max(0, n), max(0, have))
    left = have - actual
    if not actual:
        return 0
    if card is not None:
        if actual > 1000 and left <= 100000:
            plan.do({'type':'set_counter', 'card_id':obj, 'kind':kind, 'value':left}, actor=by)
        else:
            remaining = actual
            while remaining:
                chunk = min(remaining, 1000)
                plan.do({'type':'counter', 'card_ids':[obj], 'kind':kind, 'delta':-chunk}, actor=by)
                remaining -= chunk
    elif actual > 100000 and left <= 100000:
        plan.do({'type':'set_resource', 'player':obj, 'key':kind, 'value':left}, actor=by)
    else:
        remaining = actual
        while remaining:
            chunk = min(remaining, 100000)
            plan.do({'type':'resource', 'player':obj, 'key':kind, 'delta':-chunk}, actor=by)
            remaining -= chunk
    return actual
