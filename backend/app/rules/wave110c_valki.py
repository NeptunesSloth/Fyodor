"""-- Valki, God of Lies // Tibalt, Cosmic Impostor (wave 110C) --

* Valki ETB: 701.20a each opponent reveals their hand (all at once); the controller then chooses one creature card from each hand and exiles it
  until Valki leaves the battlefield (610.3: it returns to the hand it came from); the exile is linked (607.2a) to Valki's second ability.
* Valki {X}: 607.2a the creature cards exiled with Valki, mana value X (the announced X, 107.3); the controller chooses one, Valki becomes a copy
  of it (707.2, layer 1, no duration: 611.2a).
* Tibalt: "As Tibalt enters, you get an emblem" (614.12: done as it enters, no trigger). The emblem's permission reads the cards exiled with that
  Tibalt object (his +2, -3 and -8 are the exiling abilities, 607.2a/b); a Tibalt that left (400.7) keeps them, a new Tibalt object has none.
"""
from __future__ import annotations

import re
import threading
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

_VALKI_ETB = ("When Valki enters, each opponent reveals their hand. For each opponent, exile a creature card they revealed this way until Valki leaves "
              "the battlefield.")
_VALKI_X = "{X}: Choose a creature card exiled with Valki with mana value X. Valki becomes a copy of that card."
_AS_ENTERS = re.compile(r'^As (?:Tibalt|~|this planeswalker) enters, you get an emblem with "(?P<text>[^"]+)"$')
_EMBLEM = ("You may play cards exiled with Tibalt, Cosmic Impostor, and you may spend mana as though it were mana of any color to cast those spells.")
_EXILERS = {"+2: Exile the top card of each player's library.", "−3: Exile target artifact or creature.", "−8: Exile all graveyards. Add {R}{R}{R}."}
LINKED = "Linked to"
_ON = threading.local()


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = ability.text
    if text == _VALKI_ETB or text.replace("~", "Valki") == _VALKI_ETB:
        native = scripts.define(replace(ability, text="When Valki enters, you gain 1 life."), ch)
        return None if native is None else {**native, "effects": [{"do": "valki_etb110c"}]}
    if text == _VALKI_X or text.replace("~", "Valki") == _VALKI_X:
        native = scripts.define(replace(ability, text="{X}: You gain 1 life."), ch)
        return None if native is None else {**native, "effects": [{"do": "valki_copy110c"}]}
    if (m := _AS_ENTERS.fullmatch(text)) is not None and m["text"] == _EMBLEM:
        return {"kind": "static", "static": "emblem_enter110c", "effects": []}
    if text == _EMBLEM:
        return {"kind": "static", "static": "permission", "zone": "exile", "linked": True, "linked_to110c": True, "linked_look": False,
                "linked_face_down": False, "spend": "color", "once": False, "flash": False, "self": False, "play": True, "cast": True,
                "filter": None, "effects": []}
    if ch.name == "Tibalt, Cosmic Impostor" and text in _EXILERS and not getattr(_ON, "busy", False):
        _ON.busy = True
        try:
            native = scripts.define(ability, ch)
        finally:
            _ON.busy = False
        if native is None:
            return None
        return {**native, "effects": [{**e, "link": True} if e.get("do") in ("exile", "exile_top") else e for e in native["effects"]]}
    return None


def valki_etb(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    me = ctx["controller"]
    opps = [p for p in plan.apnap() if p != me and not plan.state.players[p].left]
    hands: dict[str, list[str]] = {}
    for p in opps:
        hands[p] = list(plan.state.zones.get(f"{p}:hand", []))
        if hands[p]:
            plan.do({"type": "reveal", "card_ids": hands[p]}, actor=p)
        else:
            plan.note(f"{plan.name(p)} reveals an empty hand", actor=p)
    if not ctx.get("hide_queued"):
        ctx["hide_queued"] = True
        ctx["effects"].append({"do": "hide_revealed"})
    sel = '{"card":true,"types":["Creature"],"zones":[]}'
    at = ctx["next"]
    steps: list[dict[str, Any]] = []
    for i, p in enumerate(opps):
        steps += [{"do": "revealed_of110c", "cards": hands[p]},
                  {"do": "choose_from_hand", "who": "you", "sel": f"sel:{sel}", "n": 1, "label": "creature card", "optional": False, "as": f"valki{i}"},
                  {"do": "exile_until", "who": f"ref:valki{i}", "hand_origin": True, "link": True}]
    ctx["effects"][at:at] = steps
    return True


def revealed_of(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    ctx["revealed"] = list(e["cards"])
    return True


def valki_copy(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, exiled_with, values
    from app.rules.plan import decide

    r = plan.rules
    x = int(values.evaluate(plan, ctx, {"x": 1}))
    pool: list[str] = []
    for oid in r.exiled_with.get(exiled_with.link_key(ctx), []):
        cid = oid.rsplit(".", 1)[0]
        card = plan.state.cards.get(cid)
        if card is None or not card.zone.endswith(":exile") or plan.oid(card) != oid or card.face_down:
            continue
        ch = plan.ch(card)
        if "Creature" in ch.types and ch.mana_value == x:
            pool.append(cid)
    if not pool:
        plan.note(f"{ctx.get('name') or 'It'}: no creature card exiled with it has mana value {x}", actor=ctx["controller"])
        return True
    if len(pool) == 1:
        return _become(plan, ctx, pool[0])
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"Choose a creature card exiled with {ctx.get('name') or 'it'} with mana value {x}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool], min_choices=1, max_choices=1,
           resume={"step": "valki_copy110c", "ctx": ctx}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    _ = context
    return False


def _become(plan: Plan, ctx: dict[str, Any], cid: str) -> bool:
    from app.rules import context, copying

    context.bind_objects(plan, ctx, "valki_pick110c", [cid])
    return copying.become_copy(plan, ctx, {"do": "become_copy", "who": "self", "with": "ref:valki_pick110c"})


def resume_valki_copy(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen:
        _become(plan, ctx, chosen[0])
    effects.continue_effects(plan, ctx)


def apply_enter(plan: Plan, card: CardInstance) -> None:
    """614.12: the emblem is made as Tibalt enters, remembering which Tibalt object it reads."""
    from app.rules import permissions

    for src, _, _d in permissions._table_statics(plan.state, plan.info, {"emblem_enter110c"}):
        if src.id != card.id:
            continue
        before = set(plan.state.cards)
        plan.do({"type": "create_token", "player": card.controller, "count": 1, "stacked": False,
                 "token": {"name": f"{plan.ch(card).name} Emblem", "type_line": "Emblem", "text": _EMBLEM}}, actor=card.controller)
        for cid in set(plan.state.cards) - before:
            plan.do({"type": "set_choice", "card_id": cid, "key": LINKED, "value": plan.oid(card)}, actor=card.controller)


PRIMITIVES = {"valki_etb110c": valki_etb, "revealed_of110c": revealed_of, "valki_copy110c": valki_copy}
RESUME = {"valki_copy110c": resume_valki_copy}
