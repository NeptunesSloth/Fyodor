"""-- licids (wave 50A) -- "{W}, {T}: This creature loses this ability and becomes an Aura enchantment with enchant creature. Attach it to target
creature. You may pay {W} to end this effect." (the twelve Commander-legal Licids), researched against CR 2026-09-25.

* The ability's resolution is one continuous effect without a duration (611.2a: until it is ended) with two parts: layer 4 (613.1d, 205.1a) the
  Licid is an Aura enchantment and no longer a creature (nor an artifact: Transmogrifying Licid), so its creature type drops with it; layer 6
  (613.1f) it loses the activated ability it was activated from ("this ability": only that one, its "Enchanted creature …" lines stay) and has
  enchant creature (702.5). Then it is attached to the target (701.3: ``attachments.attach``; one that can't be attached there doesn't move and the
  Aura goes to the graveyard, 704.5m; a target that is illegal on resolution means none of it happens, 608.2b).
* "You may pay {W} to end this effect" (116.2c): a special action any time its controller has priority, not on the stack (so it can't be responded to):
  the effect ends, the Licid is the creature it was again, and as one that is attached it becomes unattached (704.5p). ``end_effect``. "You" is the player who
  controlled the ability (``ContinuousEffect.controller``), whoever controls the Licid later; two resolutions are two effects, the latest ends first.
* Enchanted-creature lines are the host's whenever the Licid is attached to it, which only an Aura can be (704.5p): a creature Licid has none.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game import actions as A
from app.game.errors import ActionError
from app.rules.plan import Plan, require_no_decision, require_priority

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState

Context = dict[str, Any]
THIS_ABILITY = "loses this ability and becomes an Aura enchantment with enchant creature"
_COST = r"(?P<cost>(?:\{[^}]+\})+)"
_TEXT = re.compile(rf"(?P<lead>^\s*|\. )(?:~|[Tt]his creature) {THIS_ABILITY}\. Attach it to (?P<tgt>target creature)\. You may pay {_COST} to end this effect\.")
_ONE = re.compile(rf"^~ becomes an Aura enchantment attached to target creature until you pay {_COST} to end this effect$")


def rewrite(body: str) -> str:
    """The three sentences as the one the template below reads ("Attach it" names the Licid, which no pronoun binding would)."""
    return _TEXT.sub(lambda m: f"{m['lead']}~ becomes an Aura enchantment attached to {m['tgt']} until you pay {m['cost']} to end this effect.", body)


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.attach_abilities import _group

    return [{"do": "licid", "end": m["cost"]}], _group("target creature", kinds=("Creature",))


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_ONE, _build)]


def licid(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The resolution: the Licid (still the object that was activated, 400.7) becomes the Aura and is attached to the target; ``end`` is the cost of ending it."""
    from app.rules import attachments, effects

    cards, hosts = effects._cards(plan, ctx, "self"), effects._cards(plan, ctx, "target")
    if not cards or not hosts:  # (400.7: the Licid left; 608.2b: the target is gone and the ability did nothing)
        return True
    card = plan.state.cards[cards[0]]
    gone = [a.index for a in plan.ch(card).abilities if a.kind == "activated" and THIS_ABILITY in a.text]
    before = len(ctx.get("animated") or ())
    effects.become(plan, ctx, {"who": "self", "types": ["Enchantment"], "add_creature_types": ["Aura"], "abilities": ["Enchant creature"],
                               "lose_index": gone, "duration": "permanent",
                               "marker": f"until its controller pays {e['end']} to end this effect"})
    made = [x for x in plan.rules.effects if x.id in ctx["animated"][before:]]
    for x in made:
        x.end_cost, x.end_group = e["end"], made[0].timestamp
    attachments.attach(plan, card.id, hosts[0], ctx["controller"])
    return True


def ending(state: GameState, card: CardInstance, player: str) -> list[Any]:
    """The effects ``player`` may pay to end on this permanent (the latest resolution's), or [] (116.2c)."""
    r = state.rules
    found = [x for x in r.effects if x.end_cost and x.controller == player and r.object_id(card.id) in x.affected] if r else []
    return [x for x in found if x.end_group == max(y.end_group for y in found)]


def end_effect(plan: Plan, a: A.EndEffect) -> None:
    """116.2c: the special action - pay the cost, the effect ends (any time the player has priority; it doesn't use the stack)."""
    from app.rules import delayed, layers
    from app.rules import mana as M
    from app.rules.casting import Purpose, pay, payment_step

    require_no_decision(plan)
    require_priority(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None or not card.zone.endswith(":battlefield") or not (effects := ending(plan.state, card, plan.actor)):
        raise ActionError("There is no effect of yours to end on that permanent")
    cost = M.parse_cost(effects[0].end_cost or "")
    if payment_step(plan, a, cost, f"ending the effect on {card.name}", purpose=Purpose()):
        return
    pay(plan, plan.actor, cost, f"paid {cost.text()} to end the effect on {card.name}", sources=a.sources, purpose=Purpose())
    delayed._end(plan, effects)
    layers.control_sync(plan)
    plan.note(f"{plan.name(plan.actor)} ends the effect on {card.name}", [card.id])
    plan.rules.passed = []
