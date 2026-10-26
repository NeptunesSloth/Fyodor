"""Generic-origin X payments restricted by mana color, without changing mana symbols."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.rules import mana as M

_WORDING = re.compile(r'Spend only (?P<colors>black|red|white|blue|green|black and/or red) mana on X\.', re.IGNORECASE)
_COLORS = {'black':'B','red':'R','white':'W','blue':'U','green':'G'}


# -- wave 110J -- Emblazoned Golem: 601.2h / 609.4b a restriction on how the mana for X is spent; no more than one mana of each color, so the rows are "distinct"
# (mana_allocation_masks) and colored only (no helper pseudo-units: nothing but mana pays X).
DISTINCT = "Spend only colored mana on X. No more than one mana of each color may be spent this way."


def colors(text: str) -> tuple[str, ...]:
    found = set()
    for sentence in re.findall(r'Spend only [^.]+\.', text, re.IGNORECASE):
        if (match := _WORDING.fullmatch(sentence.strip())) is not None:
            found.add(match['colors'].lower())
    if len(found) != 1:
        return ()
    return tuple(_COLORS[c] for c in next(iter(found)).split(' and/or '))


def strip(body: str) -> str | None:
    if not colors(body):
        return None
    return _WORDING.sub('', body).strip()


def definition(text: str) -> dict[str, Any] | None:
    if text.strip().rstrip('.').lower() == DISTINCT.rstrip('.').lower():
        return {'kind': 'static', 'static': 'x_mana_restriction', 'colors': list(M.COLORS), 'distinct': True, 'effects': []}
    allowed = colors(text.rstrip('.')+'.')
    return {'kind':'static','static':'x_mana_restriction','colors':list(allowed),'effects':[]} if allowed and _WORDING.fullmatch(text.rstrip('.')+'.') else None


def metadata(text: str, x: int, reduction: int, cost: M.ManaCost, *, mode: str | None = None,
             locked: dict[str, Any] | None = None, maximum: int | None = None) -> dict[str, Any] | None:
    if locked is not None:
        return locked
    if DISTINCT in text:
        return {'colors': list(M.COLORS), 'n': min(cost.generic, max(0, x-reduction)), 'generic': cost.generic, 'max': min(x, cost.generic if maximum is None else maximum),
                'distinct': True, 'attribute_black': False}
    allowed = colors(text)
    n = min(cost.generic, max(0, x-reduction))
    if not allowed:
        return None
    return {'colors':list(M.ALL_MANA if mode in ('color','type') else allowed), 'n':n, 'generic':cost.generic,
            'max':min(x, cost.generic if maximum is None else maximum),
            'attribute_black':bool(re.search(r'amount of \{B\} spent on X', text, re.IGNORECASE))}


def solver_cost(cost: M.ManaCost, data: dict[str, Any] | None) -> M.ManaCost:
    if not data:
        return cost
    from app.rules import mana_allocation_masks as allocation

    rows = allocation.requirements(cost)
    # Helpers pay generic costs without spending mana; their internal pseudo-unit is "1".
    # Contributions already assigned to generic costs can pay restricted X first.
    n = max(0, int(data['n'])-max(0,int(data['generic'])-cost.generic))
    n = min(n,cost.generic)
    if data.get('distinct'):
        typed = allocation.constrain_generic(rows, (tuple(data['colors']),) * n)
        flagged = typed.symbols[:len(typed.symbols) - n] + tuple(replace(r, distinct=True) for r in typed.symbols[len(typed.symbols) - n:])
        return replace(cost, generic=cost.generic-n, hybrid=cost.hybrid+(tuple(data['colors']),) * n,
                       allocation=replace(typed, symbols=flagged))
    if data.get('black') is not None:
        black = int(data['black'])
        maximum = min(int(data.get('max', data['generic'])), cost.generic)
        if not 0 <= black <= maximum:
            raise M.ManaError('That amount of black mana cannot be spent on X')
        other = max(0, n-black)
        # Exact black requirements are actual mana, never generic helper contributions.
        # Remaining X can be paid by permitted nonblack mana or nonmana helpers.
        alternatives = tuple(c for c in data['colors'] if c != 'B') + ('@X', '1')
        constrained = (('B', '@X'),) * black + (alternatives,) * other
        typed = allocation.constrain_generic(rows, constrained)
        return replace(cost, generic=cost.generic-black-other,
                       hybrid=cost.hybrid+constrained, allocation=typed)
    constrained = (tuple(data['colors']) + ('1',),) * n
    return replace(cost, generic=cost.generic-n, hybrid=cost.hybrid+constrained,
                   allocation=allocation.constrain_generic(rows, constrained))


def visible(cost: M.ManaCost) -> M.ManaCost:
    """Payment-only helper pseudo-units never appear in the player's remaining-mana display."""
    return replace(cost,hybrid=tuple(tuple(c for c in slot if c not in ('1', '@X')) for slot in cost.hybrid))
