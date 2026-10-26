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

import json
import re
import secrets
from dataclasses import replace
from typing import Any

from app.game.rules_state import (
    DecisionOption,
    Event,
    ObjectRef,
    ObjectSnapshot,
    PaymentRecord,
    PendingTrigger,
    StackEntry,
    TriggerEvent,
    TurnCount,
    emit,
    track,
)
from app.game.state import COMBAT_PHASES, AttackTarget, CardInstance, MergedPart, StackInfo, TokenDef
from app.rules import characteristics as chars
from app.rules import delayed, designations, layers, scripts, selectors
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan, decide
from app.rules.targets import choose_groups, label, legal_targets, ref, source_of

_FIRST_KINDS = ("gain_life", "lose_life", "create_token")  # (wave 11C) events counted "for the first time each turn"


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
    from app.game.state import StickerPlacement101

    card = CardInstance(id=snap.card, card_id=snap.printing, name=snap.name, owner=snap.owner, controller=snap.controller,
                        zone=snap.zone, face=snap.face, face_down=snap.face_down, face_down_kind=snap.face_down_kind,
                        face_down_as=snap.face_down_as, is_token=snap.is_token,
                        stickers101=[StickerPlacement101.model_validate(p) for p in snap.stickers101],
                        token=TokenDef(name=snap.name, text=snap.text, power=snap.token_power, toughness=snap.token_toughness,
                                      colors=snap.token_colors, type_line=snap.token_type_line or "Token Creature", mana_cost=snap.token_mana_cost)
                        if snap.is_token and not snap.printing else None,
                        merged=[MergedPart(**p) for p in snap.merged], melded=snap.melded)  # (wave 18D: a merged permanent's cards)
    ch = chars.of(card, plan.info)
    # -- copy system (wave 2F): its copiable values as they were (a dying Clone's abilities) --
    from app.rules import copying

    ch = copying.lki(plan, snap, ch)
    from app.rules import stack_faces

    ch = stack_faces.apply(plan.state, card, ch, plan.info, snapshot=snap)
    # -- Rooms (review 18G) -- 709.5, 716.2b: the doors it had unlocked (and its class level) as it last existed, not every half
    recipe = getattr(snap, "copy_recipe", None)
    ch = copying.with_level(plan.state, card, ch, plan.info, snap.object_id,
                            recipe.printing if recipe is not None and recipe.printing and not snap.face_down else None)
    if snap.power is not None and snap.toughness is not None:
        ch = replace(ch, pt=(snap.power, snap.toughness))  # as it last existed (608.2h)
    if snap.base_power is not None and snap.base_toughness is not None:  # -- base power (wave 30J) -- 208.4b
        ch = replace(ch, base_pt=(snap.base_power, snap.base_toughness))
    # -- quoted grants (wave 2D) -- the abilities and keywords it had (603.10a): granted ones too
    from app.rules import granted

    ch = granted.as_last_existed(ch, snap)
    ch = chars.provenance(card, ch)
    ch = replace(ch, on_battlefield=snap.zone.endswith(":battlefield"),
                 object_counters=frozenset(k for k, n in snap.counters.items() if n > 0),
                 object_ring_bearer=snap.ring_bearer)
    return replace(ch, imposed=ch.imposed | {f"goaded:{p}" for p in snap.goaded}) if snap.goaded else ch  # -- goad (wave 48D) -- 701.15b, 608.2h


def _add(plan: Plan, *, controller: str, source_card: str, source_object: str, name: str, index: int,
         definition: dict[str, Any], manual: bool = False, event: TriggerEvent | None = None,
         cause: TriggerEvent | None = None) -> PendingTrigger | None:
    if manual:
        return None
    from app.rules import (
        trigger_multipliers,  # -- static_other sweep (wave 16B) -- "Creatures entering don't cause abilities to trigger"
    )

    src = plan.state.cards.get(source_card)  # (review 37: Elesh Norn stops only the abilities of permanents)
    permanent = index not in (trigger_multipliers.DELAYED, trigger_multipliers.REFLEXIVE, trigger_multipliers.MADNESS) and src is not None \
        and src.zone.endswith(":battlefield") and plan.oid(src) == source_object
    if trigger_multipliers.suppressed(plan, event if event is not None else cause, controller, permanent):
        return None
    from app.rules import random_characteristic_choices

    definition = random_characteristic_choices.freeze_trigger(plan, definition, source_object)
    from app.rules import chosen_color_pairs45

    definition = chosen_color_pairs45.freeze_trigger(plan, definition, source_object)
    if definition.get("if_kicked"):  # 603.4: "When ~ enters, if it was kicked, …" (702.33e)
        from app.rules import (
            values,  # (-- keywords (wave 50H) -- 702.33f: "kicked twice", "kicked with its {R} kicker")
        )

        record = plan.rules.payments.get(source_object)
        if record is None or not record.kicked or not values.kicked_holds(plan, {"source_object": source_object, "source_card": source_card}, definition["if_kicked"]):
            return None  # (it wasn't: the ability doesn't trigger; kicked status never changes later)
    if definition.get("if_paid"):  # -- any number as an additional cost (wave 48B) -- 603.4: "When you cast this spell, if you sacrificed one or more creatures this way, …": the cost's record
        record = plan.rules.payments.get(source_object)
        if record is None or not (record.sacrificed_objects if definition["if_paid"] == "sacrificed" else record.tapped_objects):
            return None
    if definition.get("if") is not None:  # 603.4: an intervening "if" must hold as it triggers
        from app.rules import conditions

        # (the source and the event it triggered on: "if ~ is an enchantment", "if it's a Dragon", 603.4)
        check: dict[str, Any] = {"controller": controller, "source_card": source_card, "source_object": source_object,
                 "event": event.model_dump(mode="json") if event is not None else None}
        # Delayed abilities restore captured object references before resolving.
        # Their intervening conditions need the same references when triggering.
        first: dict[str, Any] = next(iter(definition.get('effects') or []), {})
        if first.get('do') == 'bind_refs':
            check['refs'] = first['refs']
        record = plan.rules.payments.get(source_object)  # -- keyword meanings (wave 11B) -- 107.3m: "if X is 5 or more" (ravenous)
        if record is not None and event is not None and event.kind == "enter" \
                and any(o.object_id == source_object for o in event.objects):
            check["x"] = record.x
        if not conditions.holds(plan, check, definition["if"]):
            return None
    if definition.get("limit") in ("once_each_turn", "once_game"):  # "This ability triggers only once (each turn)." (app/rules/restrictions.py)
        from app.rules import restrictions

        if restrictions.uses(plan.rules, source_object, index, None if definition["limit"] == "once_game" else plan.state.turn.number):
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
        if definition.get("optional") and len(definition["effects"]) == 1 and definition["effects"][0].get("do") == "search":
            mark["action"] = "search"
        definition = {**definition, "effects": [{"do": "action_gate", **mark}, *definition["effects"],
                                                {"do": "record_action", **mark}]}
    # -- this-turn history (wave 4D) -- "if this is the second time this ability has resolved this turn"
    from app.rules import history

    if "effects" in definition:
        definition = {**definition, "effects": history.counting_resolutions(definition["effects"], f"{source_object}:{index}")}
    from app.rules import linked_attachment_return

    definition = linked_attachment_return.capture(plan, definition, source_object)
    from app.rules import attached_kindred_look

    definition = attached_kindred_look.capture(plan, definition, source_object)
    pending = PendingTrigger(id=secrets.token_hex(4), controller=controller, source_card=source_card,
                             source_object=source_object, name=name, ability=definition, key=f"{name}:{index}",
                             event=event)
    plan.rules.pending_triggers.append(pending)
    # -- trigger multipliers (wave 5D) -- 603.2d: "that ability triggers an additional time" (``cause``: the event it
    # triggered on, for an ability that doesn't carry one)
    from app.rules import trigger_multipliers

    trigger_multipliers.multiply(plan, pending, index, cause if cause is not None else event)
    from app.rules import wave110c_misc  # -- Strict Proctor (wave 110C) --

    wave110c_misc.proctor_triggers(plan, pending, cause if cause is not None else event)
    # -- end trigger multipliers (wave 5D) --
    return pending


def _entered(plan: Plan, card: CardInstance, oid: str, batch: int = 0) -> TriggerEvent:
    """"Whenever [another] creature enters": the event is that object entering."""
    return TriggerEvent(kind="enter", objects=[ObjectRef(card=card.id, object_id=oid, zone=card.zone)], count=1,
                        batch=batch)  # (batch: wave 5D, the multipliers there then, 603.10)


HIDDEN = ("hand", "library")


def _new_ref(card_id: str, new_oid: str | None, to_zone: str | None) -> list[ObjectRef]:
    """The object a card became where it went (400.7e: a zone-change trigger can find it there, if
    that zone is public — 603.6: never in a hidden zone such as a library or a hand)."""
    if not new_oid or not to_zone or _zone(to_zone) in HIDDEN:
        return []
    return [ObjectRef(card=card_id, object_id=new_oid, zone=to_zone)]


def pile_refs(plan: Plan, e: Event | None) -> list[ObjectRef]:
    """-- review (wave 18D) -- 730.3c / 712.21c: the other new objects a merged permanent that left in ``e`` became (public zones)."""
    from app.rules import merged

    return [r for x in (merged.parts_left(plan, e) if e is not None else []) for r in _new_ref(x.card or "", x.new_object_id, x.to_zone)]


def _was_sacrificed(plan: Plan, batch: int, object_id: str | None) -> bool:
    """Bind the action to this incarnation and this simultaneous event batch."""
    return object_id is not None and any(e.kind == "sacrificed" and e.batch == batch
                                         and e.object_id == object_id for e in plan.rules.events)


def _left(plan: Plan, kind: str, snap: ObjectSnapshot, e: Event) -> TriggerEvent:
    """A leaves-the-battlefield / dies event of one object: as it last existed on the battlefield
    (603.10a) and the new object it became where it went (400.7e, 603.6c; a merged permanent: all of them, 730.3c)."""
    return TriggerEvent(kind=kind, batch=e.batch, count=1,
                        sacrificed=_was_sacrificed(plan, e.batch, snap.object_id),
                        objects=[ObjectRef(card=snap.card, object_id=snap.object_id, zone=snap.zone, snapshot=snap)],
                        new_objects=_new_ref(snap.card, e.new_object_id, e.to_zone) + pile_refs(plan, e))


def sacrificing(plan: Plan, card_ids: list[str]) -> None:
    """701.21a: these permanents are about to be sacrificed (call just before moving them, so the
    event joins the move's batch): "Whenever you sacrifice …" (603.10a: looks back in time)."""
    for cid in card_ids:
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":battlefield"):
            emit(plan.state, "sacrificed", object_id=plan.oid(card), card=cid, player=card.controller)


def exploiting(plan: Plan, card_ids: list[str], exploiter: str, player: str) -> None:
    """-- keyword triggers (wave 23D) -- 702.110b: the creature with exploit ``exploiter`` "exploits" each of these creatures, sacrificed
    as its exploit ability resolves (call just before moving them, as ``sacrificing``; the exploiter may be one of them)."""
    src = plan.state.cards.get(exploiter)
    if src is None:
        return
    for cid in card_ids:
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":battlefield"):
            emit(plan.state, "exploited", object_id=plan.oid(card), card=cid, player=player, source=plan.oid(src), by_card=exploiter)
            plan.rules.exploited110j.append((plan.oid(src), plan.oid(card)))


def _discarded_instead(plan: Plan, e: Event) -> bool:
    """-- review (wave 23D) -- 701.9a, 702.35a: a card discarded that a replacement put somewhere other than the graveyard (madness,
    Rest in Peace, "put it onto the battlefield instead") was discarded all the same (``history.note_discards`` logged it)."""
    log = plan.rules.turn_log
    return log.turn == plan.state.turn.number and any(f.kind == "discard" and f.object_id == e.object_id for f in log.facts)


def collect(plan: Plan) -> None:
    """Look at the events since the last look (603.2)."""
    from app.rules import combat, wave110d_misc

    combat.sync_attacking(plan)
    r = plan.rules
    delayed.expire(plan)  # "for as long as …" effects whose duration ended (611.2b; app/rules/delayed.py)
    layers.control_sync(plan)  # -- control (wave 3K) -- layer 2 (613.1b), and what its changes end (611.2b)
    # -- counters & designations (wave 3E): daybound / nightbound permanents (702.145c-g), before any trigger is looked at
    from app.rules import designations

    designations.day_night_sync(plan)
    from app.rules import pairing  # -- soulbond (wave 24B) -- 702.95e: a pair ends, any time

    pairing.sync(plan)
    if any(e.batch > r.batch for e in r.events):
        # An event recorded after the step's last table change (a spell becoming cast, 601.2i)
        # is its own batch: close it now, before anyone would receive priority (603.3), rather
        # than letting it join whatever table change comes next (the spell resolving)
        track(plan.state)
    new =[e for e in r.events if r.trigger_batch < e.batch <= r.batch]  # finished batches only
    if not new:
        return
    from app.rules import state_triggers  # -- state triggers (wave 6D) -- 603.8, after the table changed

    state_triggers.check(plan)
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
    from app.rules import speed  # -- speed (wave 24B) -- 702.179d: the inherent speed trigger

    speed.on_events(plan, new)
    for e in new:
        if e.kind == "spell_cast" and not e.manual:
            _cast_triggers(plan, e.card or "", e.player or "", e.batch)
            continue
        if e.kind == "counters" and e.counter == "time" and e.amount < 0 and not e.manual:
            suspended_card = plan.state.cards.get(e.card or "")
            from app.rules import suspend_grants

            if suspended_card is not None and suspend_grants.has_suspend(plan, suspended_card) \
                    and plan.oid(suspended_card) == e.object_id and e.counter_remaining == 0:
                suspend_last(plan, suspended_card)
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
            wave110d_misc.wall_entered(plan, card, e.new_object_id)  # -- (wave 110D) -- Wall of Stolen Identity's reflexive "When you do"
            _other_enters(plan, card, ch, e.new_object_id, e.batch)
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
                         name=ch.name, index=i, definition=d, event=_left(plan, "die" if kind == "dies_self" else "leave", snap, e))

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
    """The public original object from its recorded departure or fight snapshot.

    CR 603.10a includes battlefield and graveyard departure look-back events.
    """
    from app.game.state import StickerPlacement101

    ch = _lki_characteristics(plan, snap)
    # (-- counters (wave 41A) -- 603.10a, 608.2h: "an attacking creature you control dies" (Death Tyrant, Kardur): it was attacking (and whom) / blocking / tapped as it
    # last existed — a selector that asks reads these of the dead object too)
    kind, _, ident = (snap.attack_on or "").partition(":")
    attacking = AttackTarget(kind="card" if kind == "card" else "player", id=ident) if snap.attack_on else None
    card = CardInstance(id=snap.card, card_id=snap.printing, name=snap.name, owner=snap.owner, controller=snap.controller,
                        zone=snap.zone, face=snap.face, face_down=snap.face_down, face_down_kind=snap.face_down_kind,
                        face_down_as=snap.face_down_as, is_token=snap.is_token,
                        stickers101=[StickerPlacement101.model_validate(p) for p in snap.stickers101],
                        attached_to=snap.attached_to, attached_player=snap.attached_player, tapped=snap.tapped,
                        entry_characteristics=snap.entry_characteristics, attacking=attacking, attacking_without_target=snap.attacking_without_target, attack_defender_lost=snap.attack_defender_lost, blocking=snap.blocking_ids[0] if snap.blocking_ids else None,
                        blocking_more=snap.blocking_ids[1:], blocking_without_attacker=snap.blocking and not snap.blocking_ids,
                        counters=dict(snap.counters), commander_key=snap.commander_key)  # (wave 3S: "each page counter on this Aura", 608.2h)
    if snap.x is not None:  # -- stack interaction (wave 5B) -- a spell's X as it last existed on the stack (202.3e)
        card.stack_info = StackInfo(x=snap.x)
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
    from app.rules import outside_battlefield_self

    ch = (Characteristics(name='', face_down=True) if then.face_down and zone.endswith(':exile')
          else outside_battlefield_self.apply(chars.of(then, plan.info)))
    return then, ch


def _live(plan: Plan, obj: CardInstance) -> bool:
    return plan.state.cards.get(obj.id) is obj


