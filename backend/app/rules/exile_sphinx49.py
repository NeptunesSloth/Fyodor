"""Ur-Sphinx continuation using the native simultaneous mill receipt."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

TEXT='whenever one or more sphinxes you control attack, each player mills that many cards. for each player, you may cast a card that player milled this way without paying its mana cost'


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    if packets.normalize(scripts.self_text(ability.text,ch.name))!=TEXT:
        return None
    # The native counted-attacker condition freezes all actually declared
    # Sphinx attackers, independently of whether this source attacks.
    native=scripts.define(replace(ability,text='Whenever you attack with one or more Sphinxes, each player mills that many cards.'),ch)
    assert native is not None
    mill={**native['effects'][0],'as':'ur49_milled'}
    return {**native,'effects':[mill,{'do':'ur_sphinx49','binding':'ref:ur49_milled'}]}


def run(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context

    key=e['binding'].removeprefix('ref:')
    binding=(ctx.get('refs') or {}).get(key) or {}
    # `was` is captured by native effects.mill AFTER replacement-expanded
    # counts were chosen. It records the actual original library, not owner
    # guesses or a scan of current graveyards.
    origin={r['card']:str(r.get('zone') or '').removesuffix(':library')
            for r in binding.get('was') or [] if str(r.get('zone') or '').endswith(':library')}
    actual=[cid for cid in context.objects(plan,ctx,key)
            if plan.state.cards[cid].zone.endswith(':graveyard')]
    following=[]
    for player in plan.apnap():
        name='ur49_'+player
        context.bind_objects(plan,ctx,name,[cid for cid in actual if origin.get(cid)==player])
        following.append({'do':'free_cast','zone':'that','who':'ref:'+name,'exact_refs':True,
                          'optional':True,'n':1,'source_zone':'graveyard','source_owner':'player:'+player})
    return packets.insert(ctx,following)


PRIMITIVES={'ur_sphinx49':run}
