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

Not yet: intervening-if (603.4), delayed and reflexive triggers (603.7, 603.12), "whenever
another …" and other non-self trigger conditions.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from app.game.rules_state import DecisionOption, Event, ObjectSnapshot, PendingTrigger, StackEntry
from app.game.state import CardInstance, TokenDef
from app.rules import characteristics as chars
from app.rules import scripts
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
                        zone=snap.zone, face=snap.face, face_down=False, is_token=snap.is_token,
                        token=TokenDef(name=snap.name, text=snap.text, power=snap.token_power, toughness=snap.token_toughness,
                                      colors=snap.token_colors,
                                      **({"type_line": snap.token_type_line} if snap.token_type_line else {}))
                        if snap.is_token and not snap.printing else None)
    return chars.of(card, plan.info)


def _add(plan: Plan, *, controller: str, source_card: str, source_object: str, name: str, index: int,
         definition: dict[str, Any], manual: bool = False, event_object: str | None = None,
         event_player: str | None = None, event_amount: int = 0) -> None:
    if manual:
        return
    if definition.get("if") is not None:  # 603.4: an intervening "if" must hold as it triggers
        from app.rules import conditions

        if not conditions.holds(plan, {"controller": controller, "source_card": source_card}, definition["if"]):
            return
    effects = definition.get("effects") or []
    if any(e.get("who") in ("event", "event_player") or e.get("n") == {"event_amount": 1} for e in effects):
        # What the trigger event was about, bound now (603.2, 608.2k): "it" / "that creature" (that
        # one rules object: if it changes zones, the effect no longer finds it, 400.7), "that
        # player", "that much"
        def bind(e: dict[str, Any]) -> dict[str, Any]:
            if e.get("who") == "event":
                e = {**e, "who": f"object:{event_object}"}
            elif e.get("who") == "event_player":
                e = {**e, "who": f"player:{event_player}"}
            if e.get("n") == {"event_amount": 1}:
                e = {**e, "n": event_amount}
            return e

        definition = {**definition, "effects": [bind(e) for e in effects]}
    plan.rules.pending_triggers.append(PendingTrigger(
        id=secrets.token_hex(4), controller=controller, source_card=source_card, source_object=source_object,
        name=name, ability=definition, key=f"{name}:{index}"))


def collect(plan: Plan) -> None:
    """Look at the events since the last look (603.2)."""
    r = plan.rules
    new = [e for e in r.events if r.trigger_batch < e.batch <= r.batch]  # finished batches only
    if not new:
        return
    r.trigger_batch = max(e.batch for e in new)
    _generic_events(plan, new)
    for e in new:
        if e.kind == "spell_cast" and not e.manual:
            _cast_triggers(plan, e.card or "", e.player or "")
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
            for i, d in abilities(plan, ch, "enters_self"):
                _add(plan, controller=card.controller, source_card=card.id, source_object=e.new_object_id,
                     name=ch.name, index=i, definition=d)
            _other_enters(plan, card, ch, e.new_object_id)
        if frm == "battlefield" and to != "battlefield":
            snap = r.lki.get(e.object_id or "")
            if snap is None or plan.rules.card_mode(snap.card) == "manual" or snap.controller not in plan.live():
                continue
            ch = _lki_characteristics(plan, snap)  # looks back in time (603.10a)
            if snap.object_id in plan.rules.linked_exile:  # 610.3c: "… until ~ leaves" ends: they return at once
                from app.rules.effects import return_linked

                return_linked(plan, {"controller": snap.controller}, {"source": snap.object_id})
            kinds = ["ltb_self"] + (["dies_self"] if to == "graveyard" or (e.to_zone is None and snap.is_token) else [])
            for kind in kinds:
                for i, d in abilities(plan, ch, kind):
                    if d.get("unless_counter") and snap.counters.get(d["unless_counter"], 0) > 0:
                        continue  # persist / undying: "if it had no … counters on it"
                    _add(plan, controller=snap.controller, source_card=snap.card, source_object=snap.object_id,
                         name=ch.name, index=i, definition=d)


# -- generic conditions (app/rules/events.py) --------------------------------------------------
Fact = tuple[str, CardInstance | None, Characteristics | None, str | None]  # (event, object, its characteristics, player)


def _event_watchers(plan: Plan) -> list[tuple[CardInstance, Characteristics, int, dict[str, Any]]]:
    return [w for w in _watchers(plan, "event") if w[3].get("cond")]