def _facts(plan: Plan, e: Event, window: dict[str, Any]) -> list[Fact]:
    r = plan.rules
    if e.kind == "fought":
        return [("fight", card, ch, snap.controller, {"oid": snap.object_id, "snap": snap})
                for snap in e.fighters90 for card, ch in [_snapshot_card(plan, snap)]]
    if e.kind == "damage_prevented" and e.amount > 0:
        return [("damage_prevented", None, None, e.player, {"amount": e.amount, "recipient": e.player})]
    if e.kind == "library_shuffled":
        return [("shuffle", None, None, e.player, {})]
    if e.kind == "zone_change":
        facts = _zone_facts(plan, e)
        for fact in facts:
            if fact[0] == "enter":
                fact[4]["played"] = e.new_object_id in window.get("played_lands", set())
        return facts
    if e.kind == "mana_added" and e.counter == "tap":  # -- mana riders (wave 5A) -- tapped for mana (106.12a)
        got = _object_then(plan, e.card, e.object_id)
        # (wave 110I: ``amount`` carries the colors produced as a bit mask, W=1 U=2 B=4 R=8 G=16, for C.A.M.P.'s "shares a color with the mana that land produced")
        return [("tapped_for_mana", got[0], got[1], e.player, {"oid": e.object_id, "actor": e.player,
                                                                "amount": sum(1 << "WUBRG".index(c) for c in e.mana_colors110i)})] if got is not None else []
    if e.kind == "exerted":
        got = _object_then(plan, e.card, e.object_id)
        if got is None:
            return []
        types = getattr(e, "types", None)
        ch = replace(got[1], types=frozenset(types)) if types is not None else got[1]
        return [("exerted", got[0], ch, e.player, {"oid": e.object_id, "actor": e.player})]
    if e.kind in ("tapped", "untapped", "turned_face_up"):  # (turned_face_up: wave 18A, 702.37e)
        got = _object_then(plan, e.card, e.object_id)
        return [(e.kind, got[0], got[1], got[0].controller, {"oid": e.object_id, "tapper": e.actor, "declared": e.combat, "step_phase": e.step_phase, "active_player": e.active_player})] if got is not None else []
    if e.kind == "life_paid":  # -- life paid (wave 110D) -- 119.4: "Whenever you pay life"
        return [("pay_life", None, None, e.player, {"amount": e.amount})]
    if e.kind in ("life_gain", "life_loss"):
        return [("gain_life" if e.kind == "life_gain" else "lose_life", None, None, e.player, {"amount": e.amount, **({"life_operation": e.group} if e.kind == "life_loss" and e.group else {})})]
    if e.kind == "spell_cast":
        spell = plan.state.cards.get(e.card or "")
        if spell is None:
            return []
        entry = r.stack.get(spell.id)
        # 601.2i: what the condition can ask about the spell as it became cast — the Nth spell its
        # caster cast this turn, the zone it was cast from, its targets (115.9b), whether it was kicked
        nth = e.amount or r.spells_this_turn(e.player or "", plan.state.turn.number)
        paid = r.payments.get(plan.oid(spell))  # (review 23D: a promised gift / awaken is read as "kicked" by the spell's own text only:
        # (-- cast keywords (wave 43D) -- a permanent spell has no stack entry: its payment record says how often it was kicked)
        kicks = entry.kicked if entry is not None else paid.kicked if paid is not None else 0
        kicked = bool(kicks and not (paid is not None and (paid.gift_to or paid.alternative == "awaken" or any(  # (30E: bargain)
            x.endswith(":bargain") for x in paid.additional))))
        info = {"oid": plan.oid(spell), "actor": e.player, "nth": nth, "from": window["cast_from"].get(spell.id),  # 702.33d, 702.174k)
                "opponent_turn": plan.active != e.player, "kicked": kicked,
                "teamwork": paid is not None and any(x.endswith(":teamwork") for x in paid.additional),  # -- (wave 110G) -- 702.194b
                "snow_spent": dict(paid.snow_spent) if paid is not None and paid.snow_spent is not None else None,
                "mana_tags": [list(tags) for tags in paid.mana_tags] if paid is not None and paid.mana_known else None,
                "mana_sources": list(paid.mana_sources) if paid is not None and paid.mana_known else [],
                "mana_spent": dict(paid.mana_spent) if paid is not None and paid.mana_known else None,
                "x": int(paid.x or 0) if paid is not None else int(entry.x or 0) if entry is not None else 0,
                "targets": [(t.id, t.object_id) for t in (entry.targets if entry is not None else
                    [r.aura_targets[spell.id]] if spell.id in r.aura_targets else [])]}
        # -- unless pays (wave 4C) -- "their first noncreature spell each turn"
        from app.rules import unless_pays

        info["kinds_before"] = unless_pays.mark_cast(plan, e.player or "", plan.ch(spell).types)
        out: list[Fact] = [("cast", spell, plan.ch(spell), e.player, info)]
        # -- trigger tail (wave 15B) -- 700.14: the mana spent to cast it adds to the caster's total this turn (a spell cast by
        # hand, or for free, adds none known); "expend N" is the Nth mana reached by this spell (one event per spell)
        record = r.payments.get(plan.oid(spell))
        if e.player and record is not None and record.mana_known and sum(record.mana_spent.values()) > 0:
            turn, spent = plan.state.turn.number, sum(record.mana_spent.values())
            have = r.mana_cast.get(e.player)
            before = have.count if have is not None and have.turn == turn else 0
            r.mana_cast[e.player] = TurnCount(turn=turn, count=before + spent)
            out.append(("expend", None, None, e.player, {"before": before, "after": before + spent, "actor": e.player}))
        return out
    if e.kind == "spell_copied":  # -- refused copy/mana (wave 3R3) -- 707.10: a copy put on the stack, not cast
        spell = plan.state.cards.get(e.card or "")
        if spell is None or spell.zone != "stack" or plan.oid(spell) != e.object_id:
            return []
        entry = r.stack.get(spell.id)
        return [("copy", spell, plan.ch(spell), e.player, {
            "oid": e.object_id, "actor": e.player,
            "targets": [(t.id, t.object_id) for t in (entry.targets if entry is not None else
                    [r.aura_targets[spell.id]] if spell.id in r.aura_targets else [])]})]
    if e.kind == "drew":
        return [("draw", None, None, e.player, {"amount": 1})]
    if e.kind == "case_solved":
        got = _object_then(plan, e.card, e.object_id)
        return [("case_solved", got[0] if got is not None else None, got[1] if got is not None else None,
                 e.player, {"oid": e.object_id, "actor": e.actor})]
    if e.kind == "land_played":
        if e.played_snapshot is not None:
            played_card, played_ch = _snapshot_card(plan, e.played_snapshot)
            return [("land_played", played_card, played_ch, e.player, {"oid": e.object_id, "actor": e.player, "snap": e.played_snapshot, "played_from": e.from_zone})]
        got = _object_then(plan, e.card, e.object_id)
        return [("land_played", got[0], got[1], e.player, {"oid": e.object_id, "actor": e.player, "played_from": e.from_zone})] if got is not None else []
    if e.kind == 'investigated':
        return [('investigate', None, None, e.player, {'actor': e.actor or e.player, 'amount': 1})]
    if e.kind == "plotted":  # -- (wave 110B) -- 702.170d: the card, in exile
        card = plan.state.cards.get(e.card or "")
        return [("plotted", card, plan.ch(card), e.player, {"oid": e.object_id, "actor": e.player, "amount": 1})] if card is not None else []
    if e.kind == "foretold":
        return [("foretell", None, None, e.player, {"actor": e.player, "amount": 1})]
    if e.kind == "cycled":  # 702.29: the card is in its owner's graveyard now (702.29c)
        card = plan.state.cards.get(e.card or "")
        if card is None:
            return []
        return [("cycle", card, plan.ch(card), e.player, {"oid": plan.oid(card), "actor": e.player, "amount": 1,
                                                          "x": e.amount})]  # (wave 34C: the X the cycling cost was announced with)
    if e.kind == "milled":  # -- triggers (wave 17D) -- 701.17a: the card, as it is in its owner's graveyard now
        card = plan.state.cards.get(e.card or "")
        if card is None or not card.zone.endswith(":graveyard"):
            return []
        return [("mill", card, plan.ch(card), e.player, {"oid": plan.oid(card), "actor": e.player, "amount": 1})]
    if e.kind == "sacrificed":  # 701.21a; 603.10a: looks back in time
        got = _object_then(plan, e.card, e.object_id)
        if got is None:
            return []
        live = _live(plan, got[0])
        # (wave 19B: where it went, for "put that card onto the battlefield": the zone change that followed in this batch, 400.7e)
        went = next((z for z in r.events if z.kind == "zone_change" and z.object_id == e.object_id and z.new_object_id), None)
        return [("sacrifice", got[0], got[1], e.player, {"oid": e.object_id, "actor": e.player, "amount": 1,
                                                          "snap": None if live else r.lki.get(e.object_id or ""),
                                                          **({"new_oid": went.new_object_id, "to": went.to_zone} if went else {})})]
    if e.kind in ("crew_tapped", "saddle_tapped"):  # -- crew & saddle (wave 23D) -- 702.122b / 702.171c: the creature tapped to pay the cost
        got = _object_then(plan, e.card, e.object_id)  # (``other``: the Vehicle / Mount whose ability it is, the creature "on the other side")
        if got is None:
            return []
        return [("crew" if e.kind == "crew_tapped" else "saddle", got[0], got[1], e.player,
                 {"oid": e.object_id, "actor": e.player, "other": e.by_card, "other_oid": e.source})]
    if e.kind in ("crewed", "saddled", "evolved", "trained"):  # 702.122e: its crew ability resolved; 702.171b: it became saddled
        got = _object_then(plan, e.card, e.object_id)
        return [(e.kind, got[0], got[1], e.player, {"oid": e.object_id, "actor": e.player, "crew_count80": e.crew_count80})] if got is not None else []
    if e.kind in ("attached", "unattached"):  # -- attachment events (wave 30S) -- 603.2e, 701.3d, 603.10c: the Aura / Equipment (as it last existed
        got = _object_then(plan, e.card, e.object_id)  # if it left), and the permanent on the other side (``other``) while it still is that object
        host = plan.state.cards.get(e.by_card or "")
        if got is None:
            return []
        live = host is not None and host.zone.endswith(":battlefield") and plan.oid(host) == e.source
        return [(e.kind, got[0], got[1], got[0].controller,
                 {"oid": e.object_id, "other": host.id if live and host is not None else None, "other_oid": e.source,
                  "snap": None if _live(plan, got[0]) else r.lki.get(e.object_id or "")})]
    if e.kind == "exploited":  # -- keyword triggers (wave 23D) -- 702.110b: the exploiter (it may have been sacrificed itself: its last known
        by = _object_then(plan, e.by_card, e.source)  # information) and the creature it exploited, as it was
        was = _object_then(plan, e.card, e.object_id)
        if by is None or was is None:
            return []
        return [("exploit", by[0], by[1], e.player, {"oid": e.source, "actor": e.player, "exploited": was, "exploited_oid": e.object_id, "amount": 1,
                                                    "snap": None if _live(plan, by[0]) else r.lki.get(e.source or "")})]
    if e.kind == "counters" and e.amount > 0:  # 122.6: counters put on a permanent
        got = _object_then(plan, e.card, e.object_id)
        if got is None:
            return []
        return [("counters_put", got[0], got[1], got[0].controller,
                 {"oid": e.object_id, "counter": e.counter, "amount": e.amount, "actor": e.actor, "group": e.group,  # (5H, 7C)
                  "total": got[0].counters.get(e.counter or "", 0),  # (wave 43B: "the twelfth hour counter", the count once they were put on)
                  "snap": None if _live(plan, got[0]) else r.lki.get(e.object_id or "")})]
    if e.kind == "counters" and e.amount < 0:  # -- keywords (wave 15E) -- 122.6: counters removed from a permanent ("the last time
        got = _object_then(plan, e.card, e.object_id)  # counter is removed", vanishing 702.63a); ``last``: none of that kind left
        exiled = plan.state.cards.get(e.card or "")  # (-- keywords (wave 50H) -- a time counter removed from a suspended card, in exile: it is that object still)
        if got is None and exiled is not None and exiled.zone.endswith(":exile") and (e.object_id is None or plan.oid(exiled) == e.object_id):
            got = (exiled, plan.ch(exiled))
        if got is None:
            return []
        return [("counters_removed", got[0], got[1], got[0].controller,
                 {"oid": e.object_id, "counter": e.counter, "amount": -e.amount, "actor": e.actor,
                  "last": got[0].counters.get(e.counter or "", 0) == 0,
                  "snap": None if _live(plan, got[0]) else r.lki.get(e.object_id or "")})]
    if e.kind == "damage":
        return _damage_facts(plan, e)
    if e.kind == "player_counters" and e.amount > 0 and e.player:  # -- counters & designations (wave 3E): 122.6 a player got counters --
        return [("player_counters", None, None, e.player, {"counter": e.counter, "amount": e.amount, "actor": e.actor, "group": e.group})]
    if e.kind == 'designation' and e.counter == 'echo_paid76':
        card = plan.state.cards.get(e.card or '')
        if card is None or plan.oid(card) != e.object_id:
            return []
        return [('echo_paid76', card, plan.ch(card), e.player, {'oid': e.object_id})]
    if e.kind == "designation":  # -- counters & designations (wave 3E) --
        from app.rules import designations

        return designations.facts(plan, e)
    return []


def _discard_facts(plan: Plan, e: Event) -> list[Fact]:
    if e.non_discard:
        return []
    # 701.9a: "To discard a card, move it from its owner's hand to that player's graveyard" — the rules engine moves a card that
    # way only by discarding it (an effect, a cost, cycling); -- review (wave 23D) -- or a replacement put the discard elsewhere
    if _zone(e.from_zone) != "hand" or not e.card or not (_zone(e.to_zone) == "graveyard" or _discarded_instead(plan, e)):
        return []
    got = _card_in(plan, e.card, e.to_zone if _zone(e.to_zone) != "battlefield" else e.from_zone)  # (a permanent now: the card it was)
    if got is None or (e.from_zone or "").split(":")[0] != got[0].owner:
        return []
    return [("discard", got[0], got[1], got[0].owner, {"oid": e.new_object_id, "actor": got[0].owner, "amount": 1,
                                                       "new_oid": e.new_object_id, "to": e.to_zone,
                                                       "by": e.actor})]  # (wave 23D: ``by``: the player whose effect moved it)


def _zone_facts(plan: Plan, e: Event) -> list[Fact]:
    r = plan.rules
    frm, to = _zone(e.from_zone), _zone(e.to_zone)
    out: list[Fact] = []
    if frm == "graveyard" and to != "graveyard" and e.card:
        # 603.10a: leaving the graveyard also happens when a card enters the
        # battlefield; collect it before the battlefield-entry branch returns.
        # A subsequent hidden shuffle may already have retired e.card. Use
        # the public graveyard departure snapshot, never its shuffled successor.
        snap = r.lki.get(e.object_id or "")
        got = _snapshot_card(plan, snap) if snap is not None else _card_in(plan, e.card, e.from_zone)
        if got is not None and snap is not None:
            from app.rules import outside_battlefield_self

            got = got[0], outside_battlefield_self.apply(got[1])
        if got is not None:
            out.append(("leave_graveyard", got[0], got[1], got[0].owner,
                        {"oid": e.object_id, "new_oid": e.new_object_id, "to": e.to_zone, "amount": 1}))
        if to == "hand" and not e.manual and (new := _card_in(plan, e.card, e.to_zone)) is not None and new[0].owner == (e.from_zone or "").split(":")[0]:
            out.append(("gy_to_hand110g", new[0], new[1], new[0].owner, {"oid": e.new_object_id, "actor": new[0].owner, "amount": 1}))  # -- (wave 110G) -- 400.7: the new object in its owner's hand
    if to == "battlefield" and frm != "battlefield":
        # (if it has left again since, as it was on the battlefield: it still entered, 603.6a)
        got = _object_then(plan, e.card, e.new_object_id)
        if got is not None:
            live = _live(plan, got[0])
            entered: dict[str, Any] = {"oid": e.new_object_id, "snap": None if live else r.lki.get(e.new_object_id or ""),
                                       "entered_from": e.from_zone}  # (wave 22E: "enters from your graveyard")
            out.append(("enter", got[0], got[1], got[0].controller, entered))
            if e.from_zone is None and got[0].is_token:  # 111.2: a token was created
                out.append(("create_token", got[0], got[1], got[0].controller,
                            {**entered, "actor": got[0].controller, "amount": 1}))
        return out + _discard_facts(plan, e)  # (review 23D: Obstinate Baloth, discarded onto the battlefield)
    if frm == "battlefield" and to != "battlefield":
        snap = r.lki.get(e.object_id or "")
        if snap is None:  # (-- review (wave 18D) -- a card of a merged permanent that left: put there, not a permanent leaving, 730.3)
            return _to_graveyard(plan, e, frm) if e.object_id is None else []
        card, ch = _snapshot_card(plan, snap)
        info: dict[str, Any] = {"oid": e.object_id, "snap": snap, "new_oid": e.new_object_id, "to": e.to_zone, "cause110g": e.cause110g,
                                "alone110g": __import__("app.rules.wave110g_cards", fromlist=["x"]).combat_alone(plan, e, snap)}
        out.append(("leave", card, ch, snap.controller, info))
        if to == "graveyard" or (e.to_zone is None and snap.is_token):  # 700.4
            out.append(("die", card, ch, snap.controller, info))
        out += _to_graveyard(plan, e, frm)  # -- into a graveyard (wave 6D) --
        out += _to_zone(plan, e, frm)  # -- counters (wave 21D) --
        return out
    out += _to_graveyard(plan, e, frm)  # -- into a graveyard (wave 6D) --
    out += _to_zone(plan, e, frm)  # -- counters (wave 21D) --
    out += _discard_facts(plan, e)
    return out


def _to_graveyard(plan: Plan, e: Event, frm: str) -> list[Fact]:
    """-- into a graveyard (wave 6D) -- a card put into a graveyard from any zone: the new object there (603.6c: "from
    anywhere" doesn't look back), with the zone it came from. (A token never is a card there: 111.7, 111.8.)"""
    if _zone(e.to_zone) != "graveyard" or frm == "graveyard" or not e.card or not e.new_object_id:
        return []
    got = _card_in(plan, e.card, e.to_zone)
    if got is None or got[0].is_token:  # (-- trigger other (wave 52B) -- 603.2c: a card that has since left the graveyard was put there all the same: "mill three cards, then return a creature card from your graveyard" (Dim Oubliette) with Polluted Cistern's "each card type among those cards")
        return []
    return [("to_graveyard", got[0], got[1], got[0].owner,
             {"oid": e.new_object_id, "from": frm, "amount": 1, "to": e.to_zone})]


def _to_zone(plan: Plan, e: Event, frm: str) -> list[Fact]:
    """-- counters (wave 21D) -- a card put into exile or into a library from another zone: the new object there (603.6c: "from
    anywhere" doesn't look back), with the zone and the owner of the zone it came from. (A token never is a card there: 111.7.)"""
    to = _zone(e.to_zone)
    if to not in ("exile", "library", "command") or frm == to or not e.card or not e.new_object_id:
        return []
    got = _card_in(plan, e.card, e.to_zone)
    if got is None or got[0].is_token or plan.oid(got[0]) != e.new_object_id:
        return []
    return [(f"to_{to}", got[0], got[1], got[0].owner,
             {"oid": e.new_object_id, "from": frm, "from_owner": (e.from_zone or "").split(":")[0] or None, "amount": 1, "to": e.to_zone})]


def _damage_facts(plan: Plan, e: Event) -> list[Fact]:
    from app.rules import sba

    r = plan.rules
    out: list[Fact] = []
    # (a creature dealt lethal damage was still dealt it: 510.3a / 603.10a)
    got = _object_then(plan, e.card, e.object_id) if e.player is None and (e.card or e.object_id) else None
    if got is not None:
        out.append(("dealt_damage", got[0], got[1], got[0].controller,
                    {"oid": e.object_id, "snap": None if _live(plan, got[0]) else r.lki.get(e.object_id or ""),
                     "amount": e.amount, "source_oid": e.source, "combat": e.combat, "attacking_player": e.attacking_player, "excess": e.excess, "pair110c": e.pair110c}))  # (wave 39B: 120.10)
    elif e.player is not None:  # "you're dealt combat damage", "an opponent is dealt noncombat damage"
        out.append(("dealt_damage", None, None, e.player,
                    {"recipient": e.player, "amount": e.amount, "source_oid": e.source, "combat": e.combat, "attacking_player": e.attacking_player}))
    source = next((c for c in plan.state.cards.values() if plan.oid(c) == e.source), None) if e.source else None
    src = (source, plan.ch(source)) if source is not None else (
        _snapshot_card(plan, r.lki[e.source]) if e.source and e.source in r.lki else None)
    if src is None:
        return out
    base = {"oid": e.source, "snap": None if source is not None else r.lki.get(e.source or ""), "amount": e.amount,
            "actor": e.actor, "attacking_player": e.attacking_player}
    # "~ deals damage [to a creature / a player]" (120.1): the recipient, as it is or last was
    recipient_is_creature = got is not None and got[1].is_creature
    # (120.1: a planeswalker is dealt damage too — "to a player or planeswalker", 510.2)
    recipient_is_walker = got is not None and "Planeswalker" in got[1].types
    recipient_is_battle = got is not None and "Battle" in got[1].types  # (120.3h)
    dealt_info = {**base, "combat": e.combat, "recipient": e.player, "recipient_creature": recipient_is_creature,
                  "recipient_planeswalker": recipient_is_walker, "recipient_battle": recipient_is_battle,
                  "recipient_ctl110b": got[0].controller if got is not None else None,  # (-- one-card wordings (wave 110B) -- a permanent's controller)
                  "recipient_toughness110b": sba.toughness(got[0], got[1]) if got is not None and recipient_is_creature else None,  # (wave 110B: Taii Wakeen)
                  "recipient_blocking110b": got is not None and bool(got[0].blocking),  # (-- one-card wordings (wave 110B) -- 509.1g: a blocker)
                  "recipient_subtypes": list(got[1].subtypes) if got is not None else []}  # (wave 15B)
    dealt_info["single110c"] = got is not None and e.source_targets is not None and set(e.source_targets) == {got[0].id}  # -- trigger damage (wave 110C) -- Imodane: the spell's only target
    dealt_info["recipient_blocking110c"] = got is not None and got[0].is_blocking  # -- blocking recipient (wave 110C) -- Kusari-Gama
    if got is not None:  # -- other side (wave 6D) -- "deals damage to a creature, destroy that creature" (other_side.py)
        dealt_info.update(other=got[0].id, other_oid=e.object_id)
    out.append(("deal_damage", src[0], src[1], src[0].controller, dealt_info))
    if e.player is not None:
        info = {**base, "recipient": e.player, "combat": e.combat}  # (wave 43A: combat, trigger_multipliers "dealing combat damage to a player")
        if e.player != src[0].controller:
            out.append(("deal_damage_opponent", src[0], src[1], src[0].controller, info))
        if e.combat:
            out.append(("deal_combat_damage_player", src[0], src[1], src[0].controller, info))
    return out


_PAIRED = {"block": "block_pair", "blocked": "blocked_pair"}


