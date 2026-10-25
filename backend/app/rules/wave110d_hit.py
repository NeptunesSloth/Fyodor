"""-- hit counters (wave 110D) -- "Whenever Etrata deals combat damage to a player, exile target creature that player controls and put a hit counter on
that card. That player loses the game if they own three or more exiled cards with hit counters on them. Etrata's owner shuffles Etrata into their library."
(Etrata, the Silencer): 701.13 (exile), 122.1 (counters on an exiled card), 104.3e (an effect makes a player lose the game), 701.24 (shuffle into the library).
The ability is the exile, a counter on the exiled card, the loss check and the shuffle, in that order."""
from __future__ import annotations

from typing import Any

TEXT = ("Whenever ~ deals combat damage to a player, exile target creature that player controls and put a hit counter on that card. "
        "That player loses the game if they own three or more exiled cards with hit counters on them. "
        "~'s owner shuffles ~ into their library.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name).replace("Etrata", "~") != TEXT:
        return None
    d = scripts.define(replace(ability, text="Whenever ~ deals combat damage to a player, exile target creature that player controls."), ch)
    if d is None:
        return None
    d["effects"] += [{"do": "hit_loss110d"},
                     {"do": "to_library", "who": "self", "place": "shuffle"}]
    return d


def hit_loss(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """That player (the one dealt combat damage) loses the game if they own three or more exiled cards with hit counters (104.3e)."""
    from app.rules import context, replace, win_game

    # "that card" is the creature just exiled: a new object (400.7), so the target (an object in play) is looked up by its card
    exiled = [t["id"] for t in ctx.get("targets") or [] if plan.state.cards[t["id"]].zone.endswith(":exile")]
    if exiled:
        replace.put_counters(plan, [(cid, "hit", 1) for cid in exiled], by=ctx["controller"], ctx=ctx)
    who = context.players(plan, ctx, context.EVENT) or []
    for pid in who[:1]:
        n = sum(1 for c in plan.state.cards.values() if c.owner == pid and c.zone.endswith(":exile") and c.counters.get("hit", 0) > 0)
        if n >= 3:
            return win_game.lose_game(plan, ctx, {"who": "event_player"})
    return True


PRIMITIVES = {"hit_loss110d": hit_loss}
