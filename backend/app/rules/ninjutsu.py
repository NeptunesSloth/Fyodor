"""-- keywords (wave 15E) -- ninjutsu (CR 702.49): "Ninjutsu {cost}" means "{cost}, Reveal this card from your hand, Return an
unblocked attacking creature you control to its owner's hand: Put this card onto the battlefield from your hand tapped and
attacking." (702.49a)

* An activated ability that works only while the card is in its owner's hand (702.49a), so it can be activated whenever its
  controller has priority once an attacking creature of theirs is unblocked (declare blockers step or later in combat, 509.1h;
  before blockers are declared no attacker is unblocked yet).
* The card is revealed as the ability is announced and stays revealed until the ability leaves the stack (702.49b): it is
  revealed to everyone as it is put on the stack (the ability resolving puts it onto the battlefield, public anyway).
* The creature enters attacking the same player, planeswalker or battle as the one returned (702.49c): the cost records what the
  returned creature attacked (``PaymentRecord.returned_attacking``); if that is gone by then, it enters but isn't attacking
  (506.3e/508.4a). It enters as any permanent put onto the battlefield (entry choices, replacements, enters triggers) and is
  never declared as an attacker (508.4, no attack triggers).
* Commander ninjutsu (702.49d, wave 50J): the same ability, which can also be activated from the command zone (the card is public there: no reveal).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules.oracle import AbilityText

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics

_LINE = re.compile(r"^(?:commander )?ninjutsu (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
RETURN = "Return an unblocked attacking creature you control to its owner's hand"
STEPS = ("declare_blockers", "combat_damage", "end_combat")  # after blockers are declared (509.1h), while attackers remain


def cost_of(ch: Characteristics, index: int, *, command: bool = False) -> str | None:
    """The mana cost of the ninjutsu keyword on ability line ``index`` (a line that is that keyword alone), or None. ``command``: only a commander ninjutsu (702.49d) counts."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords" and ("commander ninjutsu" in ab.keywords or (not command and "ninjutsu" in ab.keywords)):
            m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", ab.text).strip().rstrip("."))
            return m["cost"] if m else None
    return None


def supported(line: str) -> bool:
    return _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")) is not None


def ability(ch: Characteristics, index: int, cost: str) -> AbilityText:
    """The activated ability 702.49a says the keyword is (its reveal is done by :func:`revealed`)."""
    return AbilityText(index=index, kind="activated", cost=f"{cost}, {RETURN}",
                       text=f"Ninjutsu {cost}, {RETURN}: Put {ch.name} onto the battlefield from your hand tapped and attacking.")


DEFINITION: dict[str, Any] = {"kind": "activated", "effects": [{"do": "ninjutsu_enter"}], "target": None}


def is_ninjutsu(text: str) -> bool:
    return text.startswith("Ninjutsu ")


def problem(state: GameState, player: str, card: CardInstance) -> str | None:
    """Why this ninjutsu ability can't be activated now (the cost's own checks come from ability_problem)."""
    if card.zone != f"{player}:hand" and not (card.zone == f"{player}:command" and card.commander_key is not None) or card.owner != player:
        return "Ninjutsu works only from your hand (commander ninjutsu: or the command zone)"  # 702.49a, 702.49d
    if state.turn.phase not in STEPS:
        return "Ninjutsu needs an unblocked attacking creature: wait until blockers have been declared"
    return None


def enter(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The ability's effect: the card from the hand onto the battlefield tapped and attacking what the returned creature attacked."""
    from app.rules import attachments

    pid = ctx["controller"]
    cid = ctx.get("source_card") or ""
    card = plan.state.cards.get(cid)
    if card is None or card.zone not in (f"{pid}:hand", f"{pid}:command") or card.owner != pid or plan.oid(card) != ctx.get("source_object"):
        return True  # 400.7: it isn't in the hand (or command zone) any more (or is a new object): nothing to put
    sid = ctx.get("stack_id")
    record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
    plan.do({"type": "hide", "card_ids": [cid]}, actor=pid)
    if not attachments.enter(plan, [{"card": cid, "player": pid, "actor": pid, "tapped": True}], ctx):
        return False
    attack_returned(plan, cid, record, pid)  # 702.49c
    return True


def attack_returned(plan: Any, cid: str, record: Any, pid: str) -> None:
    """The creature ``cid`` just entered: attacking what the creature returned to pay for it was attacking (702.49c, sneak 702.190b);
    if that is gone by now it isn't attacking (508.4a), and a noncreature permanent never is (506.3a)."""
    from app.rules.token_grammar import _attack_with

    target = next(iter((record.returned_attacking if record is not None else {}).values()), None)
    entered = plan.state.cards.get(cid)
    if entered is not None and entered.zone.endswith(":battlefield") and plan.ch(entered).is_creature and target is not None and (
            target in plan.live() or (target in plan.state.cards and plan.state.cards[target].zone.endswith(":battlefield"))):
        _attack_with(plan, [cid], target, pid)
