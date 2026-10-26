"""-- (wave 110B) -- Hama, the Bloodbender: "When Hama enters, target opponent mills three cards. Exile up to one noncreature, nonland card from that
player's graveyard. For as long as you control Hama, you may cast the exiled card during your turn by waterbending {X} rather than paying its mana
cost, where X is its mana value."

* 701.67 / rulings 2025-10-02: waterbend {N} = pay {N}, tapping untapped artifacts and creatures for generic mana; the cast is an alternative cost
  (118.9), so additional costs still apply; normal timing rules apply; a spell with {X} in its cost has X = 0 (107.3b).
* 611.2b: the permission ends when Hama leaves or another player controls it (Permission.until source_controlled); 400.7h: the card is the exiled object.
* The permission is a stored Permission: alt_mana = {MV}, extra = "Waterbend {MV}" (the taps), when = it is your turn.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_TEXT = ("Target opponent mills three cards. Exile up to one noncreature, nonland card from that player's graveyard. For as long as you control Hama, "
         "you may cast the exiled card during your turn by waterbending {X} rather than paying its mana cost, where X is its mana value.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = re.sub(r" \([^)]*\)$", "", body.strip().replace("~", "Hama").replace("this creature", "Hama"))
    if text[:1].upper() + text[1:] != _TEXT:
        return None
    first = scripts.parse_effects(_TEXT.split(". Exile")[0] + ".")
    if first is None:
        return None
    return [*first[0], {"do": "hama110b"}], first[1], False


def hama(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _players
    from app.rules.plan import decide

    who = _players(plan, ctx, "target")
    if not who:
        return True
    pool = [c.id for c in plan.state.cards.values() if c.zone == f"{who[0]}:graveyard"
            and not (t := plan.ch(c).types) & {"Creature", "Land"} and t]
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Exile up to one noncreature, nonland card from that graveyard",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           min_choices=0, max_choices=1, resume={"step": "hama110b", "ctx": ctx, "pool": pool})
    return False


def resume_hama(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.rules_state import Permission
    from app.rules import delayed, effects

    ctx = d.resume["ctx"]
    chosen = [c for c in chosen[:1] if c in d.resume["pool"]]
    if chosen:
        effects.exile_cards(plan, ctx, {}, chosen)
        card = plan.state.cards[chosen[0]]
        if card.zone.endswith(":exile") and delayed._source_ok(plan, "source_controlled", ctx.get("source_card"), ctx.get("source_object"), ctx["controller"]):
            mv = int(plan.ch(card).mana_value)
            plan.rules.permissions.append(Permission(
                id=secrets.token_hex(4), player=ctx["controller"], cast=True, zone="exile", object_id=plan.oid(card), card=card.id,
                until="source_controlled", turn=plan.state.turn.number, alt_mana=f"{{{mv}}}", extra=f"Waterbend {{{mv}}}", when={"turn": "yours"},
                source=ctx.get("source_object"), label=f"{card.name}: cast it from exile by waterbending {{{mv}}} during your turn"))
            plan.note(f"{plan.name(ctx['controller'])} may cast {card.name} by waterbending {{{mv}}} during their turn", [card.id])
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"hama110b": hama}
RESUME = {"hama110b": resume_hama}
