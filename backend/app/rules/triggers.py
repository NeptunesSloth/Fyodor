"""Triggered abilities (CR 603), researched against CR 2026-09-25.

* **Triggering (603.2):** after each step the engine looks at the new event batch. "When ~
  enters" checks the object as it is now; leaves-the-battlefield and "dies" abilities *look back
  in time* (603.10a) and use the object's last known information, so a token that died still
  triggers. Step triggers ("at the beginning of your upkeep") are added when the step starts;
  "whenever ~ attacks" when attackers are declared.
* **Waiting (603.3):** triggered abilities go on the stack the next time a player would receive
  priority, after state-based actions.
* **APNAP (603.3b):** the active player puts theirs on the stack first, then each other player
  in turn order, so the last player's triggers resolve first. A player with several triggers
  orders them (a private ORDER decision), unless they are identical and AUTO ORDER IDENTICAL
  TRIGGERS is on. Network arrival order never matters: the engine decides the sequence.
* **Targets (603.3d):** chosen as the ability goes on the stack; with no legal target the
  ability is removed. "You may" is decided on resolution (603.5).
* Triggers from manual (sandbox) changes are not created automatically: whoever moves cards by
  hand handles their triggers by hand. With AUTO TRIGGER STACKING off (ASSISTED), the table
  confirms before the engine puts them on the stack.

* **What it triggered on (603.2, 608.2k):** each trigger carries a TriggerEvent (the objects, as
  they were — last known information for ones that left, 603.10a — the objects they became where
  they went, 400.7e, the player it was about, the amount): "it", "that creature", "its power",
  "that player", "that much" read it through app/rules/context.py, never the board as it is later.
* **Generic conditions (app/rules/events.py):** matched against the event log: zone changes,
  damage, life, draws, spells cast (the Nth each turn, from which zone, what they target),
  sacrifices (701.21a), discards and cycling (701.9a, 702.29), tokens created (111.2), counters
  put (122.6), cards leaving a graveyard (603.10a); and, as they happen, attacks (alone, with N
  creatures: 506.5, 508.3), blocks (509.3a-d) and targeting (115.1).

* **Delayed triggered abilities (603.7, app/rules/delayed.py):** created as a spell or ability
  resolves, with the objects they refer to bound then; they trigger here like the others (at a
  step's start, or from the event log: ``delayed.at_step`` / ``delayed.on_events``) and take the
  same APNAP road onto the stack.

* **What was attached (603.10a, 400.7f):** "When enchanted creature dies" / "Whenever equipped
  creature leaves the battlefield" look back in time: the object's last known information lists the
  permanents attached to it (ObjectSnapshot.attached); "return this card" finds the Aura's new object
  in its owner's graveyard (400.7f). Chapter abilities of Sagas: app/rules/sagas.py.

Reflexive triggers (603.12, wave 3R1) are added during a resolution by effects.reflexive and put on the
stack like any other pending trigger. Not yet: copies of spells
(707.10) as "cast or copy"; state triggers (603.8).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import replace
from typing import Any

from app.game.rules_state import (
    DecisionOption,
    Event,
    ObjectRef,
    ObjectSnapshot,
    PendingTrigger,
    StackEntry,
    TriggerEvent,
    emit,
    track,
)
from app.game.state import CardInstance, TokenDef
from app.rules import characteristics as chars
from app.rules import delayed, layers, scripts, selectors
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan, decide
from app.rules.targets import choose_groups, label, legal_targets, ref, source_of


def _zone(key: str | None) -> str:
    return (key or "").rsplit(":", 1)[-1]


# A trigger condition naming several events triggers on each of them (603.2).
TRIGGER_EVENTS = {"enters_or_attacks_self": ("enters_self", "attacks_self")}


def _matches_trigger(name: str, trigger: str) -> bool:
    if name.startswith("multi:"):
        return trigger in name[6:].split("+")
    return name == trigger or trigger in TRIGGER_EVENTS.get(name, ())


def abilities(plan: Plan, ch: Characteristics, trigger: str) -> list[tuple[int, dict[str, Any]]]:
    found = [(i, d) for i, d in scripts.definitions(ch).items()
             if d["kind"] == "triggered" and _matches_trigger(d["trigger"], trigger)]
    return found + [(i, d) for i, d in scripts.keyword_triggers(ch) if d["trigger"] == trigger]


def _lki_characteristics(plan: Plan, snap: ObjectSnapshot) -> Characteristics:
    card = CardInstance(id=snap.card, card_id=snap.printing, name=snap.name, owner=snap.owner, controller=snap.controller,
                        zone=snap.zone, face=snap.face, face_down=snap.face_down, is_token=snap.is_token,
                        token=TokenDef(name=snap.name, text=snap.text, power=snap.token_power, toughness=snap.token_toughness,
                                      colors=snap.token_colors, type_line=snap.token_type_line or "Token Creature")
                        if snap.is_token and not snap.printing else None)
    ch = chars.of(card, plan.info)
    # -- copy system (wave 2F): its copiable values as they were (a dying Clone's abilities) --
    from app.rules import copying

    ch = copying.lki(plan, snap, ch)
    if snap.power is not None and snap.toughness is not None:
        ch = replace(ch, pt=(snap.power, snap.toughness))  # as it last existed (608.2h)
    # -- quoted grants (wave 2D) -- the abilities and keywords it had (603.10a): granted ones too
    from app.rules import granted

    return granted.as_last_existed(ch, snap)


def _add(plan: Plan, *, controller: str, source_card: str, source_object: str, name: str, index: int,
         definition: dict[str, Any], manual: bool = False, event: TriggerEvent | None = None) -> PendingTrigger | None:
    if manual:
        return None
    if definition.get("if_kicked"):  # 603.4: "When ~ enters, if it was kicked, …" (702.33e)
        record = plan.rules.payments.get(source_object)
        if record is None or not record.kicked:
            return None  # (it wasn't: the ability doesn't trigger; kicked status never changes later)
    if definition.get("if") is not None:  # 603.4: an intervening "if" must hold as it triggers
        from app.rules import conditions

        # (the source and the event it triggered on: "if ~ is an enchantment", "if it's a Dragon", 603.4)
        check = {"controller": controller, "source_card": source_card, "source_object": source_object,
                 "event": event.model_dump(mode="json") if event is not None else None}
        if not conditions.holds(plan, check, definition["if"]):
            return None
    if definition.get("limit") == "once_each_turn":  # "This ability triggers only once each turn." (app/rules/restrictions.py)
        from app.rules import restrictions

        if restrictions.uses(plan.rules, source_object, index, plan.state.turn.number):
            return None  # it triggered this turn already (even if that ability was countered or removed)
        restrictions.record_use(plan.rules, source_object, index, plan.state.turn.number)
    if definition.get("limit") == "do_once":  # "Do this only once each turn." (603.2h, app/rules/restrictions.py)
        from app.rules import restrictions

        if restrictions.uses(plan.rules, source_object, index, plan.state.turn.number):
            return None  # its controller already took the indicated action this turn
        # the action counts as taken when the resolution gets to the end of the effects
        # (effects.record_action): not if countered, declined, or a payment it hinges on wasn't made
        # (and several instances that triggered together: only the first to resolve does it)
        mark = {"object": source_object, "index": index}
        definition = {**definition, "effects": [{"do": "action_gate", **mark}, *definition["effects"],
                                                {"do": "record_action", **mark}]}
    # -- this-turn history (wave 4D) -- "if this is the second time this ability has resolved this turn"
    from app.rules import history

    if "effects" in definition:
        definition = {**definition, "effects": history.counting_resolutions(definition["effects"], f"{source_object}:{index}")}
    pending = PendingTrigger(id=secrets.token_hex(4), controller=controller, source_card=source_card,
                             source_object=source_object, name=name, ability=definition, key=f"{name}:{index}",
                             event=event)
    plan.rules.pending_triggers.append(pending)
    return pending


def _entered(plan: Plan, card: CardInstance, oid: str) -> TriggerEvent:
    """"Whenever [another] creature enters": the event is that object entering."""
    return TriggerEvent(kind="enter", objects=[ObjectRef(card=card.id, object_id=oid, zone=card.zone)], count=1)


HIDDEN = ("hand", "library")


def _new_ref(card_id: str, new_oid: str | None, to_zone: str | None) -> list[ObjectRef]:
    """The object a card became where it went (400.7e: a zone-change trigger can find it there, if
    that zone is public — 603.6: never in a hidden zone such as a library or a hand)."""
    if not new_oid or not to_zone or _zone(to_zone) in HIDDEN:
        return []
    return [ObjectRef(card=card_id, object_id=new_oid, zone=to_zone)]


def _left(kind: str, snap: ObjectSnapshot, e: Event) -> TriggerEvent:
    """A leaves-the-battlefield / dies event of one object: as it last existed on the battlefield
    (603.10a) and the new object it became where it went (400.7e, 603.6c)."""
    return TriggerEvent(kind=kind, batch=e.batch, count=1,
                        objects=[ObjectRef(card=snap.card, object_id=snap.object_id, zone=snap.zone, snapshot=snap)],
                        new_objects=_new_ref(snap.card, e.new_object_id, e.to_zone))


def sacrificing(plan: Plan, card_ids: list[str]) -> None:
    """701.21a: these permanents are about to be sacrificed (call just before moving them, so the
    event joins the move's batch): "Whenever you sacrifice …" (603.10a: looks back in time)."""
    for cid in card_ids:
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":battlefield"):
            emit(plan.state, "sacrificed", object_id=plan.oid(card), card=cid, player=card.controller)


