"""Target selectors and legality (CR 115, 601.2c, 608.2b).

A target is chosen when a spell is cast or an ability is put on the stack, and checked again on
resolution: a target that left its zone (it is a new object) or no longer matches is illegal,
and if every target is illegal the spell or ability does nothing (608.2b). Hexproof and shroud
(702.11, 702.18) and protection (702.16) are checked here. The server computes the legal choices; the chooser gets them
in their private decision, nobody else does.
"""

from __future__ import annotations

from collections.abc import Callable

from app.game.rules_state import TargetRef
from app.game.state import CardInstance
from app.rules import protection
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan

Check = Callable[[Plan, str, CardInstance, Characteristics], bool]


def _types(*types: str) -> Check:
    return lambda plan, who, card, ch: bool(ch.types & set(types))


SELECTORS: dict[str, tuple[bool, Check | None]] = {
    # selector: (players allowed, permanent check or None for "no permanents")
    "any": (True, _types("Creature", "Planeswalker", "Battle")),
    "creature": (False, _types("Creature")),
    "creature_you_control": (False, lambda plan, who, card, ch: ch.is_creature and card.controller == who),
    "creature_opponent_controls": (False, lambda plan, who, card, ch: ch.is_creature and card.controller != who),
    "creature_or_planeswalker": (False, _types("Creature", "Planeswalker")),
    "artifact": (False, _types("Artifact")),
    "enchantment": (False, _types("Enchantment")),
    "artifact_or_enchantment": (False, _types("Artifact", "Enchantment")),
    "land": (False, _types("Land")),
    "planeswalker": (False, _types("Planeswalker")),
    "permanent": (False, lambda plan, who, card, ch: True),
    "nonland_permanent": (False, lambda plan, who, card, ch: not ch.is_land),
    "attacking_or_blocking_creature": (False, lambda plan, who, card, ch: ch.is_creature
                                       and (card.attacking is not None or bool(card.blocking))),
    "attacking_creature": (False, lambda plan, who, card, ch: ch.is_creature and card.attacking is not None),
    "blocking_creature": (False, lambda plan, who, card, ch: ch.is_creature and bool(card.blocking)),
    "player": (True, None),
    "opponent": (True, None),
}


def can_target(plan: Plan, chooser: str, card: CardInstance, ch: Characteristics,
               source: Characteristics | None = None) -> bool:
    """Hexproof: not by opponents; shroud: by nobody; protection: not by a source with that quality."""
    if "shroud" in ch.keywords:
        return False
    if "hexproof" in ch.keywords and card.controller != chooser:
        return False
    return not protection.protected_from(ch, source)


def legal_targets(plan: Plan, selector: str, chooser: str, source: Characteristics | None = None) -> list[str]:
    """Player ids and card ids that ``chooser`` may target with ``selector`` right now
    (``source``: the spell or the ability's source, for protection)."""
    players_ok, check = SELECTORS[selector]
    out: list[str] = []
    if players_ok:
        for pid in plan.live():
            if selector == "opponent" and pid == chooser:
                continue
            out.append(pid)
    if check is not None:
        for card in plan.state.cards.values():
            if not card.zone.endswith(":battlefield") or not plan.in_game(card):
                continue
            ch = plan.ch(card)
            if check(plan, chooser, card, ch) and can_target(plan, chooser, card, ch, source):
                out.append(card.id)
    return out


def ref(plan: Plan, target: str) -> TargetRef:
    return TargetRef(id=target, object_id=plan.oid(target) if target in plan.state.cards else None)


def still_legal(plan: Plan, selector: str, chooser: str, target: TargetRef, source: Characteristics | None = None) -> bool:
    """608.2b: is a chosen target still legal? A card that changed zones is a new object: illegal."""
    if target.object_id is None:
        return target.id in plan.live() and target.id in legal_targets(plan, selector, chooser, source)
    card = plan.state.cards.get(target.id)
    if card is None or plan.oid(card) != target.object_id:
        return False
    return target.id in legal_targets(plan, selector, chooser, source)


def source_of(plan: Plan, card_id: str | None) -> Characteristics | None:
    """The characteristics of a spell or of an ability's source, for protection checks."""
    card = plan.state.cards.get(card_id or "")
    return plan.ch(card) if card is not None else None


def label(plan: Plan, target: str) -> str:
    if target in plan.state.players:
        return plan.name(target)
    card = plan.state.cards.get(target)
    return card.name if card else "?"
