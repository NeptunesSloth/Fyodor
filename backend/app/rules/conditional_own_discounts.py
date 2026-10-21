"""Own conditional discounts reuse announced additional costs and selected flashback."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics

_FLASHBACK=re.compile(r'(?P<cost>Flashback (?:\{[^}]+\})+)\. This spell costs \{X\} less to cast this way, where X is the greatest mana value of a commander you own on the battlefield or in the command zone\.?',re.IGNORECASE)
_BARGAIN=re.compile(r"(?:this spell|~) costs \{(?P<n>\d+)\} less to cast if it's bargained")


def flashback_line(text: str) -> str | None:
    match=_FLASHBACK.fullmatch(text.strip())
    return match['cost'] if match is not None else None


def printed_flashback_discount(state: GameState,player: str,card: CardInstance,ch: Characteristics,info: Any,index: int | None) -> int:
    from app.rules import casting, flashback_choices, values
    from app.rules.plan import Plan

    ways=flashback_choices.options(state,card,ch,info)
    selected=flashback_choices.selected(ways,index) if ways else None
    for ab in ch.abilities:
        if ab.kind=='keywords' and 'flashback' in ab.keywords and (line:=flashback_line(ab.text)) is not None \
                and casting.flashback_parts(line)==selected:
            expression=values.parse_count('the greatest mana value of a commander you own on the battlefield or in the command zone')
            assert expression is not None
            view=Plan.view(state,player,info)
            return values.evaluate(view,{'controller':player,'source_card':card.id,'source_object':view.oid(card)},expression)
    return 0


def self_change(text: str) -> dict[str,Any] | None:
    from app.rules import cost_changes

    t=text.strip().rstrip('.').lower()
    if (match:=_BARGAIN.fullmatch(t)) is not None:
        # Applied by the announced bargain sacrifice component, never twice as
        # an unconditional self reduction before that cost has been selected.
        return {'dir':-1,'n':0,'bargain_discount':int(match['n'])}
    parts=re.split(r'\. it also costs | and (?=\{\d+\} less to cast if )',t)
    if len(parts)<2:
        return None
    first=cost_changes.self_change(parts[0])
    tail=[cost_changes.self_change('this spell costs '+part) for part in parts[1:]]
    parts_read = [first, *tail]
    if any(part is None or part.get('dir') != -1 or set(part) & {'mana', 'also', 'cap', 'targets'}
           for part in parts_read):
        return None
    return {'dir':-1,'parts':parts_read}


def bargain_discount(ch: Characteristics) -> int:
    return sum(int(match['n']) for ab in ch.abilities
               if (match:=_BARGAIN.fullmatch(ab.text.strip().rstrip('.').lower())) is not None)


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import selectors

    if body.strip().rstrip('.')=='Target opponent puts a creature card of their choice from their graveyard onto the battlefield under your control':
        return ([{'do':'return_choice','chooser':'target','to':'battlefield','tapped':False,'under':'you',
                  'sel':selectors.Selector(card=True,types=('Creature',),zone_owner='you',zones=('graveyard',)).key(),
                  'n':1,'upto':False,'random':False,'label':'creature card'}],'opponent',False)
    return None
