"""Unimported exact next-turn shield; delayed return remains the native spell grammar."""
from __future__ import annotations

from typing import Any

from app.rules import exile_packet_continuations as packets

TEXT='until your next turn, prevent all damage that would be dealt to you'


def parse(body: str) -> tuple[list[dict[str,Any]],None,bool] | None:
    if packets.normalize(body)!=TEXT:
        return None
    return [{'do':'prevent_all','scope':{'combat':None,'to_players':'you'},'duration':'next_turn'}],None,False
