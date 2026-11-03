"""-- Star Trek statics (wave 111C) -- wordings of the Star Trek sets' static and "as long as" lines (CR 2026-09-25). Hooks: scripts.define
(``definition``), scripts.parse_effects (``parse``), conditions.parse / holds (``condition`` / ``holds``), effects.PRIMITIVES.

* "If you control a Whale and haven't begun an extra turn this game, take an extra turn after this one." (H.M.S. Bounty, Unlikely Timeship):
  500.7, an extra turn is one an effect added; a player has begun one once such a turn of theirs began (engine.start_next_turn records the
  player in ``RulesState.extra_turn_begun111c``). The elided subject of the second half is the first half's "you".
* "If this spell is the first spell you've cast this game" (First Contact): 601.2i, ``RulesState.casts_game111c`` (history.note_cast).
* "If it's a combat phase, you may end the combat phase." (Merciful Mandate, 724.2), a station symbol's ability linked to the card's exiling
  ability (S.S. Botany Bay, 607.1a / 607.2a), Kang's goad for as long as you control it (701.15, 611.2b), Lwaxana Troi's additional triggers
  (603.2d), Sulu's tripled power for stationing and crewing (702.184c, 702.122), Quark's "You can't sacrifice Treasure tokens." (701.21a),
  Vulcan Mind-Meld's two face-down packets (406.3).
"""

from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

_NO_EXTRA = "haven't begun an extra turn this game"

# 721.2a: a station symbol's abilities are "printed on" the permanent (607.1a: printed within the static ability that grants them to it), so one
# that refers to cards "exiled with it" is linked to the card's printed ability that exiles them (607.2a: "return each creature card you own exiled
# with it to the battlefield", S.S. Botany Bay). A quoted grant is otherwise read on its own (scripts.granted_ability), where no exiling ability is.
_STATION_GRANT = re.compile(r'^As long as ~ has (?P<n>\d+) or more charge counters on it, it has "(?P<q>[^"]+)"$')
_PLACEHOLDER = "{T}: Add {C}."


# One-off statics, read as the native wording that means the same.
# 701.21a: a player can sacrifice only permanents they control, so "You can't sacrifice Treasure tokens." (Quark, Humble Proprietor) forbids
# exactly the sacrifices "Treasure tokens you control can't be sacrificed." does (costs and effects alike: prohibitions.sacrifice_forbidden).
_AS: dict[str, str] = {
    "You can't sacrifice Treasure tokens.": "Treasure tokens you control can't be sacrificed.",
}


def _mandate() -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Merciful Mandate: "Untap all creatures you control. If it's a combat phase, you may end the combat phase." — the controller is asked only in a
    combat phase (724.2g: outside one, ending it does nothing); yes ends it as Mandate of Peace does (724.2: wave110a_spells.end_combat_phase)."""
    import copy

    from app.rules import scripts

    found = scripts.parse_effects("Untap all creatures you control. If it's a combat phase, you may draw a card.")
    if found is None or [e["do"] for e in found[0]] != ["untap", "only_if", "may_rest", "draw"]:
        return None
    effects = copy.deepcopy(found[0])
    effects[-1] = {"do": "end_combat_phase110a"}
    return effects, found[1], found[2]


_MIND_MELD_YOU = ("Look at the top two cards of target opponent's library, then exile them face down. You may play them for as long as they remain exiled, "
                  "and mana of any type can be spent to cast them.")


def _mind_meld() -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Vulcan Mind-Meld: "Target opponent looks at the top card of your library, then exiles it face down. You look at the top two cards of their
    library, then exile them face down. For each card exiled this way, the player who exiled it may play it for as long as it remains exiled. Mana
    of any type can be spent to cast spells this way." — the opponent's half as that player (the packet Gonti, Night Minister's controller-of-the-
    creature uses: they look, exile face down, may play it for as long as it remains exiled with mana of any type), then the caster's half as
    Petty Larceny's wording reads it. 406.3: a player who looked at a card and then exiled it face down may go on looking at it."""
    import copy

    from app.rules import scripts

    found = scripts.parse_effects(_MIND_MELD_YOU)
    if found is None or [e["do"] for e in found[0]] != ["look_top", "pick_looked", "grant_play"] or found[1] != "opponent":
        return None
    return [{"do": "mind_meld_opponent_111c"}, *copy.deepcopy(found[0])], found[1], found[2]


