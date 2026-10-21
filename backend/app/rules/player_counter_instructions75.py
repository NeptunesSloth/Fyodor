"""Player-relative public permanent choices retain native putter and object bindings."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import DecisionOption
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


def _choose(who: str, binding: str, *, sel: str = 'creature', n: Any = 1) -> dict[str, Any]:
    from app.rules import selectors

    parsed = selectors.parse(sel)
    assert parsed is not None
    return {'do': 'player_chooses', 'who': who, 'sel': parsed.key(), 'n': n, 'label': sel, 'as': binding}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body[:1].upper() + body[1:] != 'Target player chooses a creature they control and puts two +1/+1 counters on it.':
        return None
    return ([_choose('target', 'mona75'),
             {'do': 'add_counters', 'who': 'ref:mona75', 'kind': '+1/+1', 'n': 2, 'by': 'target'}], 'player', False)


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == ("At the beginning of each player's upkeep, that player taps an untapped artifact, creature, or land "
                'they control for each fade counter on ~.'):
        native = scripts.define(replace(ability, text="At the beginning of each player's upkeep, that player draws a card."), ch)
        assert native is not None
        return {**native, 'effects': [_choose('event_player', 'wire75', sel='untapped artifact, creature, or land',
                                            n={'counters': 'fade', 'on': 'self'}),
                                     {'do': 'tap', 'who': 'ref:wire75'}]}
    if text != ('At the beginning of your end step, choose a player. They put two +1/+1 counters on a creature they control. '
                'Choose a second player to draw a card. Then choose a third player to create two Treasure tokens.'):
        return None
    native = scripts.define(replace(ability, text='At the beginning of your end step, you draw a card.'), ch)
    treasure = scripts.parse_effects('Create two Treasure tokens.')
    assert native is not None and treasure is not None
    return {**native, 'effects': [
        {'do': 'choose_value', 'who': 'you', 'what': 'player', 'as': 'gluntch75_1'},
        _choose('ref:gluntch75_1', 'gluntch75_creature'),
        {'do': 'add_counters', 'who': 'ref:gluntch75_creature', 'kind': '+1/+1', 'n': 2, 'by': 'ref:gluntch75_1'},
        {'do': 'choose_value', 'who': 'you', 'what': 'player', 'as': 'gluntch75_2', 'exclude_players': {'first': 'ref:gluntch75_1'}},
        {'do': 'draw', 'who': 'ref:gluntch75_2', 'n': 1},
        {'do': 'choose_value', 'who': 'you', 'what': 'player', 'as': 'gluntch75_3',
         'exclude_players': {'first': 'ref:gluntch75_1', 'second': 'ref:gluntch75_2'}},
        {**treasure[0][0], 'who': 'ref:gluntch75_3'}]}


def remaining_players(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], options: list[DecisionOption]) -> list[DecisionOption]:
    if not e.get('exclude_players'):
        return options
    from app.rules import context

    excluded = {pid for ref in e['exclude_players'].values() for pid in context.players(plan, ctx, ref.removeprefix('ref:'))}
    return [option for option in options if option.id not in excluded]
