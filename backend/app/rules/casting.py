"""Mana abilities, paying costs and casting spells (milestone 15).

Casting follows the real order (announce → move to the stack → pay), but everything is planned on
the scratch table first, so a spell you can't pay for simply isn't cast: nothing half-happens.
Costs are paid automatically from your mana pool and untapped mana sources (see ``mana.solve``);
tap lands yourself first (``activate_ability`` on their mana ability) to pay a particular way.
"""

from __future__ import annotations

from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, TurnCount
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import characteristics as chars
from app.rules import mana as M
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.costs import AbilityCost, parse_ability_cost
from app.rules.oracle import AbilityText
from app.rules.plan import Plan, decide, require_no_decision, require_priority

MAIN_PHASES = ("main1", "main2")


# -- facts about permanents -------------------------------------------------------------
def commander_identity(state: GameState, player: str, info: CardInfo) -> tuple[str, ...]:
    colors: set[str] = set()
    for c in state.cards.values():
        if c.owner == player and c.commander_key and c.card_id:
            data = info.get(c.card_id)
            if data:
                colors |= set(data.get("color_identity") or [])
    return tuple(x for x in M.COLORS if x in colors)


def summoning_sick(state: GameState, card: CardInstance) -> bool:
    """A creature can't attack or use {T} abilities unless its controller has controlled it
    continuously since the start of their most recent turn (haste is checked by the caller)."""
    r = state.rules
    if r is None:
        return False
    mark = r.controlled_since.get(card.id)
    started = r.turn_started.get(card.controller)
    if mark is None or started is None:
        return True
    return mark.turn >= started


def can_use_tap_abilities(state: GameState, card: CardInstance, ch: Characteristics) -> bool:
    if card.tapped or not card.zone.endswith(":battlefield"):
        return False
    return not (ch.is_creature and "haste" not in ch.keywords and summoning_sick(state, card))


def mana_abilities(state: GameState, card: CardInstance, info: CardInfo) -> list[tuple[int, M.ManaAbility]]:
    ch = chars.of(card, info)
    identity = commander_identity(state, card.controller, info)
    out = []
    for ab in ch.abilities:
        if ab.kind == "mana":
            parsed = M.parse_mana_ability(ab.text, identity)
            if parsed is not None:
                out.append((ab.index, parsed))
    return out


def mana_sources(state: GameState, player: str, info: CardInfo) -> list[M.Source]:
    """Untapped permanents ``player`` controls that can pay for things right now."""
    out: list[M.Source] = []
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = chars.of(card, info)
        if not can_use_tap_abilities(state, card, ch):
            continue
        abilities = mana_abilities(state, card, info)
        plain = [ab for _, ab in abilities if ab.tap and not ab.sacrifice_self]
        sac = [ab for _, ab in abilities if ab.tap and ab.sacrifice_self]
        chosen = plain or sac
        if not chosen:
            continue
        options = tuple(dict.fromkeys(opt for ab in chosen for opt in ab.options))
        rank = 0 if ch.is_land else 2 if ch.is_creature else 1
        out.append(M.Source(card.id, options, sacrifice=not plain, rank=rank + (5 if not plain else 0)))
    return out


def pay(plan: Plan, player: str, cost: M.ManaCost, label: str) -> None:
    if cost.is_free:
        return
    state = plan.state
    try:
        payment = M.solve(cost, dict(state.players[player].mana), mana_sources(state, player, plan.info),
                          life=state.players[player].life)
    except M.ManaError as exc:
        raise ActionError(f"{exc}. Tap mana yourself first, or use the table tools.") from exc
    plan.do({"type": "rules_mana", "player": player, "tap": payment.tapped, "sacrifice": payment.sacrificed,
             "delta": payment.delta(), "life": payment.life, "label": label}, actor=player)


def can_pay(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *, exclude: tuple[str, ...] = ()) -> bool:
    sources = [s for s in mana_sources(state, player, info) if s.card_id not in exclude]
    try:
        M.solve(cost, dict(state.players[player].mana), sources, life=state.players[player].life)
    except M.ManaError:
        return False
    return True


