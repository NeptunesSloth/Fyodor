"""-- hand size (wave 4J) -- "You have no maximum hand size." (Reliquary Tower, Thought Vessel, Decanter of Endless
Water). Researched against CR 2026-09-25.

* 402.2: each player has a maximum hand size, normally seven; as part of their cleanup step (514.1) the active player
  discards down to it. A static ability of a permanent saying its controller has no maximum hand size removes that
  discard while the permanent is on the battlefield under their control (611.3a: a static ability's effect applies
  while the object is on the battlefield).
* -- static statics (wave 10B) -- "Your maximum hand size is reduced by four." (Thought Devourer), "… is increased by two."
  (Trusted Advisor), "Each opponent's maximum hand size is reduced by seven." (Jin-Gitaxias, Core Augur) and "Players have
  no maximum hand size." (Price of Knowledge): reductions and increases add up (they commute), never below zero; no
  maximum ignores deltas but a later fixed setting overrides it (402.2,613.10). -- static_other sweep (wave 16B) -- A SET
  maximum of a permanent ("Your maximum hand size is eleven.": Cecily, The Ten Rings) is applied with the others in the
  order of the permanents' timestamps (613.7d: the later effect wins). Chosen players use their source's stable player-ID choice; resolved no-maximum effects retain their timestamp.

Read by the cleanup step (app/rules/engine.cleanup_step).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

NO_MAXIMUM = "no_max_hand"
MAX_HAND_SIZE = 7  # 402.2


MODIFIES = "max_hand_size"
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "twenty": 20}  # (wave 51C: Twenty-Toed Toad)
_SET = re.compile(r"^Your maximum hand size is (?P<n>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|\d+)\.$")
_CHANGE = re.compile(r"^(?P<who>Your|Each opponent's) maximum hand size is (?P<dir>reduced|increased) by "
                     r"(?P<n>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\.$")


def static_definition(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if t == "You have no maximum hand size.":
        return {"kind": "static", "static": NO_MAXIMUM, "effects": []}
    if t == "You have no maximum hand size and don't lose the game for having 0 or less life.":  # -- most-played cards III (wave 46C) -- Marina Vendrell's Grimoire (game_result.zero_life_ok)
        return {"kind": "static", "static": NO_MAXIMUM, "zero_life": True, "effects": []}
    if t == "Players have no maximum hand size.":  # -- static statics (wave 10B) --
        return {"kind": "static", "static": NO_MAXIMUM, "who": "each", "effects": []}
    dynamic = re.fullmatch(r"(?P<who>Your|Each opponent's) maximum hand size is equal to (?P<v>.+)\.", t)
    if dynamic is not None:
        from app.rules import values

        value = values.parse_count(dynamic['v'].replace('those card types', 'card types among cards in your graveyard'), it='self')
        if value is not None:
            return {'kind': 'static', 'static': MODIFIES, 'who': 'you' if dynamic['who'] == 'Your' else 'opponents',
                    'set': value, 'effects': []}
    chosen = re.fullmatch(r"The chosen player's maximum hand size is (four|\d+)\.", t)
    if chosen is not None:
        return {"kind": "static", "static": MODIFIES, "who": "chosen", "set": 4 if chosen[1] == "four" else int(chosen[1]), "effects": []}
    if (s := _SET.match(t)) is not None:
        return {"kind": "static", "static": MODIFIES, "who": "you", "set": _NUMBERS[s["n"]] if s["n"] in _NUMBERS else int(s["n"]),
                "effects": []}
    m = _CHANGE.match(t)
    if m is None:
        return None
    n = _NUMBERS[m["n"]] if m["n"] in _NUMBERS else int(m["n"])
    return {"kind": "static", "static": MODIFIES, "who": "you" if m["who"] == "Your" else "opponents",
            "delta": -n if m["dir"] == "reduced" else n, "effects": []}


def _applies(d: dict[str, Any], controller: str, player: str) -> bool:
    who = d.get("who", "you")
    return who == "each" or (who == "you" and controller == player) or (who == "opponents" and controller != player)


def bound_legacy(plan: Plan) -> None:
    """Record only what is known on first native action: old effects already exist now."""
    for player in plan.rules.no_max_hand:
        if player not in plan.rules.no_max_hand_at:
            plan.rules.no_max_hand_legacy_bound.setdefault(player, plan.rules.next_object)


def maximum(plan: Plan, player: str, *, warn_legacy: bool = False) -> int | None:
    """Apply setting/no-maximum/delta effects in timestamp order (402.2,613.10)."""
    from app.rules import chosen, scripts, statics, values
    from app.rules.layers import timestamp
    from app.rules.replace import conditional_lines

    # Source timestamps and resolved effects share the object sequence axis.
    entries: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    legacy = player in plan.rules.no_max_hand and player not in plan.rules.no_max_hand_at
    bound = plan.rules.no_max_hand_legacy_bound.get(player, plan.rules.next_object)
    ambiguous = False
    for c in plan.state.cards.values():
        emblem = c.zone.endswith(":command") and c.token is not None and c.token.type_line == "Emblem"
        if not (c.zone.endswith(":battlefield") or emblem) or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or d.get("static") not in (NO_MAXIMUM, MODIFIES):
                continue
            applies = chosen.player_of(plan, c.id) == player if d.get('who') == 'chosen' else _applies(d, c.controller, player)
            if not applies or not statics.static_if_holds(plan, d, c):
                continue
            stamp = timestamp(plan.state, c.id)
            if legacy and stamp <= bound and 'set' in d:
                ambiguous = True
            if 'set' in d and isinstance(d['set'], dict):
                d = {**d, 'set': values.evaluate(plan, {'controller': c.controller, 'source_card': c.id, 'source_object': plan.oid(c)}, d['set'])}
            entries.append(((stamp, 0, i), d))
    if player in plan.rules.no_max_hand_at:
        seq, at = plan.rules.no_max_hand_at[player]
        entries.append(((seq, 1, at), {'static': NO_MAXIMUM}))
    elif legacy:
        # Keep legacy behavior against already-existing effects of unknown order;
        # effects introduced after this bound are certainly later and may set a limit.
        entries.append(((bound, 1, 0), {'static': NO_MAXIMUM}))
        if warn_legacy and ambiguous:
            key = f'legacy_hand_order:{player}'
            if plan.rules.once_per_turn.get(key) != plan.state.turn.number:
                plan.rules.once_per_turn[key] = plan.state.turn.number
                plan.note('This older save has an untimestamped no-maximum-hand-size effect. Its order against preexisting fixed limits cannot be recovered; legacy behavior is preserved. Later native effects use their known order.', actor=player)
    for effect in plan.rules.effects:
        limit = effect.hand_limit
        if limit is not None and limit.player == player:
            d = {'static': NO_MAXIMUM} if limit.kind == 'none' else {'static': MODIFIES, limit.kind: limit.value}
            entries.append(((effect.object_seq, 1, effect.timestamp), d))
    size: int | None = MAX_HAND_SIZE
    for _, d in sorted(entries, key=lambda entry: entry[0]):
        if d['static'] == NO_MAXIMUM:
            size = None
        elif 'set' in d:
            size = int(d['set'])
        elif size is not None:
            size += int(d['delta'])
    return max(0, size) if size is not None else None


def no_maximum(plan: Plan, player: str) -> bool:
    """Whether a permanent gives ``player`` no maximum hand size (402.2)."""
    return maximum(plan, player) is None


# -- ability words (wave 20C) -- "You have no maximum hand size for the rest of the game." (Praetor's Counsel, Ancient Silver Dragon):
# 611.2a: a continuous effect from a resolving ability that changes the rules lasts "for the rest of the game"; it doesn't depend on
# the object (610.3) and works for the player who got it, whatever leaves (``RulesState.no_max_hand``, read by ``maximum``).
TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^you have no maximum hand size until your next turn$"), lambda m: ([{"do": "hand_limit", "kind": "none", "duration": "next_turn"}], None)),
    (re.compile(r"^your maximum hand size is reduced by (?P<n>three|\d+) for the rest of the game$"), lambda m: ([{"do": "hand_limit", "kind": "delta", "value": -3 if m["n"] == "three" else -int(m["n"])}], None)),
    (re.compile(r"^you have no maximum hand size for the rest of the game$"), lambda m: ([{"do": "no_max_hand"}], None))]


def no_max_hand(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    who = str(ctx["controller"])
    if who not in plan.rules.no_max_hand:
        plan.rules.no_max_hand.append(who)
    plan.rules.timestamp += 1
    plan.rules.no_max_hand_at[who] = (plan.rules.next_object, plan.rules.timestamp)
    plan.rules.no_max_hand_legacy_bound.pop(who, None)
    plan.note(f"{plan.name(who)} has no maximum hand size for the rest of the game", actor=who)
    return True


def hand_limit(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import HandLimitModifier
    from app.rules import layers

    duration = e.get('duration', 'permanent')
    effect = layers.add_effect(plan, affected=[], layer='6', source=ctx.get('source_object'), controller=ctx['controller'],
                               duration=duration, label='Maximum hand size',
                               hand_limit=HandLimitModifier(player=ctx['controller'], kind=e['kind'], value=e.get('value', 0)))
    if duration == 'next_turn':
        effect.until_player, effect.turn = ctx['controller'], plan.state.turn.number
    plan.note('Maximum hand size changes ' + ('until your next turn' if duration == 'next_turn' else 'for the rest of the game'), actor=ctx['controller'])
    return True


PRIMITIVES = {"no_max_hand": no_max_hand, "hand_limit": hand_limit}
