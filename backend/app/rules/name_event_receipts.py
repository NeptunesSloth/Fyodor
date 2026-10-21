"""Public as-played facts and exact splice-name receipts; no current-zone guessing."""
from __future__ import annotations

from typing import Any


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import events, scripts

    if text.startswith('Whenever ') and ', if it shares a card type with the exiled card, ' in text:
        head, tail = text.removeprefix('Whenever ').split(', if it shares a card type with the exiled card, ', 1)
        if head not in ('a player plays a land or casts a spell', 'you play a land or cast a spell'):
            return None
        cond = events.parse_condition(head)
        effect = scripts.parse_effects(tail[:1].upper() + tail[1:])
        if cond is not None and effect is not None:
            test = {'event_linked_types': True}
            return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'if': test, 'optional': False,
                    'target': effect[1], 'effects': [{'do': 'only_if', 'cond': test, 'skip': len(effect[0])},
                                                   *effect[0], {'do': 'played_relation', 'kind': 'link_marker', 'linked_cards': True}]}
    if text == "Whenever you play a card with the same name as one of the exiled cards, you may put one of those cards with that name into its owner's hand. Then if there are no cards exiled with ~, sacrifice it. If you do, take an extra turn after this one.":
        cond = events.parse_condition('you play a land or cast a spell')
        assert cond is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': {**cond, 'played_linked_name': True}, 'optional': False,
                'target': None, 'effects': [{'do': 'played_relation', 'kind': 'city', 'linked_cards': True}]}
    return None


def parse(text: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if text == "Counter target spell. That spell's controller reveals their hand, then discards each card with the same name as a card spliced onto that spell.":
        return ([{'do': 'played_relation', 'kind': 'splice_prepare'}], 'spell', False)
    return None


def linked_types(plan: Any, ctx: Any) -> bool:
    from app.rules import context, exiled_with

    event = context.info(plan, ctx, 'event')
    return event is not None and any(event[1].types & plan.ch(plan.state.cards[c]).types for c in exiled_with.cards(plan, ctx))


def execute(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import card_names, context, effects, exiled_with

    kind = e['kind']
    extra: list[dict[str, Any]] = []
    if kind == 'city':
        event = context.info(plan, ctx, 'event')
        pool = [c for c in exiled_with.cards(plan, ctx) if event is not None and card_names.share(plan.ch(plan.state.cards[c]), event[1])]
        context.bind_objects(plan, ctx, 'city_matching', pool)
        extra = [{'do': 'return_choice', 'who': 'ref:city_matching', 'to': 'choose', 'n': 1, 'upto': True,
                  'random': False, 'label': 'matching exiled card', 'as': 'city_chosen'},
                 {'do': 'return_card', 'who': 'ref:city_chosen', 'to': 'hand'},
                 {'do': 'played_relation', 'kind': 'city_finish'}]
    elif kind == 'city_finish':
        if not exiled_with.cards(plan, ctx):
            extra = [{'do': 'sacrifice', 'who': 'self', 'as': 'city_sacrificed'},
                     {'do': 'played_relation', 'kind': 'city_extra', 'who': 'ref:city_sacrificed'}]
    elif kind == 'city_extra':
        if effects._cards(plan, ctx, e['who']):
            extra = [{'do': 'extra_turn', 'who': 'you', 'n': 1}]
    elif kind == 'splice_prepare':
        target = effects._cards(plan, ctx, 'target')
        if not target:
            return True
        card = plan.state.cards[target[0]]
        record = plan.rules.payments.get(plan.oid(card))
        context.bind_players(ctx, 'spliced_controller', [card.controller])
        if record is None or record.spliced_names is None:
            from app.game.rules_state import DecisionOption
            from app.rules.plan import decide
            decide(plan, player=card.controller, kind='choose_one',
                   prompt='Restore public splice history: type spliced card names separated by semicolons, or No cards',
                   options=[DecisionOption(id='__name__', label='Public spliced card names, or No cards', group='historical splice names')],
                   resume={'step': 'splice_history_restore', 'ctx': ctx, 'object': plan.oid(card)})
            return False
        ctx['spliced_names'] = record.spliced_names
        extra = splice_tail()
    elif kind == 'splice_discard':
        players = effects._players(plan, ctx, 'ref:spliced_controller')
        matching = [c.id for c in plan.state.cards.values() if c.zone in [p + ':hand' for p in players]
                    and any(card_names.has_name(plan.ch(c), n) for n in ctx['spliced_names'])]
        from app.rules import grouped_discard
        return grouped_discard.begin_cards(plan, ctx, matching)
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at], *extra, *ctx['effects'][at:]]
    return True


def splice_tail() -> list[dict[str, Any]]:
    return [{'do': 'counter', 'who': 'target'}, {'do': 'reveal_hand', 'who': 'ref:spliced_controller'},
            {'do': 'played_relation', 'kind': 'splice_discard'}]


def splice_names_answer(plan: Any, typed: str | None) -> str:
    from app.rules import card_names

    if (typed or '').strip().lower() == 'no cards':
        return ''
    return ';'.join(card_names.canonical(plan, 'card name', n.strip()) for n in (typed or '').split(';'))


def resume_splice(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    ctx['spliced_names'] = chosen[0].split(';') if chosen[0] else []
    receipt = plan.rules.payments.get(d.resume['object'])
    if receipt is not None:
        receipt.spliced_names = list(ctx['spliced_names'])
    plan.note('Restored public splice history: ' + ('; '.join(ctx['spliced_names']) or 'No cards'), actor=d.player)
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at], *splice_tail(), *ctx['effects'][at:]]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'played_relation': execute}
RESUME = {'splice_history_restore': resume_splice}
