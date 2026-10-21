"""Select/reveal privately, then optionally put the exact library object onto the battlefield."""
from __future__ import annotations

from typing import Any


def steps(mode: str) -> list[dict[str, Any]]:
    from app.rules import selectors

    sel = selectors.Selector(card=True, zones=('library',), types=('Creature',),
                             compare=(('mv', '<=', 3),) if mode == 'valiant' else ())
    return [{'do': 'reveal_outcome_top', 'n': 5 if mode == 'valiant' else 6, 'player': 'you', 'exact_look': True},
            {'do': 'pick_looked', 'n': 1, 'optional': True, 'sel': sel.key(), 'reveal': True, 'to': 'choose', 'as': 'placement_selected'},
            {'do': 'look_optional_placement', 'mode': mode, 'who': 'ref:placement_selected'},
            {'do': 'rest_looked', 'to': 'bottom_random'}]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body == "Look at the top six cards of your library. You may reveal a creature card from among them. If that card has mana value 2 or less, you may put it onto the battlefield and it gains haste until end of turn. If you didn't put the revealed card onto the battlefield this way, put it into your hand. Put the rest on the bottom of your library in a random order.":
        return steps('breakout'), None, False
    return None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events, scripts

    text = scripts.self_text(ability.text, ch.name).removeprefix('Valiant — ')
    if text != "Whenever ~ becomes the target of a spell or ability you control for the first time each turn, look at the top five cards of your library. You may reveal a creature card with mana value 3 or less from among them. You may put it onto the battlefield if it's your turn. If you don't put it onto the battlefield, put it into your hand. Put the rest on the bottom of your library in a random order.":
        return None
    cond = events.parse_condition('~ becomes the target of a spell or ability you control for the first time each turn')
    assert cond is not None
    return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False, 'target': None, 'effects': steps('valiant')}


def execute(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    selected = effects._cards(plan, ctx, e['who'])
    eligible = [c for c in selected if plan.state.cards[c].zone == ctx['controller'] + ':library'
                and (plan.state.turn.active_player == ctx['controller'] if e['mode'] == 'valiant' else plan.ch(plan.state.cards[c]).mana_value <= 2)]
    context.bind_objects(plan, ctx, 'placement_eligible', eligible)
    at = ctx['next']
    ctx['effects'][at:at] = [
        {'do': 'return_choice', 'who': 'ref:placement_eligible', 'to': 'battlefield', 'under': 'you',
         'n': 1, 'upto': True, 'random': False, 'label': 'revealed card to put onto the battlefield', 'as': 'placement_arrived'},
        {'do': 'finish_optional_placement', 'mode': e['mode'], 'who': e['who'], 'arrived': 'ref:placement_arrived'}]
    return True


def finish(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    arrived = [c for c in effects._cards(plan, ctx, e['arrived']) if plan.state.cards[c].zone.endswith(':battlefield')]
    still_library = [c for c in effects._cards(plan, ctx, e['who']) if plan.state.cards[c].zone == ctx['controller'] + ':library']
    context.bind_objects(plan, ctx, 'placement_fallback', still_library)
    context.bind_objects(plan, ctx, 'placement_haste', arrived)
    at = ctx['next']
    ctx['effects'][at:at] = [
        {'do': 'return_card', 'who': 'ref:placement_fallback', 'to': 'hand'},
        *([{'do': 'grant', 'who': 'ref:placement_haste', 'keywords': ['haste'], 'duration': 'end_of_turn'}] if e['mode'] == 'breakout' else [])]
    return True


PRIMITIVES = {'look_optional_placement': execute, 'finish_optional_placement': finish}
