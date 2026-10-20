"""Known cast-payment predicates for native self-entry counter replacements."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(text: str) -> dict[str, Any] | None:
    from app.rules.conditions import _num

    m=re.fullmatch(r"~ enters with (?P<n>\w+) \+1/\+1 counters? on it (?P<tail>.+)\.",text)
    if m is None or (n:=_num(m['n'])) is None:
        return None
    tail=m['tail']
    if (colors:=re.fullmatch(r'unless (?P<n>\w+) or more colors of mana were spent to cast it',tail)) is not None:
        limit=_num(colors['n'])
        if limit is None:
            return None
        condition={'colors_below':limit}
    elif tail=="if it wasn't cast or no mana was spent to cast it":
        condition={'uncast_or_free':True}
    else:
        return None
    return {'kind':'replacement','replacement':'enters_with_counters','counter':'+1/+1','n':n,
            'if_cast':{'entry_payment':condition},'effects':[]}


def holds(plan: Plan, ctx: dict[str, Any], need: dict[str, Any]) -> bool:
    record=plan.rules.payments.get(ctx.get('source_object') or '')
    if record is not None and not record.mana_known:
        plan.note('The mana paid for this manually cast spell is unknown; apply its conditional entry counters by hand.',
                  [record.card] if record.card in plan.state.cards else ())
        return False
    if 'uncast_or_free' in need:
        return record is None or record.cast_from is None or sum(record.mana_spent.values())==0
    return sum(record.mana_spent.get(c,0)>0 for c in 'WUBRG')<need['colors_below'] if record is not None else need['colors_below']>0


def normalize_targets(body: str) -> str | None:
    """Announce an up-to target group before distributing a payment-sized counter amount."""
    m=re.fullmatch(r'Choose (?P<targets>up to \w+ other target creatures you control)\. For each (?P<count>[^,.]+), put a (?P<counter>[+-]\d+/[+-]\d+) counter on each of them\.',body,re.IGNORECASE)
    if m is None:
        return None
    from app.rules import values

    count=values.parse_count(m['count'])
    if not isinstance(count,dict) or set(count)!={'mana_pairs'}:
        return None
    return f"Put a {m['counter']} counter on each of {m['targets']} for each {m['count']}."