# -- casting ----------------------------------------------------------------------------
def from_command_zone(card: CardInstance, player: str) -> bool:
    return card.zone == zone_key(player, "command") and card.commander_key is not None and card.owner == player


def cast_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, *,
                 check_priority: bool = True) -> str | None:
    """Why ``player`` can't cast ``card`` right now (costs aside), or None."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if not (card.zone == zone_key(player, "hand") or from_command_zone(card, player)):
        return "You can cast spells from your hand, and your commander from the command zone"
    if ch.is_land:
        return f"{ch.name or 'That card'} is a land: play it instead"
    if not ch.types:
        return "Fyodor doesn't know what that card is. Use the table tools."
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    if "Instant" in ch.types or ch.has_flash:
        return None
    if state.turn.active_player != player:
        return f"{ch.name} can only be cast during your turn"
    if state.turn.phase not in MAIN_PHASES:
        return f"{ch.name} can only be cast in a main phase"
    if state.zones.get(STACK):
        return f"{ch.name} can only be cast while the stack is empty"
    return None


def spell_cost(state: GameState, card: CardInstance, ch: Characteristics, x: int = 0) -> M.ManaCost:
    cost = M.parse_cost(ch.mana_cost).with_x(x)
    if from_command_zone(card, card.owner) and card.commander_key:
        cost = cost.plus_generic(state.players[card.owner].commander_tax.get(card.commander_key, 0))
    return cost


def castable(state: GameState, player: str, card: CardInstance, info: CardInfo, *, check_priority: bool = True) -> bool:
    ch = chars.of(card, info)
    if cast_problem(state, player, card, ch, check_priority=check_priority) is not None:
        return False
    return can_pay(state, player, spell_cost(state, card, ch), info)


def cast_spell(plan: Plan, a: A.CastSpell) -> None:
    from app.rules.engine import advance  # the engine imports this module

    require_no_decision(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    probe = card.model_copy(update={"face": a.face}) if a.face is not None else card
    ch = plan.ch(probe)
    problem = cast_problem(plan.state, plan.actor, card, ch)
    if problem:
        raise ActionError(problem)
    base = M.parse_cost(ch.mana_cost)
    if base.x and a.x_value is None:
        raise ActionError(f"Choose a value for X to cast {ch.name}")
    cost = spell_cost(plan.state, card, ch, a.x_value or 0)
    for target in a.targets:
        if target not in plan.state.cards and target not in plan.state.players:
            raise ActionError("A chosen target isn't on the table")
    commander_cast = from_command_zone(card, plan.actor)
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}})
    if commander_cast and not plan.state.settings.auto_commander_tax and card.commander_key:
        plan.do({"type": "commander_tax", "commander": card.commander_key, "delta": 2})
    pay(plan, plan.actor, cost, f"paid {cost.text()} for {ch.name}")
    tags = ["Cast from the command zone"] if commander_cast else []
    if a.x_value is not None or tags:
        info: dict[str, Any] = {"type": "set_stack_info", "card_id": card.id}
        if a.x_value is not None:
            info["x"] = a.x_value
        if tags:
            info["tags"] = tags
        plan.do(info)
    if a.targets:
        plan.do({"type": "create_arrow", "source": card.id, "targets": list(a.targets), "kind": "target"})
    r = plan.rules
    turn = plan.state.turn.number
    r.spells_cast[plan.actor] = TurnCount(turn=turn, count=r.spells_this_turn(plan.actor, turn) + 1)
    r.passed = []
    r.priority = plan.actor
    if not r.stops_for(plan.actor).hold_priority:
        r.passed.append(plan.actor)  # Arena-style: you pass after casting unless you hold priority
        r.priority = plan.after(plan.actor)
    advance(plan)


# -- mana abilities ---------------------------------------------------------------------
def _find_ability(ch: Characteristics, index: int) -> AbilityText:
    ability = next((ab for ab in ch.abilities if ab.index == index), None)
    if ability is None:
        raise ActionError(f"{ch.name or 'That card'} has no such ability")
    return ability


def activate_ability(plan: Plan, a: A.ActivateAbility) -> None:
    require_no_decision(plan)
    require_priority(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    if card.controller != plan.actor or not card.zone.endswith(":battlefield"):
        raise ActionError("You can only activate abilities of permanents you control")
    ch = plan.ch(card)
    ability = _find_ability(ch, a.ability)
    if ability.kind in ("activated", "loyalty"):
        activate_to_stack(plan, card, ch, ability, a)
        return
    if ability.kind != "mana":
        raise ActionError(f"“{ability.text}” isn't an ability you activate")
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(a.ability)
    if parsed is None:
        raise ActionError(f"Fyodor can't carry out “{ability.text}” yet. Use the table tools.")
    if parsed.tap and not can_use_tap_abilities(plan.state, card, ch):
        raise ActionError(f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness")
    options = parsed.options
    if len(options) == 1:
        produce(plan, card, parsed, options[0])
    elif a.mana_choice is not None:
        chosen = next((o for o in options if o == (a.mana_choice,)), None)
        if chosen is None:
            raise ActionError(f"{ch.name} can't add {{{a.mana_choice}}}")
        produce(plan, card, parsed, chosen)
    else:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"Which mana should {ch.name} add?",
               options=[DecisionOption(id=str(i), label=M.symbols(_count(o))) for i, o in enumerate(options)],
               resume={"step": "mana_ability", "card": card.id, "ability": a.ability}, source=card)
        return
    plan.rules.passed = []


# -- other activated abilities (they use the stack) -----------------------------------------
def ability_cost(ch: Characteristics, ability: AbilityText) -> AbilityCost:
    return parse_ability_cost(ability.cost or "", card_name=ch.name, loyalty=ability.kind == "loyalty")


def ability_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, ability: AbilityText,
                    cost: AbilityCost, *, check_priority: bool = True, x: int = 0,
                    info: CardInfo | None = None) -> str | None:
    """Why ``player`` can't activate this ability now (None if they can, costs included when
    ``info`` is given)."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if card.controller != player or not card.zone.endswith(":battlefield"):
        return "You can only activate abilities of permanents you control"
    if cost.unsupported:
        return f"Pay “{', '.join(cost.unsupported)}” by hand with the table tools"
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    sorcery = ability.kind == "loyalty" or "Activate only as a sorcery" in ability.text
    if sorcery and (state.turn.active_player != player or state.turn.phase not in MAIN_PHASES or state.zones.get(STACK)):
        return "That can only be activated in your main phase while the stack is empty"
    if ability.kind == "loyalty":
        if r.loyalty_used.get(card.id) == state.turn.number:
            return f"{ch.name} has already used a loyalty ability this turn"
        if cost.loyalty is not None and cost.loyalty < 0 and card.counters.get("loyalty", 0) < -cost.loyalty:
            return f"{ch.name} doesn't have enough loyalty"
    if "Activate only once each turn" in ability.text and r.once_per_turn.get(f"{card.id}:{ability.index}") == state.turn.number:
        return "That can only be activated once each turn"
    if cost.tap and not can_use_tap_abilities(state, card, ch):
        return f"{ch.name} is tapped" if card.tapped else f"{ch.name} has summoning sickness"
    for kind, n in cost.remove_counters:
        if card.counters.get(kind, 0) < n:
            return f"{ch.name} doesn't have {n} {kind} counter{'s' if n != 1 else ''}"
    if cost.life and state.players[player].life < cost.life:
        return f"You don't have {cost.life} life to pay"
    if info is not None and cost.mana:
        mana = M.parse_cost(cost.mana).with_x(x)
        if not can_pay(state, player, mana, info, exclude=(card.id,) if cost.tap else ()):
            return f"Not enough mana to pay {mana.text()}"
    return None


