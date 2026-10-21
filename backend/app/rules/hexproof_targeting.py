"""CR 609.4 / 702.11: targeting permissions without removing hexproof."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

_WORDING = re.compile(
    r"^(?P<players>your opponents and )?(?P<kind>creatures|permanents) your opponents control"
    r"(?: with hexproof)? can be the targets of spells and abilities(?P<own> you control)? "
    r"as though they didn't have hexproof(?P<ward>\. ward abilities of those creatures don't trigger)?$")
_EFFECT = re.compile(r"^until end of turn, (?P<body>" + _WORDING.pattern[1:-1] + r")$")


def _parse(text: str) -> dict[str, Any] | None:
    m = _WORDING.fullmatch(text.strip().rstrip('.').lower().replace('’', "'"))
    if m is None or m['ward'] and (m['kind'] != 'creatures' or m['players']):
        return None
    return {'players': bool(m['players']), 'creatures': m['kind'] == 'creatures',
            'own': bool(m['own']), 'ward': bool(m['ward'])}


def static_definition(text: str) -> dict[str, Any] | None:
    parsed = _parse(text)
    return {'kind': 'static', 'static': 'hexproof_targeting', 'effects': [], **parsed} if parsed else None


def _effect(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    from app.rules.scripts import _NoMatch

    parsed = _parse(m['body'])
    if parsed is None or parsed['ward']:
        raise _NoMatch
    return [{'do': 'hexproof_targeting', **parsed}], None


def grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    # 611.2c: this changes rules, not characteristics, so membership remains dynamic.
    plan.rules.cast_limits.append({'hexproof_targeting': {k: e[k] for k in ('players', 'creatures', 'own', 'ward')},
                                   'controller': ctx['controller'], 'until': 'turn', 'turn': plan.state.turn.number,
                                   'spells': False, 'label': ctx.get('name') or 'Targeting permission'})
    plan.note(f"{ctx.get('name') or 'An effect'}: target as though hexproof were absent this turn", actor=ctx['controller'])
    return True


def _permissions(plan: Plan) -> list[tuple[str, dict[str, Any]]]:
    from app.rules import cast_limits

    found = [(src.controller, d) for src, d in cast_limits._statics(plan.state, plan.info, 'hexproof_targeting')]
    found += [(d['controller'], d['hexproof_targeting']) for d in plan.rules.cast_limits
              if d.get('hexproof_targeting') and cast_limits._record_live(plan.state, d)]
    return found


def ignores(plan: Plan, chooser: str, *, card: CardInstance | None = None,
            ch: Characteristics | None = None, player: str | None = None) -> bool:
    for controller, d in _permissions(plan):
        if d['own'] and chooser != controller:
            continue
        if player is not None and d['players'] and player != controller:
            return True
        if card is not None and card.controller != controller and (not d['creatures'] or ch is not None and ch.is_creature):
            return True
    return False


def suppresses_ward(plan: Plan, card: CardInstance, ch: Characteristics) -> bool:
    return ch.is_creature and any(d['ward'] and card.controller != controller for controller, d in _permissions(plan))


TEMPLATES = [(_EFFECT, _effect)]
PRIMITIVES = {'hexproof_targeting': grant}
