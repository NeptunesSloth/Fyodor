"""Exact exile choices proved through native casting and permissions."""
from __future__ import annotations

from typing import Any

from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

SPARK="choose target creature. exile the top card of your library. you may have ~ deal damage to that creature equal to the exiled card's mana value. if you don't, you may play that card until end of turn"


def parse(body: str) -> tuple[list[dict[str,Any]],str,bool] | None:
    if packets.normalize(body)==SPARK:
        return [{'do':'exile_spell_choice49','mode':'spark','binding':'ref:spark49'}],'creature',False
    return None


def run(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects

    assert e['mode']=='spark'
    packets.top_packet(plan,ctx,e,[ctx['controller']])
    effects.decide(plan,player=ctx['controller'],kind='choose_one',prompt='Have Spark of Creativity deal damage?',
        options=[DecisionOption(id='damage',label='Deal damage equal to the exiled card’s mana value'),
                 DecisionOption(id='play',label='Allow playing the exiled card this turn')],
        resume={'step':'exile_spell_choice49','ctx':ctx,'e':e})
    return False


def resume(plan: Plan,d: Any,chosen: list[str]) -> None:
    from app.rules import effects

    ctx,e=d.resume['ctx'],d.resume['e']
    following=({'do':'damage','who':'target','n':{'mana_value':packets.ref(e,'_packet')}} if chosen==['damage']
               else packets.grant(e,play=True))
    packets.insert(ctx,[following])
    effects.continue_effects(plan,ctx)


PRIMITIVES={'exile_spell_choice49':run}
RESUME={'exile_spell_choice49':resume}
