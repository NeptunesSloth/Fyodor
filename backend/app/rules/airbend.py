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


def complement(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """A chosen optional target is protected from the following untargeted airbend."""
    from app.rules import language, scripts, selectors

    lead = 'Choose up to one target creature, then airbend all other creatures.'
    if not body.startswith(lead):
        return None
    tail = body[len(lead):].strip()
    rest = scripts.parse_effects(tail) if tail else ([], None, False)
    group = language.target_group('up to one target creature')
    sel = selectors.parse('creatures')
    if rest is None or rest[1] is not None or rest[2] or group is None or sel is None:
        return None
    return [{'do': 'airbend', 'who': sel.key(), 'exclude_target': 'target:0'}, *rest[0]], [group], False


def spell_target(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """-- (wave 110B) -- "Airbend up to one other target creature or spell." (Aang, Swift Savior): other than the source, a creature or a spell (701.65a)."""
    from dataclasses import replace

    from app.rules import language, selectors

    if body.lower() != "airbend up to one other target creature or spell.":
        return None
    creature = selectors.parse("another creature")
    spell = selectors.parse("spell")
    group = language.target_group("up to one target spell or creature")
    if creature is None or spell is None or group is None or spell.zones != ("stack",):
        return None
    sel = replace(selectors.Selector(), either=(spell.key(), creature.key()), zones=("stack", "battlefield"))
    return [{"do": "airbend", "who": "target:0"}], [{**group, "what": sel.key()}], False


def airbend(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _cards, exile_cards

    # (permissions of cards that have since left exile are spent for good, 400.7h: dropped, so the list doesn't grow)
    plan.rules.permissions = [p for p in plan.rules.permissions if not p.alt_mana or (
        p.card in plan.state.cards and plan.oid(plan.state.cards[p.card]) == p.object_id)]
    excluded = set(_cards(plan, ctx, e['exclude_target'])) if e.get('exclude_target') else set()
    cards = [c for c in _cards(plan, ctx, e["who"]) if c not in excluded and (plan.state.cards[c].zone.endswith(":battlefield")
             or plan.state.cards[c].zone == "stack" and plan.state.cards[c].ability is None)]
    if not cards:
        return True
    r = plan.rules
    for cid in cards:  # -- (wave 110B) -- a spell leaves the stack exiled, not countered (701.65a); it is no longer a spell, so it never resolves
        if plan.state.cards[cid].zone == "stack":
            oid = plan.oid(cid)
            r.stack.pop(cid, None)
            r.buyback = [o for o in r.buyback if o != oid]
            r.flashback = [o for o in r.flashback if o != oid]
            r.exile_resolves.pop(oid, None)
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
    from app.rules import wave110b_bend

    wave110b_bend.note(plan, ctx["controller"], "air")  # 701.65b
    return True


PRIMITIVES = {"airbend": airbend}
