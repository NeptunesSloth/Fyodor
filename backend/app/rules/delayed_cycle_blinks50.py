"""Unimported exact cycle-self or battlefield-other-cycle delayed blink."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import delayed
from app.rules import delayed_blinks50 as blinks
from app.rules import exile_packet_continuations as packets

TEXT="whenever you cycle this card or cycle another card while ~ is on the battlefield, you may exile target creature. if you do, return that card to the battlefield under its owner's control at the beginning of the next end step"


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    if packets.normalize(scripts.self_text(ability.text,ch.name))!=TEXT:
        return None
    native=scripts.define(replace(ability,text='When you cycle this card, you may exile target creature.'),ch)
    assert native is not None
    return {**native,'cond':{**native['cond'],'cycle_other_you':True},
            'effects':[{'do':'exile','who':'target','as':'cycle_blink50'},
                       {'do':'blink_prepare50','binding':'ref:cycle_blink50','when':delayed.WHEN['the next end step']}]}


PRIMITIVES={'blink_prepare50':blinks.prepare_return}
