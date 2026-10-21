"""Staged pure inspection only: discovery does not establish acquisition history."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.game.rules_state import ObjectRef
from app.rules import abilities_of, scripts
from app.rules.mana_noted_profiles import ICE_INPUT
from app.rules.oracle import AbilityText

ICE_OUTPUT = ("{T}, Remove a charge counter from ~: Add ~'s last noted type and amount of mana. "
              'Spend this mana only to cast the last card exiled with ~.')


@dataclass(frozen=True)
class PairScope:
    card: str
    object_id: str
    scope: str | None
    input_slots: tuple[int, ...]
    output_slots: tuple[int, ...]
    origins: tuple[tuple[str, ...], ...]


def inspect(source: ObjectRef, name: str, abilities: Sequence[AbilityText]) -> tuple[PairScope, ...]:
    """Report complete effective pairs; unscoped identity remains explicitly unresolved.

    No registry, state, donor notes or tracked-birth marker is read or written.
    A caller cannot treat this result as a known-empty acquisition receipt.
    """
    groups: dict[str | None, tuple[list[AbilityText], list[AbilityText]]] = {}
    for ability in abilities:
        if ability.kind not in ('activated', 'mana'):
            continue
        text = scripts.self_text(ability.text, name)
        if text not in (ICE_INPUT, ICE_OUTPUT):
            continue
        halves = groups.setdefault(abilities_of.link_scope(ability), ([], []))
        halves[0 if text == ICE_INPUT else 1].append(ability)
    return tuple(PairScope(source.card, source.object_id, scope,
                           tuple(ab.index for ab in inputs), tuple(ab.index for ab in outputs),
                           tuple(ab.borrowed_origin for ab in (*inputs, *outputs)))
                 for scope, (inputs, outputs) in groups.items() if inputs and outputs)
