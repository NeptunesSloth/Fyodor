"""-- rules imposed on a permanent (wave 110D) -- "can't become untapped", "can't transform", "can't be turned face up", read where the engine does it.

* 701.26 / 502.3 (CR 2026-09-25): a permanent that "can't become untapped" is never untapped (the untap step, an untap effect, an untap cost);
  nothing is replaced, so a stun counter stays on it (122.1d only replaces an untapping that would happen).
* 701.27 / 701.28f: a permanent that "can't transform" doesn't transform or convert (an ability, a daybound or nightbound flip).
* 708.2 / 701.40: "can't be turned face up" bars both the special action and the effects that turn a permanent face up.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

CANT_UNTAP, CANT_TRANSFORM, CANT_FACE_UP = "cant_untap", "cant_transform", "cant_turn_face_up"


def has_rule(plan: Plan, card: CardInstance | str, rule: str) -> bool:
    from app.rules import scripts

    c = plan.state.cards.get(card) if isinstance(card, str) else card
    return c is not None and c.zone.endswith(":battlefield") and rule in scripts.statics(plan.ch(c))


def untappable(plan: Plan, card_ids: list[str]) -> list[str]:
    return [c for c in card_ids if not has_rule(plan, c, CANT_UNTAP)]


def face_up_barred(plan: Plan, card: CardInstance) -> str | None:
    return f"{card.name or 'A permanent'} can't be turned face up" if has_rule(plan, card, CANT_FACE_UP) else None


RULES: dict[str, tuple[str, ...]] = {
    "can't become untapped": (CANT_UNTAP,),
    "can't transform": (CANT_TRANSFORM,),
    "can't attack, block, or transform": ("cant_attack_or_block", CANT_TRANSFORM),
    "can't become untapped and can't have counters put on it": (CANT_UNTAP, "cant_counters_host110d"),
    "can't be turned face up": (CANT_FACE_UP,),
}


# "When ~ enters, tap target creature an opponent controls. That creature can't become untapped for as long as you control ~." (Spider-Woman): the
# duration of "doesn't untap during its controller's untap step for as long as you control ~" (611.2b, untap_choice._hold), with the rule of 701.26
_HOLD = re.compile(r"^(?P<o>that creature) can't become untapped for as long as (?P<d>you control ~)$")


def _hold(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import untap_choice

    effects, group = untap_choice._hold(m)
    return [effects[0], {**effects[1], "rules": [CANT_UNTAP]}], group


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_HOLD, _hold)]
