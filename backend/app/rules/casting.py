"""Mana abilities, paying costs and casting spells (milestone 15).

Casting follows the real order (announce → move to the stack → pay), but everything is planned on
the scratch table first, so a spell you can't pay for simply isn't cast: nothing half-happens.
Costs are paid automatically from your mana pool and untapped mana sources (see ``mana.solve``);
tap lands yourself first (``activate_ability`` on their mana ability) to pay a particular way.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, StackEntry, TargetRef, TurnCount, emit
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import characteristics as chars
from app.rules import commander as cmdr
from app.rules import mana as M
from app.rules import scripts
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.costs import AbilityCost, parse_ability_cost
from app.rules.oracle import AbilityText
from app.rules.plan import Plan, decide, require_no_decision, require_priority
from app.rules.targets import label as target_label
from app.rules.targets import legal_targets
from app.rules.targets import ref as target_ref

MAIN_PHASES = ("main1", "main2")


# -- facts about permanents -------------------------------------------------------------
def commander_identity(state: GameState, player: str, info: CardInfo) -> tuple[str, ...]:
    commanders = [info.get(c.card_id) for c in state.cards.values() if c.owner == player and c.commander_key and c.card_id]
    return cmdr.deck_identity([d for d in commanders if d])  # the same identity the deck checks use


def summoning_sick(state: GameState, card: CardInstance) -> bool:
    """A creature can't attack or use {T} abilities unless its controller has controlled it
    continuously since the start of their most recent turn (haste is checked by the caller)."""
    r = state.rules
    if r is None or r.card_mode(card.id) == "manual":
        return False  # a MANUAL card's timing isn't enforced: its controller handles it
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


# -- targets (601.2c) --------------------------------------------------------------------
def choose_target(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any] | None,
                  what: str) -> list[TargetRef] | None:
    """The target of an automated spell or ability: validated if given, else asked (privately).
    Returns the chosen targets, or None while waiting for the choice."""
    spec = definition.get("target") if definition else None
    if not spec:
        return []
    legal = legal_targets(plan, spec["what"], plan.actor)
    if a.targets:
        if len(a.targets) != 1 or a.targets[0] not in legal:
            raise ActionError("That isn't a legal target")
        return [target_ref(plan, a.targets[0])]
    if not legal:
        raise ActionError(f"{what} has no legal target")
    decide(plan, player=plan.actor, kind="choose_one", prompt=f"Choose a target for {what}",
           options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None) for x in legal],
           resume={"step": "cast_target", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})})
    return None


def resume_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    intent = A.parse_action(d.resume["intent"])
    intent.targets = list(chosen)  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


# -- paying mana ------------------------------------------------------------------------
PaymentMode = str  # "auto" | "ask" | "manual"


def payment_mode(plan: Plan, player: str) -> PaymentMode:
    """AUTO pays; ASK shows the suggested payment first (also when the table's AUTO MANA PAYMENT is
    off); MANUAL lets the player pick the exact sources."""
    pref = plan.rules.prefs_for(player).payment
    if pref == "manual":
        return "manual"
    if pref == "ask" or not plan.options.auto_mana_payment:
        return "ask"
    return "auto"


def find_payment(state: GameState, player: str, cost: M.ManaCost, info: CardInfo, *,
                 sources: list[str] | None = None, exclude: tuple[str, ...] = ()) -> M.Payment:
    """How to pay ``cost``: with exactly ``sources`` when given (MANUAL PAY), else automatically,
    PREFER sources first and SAVE sources only when there is no other way."""
    available = [s for s in mana_sources(state, player, info) if s.card_id not in exclude]
    pool = dict(state.players[player].mana)
    life = state.players[player].life
    if sources is not None:
        chosen = [s for s in available if s.card_id in set(sources)]
        if len(chosen) != len(set(sources)):
            raise ActionError("Pick untapped mana sources you control")
        try:
            payment = M.solve(cost, pool, chosen, life=life)
        except M.ManaError as exc:
            raise ActionError(f"Those sources can't pay {cost.text()}") from exc
        unused = set(sources) - set(payment.tapped)
        if unused:
            names = ", ".join(state.cards[c].name or "a source" for c in unused)
            raise ActionError(f"{names} isn't needed to pay {cost.text()}")
        return payment
    protection = state.rules.prefs_for(player).mana_sources if state.rules else {}
    marked = [replace(s, preferred=protection.get(s.card_id) == "prefer") for s in available]
    normal = [s for s in marked if protection.get(s.card_id) != "save"]
    try:
        return M.solve(cost, pool, normal, life=life)
    except M.ManaError:
        pass
    try:
        return M.solve(cost, pool, marked, life=life)  # SAVE sources only when nothing else works
    except M.ManaError as exc:
        raise ActionError(f"{exc}. Tap mana yourself first, or use the table tools.") from exc


def pay(plan: Plan, player: str, cost: M.ManaCost, label: str, *, sources: list[str] | None = None,
        exclude: tuple[str, ...] = ()) -> None:
    if cost.is_free and not sources:
        return
    payment = find_payment(plan.state, player, cost, plan.info, sources=sources, exclude=exclude)
    plan.do({"type": "rules_mana", "player": player, "tap": payment.tapped, "sacrifice": payment.sacrificed,
             "delta": payment.delta(), "life": payment.life, "label": label}, actor=player)


def payment_step(plan: Plan, a: A.CastSpell | A.ActivateAbility, cost: M.ManaCost, what: str, *,
                 exclude: tuple[str, ...] = ()) -> bool:
    """Before a spell or ability is put on the stack: does the player want to see or choose the
    payment first? Returns True if a decision was opened (the intent then waits for it; nothing
    has moved yet, so CANCEL simply leaves everything where it was)."""
    if a.sources is not None or cost.is_free:
        return False
    mode = payment_mode(plan, plan.actor)
    if mode == "auto":
        return False
    payment = find_payment(plan.state, plan.actor, cost, plan.info, exclude=exclude)  # (can it be paid at all?)
    resume = {"step": "payment", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}),
              "exclude": list(exclude), "cost": cost.text(), "what": what}
    if mode == "manual":
        ask_sources(plan, cost, what, resume)
        return True
    names = [plan.state.cards[c].name or "a source" for c in payment.tapped]
    pool = sum(payment.spent.values()) - sum(payment.produced.values())
    if pool > 0:
        names.append(f"{pool} from your mana pool")
    resume["suggested"] = payment.tapped
    others = [s.card_id for s in mana_sources(plan.state, plan.actor, plan.info)
              if s.card_id not in payment.tapped and s.card_id not in exclude][:12]
    decide(plan, player=plan.actor, kind="choose_one",
           display={"kind": "payment", "cost": cost.text(), "what": what, "suggested": list(payment.tapped),
                    "alternatives": others, "pool": pool},
           prompt=f"Pay {cost.text()} for {what}. Suggested payment: {', '.join(names) or 'nothing'}",
           options=[DecisionOption(id="pay", label="Pay"), DecisionOption(id="manual", label="Manual"),
                    DecisionOption(id="cancel", label="Cancel")],
           resume=resume)
    return True


def ask_sources(plan: Plan, cost: M.ManaCost, what: str, resume: dict[str, Any]) -> None:
    exclude = tuple(resume.get("exclude") or ())
    sources = [s for s in mana_sources(plan.state, plan.actor, plan.info) if s.card_id not in exclude]
    options = [DecisionOption(id=s.card_id, label=plan.state.cards[s.card_id].name or "Source", card_id=s.card_id)
               for s in sources]
    decide(plan, player=plan.actor, kind="choose_cards",
           prompt=f"Choose the mana sources to pay {cost.text()} for {what} (your mana pool is used first)",
           options=options, min_choices=0, max_choices=max(len(options), 0),
           resume={**resume, "step": "payment_sources"})


def resume_payment(plan: Plan, d: Any, chosen: list[str]) -> None:
    """PAY (the suggestion), MANUAL (pick sources) or CANCEL."""
    assert d.resume is not None
    answer = chosen[0]
    if answer == "cancel":
        plan.note(f"{plan.name(d.player)} cancelled")
        plan.rules.priority = d.player
        plan.hold = d.player
        return
    intent = A.parse_action(d.resume["intent"])
    if answer == "manual":
        ask_sources(plan, M.parse_cost(d.resume["cost"]), d.resume["what"], d.resume)
        return
    _rerun(plan, d, intent, list(d.resume.get("suggested") or []))


def resume_payment_sources(plan: Plan, d: Any, chosen: list[str]) -> None:
    assert d.resume is not None
    _rerun(plan, d, A.parse_action(d.resume["intent"]), chosen)


def _rerun(plan: Plan, d: Any, intent: Any, sources: list[str]) -> None:
    from app.rules.engine import INTENTS  # the engine imports this module

    intent.sources = sources
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


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
    faces = (0, 1) if chars.is_two_spell_card(card, info) else (None,)
    for face in faces:
        ch = chars.as_cast(card, info, face)
        if cast_problem(state, player, card, ch, check_priority=check_priority) is None and \
                can_pay(state, player, spell_cost(state, card, ch), info):
            return True
    return False


def cast_spell(plan: Plan, a: A.CastSpell) -> None:
    from app.rules.engine import advance  # the engine imports this module

    require_no_decision(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    ch = chars.as_cast(card, plan.info, a.face)  # split cards / adventures: the half being cast
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
    definition = None if plan.manual(card) else scripts.spell_definition(ch)
    chosen = choose_target(plan, a, definition, ch.name or "it")
    if chosen is None:
        return  # waiting for the target choice (601.2c comes before paying costs)
    if payment_step(plan, a, cost, ch.name or "it"):
        return
    commander_cast = from_command_zone(card, plan.actor)
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "stack"}})
    if commander_cast and not plan.state.settings.auto_commander_tax and card.commander_key:
        plan.do({"type": "commander_tax", "commander": card.commander_key, "delta": 2})
    pay(plan, plan.actor, cost, f"paid {cost.text()} for {ch.name}", sources=a.sources)
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
    emit(plan.state, "spell_cast", object_id=plan.oid(card), card=card.id, player=plan.actor)  # for "whenever you cast"
    if definition is not None:
        r.stack[card.id] = StackEntry(kind="spell", controller=plan.actor, source_card=card.id, source_object=plan.oid(card),
                                      name=ch.name, effects=list(definition["effects"]), targets=chosen,
                                      target_spec=definition.get("target"), x=a.x_value)
    turn = plan.state.turn.number
    r.spells_cast[plan.actor] = TurnCount(turn=turn, count=r.spells_this_turn(plan.actor, turn) + 1)
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return  # HOLD PRIORITY: you keep it, whatever your RESPONSE setting says
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
        if r.loyalty_used.get(r.object_id(card.id)) == state.turn.number:
            return f"{ch.name} has already used a loyalty ability this turn"
        if cost.loyalty is not None and cost.loyalty < 0 and card.counters.get("loyalty", 0) < -cost.loyalty:
            return f"{ch.name} doesn't have enough loyalty"
    once_key = f"{r.object_id(card.id)}:{ability.index}"  # per object: a flickered permanent is a new one
    if "Activate only once each turn" in ability.text and r.once_per_turn.get(once_key) == state.turn.number:
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
    oid = plan.oid(card)  # the object activating (paying a cost may move it: it'd be a new object)
    mana = M.parse_cost(cost.mana)
    if mana.x and a.x_value is None:
        raise ActionError("Choose a value for X")
    definition = None if plan.manual(card) else scripts.definitions(ch).get(ability.index)
    if definition is not None and definition["kind"] != "activated":
        definition = None
    chosen = choose_target(plan, a, definition, f"{ch.name}’s ability")
    if chosen is None:
        return
    if payment_step(plan, a, mana.with_x(a.x_value or 0), f"{ch.name}’s ability",
                    exclude=(card.id,) if cost.tap else ()):
        return
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
    pay(plan, plan.actor, mana.with_x(a.x_value or 0), f"paid {mana.with_x(a.x_value or 0).text()} to activate {ch.name}",
        sources=a.sources)
    if cost.sacrifice_self:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}})
    if a.x_value is not None and ability_id:
        plan.do({"type": "set_stack_info", "card_id": ability_id, "x": a.x_value})
    if a.targets and ability_id:
        plan.do({"type": "create_arrow", "source": ability_id, "targets": list(a.targets), "kind": "target"})
    r = plan.rules
    if definition is not None and ability_id:
        r.stack[ability_id] = StackEntry(kind="activated", controller=plan.actor, source_card=card.id, source_object=oid,
                                         name=ch.name, effects=list(definition["effects"]), targets=chosen,
                                         target_spec=definition.get("target"), x=a.x_value)
    if ability.kind == "loyalty":
        r.loyalty_used[oid] = plan.state.turn.number
    if "Activate only once each turn" in ability.text:
        r.once_per_turn[f"{oid}:{ability.index}"] = plan.state.turn.number
    r.passed = []
    r.priority = plan.actor
    if r.prefs_for(plan.actor).hold_priority:
        plan.hold = plan.actor
        return
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


def can_act(state: GameState, player: str, info: CardInfo) -> bool:
    """Could ``player`` do anything at all right now (a land, a spell, an ability)?"""
    from app.rules.engine import land_play_problem  # engine imports this module

    for key in (zone_key(player, "hand"), zone_key(player, "command")):
        for cid in state.zones.get(key, []):
            card = state.cards[cid]
            if castable(state, player, card, info, check_priority=False):
                return True
            if key.endswith(":hand") and land_play_problem(state, player, card, chars.of(card, info), check_priority=False) is None:
                return True
    return bool(activatable(state, player, info, check_priority=False))