def collect(plan: Plan) -> None:
    """Look at the events since the last look (603.2)."""
    r = plan.rules
    delayed.expire(plan)  # "for as long as …" effects whose duration ended (611.2b; app/rules/delayed.py)
    layers.control_sync(plan)  # -- control (wave 3K) -- layer 2 (613.1b), and what its changes end (611.2b)
    # -- counters & designations (wave 3E): daybound / nightbound permanents (702.145c-g), before any trigger is looked at
    from app.rules import designations

    designations.day_night_sync(plan)
    if any(e.batch > r.batch for e in r.events):
        # An event recorded after the step's last table change (a spell becoming cast, 601.2i)
        # is its own batch: close it now, before anyone would receive priority (603.3), rather
        # than letting it join whatever table change comes next (the spell resolving)
        track(plan.state)
    new =[e for e in r.events if r.trigger_batch < e.batch <= r.batch]  # finished batches only
    if not new:
        return
    r.trigger_batch = max(e.batch for e in new)
    returning: dict[int, list[dict[str, Any]]] = {}  # batch -> the cards returning "until ~ leaves" (610.3c)
    from app.rules import history  # -- this-turn history (wave 4D) -- before any trigger checks a condition

    history.note_events(plan, new)
    _generic_events(plan, new)
    delayed.on_events(plan, new)  # "when that creature dies this turn" (603.7; app/rules/delayed.py)
    # -- sagas & attached-object triggers (wave 3S): chapter abilities (714.2b) --
    from app.rules import sagas

    sagas.lore_triggers(plan, new)
    # -- counters & designations (wave 3E): 726.2 "whenever a player takes the initiative" --
    from app.rules import designations

    designations.on_events(plan, new)
    for e in new:
        if e.kind == "spell_cast" and not e.manual:
            _cast_triggers(plan, e.card or "", e.player or "")
            continue
        if e.kind == "counters" and e.counter == "defense" and e.amount < 0 and not e.manual:
            from app.rules import battles  # 310.12b: "When the last defense counter is removed …"

            battles.defeated_triggers(plan, e)
            continue
        if e.kind != "zone_change" or e.manual:
            continue
        frm, to = _zone(e.from_zone), _zone(e.to_zone)
        if to == "battlefield" and frm != "battlefield":
            # (as it is, or as it was if it has already left again: it still entered, 603.6a)
            got = _object_then(plan, e.card, e.new_object_id)
            if got is None or plan.rules.card_mode(got[0].id) == "manual" or not e.new_object_id:
                continue
            card, ch = got
            entered = TriggerEvent(kind="enter", batch=e.batch, count=1,
                                   objects=[ObjectRef(card=card.id, object_id=e.new_object_id, zone=e.to_zone)])
            for i, d in abilities(plan, ch, "enters_self"):
                _add(plan, controller=card.controller, source_card=card.id, source_object=e.new_object_id,
                     name=ch.name, index=i, definition=d, event=entered.model_copy(deep=True))
            _other_enters(plan, card, ch, e.new_object_id)
        if frm == "battlefield" and to != "battlefield":
            snap = r.lki.get(e.object_id or "")
            if snap is None or plan.rules.card_mode(snap.card) == "manual" or snap.controller not in plan.live():
                continue
            ch = _lki_characteristics(plan, snap)  # looks back in time (603.10a)
            if snap.object_id in plan.rules.linked_exile:  # 610.3c: "… until ~ leaves" ends: they return at once
                from app.rules.effects import linked_entries

                returning.setdefault(e.batch, []).extend(linked_entries(plan, snap.object_id))
            died = to == "graveyard" or (e.to_zone is None and snap.is_token)  # 700.4
            kinds = ["ltb_self"] + (["dies_self"] if died else [])
            for kind in kinds:
                for i, d in abilities(plan, ch, kind):
                    if d.get("unless_counter") and snap.counters.get(d["unless_counter"], 0) > 0:
                        continue  # persist / undying: "if it had no … counters on it"
                    _add(plan, controller=snap.controller, source_card=snap.card, source_object=snap.object_id,
                         name=ch.name, index=i, definition=d, event=_left("die" if kind == "dies_self" else "leave", snap, e))

    entries = [entry for batch in sorted(returning) for entry in returning[batch]]
    if entries:
        # 610.3d: the one-shot effects created right after simultaneous events (a board wipe that
        # took several "until ~ leaves" sources) are simultaneous too — one entry, not one per
        # source. (Departures of separate batches seen in one look are rare; they return together.)
        from app.rules import attachments  # (attachments → effects → this module)

        attachments.enter(plan, entries, None)


# -- generic conditions (app/rules/events.py) --------------------------------------------------
# (event, object, its characteristics, player, details): details of the event for the trigger's
# context — "oid" (the object as it was), "snap" (its last known information if it had left),
# "new_oid"/"to" (the object it became and where), "recipient" (the player dealt damage),
# "actor" (the player who did it: sacrificed, discarded, cycled, created, cast), "source_oid"
# (a damage source), "amount", and per event what its condition can ask about (the number of
# attackers, the creature on the other side of a block, the zone a spell was cast from …)
Fact = tuple[str, CardInstance | None, Characteristics | None, str | None, dict[str, Any]]


def _event_watchers(plan: Plan) -> list[tuple[CardInstance, Characteristics, int, dict[str, Any]]]:
    return [w for w in _watchers(plan, "event") if w[3].get("cond")]


def _snapshot_card(plan: Plan, snap: ObjectSnapshot) -> tuple[CardInstance, Characteristics]:
    """The object as it last existed on the battlefield (603.10a: leaves-the-battlefield triggers
    look back in time)."""
    ch = _lki_characteristics(plan, snap)
    card = CardInstance(id=snap.card, card_id=snap.printing, name=snap.name, owner=snap.owner, controller=snap.controller,
                        zone=snap.zone, face=snap.face, face_down=snap.face_down, is_token=snap.is_token,
                        attached_to=snap.attached_to,
                        counters=dict(snap.counters))  # (wave 3S: "each page counter on this Aura", 608.2h)
    return card, ch


def _object_then(plan: Plan, card_id: str | None, object_id: str | None) -> tuple[CardInstance, Characteristics] | None:
    """The object an event happened to: as it is now if it's still that object on the
    battlefield, else as it last existed there (it left since: 603.10, 608.2h)."""
    card = plan.state.cards.get(card_id or "")
    if card is not None and card.zone.endswith(":battlefield") and (object_id is None or plan.oid(card) == object_id):
        return card, plan.ch(card)
    snap = plan.rules.lki.get(object_id or "")
    return _snapshot_card(plan, snap) if snap is not None else None


def _card_in(plan: Plan, card_id: str | None, zone: str | None) -> tuple[CardInstance, Characteristics] | None:
    """A card as it was in a zone other than the battlefield (a graveyard, a hand, the stack): its
    own characteristics there (603.10a: "leaves your graveyard" looks back in time)."""
    card = plan.state.cards.get(card_id or "")
    if card is None or zone is None:
        return None
    then = card if card.zone == zone else card.model_copy(update={"zone": zone, "counters": {}, "tapped": False})
    return then, chars.of(then, plan.info)


def _live(plan: Plan, obj: CardInstance) -> bool:
    return plan.state.cards.get(obj.id) is obj