def _cond_matches(plan: Plan, cond: dict[str, Any], watcher: CardInstance, fact: Fact, *, source_oid: str | None = None) -> bool:
    if cond.get('first_source80'):
        from app.rules import first_crew_saddle80

        return first_crew_saddle80.matches(plan, cond, watcher, fact, source_oid)
    if cond.get('first_event78'):
        from app.rules import first_event_receipts78

        return first_event_receipts78.matches(plan, cond, watcher, fact, source_oid)
    from app.rules import selectors

    event, obj, och, player, info = fact
    you = watcher.controller
    if event == "die" and cond.get("damaged_by_exact105"):
        from app.rules import vampire_returns105

        if not vampire_returns105.damage_match(plan, info.get("oid"), source_oid or plan.oid(watcher)):
            return False
    if event == 'die' and cond.get('damaged_by_host104'):
        from app.rules import damage_death104

        if not damage_death104.matches(plan, watcher, info.get('oid'), info, source_oid):
            return False
    if event == 'deal_combat_damage_player' and cond.get('combat_recipient') == 'opponent' and info.get('recipient') == you:
        return False
    if cond.get('played_linked_name'):
        from app.rules import card_names, exiled_with

        linked_ctx = {'source_card': watcher.id, 'source_object': source_oid or plan.oid(watcher), 'controller': you}
        if och is None or not any(card_names.share(och, plan.ch(plan.state.cards[c])) for c in exiled_with.cards(plan, linked_ctx)):
            return False
    want = cond["event"]
    if cond.get('recipient_is_defender'):
        from app.rules import defending

        if obj is None or info.get('recipient') != defending.defended(plan, obj):
            return False
    if cond.get("player_controls"):
        if player is None:
            return False
        sel = selectors.replace(selectors.from_key(cond["player_controls"]), controller="you")
        if not selectors.candidates(plan, sel, player, watcher.id):
            return False
    if cond.get("exiled") and not watcher.zone.endswith(":exile"):
        return False  # -- keywords (wave 50H) -- "while it's exiled": the ability functions only there
    if cond.get("during") and (plan.active != (player if cond["during"] == "their" else you)) != (cond["during"] == "opponent"):
        return False  # -- trigger qualifiers (wave 11C) -- "during your / an opponent's / their turn" (603.2)
    if want == "either":  # -- triggers (wave 5D) -- "Whenever you create or sacrifice a token": each event (603.2c)
        return any(_cond_matches(plan, sub, watcher, fact, source_oid=source_oid) for sub in cond["conds"])
    if want == "multi":  # "Whenever ~ attacks or blocks" (this object; each event, 603.2)
        wanted = [(_PAIRED[x] if cond.get("other") else x) for x in cond["events"]]
        if cond.get("subject") == "host":  # -- attached events (wave 4L) -- what the source is attached to
            return event in wanted and obj is not None and _hosted(plan, watcher, obj, info, event) and _other_ok(plan, cond, watcher, info)  # (other: wave 11E)
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
        if pw == "chosen":
            from app.rules import chosen

            if chosen.player_of(plan, watcher.id, source_oid) != player:
                return False
        if pw == "pair110a":  # -- chosen players (wave 110A) -- Sower of Discord: one of the two players the watcher chose as it entered
            from app.rules import wave110a_pick

            if player not in wave110a_pick.pair(plan, watcher.id):
                return False
        if player is None or (pw == "you" and player != you) or (pw in ("opponent", "other") and player == you) \
                or (pw == "enchanted" and player != watcher.attached_player):
            return False
        if event in ("dealt_damage", "targeted") and obj is not None:
            return False  # ("you're dealt damage": a player, not a permanent that player controls; wave 22E: "you become the target")
        if event == "cast":
            return obj is not None and och is not None and selectors.matches(
                plan, selectors.from_key(cond["spell"]), obj, och, you, watcher.id)
        if cond.get("obj"):  # the permanent sacrificed, the card discarded, the token created …
            selected = selectors.from_key(cond["obj"])
            if event == "land_played" and info.get("snap") is not None and obj is not None:
                selected = selectors.replace(selected, zones=(obj.zone.rsplit(":", 1)[-1],))
            return obj is not None and och is not None and selectors.matches(
                plan, selected, obj, och, you, watcher.id)
        return True
    if obj is None or och is None:
        return False
    if subject == "haunted":  # -- keywords (wave 50H) -- 702.55b: the object this haunt card in exile haunts, as it died
        return event == "die" and info.get("oid") is not None and info["oid"] == plan.rules.haunting.get(plan.oid(watcher))
    if subject == "host":  # "enchanted creature" / "equipped creature": what the source is attached to
        if event in ("die", "leave"):  # -- sagas & attached-object triggers (wave 3S) --
            # 603.10a: looks back in time — what was attached to it as it last existed on the battlefield
            snap = info.get("snap")
            return snap is not None and watcher.id in snap.attached
        return _hosted(plan, watcher, obj, info, event)
    if subject == "source":  # -- source damage (wave 11F) -- "a source you control / an opponent controls deals damage": its controller
        if cond.get('source_creature_or_spell') and not (och is not None and 'Creature' in och.types
                or obj.zone == 'stack' and obj.ability is None):
            return False
        if cond.get("color") and not (och is not None and (not och.colors if cond["color"] == "colorless"  # -- counters (wave 41A) -- "a red source": 105.2
                                                          else selectors.COLORS[cond["color"]] in och.colors)):
            return False
        if cond.get("chosen_color"):  # -- chosen filters (wave 53B) -- "a source of the chosen color": the color the watching permanent chose as it entered (614.12a), none chosen: none
            selected_color = selectors.source_choice(plan, watcher.id, "color")
            if selected_color is None or selectors.COLORS.get(selected_color.lower()) not in (och.colors if och is not None else ()):
                return False
        return int(info.get("amount") or 0) > 0 and (cond.get("ctl", "any") == "any" or (cond["ctl"] == "you") == (player == you))
    if subject == "self_or_paired110c":  # -- soulbond (wave 110C) -- "~ or a creature it's paired with" (Donna Noble): the pair is on the battlefield with it (702.95e)
        return obj.id == watcher.id or (plan.rules.pairs.get(plan.oid(watcher)) or [None])[0] == plan.oid(obj) or (info.get("pair110c") is not None and info["pair110c"] == plan.oid(watcher))  # 603.2: pair as the damage was dealt
    if subject == "self_or_host":  # "~ or equipped creature"
        return obj.id == watcher.id or _hosted(plan, watcher, obj, info, event)
    if subject == "self" and event == "cycle" and cond.get("cycle_other_you") and obj.id != watcher.id:
        return watcher.zone.endswith(":battlefield") and player == you
    if subject in ("self", "self_or") and obj.id == watcher.id:
        return True
    if subject == "self":
        return False
    sel = selectors.from_key(cond["sel"])
    if event == "turned_face_up" and "face_down" in sel.extras:  # -- hidden exile (wave 18A) -- "a face-down permanent … is turned face up": it was
        sel = selectors.replace(sel, extras=tuple(x for x in sel.extras if x != "face_down"))  # face down; it is face up now
    if event in ("die", "leave") and "modified" in sel.extras:  # -- trigger other (wave 25B) -- 603.10a, 700.9: modified as it last existed
        snap = info.get("snap")
        if snap is None or not _was_modified(plan, snap):
            return False
        sel = selectors.replace(sel, extras=tuple(x for x in sel.extras if x != "modified"))
    if event == "phase_out" and obj.zone.endswith(":phased"):  # -- wave 110D -- 702.26d: the permanent that phased out is matched as the battlefield permanent it was (The War Doctor)
        obj = obj.model_copy(update={"zone": obj.zone.replace(":phased", ":battlefield")})
    return selectors.matches(plan, sel, obj, och, you, watcher.id)


_LOOK_BACK = frozenset({"dealt_damage", "deal_damage", "deal_damage_opponent", "deal_combat_damage_player", "tapped"})


def _hosted(plan: Plan, watcher: CardInstance, obj: CardInstance, info: dict[str, Any], event: str) -> bool:
    """-- attached triggers (wave 50D) -- 603.2, 704.3: "enchanted / equipped creature is dealt damage / deals damage": the event happened while the Aura / Equipment
    was attached. State-based actions come after it (704.5g, 704.5m, 704.5n), so by the time the trigger is looked at the creature may be gone and the Aura let go
    of it (or the Equipment unattached): the creature's last known information lists what was attached to it (603.10a).
    ponytail: that list is as the creature left, not as the damage was dealt; they differ only if the Aura / Equipment moved between the two within one look.
    Only for those events: an ability is activated once its costs are paid (602.2i), so a creature sacrificed to pay for it is no longer equipped (Illusionist's Bracers ruling)."""
    snap = plan.rules.lki.get(info.get("oid") or "") if event in _LOOK_BACK else None
    return (watcher.attached_to is not None and obj.id == watcher.attached_to) or (snap is not None and watcher.id in snap.attached)


def _was_modified(plan: Plan, snap: ObjectSnapshot) -> bool:
    """-- trigger other (wave 25B) -- 700.9: a permanent is modified if it has a counter, is equipped, or is enchanted by an Aura its
    controller controls; a permanent that left is read as it last existed (603.10a: the counters and attachments it had)."""
    if any(n > 0 for n in snap.counters.values()):
        return True
    for cid in snap.attached:
        att = plan.state.cards.get(cid)
        if att is not None:
            subs = plan.ch(att).subtypes
            if "Equipment" in subs or ("Aura" in subs and att.controller == snap.controller):
                return True
    return False


def _damaged_by(plan: Plan, watcher: CardInstance, victim: str | None) -> bool:
    """-- counters (wave 7C) -- did the watcher (the object it is now, or as it last existed if it left) deal damage this
    turn to the object that died? (the turn's log: history.note_events)"""
    log = plan.rules.turn_log
    if victim is None or log.turn != plan.state.turn.number:
        return False
    if plan.state.cards.get(watcher.id) is watcher:
        mine = {plan.oid(watcher)}
    else:  # it left in the same batch: the object it was (603.10a)
        mine = {o for o, s in plan.rules.lki.items() if s.card == watcher.id}
    return any(f.kind == "damaged" and f.object_id == victim and f.source in mine for f in log.facts)


def _other_ok(plan: Plan, cond: dict[str, Any], watcher: CardInstance, info: dict[str, Any], obj: CardInstance | None = None) -> bool:
    """"blocks a creature with flying" / "becomes blocked by a Wall": the creature on the other side."""
    from app.rules import selectors

    if not cond.get("other"):
        return True
    other = plan.state.cards.get(info.get("other") or "")
    if other is not None and cond.get("other_cmp") and obj is not None:  # -- block events (wave 53C) -- "blocked by a creature with lesser power" (No Quarter): than the creature it is blocked by / blocks, 509.3f
        from app.rules.sba import power

        theirs, mine = power(other, plan.ch(other)), power(obj, plan.ch(obj))
        if theirs is None or mine is None or not theirs < mine:
            return False
    return other is not None and selectors.matches(plan, selectors.from_key(cond["other"]), other, plan.ch(other),
                                                   watcher.controller, watcher.id)


