"""-- gift (wave 23D) -- Gift (CR 702.174), researched against the stored Comprehensive Rules (2026-09-25).

* 702.174a: "Gift a [something]" is two abilities. The first, "As an additional cost to cast this spell, you may choose an opponent", is
  announced with the other optional additional costs (601.2b; ``cost_changes.optional_offers``, the intent's ``optional_costs``) and the
  caster names the opponent (``CastSpell.gift_to``; asked as a decision when more than one opponent could be chosen, like assist's helper).
  The chosen opponent is kept in the spell's payment record (``PaymentRecord.gift_to``, carried to the permanent it becomes).
* 702.174b / 702.174k: the second ability is "When this permanent enters, if its gift cost was paid, [effect]" on a permanent, and "If this
  spell's gift cost was paid, [effect]" on an instant or sorcery; the spell was "promised" the gift. A promised gift is read as the
  spell having been kicked (``record.kicked``, as awaken is): "If the gift was promised, [effect]" / "… instead" and the targets only a
  promised spell chooses (702.174m, like 702.33g) are the kicked machinery's (scripts.self_text writes the wording as it).
* 702.174d-i: the effect is performed by the chosen opponent: a Food / Treasure token, a card drawn, a tapped 1/1 blue Fish, an 8/8 blue
  Octopus. 702.174j: on an instant or sorcery it happens before the spell's other abilities and not at all if the spell is countered or
  leaves the stack. "an extra turn" (702.174g) and "whenever you give a gift" (702.174c) are not modelled: such cards stay manual.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.actions import CastSpell
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

WAITING = object()  # the opponent question was asked: the cast resumes with its answer
GIFT = re.compile(r"^gift (?P<what>a card|a treasure|a food|a tapped fish|an octopus)$", re.IGNORECASE)
_DOES = {"a card": "draws a card", "a treasure": "creates a Treasure token", "a food": "creates a Food token",
         "a tapped fish": "creates a tapped 1/1 blue Fish creature token", "an octopus": "creates an 8/8 blue Octopus creature token"}


def what(text: str) -> str | None:
    """The gift ("a card", "a treasure" …) of one keyword line "Gift a card", or None (unknown gifts, "an extra turn")."""
    m = GIFT.fullmatch(text.strip().rstrip("."))
    return m["what"].lower() if m else None


def own(ch: Characteristics) -> str | None:
    """The one gift this card has (None: none, or several lines: not read)."""
    found = [w for ab in ch.abilities if ab.kind == "keywords" and "gift" in ab.keywords for w in [what(ab.text)]]
    return found[0] if len(found) == 1 and found[0] else None


def has_line(ch: Characteristics) -> bool:
    return any(ab.kind == "keywords" and "gift" in ab.keywords for ab in ch.abilities)


def supported(line: str) -> bool:
    return what(line) is not None


@lru_cache(maxsize=32)
def _definition(w: str, spell: bool) -> str | None:
    """The gift's effect as the grammar reads "[each opponent] draws a card", the recipient the one chosen (``who`` "gifted"); for a spell
    as its leading instructions (guarded by "If this spell was kicked", 702.174j), for a permanent as its enters trigger."""
    from app.rules import scripts
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText

    text = (f"If this spell was kicked, each opponent {_DOES[w]}." if spell else
            f"When this permanent enters, if it was kicked, each opponent {_DOES[w]}.")
    ab = AbilityText(index=0, text=text, kind="spell" if spell else "triggered")
    d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,), types=frozenset({"Sorcery" if spell else "Creature"})))
    if d is None or d.get("kind") != ("spell" if spell else "triggered"):
        return None
    raw = json.dumps(d).replace('"who": "each_opponent"', '"who": "gifted"')
    return raw if '"each_opponent"' not in raw else None


def spell_effects(ch: Characteristics) -> list[dict[str, Any]]:
    """The leading instructions of an instant or sorcery with gift (702.174j), [] when it has none."""
    w = own(ch)
    found = _definition(w, True) if w else None
    return json.loads(found)["effects"] if found else []


def trigger(ch: Characteristics) -> dict[str, Any] | None:
    """The enters trigger of a permanent with gift (702.174b)."""
    w = own(ch)
    found = _definition(w, False) if w and not ch.is_instant_or_sorcery else None
    return json.loads(found) if found else None


def offered(ch: Characteristics) -> bool:
    return own(ch) is not None


def announce(plan: Plan, a: CastSpell, card: CardInstance, ch: Characteristics) -> Any:
    """601.2b: the opponent the gift is promised to (a player id), or WAITING while the caster is asked."""
    from app.rules.plan import decide

    others = [p for p in plan.live() if p != plan.actor]
    if not others:
        raise ActionError("There is no opponent to promise a gift to")
    if a.gift_to is None and len(others) == 1:
        return others[0]
    if a.gift_to is None:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"{ch.name or 'This spell'}: promise the gift to which opponent?",
               options=[DecisionOption(id=p, label=plan.name(p)) for p in others],
               resume={"step": "gift", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)
        return WAITING
    if a.gift_to not in others:
        raise ActionError("Promise the gift to an opponent still in the game")
    return a.gift_to


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.engine import INTENTS

    intent = A.parse_action(d.resume["intent"])
    intent.gift_to = chosen[0]  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def recipient(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    """The opponent the source's gift was promised to (its payment record, kept for the permanent it became)."""
    rec = plan.rules.payments.get(ctx.get("source_object") or "")
    return [rec.gift_to] if rec is not None and rec.gift_to in plan.live() else []
