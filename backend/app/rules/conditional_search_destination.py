"""Optional conditional destinations for a single revealed library search result."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WORDING = re.compile(r"search your library for (?P<kind>.+?) and reveal it\. "
                      r"if (?P<cond>[^,]+), you may put that card onto the battlefield(?P<tapped> tapped)?\. "
                      r"if you don't put the card onto the battlefield, put it into your hand\. then shuffle\.", re.IGNORECASE)


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import conditions, scripts

    if (family := _family_parse(body)) is not None:
        return family

    m = _WORDING.fullmatch(' '.join(body.split()))
    if m is None:
        return None
    cond = conditions.parse(m['cond'])
    native = scripts.parse_effects(f"Search your library for {m['kind']}, reveal it, put it into your hand, then shuffle.")
    if cond is None or native is None or native[1] is not None or native[2] or len(native[0]) != 1:
        return None
    search = native[0][0]
    if search.get('do') != 'search' or search.get('max') != 1 or search.get('to') != 'hand' or search.get('who') != 'you':
        return None
    return [{**search, 'optional_to_if': {'cond': cond, 'to': 'battlefield_tapped' if m['tapped'] else 'battlefield'}}], None, False



def _family_parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import conditions, scripts, selectors

    text = ' '.join(body.lower().split()).rstrip('.')
    kind, optional, top = 'artifact card', False, False
    source_condition, target = None, 'battlefield'
    card_condition = None
    if text == "you may search your library for an artifact card and reveal it. put it onto the battlefield if its mana value is 2 or less. otherwise, put it into your hand. if you search your library this way, shuffle":
        optional = True
        sel = selectors.parse('artifact card')
        assert sel is not None
        card_condition = selectors.replace(sel, compare=(('mv', '<=', 2),)).key()
    elif text == 'search your library for an equipment card and reveal it. if you reveal a card named hammer of nazahn this way, put it onto the battlefield. otherwise, put that card into your hand. then shuffle':
        kind = 'Equipment card'
        sel = selectors.parse('card')
        assert sel is not None
        card_condition = selectors.replace(sel, extras=(*sel.extras, 'name:Hammer of Nazahn')).key()
    elif text == 'search your library for a basic plains card and reveal it. if an opponent controls more lands than you, put it onto the battlefield tapped. otherwise, put it into your hand. then shuffle':
        kind, target = 'basic Plains card', 'battlefield_tapped'
        source_condition = conditions.parse('an opponent controls more lands than you')
    elif text == 'search your library for a vehicle card, reveal it, and put it into your hand. if this spell was cast from a graveyard, put that card onto the battlefield instead. then shuffle':
        kind = 'Vehicle card'
        source_condition = conditions.parse('this spell was cast from a graveyard', objects=True)
    elif text == "you may search your library for an artifact card, reveal it, then shuffle. put that card into your hand if you control an assassin. otherwise, put that card on top of your library":
        optional, top, target = True, True, 'hand'
        source_condition = conditions.parse('you control an Assassin')
    elif text == 'you may search your library for a basic land card, reveal it, then shuffle and put that card on top. if you control a dragon, put that card onto the battlefield tapped instead':
        kind, optional, top, target = 'basic land card', True, True, 'battlefield_tapped'
        source_condition = conditions.parse('you control a Dragon')
    else:
        return None
    suffix = 'then shuffle and put that card on top.' if top else 'put it into your hand, then shuffle.'
    article = 'an' if kind[0].lower() in 'aeiou' else 'a'
    native = scripts.parse_effects(f'Search your library for {article} {kind}, reveal it, {suffix}')
    assert native is not None and len(native[0]) == 1 and native[0][0]['do'] == 'search'
    search = {**native[0][0], **({'may': True} if optional else {})}
    if card_condition is not None:
        search['to_if'] = {'sel': card_condition, 'to': target}
    else:
        assert source_condition is not None
        search['source_to_if'] = {'cond': source_condition, 'to': target}
    return [search], None, False


def destination_map(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], dest: dict[str, str]) -> dict[str, str]:
    """Read the condition when the found card is assigned; never override Agent exile."""
    from app.rules import conditions

    option = e.get('source_to_if')
    if option is None or not conditions.holds(plan, ctx, option['cond']):
        return dest
    return {cid: option['to'] if to == e['to'] else to for cid, to in dest.items()}

def offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], pid: str, chosen: list[str], dest: dict[str, str]) -> bool:
    """True if a revealed search result is waiting for its optional destination choice."""
    from app.rules import conditions, prohibitions
    from app.rules.plan import decide

    option = e.get('optional_to_if')
    if option is None or len(chosen) != 1 or dest.get(chosen[0]) != 'hand' or not conditions.holds(plan, ctx, option['cond']):
        return False
    card = plan.state.cards.get(chosen[0])
    if card is None or prohibitions.cant_enter(plan, card, pid) is not None:
        return False  # An impossible optional entry cannot be chosen; retain the hand destination.
    decide(plan, player=pid, kind='confirm', prompt=f"Put {card.name or 'that card'} onto the battlefield{' tapped' if option['to'] == 'battlefield_tapped' else ''}?",
           options=[DecisionOption(id='yes', label='Put onto the battlefield'), DecisionOption(id='no', label='Put into your hand')],
           resume={'step': 'conditional_search_destination', 'ctx': ctx, 'e': e, 'chosen': chosen, 'dest': dest})
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    frame = d.resume
    e = dict(frame['e'])
    option = e.pop('optional_to_if')
    dest = dict(frame['dest'])
    if chosen == ['yes']:
        dest[frame['chosen'][0]] = option['to']
    effects._finish_search(plan, frame['ctx'], {**e, 'reveal': False}, d.player, frame['chosen'], dest)


RESUME = {'conditional_search_destination': resume}