def _details_ok(plan: Plan, cond: dict[str, Any], watcher: CardInstance, fact: Fact) -> bool:
    """The parts of a condition beyond its subject and event."""
    if cond.get('target_source77'):
        from app.rules import targeting_sources77

        if not targeting_sources77.matches(plan, cond, fact):
            return False
    from app.rules import selectors

    event, obj, och, player, info = fact
    you = watcher.controller
    if cond.get('during_step') and plan.state.turn.phase != cond['during_step']:
        return False
    if 'life_loss_exact' in cond and (event != 'lose_life' or info.get('amount') != cond['life_loss_exact']):
        return False
    if event == "attack" and cond.get("defender_lands_min"):
        defender = obj.attacking.id if obj is not None and obj.attacking is not None and obj.attacking.kind == "player" else None
        lands = sum(c.zone.endswith(":battlefield") and c.controller == defender and plan.ch(c).is_land for c in plan.state.cards.values())
        if defender not in plan.live() or lands < cond["defender_lands_min"]:
            return False
    if cond.get("recipient_more_lands"):
        recipient = info.get("recipient")
        own_lands = sum(c.zone.endswith(":battlefield") and c.controller == you and plan.ch(c).is_land for c in plan.state.cards.values())
        recipient_lands = sum(c.zone.endswith(":battlefield") and c.controller == recipient and plan.ch(c).is_land for c in plan.state.cards.values())
        if recipient not in plan.live() or recipient_lands <= own_lands:
            return False
    if event == "exerted" and cond.get("by") == "you" and player != you:
        return False
    if cond.get("not_played") and info.get("played"):
        return False
    if cond.get("own_untap") and not (info.get("step_phase") == "untap" and info.get("active_player") == watcher.controller):
        return False
    if cond.get("aura_controller57"):
        from app.rules import graveyard_return57

        if not graveyard_return57.enchanted_before(you, info):
            return False
    if not _other_ok(plan, cond, watcher, info, obj):
        return False
    if cond.get("host_mv_le_aura110n"):  # -- (wave 110N) -- Eriette: "with mana value less than or equal to that Aura's mana value", part of the event (603.2)
        host = plan.state.cards.get(info.get("other") or "")
        if obj is None or host is None or plan.ch(host).mana_value > plan.ch(obj).mana_value:
            return False
    if cond.get("mana_source") == "self" and plan.oid(watcher) not in info.get("mana_sources", []):
        return False
    if cond.get("to") == "self" and info.get("other") != watcher.id:  # -- attachment events (wave 30S) -- "an Aura becomes attached to this creature"
        return False
    if cond.get("cause") == "opponent" and not (  # -- discard causes (wave 23D) -- 701.9: "a spell or ability an opponent controls causes you to
            info.get("by") and info["by"] != player):  # discard": the discard was moved by a resolving effect of another player
        return False
    if cond.get("main_phase") and plan.state.turn.phase not in ("main1", "main2"):  # -- crew & saddle (wave 23D) -- "during your main phase"
        return False
    if cond.get("exploited") and not (  # -- keyword triggers (wave 23D) -- "exploits a nontoken creature": the one sacrificed, as it was (702.110b)
            info.get("exploited") and selectors.matches(plan, selectors.from_key(cond["exploited"]), info["exploited"][0],
                                                        info["exploited"][1], you, watcher.id)):
        return False
    if cond.get("into") and (info.get("face_name") or "").lower() != cond["into"].lower():  # -- transform (wave 16F) --
        return False
    if cond.get("into_sel") and not (obj is not None and och is not None and selectors.matches(  # -- transform (wave 26D) -- "transforms into a Phyrexian": its new face
            plan, selectors.from_key(cond["into_sel"]), obj, och, you, watcher.id)):
        return False
    if cond.get("alone") and info.get("attackers") != 1:  # 506.5
        return False
    if cond.get("min_blockers") and info.get("blockers", 0) < cond["min_blockers"]:  # -- block events (wave 53C) -- 509.3c: "becomes blocked by two or more creatures"
        return False
    if cond.get("min_blocked") and info.get("blocked", 0) < cond["min_blocked"]:  # -- trigger lines (wave 100A) -- 509.3e: "blocks two or more creatures"
        return False
    if cond.get("while") is not None:  # "attacks while you control …", -- counters (wave 33C) -- "enters while this creature has a -1/-1 counter on it": part of the trigger event
        from app.rules import conditions

        if not conditions.holds(plan, {"controller": you, "source_card": watcher.id}, cond["while"]):
            return False
    if event in ("attack", "unblocked", "you_attack"):
        if cond.get("self_or_owned_commander") and not any(
                cid == watcher.id or (plan.state.cards[cid].owner == you and plan.state.cards[cid].commander_key is not None)
                for cid in info.get("attacking", []) if cid in plan.state.cards):
            return False
        want = cond.get("defender")
        # "whenever you attack" is once per combat; "whenever a player attacks you" once per player
        # attacked (508.3d, 508.3e): each reads only its own fact
        if event == "you_attack" and want == "opponent_any":  # -- trigger sweep (wave 27B) -- "a player attacks one or more of your opponents": once per attack (508.3d)
            if "defended" in info or not any(d != watcher.controller for d in info.get("defended_direct", [])):
                return False
        elif event == "you_attack" and bool(want) != ("defended" in info):
            return False
        if event == "you_attack" and ("pw" in info) != (want == "each_pw") and not (want == "player_or_pw" and "pw" in info):  # (wave 110M)  # -- trigger lines (wave 110F) -- 508.3a: one fact per planeswalker attacked
            return False
        if want and want != "opponent_any" and not _defender_ok(want, watcher, info, plan):
            return False
        if cond.get("first_each_turn") and not info.get("first"):
            return False
        if cond.get("defending_player") == "you":  # -- trigger other (wave 44B) -- 508.5: "if you're the defending player" (a battle you protect included)
            from app.rules import defending

            if obj is None or defending.defended(plan, obj) != you:
                return False
    if event == 'dealt_damage' and cond.get('damage_source'):
        ref = _source_ref(plan, info.get('source_oid'))
        source = _object_then(plan, ref.card, ref.object_id) if ref is not None else None
        if source is None or not selectors.matches(plan, selectors.from_key(cond['damage_source']),
                                                   source[0], source[1], watcher.controller, watcher.id):
            return False
    if event == "dealt_damage" and cond.get("combat") is not None and bool(info.get("combat")) != cond["combat"]:
        return False
    if event == "dealt_damage" and cond.get("excess") and int(info.get("excess") or 0) <= 0:  # -- trigger damage (wave 39B) -- 120.10: it was dealt excess damage
        return False
    if cond.get("first_each_turn") and event in ("dealt_damage", "deal_combat_damage_player", "counters_put") and not _first_of(plan, cond, event, info):
        return False  # (wave 39B)
    if event in _FIRST_KINDS and cond.get("first_each_turn") and not info.get("first"):  # (wave 11C)
        return False
    if event == "tapped" and cond.get("first_each_turn") and not info.get("first"):  # (wave 42B)
        return False
    if event == "discard" and cond.get("first_each_turn") and not _first_discard(plan, cond, player, info):  # (wave 36A)
        return False
    if cond.get('treasure_paid'):
        tags = (info.get('activation_cost') or {}).get('mana_tags') if event == 'activate' else info.get('mana_tags')
        if not any('Treasure' in t for t in tags or []):
            return False
    if cond.get('snow_matches_spell') and (och is None or not any(
            (info.get('snow_spent') or {}).get(color, 0) > 0 for color in och.colors)):
        return False
    if cond.get('cost_has_x') and (och is None or '{X}' not in (och.mana_cost or '')):
        return False
    if event == 'activate' and info.get('loyalty_removed110b', 0) < cond.get('loyalty_removed110b', 0):
        return False  # -- wave 110B -- "if you removed two or more loyalty counters to activate it" (Way of the Mind Sculptor)
    if cond.get('activation_cost'):
        from app.rules import activated_copy_effects

        if not activated_copy_effects.matches(cond['activation_cost'], info.get('activation_cost')):
            return False
    if event == 'activate' and cond.get('only_self103'):
        ref = info.get('source_ref')
        entry = plan.rules.stack.get(ref.card) if ref is not None else None
        if entry is None or not _targets_ok(plan, 'self_only', watcher, [(t.id, t.object_id) for t in entry.targets]):
            return False
    if event == "activate" and cond.get("nonmana") and info.get("mana_ability"):
        return False
    if event == "activate" and ((cond.get("loyalty") and not info.get("loyalty")) or (
            cond.get("own") and (obj is None or obj.controller != player))):  # -- activation (wave 11F) --
        return False
    if event == "activate" and cond.get("gy110d") and (obj is None or obj.zone != f"{obj.owner}:graveyard" or obj.owner != info.get("actor")):  # (wave 110D) Neerdiv
        return False
    if event == "activate" and cond.get("ability_kinds") and info.get("ability_kind") not in cond["ability_kinds"]:
        return False
    if event == "activate" and cond.get("ability_kind") != info.get("ability_kind") and cond.get("ability_kind"):
        return False
    if event == "activate" and cond.get("host_source") and (obj is None or not _hosted(plan, watcher, obj, info, event)):
        return False
    if event == "activate" and cond.get("ability_word") and info.get("outlast110b") is not True:  # -- (wave 110B) -- its own outlast ability (702.107a)
        return False
    if event == "activate" and cond.get("self_source") and (obj is None or obj.id != watcher.id):
        return False
    if event == "activate" and cond.get("word") and info.get("word") != cond["word"]:  # -- counters (wave 33C) -- "an exhaust / a boast / a power-up ability"
        return False
    if event == "activate" and cond.get("ability_targets"):  # -- stack interaction (wave 23B) -- "an ability that targets a creature or player"
        ref = info.get("source_ref")
        ability = plan.state.cards.get(ref.card) if ref is not None else None
        if ability is None or not any(selectors.targets_match(plan, ability, x, you, watcher.id) for x in cond["ability_targets"]):
            return False
    if event == "become_level" and cond.get("level") != info.get("level"):  # -- Class (wave 16A) --
        return False
    if event == "unlock_door" and cond.get("door") != info.get("door"):  # -- Rooms (wave 18G) -- only the door that was unlocked
        return False
    if event in ("scry", "surveil") and cond.get("nth") and info.get("nth") != cond["nth"]:  # -- looks (wave 8B) --
        return False
    if event == "coin_flip" and cond.get("won") != info.get("won"):  # -- coin events (wave 45C) -- won or lost (705.2)
        return False
    if event == "turned_face_up" and cond.get("turner110d") == "you" and info.get("tapper") != you:
        return False  # -- lines (wave 110D) -- "Whenever you turn a permanent face up": 702.37e, 701.40b the player who turned it up
    if event == "tapped" and ((cond.get("tapper") == "you" and info.get("tapper") != you) or (cond.get("not_declared") and info.get("declared"))):
        return False  # -- tap events (wave 45C) -- "you tap …" (the step's actor); "if it isn't being declared as an attacker" (508.1f)
    if event == "control_change":
        if cond.get("to") == "you":
            if player != you or info.get("was") in (None, you):
                return False
        elif player == you or info.get("was") != you:
            return False
    if event == "final_chapter" and cond.get("when") != info.get("when"):  # -- saga events (wave 45C) -- triggers or resolves (rules/sagas.py)
        return False
    if event == "roll_die":  # -- dice (wave 24B) -- the die's own result / size / place in the turn (app/rules/dice.py)
        from app.rules import dice

        if not dice.die_matches(cond, info):
            return False
    if event == "roll_visit":  # -- Attractions (wave 100L) -- a visit ability: the result lit up on it (702.159a)
        from app.rules import attractions100l

        if not attractions100l.matches(plan, cond, watcher, info):
            return False
    if event == "die" and cond.get("damaged_by_self") and not _damaged_by(plan, watcher, info.get("oid")):  # (wave 7C)
        return False
    if event in ("die", "enter") and cond.get("in_combat") and plan.state.turn.phase not in COMBAT_PHASES:  # (wave 16C: "dies during combat"; 30T: "enters")
        return False
    n = cond.get("min_attackers")
    if n and len(_counted_attackers(plan, cond, watcher, info)) < n:
        return False
    if cond.get("min_total_power") and sum((plan.ch(c).pt or (0, 0))[0] for c in _counted_attackers(plan, cond, watcher, info)) < cond["min_total_power"]:  # (wave 110D)
        return False
    if (cap := cond.get("max_attackers110j")) and len(_counted_attackers(plan, cond, watcher, info)) > cap:  # -- wave 110J -- "exactly two creatures" (Love on the Battlefield)
        return False
    if cond.get("all110j"):  # -- wave 110J -- "Whenever all non-Wall creatures you control attack" (Mob Mentality): none of them stays home, 508.1
        from app.rules import selectors as _sel

        kind = _sel.from_key(cond["sel"])
        if any(c.id not in (info.get("attacking") or []) for c in plan.state.cards.values() if c.zone.endswith(":battlefield")
               and c.controller == watcher.controller and _sel.matches(plan, kind, c, plan.ch(c), watcher.controller, watcher.id)):
            return False
    if event == "cast":
        if cond.get('cast_targets102') and not (info.get('targets') or []):
            return False
        if cond.get('disjoint_creatures102'):
            from app.rules import stack_events102

            if obj is None or not stack_events102.disjoint(plan, watcher, obj):
                return False
        if cond.get("cast_foreign_owned") and (obj is None or obj.owner == info.get("actor")):
            return False
        if cond.get('card_only') and (obj is None or obj.is_token):
            return False
        if cond.get("nth") and info.get("nth") != cond["nth"]:
            return False
        if cond.get("nth_min") and int(info.get("nth") or 0) < cond["nth_min"]:  # -- counters (wave 21D) --
            return False
        if cond.get("first_kind"):  # -- unless pays (wave 4C) --
            from app.rules import unless_pays

            if not unless_pays.first_of_kind(cond["spell"], info.get("kinds_before") or []):
                return False
        if cond.get("first_note"):  # -- history (wave 22E) -- 601.2i: no spell of that kind by this player earlier this turn (the turn's casts, as cast)
            from app.rules import history

            kind = selectors.from_key(cond["spell"])
            if sum(1 for n in history.log_for(plan).casts if n.player == player
                   and history.note_matches(kind, n.types, n.subtypes, n.supertypes, n.colors, n.mv, x_cost=n.x_cost)) != 1:
                return False
        if cond.get("alania110b") and not alania_first(plan, watcher, player, info):  # -- wave 110B -- Alania: the first instant, sorcery or Otter (other than it) cast this turn
            return False
        if cond.get("nth_note"):  # -- triggers (wave 30J) -- 601.2i: this spell is the Nth of its kind (and place) this player cast this turn
            from app.rules import history

            kind = selectors.from_key(cond["spell"])
            same = [n.object_id for n in history.log_for(plan).casts if n.player == player and (not cond.get("note_from") or n.cast_from == cond["note_from"])
                    and history.note_matches(kind, n.types, n.subtypes, n.supertypes, n.colors, n.mv, x_cost=n.x_cost)]
            if info.get("oid") not in same or same.index(info["oid"]) + 1 != cond["nth_note"]:
                return False
        if cond.get("turn") == "opponent" and not info.get("opponent_turn"):
            return False
        if cond.get("kicked") and not info.get("kicked"):
            return False
        if cond.get("teamwork") and not info.get("teamwork"):  # -- (wave 110G) -- "a spell using teamwork" (702.194b)
            return False
        frm = _zone(info.get("from"))
        frm = "exile" if frm == "foretell" else frm  # (-- review 30 -- the foretell zone is exile, 702.143a, as casting.cast_spell records it)
        origin = info.get("from") or ""
        owner = origin.split(":", 1)[0] if ":" in origin else None
        wanted_owner = you if cond.get("from_owner") == "you" else info.get("actor")
        if cond.get("from") == "not_hand" and cond.get("from_owner"):
            # Outside YOUR/THEIR hand includes another player's hand. An
            # unidentified hand origin cannot prove that negative predicate.
            if not frm or (frm == "hand" and (owner is None or wanted_owner is None or owner == wanted_owner)):
                return False
        else:
            if cond.get("from") and not (frm == cond["from"] or (cond["from"] == "not_hand" and frm and frm != "hand")):
                return False
            if cond.get("from_owner") and (owner is None or owner != wanted_owner):
                return False
        if cond.get("targets") and not _targets_ok(plan, cond["targets"], watcher, info.get("targets") or []):
            return False
    if event == "targeted":
        by = cond.get("by", "any")
        if (by == "you" and info.get("by") != you) or (by == "opponent" and info.get("by") == you):
            return False
        if cond.get("spell_only") and not info.get("spell"):
            return False
        if cond.get("ability_only") and info.get("spell"):  # -- stack interaction (wave 23B) -- "becomes the target of an ability"
            return False
        if cond.get("first_each_turn") and not (info.get("first") or {}).get({"you": "by", "opponent": "by_opp"}.get(by, "any")):
            return False
        if cond.get("spell_sel"):  # -- history (wave 22E) -- "an instant or sorcery spell": the spell as it is on the stack
            ref = info.get("source_ref")
            spell = plan.state.cards.get(ref.card) if ref is not None else None
            if spell is None or spell.ability is not None or not selectors.matches(
                    plan, selectors.from_key(cond["spell_sel"]), spell, plan.ch(spell), you, watcher.id):
                return False
    if event in ("enter", "land_played") and cond.get("entered_from"):  # -- history (wave 22E) -- "Whenever a creature enters from your graveyard"
        from app.rules import history

        # (-- trigger from (wave 30F) -- 701.18a: "you play a land from exile" is the zone the land was put onto the battlefield from: the turn's
        # entry log has it, recorded with the move before this event)
        came = history.entered_from(info.get("entered_from"), cond["entered_from"], you) if event == "enter" \
            else history.entered_from(info["played_from"], cond["entered_from"], you) if info.get("played_from") is not None \
            else history.entry_came_from(plan, info.get("oid"), cond["entered_from"], you)
        if not came:
            return False
    if event == "enter" and cond.get("entered_tapped") is not None:  # -- entry forms (wave 5F) --
        from app.rules import entry_forms

        if entry_forms.entered_tapped(plan, info) != cond["entered_tapped"]:
            return False
    if event == "enter" and cond.get("entered_transformed110j"):  # -- wave 110J -- 712.14a
        from app.rules import wave110j_cards

        if not wave110j_cards.entered_transformed(plan, info):
            return False
    if event == "counters_put" and cond.get("counter") and info.get("counter") != cond["counter"]:
        return False
    if event == "counters_put" and cond.get("nth") and not (info.get("total", 0) - info.get("amount", 0) < cond["nth"] <= info.get("total", 0)):
        return False  # -- most-played cards (wave 43B) -- fewer than that many before the counters were put on, that many or more after
    if event == "counters_removed" and ((cond.get("counter") and info.get("counter") != cond["counter"])
                                        or (cond.get("last") and not info.get("last"))):  # (wave 15E)
        return False
    if event == "leave" and cond.get("dest") and _zone(info.get("to")) != cond["dest"]:  # -- trigger tail (wave 15B) -- "put into exile"
        return False
    if event == "leave" and cond.get("nodie") and (_zone(info.get("to")) == "graveyard" or (info.get("to") is None and getattr(info.get("snap"), "is_token", False))):
        return False  # -- triggers (wave 17D) -- "without dying": 700.4's own test, as _zone_facts makes the "die" fact
    if event == "explore" and cond.get("kind") and info.get("revealed") != (1 if cond["kind"] == "land" else 2):
        return False  # (-- trigger tail (wave 15B) -- "explores a land card": the card it revealed)
    if event == "expend" and not info["before"] < cond["n"] <= info["after"]:
        return False
    if event == "to_graveyard" and cond.get("from") and info.get("from") != cond["from"]:  # -- into a graveyard (wave 6D)
        return False
    if event == "to_graveyard" and cond.get("froms") and info.get("from") not in cond["froms"]:  # -- trigger other (wave 110B) -- "from your hand or library"
        return False
    if event == "to_graveyard" and cond.get("not_from") and info.get("from") == cond["not_from"]:  # -- most-played cards (wave 43B) -- "from anywhere other than the battlefield"
        return False
    if event in ("to_exile", "to_library") and ((cond.get("froms") and info.get("from") not in cond["froms"])
                                                 or (cond.get("from_owner") == "you" and info.get("from_owner") != you)):
        return False  # -- counters (wave 21D) -- "put into exile from your graveyard"
    # -- graveyard owner (wave 6D) -- "put into your / an opponent's graveyard": its owner's graveyard (400.3)
    if event == "die" and cond.get("gy_owner") and (obj is None or (obj.owner == you) != (cond["gy_owner"] == "you")):
        return False
    if event == "die" and cond.get("cause_opp110g") and info.get("cause110g") in (None, you):  # -- wave 110G -- "a spell or ability an opponent controls causes" (SBA: no cause)
        return False
    if event in ("counters_put", "counters_removed", "player_counters") and cond.get("by") == "you" and info.get("actor") != you:  # -- counters (wave 5H) --
        return False  # ("Whenever you put one or more +1/+1 counters on …": the player who put them, 122.6a)
    if event == "counters_put" and cond.get("by") == "opponent" and (info.get("actor") in (None, you)):  # (wave 7C)
        return False
    if event == "counters_put" and cond.get("own") and (obj is None or obj.controller != info.get("actor")):
        return False  # ("… on a creature they control": the permanent's controller is the player who put them)
    if event == "player_counters" and cond.get("counter") and info.get("counter") != cond.get("counter"):  # (wave 3E: "you get one or more {E}")
        return False
    if event == "deal_damage":
        combat = cond.get("combat")
        if combat is not None and bool(info.get("combat")) != combat:
            return False
        to = cond.get("to", "any")
        if to == "enchanted_planeswalker":
            target = info.get("other")
            oid = info.get("other_oid")
            current = target in plan.state.cards and plan.oid(target) == oid and watcher.attached_to == target
            before = plan.rules.lki.get(oid or "")
            if not info.get("recipient_planeswalker") or not (current or (before is not None and watcher.id in before.attached)):
                return False
        if cond.get("blocking110c") and not info.get("recipient_blocking110c"):
            return False
        if cond.get("single110c") and not info.get("single110c"):
            return False
        recipient = info.get("recipient")
        if (to == "player" and recipient is None) or (to == "you" and recipient != you) or (to.startswith("pid:") and recipient != to[4:]) or \
                (to == "you_or_perm110b" and you not in (recipient, info.get("recipient_ctl110b"))) or \
                (to == "creature_or_opponent" and not (info.get('recipient_creature') or recipient is not None and recipient != you)) or \
                (to == "opponent" and (recipient is None or recipient == you)) or \
                (to == "creature" and not info.get("recipient_creature")) or \
                (cond.get("to_types") and not set(cond["to_types"]) & set(info.get("recipient_subtypes") or ())) or \
                (to == "planeswalker" and not info.get("recipient_planeswalker")) or \
                (to == "player_or_pw" and recipient is None and not info.get("recipient_planeswalker")) or \
                (to == "player_or_battle" and recipient is None and not info.get("recipient_battle")) or \
                (to == "opponent_or_battle" and (recipient == you or recipient is None and not info.get("recipient_battle"))) or \
                (to == "its_owner" and (recipient is None or obj is None or recipient != obj.owner)) or \
                (to == "self" and info.get("other") != watcher.id) or \
                (to == "players" and recipient is None) or (to == "opponents" and (recipient is None or recipient == you)) or \
                (to == "creatures" and not info.get("recipient_creature")) or (cond.get("blocking110b") and not info.get("recipient_blocking110b")) or \
                (cond.get("min") and int(info.get("amount") or 0) < cond["min"]) or \
                (cond.get("eq_toughness110b") and info.get("amount") != info.get("recipient_toughness110b")) or \
                (to == "enchanted_player" and (recipient is None or recipient != watcher.attached_player)):
            return False
    return True


def _defender_ok(want: str, watcher: CardInstance, info: dict[str, Any], plan: Plan | None = None) -> bool:
    """Whom the attack was declared against (508.3a, 508.3e, 508.6): ``defended`` is the defending
    player (a planeswalker's controller), ``direct`` whether it was that player (not a planeswalker)."""
    defended, you = info.get("defended"), watcher.controller
    if want == "battle":  # -- triggers (wave 49C) -- "attacks a battle": the attack's recipient is a battle (310.5)
        return bool(info.get("battle"))
    if defended is None or (info.get("battle") and want in ("you_or_pw", "opponent_or_pw")):
        return False  # (-- review 34 -- 310.5, 508.5: a creature attacking a battle attacks no player and no planeswalker, Gahiji / Frontier Warmonger)
    if want == "each_pw":
        return defended == you
    if want == "player_or_pw":  # -- (wave 110M) -- 508.3a: a player attacked directly, or a planeswalker (its own fact)
        return bool(info.get("pw")) or bool(info.get("direct"))
    if want == "your_pw":
        if plan is None or defended != you:
            return False
        return any(
            (attacker := plan.state.cards.get(cid)) is not None and attacker.attacking is not None
            and attacker.attacking.kind != "player"
            and (target := plan.state.cards.get(attacker.attacking.id)) is not None
            and target.controller == you and "Planeswalker" in plan.ch(target).types
            for cid in info.get("attacking", [])
        )
    if want == "you_or_pw":  # "attacks you or a planeswalker you control"
        return defended == you
    if want == "opponent_or_pw":  # -- trigger other (wave 36A) -- "attacks one of your opponents or a planeswalker an opponent controls": not you, not what you control
        return defended != you
    if want == "truce100a":  # -- trigger lines (wave 100A) -- Tenuous Truce: you attack the enchanted player or a planeswalker they control, or they attack you or yours
        return not info.get("battle") and (info.get("attacker"), defended) in ((you, watcher.attached_player), (watcher.attached_player, you))
    if not info.get("direct"):
        return False
    if want == "you":
        return defended == you
    if want == "opponent":  # "attacks one of your opponents"
        return defended != you
    if want == "other_opponent":  # -- trigger sweep (wave 27B) -- "an opponent attacks another one of your opponents": neither you nor the attacker
        return defended not in (you, info.get("attacker"))
    if want == "enchanted_player":
        return defended == watcher.attached_player
    if want == "monarch":  # -- this-turn state (wave 42B) -- 725.1: the player attacked is the monarch now (as the attack is declared)
        return plan is not None and defended == plan.state.table.monarch
    if want == "initiative":  # -- initiative (wave 45B) -- 726.1: the player attacked has the initiative now (as the attack is declared)
        return plan is not None and defended == plan.state.table.initiative
    if want == "most_life":  # -- keywords (wave 15E) -- 702.105a: the player attacked has the most life or is tied for it
        return plan is not None and plan.state.players[defended].life >= max(plan.state.players[p].life for p in plan.live())
    return want == "player"


def _first_of(plan: Plan, cond: dict[str, Any], event: str, info: dict[str, Any]) -> bool:
    """-- trigger damage (wave 39B) -- "Whenever ~ is dealt damage / deals combat damage to a player / has +1/+1 counters put on it for the first time each
    turn" (Hercules, Raphael, Axgard Artisan, Danny Pink; 603.2): this event is the first of its kind for THIS object this turn when no earlier batch of the
    turn did the same to it (400.7: a new object has done nothing yet). The turn's log has each damage and counters fact with its batch (history.note_events),
    so an ability the object gained mid-turn counts what happened before it had it, and two events of one batch (simultaneous damage) are one."""
    from app.rules import combat_player_scope43, history

    if event == 'deal_combat_damage_player':
        return combat_player_scope43.first_result(plan, cond, info) is True

    batch, oid = int(info.get("batch") or 0), info.get("oid")
    kind, key = {"dealt_damage": ("damaged", "object_id"), "deal_combat_damage_player": ("damage", "object_id"),
                 "counters_put": ("counters", "object_id")}[event]
    for f in history.log_for(plan).facts:
        if f.kind != kind or getattr(f, key) != oid or f.amount <= 0 or not f.batch or f.batch >= batch:
            continue
        if (event == "dealt_damage" and cond.get("combat") is not None and f.combat != cond["combat"]) \
                or (event == "deal_combat_damage_player" and not f.combat) or (event == "counters_put" and cond.get("counter") and f.counter != cond["counter"]):
            continue
        return False
    return True


def _first_discard(plan: Plan, cond: dict[str, Any], player: str | None, info: dict[str, Any]) -> bool:
    """-- trigger other (wave 36A) -- "Whenever you discard one or more [nonland] cards for the first time each turn" (Rielle, the Everwise; Veronica,
    Dissident Scribe): this event (the batch of discards, 603.2c) is the first of its kind this turn when no earlier batch of the turn discarded a card
    that fits (a land discarded earlier doesn't count for "nonland cards"). The turn's log has each discard and its batch (history.note_events)."""
    from app.rules import history, selectors

    sel = selectors.from_key(cond["obj"]) if cond.get("obj") else None
    batch = int(info.get("batch") or 0)
    for f in history.log_for(plan).facts:
        if f.kind != "discard" or f.player != player or not f.batch or f.batch >= batch:
            continue
        if sel is None or history.note_matches(sel, f.types, f.subtypes, f.supertypes):
            return False
    return True


def _targets_ok(plan: Plan, want: str, watcher: CardInstance, targets: list[tuple[str, str | None]]) -> bool:
    """115.9b: "a spell that targets ~ / a creature you control" — the spell's targets as they are now."""
    from app.rules import selectors

    if want.startswith("opp_or:"):  # -- counters (wave 33C) -- 115.9b: "a spell that targets an opponent or a creature an opponent controls" (Danitha)
        return any(c in plan.state.players and c != watcher.controller for c, _ in targets) or _targets_ok(plan, want[len("opp_or:"):], watcher, targets)
    if want == "self_only":  # -- copied abilities (wave 18F) -- "that targets only ~": every target, and at least one, is the watcher (115.9b)
        return bool(targets) and all(c == watcher.id and (o is None or plan.oid(watcher) == o) for c, o in targets)
    if want.startswith("only_one:"):  # -- spell copies (wave 31D) -- 115.9c: exactly one different object or player chosen, and 115.9b: it matches now
        if len({c for c, _ in targets}) != 1:
            return False
        card_id, oid = targets[0]
        card = plan.state.cards.get(card_id)
        return card is not None and (oid is None or plan.oid(card) == oid) and selectors.matches(
            plan, selectors.from_key(want[len("only_one:"):]), card, plan.ch(card), watcher.controller, watcher.id)
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


def _counted_attackers(plan: Plan, cond: dict[str, Any], watcher: CardInstance, info: dict[str, Any]) -> list[CardInstance]:
    """The attackers a "you attack with N or more …" condition counts (508.1, 603.2c): those attacking that player when one is
    named, not ~ for "other", and of the kind named. (Review 22E: "those creatures" / "that many" are these, not every attacker.)"""
    from app.rules import selectors

    direct = cond.get("defender") not in (None, "you_or_pw", "each_pw")  # (only the creatures attacking that player; wave 110F: each_pw counts the creatures at that planeswalker)
    direct = direct and not (cond.get("defender") == "player_or_pw" and "pw" in info)  # (wave 110M) a planeswalker's own fact counts its attackers
    attackers = [plan.state.cards[c] for c in info.get("attacking_direct" if direct and "attacking_direct" in info
                                                       else "attacking") or [] if c in plan.state.cards]
    if cond.get("others_only"):  # (wave 11C) "~ and at least one other Warrior attack": not counting ~
        attackers = [c for c in attackers if c.id != watcher.id]
    if cond.get("sel"):
        sel = selectors.from_key(cond["sel"])
        attackers = [c for c in attackers if selectors.matches(plan, sel, c, plan.ch(c), watcher.controller, watcher.id)]
    return attackers


