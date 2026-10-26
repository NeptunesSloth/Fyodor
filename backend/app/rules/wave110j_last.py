"""Wave 110J last cards: exact Oracle wordings settled by their official rulings (scratchpad rul/final11.json)."""
from __future__ import annotations

from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide

Context = dict[str, Any]

# -- Contractual Safeguard -- the addendum (702 "Addendum" ability word: an "if you cast this spell during your main phase" condition) puts a shield
# counter first, so the second part may choose it (ruling 2022-04-29). "Choose a kind of counter on a creature you control" picks a creature and one
# kind of counter on it (608.2d); "each other creature you control" is every creature you control other than that creature.
SAFEGUARD = "Choose a kind of counter on a creature you control. Put a counter of that kind on each other creature you control."


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() == SAFEGUARD:  # the addendum paragraph before it is read natively (an "only_if" main-phase cast condition)
        return ([{"do": "safeguard110j"}], None, False)
    return None


def _yours(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and "Creature" in plan.ch(c).types]


def safeguard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    pid = ctx["controller"]
    options = [DecisionOption(id=f"{c}|{k}", card_id=c, label=f"{k} counter on {plan.ch(plan.state.cards[c]).name}")
               for c in _yours(plan, pid) for k, n in sorted(plan.state.cards[c].counters.items()) if n > 0]
    if not options:  # no creature you control has a counter: nothing to choose
        return True
    decide(plan, player=pid, kind="choose_one", prompt="Choose a kind of counter on a creature you control", options=options,
           resume={"step": "safeguard110j", "ctx": ctx}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_safeguard(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the counters offered")
    cid, kind = chosen[0].split("|", 1)
    plan.note(f"{plan.name(d.player)} chooses {kind} counters", actor=d.player)
    others = [c for c in _yours(plan, d.player) if c != cid]
    context.bind_objects(plan, ctx, "safeguard110j", others)
    at = ctx["next"]
    ctx["effects"][at:at] = [{"do": "add_counters", "who": "ref:safeguard110j", "kind": kind, "n": 1}]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"safeguard110j": safeguard}
RESUME = {"safeguard110j": resume_safeguard}


# -- Captain America, First Avenger -- Throw: the damage equals the mana value of the Equipment unattached as a cost. 601.2b (602.2b): when a value
# in the text is defined by a choice the player would make later in the announcement, that choice is made at this time instead, so the Equipment
# is chosen before the targets and the division (601.2c-d, Gatherer rulings 2026-06-19: the targets and the division are chosen on activation,
# each target gets at least 1). At resolution the division stays and damage to an illegal target isn't dealt (608.2b, the same rulings).
CAPTAIN = ("Throw ... — {3}, Unattach an Equipment from Captain America: He deals damage equal to that Equipment's mana value divided as you "
           "choose among one, two, or three targets.")
_CAP_COMPONENT = 1  # the cost's parts: {3}, then the Equipment


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text == PARNESSE:
        return parnesse_definition(ability, ch)
    if (magar_def := magar_definition(ability, ch)) is not None:
        return magar_def
    if (meddle_def := meddle_definition(ability, ch)) is not None:
        return meddle_def
    if ability.kind != "activated" or ability.text != CAPTAIN:
        return None
    return {"kind": "activated", "cost": "{3}, Unattach an Equipment from ~", "effects": [{"do": "damage", "who": "target:0", "n": {"divided": 0}}],
            "target": None, "targets": [{"what": "any", "min": 1, "max": 3, "divide": {"what": "damage", "total": {"x": 1}, "value": {"cap110j": 1}}}],
            "delegated_target": "cap110j"}


def _equipment(plan: Plan, source: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.attached_to == source and c.zone.endswith(":battlefield") and "Equipment" in plan.ch(c).subtypes]


def cap_total(plan: Plan, source: str | None) -> int:
    """The total being divided: the chosen Equipment's mana value (while the ability is announced), else the largest one attached (an estimate for listings)."""
    chosen = getattr(plan, "cap110j", None)
    if chosen is not None:
        return int(chosen)
    return max((int(plan.ch(plan.state.cards[c]).mana_value) for c in _equipment(plan, source or "")), default=0)


def cap_announce(plan: Plan, a: Any, definition: dict[str, Any], what: str) -> Any:
    from app.game import actions as A
    from app.rules import casting

    if not isinstance(a, A.ActivateAbility):
        raise ActionError("Unsupported delegated target announcement")
    equips = _equipment(plan, a.card_id)
    given = next((c.cards for c in a.cost_choices if c.component == _CAP_COMPONENT), None)
    if given is not None and (len(given) != 1 or given[0] not in equips):
        raise ActionError("Choose one Equipment attached to it")
    if not equips:
        raise ActionError("No Equipment is attached to it")  # 118.3
    values = {int(plan.ch(plan.state.cards[c]).mana_value) for c in ([given[0]] if given else equips)}
    if len(values) > 1:  # which Equipment fixes the amount: asked now (601.2b)
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"{what}: choose the Equipment to unattach (its mana value is the damage)",
               options=[DecisionOption(id=c, card_id=c, label=f"{plan.ch(plan.state.cards[c]).name} (mana value {plan.ch(plan.state.cards[c]).mana_value:g})") for c in equips],
               resume={"step": "cap110j", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}), "actor": plan.actor})
        return None
    total = values.pop()
    if total < 1:  # 601.2d: each of the one to three targets must receive at least 1 of it
        raise ActionError("That Equipment's mana value is 0: there is no damage to divide among one, two, or three targets")
    plan.cap110j = total  # type: ignore[attr-defined]
    try:
        return casting.choose_targets(plan, a, {k: v for k, v in definition.items() if k != "delegated_target"}, what)
    finally:
        plan.cap110j = None  # type: ignore[attr-defined]


