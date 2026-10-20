"""CR 201.5, 601.2i, 707.4: mana-source cast triggers and copying their spell."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_COPY = re.compile(r'^(?P<target>(?:up to one (?:other )?)?target .+?) becomes a copy of that spell until end of turn$')


def copy_definition(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, selectors
    from app.rules.scripts import _NoMatch

    group = language.target_group(m['target'])
    if group is None:
        raise _NoMatch
    sel = selectors.from_key(group['what']) if group['what'].startswith(selectors.PREFIX) else None
    if sel is None or sel.player is not None or sel.card or sel.zones != ('battlefield',) or group['max'] != 1:
        raise _NoMatch
    return [{'do': 'become_copy', 'who': 'target', 'with': 'event_spell', 'duration': 'end_of_turn'}], group


def spell_recipe(plan: Plan, ctx: dict[str, Any]) -> tuple[Any, str | None]:
    from app.game.rules_state import CopyRecipe
    from app.rules import copying

    found = next(iter(copying._copy_sources(plan, ctx, 'event_spell')), None)
    if found is None:
        return None, None
    cid, oid = found
    card = plan.state.cards[cid]
    mem = copying.lki_spell(plan, cid, oid)
    if mem is None:
        if card.face_down:
            return _face_down_recipe(plan.ch(card)), None
        problem = copying.supported_source(plan, card)
        return (None, problem) if problem else (copying.recipe_of(plan, card), None)
    snap = plan.rules.lki[oid]
    if snap.face_down:
        from app.rules.triggers import _snapshot_card

        return _face_down_recipe(_snapshot_card(plan, snap)[1]), None
    base = snap.copy_recipe.model_copy(deep=True) if snap.copy_recipe is not None else CopyRecipe(
        printing=snap.printing, face=snap.face, source=snap.name[:200])
    record = plan.rules.payments.get(oid)
    return (base.model_copy(update={'prototyped': True}) if record is not None and record.prototyped else base), None


TEMPLATES = [(_COPY, copy_definition)]


def _face_down_recipe(ch: Any) -> Any:
    from app.game.rules_state import CopyRecipe

    # 707.2a: copy the public face-down characteristics, never the hidden printing.
    line = ' '.join(sorted(ch.supertypes) + sorted(ch.types))
    if ch.subtypes:
        line += ' — ' + ' '.join(sorted(ch.subtypes))
    return CopyRecipe(token={'name': ch.name, 'power': ch.power, 'toughness': ch.toughness,
                             'colors': sorted(ch.colors), 'type_line': line, 'mana_cost': ch.mana_cost,
                             'text': '\n'.join(a.text for a in ch.abilities)}, source='Face-down spell')