def _facts(plan: Plan, e: Event, window: dict[str, Any]) -> list[Fact]:
    r = plan.rules
    if e.kind == "zone_change":
        return _zone_facts(plan, e)
    if e.kind in ("tapped", "untapped"):
        got = _object_then(plan, e.card, e.object_id)
        return [(e.kind, got[0], got[1], got[0].controller, {"oid": e.object_id})] if got is not None else []
    if e.kind in ("life_gain", "life_loss"):
        return [("gain_life" if e.kind == "life_gain" else "lose_life", None, None, e.player, {"amount": e.amount})]
    if e.kind == "spell_cast":
        spell = plan.state.cards.get(e.card or "")
        if spell is None:
            return []
        entry = r.stack.get(spell.id)
        # 601.2i: what the condition can ask about the spell as it became cast — the Nth spell its
        # caster cast this turn, the zone it was cast from, its targets (115.9b), whether it was kicked
        nth = e.amount or r.spells_this_turn(e.player or "", plan.state.turn.number)
        info = {"oid": plan.oid(spell), "actor": e.player, "nth": nth, "from": window["cast_from"].get(spell.id),
                "opponent_turn": plan.active != e.player, "kicked": bool(entry is not None and entry.kicked),
                "targets": [(t.id, t.object_id) for t in (entry.targets if entry is not None else [])]}
        # -- unless pays (wave 4C) -- "their first noncreature spell each turn"
        from app.rules import unless_pays

        info["kinds_before"] = unless_pays.mark_cast(plan, e.player or "", plan.ch(spell).types)
        return [("cast", spell, plan.ch(spell), e.player, info)]
    if e.kind == "spell_copied":  # -- refused copy/mana (wave 3R3) -- 707.10: a copy put on the stack, not cast
        spell = plan.state.cards.get(e.card or "")
        if spell is None or spell.zone != "stack" or plan.oid(spell) != e.object_id:
            return []
        entry = r.stack.get(spell.id)
        return [("copy", spell, plan.ch(spell), e.player, {
            "oid": e.object_id, "actor": e.player,
            "targets": [(t.id, t.object_id) for t in (entry.targets if entry is not None else [])]})]
    if e.kind == "drew":
        return [("draw", None, None, e.player, {"amount": 1})]
    if e.kind == "cycled":  # 702.29: the card is in its owner's graveyard now (702.29c)
        card = plan.state.cards.get(e.card or "")
        if card is None:
            return []
        return [("cycle", card, plan.ch(card), e.player, {"oid": plan.oid(card), "actor": e.player, "amount": 1})]
    if e.kind == "sacrificed":  # 701.21a; 603.10a: looks back in time
        got = _object_then(plan, e.card, e.object_id)
        if got is None:
            return []
        live = _live(plan, got[0])
        return [("sacrifice", got[0], got[1], e.player, {"oid": e.object_id, "actor": e.player, "amount": 1,
                                                          "snap": None if live else r.lki.get(e.object_id or "")})]
    if e.kind == "counters" and e.amount > 0:  # 122.6: counters put on a permanent
        got = _object_then(plan, e.card, e.object_id)
        if got is None:
            return []
        return [("counters_put", got[0], got[1], got[0].controller,
                 {"oid": e.object_id, "counter": e.counter, "amount": e.amount,
                  "snap": None if _live(plan, got[0]) else r.lki.get(e.object_id or "")})]
    if e.kind == "damage":
        return _damage_facts(plan, e)
    if e.kind == "player_counters" and e.amount > 0 and e.player:  # -- counters & designations (wave 3E): 122.6 a player got counters --
        return [("player_counters", None, None, e.player, {"counter": e.counter, "amount": e.amount})]
    if e.kind == "designation":  # -- counters & designations (wave 3E) --
        from app.rules import designations

        return designations.facts(plan, e)
    return []


def _zone_facts(plan: Plan, e: Event) -> list[Fact]:
    r = plan.rules
    frm, to = _zone(e.from_zone), _zone(e.to_zone)
    out: list[Fact] = []
    if to == "battlefield" and frm != "battlefield":
        # (if it has left again since, as it was on the battlefield: it still entered, 603.6a)
        got = _object_then(plan, e.card, e.new_object_id)
        if got is not None:
            live = _live(plan, got[0])
            entered: dict[str, Any] = {"oid": e.new_object_id, "snap": None if live else r.lki.get(e.new_object_id or "")}
            out.append(("enter", got[0], got[1], got[0].controller, entered))
            if e.from_zone is None and got[0].is_token:  # 111.2: a token was created
                out.append(("create_token", got[0], got[1], got[0].controller,
                            {**entered, "actor": got[0].controller, "amount": 1}))
        return out
    if frm == "battlefield" and to != "battlefield":
        snap = r.lki.get(e.object_id or "")
        if snap is None:
            return []
        card, ch = _snapshot_card(plan, snap)
        info: dict[str, Any] = {"oid": e.object_id, "snap": snap, "new_oid": e.new_object_id, "to": e.to_zone}
        out.append(("leave", card, ch, snap.controller, info))
        if to == "graveyard" or (e.to_zone is None and snap.is_token):  # 700.4
            out.append(("die", card, ch, snap.controller, info))
        return out
    if frm == "hand" and to == "graveyard" and e.card:
        # 701.9a: "To discard a card, move it from its owner's hand to that player's graveyard" —
        # the rules engine moves a card that way only by discarding it (an effect, a cost, cycling)
        got = _card_in(plan, e.card, e.to_zone)
        if got is not None and (e.from_zone or "").split(":")[0] == got[0].owner:
            out.append(("discard", got[0], got[1], got[0].owner,
                        {"oid": e.new_object_id, "actor": got[0].owner, "amount": 1, "new_oid": e.new_object_id,
                         "to": e.to_zone}))
    if frm == "graveyard" and to != "graveyard" and e.card:
        # "leaves your graveyard": the card as it was there (603.10a looks back in time)
        got = _card_in(plan, e.card, e.from_zone)
        if got is not None:
            out.append(("leave_graveyard", got[0], got[1], got[0].owner,
                        {"oid": e.object_id, "new_oid": e.new_object_id, "to": e.to_zone, "amount": 1}))
    return out


def _damage_facts(plan: Plan, e: Event) -> list[Fact]:
    r = plan.rules
    out: list[Fact] = []
    # (a creature dealt lethal damage was still dealt it: 510.3a / 603.10a)
    got = _object_then(plan, e.card, e.object_id) if e.player is None and (e.card or e.object_id) else None
    if got is not None:
        out.append(("dealt_damage", got[0], got[1], got[0].controller,
                    {"oid": e.object_id, "snap": None if _live(plan, got[0]) else r.lki.get(e.object_id or ""),
                     "amount": e.amount, "source_oid": e.source, "combat": e.combat}))
    elif e.player is not None:  # "you're dealt combat damage", "an opponent is dealt noncombat damage"
        out.append(("dealt_damage", None, None, e.player,
                    {"recipient": e.player, "amount": e.amount, "source_oid": e.source, "combat": e.combat}))
    source = next((c for c in plan.state.cards.values() if plan.oid(c) == e.source), None) if e.source else None
    src = (source, plan.ch(source)) if source is not None else (
        _snapshot_card(plan, r.lki[e.source]) if e.source and e.source in r.lki else None)
    if src is None:
        return out
    base = {"oid": e.source, "snap": None if source is not None else r.lki.get(e.source or ""), "amount": e.amount}
    # "~ deals damage [to a creature / a player]" (120.1): the recipient, as it is or last was
    recipient_is_creature = got is not None and got[1].is_creature
    # (120.1: a planeswalker is dealt damage too — "to a player or planeswalker", 510.2)
    recipient_is_walker = got is not None and "Planeswalker" in got[1].types
    recipient_is_battle = got is not None and "Battle" in got[1].types  # (120.3h)
    out.append(("deal_damage", src[0], src[1], src[0].controller,
                {**base, "combat": e.combat, "recipient": e.player, "recipient_creature": recipient_is_creature,
                 "recipient_planeswalker": recipient_is_walker, "recipient_battle": recipient_is_battle}))
    if e.player is not None and e.player != src[0].controller:
        info = {**base, "recipient": e.player}
        out.append(("deal_damage_opponent", src[0], src[1], src[0].controller, info))
        if e.combat:
            out.append(("deal_combat_damage_player", src[0], src[1], src[0].controller, info))
    return out


_PAIRED = {"block": "block_pair", "blocked": "blocked_pair"}


def _cond_matches(plan: Plan, cond: dict[str, Any], watcher: CardInstance, fact: Fact) -> bool:
    from app.rules import selectors

    event, obj, och, player, info = fact
    you = watcher.controller
    want = cond["event"]
    if want == "multi":  # "Whenever ~ attacks or blocks" (this object; each event, 603.2)
        wanted = [(_PAIRED[x] if cond.get("other") else x) for x in cond["events"]]
        if cond.get("subject") == "host":  # -- attached events (wave 4L) -- what the source is attached to
            return event in wanted and obj is not None and watcher.attached_to is not None and obj.id == watcher.attached_to
        return event in wanted and obj is not None and obj.id == watcher.id and _other_ok(plan, cond, watcher, info)
    if want in _PAIRED and cond.get("other"):
        want = _PAIRED[want]  # 509.3b / 509.3d: once per creature on the other side
    if want == "cast" and cond.get("copy"):  # -- refused copy/mana (wave 3R3) -- magecraft (707.10)
        if event == "copy":
            event = "cast"
        elif cond["copy"] == "only":
            return False
    if want != event:
        return False
    if not _details_ok(plan, cond, watcher, fact):
        return False
    subject = cond["subject"]
    if subject == "player":
        pw = cond["player"]
        if player is None or (pw == "you" and player != you) or (pw == "opponent" and player == you):
            return False
        if event == "dealt_damage" and obj is not None:
            return False  # ("you're dealt damage": a player, not a permanent that player controls)
        if event == "cast":
            return obj is not None and och is not None and selectors.matches(
                plan, selectors.from_key(cond["spell"]), obj, och, you, watcher.id)
        if cond.get("obj"):  # the permanent sacrificed, the card discarded, the token created …
            return obj is not None and och is not None and selectors.matches(
                plan, selectors.from_key(cond["obj"]), obj, och, you, watcher.id)
        return True
    if obj is None or och is None:
        return False
    if subject == "host":  # "enchanted creature" / "equipped creature": what the source is attached to
        if event in ("die", "leave"):  # -- sagas & attached-object triggers (wave 3S) --
            # 603.10a: looks back in time — what was attached to it as it last existed on the battlefield
            snap = info.get("snap")
            return snap is not None and watcher.id in snap.attached
        return watcher.attached_to is not None and obj.id == watcher.attached_to
    if subject == "self_or_host":  # "~ or equipped creature"
        return obj.id == watcher.id or (watcher.attached_to is not None and obj.id == watcher.attached_to)
    if subject in ("self", "self_or") and obj.id == watcher.id:
        return True
    if subject == "self":
        return False
    return selectors.matches(plan, selectors.from_key(cond["sel"]), obj, och, you, watcher.id)


