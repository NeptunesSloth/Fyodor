"""-- trigger other (wave 25B) -- "Airbend up to one target creature." (701.65, Avatar: The Last Airbender), researched against CR
2026-09-25.

* 701.65a: to airbend a permanent (or spell) is to exile it; for each card exiled this way, for as long as it remains exiled, its
  OWNER may cast it by paying {2} rather than paying its mana cost. That is an alternative cost (118.9): additional costs, increases
  and reductions still apply (118.9d), and only one alternative cost applies to a spell (118.9a).
* 400.7h: the permission follows the object it was made for. A card that leaves exile is a new object, so it is spent; the permission
  is stored with the exile object's id (``Permission.object_id``, ``Permission.alt_mana``) and read by casting.cast_grant.
* A token is exiled and ceases to exist (111.7): nothing to cast. A card that didn't reach exile (a commander its owner put into the
  command zone instead, 903.9b, or a replacement effect) is not exiled by this and gets no permission.
* Spells aren't airbent here (a spell's exile from the stack is a separate mover): the grammar reads permanents only.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import Permission

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
ALT_COST = "{2}"  # 701.65a


def airbend(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _cards, exile_cards

    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if not cards:
        return True
    exile_cards(plan, ctx, e, cards)
    for cid in cards:
        card = plan.state.cards.get(cid)
        if card is None or card.is_token or not card.zone.endswith(":exile"):
            continue
        plan.rules.permissions.append(Permission(
            id=secrets.token_hex(4), player=card.owner, cast=True, zone="exile", object_id=plan.oid(card), card=card.id,
            until="permanent", turn=plan.state.turn.number, alt_mana=ALT_COST, source=ctx.get("source_object"),
            label=f"{card.name}: cast it from exile for {ALT_COST} (airbend)"))
        plan.note(f"{card.name} is airbent: {plan.name(card.owner)} may cast it from exile for {ALT_COST}", [card.id])
    return True


PRIMITIVES = {"airbend": airbend}
