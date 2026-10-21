"""A Form becomes an Aura, then manifests and attaches to that native committed object."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('When this enchantment enters, it becomes an Aura with enchant creature. '
        'Manifest the top card of your library and attach this enchantment to it.')
BASE = 'When this enchantment enters, manifest the top card of your library.'
BINDING = 'manifest_aura74'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=BASE), ch)
    if native is None or [e.get('do') for e in native.get('effects', [])] != ['manifest']:
        return None
    return {**native, 'effects': [{'do': 'manifest_aura74'},
                                 {**native['effects'][0], 'as': BINDING},
                                 {'do': 'attach_to', 'src': 'self', 'who': 'ref:' + BINDING}]}


def become_aura(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, layers

    # Set only the enchantment subtype set (205.1a), preserving card types.
    # Native layer4 removes these other enchantment types on every derivation.
    return effects.become(plan, ctx, {'who': 'self', 'add_creature_types': ['Aura'],
                                     'remove_subtypes': sorted(layers.ENCHANTMENT_TYPES - {'Aura'}),
                                     'abilities': ['Enchant creature'], 'duration': 'permanent'})