def _other_ok(plan: Plan, cond: dict[str, Any], watcher: CardInstance, info: dict[str, Any]) -> bool:
    """"blocks a creature with flying" / "becomes blocked by a Wall": the creature on the other side."""
    from app.rules import selectors

    if not cond.get("other"):
        return True
    other = plan.state.cards.get(info.get("other") or "")
    return other is not None and selectors.matches(plan, selectors.from_key(cond["other"]), other, plan.ch(other),
                                                   watcher.controller, watcher.id)


def _details_ok(plan: Plan, cond: dict[str, Any], watcher: CardInstance, fact: Fact) -> bool:
    """The parts of a condition beyond its subject and event."""
    from app.rules import selectors

    event, obj, _, player, info = fact
    you = watcher.controller
    if not _other_ok(plan, cond, watcher, info):
        return False
    if cond.get("alone") and info.get("attackers") != 1:  # 506.5
        return False
    if event in ("attack", "unblocked", "you_attack"):
        want = cond.get("defender")
        # "whenever you attack" is once per combat; "whenever a player attacks you" once per player
        # attacked (508.3d, 508.3e): each reads only its own fact
        if event == "you_attack" and bool(want) != ("defended" in info):
            return False
        if want and not _defender_ok(want, watcher, info):
            return False
        if cond.get("first_each_turn") and not info.get("first"):
            return False
        if cond.get("while") is not None:  # "attacks while you control …": part of the trigger event
            from app.rules import conditions

            if not conditions.holds(plan, {"controller": you, "source_card": watcher.id}, cond["while"]):
                return False
    if event == "dealt_damage" and cond.get("combat") is not None and bool(info.get("combat")) != cond["combat"]:
        return False
    n = cond.get("min_attackers")
    if n:
        direct = cond.get("defender") not in (None, "you_or_pw")  # (only the creatures attacking that player)
        attackers = [plan.state.cards[c] for c in info.get("attacking_direct" if direct and "attacking_direct" in info
                                                           else "attacking") or [] if c in plan.state.cards]
        if cond.get("sel"):
            sel = selectors.from_key(cond["sel"])
            attackers = [c for c in attackers if selectors.matches(plan, sel, c, plan.ch(c), you, watcher.id)]
        if len(attackers) < n:
            return False
    if event == "cast":
        if cond.get("nth") and info.get("nth") != cond["nth"]:
            return False
        if cond.get("first_kind"):  # -- unless pays (wave 4C) --
            from app.rules import unless_pays

            if not unless_pays.first_of_kind(cond["spell"], info.get("kinds_before") or []):
                return False
        if cond.get("turn") == "opponent" and not info.get("opponent_turn"):
            return False
        if cond.get("kicked") and not info.get("kicked"):
            return False
        frm = _zone(info.get("from"))
        if cond.get("from") and not (frm == cond["from"] or (cond["from"] == "not_hand" and frm and frm != "hand")):
            return False
        if cond.get("targets") and not _targets_ok(plan, cond["targets"], watcher, info.get("targets") or []):
            return False
    if event == "targeted":
        by = cond.get("by", "any")
        if (by == "you" and info.get("by") != you) or (by == "opponent" and info.get("by") == you):
            return False
        if cond.get("spell_only") and not info.get("spell"):
            return False
        if cond.get("first_each_turn") and not info.get("first"):
            return False
    if event == "counters_put" and cond.get("counter") and info.get("counter") != cond["counter"]:
        return False
    if event == "player_counters" and info.get("counter") != cond.get("counter"):  # (wave 3E: "you get one or more {E}")
        return False
    if event == "deal_damage":
        combat = cond.get("combat")
        if combat is not None and bool(info.get("combat")) != combat:
            return False
        to = cond.get("to", "any")
        recipient = info.get("recipient")
        if (to == "player" and recipient is None) or (to == "you" and recipient != you) or \
                (to == "opponent" and (recipient is None or recipient == you)) or \
                (to == "creature" and not info.get("recipient_creature")) or \
                (to == "planeswalker" and not info.get("recipient_planeswalker")) or \
                (to == "player_or_pw" and recipient is None and not info.get("recipient_planeswalker")) or \
                (to == "player_or_battle" and recipient is None and not info.get("recipient_battle")) or \
                (to == "enchanted_player" and (recipient is None or recipient != watcher.attached_player)):
            return False
    return True


def _defender_ok(want: str, watcher: CardInstance, info: dict[str, Any]) -> bool:
    """Whom the attack was declared against (508.3a, 508.3e, 508.6): ``defended`` is the defending
    player (a planeswalker's controller), ``direct`` whether it was that player (not a planeswalker)."""
    defended, you = info.get("defended"), watcher.controller
    if defended is None:
        return False
    if want == "you_or_pw":  # "attacks you or a planeswalker you control"
        return defended == you
    if not info.get("direct"):
        return False
    if want == "you":
        return defended == you
    if want == "opponent":  # "attacks one of your opponents"
        return defended != you
    if want == "enchanted_player":
        return defended == watcher.attached_player
    return want == "player"


def _targets_ok(plan: Plan, want: str, watcher: CardInstance, targets: list[tuple[str, str | None]]) -> bool:
    """115.9b: "a spell that targets ~ / a creature you control" — the spell's targets as they are now."""
    from app.rules import selectors

    for card_id, oid in targets:
        card = plan.state.cards.get(card_id)
        if card is None or (oid is not None and plan.oid(card) != oid):
            continue
        if want == "self":
            if card.id == watcher.id:
                return True
        elif selectors.matches(plan, selectors.from_key(want), card, plan.ch(card), watcher.controller, watcher.id):
            return True
    return False


Watcher = tuple[CardInstance, Characteristics, int, dict[str, Any]]


# "One or more" triggers already added for an event batch (603.2c): later facts of the batch join
# their event (objects, amount, count) instead of triggering again
Fired = dict[tuple[str, int, int, str], PendingTrigger]


def _ref(obj: CardInstance | None, info: dict[str, Any], plan: Plan) -> ObjectRef | None:
    """The object a fact is about, as a stable reference (the object id it was, its zone, and its
    last known information if it had already left)."""
    if obj is None or not info.get("oid"):
        return None
    snap = info.get("snap")
    return ObjectRef(card=obj.id, object_id=info["oid"], zone=snap.zone if snap is not None else obj.zone,
                     snapshot=snap)


def _source_ref(plan: Plan, oid: str | None) -> ObjectRef | None:
    """The source of damage dealt, as it is (while it's still that object) or last was (608.2h)."""
    if not oid:
        return None
    card = next((c for c in plan.state.cards.values() if plan.oid(c) == oid), None)
    if card is not None:
        return ObjectRef(card=card.id, object_id=oid, zone=card.zone)
    snap = plan.rules.lki.get(oid)
    return ObjectRef(card=snap.card, object_id=oid, zone=snap.zone, snapshot=snap) if snap is not None else None


def _event(plan: Plan, fact: Fact, batch: int) -> TriggerEvent:
    kind, obj, _, player, info = fact
    ref = _ref(obj, info, plan)
    new: list[ObjectRef] = []
    if obj is not None:
        new = _new_ref(obj.id, info.get("new_oid"), info.get("to"))
    if info.get("recipient"):
        players = [info["recipient"]]
    elif info.get("actor"):  # the player who cast, sacrificed, discarded, cycled, created …
        players = [info["actor"]]
    else:
        players = [player] if player and obj is None else []
    return TriggerEvent(kind=kind, batch=batch, objects=[ref] if ref else [], new_objects=new, players=players,
                        source=info.get("source_ref") or (
                            _source_ref(plan, info.get("source_oid")) if kind == "dealt_damage" else None),
                        amount=int(info.get("amount") or 0), count=1)


def _fire_generic(plan: Plan, facts: list[Fact], batch: int, fired: Fired,
                  watchers: list[tuple[Watcher, int, int]] | None = None, left: dict[int, str] | None = None) -> None:
    """Each watcher (with the batches it was on the battlefield for: it sees events from when it
    entered, 603.6a, until it left, 603.10a) against each fact of one event. What the ability
    triggered on is captured now, as a TriggerEvent it carries to resolution (603.2, 608.2k)."""
    for (watcher, ch, i, d), lo, hi in (watchers if watchers is not None else [(w, -1, -1) for w in _event_watchers(plan)]):
        if batch >= 0 and not (lo <= batch <= hi or (lo, hi) == (-1, -1)):
            continue
        cond = d["cond"]
        for fact in facts:
            if not _cond_matches(plan, cond, watcher, fact):
                continue
            nth = cond.get("nth") if cond["event"] == "draw" else None
            if nth and plan.rules.draws_this_turn.get(fact[3] or "", 0) != nth:
                continue
            event = _event(plan, fact, batch)
            info = fact[4]
            # One damage event to several recipients at once is one "deals damage" (and several
            # sources at once one "is dealt damage"): once per batch per object, amounts summed
            one_event = cond["event"] == "dealt_damage" or (cond["event"] == "deal_damage" and cond.get("to", "any") == "any")
            # ("one or more creatures you control attack a player": once for each player attacked, 508.3e)
            per = (info.get("oid") or info.get("recipient") or "") if one_event else \
                info.get("recipient") or info.get("actor") or (info.get("defended") if cond.get("defender") else "") or ""
            if cond.get("aggregate") or one_event:  # "one or more …": once per event batch (603.2c) …
                # (… and per player dealt the damage: "one or more creatures deal combat damage to a player")
                key = (watcher.id, i, batch, per)
                pending = fired.get(key)
                if pending is not None and pending.event is not None:  # the batch's other objects join it
                    if not one_event:
                        pending.event.objects += event.objects
                        pending.event.new_objects += event.new_objects
                    pending.event.amount += event.amount
                    pending.event.count += 1
                    continue
            # -- sagas & attached-object triggers (wave 3S): a watcher that has left since is the object it
            # was (603.10a: "this Aura" reads its last known information, 608.2h), not the card's new object
            source_object = (left or {}).get(id(watcher)) or plan.oid(watcher)
            d = _aura_card_bound(plan, d, (left or {}).get(id(watcher)))
            added = _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=source_object,
                         name=ch.name, index=i, definition=d, event=event)
            if (cond.get("aggregate") or one_event) and added is not None:
                fired[(watcher.id, i, batch, per)] = added


