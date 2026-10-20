"""Exact Codie mana, delayed cast watch and ordinary timed exile permission."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules import mana as M
    from app.rules.plan import Plan

TEXT = ('{4}, {T}: Add {W}{U}{B}{R}{G}. When you next cast a spell this turn, exile cards from the '
        'top of your library until you exile an instant or sorcery card with lesser mana value. '
        'Until end of turn, you may cast that card without paying its mana cost. Put each other '
        'card exiled this way on the bottom of your library in a random order.')


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    if text != TEXT:
        return None
    from app.rules import delayed, events
    from app.rules import mana as M

    native = M.parse_mana_ability('{4}, {T}: Add {W}{U}{B}{R}{G}.', identity, card_name=name)
    cond = events.parse_condition('you cast a spell')
    if native is None or cond is None:
        return None
    effects = delayed.wrap_when([{'do': 'codie_packet'}],
        {'kind': 'watch', 'cond': cond, 'text': 'you next cast a spell'}, this_turn=True)
    return replace(native, delayed_effects=tuple(effects))


def packet(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, permissions, selectors
    from app.rules import exile_packet_continuations as packets
    from app.rules.plan import decide

    # The generic context reader has a physical-card fallback for old graveyard
    # bindings. A spell-cast event must instead retain its exact stack object.
    refs = context._object_refs(ctx, context.EVENT, was=True)
    spell = None
    if len(refs) == 1 and refs[0].zone == 'stack':
        current = context._same(plan, refs[0])
        if current is not None and not current.ability:
            spell = current, plan.ch(current)
        elif (snap := context.snapshot(plan, refs[0])) is not None and snap.zone == 'stack':
            from app.rules.triggers import _snapshot_card

            spell = _snapshot_card(plan, snap)
    if spell is None:
        from app.game.rules_state import DecisionOption

        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt='The original spell has no saved mana value: resolve this Codie trigger by hand.',
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'codie_legacy_mv_done', 'ctx': ctx})
        return False
    from app.rules.stack_interaction import mana_value

    threshold = mana_value(*spell)
    match = selectors.Selector(zones=('library',), card=True, types=('Instant', 'Sorcery'),
                               compare=(('mv', '<', threshold),)).key()
    descriptor = {'binding': 'codie', 'mode': 'codie'}
    shown = packets.until_packet(plan, ctx, descriptor, ctx['controller'], match)
    found = set(packets.remaining(plan, ctx, descriptor, '_found'))
    permissions.grant_play(plan, ctx, packets.grant(descriptor, '_found', free=True))
    effects.bottom_at_random(plan, ctx['controller'], [cid for cid in shown if cid not in found])
    return True


PRIMITIVES = {'codie_packet': packet}


def resume_legacy(plan: Plan, d: Any, chosen: list[str]) -> None:
    """Resume only after the player acknowledges the unknown-history instruction."""
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen != ['done']:
        raise ActionError('Choose Done after resolving the Codie trigger by hand')
    effects.continue_effects(plan, d.resume['ctx'])


RESUME = {'codie_legacy_mv_done': resume_legacy}