def activate_to_stack(plan: Plan, card: CardInstance, ch: Characteristics, ability: AbilityText,
                      a: A.ActivateAbility) -> None:
    from app.rules.engine import advance  # the engine imports this module

    cost = ability_cost(ch, ability)
    problem = ability_problem(plan.state, plan.actor, card, ch, ability, cost)
    if problem:
        raise ActionError(problem)
    mana = M.parse_cost(cost.mana)
    if mana.x and a.x_value is None:
        raise ActionError("Choose a value for X")
    effect = ability.text.split(":", 1)[1].strip() if ":" in ability.text else ability.text
    created = plan.do({"type": "create_ability", "text": effect[:500], "source_id": card.id, "kind": "activated"})
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    # Pay the costs (602.2): tap first so the source can't also pay for its own mana cost.
    if cost.tap:
        plan.do({"type": "tap", "card_ids": [card.id], "tapped": True})
    if cost.loyalty:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "loyalty", "delta": cost.loyalty})
    for kind, n in cost.remove_counters:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": kind, "delta": -n})
    if cost.life:
        plan.do({"type": "life", "player": plan.actor, "delta": -cost.life})
    pay(plan, plan.actor, mana.with_x(a.x_value or 0), f"paid {mana.with_x(a.x_value or 0).text()} to activate {ch.name}")
    if cost.sacrifice_self:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}})
    if a.x_value is not None and ability_id:
        plan.do({"type": "set_stack_info", "card_id": ability_id, "x": a.x_value})
    if a.targets and ability_id:
        plan.do({"type": "create_arrow", "source": ability_id, "targets": list(a.targets), "kind": "target"})
    r = plan.rules
    if ability.kind == "loyalty":
        r.loyalty_used[card.id] = plan.state.turn.number
    if "Activate only once each turn" in ability.text:
        r.once_per_turn[f"{card.id}:{ability.index}"] = plan.state.turn.number
    r.passed = []
    r.priority = plan.actor
    if not r.stops_for(plan.actor).hold_priority:
        r.passed.append(plan.actor)
        r.priority = plan.after(plan.actor)
    advance(plan)