def _event(plan: Plan, fact: Fact, batch: int) -> TriggerEvent:
    kind, obj, _, player, info = fact
    ref = _ref(obj, info, plan)
    new: list[ObjectRef] = []
    if obj is not None:
        new = _new_ref(obj.id, info.get("new_oid"), info.get("to"))
        if kind in ("leave", "die") and info.get("new_oid"):  # (review (wave 18D): a merged permanent became all of its cards, 730.3c)
            new += pile_refs(plan, next((e for e in plan.rules.events if e.kind == "zone_change" and e.object_id == info.get("oid")
                                         and e.new_object_id == info["new_oid"]), None))
    if info.get("recipient"):
        players = [info["recipient"]]
    elif info.get("actor"):  # the player who cast, sacrificed, discarded, cycled, created …
        players = [info["actor"]]
    elif player and obj is not None and kind in ("enter", "die", "leave", "to_graveyard", "unblocked"):  # CR 509.3g: the attacking creature's controller at the event
        # -- triggers (wave 5D) -- "Whenever a creature an opponent controls dies, that player loses 2 life": its
        # controller as it entered / as it last existed (603.10a), fixed as it triggers
        players = [player]
    else:
        players = [player] if player and obj is None else []
    from app.game.rules_state import CounterPlacement

    placements = [CounterPlacement(destination=ref, kind=info["counter"], amount=int(info["amount"]))] \
        if kind == "counters_put" and ref is not None and info.get("counter") and int(info.get("amount") or 0) > 0 else []
    return TriggerEvent(kind=kind, batch=batch, objects=[ref] if ref else [], new_objects=new, players=players,
                        counter_placements=placements,
                        dice_total=info.get("dice_total") if kind == "roll" else None,
                        turn_start_life=info.get('turn_start_life') if kind=='lose_game' else None,
                        actor=info.get("actor"), attacking_player=info.get("attacking_player"),
                        cast_targets=[target for _, oid in info.get('targets') or [] if oid and (target := _source_ref(plan, oid)) is not None] if kind == 'cast' else [],
                        activation_cost=info.get('activation_cost') if kind=='activate' else None,
                        mana_spent=info.get("mana_spent") if kind=="cast" else None,
                        sacrificed=_was_sacrificed(plan, batch, info.get("oid")) if kind in ("die", "leave") else None,
                        source=info.get("source_ref") or (
                            _source_ref(plan, info.get("source_oid")) if kind == "dealt_damage" else None),
                        amount=int(info.get("amount") or 0), count=1, x=info.get("x") if kind in ("cycle", "cast") else None, combat=info.get("combat"),  # (wave 43A)
                        defended=info.get("defended") if kind == "you_attack" else _attack_defended(plan, kind, obj),
                        attacked_players=info.get("defended_direct", []) if kind == "you_attack" else [],
                        attacked=_attack_object(plan, kind, obj),  # (wave 45A)
                        # -- damage wordings (wave 6B) -- the creature on the other side of a block (509.3c-d)
                        other=_source_ref(plan, plan.oid(plan.state.cards[info["other"]]))
                        if kind in _PAIRED.values() and info.get("other") in plan.state.cards
                        else _source_ref(plan, info.get("exploited_oid")) if kind == "exploit" else  # -- exploit (wave 110G) -- the exploited creature, as it was
                        _source_ref(plan, info.get("bearer")) if kind == "ring_tempts" else None,  # (wave 19B: the Ring-bearer chosen)
                        ballots=info.get("ballots") or [], combat_alone110g=info.get("alone110g"))  # (-- voting (wave 48D) --)


def _attack_object(plan: Plan, kind: str, obj: CardInstance | None) -> ObjectRef | None:
    """-- attacked object (wave 45A) -- an attacking creature's event: the planeswalker or battle it attacks now (508.5), else None (a player)."""
    t = obj.attacking if obj is not None and kind in ("attack", "unblocked", "blocked", "blocked_pair") else None
    c = plan.state.cards.get(t.id) if t is not None and t.kind == "card" else None
    return ObjectRef(card=c.id, object_id=plan.oid(c), zone=c.zone) if c is not None else None


def _attack_defended(plan: Plan, kind: str, obj: CardInstance | None) -> str | None:
    """-- defending player (wave 6D) -- an attacking creature's event: its defending player now (508.5)."""
    if kind not in ("attack", "unblocked", "blocked", "blocked_pair") or obj is None:
        return None
    from app.rules import defending

    return defending.defended(plan, obj)


def _fire_generic(plan: Plan, facts: list[Fact], batch: int, fired: Fired,
                  watchers: list[tuple[Watcher, int, int]] | None = None, left: dict[int, str] | None = None) -> None:
    """Each watcher (with the batches it was on the battlefield for: it sees events from when it
    entered, 603.6a, until it left, 603.10a) against each fact of one event. What the ability
    triggered on is captured now, as a TriggerEvent it carries to resolution (603.2, 608.2k)."""
    from app.rules import (
        combat_player_scope43,
        watches,  # -- turn watches (wave 7D) -- "whenever … this turn" delayed triggers (also combat events)
    )

    watches.on_facts(plan, facts, batch, fired)  # (-- turn-long triggers (wave 33A) -- "one or more": once per batch)
    for (watcher, ch, i, d), lo, hi in (watchers if watchers is not None else [(w, -1, -1) for w in _event_watchers(plan)]):
        if batch >= 0 and not (lo <= batch <= hi or (lo, hi) == (-1, -1)):
            continue
        whole = d["cond"]
        for fact in facts:
            fact[4]['batch'] = batch
            # CR 603.6a, 603.10a/c/d: an entrant sees the post-event
            # table, but was absent for look-back events in its entry batch.
            # Conversely, an object leaving in this batch does not see the
            # incoming object's ETB (it still sees simultaneous deaths).
            look_back = fact[0] in ("die", "leave", "sacrifice", "exploit", "leave_graveyard", "unattached", "control_change", "destroyed")  # (destroyed: wave 100A, 603.10a — Karmic Justice's ruling)
            if batch >= 0 and ((look_back and batch == lo) or (not look_back and batch == hi)):
                continue
            if not combat_player_scope43.printed_verdict(plan, whole, watcher, fact,
                    source_oid=(left or {}).get(id(watcher)) or plan.oid(watcher), index=i, name=ch.name):
                continue
            # -- either with a batch half (wave 49D) -- 603.2c: "discards a card or mills one or more cards": the half this event is batches (or not) on its own
            cond = next((x for x in whole["conds"] if _cond_matches(plan, x, watcher, fact, source_oid=(left or {}).get(id(watcher)) or plan.oid(watcher))), whole) if whole["event"] == "either" and (whole.get("counter_union") or any(x.get("aggregate") or (x["event"] == "draw" and x.get("nth")) for x in whole["conds"])) else whole  # (-- trigger other (wave 52B) -- or a half that is "your second card each turn": Trouble in Pairs)
            if cond.get('damage_at_least') is not None:
                from app.rules import trigger_damage_threshold70

                if not trigger_damage_threshold70.matches(cond, fact):
                    continue
            nth = cond.get("nth") if cond["event"] == "draw" else None
            if nth and plan.rules.draws_this_turn.get(fact[3] or "", 0) != nth:
                continue
            if cond["event"] == "draw" and cond.get("nth_max") and plan.rules.draws_this_turn.get(fact[3] or "", 0) > cond["nth_max"]:
                continue  # -- counters (wave 33C) -- "your first or second card each turn"
            if cond.get("not_first_in_draw_step") and fact[4].get("first_in_draw_step"):  # -- triggers (wave 5D) --
                continue
            if cond.get("only_first_in_draw_step") and not fact[4].get("first_in_draw_step"):  # -- hideaway (wave 29D) -- Wiretapping
                continue
            event = _event(plan, fact, batch)
            info = fact[4]
            if cond.get('damaged_by_host104'):
                event.other = info.get('damage_host104')
            if cond.get("blocking110c"):  # -- blocking recipient (wave 110C) -- the blocker, and the defending player (508.5) of the attacker that damaged it
                from app.rules import defending

                event.other = _source_ref(plan, info.get("other_oid"))
                event.defended = defending.defended(plan, fact[1])
            if cond.get('cast_targets102'):
                event.amount = len({(cid, oid) for cid, oid in info.get('targets') or []})
            if cond.get("excess"):  # -- trigger damage (wave 39B) -- 120.10: "that excess damage" / "the excess": the amount of this event is the excess (the batch's total, 603.2c)
                event.amount = int(info.get("excess") or 0)
            if cond["event"] == "you_attack" and cond.get("min_attackers"):  # -- history (wave 22E; review) -- "those creatures", "that many":
                # the attackers the condition counted (508.1, 603.2c)
                counted = _counted_attackers(plan, cond, watcher, info)
                event.objects = [ObjectRef(card=c.id, object_id=plan.oid(c), zone=c.zone) for c in counted]
                event.amount = len(counted)
                if d.get('event_players_from_counted_attackers'):
                    from app.rules.random_choice_receipts import freeze_attacked_players

                    if not freeze_attacked_players(event, counted):
                        continue
            # -- other side (wave 6D) -- "that creature": the one on the other side (app/rules/other_side.py)
            from app.rules import other_side

            if other_side.wanted(cond):
                event = other_side.event(plan, info, event)
                if cond.get("host_mv_le_aura110n"):  # -- (wave 110N) -- Eriette: "that permanent" is the host (as other_side made it); the Aura stays the event's other side
                    event.other = _source_ref(plan, info.get("oid"))
            # One damage event to several recipients at once is one "deals damage" (and several
            # sources at once one "is dealt damage"): once per batch per object, amounts summed
            one_event = cond["event"] == "dealt_damage" or (cond["event"] == "deal_damage" and cond.get("to", "any") == "any")
            # -- counters (wave 7C) -- counters of any kind one instruction put on one permanent: one event (122.6)
            anykind = (cond["event"] == "counters_put" or cond.get("counter_amount")) and not cond.get("counter") and not cond.get("aggregate") \
                and bool(fact[4].get("group"))
            # ("one or more creatures you control attack a player": once for each player attacked, 508.3e)
            per = (info.get("oid") or info.get("recipient") or "") if one_event else \
                info.get("recipient") or info.get("actor") or (info.get("defended") if cond.get("defender") else "") or ""
            if cond.get("to") in ("players", "opponents", "creatures"):  # -- source damage (wave 11F) -- 603.2c: one per batch
                per = (info.get("oid") or "") if cond.get("subject") == "source" else ""  # (wave 39B: "a source …": each source of the batch, 603.2c)
            if cond["event"] == "mill" and cond.get("aggregate") and cond.get("player") == "any":
                per = ""  # -- triggers (wave 17D) -- "one or more cards are milled": every player's cards of the batch are one event (603.2c)
            if cond.get("batch110m"):
                per = ""  # -- (wave 110M) -- "one or more of your opponents are dealt combat damage": all of the batch's recipients are one event (603.2c)
            if cond.get("all_players"):
                per = ""  # -- trigger other (wave 36A) -- "one or more players sacrifice one or more creatures": every player's part of the batch is one event (603.2c)
            if cond["event"] == "lose_life" and cond.get("aggregate"):
                per = ""  # -- life floor (wave 35C) -- "one or more opponents lose life": every player's loss of the batch is one event (603.2c)
            if cond.get("subject") == "source":  # "that source's controller" is the event's player
                event.players = [fact[3]] if fact[3] else []
            if d.get('event_players_from_damage_recipient'):
                event.players = [info['recipient']] if info.get('recipient') else []
            if cond.get("cause") == "opponent" and info.get("by"):  # -- discard causes (wave 50E) -- "that player loses 5 life" (Psychic Purge): the opponent whose spell or ability did it, not the discarder
                event.players = [info["by"]]
            if anykind:  # (its steps are in batches of their own: keyed by the instruction, not the batch)
                per, batch_key = f"{info.get('oid') or fact[3]}:{info['group']}", 0
            else:
                batch_key = batch
            if cond["event"] == "lose_life" and cond.get("aggregate") and info.get("life_operation"):
                batch_key, per = 0, f"life_operation:{info['life_operation']}"
            if cond.get("aggregate") or one_event or anykind:  # "one or more …": once per event batch (603.2c) …
                # (… and per player dealt the damage: "one or more creatures deal combat damage to a player")
                key = (watcher.id, i, batch_key, per)
                pending = fired.get(key)
                if pending is not None and pending.event is not None:  # the batch's other objects join it
                    if anykind:
                        pending.event.counter_placements += event.counter_placements
                        if cond.get("counter_amount"):
                            pending.event.amount += event.amount
                        from app.rules import trigger_multipliers

                        trigger_multipliers.joined(plan, pending)
                        continue
                    if not one_event:
                        pending.event.objects += event.objects
                        pending.event.new_objects += event.new_objects
                    if one_event and pending.event.attacking_player != event.attacking_player:
                        pending.event.attacking_player = None  # Mixed/legacy knowledge cannot establish an attacking player.
                    pending.event.amount += event.amount
                    pending.event.count += 1
                    if cond.get("to") in ("opponents", "players"):  # -- trigger other (wave 52B) -- the players the batch dealt damage to (603.2c): "for each opponent dealt damage"
                        pending.event.players += [p for p in event.players if p not in pending.event.players]
                    from app.rules import trigger_multipliers  # -- trigger multipliers (wave 5D) --

                    trigger_multipliers.joined(plan, pending)
                    continue
            # -- sagas & attached-object triggers (wave 3S): a watcher that has left since is the object it
            # was (603.10a: "this Aura" reads its last known information, 608.2h), not the card's new object
            source_object = (left or {}).get(id(watcher)) or plan.oid(watcher)
            d = _aura_card_bound(plan, d, (left or {}).get(id(watcher)))
            added = None
            repetitions = event.amount if cond.get("per_counter") else 1
            for _ in range(repetitions):
                added = _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=source_object,
                             name=ch.name, index=i, definition=d,
                             event=event.model_copy(update={"amount": 1}) if cond.get("per_counter") else event)
            if (cond.get("aggregate") or one_event or anykind) and added is not None:
                fired[(watcher.id, i, batch_key, per)] = added


def _generic_events(plan: Plan, events: list[Event]) -> None:
    """Generic "When/Whenever [subject] [event]" conditions against the event log."""
    from app.rules import trigger_damage_threshold70

    r = plan.rules
    from app.rules import first_event_receipts78

    first_batches78: dict[str, tuple[int, bool | None]] = {}
    simultaneous_damage = trigger_damage_threshold70.amounts(events)
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
    window: dict[str, Any] = {"cast_from": {}, "played_lands": {e.object_id for e in events if e.kind == "land_played" and not e.manual}}
    for e in events:
        if e.kind == "designation" and e.counter == "control" and not e.manual and e.card in plan.state.cards and e.from_zone in plan.live():
            card = plan.state.cards[e.card]  # -- control events (wave 45C) -- 603.10d: "an opponent gains control of … from you" looks back in time, so the
            if card.zone.endswith(":battlefield") and plan.oid(card) == e.object_id and not plan.manual(card):  # permanent's own abilities
                ch = plan.ch(card)  # (Zidane taken by an opponent) are its old controller's, as it was before the event
                watchers += [((card.model_copy(update={"controller": e.from_zone}), ch, i, d), -big, big) for i, d in abilities(plan, ch, "event")
                             if d.get("cond", {}).get("event") == "control_change"]
        if e.kind == "plotted" and not e.manual and e.card in plan.state.cards:  # -- (wave 110B) -- "When this card becomes plotted": from exile (603.6)
            card = plan.state.cards[e.card]
            if not plan.manual(card) and card.owner in plan.live():
                ch = plan.ch(card)
                watchers += [((card, ch, i, d), -big, big) for i, d in abilities(plan, ch, "event")
                             if d.get("cond", {}).get("event") == "plotted" and d["cond"].get("subject") == "self"]
        if e.kind == "zone_change" and not e.manual and _zone(e.from_zone) == "graveyard" and _zone(e.to_zone) == "hand" and e.card in plan.state.cards:
            card = plan.state.cards[e.card]  # -- (wave 110G) -- "When this card is put into your hand from your graveyard": triggers from the hand (603.6)
            if not plan.manual(card) and card.owner in plan.live():
                ch = plan.ch(card)
                watchers += [((card, ch, i, d), -big, big) for i, d in abilities(plan, ch, "event")
                             if d.get("cond", {}).get("event") == "gy_to_hand110g" and d["cond"].get("subject") == "self"]
        if e.kind == "cycled" and not e.manual and e.card in plan.state.cards:
            # 702.29c: "When you cycle ~" triggers from whatever zone the card went to
            card = plan.state.cards[e.card]
            if not plan.manual(card) and card.owner in plan.live():
                ch = plan.ch(card)
                watchers += [((card, ch, i, d), -big, big) for i, d in abilities(plan, ch, "event")
                             if d.get("cond", {}).get("event") == "cycle" and d["cond"].get("subject") == "self"]
        if e.kind == "zone_change" and not e.manual and _zone(e.from_zone) == "hand" and e.card in plan.state.cards and (
                _zone(e.to_zone) == "graveyard" or (_zone(e.to_zone) == "exile" and _discarded_instead(plan, e))):  # (review 23D: or exiled instead)
            card = plan.state.cards[e.card]  # -- discard causes (wave 23D) -- "When a spell or ability an opponent controls causes you to
            if not plan.manual(card) and card.owner in plan.live():  # discard this card": it is in the graveyard by now (701.9a)
                ch = plan.ch(card)
                watchers += [((card, ch, i, d), -big, big) for i, d in abilities(plan, ch, "event")
                             if d.get("cond", {}).get("event") == "discard" and d["cond"].get("subject") == "self"]
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
                         for i, d in abilities(plan, ch, "event") if d.get("cond") and not arrives_in_graveyard(d) and not gy_sees_others(d)]
    # (-- graveyard triggers (wave 19C) -- an ability of a card in the graveyard about another object's leaving sees the events after the
    # card got there: not the one that put it there (603.10a: before it, it wasn't in the graveyard), nor its own death as a permanent)
    watchers += [(w, entered.get(plan.oid(w[0]), -big) + (1 if gy_sees_others(w[3]) else 0), big) for w in _event_watchers(plan)]
    for e in events:
        if e.manual:
            continue
        if e.kind == "drew" and e.player:
            r.draws_this_turn[e.player] = r.draws_this_turn.get(e.player, 0) + 1
        if e.kind == "player_lost_game":
            from app.rules import life_game_history

            frozen_watchers: list[tuple[Watcher, int, int]] = []
            frozen_left: dict[int, str] = {}
            for snap in e.loss_watchers:
                if snap.controller not in plan.live():
                    continue  # 800.4d: a departed player cannot put triggers on the stack.
                loss_card, loss_ch = _snapshot_card(plan, snap)
                frozen_left[id(loss_card)] = snap.object_id
                frozen_watchers.extend(((loss_card, loss_ch, i, d), -big, big)
                                       for i, d in abilities(plan, loss_ch, "event")
                                       if life_game_history._loss_condition(d.get("cond", {})))
            _fire_generic(plan, [("lose_game", None, None, e.player, {'turn_start_life':e.turn_start_life})], e.batch, fired,
                          watchers=frozen_watchers, left=frozen_left)
            continue
        facts = _facts(plan, e, window)
        first_event_receipts78.annotate(plan, facts, e.batch, first_batches78)
        from app.rules import first_crew_saddle80

        first_crew_saddle80.annotate(plan, facts)
        for fact in facts:
            if fact[0] == 'dealt_damage' and fact[4].get('oid'):
                fact[4]['simultaneous_amount'] = simultaneous_damage.get((e.batch, fact[4]['oid']), 0)
        for f in facts:
            if f[0] in ("discard", "dealt_damage", "deal_combat_damage_player", "counters_put"):
                f[4]["batch"] = e.batch  # -- trigger other (wave 36A) -- the event batch, for "for the first time each turn" (_first_discard; wave 39B: _first_of)
        for f in facts:  # -- this-turn state (wave 42B) -- 603.2: "a creature becomes tapped for the first time each turn", kept per object per turn (400.7: a new object
            if f[0] == "tapped" and f[4].get("oid"):  # is untapped and has not become tapped yet) whoever watches, so an ability that began mid-turn counts earlier taps
                key = f"tapped:{f[4]['oid']}"
                f[4]["first"] = r.once_per_turn.get(key) != plan.state.turn.number
                r.once_per_turn[key] = plan.state.turn.number
        for f in facts:  # -- trigger qualifiers (wave 11C) -- 603.2: "for the first time each turn", kept per player whoever watches
            if f[0] in _FIRST_KINDS and f[3] and int(f[4].get("amount") or 0) > 0:
                key = f"first:{f[0]}:{f[3]}"
                f[4]["first"] = r.once_per_turn.get(key) != plan.state.turn.number
                r.once_per_turn[key] = plan.state.turn.number
        if e.kind == "drew" and e.player and facts:  # -- triggers (wave 5D) -- the first card a player draws in
            # their own draw step (504.1), kept per player per turn (they have one draw step a turn)
            first = plan.state.turn.phase == "draw" and e.player == plan.active and \
                r.once_per_turn.get(f"drawstep:{e.player}") != plan.state.turn.number
            if first:
                r.once_per_turn[f"drawstep:{e.player}"] = plan.state.turn.number
            facts[0][4]["first_in_draw_step"] = first
        if facts:
            _fire_generic(plan, facts, e.batch, fired, watchers, left)


