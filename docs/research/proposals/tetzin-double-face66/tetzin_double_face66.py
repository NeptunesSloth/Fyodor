"""Tetzin's physical double-faced artifacts, public mill pick, and native back-face trigger."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

_FRONT = 'Whenever ~ or another double-faced artifact you control enters, mill three cards. You may put an artifact card from among them into your hand.'
_BACK = 'Whenever ~ enters or attacks, transform up to one other target double-faced artifact you control. Create two 1/1 colorless Gnome artifact creature tokens.'
_EXTRA = 'double_faced_permanent66'


def physical(plan: Plan, card: CardInstance) -> bool:
    if card.merged and not card.melded:  # 730.2i; native meld representation is a separate712 case.
        return False
    if card.token is not None and card.token.back is not None:
        return True
    data = plan.info.get(card.card_id) if card.card_id else None
    # Artwork-only reversible treatments have the mechanics of their ordinary single-faced printing.
    return bool(data and data.get('layout') in ('transform', 'modal_dfc', 'meld', 'battle'))


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered':
        return None
    text = scripts.self_text(ability.text, ch.name)
    if text == _FRONT:
        native = scripts.define(replace(ability, text='Whenever ~ or another artifact you control enters, draw a card.'), ch)
        if native is None:
            return None
        cond = dict(native['cond'])
        sel = selectors.from_key(cond['sel'])
        cond['sel'] = replace(sel, extras=(*sel.extras, _EXTRA)).key()
        return {**native, 'cond': cond,
                'effects': [{'do': 'mill', 'who': 'you', 'n': 3, 'as': 'public_mill65'},
                            {'do': 'public_pick65', 'nashi': False, 'artifact66': True}]}
    if text == _BACK:
        native = scripts.define(replace(ability, text='Whenever ~ enters or attacks, transform up to one target artifact you control. Create two 1/1 colorless Gnome artifact creature tokens.'), ch)
        if native is None:
            return None
        sel = selectors.Selector(controller='you', types=('Artifact',), other=True, extras=(_EXTRA,))
        return {**native, 'targets': [{**native['targets'][0], 'what': sel.key()}]}
    return None