def _generic_events(plan: Plan, events: list[Event]) -> None:
    """Generic "When/Whenever [subject] [event]" conditions against the event log."""
    r = plan.rules
    if r.draws_turn != plan.state.turn.number:
        r.draws_turn, r.draws_this_turn = plan.state.turn.number, {}
    fired: Fired = {}
    # Who was watching when: an object that left in these events saw everything up to and
    # including its leaving (603.10a: two creatures dying together each see the other die; a
    # creature dealt lethal damage was dealt it); one that entered sees events from its entering
    # on (603.6a), not earlier ones.
    big = 1 << 60
    entered: dict[str, int] = {}
    watchers: list[tuple[Watcher, int, int]] = []
    left: dict[int, str] = {}  # (a watcher that left: the object it was, wave 3S)
    window: dict[str, Any] = {"cast_from": {}}
    for e in events:
        if e.kind == "cycled" and not e.manual and e.card in plan.state.cards:
            # 702.29c: "When you cycle ~" triggers from whatever zone the card went to
            card = plan.state.cards[e.card]
            if not plan.manual(card) and card.owner in plan.live():
                ch = plan.ch(card)
                watchers += [((card, ch, i, d), -big, big) for i, d in abilities(plan, ch, "event")
                             if d.get("cond", {}).get("event") == "cycle" and d["cond"].get("subject") == "self"]
        if e.kind != "zone_change":
            continue
        if _zone(e.to_zone) == "stack" and e.card:
            window["cast_from"][e.card] = e.from_zone  # (where a spell was cast from, 601.2a)
        if _zone(e.to_zone) == "battlefield" and _zone(e.from_zone) != "battlefield" and e.new_object_id:
            entered[e.new_object_id] = e.batch
        if _zone(e.to_zone) == "graveyard" and e.new_object_id:  # -- refused zones/sized (wave 3R4) -- (603.10)
            entered[e.new_object_id] = e.batch
        if _zone(e.from_zone) == "battlefield" and _zone(e.to_zone) != "battlefield":
            snap = r.lki.get(e.object_id or "")
            if snap is None or snap.controller not in plan.live() or plan.rules.card_mode(snap.card) == "manual":
                continue
            card, ch = _snapshot_card(plan, snap)
            left[id(card)] = snap.object_id
            watchers += [((card, ch, i, d), entered.get(snap.object_id, -big), e.batch)
                         for i, d in abilities(plan, ch, "event") if d.get("cond")]
    watchers += [(w, entered.get(plan.oid(w[0]), -big), big) for w in _event_watchers(plan)]
    for e in events:
        if e.manual:
            continue
        if e.kind == "drew" and e.player:
            r.draws_this_turn[e.player] = r.draws_this_turn.get(e.player, 0) + 1
        facts = _facts(plan, e, window)
        if facts:
            _fire_generic(plan, facts, e.batch, fired, watchers, left)


def generic_combat(plan: Plan, event: str, cards: list[CardInstance],
                   pairs: list[tuple[CardInstance, CardInstance]] = ()) -> None:  # type: ignore[assignment]
    """"Whenever [creature] attacks / blocks / becomes blocked", "Whenever you attack" (508.3a,
    509.3a/c): one fact per creature; "you attack" once per combat for the attacking player.
    ``pairs`` (this creature, the creature on the other side): "blocks a creature" / "becomes
    blocked by a creature" trigger once for each (509.3b, 509.3d)."""
    if not cards:
        return
    fired: Fired = {}
    attacking = [c.id for c in cards]
    turn = plan.state.turn.number
    facts: list[Fact] = []
    for c in cards:
        info: dict[str, Any] = {"oid": plan.oid(c), "attackers": len(cards), "attacking": attacking}
        if event in ("attack", "unblocked"):  # whom it attacks (508.3a, 509.3g)
            info["defended"], info["direct"] = _defended(plan, c)
        if event == "attack":  # "attacks for the first time each turn" (kept per object per turn)
            key = f"attacked:{info['oid']}"
            info["first"] = plan.rules.once_per_turn.get(key) != turn
            plan.rules.once_per_turn[key] = turn
        facts.append((event, c, plan.ch(c), c.controller, info))
    if event == "attack":  # 506.5 / 508.3d: how many creatures were declared as attackers
        facts.append(("you_attack", None, None, cards[0].controller, {"attackers": len(cards), "attacking": attacking}))
        # 508.3e / 508.3b: once for each player attacked (directly, or through a planeswalker they
        # control), with the creatures attacking them
        groups: dict[str, dict[str, list[str]]] = {}
        for c in cards:
            defended, direct = _defended(plan, c)
            if defended is None:
                continue
            g = groups.setdefault(defended, {"all": [], "direct": []})
            g["all"].append(c.id)
            if direct:
                g["direct"].append(c.id)
        for defended, g in groups.items():
            facts.append(("you_attack", None, None, cards[0].controller,
                          {"defended": defended, "direct": bool(g["direct"]), "attackers": len(g["all"]),
                           "attacking": g["all"], "attacking_direct": g["direct"]}))
    facts += [(_PAIRED[event], c, plan.ch(c), c.controller, {"oid": plan.oid(c), "other": other.id})
              for c, other in pairs if event in _PAIRED]
    _fire_generic(plan, facts, -1, fired)


def _defended(plan: Plan, c: CardInstance) -> tuple[str | None, bool]:
    """The defending player an attacking creature attacks (508.5: a planeswalker's controller), and
    whether it attacks that player rather than a planeswalker."""
    t = c.attacking
    if t is None:
        return None, False
    if t.kind == "player":
        return str(t.id), True
    walker = plan.state.cards.get(t.id)
    return (walker.controller if walker is not None else None), False


def unblocked(plan: Plan, attackers: list[CardInstance]) -> None:
    """509.3g: "Whenever ~ attacks and isn't blocked" — once blockers are declared, each attacking
    creature no creature was declared as a blocker for (509.1h), including one put onto the
    battlefield attacking."""
    generic_combat(plan, "unblocked", attackers)


def _watchers(plan: Plan, trigger: str) -> list[tuple[CardInstance, Characteristics, int, dict[str, Any]]]:
    out = []
    for card in plan.state.cards.values():
        if card.zone.endswith(":graveyard"):  # -- refused zones/sized (wave 3R4) --
            out += graveyard_abilities(plan, card, trigger)
            continue
        if not card.zone.endswith(":battlefield") or not plan.in_game(card) or plan.manual(card):
            continue
        ch = plan.ch(card)
        out += [(card, ch, i, d) for i, d in abilities(plan, ch, trigger) if not graveyard_ability(d)]
    return out


# -- refused zones/sized (wave 3R4) ------------------------------------------------------------------
# 113.6m: a triggered ability whose effect returns its own card "from your graveyard" (``self_gy``)
# functions only in the graveyard: it triggers from there (the card's owner controls it, 603.3a with
# 400.3/108.4a: a card in a graveyard is controlled by no one, so its owner), and never from the
# battlefield. Objects that exist immediately after an event are the ones checked (603.10): a card
# put into the graveyard by an event sees events from that batch on (_generic_events' window).
# Coverage (app/rules/coverage.py) keeps the look-back events (603.10a) and the enchanted-creature
# triggers out, so those stay manual.
def graveyard_ability(d: dict[str, Any]) -> bool:
    import json

    return '"self_gy"' in json.dumps(d, default=str)


def graveyard_abilities(plan: Plan, card: CardInstance, trigger: str,
                        ) -> list[tuple[CardInstance, Characteristics, int, dict[str, Any]]]:
    if card.owner not in plan.live() or plan.manual(card) or not card.zone.endswith(":graveyard"):
        return []
    ch = plan.ch(card)
    if "graveyard" not in (ch.oracle_text or ""):
        return []
    return [(card, ch, i, d) for i, d in abilities(plan, ch, trigger) if graveyard_ability(d) and graveyard_trigger_ok(d)]


_GY_TRIGGERS = ("event", "landfall", "enters_other", "cast_you", "upkeep_you", "end_step_you")
_GY_LOOK_BACK = ("die", "leave", "sacrifice", "leave_graveyard", "multi")  # (603.10a; "multi": not judged here)