def generic_combat(plan: Plan, event: str, cards: list[CardInstance],
                   pairs: list[tuple[CardInstance, CardInstance]] = ()) -> None:  # type: ignore[assignment]
    """"Whenever [creature] attacks / blocks / becomes blocked", "Whenever you attack" (508.3a,
    509.3a/c): one fact per creature; "you attack" once per combat for the attacking player.
    ``pairs`` (this creature, the creature on the other side): "blocks a creature" / "becomes
    blocked by a creature" trigger once for each (509.3b, 509.3d)."""
    if not cards and not pairs:  # (110E: a creature put onto the battlefield blocking, 509.3d)
        return
    fired: Fired = {}
    attacking = [c.id for c in cards]
    turn = plan.state.turn.number
    facts: list[Fact] = []
    for c in cards:
        info: dict[str, Any] = {"oid": plan.oid(c), "attackers": len(cards), "attacking": attacking, "amount": 1}  # (amount: wave 17D, "that many")
        if event in ("attack", "unblocked"):  # whom it attacks (508.3a, 509.3g)
            info["defended"], info["direct"] = _defended(plan, c)
            if c.attacking is not None and c.attacking.kind != "player" and (t := plan.state.cards.get(c.attacking.id)) is not None \
                    and "Battle" in plan.ch(t).types:
                info["battle"] = True  # -- review 34 -- 310.5: an attack on a battle (attacks neither a player nor a planeswalker)
        if event == "blocked":  # -- block events (wave 53C) -- 509.3c: how many creatures were declared as blockers for it ("becomes blocked by two or more creatures")
            info["blockers"] = sum(1 for o in plan.state.cards.values() if o.blocks(c.id))
        if event == "block":  # -- trigger lines (wave 100A) -- 509.3e: how many creatures it blocks ("blocks two or more creatures")
            info["blocked"] = (1 if c.blocking else 0) + len(c.blocking_more)
        if event == "attack":  # "attacks for the first time each turn" (kept per object per turn)
            key = f"attacked:{info['oid']}"
            info["first"] = plan.rules.once_per_turn.get(key) != turn
            plan.rules.once_per_turn[key] = turn
        facts.append((event, c, plan.ch(c), c.controller, info))
    if event == "attack":  # 506.5 / 508.3d: how many creatures were declared as attackers
        facts.append(("you_attack", None, None, cards[0].controller, {"attackers": len(cards), "attacking": attacking,
                                                                       "defended_direct": sorted({d for d, direct in (_defended(plan, c) for c in cards) if d and direct})}))  # (wave 27B: "one or more of your opponents")
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
        for c in cards:  # -- trigger lines (wave 110F) -- 508.3a: "attacks a planeswalker you control": once for each planeswalker attacked
            # 603.2c: an ability can trigger repeatedly if one event (one attack declaration) contains multiple occurrences, so one fact per planeswalker.
            pw = plan.state.cards.get(c.attacking.id) if c.attacking is not None and c.attacking.kind != "player" else None
            if pw is not None and "Planeswalker" in plan.ch(pw).types and not any(f[4].get("pw") == pw.id for f in facts):
                ids = [x.id for x in cards if x.attacking is not None and x.attacking.id == pw.id]
                facts.append(("you_attack", None, None, cards[0].controller, {"defended": pw.controller, "attacker": cards[0].controller, "direct": False,
                                                                               "attackers": len(ids), "attacking": ids, "attacking_direct": [], "pw": pw.id}))
        for defended, g in groups.items():
            facts.append(("you_attack", None, None, cards[0].controller,
                          {"defended": defended, "attacker": cards[0].controller, "direct": bool(g["direct"]), "attackers": len(g["all"]),
                           "attacking": g["all"], "attacking_direct": g["direct"]}))
    facts += [(_PAIRED[event], c, plan.ch(c), c.controller, {"oid": plan.oid(c), "other": other.id,
                                                              "other_oid": plan.oid(other)})  # (other_oid: wave 6D)
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
        if card.zone.endswith(":command") and not designations.emblem_card(card):  # (wave 25B: eminence; an emblem's own abilities are read below)
            out += command_zone_abilities(plan, card, trigger)
            continue
        if card.zone.endswith(":exile"):  # -- keywords (wave 50H) -- 702.55c: "When the creature it haunts dies" functions in exile
            if trigger == "event" and plan.in_game(card) and not plan.manual(card):
                ch = plan.ch(card)
                out += [(card, ch, i, d) for i, d in abilities(plan, ch, trigger)
                        if ((d.get("cond") or {}).get("subject") == "haunted" and plan.oid(card) in plan.rules.haunting) or (d.get("cond") or {}).get("exiled") or d.get("ex110b")]  # (wave 110B: Senu works from exile, 113.6k)
            continue
        if card.zone.endswith(":phased"):  # -- phase out (wave 110B) -- 702.26d: a phased-out permanent's "Whenever ~ phases out" still triggers (looks back at the shift)
            if trigger == "event" and plan.in_game(card) and not plan.manual(card):
                ch = plan.ch(card)
                out += [(card, ch, i, d) for i, d in abilities(plan, ch, trigger) if (d.get("cond") or {}).get("event") == "phase_out"]
            continue
        if not (card.zone.endswith(":battlefield") or designations.emblem_card(card)) or not plan.in_game(card) or plan.manual(card):
            continue  # (-- emblems (wave 13A) -- 114.4: an emblem's triggered abilities work from the command zone)
        ch = plan.ch(card)
        out += [(card, ch, i, d) for i, d in abilities(plan, ch, trigger) if not graveyard_ability(d) or d.get("gy_bf110b")]  # (-- wave 110B -- Quakebringer: also from the battlefield)
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

    # (-- graveyard triggers (wave 19C) -- "At the beginning of your upkeep, if this card is in your graveyard, …": it works there only)
    # (-- multi (wave 100M) -- 113.6m: "you may exile this card from your graveyard" moves it out of the graveyard: Kozilek's Return)
    s = json.dumps(d, default=str)
    return '"self_gy"' in s or '"Exile this card from your graveyard"' in s or arrives_in_graveyard(d) or d.get("if") == IN_GRAVEYARD or bool(d.get("gy_bf110b"))


IN_GRAVEYARD = {"object": "self", "test": "in_graveyard"}
# -- trigger other (wave 25B) -- eminence: "if ~ is in the command zone or on the battlefield" names the zones it functions in (113.6b)
COMMAND_OR_BATTLEFIELD = {"object": "self", "test": "command_or_battlefield"}
# -- trailing & intervening ifs (wave 38A) -- "At the beginning of your upkeep, if Oloro is in the command zone, you gain 2 life.": the zone it functions in, 113.6b
COMMAND_IFS = (COMMAND_OR_BATTLEFIELD, {"object": "self", "test": "in_command"})


def command_zone_abilities(plan: Plan, card: CardInstance, trigger: str) -> list[tuple[CardInstance, Characteristics, int, dict[str, Any]]]:
    """The eminence abilities of a card in the command zone (not an emblem: 114.4) for this trigger."""
    if not card.zone.endswith(":command") or designations.emblem_card(card) or not plan.in_game(card) or plan.manual(card):
        return []
    ch = plan.ch(card)
    return [(card, ch, i, d) for i, d in abilities(plan, ch, trigger) if d.get("if") in COMMAND_IFS]
_GY_OTHERS = ("die", "leave", "sacrifice", "leave_graveyard")
_SELFISH = ("self", "self_or", "host", "self_or_host")


def gy_sees_others(d: dict[str, Any]) -> bool:
    """-- graveyard triggers (wave 19C) -- a graveyard ability about *another* object leaving the battlefield or a graveyard ("Whenever a
    creature you control dies while this card is in your graveyard", "Whenever another creature is put into your graveyard from the
    battlefield, … return this card from your graveyard …"; recover): not the card's own leaving, and it works from the graveyard only."""
    cond = d.get("cond") or {}
    return bool(d.get("gy_watch")) or (graveyard_ability(d) and cond.get("event") in _GY_OTHERS and cond.get("subject") not in _SELFISH)


def arrives_in_graveyard(d: dict[str, Any]) -> bool:
    """-- trigger tail (wave 15B) -- "When ~ is put into a graveyard from anywhere" (603.6c: never a leaves-the-battlefield
    ability): it triggers on the card's new object in the graveyard, and works only from there."""
    cond = d.get("cond") or {}
    return cond.get("event") == "to_graveyard" and cond.get("subject") == "self"


def graveyard_abilities(plan: Plan, card: CardInstance, trigger: str,
                        ) -> list[tuple[CardInstance, Characteristics, int, dict[str, Any]]]:
    if card.owner not in plan.live() or plan.manual(card) or not card.zone.endswith(":graveyard"):
        return []
    ch = plan.ch(card)
    if "graveyard" not in (ch.oracle_text or ""):
        return []
    return [(card, ch, i, d) for i, d in abilities(plan, ch, trigger) if graveyard_ability(d) and graveyard_trigger_ok(d)]


_GY_TRIGGERS = ("event", "landfall", "enters_other", "cast_you", "upkeep_you", "end_step_you")
_GY_LOOK_BACK = ("die", "leave", "sacrifice", "leave_graveyard", "multi",  # (603.10a; "multi": not judged here)
                 "either")  # (-- triggers (wave 5D) -- nor "either": one of its events may look back)


def graveyard_trigger_ok(d: dict[str, Any]) -> bool:
    """Is this graveyard ability's trigger one the graveyard watchers above read? Not a look-back
    event (603.10a: a card arriving in the graveyard with the event would have to be told apart),
    nor one about this object or the permanent it was attached to (they left the battlefield)."""
    trigger = str(d.get("trigger"))
    if gy_sees_others(d):  # -- casting extras (wave 18E) -- recover 702.59a: the card is already in the graveyard when the creature dies (no look-back)
        return d.get("kind") == "triggered"  # (wave 19C: and the other graveyard abilities about another object's leaving)
    if d.get("kind") != "triggered" or not (trigger in _GY_TRIGGERS or trigger.startswith("step:")):
        return False
    cond = d.get("cond") or {}
    if trigger == "event" and cond.get("event") == "either":
        return bool(cond.get("conds")) and all(graveyard_trigger_ok({**d, "cond": child}) for child in cond["conds"])
    return trigger != "event" or (cond.get("event") not in _GY_LOOK_BACK
                                  and cond.get("subject") not in ("self", "self_or", "host", "self_or_host")) \
        or arrives_in_graveyard(d)


def _other_enters(plan: Plan, entered: CardInstance, ech: Characteristics, oid: str, batch: int = 0) -> None:
    """603.6a: "Whenever [another] creature [you control] enters" on every permanent, including
    ones entering at the same time."""
    if ech.is_land:  # "Landfall — Whenever a land you control enters"
        for watcher, ch, i, d in _watchers(plan, "landfall"):
            if entered.controller == watcher.controller:
                _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=plan.oid(watcher),
                     name=ch.name, index=i, definition=d, event=_entered(plan, entered, oid, batch))
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
             index=i, definition=d, event=_entered(plan, entered, oid, batch))


CAST_FILTERS = {
    "a spell": lambda ch: True,
    "a creature spell": lambda ch: ch.is_creature,
    "a noncreature spell": lambda ch: not ch.is_creature,
    "an instant or sorcery spell": lambda ch: ch.is_instant_or_sorcery,
    "an artifact spell": lambda ch: "Artifact" in ch.types,
    "an enchantment spell": lambda ch: "Enchantment" in ch.types,
}


def _cast_triggers(plan: Plan, spell_id: str, caster: str, batch: int = 0) -> None:
    spell = plan.state.cards.get(spell_id)
    if spell is None:
        return
    sch = plan.ch(spell)
    # -- trigger multipliers (wave 5D) -- what it triggered on (603.2d "you casting … causes")
    cast = TriggerEvent(kind="cast", batch=batch, count=1, players=[caster],
                        objects=[ObjectRef(card=spell.id, object_id=plan.oid(spell), zone=spell.zone)])
    # -- cast triggers (wave 6D) -- "When you cast this spell, …": the spell's own ability, from the stack (601.2i;
    # a copy isn't cast, 707.10: no spell_cast event)
    if not plan.manual(spell) and spell.zone == "stack" and spell.controller == caster:
        for i, d in abilities(plan, sch, "cast_self"):
            if d.get("while") is not None:  # -- retarget (wave 100O); multi (wave 100N) -- "When you cast this spell while you control your commander": judged as it triggers only
                from app.rules import conditions

                if not conditions.holds(plan, {"controller": caster, "source_card": spell.id, "source_object": plan.oid(spell)}, d["while"]):
                    continue
            if d.get("cast_hand103"):
                receipt = plan.rules.payments.get(plan.oid(spell))
                if receipt is None or receipt.cast_from != "hand" or receipt.cast_from_player != caster:
                    continue
            if d.get("cast_initial103") is not None:
                from app.rules import conditions

                if not conditions.holds(plan, {"controller": caster, "source_card": spell.id, "source_object": plan.oid(spell)}, d["cast_initial103"]):
                    continue
            _add(plan, controller=caster, source_card=spell.id, source_object=plan.oid(spell), name=sch.name, index=i,
                 definition=d, event=cast.model_copy(deep=True))
    from app.rules import mana_units

    mana_units.cast_triggers(plan, spell, caster, cast)  # -- mana provenance (wave 18B) -- 106.6: "When that mana is spent to cast …"
    for watcher, ch, i, d in _watchers(plan, "cast_you"):
        if watcher.controller == caster and CAST_FILTERS[d.get("filter", "a spell")](sch):
            _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=plan.oid(watcher), name=ch.name,
                 index=i, definition=d, cause=cast)


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
        if card.zone.endswith(":command") and not designations.emblem_card(card) and card.controller == plan.active:  # (-- wave 25B -- eminence)
            for _, ch, i, d in command_zone_abilities(plan, card, trigger):
                _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i, definition=d)
            continue
        if not (card.zone.endswith(":battlefield") or designations.emblem_card(card)) or card.controller != plan.active or plan.manual(card):
            continue
        ch = plan.ch(card)
        for i, d in abilities(plan, ch, trigger):
            if graveyard_ability(d) and not d.get("gy_bf110b"):  # (-- wave 110B --)
                continue  # (113.6m: it functions only in the graveyard)
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i,
                 definition=d)


def at_step_generic(plan: Plan) -> None:
    """"At the beginning of [whose] [step]" (503.1a, 504, 505, 507, 513): every permanent's
    abilities for this step, when it's the right player's step."""
    phase = plan.state.turn.phase
    prefix = f"step:{phase}:"
    prefixes = (prefix, "step:main:") if phase in ("main1", "main2") else (prefix,)  # -- trigger other (wave 52B) -- "each of your main phases" (Frontier Siege)
    ap = plan.active
    for card in list(plan.state.cards.values()):
        gy = card.zone.endswith(":graveyard")  # -- refused zones/sized (wave 3R4) -- (113.6m)
        cz = card.zone.endswith(":command") and not designations.emblem_card(card)  # (-- trigger other (wave 25B) -- eminence, 113.6b)
        exiled = card.zone.endswith(":exile")
        if exiled and card.owner in plan.live() and not plan.manual(card) or gy and card.owner in plan.live() and not plan.manual(card) and "graveyard" in (plan.ch(card).oracle_text or "") or cz and plan.in_game(card) and not plan.manual(card) and card.controller in plan.live():
            pass
        elif not (card.zone.endswith(":battlefield") or designations.emblem_card(card)) or plan.manual(card) or card.controller not in plan.live():
            continue
        ch = plan.ch(card)
        for i, d in scripts.definitions(ch).items():
            if d["kind"] != "triggered" or not str(d["trigger"]).removeprefix("multi:").split("+")[-1].startswith(prefixes):  # (-- wave 110B -- a "multi:" ability may end in a step half)
                continue
            if bool(d.get("exiled_step")) != exiled:
                continue
            if graveyard_ability(d) != gy or (cz and d.get("if") not in COMMAND_IFS):
                continue
            if d.get("first_step") and plan.rules.step_counts.get(phase, 0) != 1:
                continue
            if _whose_step(plan, card, d["trigger"].rsplit(":", 1)[-1], ap):
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
    if whose in ("each", "any"):  # (wave 31D: "any": "At end of combat", every turn's, no player is named)
        return True
    if whose == "monarch":
        return plan.state.table.monarch == ap
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


# -- keywords (wave 43C) -- the cost a keyword line names (echo 702.30a, cumulative upkeep 702.24a, ward 702.21a). Plain mana; or "Echo—Discard a card." /
# "Cumulative upkeep—Sacrifice a creature." / "Ward—Get five poison counters.": a cost the optional payment engine pays (optional_payment.cost_text), or
# ("do") a sentence of always-payable instructions the grammar reads ("Draw a card.", "Add {R}.", "You get five poison counters."). A cost that names a
# choice the engine can't make for the payer (a creature of an opponent's, a graveyard) is None: the card stays manual.
_DO_PAYABLE = frozenset({"draw", "add_mana", "player_counter"})  # (118.3: nothing to run out of; a draw from an empty library is still paid, ruling on Psychic Vortex 2008-04-01)
_DO_OPPONENT = frozenset({"gain_life", "create_token"})  # ("An opponent gains 1 life.", "Have an opponent create a 1/1 red Survivor creature token.": an opponent can always be given them)


def _phrase(text: str) -> str:
    return text[:1].lower() + text[1:]


def effect_cost(phrase: str) -> list[dict[str, Any]] | None:
    """The instructions of an always-payable cost written as a sentence ("Draw a card", "Add {R}", "Get five poison counters"; with "an opponent" it
    is chosen when the cost is paid: choose_opponent), or None."""
    sentence = _phrase(phrase.strip().rstrip("."))
    opponent = False
    if m := re.fullmatch(r"an opponent gains (.+)", sentence):  # (read as "you gain …" and aimed at the opponent chosen)
        sentence, opponent = f"you gain {m[1]}", True
    elif m := re.fullmatch(r"have an opponent (create .+)", sentence):
        sentence, opponent = m[1], True
    found = scripts.parse_effects(("You " + sentence if sentence.startswith("get ") else sentence[:1].upper() + sentence[1:]) + ".")
    if found is None or found[1] is not None or found[2] or not found[0]:
        return None
    if opponent:
        if any(e["do"] not in _DO_OPPONENT or e.get("who") != "you" for e in found[0]):
            return None
        return [{"do": "choose_opponent", "as": "copp"}, *({**e, "who": "ref:copp"} for e in found[0])]
    return found[0] if all(e["do"] in _DO_PAYABLE for e in found[0]) else None


def keyword_cost(line: str, word: str) -> tuple[str, Any] | None:
    """The cost of an echo / cumulative upkeep keyword line as ("mana", "{1}{G}"), ("cost", cost text) or ("do", instructions), or None
    when it is none of those (CR 702.30a, 702.24a)."""
    text = re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")
    if (m := re.fullmatch(rf"{word} (?P<cost>(?:\{{[^}}]+\}})+)", text, re.IGNORECASE)) is not None:
        return "mana", m["cost"]
    if word == "cumulative upkeep" and (m := re.fullmatch(r"cumulative upkeep \{([WUBRG])\} or \{([WUBRG])\}", text, re.IGNORECASE)) is not None:
        return "mana", f"{{{m[1].upper()}/{m[2].upper()}}}"  # "{G} or {W}" for each age counter is that many {G/W}: each one paid with either
    if (m := re.fullmatch(rf"{word}—(?P<phrase>.+)", text, re.IGNORECASE)) is None:
        return None
    from app.rules import optional_payment

    if word == "cumulative upkeep" and m["phrase"] == "Put two cards from a single graveyard on the bottom of their owner's library":  # -- wave 110G -- Jötun Grunt
        return "gy_pairs110g", None
    if (cost := optional_payment.cost_text(_phrase(m["phrase"]))) is not None:
        return "cost", cost
    done = effect_cost(m["phrase"]) if word == "cumulative upkeep" else None  # (no echo cost is an instruction: not read)
    return ("do", done) if done is not None else None


def echo_cost(ch: Any) -> tuple[str, Any] | None:
    for ab in ch.abilities:
        if ab.kind == "keywords" and "echo" in ab.keywords:
            return keyword_cost(ab.text, "echo")
    from app.rules import wave110c_misc  # -- echo {X}, X your life total (wave 110C) --

    return wave110c_misc.echo_cost(ch)


def cumulative_costs(ch: Any) -> list[tuple[str, Any]]:
    """The cost of each cumulative upkeep ability the object has (702.24b: each instance triggers on its own)."""
    return [c for ab in ch.abilities if ab.kind == "keywords" and "cumulative upkeep" in ab.keywords
            if (c := keyword_cost(ab.text, "cumulative upkeep")) is not None]


