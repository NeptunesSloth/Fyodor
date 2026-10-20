"""Exact artifact tables and opt-in native delayed-watcher departure cleanup."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_TEXT = ('{2}, {T}: Roll a d20 and subtract the number of cards in your hand. '
         'If the result is 0 or less, discard your hand. '
         '1—9 | Return a card at random from your graveyard to your hand. '
         '10—19 | Draw two cards. '
         '20 | Put a creature card from any graveyard onto the battlefield under your control. '
         'When that creature dies, its owner loses the game.')


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import dice, scripts, selectors

    for ability in ch.abilities:
        if ability.text != _TEXT:
            continue
        native = scripts.define(replace(ability, text='{2}, {T}: Roll a d20.'), ch)
        if native is None or native.get('kind') != 'activated':
            continue
        creature = selectors.Selector(zones=('graveyard',), card=True, types=('Creature',)).key()
        effects = [{'do': 'roll', 'sides': 20, 'count': 1, 'mod': {'op': '-', 'v': {'hand': 'you'}}},
                   {'do': 'only_if', 'cond': {'value': {'die': 'result'}, 'op': '<=', 'n': 0}, 'skip': 1},
                   {'do': 'discard', 'who': 'you', 'n': 0, 'all': True},
                   {'do': 'only_if', 'cond': dice.condition('the result is 1 to 9'), 'skip': 1},
                   {'do': 'random_artifact42', 'kind': 'deck_return'},
                   {'do': 'only_if', 'cond': dice.condition('the result is 10 to 19'), 'skip': 1},
                   {'do': 'draw', 'who': 'you', 'n': 2},
                   {'do': 'only_if', 'cond': dice.condition('the result is 20 to 20'), 'skip': 2},
                   {'do': 'return_choice', 'sel': creature, 'n': 1, 'to': 'choose', 'as': 'r42_deck_chosen'},
                   {'do': 'random_artifact42', 'kind': 'deck_enter',
                    'who': 'ref:r42_deck_chosen', 'as': 'r42_deck_entered'}]
        out[ability.index] = {**native, 'effects': effects}


def consume(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    import secrets

    from app.rules import coin_recipes, context, effects

    kind = effect['kind']
    if kind == 'deck_return':
        pool = sorted(plan.state.zones.get(ctx['controller'] + ':graveyard', []))
        if pool:
            selected = (plan.rng or secrets.SystemRandom()).choice(pool)
            context.bind_objects(plan, ctx, 'r42_deck_return', [selected])
            coin_recipes.insert(ctx, [{'do': 'return_card', 'who': 'ref:r42_deck_return', 'to': 'hand'}])
    elif kind == 'deck_enter':
        selected = effects._cards(plan, ctx, effect['who'])
        if selected:
            card = plan.state.cards[selected[0]]
            coin_recipes.insert(ctx, [{'do': 'return_card', 'who': effect['who'], 'to': 'battlefield',
                                      'under': 'you', 'as': effect['as']},
                                     {'do': 'random_artifact42', 'kind': 'deck_watch', 'owner': card.owner,
                                      'who': 'ref:' + effect['as']}])
    elif kind == 'deck_watch':
        if effects._cards(plan, ctx, effect['who']):
            coin_recipes.insert(ctx, [{'do': 'delayed', 'when': {'kind': 'event', 'event': 'die', 'forget_on_departure': True},
                                      'who': effect['who'], 'n': 1},
                                     {'do': 'lose_game', 'who': 'player:' + effect['owner']}])
    else:
        raise ValueError('Unknown artifact table consequence')
    return True


PRIMITIVES = {'random_artifact42': consume}


def departed_watchers(plan: Any, events: list[Any]) -> set[str]:
    """Only exact opt-in watchers expire on actual native BF departures."""
    departed = set()
    for event in events:
        if (event.kind != 'zone_change' or event.manual or not event.object_id
                or (event.from_zone or '').rsplit(':', 1)[-1] != 'battlefield'
                or (event.to_zone or '').rsplit(':', 1)[-1] in ('battlefield', 'graveyard')):
            continue
        if event.to_zone is None:
            snapshot = plan.rules.lki.get(event.object_id)
            if snapshot is None or snapshot.is_token:
                continue  # Native delayed die handling owns token deaths; unknown is not inferred.
        departed.add(event.object_id)
    return {watch.id for watch in plan.rules.delayed
            if watch.when.get('kind') == 'event' and watch.when.get('event') == 'die'
            and watch.when.get('forget_on_departure') is True
            and any(ref.get('object_id') in departed for ref in (watch.refs.get('watch') or {}).get('objects') or [])}