def graveyard_trigger_ok(d: dict[str, Any]) -> bool:
    """Is this graveyard ability's trigger one the graveyard watchers above read? Not a look-back
    event (603.10a: a card arriving in the graveyard with the event would have to be told apart),
    nor one about this object or the permanent it was attached to (they left the battlefield)."""
    trigger = str(d.get("trigger"))
    if d.get("kind") != "triggered" or not (trigger in _GY_TRIGGERS or trigger.startswith("step:")):
        return False
    cond = d.get("cond") or {}
    return trigger != "event" or (cond.get("event") not in _GY_LOOK_BACK
                                  and cond.get("subject") not in ("self", "self_or", "host", "self_or_host"))


def _other_enters(plan: Plan, entered: CardInstance, ech: Characteristics, oid: str) -> None:
    """603.6a: "Whenever [another] creature [you control] enters" on every permanent, including
    ones entering at the same time."""
    if ech.is_land:  # "Landfall — Whenever a land you control enters"
        for watcher, ch, i, d in _watchers(plan, "landfall"):
            if entered.controller == watcher.controller:
                _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=plan.oid(watcher),
                     name=ch.name, index=i, definition=d, event=_entered(plan, entered, oid))
    if not ech.is_creature:
        return
    for watcher, ch, i, d in _watchers(plan, "enters_other"):
        f = d.get("filter", "")
        if "another" in f and watcher.id == entered.id:
            continue
        if "you control" in f and entered.controller != watcher.controller:
            continue
        if "nontoken" in f and entered.is_token:
            continue
        _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=plan.oid(watcher), name=ch.name,
             index=i, definition=d, event=_entered(plan, entered, oid))


CAST_FILTERS = {
    "a spell": lambda ch: True,
    "a creature spell": lambda ch: ch.is_creature,
    "a noncreature spell": lambda ch: not ch.is_creature,
    "an instant or sorcery spell": lambda ch: ch.is_instant_or_sorcery,
    "an artifact spell": lambda ch: "Artifact" in ch.types,
    "an enchantment spell": lambda ch: "Enchantment" in ch.types,
}


def _cast_triggers(plan: Plan, spell_id: str, caster: str) -> None:
    spell = plan.state.cards.get(spell_id)
    if spell is None:
        return
    sch = plan.ch(spell)
    for watcher, ch, i, d in _watchers(plan, "cast_you"):
        if watcher.controller == caster and CAST_FILTERS[d.get("filter", "a spell")](sch):
            _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=plan.oid(watcher), name=ch.name,
                 index=i, definition=d)


MONARCH_DRAW = {"kind": "triggered", "trigger": "end_step_you", "effects": [{"do": "draw", "who": "you", "n": 1}],
                "optional": False, "target": None}
MONARCH_STEAL = {"kind": "triggered", "trigger": "combat_damage", "effects": [{"do": "monarch", "who": "you"}],
                 "optional": False, "target": None}


def monarch_end_step(plan: Plan) -> None:
    """725.2: "At the beginning of the monarch's end step, that player draws a card" (no source)."""
    if plan.state.table.monarch == plan.active:
        _add(plan, controller=plan.active, source_card="", source_object="", name="The Monarch", index=0,
             definition=MONARCH_DRAW)


def monarch_damaged(plan: Plan, attackers: list[CardInstance]) -> None:
    """725.2: "Whenever a creature deals combat damage to the monarch, its controller becomes the monarch."
    """
    monarch = plan.state.table.monarch
    for card in attackers:
        if card.controller != monarch:
            _add(plan, controller=card.controller, source_card="", source_object="", name="The Monarch", index=1,
                 definition=MONARCH_STEAL)


def at_step(plan: Plan, trigger: str) -> None:
    """"At the beginning of your upkeep / end step": the active player's permanents."""
    # delayed triggers "at the beginning of the next end step / your next upkeep" (603.7): they join
    # this step's triggers and go on the stack with them in APNAP order (603.3b)
    delayed.at_step(plan, "end" if trigger == "end_step_you" else "upkeep")
    if trigger == "upkeep_you":
        _echo(plan)
        _suspend(plan)
        _cumulative_upkeep(plan)
        _rebound(plan)
    for card in list(plan.state.cards.values()):
        if card.zone.endswith(":graveyard") and card.owner == plan.active:  # -- refused zones/sized (wave 3R4) --
            for _, ch, i, d in graveyard_abilities(plan, card, trigger):
                _add(plan, controller=card.owner, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i,
                     definition=d)
            continue
        if not card.zone.endswith(":battlefield") or card.controller != plan.active or plan.manual(card):
            continue
        ch = plan.ch(card)
        for i, d in abilities(plan, ch, trigger):
            if graveyard_ability(d):
                continue  # (113.6m: it functions only in the graveyard)
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i,
                 definition=d)


def at_step_generic(plan: Plan) -> None:
    """"At the beginning of [whose] [step]" (503.1a, 504, 505, 507, 513): every permanent's
    abilities for this step, when it's the right player's step."""
    phase = plan.state.turn.phase
    prefix = f"step:{phase}:"
    ap = plan.active
    for card in list(plan.state.cards.values()):
        gy = card.zone.endswith(":graveyard")  # -- refused zones/sized (wave 3R4) -- (113.6m)
        if gy and card.owner in plan.live() and not plan.manual(card) and "graveyard" in (plan.ch(card).oracle_text or ""):
            pass
        elif not card.zone.endswith(":battlefield") or plan.manual(card) or card.controller not in plan.live():
            continue
        ch = plan.ch(card)
        for i, d in scripts.definitions(ch).items():
            if d["kind"] != "triggered" or not str(d["trigger"]).startswith(prefix):
                continue
            if graveyard_ability(d) != gy:
                continue
            if _whose_step(plan, card, d["trigger"][len(prefix):], ap):
                _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                     index=i, definition=d, event=_step_event(plan, card, d))


# -- sagas & attached-object triggers (wave 3S) --
def _aura_card_bound(plan: Plan, d: dict[str, Any], gone: str | None) -> dict[str, Any]:
    """400.7f: "return this card" in a trigger on the enchanted permanent leaving names the new object
    the Aura became in its owner's graveyard — bound now, as it triggers (the Aura is put there with
    the enchanted permanent, or by the state-based action just before, 704.5m), never found later."""
    if scripts.AURA_CARD not in str(d.get("effects")):
        return d
    new = None
    if gone is not None:  # (an Aura still on the battlefield: there is no such object)
        new = next((e.new_object_id for e in plan.rules.events if e.kind == "zone_change" and e.object_id == gone
                    and _zone(e.from_zone) == "battlefield" and _zone(e.to_zone) == "graveyard"), None)
    who = f"{scripts.AURA_CARD}:{new or '-'}"
    return {**d, "effects": [{**e, "who": who} if e.get("who") == scripts.AURA_CARD else e for e in d["effects"]]}


def _step_event(plan: Plan, card: CardInstance, d: dict[str, Any]) -> TriggerEvent | None:
    """"At the beginning of enchanted player's upkeep / the upkeep of enchanted creature's
    controller, that player … that creature": the player whose step it is, and the enchanted
    creature as the step began (it, while it's still that object: 400.7)."""
    if not scripts.step_names_player(d):
        return None
    objects = []
    if str(d["trigger"]).endswith(":host_controller"):
        host = plan.state.cards.get(card.attached_to or "")
        if host is not None:
            objects = [ObjectRef(card=host.id, object_id=plan.oid(host), zone=host.zone)]
    return TriggerEvent(kind="step", players=[plan.active], objects=objects, count=1)
# -- end sagas & attached-object triggers (wave 3S) --


def _whose_step(plan: Plan, card: CardInstance, whose: str, ap: str) -> bool:
    if whose == "you":
        return card.controller == ap
    if whose == "each":
        return True
    if whose == "opponent":
        return card.controller != ap
    if whose == "enchanted_player":
        return card.attached_player == ap
    if whose == "chosen_player":  # -- chosen player (wave 4J) -- the player this permanent chose as it entered
        from app.rules import chosen

        return chosen.player_of(plan, card.id) == ap
    if whose == "host_controller":  # "the upkeep of enchanted creature's controller"
        host = plan.state.cards.get(card.attached_to or "")
        return host is not None and host.controller == ap
    return False


ECHO = re.compile(r"^echo (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def echo_cost(ch: Any) -> str | None:
    for ab in ch.abilities:
        if ab.kind == "keywords" and "echo" in ab.keywords:
            m = ECHO.fullmatch(ab.text.strip().rstrip("."))
            return m["cost"] if m else None
    return None


CUMULATIVE = re.compile(r"^cumulative upkeep (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def cumulative_cost(ch: Any) -> str | None:
    for ab in ch.abilities:
        if ab.kind == "keywords" and "cumulative upkeep" in ab.keywords:
            m = CUMULATIVE.fullmatch(ab.text.strip().rstrip("."))
            return m["cost"] if m else None
    return None


def _cumulative_upkeep(plan: Plan) -> None:
    """702.24a: "At the beginning of your upkeep, if this permanent is on the battlefield, put an
    age counter on it. Then you may pay [cost] for each age counter on it. If you don't, sacrifice it." """
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or card.controller != plan.active or plan.manual(card):
            continue
        ch = plan.ch(card)
        cost = cumulative_cost(ch)
        if cost is None:
            continue
        _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
             index=5100, definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                                     "effects": [{"do": "add_counters", "who": "self", "kind": "age", "n": 1},
                                                 {"do": "pay_or_sacrifice", "cost": cost, "per": "age"}]})


