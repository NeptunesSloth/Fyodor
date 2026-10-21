"""Unimported exact Kaya exile choices; other loyalties remain native."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import delayed
from app.rules import delayed_blinks50 as blinks
from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

ZERO="0: exile ~ or up to one target creature. return that card to the battlefield under its owner's control at the beginning of your next upkeep. you lose 2 life"


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    if text==ZERO:
        native=scripts.define(replace(ability,text='0: Exile up to one target creature.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'kaya_blink50'},{'do':'lose_life','who':'you','n':2}]}
    return None


def _exile(ctx: dict[str,Any]) -> bool:
    return packets.insert(ctx,[{'do':'exile','who':'ref:kaya50','as':'kaya50'},
        {'do':'blink_prepare50','binding':'ref:kaya50','when':delayed.WHEN['your next upkeep']}])


def blink(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, effects

    choices=list(dict.fromkeys([*effects._cards(plan,ctx,'self'),*effects._cards(plan,ctx,'target:0')]))
    context.bind_objects(plan,ctx,'kaya50',choices)
    if len(choices)<2:
        return _exile(ctx) if choices else True
    effects.decide(plan,player=ctx['controller'],kind='choose_one',prompt='Choose which permanent to exile',
        options=[DecisionOption(id=cid,label=plan.state.cards[cid].name,card_id=cid) for cid in choices],
        resume={'step':'kaya_blink50','ctx':ctx})
    return False


def resume_blink(plan: Plan,d: Any,chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx=d.resume['ctx']
    current=context.objects(plan,ctx,'kaya50')
    context.bind_objects(plan,ctx,'kaya50',[cid for cid in chosen if cid in current])
    _exile(ctx)
    effects.continue_effects(plan,ctx)


PRIMITIVES={'kaya_blink50':blink,'blink_prepare50':blinks.prepare_return}
RESUME={'kaya_blink50':resume_blink}