def _snapshot_card(plan: Plan, snap: ObjectSnapshot) -> tuple[CardInstance, Characteristics]:
    """The object as it last existed on the battlefield (603.10a: leaves-the-battlefield triggers
    look back in time)."""
    ch = _lki_characteristics(plan, snap)
    card = CardInstance(id=snap.card, card_id=snap.printing, name=snap.name, owner=snap.owner, controller=snap.controller,
                        zone=snap.zone, face=snap.face, face_down=False, is_token=snap.is_token)
    return card, ch


def _object_then(plan: Plan, card_id: str | None, object_id: str | None) -> tuple[CardInstance, Characteristics] | None:
    """The object an event happened to: as it is now if it's still that object on the
    battlefield, else as it last existed there (it left since: 603.10, 608.2h)."""
    card = plan.state.cards.get(card_id or "")
    if card is not None and card.zone.endswith(":battlefield") and (object_id is None or plan.oid(card) == object_id):
        return card, plan.ch(card)
    snap = plan.rules.lki.get(object_id or "")
    return _snapshot_card(plan, snap) if snap is not None else None


def _facts(plan: Plan, e: Event) -> list[Fact]:
    r = plan.rules
    if e.kind == "zone_change":
        frm, to = _zone(e.from_zone), _zone(e.to_zone)
        if to == "battlefield" and frm != "battlefield":
            # (if it has left again since, as it was on the battlefield: it still entered, 603.6a)
            got = _object_then(plan, e.card, e.new_object_id)
            if got is not None:
                return [("enter", got[0], got[1], got[0].controller)]
        if frm == "battlefield" and to != "battlefield":
            snap = r.lki.get(e.object_id or "")
            if snap is None:
                return []
            card, ch = _snapshot_card(plan, snap)
            out: list[Fact] = [("leave", card, ch, snap.controller)]
            if to == "graveyard" or (e.to_zone is None and snap.is_token):
                out.append(("die", card, ch, snap.controller))
            return out
        return []
    if e.kind in ("tapped", "untapped"):
        got = _object_then(plan, e.card, e.object_id)
        return [(e.kind, got[0], got[1], got[0].controller)] if got is not None else []
    if e.kind in ("life_gain", "life_loss"):
        return [("gain_life" if e.kind == "life_gain" else "lose_life", None, None, e.player)]
    if e.kind == "spell_cast":
        spell = plan.state.cards.get(e.card or "")
        return [("cast", spell, plan.ch(spell), e.player)] if spell is not None else []
    if e.kind == "drew":
        return [("draw", None, None, e.player)]
    if e.kind == "damage":
        out = []
        # (a creature dealt lethal damage was still dealt it: 510.3a / 603.10a)
        got = _object_then(plan, e.card, e.object_id) if e.player is None and (e.card or e.object_id) else None
        if got is not None:
            out.append(("dealt_damage", got[0], got[1], got[0].controller))
        live = next((c for c in plan.state.cards.values() if plan.oid(c) == e.source), None) if e.source else None
        src = (live, plan.ch(live)) if live is not None else (
            _snapshot_card(plan, r.lki[e.source]) if e.source and e.source in r.lki else None)
        if src is not None and e.player is not None and e.player != src[0].controller:
            out.append(("deal_damage_opponent", src[0], src[1], src[0].controller))
            if e.combat:
                out.append(("deal_combat_damage_player", src[0], src[1], src[0].controller))
        return out
    return []


def _cond_matches(plan: Plan, cond: dict[str, Any], watcher: CardInstance, fact: Fact) -> bool:
    from app.rules import selectors

    event, obj, och, player = fact
    if cond["event"] != event:
        return False
    subject = cond["subject"]
    you = watcher.controller
    if subject == "player":
        want = cond["player"]
        if player is None or (want == "you" and player != you) or (want == "opponent" and player == you):
            return False
        if event == "cast":
            return obj is not None and och is not None and selectors.matches(
                plan, selectors.from_key(cond["spell"]), obj, och, you, watcher.id)
        return True
    if obj is None or och is None:
        return False
    if subject in ("self", "self_or") and obj.id == watcher.id:
        return True
    if subject == "self":
        return False
    return selectors.matches(plan, selectors.from_key(cond["sel"]), obj, och, you, watcher.id)


Watcher = tuple[CardInstance, Characteristics, int, dict[str, Any]]