def _rebound(plan: Plan) -> None:
    """702.88a: "At the beginning of your next upkeep, you may cast this card from exile without
    paying its mana cost." """
    for cid in list(plan.rules.rebounding):
        card = plan.state.cards.get(cid)
        if card is None or card.zone != f"{plan.active}:exile" or card.owner != plan.active:
            continue
        plan.rules.rebounding = [c for c in plan.rules.rebounding if c != cid]
        _add(plan, controller=card.owner, source_card=cid, source_object=plan.oid(card), name=card.name, index=5200,
             definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                         "effects": [{"do": "free_cast_offer", "card": cid}]})


def _suspend(plan: Plan) -> None:
    """702.62b: "At the beginning of your upkeep, if this card is suspended, remove a time counter
    from it." (A triggered ability of the exiled card itself.)"""
    for cid in list(plan.rules.suspended):
        card = plan.state.cards.get(cid)
        if card is None or card.zone != f"{plan.active}:exile" or card.owner != plan.active:
            continue
        _add(plan, controller=card.owner, source_card=card.id, source_object=plan.oid(card), name=card.name,
             index=5000, definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                                     "effects": [{"do": "suspend_tick", "card": card.id}]})


def _echo(plan: Plan) -> None:
    """702.30a echo: "At the beginning of your upkeep, if this permanent came under your control
    since the beginning of your last upkeep, sacrifice it unless you pay [cost]." Each permanent
    gets this once per controller (a new object, or a new controller, is due again)."""
    r = plan.rules
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or card.controller != plan.active or plan.manual(card):
            continue
        ch = plan.ch(card)
        cost = echo_cost(ch)
        key = f"{plan.oid(card)}:{card.controller}"
        if cost is None or key in r.echo_done:
            continue
        r.echo_done.append(key)
        _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
             index=3000, definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                                     "effects": [{"do": "pay_or_sacrifice", "cost": cost}]})


def _keyword_n(ch: Any, word: str) -> list[int]:
    """The N of each instance of a numbered keyword ("Bushido 2", "Renown 1") on the card."""
    out = []
    for ab in ch.abilities:
        if ab.kind == "keywords" and word in ab.keywords:
            for piece in re.split(r"[,;]\s*", ab.text):
                m = re.fullmatch(rf"{word} (\d+)", piece.strip().rstrip(".").lower())
                if m:
                    out.append(int(m.group(1)))
    return out


WARD = re.compile(r"^ward (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def ward_cost(ch: Any) -> str | None:
    costs = ward_costs(ch)
    return costs[0] if costs else None


def ward_costs(ch: Any) -> list[str]:
    """-- attached events (wave 4L) -- the cost of each ward ability the object has, printed or granted ("Equipped
    creature has ward {1}"): each instance is its own triggered ability (702.21a) and triggers on its own."""
    out = []
    for ab in ch.abilities:
        if ab.kind == "keywords" and "ward" in ab.keywords:
            m = WARD.fullmatch(ab.text.strip().rstrip("."))
            if m:
                out.append(m["cost"])
    return out


def targeted(plan: Plan, stack_id: str | None, controller: str, targets: list[Any]) -> None:
    """702.21a ward: "Whenever this permanent becomes the target of a spell or ability an opponent
    controls, counter it unless that player pays [cost]." """
    if not stack_id:
        return
    # An object chosen for several words "target" (115.3) becomes the target of that spell or
    # ability once: one event, one trigger.
    targets = list({(t.id if hasattr(t, "id") else t): t for t in targets}.values())
    from app.rules import history  # -- this-turn history (wave 4D) -- 700.13: committing a crime

    history.note_crime(plan, stack_id, controller, targets)
    for t in targets:  # "When ~ becomes the target of a spell or ability, …" (any controller)
        card = plan.state.cards.get(t.id if hasattr(t, "id") else t)
        if card is None or not card.zone.endswith(":battlefield") or plan.manual(card):
            continue
        ch = plan.ch(card)
        spell = plan.state.cards.get(stack_id)
        for i, d in abilities(plan, ch, "targeted_self"):
            event = TriggerEvent(kind="targeted", count=1,
                                 objects=[ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone)],
                                 source=ObjectRef(card=stack_id, object_id=plan.oid(spell), zone=spell.zone)
                                 if spell is not None else None)
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=i, definition=d, event=event)
    _targeted_generic(plan, stack_id, controller, targets)
    for t in targets:
        card = plan.state.cards.get(t.id if hasattr(t, "id") else t)
        if card is None or not card.zone.endswith(":battlefield") or card.controller == controller or plan.manual(card):
            continue
        ch = plan.ch(card)
        for k, cost in enumerate(ward_costs(ch)):  # -- attached events (wave 4L) -- each instance (702.21a)
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=9000 + k, definition={"kind": "triggered", "trigger": "ward", "optional": False, "target": None,
                                         "effects": [{"do": "counter_unless", "cost": cost, "object": stack_id}]})


def _targeted_generic(plan: Plan, stack_id: str, controller: str, targets: list[Any]) -> None:
    """"Whenever ~ / a creature you control becomes the target of a spell or ability [an opponent
    controls] [for the first time each turn]" (115.1, 603.2e): one event per object targeted, as
    the spell or ability is put on the stack (601.2c, 603.3d). The event's source is that spell
    or ability ("counter that spell or ability")."""
    spell = plan.state.cards.get(stack_id)
    is_spell = spell is not None and spell.ability is None
    source = ObjectRef(card=stack_id, object_id=plan.oid(spell), zone=spell.zone) if spell is not None else None
    turn = plan.state.turn.number
    facts: list[Fact] = []
    for t in targets:
        card = plan.state.cards.get(t.id if hasattr(t, "id") else t)
        if card is None or not card.zone.endswith(":battlefield") or plan.manual(card):
            continue
        oid = plan.oid(card)
        # "for the first time each turn": the first time this turn that player's spells and
        # abilities targeted this object (kept per turn, like other once-each-turn marks)
        key = f"targeted:{controller}:{oid}"
        first = plan.rules.once_per_turn.get(key) != turn
        plan.rules.once_per_turn[key] = turn
        facts.append(("targeted", card, plan.ch(card), card.controller,
                      {"oid": oid, "by": controller, "spell": is_spell, "first": first, "source_ref": source}))
    if facts:
        _fire_generic(plan, facts, -1, {})


def flanking(plan: Plan, pairs: list[tuple[CardInstance, CardInstance]]) -> None:
    """702.25a: "Whenever this creature becomes blocked by a creature without flanking, the blocking
    creature gets -1/-1 until end of turn." (Per instance, per blocker.)"""
    for blocker, attacker in pairs:
        if plan.manual(attacker):
            continue
        ach = plan.ch(attacker)
        n = sum(1 for ab in ach.abilities if ab.kind == "keywords" for kw in ab.keywords if kw == "flanking")
        if not n or "flanking" in plan.ch(blocker).keywords:
            continue
        for k in range(n):
            _add(plan, controller=attacker.controller, source_card=attacker.id, source_object=plan.oid(attacker),
                 name=ach.name, index=4200 + k,
                 definition={"kind": "triggered", "trigger": "flanking", "optional": False, "target": None,
                             "effects": [{"do": "pump", "who": f"object:{plan.oid(blocker)}", "p": -1, "t": -1}]})


def blocked(plan: Plan, blockers: list[CardInstance], attackers: list[CardInstance]) -> None:
    """702.45 bushido N: "Whenever this creature blocks or becomes blocked, it gets +N/+N until
    end of turn." (Once per creature per combat, however many creatures it blocks or is blocked by.)"""
    # (each blocker and the attacker it blocks: CardInstance.blocking, 509.1)
    pairs = [(b, plan.state.cards[b.blocking]) for b in {c.id: c for c in blockers}.values()
             if b.blocking in plan.state.cards]
    generic_combat(plan, "block", list({c.id: c for c in blockers}.values()), pairs)
    generic_combat(plan, "blocked", list({c.id: c for c in attackers}.values()), [(a, b) for b, a in pairs])
    # -- counters & designations (wave 3E): the Ring's third ability (701.54c) --
    from app.rules import designations

    designations.ring_blocked(plan, [(a, b) for b, a in pairs])
    for card in {c.id: c for c in [*blockers, *attackers]}.values():
        if plan.manual(card):
            continue
        ch = plan.ch(card)
        for k, n in enumerate(_keyword_n(ch, "bushido")):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=4000 + k, definition={"kind": "triggered", "trigger": "bushido", "optional": False, "target": None,
                                             "effects": [{"do": "pump", "who": "self", "p": n, "t": n}]})


def dealt_combat_damage_to_player(plan: Plan, sources: list[CardInstance]) -> None:
    """702.112 renown N: "When this creature deals combat damage to a player, if it isn't renowned,
    put N +1/+1 counters on it and it becomes renowned." (Checked again on resolution.)"""
    # -- counters & designations (wave 3E): the Ring's fourth ability (701.54c) --
    from app.rules import designations

    designations.ring_damage(plan, sources)
    for card in sources:
        if plan.manual(card):
            continue
        ch = plan.ch(card)
        for i, d in abilities(plan, ch, "combat_damage_player_self"):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=i, definition=d)
        if plan.oid(card) in plan.rules.renowned:
            continue
        for k, n in enumerate(_keyword_n(ch, "renown")):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=4100 + k, definition={"kind": "triggered", "trigger": "renown", "optional": False, "target": None,
                                             "effects": [{"do": "renown", "n": n}]})