def mind_meld_opponent(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    from app.rules import exile_packet_continuations as packets

    opponents = [p for p in effects._players(plan, ctx, "target") if p in plan.live()]
    if not opponents:
        return True
    return packets.insert(ctx, [{"do": "as_player", "player": opponents[0]},
                                {"do": "exile_packet_stage", "binding": packets.BINDING, "mode": "gonti_damage", "stage": "damage_packet",
                                 "owner": ctx["controller"]},
                                {"do": "as_player_end"}])


_BODIES = {
    "Untap all creatures you control. If it's a combat phase, you may end the combat phase.": _mandate,
    "Target opponent looks at the top card of your library, then exiles it face down. You look at the top two cards of their library, then exile them face "
    "down. For each card exiled this way, the player who exiled it may play it for as long as it remains exiled. Mana of any type can be spent to cast "
    "spells this way.": _mind_meld,
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Exact spell bodies (scripts.parse_effects), or None."""
    build = _BODIES.get(body.strip())
    return build() if build is not None else None


# Kang, Suspicious Captain: "When Kang enters, choose target creature an opponent controls. Kang and that creature are goaded for as long as you
# control Kang." — the target as "goad target creature an opponent controls" reads it; then both are goaded by the ability's controller (701.15b)
# with the duration the card gives instead of 701.15a's default (611.2b: it ends the moment you no longer control Kang; if you don't control it as
# the ability resolves, it never begins). 701.15d: one already goaded by you isn't goaded again.
_KANG = "When ~ enters, choose target creature an opponent controls. ~ and that creature are goaded for as long as you control ~."


def _kang(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text="When ~ enters, goad target creature an opponent controls."), ch)
    if d is None or d.get("effects") != [{"do": "goad", "who": "target"}]:
        return None
    return {**d, "effects": [{"do": "goad_while_controlled_111c"}]}


def goad_while_controlled(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import delayed, effects, keyword_actions, layers

    pid = ctx["controller"]
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object") or src.controller != pid:
        return True
    cards = list(dict.fromkeys([*effects._cards(plan, ctx, "target"), src.id]))
    fresh = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")
             and pid not in keyword_actions.goaded_by(plan.ch(plan.state.cards[c]))]
    if not fresh:
        return True
    effect = layers.add_effect(plan, affected=[plan.oid(c) for c in fresh], layer="6", source=ctx["source_object"], controller=pid,
                               imposes=(keyword_actions.GOADED + pid,), label=f"goaded by {plan.name(pid)}")
    effect.duration, effect.until_player, effect.turn, effect.source_card = "source_controlled", pid, plan.state.turn.number, src.id
    effect.markers = delayed.marker_ids(plan.do({"type": "add_effect", "card_ids": fresh, "name": f"Goaded by {plan.name(pid)}"[:60],
                                                 "value": "Goaded", "text": f"for as long as {plan.name(pid)} controls {src.name}"[:120]}))
    plan.note(f"{plan.name(pid)} goads {effects._labels(plan, fresh)}", fresh, actor=pid)
    return True


# Lwaxana Troi, Charming Guest: "{2}, {T}: Choose another target creature you control. For as long as Lwaxana Troi remains tapped, if a triggered
# ability of that creature triggers, that ability triggers an additional time." — the target as "Tap another target creature you control" reads it;
# then a rule on that object (layer 6 marker, locked to it: 611.2c) lasting while Lwaxana stays tapped (611.2b: if she is untapped or gone as it
# resolves it never begins; once she untaps it is over). 603.2d: each instance adds one, for triggered abilities the creature has, not delayed or
# reflexive ones (trigger_multipliers.count, the creature as it is as the ability triggers, or as it last existed: 603.10a).
_LWAXANA = ("{2}, {T}: Choose another target creature you control. For as long as ~ remains tapped, if a triggered ability of that creature triggers, "
            "that ability triggers an additional time.")
AGAIN = "trigger_again_111c:"


def _lwaxana(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text="{2}, {T}: Tap another target creature you control."), ch)
    if d is None or d.get("effects") != [{"do": "tap", "who": "target"}]:
        return None
    return {**d, "effects": [{"do": "trigger_again_while_tapped_111c"}]}


def trigger_again_while_tapped(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import delayed, effects, layers

    pid = ctx["controller"]
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object") or not src.tapped:
        return True
    cards = [c for c in effects._cards(plan, ctx, "target") if plan.state.cards[c].zone.endswith(":battlefield")]
    if not cards:
        return True
    # (one such effect of this Lwaxana at a time: her {T} cost needs her untapped, which ends the one before)
    effect = layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="6", source=ctx["source_object"], controller=pid,
                               imposes=(AGAIN + str(ctx["source_object"]),), label=f"triggers an additional time while {src.name} is tapped")
    effect.duration, effect.turn, effect.source_card = "source_tapped", plan.state.turn.number, src.id
    effect.markers = delayed.marker_ids(plan.do({"type": "add_effect", "card_ids": cards, "name": "Triggers an additional time"[:60],
                                                 "value": "Triggers twice", "text": f"for as long as {src.name} remains tapped"[:120]}))
    plan.note(f"{effects._labels(plan, cards)}'s triggered abilities trigger an additional time while {src.name} remains tapped", cards, actor=pid)
    return True


# Ensign Pavel Chekov: "When Ensign Chekov enters, each opponent exiles the top X cards of their library, where X is the number of differently named
# lands you control. For each opponent, choose a land card that player owns exiled this way. You may play the chosen cards for as long as they
# remain exiled." — the exile as the grammar reads its first sentence (face up: public, 406.3), then the controller's choice for each opponent
# in turn order (101.4) among that player's land cards exiled this way (none: nothing to choose; one: that one), then the permission (611.2a: for
# as long as each remains in exile, a new object once it leaves, 400.7).
_CHEKOV = ("When ~ enters, each opponent exiles the top X cards of their library, where X is the number of differently named lands you control. For each "
           "opponent, choose a land card that player owns exiled this way. You may play the chosen cards for as long as they remain exiled.")
_CHEKOV_EXILE = "When ~ enters, each opponent exiles the top X cards of their library, where X is the number of differently named lands you control."
_CHEKOV_BIND = "exiled111c"


def _chekov(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text=_CHEKOV_EXILE), ch)
    if d is None or len(d.get("effects") or []) != 1 or d["effects"][0].get("do") != "exile_top" or d["effects"][0].get("player") != "each_opponent" \
            or d["effects"][0].get("face_down"):
        return None
    return {**d, "effects": [{**d["effects"][0], "as": _CHEKOV_BIND},
                             {"do": "choose_exiled_lands_111c", "from": _CHEKOV_BIND, "as": _CHEKOV_BIND + "_chosen"},
                             {"do": "grant_play", "who": "ref:" + _CHEKOV_BIND + "_chosen", "play": True, "cast": True, "until": "permanent",
                              "optional": True}]}


def _land_cards_of(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], owner: str) -> list[str]:
    from app.rules import context

    return [c for c in context.objects(plan, ctx, e["from"]) if plan.state.cards[c].zone == f"{owner}:exile" and plan.state.cards[c].owner == owner
            and "Land" in plan.ch(plan.state.cards[c]).types]


def choose_exiled_lands(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    context.bind_objects(plan, ctx, e["as"], [])
    return _next_land(plan, ctx, e, [p for p in plan.apnap() if p in plan.live() and p != ctx["controller"]], [])


def _next_land(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], owners: list[str], chosen: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    while owners:
        owner, owners = owners[0], owners[1:]
        lands = _land_cards_of(plan, ctx, e, owner)
        if len(lands) == 1:
            chosen = [*chosen, lands[0]]
        elif lands:
            decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose a land card {plan.name(owner)} owns exiled this way",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "card") for c in lands],
                   resume={"step": "choose_exiled_lands_111c", "ctx": ctx, "e": e, "owners": owners, "chosen": chosen})
            return False
    context.bind_objects(plan, ctx, e["as"], chosen)
    if chosen:
        plan.note(f"{plan.name(ctx['controller'])} chooses {', '.join(plan.state.cards[c].name or 'a card' for c in chosen)}", chosen, actor=ctx["controller"])
    return True


def resume_choose_exiled_lands(plan: Plan, d: Any, picked: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    if _next_land(plan, r["ctx"], r["e"], r["owners"], [*r["chosen"], *picked[:1]]):
        continue_effects(plan, r["ctx"])


RESUME = {"choose_exiled_lands_111c": resume_choose_exiled_lands}

# Extraction Integrant's granted "Whenever a creature blocks this creature, that creature gets -1/-1 until end of turn." — 509.3b: "[a creature]
# blocks a creature" triggers once for each blocker declared (or made to block by an effect) for this creature, not for one put onto the battlefield
# blocking (combat_rules: no "blocks" pair then); "that creature" is the blocker, the event's object (a "Whenever a creature blocks" ability with the
# other side of the block bound to the creature that has it: triggers._other_ok "self").
_BLOCKS_THIS = "Whenever a creature blocks ~, that creature gets -1/-1 until end of turn."


def _blocks_this(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text="Whenever a creature blocks, that creature gets -1/-1 until end of turn."), ch)
    cond = (d or {}).get("cond") or {}
    if d is None or cond.get("event") != "block" or cond.get("subject") != "sel" or cond.get("other") or d.get("effects") != [
            {"do": "pump", "who": "event", "p": -1, "t": -1}]:
        return None
    return {**d, "cond": {**cond, "other": "self"}}


def again(ch: Characteristics) -> int:
    """How many Lwaxana effects make this object's triggered abilities trigger an additional time (603.2d: each adds one)."""
    return sum(1 for r in ch.imposed if r.startswith(AGAIN))


PRIMITIVES = {"goad_while_controlled_111c": goad_while_controlled, "trigger_again_while_tapped_111c": trigger_again_while_tapped,
              "mind_meld_opponent_111c": mind_meld_opponent, "choose_exiled_lands_111c": choose_exiled_lands}

# Sulu, Heroic Helmsman: "Sulu stations Spacecraft and crews Vehicles as though his power were tripled." — 702.184c: a static that changes what a
# station ability counts; 702.122b: the creatures tapped to pay a Vehicle's crew cost count their power (casting.crew_value). Only for a Spacecraft's
# station ability (a Planet's isn't one) and a Vehicle's crew ability (not saddling a Mount, 702.171a). Read with the rules it imposes on itself.
_SULU = "~ stations Spacecraft and crews Vehicles as though ~'s power were tripled."
STATION_X3 = "station_spacecraft_x3_111c"
CREW_X3 = "crew_vehicles_x3_111c"


def _sulu(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text="~ crews Vehicles as though its power were 2 greater."), ch)
    if d is None or d.get("rules") != ["crew_plus:2"] or d.get("who") != "self":
        return None
    return {**d, "rules": [STATION_X3, CREW_X3]}


def station_value(plan: Plan, ctx: dict[str, Any], ch: Characteristics) -> int | None:
    """The tapped creature's station value under Sulu's static (its power tripled) when the station ability is a Spacecraft's; None otherwise. A
    creature that stations using its toughness (702.184c, Tapestry Warden) uses that toughness as it is: Sulu's static is about his power."""
    if STATION_X3 not in ch.imposed or "station_toughness110e" in ch.imposed:
        return None
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is None or "Spacecraft" not in plan.ch(src).subtypes:
        return None
    from app.rules.values import _stat_of

    power = _stat_of(ch, "power")
    return None if power is None else 3 * power


def crew_times(ch: Characteristics, crewed: Characteristics | None) -> int:
    """How many times its power a creature counts toward a crew cost: three times for Sulu crewing a Vehicle, else once."""
    return 3 if CREW_X3 in ch.imposed and crewed is not None and "Vehicle" in crewed.subtypes else 1


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    """A one-off ability's native reading, or the station symbol's grant of a linked-referring ability (the static's own reading, with the
    grant read against this card), or None."""
    from app.rules import exiled_with, scripts, statics

    if ability.kind == "triggered" and ability.index < 100 and scripts.self_text(ability.text, ch.name) == _KANG:
        return _kang(ability, ch)
    if ability.kind == "triggered" and ability.index < 100 and scripts.self_text(ability.text, ch.name) == _CHEKOV:
        return _chekov(ability, ch)
    if ability.kind == "triggered" and scripts.self_text(ability.text, ch.name) == _BLOCKS_THIS:
        return _blocks_this(ability, ch)
    if ability.kind == "activated" and ability.index < 100 and scripts.self_text(ability.text, ch.name) == _LWAXANA:
        return _lwaxana(ability, ch)
    if ability.kind != "static" or ability.index >= 100:
        return None
    if scripts.self_text(ability.text, ch.name) == _SULU:
        return _sulu(ability, ch)
    if ability.text in _AS:
        return scripts.define(replace(ability, text=_AS[ability.text]), ch)
    m = _STATION_GRANT.match(scripts.self_text(ability.text, ch.name))
    if m is None or not exiled_with._REFERS.search(m["q"]) or scripts.granted_ability(m["q"]) is not None:
        return None
    if linked_grant(m["q"], ch, 100) is None:
        return None
    d = statics.parse(m.group(0).replace(m["q"], _PLACEHOLDER))
    if d is None or d.get("grants") != [_PLACEHOLDER] or d.get("who") != "self":
        return None
    return {**d, "grants": [m["q"]], "linked111c": True}


@lru_cache(maxsize=256)
def linked_grant(text: str, ch: Characteristics, index: int) -> AbilityText | None:
    """The granted ability ``text`` as ability ``index`` of ``ch`` (layers: the station grant on the object itself), if the engine reads it there."""
    from app.rules import scripts
    from app.rules.oracle import parse_abilities

    parsed = parse_abilities(text)
    if len(parsed) != 1 or parsed[0].kind != "triggered":
        return None
    ab = replace(parsed[0], index=index)
    printed = tuple(a for a in ch.abilities if a.index < 100)
    return ab if scripts.define(ab, replace(ch, abilities=(*printed, ab))) is not None else None


def condition(text: str, objects: bool) -> dict[str, Any] | None:
    """A condition of these wordings, or None."""
    if text == f"you {_NO_EXTRA}":
        return {"w111c": "no_extra_turn"}
    if objects and text == "this spell is the first spell you've cast this game":
        return {"w111c": "first_spell_game"}
    if text == "it's a combat phase":  # (Merciful Mandate: 506.1, any step of a combat phase, as "it's combat" reads)
        return {"combat_phase": "any"}
    m = re.fullmatch(rf"(?P<a>you control .+) and {_NO_EXTRA}", text)
    if m is None:
        return None
    from app.rules import conditions

    first = conditions.parse(m["a"], objects=objects)
    return None if first is None else {"all": [first, {"w111c": "no_extra_turn"}]}


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """Both histories are known only from the game's start (``None`` otherwise: automation began mid-game, or an older save): unknown is "no"
    (no extra turn, no life), as Once Upon a Time's "first spell you've cast this game" is (conditional_free_casts68)."""
    r, who = plan.rules, ctx["controller"]
    if cond["w111c"] == "no_extra_turn":
        return r.extra_turn_begun111c is not None and who not in r.extra_turn_begun111c
    if cond["w111c"] == "first_spell_game":  # 601.2i: this spell was cast, and its controller cast no spell before it this game (a copy wasn't cast, 707.10)
        from app.game.rules_state import turn_log_now

        log = turn_log_now(plan.state)
        mine = [n for n in (log.casts if log is not None else []) if n.player == who]
        # (review: spells cast after it, in response, don't change which was first: every cast of the game is this turn's, and it is the first of them)
        return r.casts_game111c is not None and r.casts_game111c.get(who) == len(mine) and bool(mine) and mine[0].object_id == ctx.get("source_object")
    return False


def turn_began(plan: Plan, extra: bool) -> None:
    """500.7: the active player has begun an extra turn (engine.start_next_turn, as the turn begins)."""
    if extra and plan.rules.extra_turn_begun111c is not None and plan.active not in plan.rules.extra_turn_begun111c:
        plan.rules.extra_turn_begun111c.append(plan.active)