def pay_or_else(ask: str, payer: str, paid: list[dict[str, Any]], otherwise: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """-- keywords (wave 43C) -- 118.12a: "[do something] unless [a player does something else]" for a cost that is an instruction: ``payer``
    is asked (privately), the ``paid`` instructions are the payment, ``otherwise`` happens if they decline."""
    return [{"do": "optional_payment", "who": payer, "ask": ask, "bind": "pay0"},
            *([{"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": len(otherwise)}, *otherwise] if otherwise else []),
            {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": len(paid)}, *paid]


def _cumulative_upkeep(plan: Plan) -> None:
    """702.24a: "At the beginning of your upkeep, if this permanent is on the battlefield, put an
    age counter on it. Then you may pay [cost] for each age counter on it. If you don't, sacrifice it." (-- keywords (wave 43C) -- a
    cost that isn't mana is paid once for each age counter, all at once, 118.3: no partial payment; 702.24b: every instance counts all
    of the age counters)"""
    age = {"counters": "age", "on": "self"}
    sacrifice = [{"do": "sacrifice", "who": "self"}]
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or card.controller != plan.active or plan.manual(card):
            continue
        ch = plan.ch(card)
        for k, (kind, cost) in enumerate(cumulative_costs(ch)):
            if kind == "mana":
                pay = [{"do": "pay_or_sacrifice", "cost": cost, "per": "age"}]
            elif kind == "gy_pairs110g":  # -- wave 110G -- 702.24a: the cost once for each age counter, all or nothing (118.3)
                pay = [{"do": "gy_pairs110g", "n": age, "bind": "pay0"}, {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1}, *sacrifice]
            elif kind == "cost":
                pay = [{"do": "optional_payment", "who": "you", "cost": cost, "times": age, "bind": "pay0"},
                       {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1}, *sacrifice]
            else:  # ("Draw a card.": once for each age counter, as the cost)
                pay = pay_or_else("pay its cumulative upkeep (once for each age counter)", "you",
                                  [{"do": "repeat", "n": age, "span": len(cost)}, *cost], sacrifice)
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=5100 + k, definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                                             "effects": [{"do": "add_counters", "who": "self", "kind": "age", "n": 1}, *pay,
                                                         {"do": "paid_cumulative110j"}]})  # -- cumulative upkeep paid (wave 110J) --


def _rebound(plan: Plan) -> None:
    """702.88a: "At the beginning of your next upkeep, you may cast this card from exile without
    paying its mana cost." """
    for cid in list(plan.rules.rebounding):
        card = plan.state.cards.get(cid)
        expected = plan.rules.rebound_objects.get(cid)
        if card is None or (expected is not None and plan.oid(card) != expected):
            plan.rules.rebounding = [c for c in plan.rules.rebounding if c != cid]
            plan.rules.rebound_objects.pop(cid, None)
            plan.rules.rebound_controllers.pop(cid, None)
            continue
        controller = plan.rules.rebound_controllers.get(cid, card.owner)
        if not card.zone.endswith(":exile") or controller != plan.active:
            continue
        plan.rules.rebounding = [c for c in plan.rules.rebounding if c != cid]
        plan.rules.rebound_objects.pop(cid, None)
        plan.rules.rebound_controllers.pop(cid, None)
        _add(plan, controller=controller, source_card=cid, source_object=plan.oid(card), name=card.name, index=5200,
             definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                         "effects": [{"do": "free_cast_offer", "card": cid, "object": plan.oid(card)}]})


def _suspend(plan: Plan) -> None:
    """702.62b: "At the beginning of your upkeep, if this card is suspended, remove a time counter
    from it." (A triggered ability of the exiled card itself.)"""
    from app.rules import suspend_grants

    for card in list(plan.state.cards.values()):
        if card.zone != f"{plan.active}:exile" or card.owner != plan.active or not suspend_grants.is_suspended(plan, card):
            continue
        if card.id not in plan.rules.suspended:
            plan.rules.suspended.append(card.id)
        _add(plan, controller=card.owner, source_card=card.id, source_object=plan.oid(card), name=card.name,
             index=5000, definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                                     "effects": [{"do": "suspend_tick", "card": card.id}]})


def paradigm_trigger(plan: Plan, card: CardInstance, controller: str, definition: dict[str, Any]) -> None:
    """-- keywords (wave 50H) -- 702.192a: the delayed trigger of a paradigm card in exile (app/rules/paradigm.py)."""
    _add(plan, controller=controller, source_card=card.id, source_object=plan.oid(card), name=card.name, index=5003, definition=definition,
         event=_entered(plan, card, plan.oid(card)))  # (the card in exile is the event's object: "the copy" is made of it)


def haunt_spell(plan: Plan, card: CardInstance, controller: str, definition: dict[str, Any]) -> None:
    """-- keywords (wave 50H) -- 702.55a: the haunt trigger of an instant or sorcery that resolved (app/rules/haunt.py): its controller is the spell's."""
    _add(plan, controller=controller, source_card=card.id, source_object=plan.oid(card), name=card.name, index=5002, definition=definition)


def exile_watch(plan: Plan, card: CardInstance) -> bool:
    """-- keywords (wave 50H) -- does the card have an ability of its own that functions in exile ("Whenever a time counter is removed from this card while it's exiled")?"""
    return any((d.get("cond") or {}).get("exiled") for _, d in abilities(plan, plan.ch(card), "event"))


def suspend_last(plan: Plan, card: CardInstance) -> None:
    """-- keywords (wave 50H) -- 702.62a: "When the last time counter is removed from this card, if it's exiled, you may play it without paying its mana cost": a triggered ability of its own."""
    if card.id not in plan.rules.suspended:
        plan.rules.suspended.append(card.id)
    _add(plan, controller=card.owner, source_card=card.id, source_object=plan.oid(card), name=card.name,
         index=5001, definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None,
                                 "effects": [{"do": "suspend_cast", "card": card.id, "object": plan.oid(card)}]})


def _echo(plan: Plan) -> None:
    """702.30a echo: "At the beginning of your upkeep, if this permanent came under your control
    since the beginning of your last upkeep, sacrifice it unless you pay [cost]." Each permanent
    gets this once per controller (a new object, or a new controller, is due again)."""
    r = plan.rules
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or card.controller != plan.active or plan.manual(card):
            continue
        ch = plan.ch(card)
        found = echo_cost(ch)
        key = f"{plan.oid(card)}:{card.controller}"
        if found is None or key in r.echo_done:
            continue
        # -- keywords (wave 43C) -- 702.30a: it came under THIS player's control since their last upkeep: the other controllers' marks go (a permanent
        # that comes back to a former controller owes the echo again), and "Echo—Discard a card." is an optional payment of that cost (118.12a)
        r.echo_done[:] = [k for k in r.echo_done if not k.startswith(f"{plan.oid(card)}:")]
        r.echo_done.append(key)
        kind, cost = found
        effects = [{"do": "pay_or_sacrifice", "cost": cost, "echo_paid76": True}] if kind == "mana" else [
            {"do": "optional_payment", "who": "you", "cost": cost, "bind": "pay0"},
            {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1}, {"do": "sacrifice", "who": "self"}]
        if kind != 'mana':
            effects += [{'do': 'only_if', 'cond': {'succeeded': 'pay0'}, 'skip': 1}, {'do': 'note_echo_paid76'}]
        effects = [{'do': 'echo_payment76', 'original': effects}]
        _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
             index=3000, definition={"kind": "triggered", "trigger": "upkeep_you", "optional": False, "target": None, "effects": effects})


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
# -- keywords (wave 15E) -- "Ward—Pay 3 life." / "Ward—Sacrifice a creature." / "Ward—Discard a card." (702.21a: counter it unless that
# player pays that cost): any cost the optional payment engine pays (app/rules/optional_payment.py)
WARD_COST = re.compile(r"^ward—(?P<cost>[^.]+?)\.?$", re.IGNORECASE)


def ward_piece_cost(piece: str) -> str | None:
    """The cost of one ward piece: its mana ("{2}") or the non-mana cost text ("Pay 3 life"), or None when not read."""
    from app.rules import optional_payment, paid_x

    m = WARD.fullmatch(piece)
    if m:
        return m["cost"]
    m = WARD_COST.fullmatch(piece.strip())
    if m is None:
        return None
    phrase = m["cost"].strip()
    if (cost := optional_payment.cost_text(_phrase(phrase))) is not None:
        return cost
    # -- keywords (wave 43C) -- "Ward—Pay life equal to Raubahn's power." (a life payment sized as it resolves, 608.2h; the ward permanent's own
    # power), "Ward—Discard a card or pay {2}." (one cost or the other, 118.12), "Ward—Get five poison counters." (an always-payable instruction)
    phrase = re.sub(r"(?<=equal to )(?:this creature|[A-Z][^']*?)'s power$", "~'s power", phrase)
    if paid_x.payment(_phrase(phrase)) is not None or optional_payment.alternatives(_phrase(phrase)) or effect_cost(phrase) is not None:
        return phrase
    return None


def ward_cost(ch: Any) -> str | None:
    costs = ward_costs(ch)
    return costs[0] if costs else None


def ward_costs(ch: Any) -> list[str]:
    """-- attached events (wave 4L) -- the cost of each ward ability the object has, printed or granted ("Equipped
    creature has ward {1}"): each instance is its own triggered ability (702.21a) and triggers on its own. -- activated other (wave 42C) --
    An object that has lost ward ("lose hexproof, indestructible, protection, shroud, and ward", Shay Cormac) has none (613.1f)."""
    out: list[str] = []
    if "ward" not in ch.keywords:
        return out
    for ab in ch.abilities:
        if ab.kind == "keywords" and "ward" in ab.keywords:
            # -- static wordings (wave 6E) -- a keyword line listing several keywords ("Flying, ward {2}"): each piece
            # is its own keyword ability (702.1), the ward piece triggers as any other (702.21a)
            for piece in ward_pieces(ab.text):
                cost = ward_piece_cost(piece)
                if cost is not None:
                    out.append(cost)
    return out


def ward_pieces(line: str) -> list[str]:
    """-- static wordings (wave 6E) -- the ward pieces of a keyword line ("Flying, ward {2}" → ["ward {2}"])."""
    out: list[str] = []
    for p in (p.strip() for p in re.split(r"[,;]\s*", line.strip().rstrip("."))):
        if out and out[-1].lower().startswith("ward—") and re.match(r"(?i)(?:pay|sacrifice|discard|exile|tap|return|put|remove|reveal|mill|\{)", p):
            out[-1] += ", " + p  # -- static_other sweep (wave 17C) -- "Ward—{2}, Pay 2 life.": one cost of two parts
        elif p.lower().startswith("ward"):
            out.append(p)
    return out


def _ward_payment(cost: str, payer: str, countered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """-- keywords (wave 43C) -- 702.21a: "counter it unless that player pays [cost]" for a cost that isn't mana: ``payer`` (the player whose spell or
    ability targeted it) may pay it, else ``countered`` happens (118.12a). The cost is a plain cost text, a life payment sized as the ward trigger
    resolves ("Pay life equal to ~'s power": the ward permanent's power then, 608.2h), one of two costs ("Discard a card or pay {2}") or an
    always-payable instruction ("Get five poison counters": the payer's, not the ward permanent's controller's)."""
    from app.rules import optional_payment, paid_x

    p = _phrase(cost)
    if optional_payment.parse(cost) is not None:
        pay: dict[str, Any] = {"cost": cost}
    elif sized := paid_x.payment(p):
        pay = sized
    elif alts := optional_payment.alternatives(p):
        pay = {"alts": alts}
    else:
        paid = [{**e, "who": payer} if e.get("who") == "you" else e for e in effect_cost(cost) or []]
        return pay_or_else(f"ward: {p}, or the spell is countered", payer, paid, countered)
    return [{"do": "optional_payment", "who": payer, **pay, "bind": "pay0"},
            {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": len(countered)}, *countered]


def targeted(plan: Plan, stack_id: str | None, controller: str, targets: list[Any], *, crime: bool = True) -> None:
    """702.21a ward: "Whenever this permanent becomes the target of a spell or ability an opponent
    controls, counter it unless that player pays [cost]." """
    if not stack_id:
        return
    # An object chosen for several words "target" (115.3) becomes the target of that spell or
    # ability once: one event, one trigger.
    targets = list({(t.id if hasattr(t, "id") else t): t for t in targets}.values())
    from app.rules import history  # -- this-turn history (wave 4D) -- 700.13: committing a crime

    if crime:  # (-- stack interaction (wave 5B) -- a changed target is no crime: 700.13 is about casting / activating)
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
                                 players=[controller],  # -- triggers (wave 21B) -- "that spell's controller" (115.1)
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
        from app.rules import hexproof_targeting

        if "ward" in ch.keywords and hexproof_targeting.suppresses_ward(plan, card, ch):
            continue
        from app.rules import (
            wave110d_lines,  # -- ward X (wave 110D) -- "ward {X}, where X is the number of experience counters you have" (Minthara)
        )

        extra = [] if hexproof_targeting.suppresses_ward(plan, card, ch) else wave110d_lines.ward_xp(plan, card)
        for k, cost in enumerate([*ward_costs(ch), *extra]):  # -- attached events (wave 4L) -- each instance (702.21a)
            effects: list[dict[str, Any]] = [{"do": "counter_unless", "cost": cost, "object": stack_id}]
            if not WARD.fullmatch(f"ward {cost}"):  # (wave 15E; 17C: "{2}, Pay 2 life" is not mana alone) a non-mana ward cost: the targeting player may pay it, else it's countered
                effects = _ward_payment(cost, f"player:{controller}", [{"do": "counter", "object": stack_id}])
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=9000 + k, definition={"kind": "triggered", "trigger": "ward", "optional": False, "target": None,
                                         "effects": effects})


def activated(plan: Plan, card: CardInstance, oid: str, *, loyalty: bool = False, ability_id: str | None = None, text: str = "", cost_has_x: bool | None = None, cost_has_tap: bool | None = None,
              payment: PaymentRecord | None = None, mana_ability: bool = False, actor: str | None = None, outlast: bool = False) -> None:
    """-- activation (wave 11F) -- 602.2: an activated ability (not a mana ability) was put on the stack by ``plan.actor``:
    "Whenever an opponent activates an ability of a creature …" (603.2). The source is the object that activated it,
    as it last existed if paying the cost moved it (603.10a, 608.2h)."""
    snap = None if plan.oid(card) == oid else plan.rules.lki.get(oid)
    obj, och = _snapshot_card(plan, snap) if snap is not None else (card, plan.ch(card))
    from app.rules import controller_tutors, ninjutsu

    ability = plan.state.cards.get(ability_id or "")  # (wave 18F: the activated ability itself, for "copy that ability")
    record = payment if payment is not None else plan.rules.payments.get(plan.oid(ability)) if ability is not None else None
    actor = actor or plan.actor
    from app.rules import wave110a_activation  # -- activation cost (wave 110A) --

    wave110a_activation.note(plan, och, actor, oid)
    activation_cost = {'has_tap': record.activation_cost_has_tap if record is not None and record.activation_cost_has_tap is not None else cost_has_tap,
                       'mana_tags': [list(tags) for tags in record.mana_tags] if record is not None and record.mana_known else None,
                       'mana': dict(record.mana_spent) if record is not None and record.mana_known else None,
                       'life': record.activation_life_paid if record is not None else None,
                       'sacrificed': len(record.sacrificed_objects) if record is not None else 0,
                       'has_x': record.activation_cost_has_x if record is not None and record.activation_cost_has_x is not None
                       else cost_has_x if cost_has_x is not None else '{X}' in (text.split(':', 1)[0] if ':' in text else '')}
    fact: Fact = ("activate", obj, och, actor,
                          {"oid": oid, "snap": snap, "actor": actor, "mana_ability": mana_ability, "amount": 1, "loyalty": loyalty, "activation_cost": activation_cost,
                           "loyalty_removed110b": plan.rules.once_per_turn.get("loyalty_removed110b", 0) if loyalty else 0,  # (606.4: counters its cost removed)
                           "ability_kind": "ninjutsu" if ninjutsu.is_ninjutsu(text) else controller_tutors.activation_kind(och, text),
                           "outlast110b": outlast and re.fullmatch(r"(?:\{[^}]+\})+, \{T\}: Put a \+1/\+1 counter on this creature\. Activate only as a sorcery\.", text) is not None,  # (702.107a: the keyword's own ability: AbilityText.special, or a granted one)
                           "word": (w[1].lower() if (w := re.match(r"(Exhaust|Boast|Power-up) — ", text)) else None),  # (wave 33C: its ability word)
                           "source_ref": ObjectRef(card=ability.id, object_id=plan.oid(ability), zone=ability.zone) if ability else None})
    _fire_generic(plan, [fact], -1, {})
    if record is not None:
        from app.rules import mana_units

        mana_units.copy_spend_triggers(plan, record, _event(plan, fact, -1), actor)


def voted(plan: Plan, starter: str, ballots: list[list[str]]) -> None:
    """-- voting (wave 48D) -- 701.38: the votes of one spell or ability are all in: "Whenever players finish voting" triggers (603.2) as it finishes resolving
    (rulings of Grudge Keeper); the trigger carries the votes of this voting alone."""
    _fire_generic(plan, [("voted", None, None, starter, {"ballots": [list(b) for b in ballots]})], -1, {})


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
        tid = t.id if hasattr(t, "id") else t
        if tid in plan.state.players:  # -- history (wave 22E) -- 115.1: "whenever you become the target of a spell or ability"
            if tid in plan.live():
                facts.append(("targeted", None, None, tid, {"by": controller, "spell": is_spell, "source_ref": source,
                                                            "actor": controller}))
            continue
        card = plan.state.cards.get(tid)
        if card is None or plan.manual(card) or not (card.zone.endswith(":battlefield") or (card.zone == "stack" and card.ability is None)):
            continue  # (-- target events (wave 45C) -- 115.1: a spell on the stack can become a target too: "a creature spell you control", Surrak)
        oid = plan.oid(card)
        # "for the first time each turn" (603.2): the first time this turn that something targeted this object ("any"), or the
        # first time a spell or ability its controller controls did / an opponent's did ("by": the ones the trigger asks about);
        # kept per turn, like other once-each-turn marks
        # (review 22E: a save from before this wave kept "targeted:<player>:<object>" marks - still read this turn)
        before = {p for p in plan.state.players if plan.rules.once_per_turn.get(f"targeted:{p}:{oid}") == turn}
        first = {}
        for group, mine, legacy in (("any", True, before), ("by", controller == card.controller, before & {card.controller}),
                                    ("by_opp", controller != card.controller, before - {card.controller})):
            if mine:
                key = f"targeted:{group}:{oid}"
                first[group] = plan.rules.once_per_turn.get(key) != turn and not legacy
                plan.rules.once_per_turn[key] = turn
        facts.append(("targeted", card, plan.ch(card), card.controller,
                      {"oid": oid, "by": controller, "spell": is_spell, "first": first, "source_ref": source,
                       "actor": controller}))  # (wave 19B: "that player" is the one whose spell or ability targeted it)
    if facts:
        _fire_generic(plan, facts, -1, {})


def flanking(plan: Plan, pairs: list[tuple[CardInstance, CardInstance]]) -> None:
    """702.25a: "Whenever this creature becomes blocked by a creature without flanking, the blocking
    creature gets -1/-1 until end of turn." (Per instance, per blocker.)"""
    for blocker, attacker in pairs:
        if plan.manual(attacker):
            continue
        ach = plan.ch(attacker)
        n = ach.flanking_count if ach.flanking_count is not None else int("flanking" in ach.keywords)
        # Count only instances that survived timestamp-ordered loss and grants (702.25b).
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
    pairs = [(b, plan.state.cards[x]) for b in {c.id: c for c in blockers}.values()  # (wave 13B: every attacker it blocks)
             for x in [b.blocking, *b.blocking_more] if x in plan.state.cards]
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
        for i, d in abilities(plan, ch, "bushido"):  # -- X keywords (wave 41B) -- "~ has bushido X, where X is …": its X is worked out as it resolves (keyword_triggers.dynamic_x)
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i, definition=d)


def dealt_combat_damage_to_player(plan: Plan, sources: list[CardInstance], hit: dict[str, list[str]] | None = None) -> None:
    """702.112 renown N: "When this creature deals combat damage to a player, if it isn't renowned,
    put N +1/+1 counters on it and it becomes renowned." (Checked again on resolution.)"""
    # -- counters & designations (wave 3E): the Ring's fourth ability (701.54c) --
    from app.rules import designations

    designations.ring_damage(plan, sources)
    for card in sources:
        if plan.manual(card):
            continue
        ch = plan.ch(card)
        # (wave 43A: the damage it triggered on — the players it hit — for a trigger multiplier that names it: Felix Five-Boots, 603.2d)
        dealt = TriggerEvent(kind="deal_combat_damage_player", count=1, combat=True, players=list((hit or {}).get(card.id, [])),
                             objects=[ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone)])
        for i, d in abilities(plan, ch, "combat_damage_player_self"):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=i, definition=d, cause=dealt)
        # -- static_other sweep (wave 17C) -- cipher 702.99a: "Whenever this creature deals combat damage to a player, you may copy the
        # encoded card and you may cast the copy without paying its mana cost." — one ability for each card encoded on it
        for k, oid in enumerate(plan.rules.exiled_with.get("cipher:" + plan.oid(card), [])):  # (recursion.CIPHER)
            enc = plan.state.cards.get(oid.rsplit(".", 1)[0])
            if enc is not None and enc.zone.endswith(":exile") and plan.oid(enc) == oid and not enc.face_down:
                _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=7400 + k,  # (wave 43A: not 7000, a delayed trigger's — the creature's own ability, which a trigger multiplier multiplies)
                     definition={"kind": "triggered", "trigger": "cipher", "optional": True, "target": None, "effects": [
                         {"do": "copy_cards", "who": f"exiled_card:{oid}", "as": "e0"},
                         {"do": "free_cast", "zone": "that", "who": "ref:e0", "filter": None, "optional": True, "mv": None, "n": 1}]}, cause=dealt)
        if plan.oid(card) in plan.rules.renowned:
            continue
        for k, n in enumerate(_keyword_n(ch, "renown")):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=4100 + k, definition={"kind": "triggered", "trigger": "renown", "optional": False, "target": None,
                                             "effects": [{"do": "renown", "n": n}]}, cause=dealt)


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
        # -- defending player (wave 6D) -- the attack, with the player it's against (508.5: app/rules/defending.py)
        attack = TriggerEvent(kind="attack", count=1, objects=[ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone)],
                              defended=_attack_defended(plan, "attack", card), attacked=_attack_object(plan, "attack", card))
        for i, d in abilities(plan, ch, "attacks_self"):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i,
                 definition=d, event=attack)


