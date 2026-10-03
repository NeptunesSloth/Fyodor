"""-- untap choice (wave 7F) -- "You may choose not to untap ~ during your untap step." (Hollow Trees, Rubinia
Soulsinger, Vedalken Shackles, Amber Prison …).

502.3: the active player determines which permanents untap; a static ability can let them choose not to untap
some. The choice is made during the untap step, where no player receives priority (502.4), so it is a
decision asked of the new active player right after the turn changes and before anything untaps: the engine
keeps the permanents that have the ability and are tapped, controlled by that player, tapped for the turn
change, asks which to keep tapped (none picked: all untap) and untaps the rest. The static is the rule
``may_stay_tapped`` (app/rules/statics.py); a permanent that stays tapped for another reason (exerted, "doesn't
untap", a skipped untap step) isn't asked. 122.1d: a stunned permanent that would untap loses a stun counter
instead, so one that is kept tapped keeps its counter.
"""

from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import scripts
from app.rules.plan import Plan, decide

# "Tap target creature. It doesn't untap during its controller's untap step for as long as ~ remains tapped." (611.2b):
# a rule-modifying restriction (``doesnt_untap``, read by engine._keep_tapped) that lasts while the source stays tapped.
_HOLD = re.compile(r"^(?P<o>.+?) doesn't untap during its controller's untap step for as long as (?P<d>~ remains tapped|you control ~)$")
# -- as long as (wave 9B) -- "… for as long as you control ~" (Ty Lee, Icefall Regent, Dungeon Geists): 611.2b, ends when
# the source leaves the battlefield or another player controls it (delayed.py "source_controlled")
_DURATION = {"~ remains tapped": "source_tapped", "you control ~": "source_controlled"}


def _hold(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    try:
        kind, key, group = language.ref(m["o"])
    except language._Fail:
        raise scripts._NoMatch from None
    if kind not in ("it", "them", "target", "self"):  # (a named object: 611.2c, a mass wording would be a set)
        raise scripts._NoMatch
    return [{"do": "until", "duration": _DURATION[m["d"]], "n": 1},
            {"do": "restrict", "who": language._who(kind, key), "rules": ["doesnt_untap"]}], language._one(group)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_HOLD, _hold)]


def candidates(plan: Plan, player: str, keep: list[str]) -> list[str]:
    """Tapped permanents ``player`` controls that they may choose not to untap and that would untap otherwise."""
    return [c.id for c in plan.state.cards.values()
            if c.tapped and c.controller == player and c.zone.endswith(":battlefield") and c.id not in keep
            and not plan.manual(c) and "may_stay_tapped" in scripts.statics(plan.ch(c))][:50]


def ask(plan: Plan, asked: list[str], then: dict[str, object]) -> bool:
    """Ask the active player which of ``asked`` stay tapped; True when the untap step waits for the answer."""
    asked = [c for c in asked if plan.state.cards[c].controller == plan.active]
    if not asked:
        return False
    decide(plan, player=plan.active, kind="choose_cards",
           prompt="Untap step: choose the permanents to keep tapped (the others untap)",
           options=[DecisionOption(id=c, label=f"Keep {plan.state.cards[c].name or 'permanent'} tapped", card_id=c)
                    for c in asked],
           min_choices=0, max_choices=len(asked), resume={"step": "untap_keep", "asked": asked, **then})
    return True


def resume(plan: Plan, d: object, chosen: list[str]) -> None:
    from app.rules import effects, engine

    r = d.resume  # type: ignore[attr-defined]
    asked: list[str] = r["asked"]
    let_go = [c for c in asked if c not in chosen and c in plan.state.cards]
    stuck = effects.keyword_actions.stunned(plan, let_go)  # 122.1d (the counter comes off in finish_turn_start)
    keep = [c for c in r["keep"] if c not in asked] + [c for c in chosen if c not in r["keep"]] + stuck
    if plan.state.settings.auto_untap:
        free = [c for c in let_go if c not in stuck]
        if free:
            plan.do({"type": "tap", "card_ids": free, "tapped": False}, actor=plan.active)
    for c in chosen:
        plan.note(f"{plan.state.cards[c].name or 'It'} stays tapped (it isn't untapped during the untap step)", [c], actor=plan.active)
    engine.finish_turn_start(plan, [*r["stunned"], *stuck], (r["previous"][0], r["previous"][1]),
                             [(p, n) for p, n in r["skipped"]], r["plain"], keep)