def activatable(state: GameState, player: str, info: CardInfo, *, check_priority: bool = True) -> list[dict[str, Any]]:
    """Abilities of ``player``'s permanents that could be activated right now (for hints)."""
    out: list[dict[str, Any]] = []
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = chars.of(card, info)
        for ab in ch.abilities:
            if ab.kind in ("activated", "loyalty"):
                problem = ability_problem(state, player, card, ch, ab, ability_cost(ch, ab),
                                          check_priority=check_priority, info=info)
                if problem is None:
                    out.append({"card_id": cid, "ability": ab.index})
            elif ab.kind == "mana" and not check_priority:
                continue
    return out


def _count(option: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in option:
        out[m] = out.get(m, 0) + 1
    return out


def produce(plan: Plan, card: CardInstance, ability: M.ManaAbility, option: tuple[str, ...]) -> None:
    mana = _count(option)
    plan.do({"type": "rules_mana", "player": card.controller, "tap": [card.id] if ability.tap else [],
             "sacrifice": [card.id] if ability.sacrifice_self else [], "delta": mana,
             "label": f"added {M.symbols(mana)}"}, actor=card.controller)


def resume_mana_ability(plan: Plan, d: Any, chosen: list[str]) -> None:
    card = plan.state.cards.get(d.resume["card"])
    if card is None:
        return
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(int(d.resume["ability"]))
    if parsed is None or not can_use_tap_abilities(plan.state, card, plan.ch(card)):
        raise ActionError("That mana ability can't be activated any more")
    produce(plan, card, parsed, parsed.options[int(chosen[0])])
    plan.rules.priority = plan.actor
    plan.rules.passed = []


# -- responding -------------------------------------------------------------------------
def has_responses(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at instant speed right now? (For Arena-style auto-passing.)"""
    for key in (zone_key(player, "hand"), zone_key(player, "command")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            ch = chars.of(card, info)
            if ("Instant" in ch.types or ch.has_flash) and castable(state, player, card, info, check_priority=False):
                return True
    return bool(activatable(state, player, info, check_priority=False))