def _exalted(plan: Plan, alone: CardInstance) -> None:
    """702.83: "Whenever a creature you control attacks alone, that creature gets +1/+1 until end of
    turn" — once for each instance of exalted among permanents its controller controls."""
    target = f"object:{plan.oid(alone)}"
    # (wave 43A: the attack it triggered on, for a trigger multiplier that names a creature attacking — Isshin, 603.2d)
    attack = TriggerEvent(kind="attack", count=1, objects=[ObjectRef(card=alone.id, object_id=plan.oid(alone), zone=alone.zone)])
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
                                             "effects": [{"do": "pump", "who": target, "p": 1, "t": 1}]}, cause=attack)


def apnap(plan: Plan) -> list[str]:
    order, p = [], plan.active if plan.active in plan.live() else plan.after(plan.active)
    for _ in plan.live():
        order.append(p)
        p = plan.after(p)
    return order


def flush(plan: Plan) -> bool:
    """Put waiting triggers on the stack (603.3). True if the stack changed or a decision opened."""
    collect(plan)
    from app.rules import combat_player_scope43

    if combat_player_scope43.ask_pending(plan):
        return True
    from app.rules import first_event_receipts78

    if first_event_receipts78.ask_pending(plan):
        return True
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
    # -- core review -- 117.3c / 603.3: the player who was about to receive priority gets it once the triggers are on the
    # stack — the caster after a cast or activation, the active player after a resolution or at a step's start
    holder = plan.hold or r.priority
    r.priority = holder if holder in plan.live() else (plan.active if plan.active in plan.live() else plan.after(plan.active))
    return True


def _identical(plan: Plan, player: str, mine: list[PendingTrigger]) -> bool:
    return plan.rules.prefs_for(player).auto_order_identical_triggers and len({t.key for t in mine}) == 1 \
        and not any(t.ability.get("target") or t.ability.get("targets") for t in mine)


# -- damage wordings (wave 6B) --
def bind_that_player(t: PendingTrigger) -> None:
    """"Whenever ~ deals combat damage to a player, destroy target artifact that player controls": the selectors' "that
    player" (controller "that_player") becomes the one player the trigger event is about, as the ability is put on the
    stack and its targets are chosen (603.3d, 608.2k) — "player:<id>", kept for the 608.2b check. An event with no
    single player leaves it unbound (nothing matches: no legal target)."""
    # -- player-relative selectors (wave 53A) -- an instruction tagged ``that`` names its own player (a target, a choice: scripts.resolve_it): the trigger event's player is not it
    keep = {i: e for i, e in enumerate(t.ability.get("effects") or []) if e.get("that")}
    raw = json.dumps({**t.ability, "effects": [None if i in keep else e for i, e in enumerate(t.ability["effects"])]} if keep else t.ability)
    if t.event is not None and t.event.defended and '\\"defended_player\\"' in raw:  # -- triggers (wave 19B) -- 508.5: the player the attacker attacked
        for key in ("controller", "zone_owner"):
            raw = raw.replace(f'\\"{key}\\":\\"defended_player\\"', f'\\"{key}\\":\\"player:{t.event.defended}\\"')
        t.ability = json.loads(raw)
        if keep:
            t.ability = {**t.ability, "effects": [keep.get(i, e) for i, e in enumerate(t.ability["effects"])]}
    players = list(t.event.players) if t.event is not None else []
    if t.event is not None and t.event.kind == "you_attack" and t.event.defended and (t.ability.get("cond") or {}).get("player") == "you":
        players = [t.event.defended]  # (review 27B) "Whenever you attack a player, tap target creature that player controls": the one attacked (508.3e)
    if len(players) != 1:
        return
    for key in ("controller", "zone_owner", "player_exclude", "attacking_player"):  # event-relative selector bindings
        marker = f'\\"{key}\\":\\"that_player\\"'
        raw = raw.replace(marker, f'\\"{key}\\":\\"player:{players[0]}\\"')
    for kind in ("protected_by", "controlled_by"):  # (wave 110H) Rampaging Raptor: the player's battle (310.8) or planeswalker, in a nested selector key
        raw = raw.replace(f"{kind}:that_player", f"{kind}:player:{players[0]}")
    t.ability = json.loads(raw)
    if keep:
        t.ability = {**t.ability, "effects": [keep.get(i, e) for i, e in enumerate(t.ability["effects"])]}


def bind_event_stat(plan: Plan, t: PendingTrigger) -> None:
    """-- reanimation (wave 16F) -- "return target creature card with lesser mana value": the selectors' ``evt:<stat>`` becomes the
    number the one object the trigger is about had (as it last existed, 608.2h), as the ability is put on the stack."""
    from app.rules import fight_receipts90
    from app.rules.selectors import EVENT_STAT, _stat

    fight_receipts90.bind(plan, t)
    from app.rules import exchange_choices92

    exchange_choices92.bind(plan, t)
    raw = json.dumps(t.ability)
    if t.event is not None and t.event.kind == "reflexive" and f'\\"{EVENT_STAT}amount\\"' in raw:  # -- one-card wordings (wave 110H) -- Unleash the Inferno: the reflexive trigger's amount
        t.ability = json.loads(raw.replace(f'\\"{EVENT_STAT}amount\\"', str(t.event.amount or 0)))
        raw = json.dumps(t.ability)
    other_is_type = bool(t.ability.get('target_other_is_type'))
    if (f'\\"{EVENT_STAT}' not in raw and not other_is_type) or t.event is None or len(t.event.objects) != 1:
        return
    if t.event.kind != "reflexive" and '"do": "reflexive"' in raw:  # -- amass reflexive (wave 110D) -- its nested ability binds its own event (the amassed Army)
        return
    ref = t.event.objects[0]
    snap = ref.snapshot or plan.rules.lki.get(ref.object_id)
    card = plan.state.cards.get(ref.card)
    if snap is not None and (card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ref.object_id):
        ch = _lki_characteristics(plan, snap)
        counters = sum(snap.counters.values())
    elif card is not None:
        ch = plan.ch(card)
        counters = sum(card.counters.values())
    else:
        return
    if other_is_type:
        # The triggering spell's actual cast face determines the opposite target-card type.
        wanted = tuple(other for kind, other in (("Instant", "Sorcery"), ("Sorcery", "Instant")) if kind in ch.types) or ("__no_opposite_spell_type__",)
        groups = t.ability.get("targets") or []
        t.ability = {**t.ability, "targets": [
            {**group, "what": replace(selectors.from_key(group["what"]), types=wanted).key()}
            for group in groups
        ]}
        raw = json.dumps(t.ability)
    raw = raw.replace(f'\\"{EVENT_STAT}counters\\"', str(counters))  # -- lines (wave 110D) -- Puca's Covenant: counters on that creature, as it last existed
    for what in ("mv", "power", "toughness"):
        n = _stat(ch, what)
        if n is not None and what == "mv" and card is not None and card.zone == "stack" and card.stack_info is not None and card.stack_info.x:
            n += card.stack_info.x * ch.mana_cost.count("{X}")  # -- event spells (wave 28D) -- 202.3e: X on the stack is the value chosen
        if n is not None:
            raw = raw.replace(f'\\"{EVENT_STAT}{what}\\"', str(n))
    t.ability = json.loads(raw)
# -- end damage wordings (wave 6B) --


def put(plan: Plan, t: PendingTrigger, target: str | None = None, picks: dict[str, Any] | None = None) -> bool:
    """Put one trigger on the stack. False if it waits for its controller's target choice.
    ``picks``: the choices so far for an ability with target groups (603.3d → 601.2c-d)."""
    x = cast_x(plan, t)  # Own entry triggers also use their exact original payment X (107.3m); cast/cycle events delegate unchanged.
    if x is None:
        return _put(plan, t, target, picks)
    before, plan.x_choice = plan.x_choice, x
    try:
        return _put(plan, t, target, picks)
    finally:
        plan.x_choice = before


def _put(plan: Plan, t: PendingTrigger, target: str | None = None, picks: dict[str, Any] | None = None) -> bool:
    from app.rules import name_relation_continuations

    name_relation_continuations.bind_trigger_reference(plan, t)
    bind_that_player(t)  # -- damage wordings (wave 6B) --
    bind_event_stat(plan, t)  # -- reanimation (wave 16F) --
    # -- bounds defined by text (wave 28D) -- "mana value X or less, where X is …" (603.3d; review 28D: settled values only)
    from app.rules import where_bound

    t.ability = where_bound.bind(plan, t.ability, t.controller, t.source_card, t.source_object,
                                 t.event.model_dump(mode="json") if t.event is not None else None)
    from app.rules import (
        per_opponent,  # -- per-opponent targets (wave 12C) -- a group for each opponent, as it is put
    )

    per_opponent.expand(plan, t)
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
        from app.rules.targets import BadPick

        specs = target_groups(t.ability)  # (review 28D / wave 29C: "up to X target …, where X is …": X is the only limit, 107.3c, 601.2c)
        picks = picks or {"targets": [], "counts": [], "division": []}
        try:
            found = choose_groups(plan, specs, t.controller, source_of(plan, t.source_card, object_id=t.source_object), t.source_card,
                                  picks["targets"], picks["counts"], picks["division"], cast_x(plan, t), t.name or "It",
                                  attacker=attacker, source_object=t.source_object,  # (wave 19F: "up to X target …", X as 107.3m / 701.37c give it)
                                  event=t.event.model_dump(mode="json") if t.event is not None else None)  # (wave 28D: "where X is" an event's amount)
        except BadPick:  # -- X from the triggering object (wave 34C) -- a choice that breaks a rule of the group (over a total, 601.2c) is asked again
            raise
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
        legal = legal_targets(plan, spec["what"], t.controller, source_of(plan, t.source_card, object_id=t.source_object), t.source_card, attacker, source_object=t.source_object)
        if target is None:
            if not legal:
                r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
                plan.note(f"{t.name}'s ability has no legal target and is removed")
                return True
            choice_player = t.controller
            if t.ability.get("target_choice") == "event_player":
                event_players = list(t.event.players) if t.event is not None else []
                if len(event_players) != 1 or event_players[0] not in plan.live():
                    r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
                    plan.note(f"{t.name}'s ability has no unique player to choose its target and is removed")
                    return True
                choice_player = event_players[0]
            if t.ability.get("target_choice") == "defending100j":  # -- counters (wave 100J) -- "of defending player's choice" (Erithizon: 508.5)
                if t.event is None or t.event.defended not in plan.live():
                    r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
                    plan.note(f"{t.name}'s ability has no defending player to choose its target and is removed")
                    return True
                choice_player = t.event.defended
            if t.ability.get("target_choice") == "opponent110d":  # -- delegated (wave 110D) -- "of an opponent's choice": the controller picks the opponent (one: no question), who picks the target
                opponents = [pid for pid in plan.live() if pid != t.controller]
                if not opponents:
                    r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
                    plan.note(f"{t.name}'s ability has no opponent to choose its target and is removed")
                    return True
                if (picked := (picks or {}).get("opp110d")) is None and len(opponents) > 1:
                    decide(plan, player=t.controller, kind="choose_one", prompt=f"{t.name}: choose an opponent to select the target",
                           options=[DecisionOption(id=pid, label=plan.name(pid)) for pid in opponents],
                           resume={"step": "trigger_opp110d", "trigger": t.id})
                    return False
                choice_player = picked or opponents[0]
            decide(plan, player=choice_player, kind="choose_one", prompt=f"{t.name}: choose a target",
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
                                     event=t.event, x=cast_x(plan, t),
                                     x_from_event_spell=(t.event is not None and t.event.kind == 'cast'
                                         and t.source_card in plan.state.cards
                                         and x_source(t.ability, plan.ch(plan.state.cards[t.source_card])) == 'cast'), **extra)  # (x: wave 4J, 107.3m)
    if t.id in r.proctor_links110c:  # -- Strict Proctor (wave 110C) -- "that ability" for the Proctor triggers (wave110c_misc.proctor)
        r.proctor_links110c[t.id] = ability_id
    if t.ability.get("chosen_modes"):  # -- modal frames (wave 33B) -- 603.3c: the modes chosen are announced (a modal ability whose modes have target groups)
        plan.do({"type": "set_stack_info", "card_id": ability_id, "modes": t.ability["chosen_modes"]}, actor=t.controller)
    if t.ability.get('stack_tags'):
        plan.do({'type': 'set_stack_info', 'card_id': ability_id, 'tags': t.ability['stack_tags']}, actor=t.controller)
    if t.ability.get("link_player100a") and targets and t.source_object:  # -- trigger lines (wave 100A) -- the player a linked leaves ability means
        r.linked_players100a.setdefault(t.source_object, []).append(targets[0].id)
    if targets:
        plan.target_arrows(ability_id, [x.id for x in targets], actor=t.controller)  # (review 28D: an arrow points at up to 20)
        targeted(plan, ability_id, t.controller, targets)
    return True


# -- X from the triggering object (wave 34C) --
def x_source(d: dict[str, Any], ch: Characteristics) -> str | None:
    """Whose X a triggered ability's bare X is when it isn't an enters trigger's (107.3m): "cast" — the spell it triggered on, 107.3e
    ("Whenever you cast a spell with {X} in its mana cost, put X +1/+1 counters …": Zaxara, Nev) or the spell it is an ability of,
    107.3i ("When you cast this spell, copy it X times": its own X); "cycle" — the X "Cycling {X}" was announced with, 107.3a ("When you cycle
    this card, create an X/X …": Shark Typhoon). None for any other trigger: its X stays undefined, so the ability stays manual."""
    from app.rules import selectors

    if d.get("kind") != "triggered":
        return None
    cond = d.get("cond") or {}
    if d.get("trigger") == "turned_face_up_self":  # -- face-down X (wave 110B) -- 107.3a: "Morph {X}{B}{B}" / "Disguise {X}{3}{W}": the X paid to turn it face up
        from app.rules import casting

        morph, disguise = casting.morph_cost(ch), casting.disguise_cost(ch)
        return "faceup" if "{X}" in (morph[1] if morph else "") + (disguise or "") else None
    if d.get("trigger") == "cast_self":
        return "cast" if "{X}" in (ch.mana_cost or "") else None
    if cond.get("event") == "cast" and isinstance(cond.get("spell"), str):
        sel = selectors.from_key(cond["spell"])
        return "cast" if sel is not None and "x_cost" in sel.extras else None
    if cond.get("event") == "cycle" and cond.get("subject") == "self":
        from app.rules import casting

        return "cycle" if any((found := casting.hand_ability(ch, a.index)) is not None and "{X}" in found[1] for a in ch.abilities) else None
    return None


def event_spell_x(plan: Plan, event: TriggerEvent | None) -> int | None:
    """CR107.3e/i: the exact referenced spell's current X or stack LKI.

    A later effect may change X without changing mana already spent. Legacy
    saves can fall back to the original decision when no stack snapshot exists.
    """
    if event is None or event.kind != 'cast' or not event.objects:
        return None
    ref = event.objects[0]
    card = plan.state.cards.get(ref.card)
    if card is not None and card.zone == 'stack' and plan.oid(card) == ref.object_id \
            and card.stack_info is not None and card.stack_info.x is not None:
        return card.stack_info.x
    snap = plan.rules.lki.get(ref.object_id)
    if snap is not None and snap.zone == 'stack' and snap.x is not None:
        return snap.x
    record = plan.rules.payments.get(ref.object_id)
    return record.x if record is not None else None


def alania_first(plan: Plan, watcher: CardInstance, player: str | None, info: dict[str, Any]) -> bool:
    """601.2i: "it's the first instant spell, the first sorcery spell, or the first Otter spell other than Alania you've cast this turn" -- read from the
    turn's cast log, as each spell was cast (the spell itself and the ones before it)."""
    from app.rules import history

    notes = [n for n in history.log_for(plan).casts if n.player == player]
    at = next((i for i, n in enumerate(notes) if n.object_id == info.get("oid")), None)
    if at is None:
        return False
    cur, before = notes[at], notes[:at]
    me = plan.ch(watcher).name

    def otter(n: Any) -> bool:
        return "Otter" in n.subtypes and me not in (n.names or [])
    return any(kind in cur.types and not any(kind in n.types for n in before) for kind in ("Instant", "Sorcery")) \
        or (otter(cur) and not any(otter(n) for n in before))


def event_x(plan: Plan, t: PendingTrigger) -> int | None:
    """The X of the object a triggered ability triggered on (x_source): the spell cast (its payment record: 601.2h, 107.3e) or the cycling
    cost's announced X (107.3a). None when this trigger doesn't take its X from its event."""
    if t.ability.get("x_event") and t.event is not None and t.event.amount is not None:  # -- cast-permission riders (wave 38C) -- the X a reflexive ability's payment named
        return int(t.event.amount)
    cond = t.ability.get("cond") or {}
    if t.ability.get("trigger") == "turned_face_up_self":  # -- face-down X (wave 110B) -- the X paid as it was turned face up
        return t.event.x if t.event is not None and t.event.kind == "turned_face_up" else None
    if t.ability.get("trigger") != "cast_self" and cond.get("event") not in ("cast", "cycle"):
        return None  # (cheap: only these triggers read their event's X; the characteristics are derived below)
    kind = x_source(t.ability, plan.ch(plan.state.cards[t.source_card])) if t.source_card in plan.state.cards else None
    if kind == "cycle":
        return t.event.x if t.event is not None and t.event.kind == "cycle" else None
    if kind == "cast" and t.event is not None and t.event.kind == "cast" and t.event.objects:
        return event_spell_x(plan, t.event)
    return None
# -- end X from the triggering object --


# -- cast X (wave 4J) --
def cast_x(plan: Plan, t: PendingTrigger) -> int | None:
    """107.3m: an object's enters-the-battlefield triggered ability that refers to X uses the X of the spell that
    became that object as it resolved (its payment record, which follows it onto the battlefield); for any other
    triggered ability — or an object that wasn't cast with X — X is undefined here (0, 107.3i)."""
    if t.event is not None and t.event.kind == "become_monstrous" and any(o.object_id == t.source_object for o in t.event.objects):
        return plan.rules.monstrous_x.get(t.source_object)  # -- X sized by a count (wave 19F) -- 701.37c
    if (from_event := event_x(plan, t)) is not None:  # -- X from the triggering object (wave 34C) --
        return from_event
    if t.event is None or t.event.kind != "enter" or not any(o.object_id == t.source_object for o in t.event.objects):
        return None
    record = plan.rules.payments.get(t.source_object)
    if record is not None and not record.mana_known and '"x"' in json.dumps(t.ability.get("effects") or []):
        # -- review (wave 4R) -- cast by hand: its X isn't known (read as 0, as for the permanent's counters)
        plan.note(f"{t.name or 'It'} was cast by hand: its X isn't known (read as 0) — adjust by hand")
    return (record.resolved_x if record.resolved_x is not None else record.x) if record is not None else None
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


def resume_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    """-- delegated (wave 110D) -- the controller named the opponent who picks the target of "of an opponent's choice"."""
    t = next((p for p in plan.rules.pending_triggers if p.id == d.resume["trigger"]), None)
    if t is not None and chosen[0] in plan.live() and chosen[0] != t.controller and not put(plan, t, picks={"opp110d": chosen[0]}):
        return  # (the opponent's own decision is open: flush would ask the controller again)
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