def attacked(plan: Plan, attackers: list[CardInstance]) -> None:
    generic_combat(plan, "attack", attackers)
    # -- counters & designations (wave 3E): the Ring's second ability (701.54c) --
    from app.rules import designations

    designations.ring_attacks(plan, attackers)
    if len(attackers) == 1:
        _exalted(plan, attackers[0])
    for card in attackers:
        if plan.manual(card):
            continue
        ch = plan.ch(card)
        for i, d in abilities(plan, ch, "attacks_self"):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i,
                 definition=d)


def _exalted(plan: Plan, alone: CardInstance) -> None:
    """702.83: "Whenever a creature you control attacks alone, that creature gets +1/+1 until end of
    turn" — once for each instance of exalted among permanents its controller controls."""
    target = f"object:{plan.oid(alone)}"
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or card.controller != alone.controller or plan.manual(card):
            continue
        ch = plan.ch(card)
        n = sum(1 for ab in ch.abilities if ab.kind == "keywords" for kw in ab.keywords if kw == "exalted")
        if "exalted" in ch.granted and not n:
            n = 1
        for i in range(n if "exalted" in ch.keywords else 0):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=2000 + i, definition={"kind": "triggered", "trigger": "exalted", "optional": False, "target": None,
                                             "effects": [{"do": "pump", "who": target, "p": 1, "t": 1}]})


def apnap(plan: Plan) -> list[str]:
    order, p = [], plan.active if plan.active in plan.live() else plan.after(plan.active)
    for _ in plan.live():
        order.append(p)
        p = plan.after(p)
    return order


def flush(plan: Plan) -> bool:
    """Put waiting triggers on the stack (603.3). True if the stack changed or a decision opened."""
    collect(plan)
    r = plan.rules
    r.pending_triggers = [t for t in r.pending_triggers if t.controller in plan.live()]
    if not r.pending_triggers:
        return False
    if not plan.options.auto_trigger_stacking and not getattr(plan, "triggers_confirmed", False):
        names = ", ".join(t.name for t in r.pending_triggers)
        decide(plan, player=plan.turn_player, kind="confirm", prompt=f"Triggered: {names}",
               options=[DecisionOption(id="yes", label="Put on the stack"), DecisionOption(id="no", label="By hand")],
               resume={"step": "trigger_confirm"})
        return True
    for player in apnap(plan):
        mine = [t for t in r.pending_triggers if t.controller == player]
        if not mine:
            continue
        if len(mine) > 1 and not all(t.ordered for t in mine) and not _identical(plan, player, mine):
            decide(plan, player=player, kind="order",
                   prompt="Order your triggered abilities (the first you pick goes on the stack first and resolves last)",
                   options=[DecisionOption(id=t.id, label=t.name) for t in mine],
                   min_choices=len(mine), max_choices=len(mine), resume={"step": "order_triggers"})
            return True
        for t in mine:
            if not put(plan, t):
                return True  # waiting for a target choice
    r.passed = []
    r.priority = plan.active if plan.active in plan.live() else plan.after(plan.active)
    return True


def _identical(plan: Plan, player: str, mine: list[PendingTrigger]) -> bool:
    return plan.rules.prefs_for(player).auto_order_identical_triggers and len({t.key for t in mine}) == 1 \
        and not any(t.ability.get("target") or t.ability.get("targets") for t in mine)


def put(plan: Plan, t: PendingTrigger, target: str | None = None, picks: dict[str, Any] | None = None) -> bool:
    """Put one trigger on the stack. False if it waits for its controller's target choice.
    ``picks``: the choices so far for an ability with target groups (603.3d → 601.2c-d)."""
    if t.ability.get("modes"):  # -- modal triggered abilities (wave 1A): the modes first (603.3c, 700.2b) --
        from app.rules import modal_abilities

        return modal_abilities.put_trigger(plan, t, picks)
    r = plan.rules
    spec = t.ability.get("target")
    targets = []
    extra: dict[str, Any] = {}
    # "Whenever a creature you control attacks, … target creature defending player controls": the
    # defending player is the one *that* creature attacks (508.5, 508.5a), not the source's
    attacker = selectors.attacker_of(t.event)
    if t.ability.get("targets"):
        from app.game.errors import ActionError
        from app.rules.casting import ask_targets
        from app.rules.scripts import target_groups

        specs = target_groups(t.ability)
        picks = picks or {"targets": [], "counts": [], "division": []}
        try:
            found = choose_groups(plan, specs, t.controller, source_of(plan, t.source_card), t.source_card,
                                  picks["targets"], picks["counts"], picks["division"], None, t.name or "It",
                                  attacker=attacker)
        except ActionError:  # 603.3d: no legal choice for a required target: removed from the stack
            r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
            plan.note(f"{t.name}'s ability doesn't have enough legal targets and is removed")
            return True
        if found.ask is not None:
            ask_targets(plan, t.controller, found, specs, f"{t.name}'s ability",
                        {"step": "trigger_group", "trigger": t.id, **picks, "counts": found.counts})
            return False
        groups = [[ref(plan, x) for x in g] for g in found.groups]
        targets = [x for g in groups for x in g]
        extra = {"groups": groups, "group_specs": specs, "division": found.division}
        spec = None
    elif spec:
        legal = legal_targets(plan, spec["what"], t.controller, source_of(plan, t.source_card), t.source_card, attacker)
        if target is None:
            if not legal:
                r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
                plan.note(f"{t.name}'s ability has no legal target and is removed")
                return True
            decide(plan, player=t.controller, kind="choose_one", prompt=f"{t.name}: choose a target",
                   options=[DecisionOption(id=x, label=label(plan, x), card_id=x if x in plan.state.cards else None) for x in legal],
                   resume={"step": "trigger_target", "trigger": t.id})
            return False
        targets = [ref(plan, target)]
    r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
    source = t.source_card if t.source_card in plan.state.cards else None
    text = t.name + "’s ability" if t.name else "Triggered ability"
    created = plan.do({"type": "create_ability", "text": text, "source_id": source, "kind": "triggered"}, actor=t.controller)
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    if ability_id is None:
        return True
    r.stack[ability_id] = StackEntry(kind="trigger", controller=t.controller, source_card=t.source_card,
                                     source_object=t.source_object, name=t.name, effects=list(t.ability["effects"]),
                                     targets=targets, target_spec=spec, optional=bool(t.ability.get("optional")),
                                     event=t.event, x=cast_x(plan, t), **extra)  # (x: wave 4J, 107.3m)
    if targets:
        plan.do({"type": "create_arrow", "source": ability_id, "targets": [x.id for x in targets], "kind": "target"},
                actor=t.controller)
        targeted(plan, ability_id, t.controller, targets)
    return True


# -- cast X (wave 4J) --
def cast_x(plan: Plan, t: PendingTrigger) -> int | None:
    """107.3m: an object's enters-the-battlefield triggered ability that refers to X uses the X of the spell that
    became that object as it resolved (its payment record, which follows it onto the battlefield); for any other
    triggered ability — or an object that wasn't cast with X — X is undefined here (0, 107.3i)."""
    if t.event is None or t.event.kind != "enter" or not any(o.object_id == t.source_object for o in t.event.objects):
        return None
    record = plan.rules.payments.get(t.source_object)
    return record.x if record is not None else None
# -- end cast X (wave 4J) --


def resume_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = plan.rules
    mine = {t.id: t for t in r.pending_triggers if t.controller == d.player}
    ordered = [mine[c] for c in chosen if c in mine]
    for t in ordered:
        t.ordered = True
    rest = [t for t in r.pending_triggers if t.controller != d.player]
    r.pending_triggers = rest + ordered
    for t in ordered:
        if not put(plan, t):
            return
    flush(plan)


def resume_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    t = next((p for p in plan.rules.pending_triggers if p.id == d.resume["trigger"]), None)
    if t is not None:
        put(plan, t, target=chosen[0])
    flush(plan)


def resume_group(plan: Plan, d: Any, chosen: list[str]) -> None:
    """A target group of a trigger was chosen (603.3d): the next choice, or onto the stack."""
    res = d.resume
    t = next((p for p in plan.rules.pending_triggers if p.id == res["trigger"]), None)
    if t is not None:
        picks = {"targets": [*res["targets"], *chosen], "counts": [*res["counts"], len(chosen)], "division": res["division"]}
        if not put(plan, t, picks=picks):
            return
    flush(plan)


def resume_divide(plan: Plan, d: Any, chosen: list[str]) -> None:
    """A trigger's division was chosen (601.2d)."""
    res = d.resume
    t = next((p for p in plan.rules.pending_triggers if p.id == res["trigger"]), None)
    if t is not None:
        picks = {"targets": res["targets"], "counts": res["counts"], "division": [*res["division"], *(int(c) for c in chosen)]}
        if not put(plan, t, picks=picks):
            return
    flush(plan)


def resume_confirm(plan: Plan, d: Any, chosen: list[str]) -> None:
    if chosen[0] == "yes":
        plan.triggers_confirmed = True  # type: ignore[attr-defined]
        flush(plan)
    else:
        plan.note(f"{plan.name(d.player)} will handle the triggered abilities by hand")
        plan.rules.pending_triggers = []
