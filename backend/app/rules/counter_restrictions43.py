"""Kind-specific removal prohibitions, legal counter modes and compound Eerie."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events, scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == "Stun counters can't be removed from permanents your opponents control.":
        return {'kind': 'static', 'static': 'cant_remove_counters', 'counter': 'stun', 'effects': []}
    if text != ('Whenever ~ or another enchantment you control enters and whenever you fully unlock a Room, '
                'tap up to one target creature and put a stun counter on it.'):
        return None
    entry = events.parse_condition('~ or another enchantment you control enters')
    unlock = events.parse_condition('you fully unlock a Room')
    native = scripts.parse_effects('Tap up to one target creature and put a stun counter on it.')
    assert entry is not None and unlock is not None and native is not None
    # "it" in this printed body refers to its target. The generic compound
    # grammar conservatively rejects pronouns referring to different subjects.
    return {'kind': 'triggered', 'trigger': 'event',
            'cond': {'event': 'either', 'conds': [entry, unlock], 'subject': 'mixed'},
            'effects': native[0], 'optional': False, **scripts.target_fields(native[1])}


def fixed_counter_choices(plan: Any, found: list[str], to: list[str], picks: dict[str, str]) -> dict[str, str]:
    """608.2d: when removing this kind is prohibited everywhere, only put remains.

    If putting is also prohibited the native put performs no action. A choice
    with no possible branch needs no answer. The
    native counter_kinds menu calls this without changing removal actions.
    """
    from app.rules import prohibitions

    return {**picks, **{kind: 'put' for kind in found if kind not in picks and to
                       and all(prohibitions.cant_remove_counters(plan, cid, kind) for cid in to)}}


def fixed_suspended_mode(plan: Any, card: str, kind: str) -> str | None:
    """Only Clockspinning's mandatory put-or-remove mode can be forced this way."""
    from app.rules import prohibitions

    if not prohibitions.cant_remove_counters(plan, card, kind):
        return None
    return 'decline' if prohibitions.cant_counters(plan, card, None, kind) else 'add'