def resume_cap(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.engine import INTENTS

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one Equipment")
    raw = d.resume["intent"]
    raw["cost_choices"] = [c for c in raw.get("cost_choices") or [] if c["component"] != _CAP_COMPONENT] + [{"component": _CAP_COMPONENT, "cards": chosen}]
    intent = A.parse_action({**raw, "actor": d.resume["actor"]})
    actor = plan.actor
    plan.actor = d.resume["actor"]
    plan.rules.priority, plan.rules.passed = d.resume["actor"], []
    try:
        INTENTS[intent.type](plan, intent)
    finally:
        plan.actor = actor


RESUME["cap110j"] = resume_cap


# -- Parnesse, the Subtle Brush -- "Whenever you copy a spell, up to one target opponent may also copy that spell": "that spell" is the spell you
# copied (the trigger's event carries it, triggers.py "orig110j"). If it has left the stack by then, it is copied as it last existed there: 608.2h
# (an effect needing information from an object no longer in the expected public zone uses its last known information) with 707.10 (the copy has
# its characteristics and every choice made for it); the engine's copying.lki_spell does this for the Storm cycle too. 707.10c: new targets may be chosen.
PARNESSE = "Whenever you copy a spell, up to one target opponent may also copy that spell. They may choose new targets for that copy."


def parnesse_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != "triggered" or ability.text != PARNESSE:
        return None
    native = scripts.define(replace(ability, text="Whenever you copy a spell, you gain 1 life."), ch)
    if native is None:
        return None
    return {**native, "cond": {**native["cond"], "orig110j": True}, "target": None, "targets": [{"what": "opponent", "min": 0, "max": 1}],
            "effects": [{"do": "parnesse110j"}]}


def parnesse(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    opponents = effects._players(plan, ctx, "target:0")
    other = (ctx.get("event") or {}).get("other")
    if not opponents or not other:
        return True
    decide(plan, player=opponents[0], kind="choose_one", prompt="Parnesse: copy that spell? (you may choose new targets for the copy)",
           options=[DecisionOption(id="yes", label="Copy it"), DecisionOption(id="no", label="Don't")],
           resume={"step": "parnesse110j", "ctx": ctx, "card": other["card"], "oid": other["object_id"]})
    return False


def resume_parnesse(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import copying, effects

    ctx = d.resume["ctx"]
    if chosen == ["yes"]:
        job = copying.new_job(ctx, controller=d.player, objects=[(d.resume["card"], d.resume["oid"], 1)], retarget=True, label="Parnesse")
        if not copying.run(plan, job):
            return
    elif chosen != ["no"]:
        raise ActionError("Choose yes or no")
    effects.continue_effects(plan, ctx)


PRIMITIVES["parnesse110j"] = parnesse
RESUME["parnesse110j"] = resume_parnesse


# -- Magar of the Magic Strings -- the target instant or sorcery card goes onto the battlefield face down as a 3/3 creature with two abilities
# (characteristics.MAGAR_SPEC, 708.2a), and its name is noted on that object (a public choice: copies of the face-down creature don't have it, so
# their trigger makes nothing, ruling 2022-10-07). On combat damage to a player, the copy is made from the noted name's card as it last existed in
# the graveyard (707.14; its Oracle characteristics), and may be cast without paying its mana cost. The exile replacement keeps a blinked one in
# exile (an instant or sorcery card can't enter the battlefield face up, ruling 2022-10-07); an effect turning it face up only reveals it (facedown._turn_up).
MAGAR = ("{1}{B}{R}: Note the name of target instant or sorcery card in your graveyard and put it onto the battlefield face down. It's a 3/3 creature with "
         "\"Whenever this creature deals combat damage to a player, you may create a copy of the card with the noted name. You may cast the copy without paying its mana cost\" "
         "and \"If this creature would leave the battlefield, exile it instead of putting it anywhere else.\"")
MAGAR_KEY = "Noted name"


def magar_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import card_copy_sources, characteristics, scripts

    if ability.kind == "activated" and ability.text == MAGAR:
        native = scripts.define(replace(ability, text="{1}{B}{R}: Return target instant or sorcery card from your graveyard to your hand."), ch)
        return {**native, "effects": [{"do": "magar110j"}]} if native is not None else None
    if ability.kind == "triggered" and ability.text == characteristics.MAGAR_TEXT.split("\n")[0]:
        native = scripts.define(replace(ability, text="Whenever this creature deals combat damage to a player, draw a card."), ch)
        # "you may create a copy": the copy is always made and the cast is the choice (a copy not cast ceases to exist, 707.10a: the same outcome)
        return {**native, "effects": [{"do": "magar_copy110j"}, card_copy_sources.copy_cast()[1]]} if native is not None else None
    return None


def magar(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import characteristics, effects, facedown

    for cid in effects._cards(plan, ctx, "target"):
        card = plan.state.cards[cid]
        if not card.zone.endswith(":graveyard"):
            continue
        name = plan.ch(card).name
        pid = ctx["controller"]
        if facedown.put_face_down(plan, cid, pid, "generic", actor=pid, spec=characteristics.MAGAR_SPEC):
            plan.do({"type": "set_choice", "card_id": cid, "key": MAGAR_KEY, "value": name}, actor=pid)
            plan.note(f"{plan.name(pid)} notes the name {name}", actor=pid)
    return True


def magar_copy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import card_copy_sources, effects

    card = plan.state.cards.get(ctx.get("source_card") or "")
    oid = ctx.get("source_object")
    snap = plan.rules.lki.get(oid or "")
    choices = card.choices if card is not None and plan.oid(card) == oid else snap.choices if snap is not None else {}
    name = choices.get(MAGAR_KEY)
    found = getattr(plan.info, "resolve", lambda n: None)(name) if name else None
    made: list[str] = []
    if card is not None and found is not None:  # (707.14: the card's characteristics as it last existed in the graveyard: its Oracle card)
        created = plan.do({"type": "copy_card", "card_id": card.id, "player": ctx["controller"], "count": 1, "zone": "exile", "printing": found["id"], "name": name},
                          actor=ctx["controller"])
        made = list(getattr(getattr(created, "r", None), "ids", []))
    else:
        plan.note("No name was noted for this creature: no copy is created")  # (a copy of the face-down creature, ruling 2022-10-07)
    effects._remember(plan, ctx, {"as": card_copy_sources.COPIES}, made)
    return True


PRIMITIVES.update({"magar110j": magar, "magar_copy110j": magar_copy})


# -- Ertai's Meddling -- the target spell is exiled with X delay counters as Meddling resolves (ruling 2008-04-01); a copy of a spell has no card, so
# it ceases to exist (707.10a) and gets nothing (ruling 2004-10-04). A delayed triggered ability (603.7) of Meddling's controller triggers at each of
# that player's upkeeps while that card is still that exiled object (an intervening "if", 603.4): it removes a delay counter, and with none left
# the player puts the card itself onto the stack as a copy of the original spell (707.10: its targets, X, modes and kicker; the spliced effects stay,
# ruling 2013-04-15). It isn't cast (601.2i: no cast triggers, not counted, ruling 2013-04-15), it is a new object that can be countered or targeted
# (ruling 2004-10-04), and cast with flashback it is still exiled as it leaves the stack (ruling 2011-01-22, 702.34a). A face-down spell's copy is a
# face-up nameless colorless 2/2 creature spell with no text (ruling 2004-10-04: the copiable values of the face-down spell, 708.2a, 707.2).
MEDDLE_LINES = ("X can't be 0.", "Target spell's controller exiles it with X delay counters on it.",
                "At the beginning of each of that player's upkeeps, if that card is exiled, remove a delay counter from it. If the card has no delay counters on it, "
                "the player puts it onto the stack as a copy of the original spell.")


def meddle_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text not in MEDDLE_LINES or ch.name != "Ertai's Meddling" or (ability.kind != "spell") != (ability.text == MEDDLE_LINES[2]):
        return None
    if ability.text == MEDDLE_LINES[0]:
        return {"kind": "spell", "effects": [], "target": None, "x_min": 1}  # 107.1b
    if ability.text == MEDDLE_LINES[1]:
        return {"kind": "spell", "effects": [{"do": "meddle110j"}], "target": {"what": "spell"}}
    # (read as a triggered line, but it is the spell's delayed triggered ability, 603.7: made by meddle110j as the spell resolves; this
    # definition is inert, a card's own triggered ability never comes from it)
    return {"kind": "spell", "effects": [], "target": None}


def meddle(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    from app.game.rules_state import DelayedTrigger
    from app.rules import copying, effects

    r = plan.rules
    for cid in effects._cards(plan, ctx, "target"):
        card = plan.state.cards[cid]
        if card.zone != "stack" or card.ability is not None:
            continue
        entry = r.stack.get(cid)
        player = entry.controller if entry is not None else card.controller
        old = plan.oid(card)
        if card.is_token:  # a copy of a spell: exiled, it ceases to exist (707.10a); no counters, nothing comes back
            plan.do({"type": "move", "card_ids": [cid], "to": {"zone": "exile"}}, actor=player)
            continue
        record = {"player": player, "orig": old, "entry": entry.model_dump(mode="json") if entry is not None else None,
                  "info": card.stack_info.model_dump(mode="json") if card.stack_info is not None else None,
                  "flashback": old in r.flashback, "evoked": cid in r.evoked, "dashed": cid in r.dashed,
                  "face_down": copying.face_down_recipe(card).model_dump(mode="json") if card.face_down else None}
        r.flashback = [o for o in r.flashback if o != old]  # (it is exiled now: by Meddling, not by flashback)
        plan.do({"type": "move", "card_ids": [cid], "to": {"zone": "exile"}}, actor=player)
        card = plan.state.cards[cid]
        if not card.zone.endswith(":exile"):
            continue
        n = max(0, int(ctx.get("x") or 0))
        plan.do({"type": "set_counter", "card_id": cid, "kind": "delay", "value": n}, actor=player)
        r.meddled110j[cid] = {**record, "exiled": plan.oid(card)}
        r.delayed.append(DelayedTrigger(
            id=secrets.token_hex(4), controller=ctx["controller"], source_card=ctx.get("source_card"), source_object=ctx.get("source_object"),
            name=ctx.get("name") or "Ertai's Meddling", when={"kind": "step", "step": "upkeep", "whose": "payer", "player": player},
            turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=r.step_serial, once=False,
            effects=[{"do": "meddle_tick110j", "card": cid, "object": plan.oid(card)}]))
        plan.note(f"{card.name} is exiled with {n} delay counter{'s' if n != 1 else ''} on it", [cid], actor=player)
    return True


def meddle_live(plan: Plan, e: dict[str, Any]) -> bool:
    card = plan.state.cards.get(e["card"])
    return card is not None and card.zone.endswith(":exile") and plan.oid(card) == e["object"] and e["card"] in plan.rules.meddled110j


def meddle_tick(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import StackEntry
    from app.game.state import StackInfo
    from app.rules import copying

    r = plan.rules
    if not meddle_live(plan, e):  # 603.4: checked again as it resolves
        return True
    cid = e["card"]
    card = plan.state.cards[cid]
    rec = r.meddled110j[cid]
    left = max(0, int(card.counters.get("delay", 0)) - 1) if card.counters.get("delay", 0) else 0
    if card.counters.get("delay", 0):
        plan.do({"type": "set_counter", "card_id": cid, "kind": "delay", "value": left}, actor=rec["player"])
    if left:
        return True
    player = rec["player"]
    r.delayed = [t for t in r.delayed if not (t.effects and t.effects[0].get("do") == "meddle_tick110j" and t.effects[0]["card"] == cid)]
    del r.meddled110j[cid]
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": player, "zone": "stack"}}, actor=player)
    card = plan.state.cards[cid]
    if card.zone != "stack":
        return True
    oid = plan.oid(card)
    if rec["entry"] is not None:
        entry = StackEntry.model_validate(rec["entry"])
        r.stack[cid] = copying._entry_copy(entry, controller=player, source=(cid, oid), orig=rec["orig"])
    if rec["info"] is not None:
        info = StackInfo.model_validate(rec["info"])
        payload: dict[str, Any] = {"type": "set_stack_info", "card_id": cid, "tags": list(info.tags)}
        if info.x is not None:
            payload["x"] = info.x
        if info.modes:
            payload["modes"] = list(info.modes)
        plan.do(payload, actor=player)
    if rec["flashback"]:
        r.flashback.append(oid)  # 702.34a: still exiled as it leaves the stack (ruling 2011-01-22)
    for marks, kept in ((r.evoked, rec["evoked"]), (r.dashed, rec["dashed"])):
        if kept:
            marks.append(cid)
    if rec["face_down"] is not None:
        from app.game.rules_state import CopyRecipe

        copying.add_copy_effect(plan, [oid], CopyRecipe.model_validate(rec["face_down"]), player, label=copying.MEDDLE_COPY)
    copying._payment_alias(plan, rec["orig"], oid, cid, player)
    plan.note(f"{plan.name(player)} puts {plan.ch(card).name or 'the card'} onto the stack as a copy of the original spell (it isn't cast)", [cid], actor=player)
    return True


PRIMITIVES.update({"meddle110j": meddle, "meddle_tick110j": meddle_tick})
