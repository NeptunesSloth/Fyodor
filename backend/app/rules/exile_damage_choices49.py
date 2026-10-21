"""Unregistered exact source-damage threshold recipe; native cohort prerequisite held."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import exile_packet_continuations as packets

TEXT='whenever ~ deals 4 or more damage, exile the top card of your library. until the end of your next turn, you may play that card'


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    if packets.normalize(scripts.self_text(ability.text,ch.name))!=TEXT:
        return None
    native=scripts.define(replace(ability,text='Whenever ~ deals damage, exile the top card of your library. Until the end of your next turn, you may play that card.'),ch)
    assert native is not None
    return {**native,'cond':{**native['cond'],'source_damage_min':4}}