def _fire_generic(plan: Plan, facts: list[Fact], batch: int, fired: set[tuple[str, int, int]],
                  watchers: list[tuple[Watcher, int, int]] | None = None, amount: int = 0) -> None:
    """Each watcher (with the batches it was on the battlefield for: it sees events from when it
    entered, 603.6a, until it left, 603.10a) against each fact of one event."""
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
            if cond.get("aggregate"):  # "one or more …": once per event batch (603.2c)
                key = (watcher.id, i, batch)
                if key in fired:
                    continue
                fired.add(key)
            obj = fact[1]  # (a live object; a snapshot of one that left isn't there to refer to)
            live = obj is not None and plan.state.cards.get(obj.id) is obj
            _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=plan.oid(watcher),
                 name=ch.name, index=i, definition=d, event_object=plan.oid(obj) if live and obj is not None else None,
                 event_player=fact[3], event_amount=amount)


def _generic_events(plan: Plan, events: list[Event]) -> None:
    """Generic "When/Whenever [subject] [event]" conditions against the event log."""
    r = plan.rules
    if r.draws_turn != plan.state.turn.number:
        r.draws_turn, r.draws_this_turn = plan.state.turn.number, {}
    fired: set[tuple[str, int, int]] = set()
    # Who was watching when: an object that left in these events saw everything up to and
    # including its leaving (603.10a: two creatures dying together each see the other die; a
    # creature dealt lethal damage was dealt it); one that entered sees events from its entering
    # on (603.6a), not earlier ones.
    big = 1 << 60
    entered: dict[str, int] = {}
    watchers: list[tuple[Watcher, int, int]] = []
    for e in events:
        if e.kind != "zone_change":
            continue
        if _zone(e.to_zone) == "battlefield" and _zone(e.from_zone) != "battlefield" and e.new_object_id:
            entered[e.new_object_id] = e.batch
        if _zone(e.from_zone) == "battlefield" and _zone(e.to_zone) != "battlefield":
            snap = r.lki.get(e.object_id or "")
            if snap is None or snap.controller not in plan.live() or plan.rules.card_mode(snap.card) == "manual":
                continue
            card, ch = _snapshot_card(plan, snap)
            watchers += [((card, ch, i, d), entered.get(snap.object_id, -big), e.batch)
                         for i, d in abilities(plan, ch, "event") if d.get("cond")]
    watchers += [(w, entered.get(plan.oid(w[0]), -big), big) for w in _event_watchers(plan)]
    for e in events:
        if e.manual:
            continue
        if e.kind == "drew" and e.player:
            r.draws_this_turn[e.player] = r.draws_this_turn.get(e.player, 0) + 1
        facts = _facts(plan, e)
        if facts:
            _fire_generic(plan, facts, e.batch, fired, watchers, amount=e.amount)


def generic_combat(plan: Plan, event: str, cards: list[CardInstance]) -> None:
    """"Whenever [creature] attacks / blocks / becomes blocked", "Whenever you attack" (508.3a,
    509.3a/c): one fact per creature; "you attack" once per combat for the attacking player."""
    if not cards:
        return
    fired: set[tuple[str, int, int]] = set()
    facts: list[Fact] = [(event, c, plan.ch(c), c.controller) for c in cards]
    if event == "attack":
        facts.append(("you_attack", None, None, cards[0].controller))
    _fire_generic(plan, facts, -1, fired)


def _watchers(plan: Plan, trigger: str) -> list[tuple[CardInstance, Characteristics, int, dict[str, Any]]]:
    out = []
    for card in plan.state.cards.values():
        if not card.zone.endswith(":battlefield") or not plan.in_game(card) or plan.manual(card):
            continue
        ch = plan.ch(card)
        out += [(card, ch, i, d) for i, d in abilities(plan, ch, trigger)]
    return out


def _other_enters(plan: Plan, entered: CardInstance, ech: Characteristics, oid: str) -> None:
    """603.6a: "Whenever [another] creature [you control] enters" on every permanent, including
    ones entering at the same time."""
    if ech.is_land:  # "Landfall — Whenever a land you control enters"
        for watcher, ch, i, d in _watchers(plan, "landfall"):
            if entered.controller == watcher.controller:
                _add(plan, controller=watcher.controller, source_card=watcher.id, source_object=plan.oid(watcher),
                     name=ch.name, index=i, definition=d, event_object=oid)
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
             index=i, definition=d, event_object=oid)


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
    if trigger == "end_step_you":
        _delayed(plan)
    if trigger == "upkeep_you":
        _echo(plan)
        _suspend(plan)
        _cumulative_upkeep(plan)
        _rebound(plan)
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or card.controller != plan.active or plan.manual(card):
            continue
        ch = plan.ch(card)
        for i, d in abilities(plan, ch, trigger):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i,
                 definition=d)


