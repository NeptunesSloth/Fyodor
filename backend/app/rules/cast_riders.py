"""-- cast riders (wave 25C) -- "When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it."
(Kumano Faces Kakkazan, Summon: Fenrir, Long List of the Ents) and "…, it gains haste until end of turn." (Summon: Brynhildr): a turn
watch (app/rules/watches.py, 603.7) whose deferred effect changes the spell it triggered on, researched against CR 2026-09-25.

* 603.7c / 608.2k: the delayed trigger goes on the stack above the creature spell that triggered it, and "that creature" is that spell,
  still on the stack when it resolves; once the spell has resolved (or is gone: countered, a new object, 400.7) the effect does nothing.
* 614.1c: "enters with an additional +1/+1 counter" is a replacement effect of the permanent entering; 613.1f / 611.2a: "gains haste until
  end of turn" is a continuous effect from the moment it enters. Both are riders on the spell's payment record
  (``PaymentRecord.mana_riders``, kinds "counter" and "haste": the same ones mana of a Cavern or a Hall carries, app/rules/mana_units.py,
  106.6), which the entering permanent reads as it enters (``mana_units.entering_counters`` / ``entered``). One rider per counter.
* A watched instant or sorcery may instead gain rebound on the stack. A layer-6 grant makes the keyword visible; the native rebound marker applies only if that exact spell was cast from hand and later resolves successfully (702.88a).
* Only a creature spell: the watch's spell selector must say so ("a creature spell", "a Bird creature spell"), else "that creature" would
  name no creature (the sentence stays manual).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_NUMBERS = {"an": 1, "one": 1, "two": 2, "three": 3}
_COUNTERS = re.compile(r"^(?:that creature|it) enters with (?P<n>an|one|two|three) additional \+1/\+1 counters? on it$", re.IGNORECASE)
_HASTE = re.compile(r"^(?:that creature|it) gains haste until end of turn$", re.IGNORECASE)


def _creature_spell_watch(cond: dict[str, Any] | None) -> bool:
    from app.rules import selectors

    if cond is None or cond.get("event") != "cast" or cond.get("subject") != "player" or cond.get("player") != "you":
        return False
    key = cond.get("spell")
    sel = selectors.from_key(key) if isinstance(key, str) and key.startswith(selectors.PREFIX) else None
    return sel is not None and sel.types == ("Creature",) and not sel.union and not sel.not_types and sel.zones == ("stack",)


def _rebound_spell_watch(cond: dict[str, Any] | None) -> bool:
    from app.rules import selectors

    if cond is None or cond.get('event') != 'cast' or cond.get('subject') != 'player' or cond.get('copy'):
        return False
    key = cond.get('spell')
    sel = selectors.from_key(key) if isinstance(key, str) and key.startswith(selectors.PREFIX) else None
    return bool(sel is not None and sel.types and set(sel.types) <= {'Instant', 'Sorcery'}
                and sel.zones == ('stack',) and not sel.either and not sel.union and not sel.not_types)


def parse(cond: dict[str, Any] | None, clause: str) -> tuple[list[dict[str, Any]], None] | None:
    """The deferred effect of a "when you next cast a creature spell this turn" watch that changes the spell, or None."""
    text = clause.strip().rstrip(".")
    if text.lower() == "it gains rebound" and _rebound_spell_watch(cond):
        return [{"do": "spell_rider", "who": "event_spell", "keyword": "rebound"}], None
    timed = re.fullmatch(r"(?:it|that creature) enters with an additional \+1/\+1 counter on it and gains (?P<keyword>hexproof|haste) until your next turn", text, re.IGNORECASE)
    if timed is not None and _creature_spell_watch(cond):
        return [{"do": "spell_rider", "who": "event_spell", "riders": [
            {"kind": "counter"}, {"kind": "keyword", "keyword": timed['keyword'].lower(), "until": "next_turn"}]}], None
    if (m := _COUNTERS.fullmatch(text)) is not None and _creature_spell_watch(cond):
        return [{"do": "spell_rider", "who": "event_spell", "riders": [{"kind": "counter"}] * _NUMBERS[m["n"].lower()]}], None
    if _HASTE.fullmatch(text) is not None and _creature_spell_watch(cond):
        return [{"do": "spell_rider", "who": "event_spell", "riders": [{"kind": "haste", "until": "end_of_turn"}]}], None
    return None


def spell_rider(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The deferred effect: the creature spell the watch triggered on (while it is still that spell on the stack) gets the riders."""
    from app.rules import copying, values

    times = max(0, values.evaluate(plan, ctx, e["n"])) if "n" in e else 1  # (wave 47D: "for each …", "X additional counters": read as the trigger resolves, 608.2h)
    for sid in copying._stack_objects(plan, ctx, e["who"]):
        rec = plan.rules.payments.get(plan.oid(sid))
        if e.get('keyword') == 'sunburst':
            from app.rules import layers

            layers.add_effect(plan, affected=[plan.oid(sid)], layer='6', source=ctx.get('source_object'),
                              controller=ctx['controller'], add_abilities=['Sunburst'], duration='permanent', label='Sunburst')
            continue
        if e.get("keyword") == "rebound":
            from app.rules import layers

            oid = plan.oid(sid)
            layers.add_effect(plan, affected=[oid], layer="6", source=ctx.get("source_object"),
                              controller=ctx["controller"], add_keywords=("rebound",), duration="permanent", label="Rebound")
            # Rebound replaces only a successful resolution of a spell cast from hand.
            if rec is not None and rec.cast_from == "hand" and "rebound" in plan.ch(plan.state.cards[sid]).keywords and oid not in plan.rules.rebound_cast:
                plan.rules.rebound_cast.append(oid)
            continue
        if rec is not None:  # (a spell moved onto the stack by hand has no record: nothing to carry the rider)
            riders = []
            for rider in e["riders"] * times:
                item = {**rider, "name": ctx.get("name") or ""}
                if rider.get('kind') == 'granted_ability' and rider.get('ability') == 'dies_exile_self':
                    from app.rules import spell_ability_riders42

                    item['src'] = ctx.get('source_object')
                    spell_ability_riders42.grant(plan, sid, item, ctx['controller'])
                if rider.get("kind") == "keyword" and rider.get("until") == "next_turn":
                    item.update(until_player=ctx['controller'], turn=plan.state.turn.number,
                                turns_taken=values.evaluate(plan, ctx, {"turns_taken": 1}))
                riders.append(item)
            rec.mana_riders = [*rec.mana_riders, *riders]
    return True


PRIMITIVES = {"spell_rider": spell_rider}