def at_step_generic(plan: Plan) -> None:
    """"At the beginning of [whose] [step]" (503.1a, 504, 505, 507, 513): every permanent's
    abilities for this step, when it's the right player's step."""
    phase = plan.state.turn.phase
    prefix = f"step:{phase}:"
    ap = plan.active
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or plan.manual(card) or card.controller not in plan.live():
            continue
        ch = plan.ch(card)
        for i, d in scripts.definitions(ch).items():
            if d["kind"] != "triggered" or not str(d["trigger"]).startswith(prefix):
                continue
            if _whose_step(plan, card, d["trigger"][len(prefix):], ap):
                _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                     index=i, definition=d)


def _whose_step(plan: Plan, card: CardInstance, whose: str, ap: str) -> bool:
    if whose == "you":
        return card.controller == ap
    if whose == "each":
        return True
    if whose == "opponent":
        return card.controller != ap
    if whose == "enchanted_player":
        return card.attached_player == ap
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


def _delayed(plan: Plan) -> None:
    """Delayed triggers "at the beginning of the next end step" (unearth, dash)."""
    due, plan.rules.delayed = plan.rules.delayed, []
    for entry in due:
        card = plan.state.cards.get(entry["card"])
        controller = card.controller if card is not None else plan.active
        _add(plan, controller=controller, source_card=entry["card"], source_object=entry["object"], name=entry.get("name", ""),
             index=7000, definition={"kind": "triggered", "trigger": "delayed", "optional": False, "target": None,
                                     "effects": [{"do": "delayed_move", "card": entry["card"], "object": entry["object"],
                                                  "to": entry["to"]}]})


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
    for ab in ch.abilities:
        if ab.kind == "keywords" and "ward" in ab.keywords:
            m = WARD.fullmatch(ab.text.strip().rstrip("."))
            return m["cost"] if m else None
    return None


def targeted(plan: Plan, stack_id: str | None, controller: str, targets: list[Any]) -> None:
    """702.21a ward: "Whenever this permanent becomes the target of a spell or ability an opponent
    controls, counter it unless that player pays [cost]." """
    if not stack_id:
        return
    # An object chosen for several words "target" (115.3) becomes the target of that spell or
    # ability once: one event, one trigger.
    targets = list({(t.id if hasattr(t, "id") else t): t for t in targets}.values())
    for t in targets:  # "When ~ becomes the target of a spell or ability, …" (any controller)
        card = plan.state.cards.get(t.id if hasattr(t, "id") else t)
        if card is None or not card.zone.endswith(":battlefield") or plan.manual(card):
            continue
        ch = plan.ch(card)
        for i, d in abilities(plan, ch, "targeted_self"):
            _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                 index=i, definition=d)
    for t in targets:
        card = plan.state.cards.get(t.id if hasattr(t, "id") else t)
        if card is None or not card.zone.endswith(":battlefield") or card.controller == controller or plan.manual(card):
            continue
        ch = plan.ch(card)
        cost = ward_cost(ch)
        if cost is None:
            continue
        _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
             index=9000, definition={"kind": "triggered", "trigger": "ward", "optional": False, "target": None,
                                     "effects": [{"do": "counter_unless", "cost": cost, "object": stack_id}]})


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
    generic_combat(plan, "block", list({c.id: c for c in blockers}.values()))
    generic_combat(plan, "blocked", list({c.id: c for c in attackers}.values()))
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
        decide(plan, player=plan.active, kind="confirm", prompt=f"Triggered: {names}",
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
    r = plan.rules
    spec = t.ability.get("target")
    targets = []
    extra: dict[str, Any] = {}
    if t.ability.get("targets"):
        from app.game.errors import ActionError
        from app.rules.casting import ask_targets
        from app.rules.scripts import target_groups

        specs = target_groups(t.ability)
        picks = picks or {"targets": [], "counts": [], "division": []}
        try:
            found = choose_groups(plan, specs, t.controller, source_of(plan, t.source_card), t.source_card,
                                  picks["targets"], picks["counts"], picks["division"], None, t.name or "It")
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
        legal = legal_targets(plan, spec["what"], t.controller, source_of(plan, t.source_card), t.source_card)
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
                                     targets=targets, target_spec=spec, optional=bool(t.ability.get("optional")), **extra)
    if targets:
        plan.do({"type": "create_arrow", "source": ability_id, "targets": [x.id for x in targets], "kind": "target"},
                actor=t.controller)
        targeted(plan, ability_id, t.controller, targets)
    return True


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
