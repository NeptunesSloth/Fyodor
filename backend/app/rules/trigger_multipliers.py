"""-- trigger multipliers (wave 5D) -- "that ability triggers an additional time" (CR 603.2d). Researched against
CR 2026-09-25 and the Wizards rulings of the cards below.

* 603.2d: rather than simply determining that an ability has triggered, determine how many times it triggers, then
  it triggers that many times. Each such effect adds one (two Panharmonicons: three times, not four); an effect
  doesn't apply to itself or to other such effects. It refers only to triggered abilities the object has — never to
  the delayed (603.7) or reflexive (603.12) triggered abilities they create.
* Each instance is a separate triggered ability (rulings: "doesn't copy the triggered ability"): its own targets and
  modes as it's put on the stack (603.3c-d), its own choices on resolution, ordered with the controller's other
  triggers (603.3b).
* "a permanent you control": only triggered abilities of permanents (as they are, or as they last existed for an
  ability that looks back in time, 603.10a) controlled by the multiplier's controller. A spell's "when you cast"
  ability, a card in a graveyard and the designations' inherent abilities (monarch, initiative) are not permanents
  (a multiplier that names a spell, Echoes of Eternity, reads a spell's; one that names an emblem, The Masamune, an emblem's).
* Which multipliers count (603.10): the continuous effects that exist immediately after the event — a Panharmonicon
  entering together with a creature counts for that creature (ruling) — except for abilities that look back in time
  (603.10a: leaves-the-battlefield, dies, sacrifice, leaving a graveyard), which use the effects that existed
  immediately before it — Teysa dying together with other creatures still counts (ruling).
* Two forms:
  - by cause: "If [an artifact or creature entering / a land entering / a permanent entering / a Wizard you control
    entering / a creature dying / you casting or copying an instant or sorcery spell / a player drawing a card]
    causes a triggered ability of a permanent you control to trigger, …". The trigger event must be that event:
    an object entering (603.6a), an object dying (700.4; a "leaves the battlefield" ability triggers twice when it
    died, a "whenever you sacrifice" ability doesn't — Teysa rulings; by the same reading "whenever you create a
    token" isn't "entering"), a spell cast or copied by that player (707.10), a card drawn.
  - by source: "If a triggered ability of [a Shaman or another Wizard / a creature you control with power 2 or less
    / a legendary creature / an Ally / another Elemental / a Ninja creature / another Wolf or battle] you control
    triggers, …": the source as it is as the ability triggers (Delney rulings: a later change doesn't matter).

(wave 43A) Also read: "entering [or leaving] the battlefield" causes (Panharmonicon, Yarok, Ancient Greenwarden, Elesh Norn, Gandalf, Naban, Starfield
Vocalist, Traveling Chocobo, Virtue of Knowledge), "a creature [you control] attacking" (Isshin, Windcrag Siege, Wulfgar), "a creature you control dealing
combat damage to a player" (Felix), the sources "equipped creature" (Wizard's Staff), "Cloud or an Equipment attached to it" (as long as it is equipped), "this
creature or an emblem you own" (The Masamune's grant), "a colorless spell you control or another colorless permanent you control" (Echoes of Eternity), "another
Shrine you control … while you control six or more Shrines" and "Room abilities of dungeons you own" (Hama Pashar, Dungeon Delver: 309.4c).

Refused (stay manual): any other cause or source wording (a face-down permanent turned face up, a creature being dealt damage, "while you have an enduring
story", …). An ability that "triggers only once each turn" is never multiplied (its additional instances would be a second triggering that turn; ruling of
Elvish Warmaster: "once the triggered ability has triggered once during a turn, it can't trigger again").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef, PendingTrigger, TriggerEvent

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

STATIC = "trigger_multiplier"
# -- static_other sweep (wave 16B) -- "Creatures entering [or dying] don't cause abilities to trigger." (Torpor Orb, Hushbringer, Hushwing Gryff,
# Tocatli Honor Guard): the opposite of a multiplier (603.2d: rather than determining that an ability triggered, nothing triggers). It
# stops the abilities (of any permanent, whoever controls it) that trigger from a creature — as it entered, or as it last existed on the
# battlefield — entering (or dying: 700.4); not a spell's, a delayed or a reflexive one, which no such event causes. The effects counted
# are those existing immediately after the event (603.10), for dying immediately before it (603.10a: Hushbringer dying with the creatures).
SUPPRESS = "trigger_suppress"
# (wave 42A: "Artifacts and creatures entering the battlefield don't cause abilities to trigger." (Karn, Argent Defender; Doorkeeper Thrull): the objects it stops are
# those of either kind, ``kinds``)
_SUPPRESS_TEXT = re.compile(r"^(?P<what>Creatures|Artifacts and creatures|Permanents) entering(?P<die> or dying)?(?: the battlefield)? don't cause abilities "
                            r"(?P<opp>of permanents your opponents control )?to trigger\.$")
# (wave 43A: "Permanents entering don't cause abilities of permanents your opponents control to trigger." (Elesh Norn, Mother of Machines): any permanent entering, but only
# the abilities of permanents the effect's controller's opponents control — "don't look at who controls the permanent entering, only who controls the permanent that has the
# triggered ability" (ruling of 2023-02-04); ``opponents``, ``any``)
_TAIL = r", (?:that ability|it) triggers an additional time\.$"
_CAUSE = re.compile(r"^If (?P<cause>.+?) causes a triggered ability of (?P<of>a permanent you control|(?:this creature|~) or an emblem you own) to trigger" + _TAIL)
# (wave 43A: "As long as ~ is equipped, if a triggered ability of ~ or an Equipment attached to it triggers, …" (Cloud, Midgar Mercenary), "… triggers while you control six or more
# Shrines, …" (Sanctum of All): the condition is read as the ability triggers)
_SOURCE = re.compile(r"^(?:As long as (?:(?P<equipped>~ is equipped)|(?P<story>you have an enduring story)), i|I)f a triggered ability of (?P<src>.+?) triggers(?: while (?P<while>.+?))?" + _TAIL)
# (wave 45D: "As long as you have an enduring story, if a triggered ability of a Dwarf you control triggers, …" (Bifur, Melodic Rider): read as the ability triggers; the designation is
# gained before triggers are collected (702.195c), so "if Bifur entering causes you to have an enduring story, his ability triggers an additional time" (ruling of 2026-06-29))
# -- trigger multipliers (wave 43A) -- 309.4c, 603.2d: "Room abilities of dungeons you own trigger an additional time." (Hama Pashar, Dungeon Delver's grant): the room ability of a dungeon its
# owner ventured into triggers again (the same room: it doesn't move the marker again — rulings of 2021-07-23, 2022-06-10); each such effect adds one
_ROOM = re.compile(r"^Room abilities of dungeons you own trigger an additional time\.$")
# the trigger events each cause names (603.2d: "If [event] causes a triggered ability … to trigger")
_CAUSES = (
    (re.compile(r"^an? (?P<sel>.+?) entering or leaving the battlefield$"), "enter_leave"),  # (wave 43A) Gandalf the White: 603.6a, 603.6c
    (re.compile(r"^an? (?P<sel>.+?) entering(?: the battlefield)?$"), "enter"),
    (re.compile(r"^an? (?P<sel>.+?) dying$"), "die"),
    # (wave 43A) 508.1m, 508.3: a creature declared as an attacker (Isshin, Windcrag Siege, Wulfgar): nothing else is read off the attackers, so only these two wordings
    (re.compile(r"^an? (?P<sel>creature(?: you control)?) attacking$"), "attack"),
    # (wave 43A) 120.2, 510.2 (Felix Five-Boots): damage a creature you control dealt a player in combat; a planeswalker or battle isn't "a player"
    (re.compile(r"^an? (?P<sel>creature you control) dealing combat damage to a player$"), "damage"),
    (re.compile(r"^you casting or copying an? (?P<sel>instant or sorcery spell)$"), "cast"),
    (re.compile(r"^a player drawing a card$"), "draw"),
)
# Not multiplied: the ids of the abilities _add creates that aren't "triggered abilities the object has" (603.2d)
DELAYED, REFLEXIVE, MADNESS = 7000, 7300, 8000
LOOK_BACK = ("die", "leave", "sacrifice", "leave_graveyard")  # 603.10a
# -- review (wave 43A) -- "If [a permanent] entering causes a triggered ability … to trigger" (Panharmonicon, Yarok, Ancient Greenwarden, Virtue of Knowledge, Naban, Starfield
# Vocalist, Traveling Chocobo, Elesh Norn) is read again. Wave 5R had refused it because "whenever you create a token" might be triggered by the token *entering* (701.7a). The
# event an ability triggers on is the one it names, and the rulings draw that line for the other actions the CR defines as a zone change: "an ability that triggers
# whenever you play a land won't trigger an additional time" (Ancient Greenwarden, 2020-09-25; 305.1: playing a land puts it onto the battlefield), "an ability that
# triggers on an event that causes a creature to die doesn't trigger twice … 'whenever you sacrifice a creature'" (Teysa Karlov, 2019-01-25; 701.21a) and "when you unlock
# this door … since the door becoming unlocked is what causes the ability to trigger, effects that cause abilities that trigger when a permanent enters to trigger an
# additional time (such as that of Panharmonicon) won't apply", even as the Room enters (Defiled Crypt // Cadaver Lab, 2024-09-20). Creating a token is the same kind of
# action (701.7a), so a "whenever you create a token" ability (the event "create_token", not "enter") is not multiplied. No ruling states that one outright - the one
# uncertain reading of this wave (to refuse the entering cause again, make static_definition return None for it); the rest (an "enters" trigger, a keyword's enters
# trigger, landfall, "another creature enters") is explicit in every ruling of the cards.
# -- end review (wave 43A) --


def _sels(text: str) -> list[str] | None:
    """The selector keys of a cause's objects: "artifact or creature" is one selector, "legendary permanent or an artifact" two (either)."""
    from app.rules import selectors

    whole = selectors.parse(text)
    parts = [whole] if whole is not None else [selectors.parse(p) for p in re.split(r" or an? ", text)] if " or " in text else [None]
    return None if any(p is None or p.player is not None for p in parts) else [p.key() for p in parts if p is not None]


def _source_keys(src: str) -> list[str] | None:
    """The sources "a triggered ability of …" names: selector keys, or the tokens "self" (the object with the ability), "host" ("equipped creature": the permanent
    the Equipment with the ability is attached to, 301.5, 303.4: Wizard's Staff) and "attached" (an Equipment attached to the object with the ability)."""
    from app.rules import selectors

    if src == "equipped creature":
        return ["host"]
    if src == "~ or an Equipment attached to it":
        return ["self", "attached"]
    keys: list[str] = []
    # "a Shaman or another Wizard you control": either one ("another": not the multiplier itself)
    parts = re.split(r" or (?=another )", re.sub(r"^an? ", "", src))
    tail = re.search(r" you control(?: with .+)?$", parts[-1])
    for part in parts:
        phrase = part if part is parts[-1] or tail is None or " you control" in part else part + tail.group(0)
        sel = selectors.parse(phrase)
        if sel is None or sel.controller != "you":
            return None
        keys.append(sel.key())
    return keys


def static_definition(text: str) -> dict[str, Any] | None:
    """The static line, or None (unread: the card stays manual)."""
    from app.rules import conditions

    text = text.strip()
    if (s := _SUPPRESS_TEXT.match(text)) is not None:
        if s["what"] == "Permanents" and s["die"]:
            return None
        return {"kind": "static", "static": SUPPRESS, "causes": ["enter", "die"] if s["die"] else ["enter"], "effects": [],
                **({"kinds": ["Artifact", "Creature"]} if s["what"] == "Artifacts and creatures" else {"any": True} if s["what"] == "Permanents" else {}),
                **({"opponents": True} if s["opp"] else {})}
    if _ROOM.match(text):
        return {"kind": "static", "static": STATIC, "room": True, "effects": []}
    m = _CAUSE.match(text)
    if m is not None:
        for rx, cause in _CAUSES:
            c = rx.match(m["cause"])
            if c is None:
                continue
            sels = _sels(c["sel"]) if "sel" in rx.groupindex else _sels("permanent")
            if sels is None:
                return None
            # ("of": "a permanent you control", or — the Masamune's grant — only the creature that has it and the emblems its controller owns)
            return {"kind": "static", "static": STATIC, "cause": cause, "sels": sels, "effects": [],
                    **({} if m["of"].startswith("a permanent") else {"source": ["self", "emblem"]})}
        return None
    m = _SOURCE.match(text)
    if m is None:
        return None
    keys = _source_keys(m["src"])
    if keys is None:
        return None
    out: dict[str, Any] = {"kind": "static", "static": STATIC, "source": keys, "effects": []}
    if m["equipped"]:
        out["while"] = "equipped"
    if m["while"] or m["story"]:
        cond = conditions.parse(m["while"] or m["story"])
        if cond is None:
            return None
        out["while"] = cond
    return out


def _source(plan: Plan, t: PendingTrigger) -> tuple[CardInstance, Characteristics, str] | None:
    """The object whose ability triggered, as it is, or as it last existed on the battlefield (603.10a), and what kind of object it is: a "permanent", a "spell" on the
    stack (wave 43A: its "when you cast this spell" ability, Echoes of Eternity) or an "emblem" (114.4, wave 43A: The Masamune)."""
    from app.rules import designations
    from app.rules.triggers import _snapshot_card

    card = plan.state.cards.get(t.source_card)
    if card is not None and plan.oid(card) == t.source_object:
        if card.zone.endswith(":battlefield"):
            return card, plan.ch(card), "permanent"
        if card.zone == "stack" and card.ability is None:
            return card, plan.ch(card), "spell"
        if designations.emblem_card(card):
            return card, plan.ch(card), "emblem"
    snap = plan.rules.lki.get(t.source_object)
    if snap is not None and snap.zone.endswith(":battlefield") and snap.card == t.source_card:
        return (*_snapshot_card(plan, snap), "permanent")
    return None


def _definitions(plan: Plan, ch: Characteristics, kind: str = STATIC) -> list[dict[str, Any]]:
    from app.rules import scripts

    phrase = "an additional time" if kind == STATIC else "t cause abilities"  # (don't cause abilities [of permanents your opponents control] to trigger)
    # (wave 43A: or in an ability it was granted — The Masamune's, Dungeon Delver's)
    if phrase not in (ch.oracle_text or "") and not any(phrase in ab.text for ab in ch.abilities):
        return []
    return [d for d in scripts.definitions(ch).values() if d.get("kind") == "static" and d.get("static") == kind]


def _multipliers(plan: Plan, controller: str | None, batch: int | None,
                 look_back: bool, kind: str = STATIC) -> list[tuple[CardInstance, dict[str, Any]]]:
    """The multipliers ``controller`` (None: anyone) controlled when the event of ``batch`` happened (603.10): right after it, or
    right before it for an ability that looks back in time (603.10a). No batch: as they are now."""
    from app.rules.triggers import _snapshot_card, _zone

    r = plan.rules
    entered: dict[str, int] = {}
    if batch is not None:
        for e in r.events:
            if e.kind == "zone_change" and _zone(e.to_zone) == "battlefield" and _zone(e.from_zone) != "battlefield" \
                    and e.new_object_id:
                entered[e.new_object_id] = e.batch
    out: list[tuple[CardInstance, dict[str, Any]]] = []
    for card in plan.state.cards.values():
        if (controller is not None and card.controller != controller) or not card.zone.endswith(":battlefield") or plan.manual(card) \
                or not plan.in_game(card):
            continue
        came = entered.get(plan.oid(card))
        if batch is not None and came is not None and (came > batch or (look_back and came == batch)):
            continue  # it wasn't there yet
        out += [(card, d) for d in _definitions(plan, plan.ch(card), kind)]
    if batch is None:
        return out
    for e in r.events:  # those that have left since (or with) the event
        if e.kind != "zone_change" or _zone(e.from_zone) != "battlefield" or _zone(e.to_zone) == "battlefield":
            continue
        if e.batch < batch or (e.batch == batch and not look_back):
            continue
        snap = r.lki.get(e.object_id or "")
        if snap is None or (controller is not None and snap.controller != controller) or plan.rules.card_mode(snap.card) == "manual":
            continue
        came = entered.get(snap.object_id)
        if came is not None and (came > batch or (look_back and came == batch)):
            continue
        card, ch = _snapshot_card(plan, snap)
        out += [(card, d) for d in _definitions(plan, ch, kind)]
    return out


def _object(plan: Plan, ref: ObjectRef) -> tuple[CardInstance, Characteristics] | None:
    from app.rules.triggers import _object_then, _snapshot_card

    if ref.snapshot is not None:
        return _snapshot_card(plan, ref.snapshot)
    card = plan.state.cards.get(ref.card)
    if card is not None and plan.oid(card) == ref.object_id:  # (a spell on the stack, a permanent still there)
        return card, plan.ch(card)
    return _object_then(plan, ref.card, ref.object_id)


def _died(plan: Plan, ref: ObjectRef) -> bool:
    """700.4: did this object leave the battlefield for a graveyard (a token: it went there and ceased to exist)?"""
    from app.rules.triggers import _zone

    for e in plan.rules.events:
        if e.kind == "zone_change" and e.object_id == ref.object_id and _zone(e.from_zone) == "battlefield":
            snap = plan.rules.lki.get(ref.object_id)
            return _zone(e.to_zone) == "graveyard" or (e.to_zone is None and snap is not None and snap.is_token)
    return False


def _caused(plan: Plan, d: dict[str, Any], mult: CardInstance, event: TriggerEvent | None) -> bool:
    from app.rules import selectors

    if event is None:
        return False
    cause, sels = d["cause"], [selectors.from_key(k) for k in d["sels"]]

    def fits(ref: ObjectRef | None, extra: Any = None) -> bool:
        got = _object(plan, ref) if ref is not None else None
        return got is not None and (extra is None or extra(ref)) and \
            any(selectors.matches(plan, sel, got[0], got[1], mult.controller, mult.id) for sel in sels)

    def any_object(extra: Any = None) -> bool:
        return any(fits(ref, extra) for ref in event.objects)

    if cause == "enter":
        return event.kind == "enter" and any_object()
    if cause == "enter_leave":  # (wave 43A) 603.6a, 603.6c: an object entering, or leaving the battlefield for anywhere (dying is leaving, 700.4); never a sacrifice
        return event.kind in ("enter", "leave", "die") and any_object()
    if cause == "die":  # (a "leaves the battlefield" ability, when it died; never "whenever you sacrifice")
        return event.kind == "die" and any_object() or event.kind == "leave" and any_object(lambda ref: _died(plan, ref))
    if cause == "attack":  # (wave 43A) 508.1m, 508.3a-d: a creature declared as an attacker — "attacks", "you attack", "attacks alone", "is attacked" ("you attack": its attackers are the
        # attacking player's); never "attacks and isn't blocked" (508.3f, 509.3g: it triggers at the declare blockers step, "even if the creature was never declared as an attacker")
        if event.kind == "attack":
            return any_object()
        return event.kind == "you_attack" and all(sel.controller != "you" or event.players == [mult.controller] for sel in sels)
    if cause == "damage":  # (wave 43A) Felix Five-Boots: the trigger's event is that creature dealing combat damage to a player (a planeswalker's or battle's isn't), not what the damage did
        if event.kind not in ("deal_damage", "deal_damage_opponent", "deal_combat_damage_player", "dealt_damage") or not event.combat or not event.players:
            return False
        return fits(event.source) if event.kind == "dealt_damage" else any_object()
    if cause == "cast":  # "you casting or copying": the player who cast or copied it (601.2i, 707.10)
        return event.kind in ("cast", "copy") and event.players == [mult.controller] and any_object()
    if cause == "draw":
        return event.kind == "draw"
    return False


def _held(plan: Plan, attachment: CardInstance, host: str, batch: int | None, look_back: bool) -> bool:
    """(wave 43A) Is ``attachment`` attached to the permanent ``host`` — or was it immediately before the event of ``batch``, for an ability that looks back in time
    (603.10a: a host that left let go of it in the same step, 603.10c; the "unattached" event of that step says so)?"""
    return attachment.attached_to == host or (look_back and batch is not None and any(
        e.kind == "unattached" and e.card == attachment.id and e.by_card == host and e.batch >= batch for e in plan.rules.events))


def _equipped(plan: Plan, mult: CardInstance, batch: int | None, look_back: bool) -> bool:
    """(wave 43A) 301.5: is an Equipment attached to ``mult`` (as it was right before the event, for an ability that looks back in time)?"""
    if any(c.attached_to == mult.id and "Equipment" in plan.ch(c).subtypes for c in plan.state.cards.values() if c.zone.endswith(":battlefield")):
        return True
    return look_back and batch is not None and any(
        e.kind == "unattached" and e.by_card == mult.id and e.batch >= batch and e.card in plan.state.cards
        and "Equipment" in plan.ch(plan.state.cards[e.card]).subtypes for e in plan.rules.events)


def _while(plan: Plan, cond: Any, mult: CardInstance, batch: int | None, look_back: bool) -> bool:
    """(wave 43A) The condition a multiplier states ("as long as ~ is equipped", "while you control six or more Shrines"), as the ability triggers."""
    if cond == "equipped":
        return _equipped(plan, mult, batch, look_back)
    from app.rules import conditions

    return conditions.holds(plan, {"controller": mult.controller, "source_card": mult.id, "source_object": plan.oid(mult), "event": None}, cond)


def _is_source(plan: Plan, key: str, mult: CardInstance, source: tuple[CardInstance, Characteristics, str], batch: int | None, look_back: bool) -> bool:
    """(wave 43A) Is the object whose ability triggered one this source names (a selector key, or "self", "emblem", "host", "attached")?"""
    from app.rules import selectors

    card, ch, kind = source
    if key == "self":
        return card.id == mult.id
    if key == "emblem":  # "an emblem you own" (114.3, 114.4)
        return kind == "emblem" and card.owner == mult.controller
    if key == "host":  # "equipped creature": the permanent ``mult`` (an Equipment) is attached to, a creature as it is or as it last was
        return kind == "permanent" and "Creature" in ch.types and _held(plan, mult, card.id, batch, look_back)
    if key == "attached":  # "an Equipment attached to it": attached to ``mult``
        return kind == "permanent" and "Equipment" in ch.subtypes and _held(plan, card, mult.id, batch, look_back)
    return selectors.matches(plan, selectors.from_key(key), card, ch, mult.controller, mult.id)


def _applies(plan: Plan, d: dict[str, Any], mult: CardInstance, t: PendingTrigger, source: tuple[CardInstance, Characteristics, str],
             cause: TriggerEvent | None, batch: int | None, look_back: bool) -> bool:
    """Does this multiplier add an instance to the ability ``t`` that just triggered (603.2d)?"""
    if d.get("room"):
        return False  # (room abilities: count)
    # "a triggered ability of a permanent you control" (the Masamune's grant: only its creature's and its controller's emblems')
    if "cause" in d and (mult.controller != t.controller or not _caused(plan, d, mult, cause) or ("source" not in d and source[2] != "permanent")):
        return False
    if "source" in d and not any(_is_source(plan, k, mult, source, batch, look_back) for k in d["source"]):
        return False
    return d.get("while") is None or _while(plan, d["while"], mult, batch, look_back)


def count(plan: Plan, t: PendingTrigger, index: int, cause: TriggerEvent | None) -> int:
    """How many additional times this just-triggered ability triggers (603.2d)."""
    if t.ability.get("trigger") == "room":  # (wave 43A) 309.4c: the room ability of a dungeon its controller owns (no source object); each effect adds one
        return sum(1 for _, d in _multipliers(plan, t.controller, None, False) if d.get("room"))
    if index in (DELAYED, REFLEXIVE, MADNESS) or t.ability.get("trigger") in ("delayed", "inherent") or not t.source_object:
        return 0
    if t.ability.get("limit") == "once_each_turn":
        return 0  # ("This ability triggers only once each turn.": its additional instances would be more than once)
    source = _source(plan, t)
    if source is None:
        return 0
    batch = cause.batch if cause is not None and cause.batch > 0 else None
    look_back = cause is not None and cause.kind in LOOK_BACK
    return sum(_applies(plan, d, mult, t, source, cause, batch, look_back) for mult, d in _multipliers(plan, None, batch, look_back))


def suppressed(plan: Plan, event: TriggerEvent | None, controller: str | None = None, permanent: bool = True) -> bool:
    """Is the trigger this event would cause (an ability ``controller`` controls) stopped by a "Creatures entering [or dying] don't cause abilities to trigger" effect?
    (-- review 37 -- ``permanent``: the ability is a permanent's; "abilities of permanents your opponents control" (Elesh Norn) doesn't stop a card's in a graveyard,
    Bloodghast's landfall, nor a delayed triggered ability, 603.2d, 110.1)"""
    if event is None or event.kind not in ("enter", "die", "leave") or not event.objects:
        return False
    cause = "enter" if event.kind == "enter" else "die"
    look_back = event.kind in LOOK_BACK
    batch = event.batch if event.batch > 0 else None
    # (wave 43A: "… abilities of permanents your opponents control": only those, whoever controls the object that entered, 603.2d)
    found = [d for pid in plan.state.players for _, d in _multipliers(plan, pid, batch, look_back, SUPPRESS)
             if cause in d["causes"] and (not d.get("opponents") or (controller is not None and controller != pid and permanent))]
    for ref in event.objects:  # every object of the event is one the effects name (a creature; wave 42A: or an artifact, where the effect says so; wave 43A: or any permanent)
        got = _object(plan, ref)
        if got is None or (event.kind == "leave" and not _died(plan, ref)) \
                or not any(d.get("any") or set(d.get("kinds") or ("Creature",)) & got[1].types for d in found):
            return False
    return bool(found)


def _extras(plan: Plan) -> dict[str, tuple[list[PendingTrigger], int]]:
    found: dict[str, tuple[list[PendingTrigger], int]] | None = getattr(plan, "_trigger_extras", None)
    if found is None:
        found = {}
        plan._trigger_extras = found  # type: ignore[attr-defined]
    return found


def multiply(plan: Plan, t: PendingTrigger, index: int, cause: TriggerEvent | None) -> None:
    """Add this trigger's additional instances (603.2d) next to it, each a separate triggered ability."""
    extras, _ = _extras(plan).get(t.id, ([], index))
    n = count(plan, t, index, cause) - len(extras)
    for _ in range(max(n, 0)):
        import secrets

        extra = t.model_copy(update={"id": secrets.token_hex(4)}, deep=True)
        plan.rules.pending_triggers.append(extra)
        extras.append(extra)
    _extras(plan)[t.id] = (extras, index)


def joined(plan: Plan, t: PendingTrigger) -> None:
    """A "one or more" trigger's event gained another object of its batch (603.2c): its additional instances carry
    the same event, and the new object may be the one a multiplier's cause names."""
    extras, index = _extras(plan).get(t.id, ([], -1))
    for extra in extras:
        extra.event = t.event.model_copy(deep=True) if t.event is not None else None
    if index >= 0:
        multiply(plan, t, index, t.event)


def entering(plan: Plan, card_id: str) -> TriggerEvent | None:
    """The event of a permanent entering (its zone change), for an enters trigger added outside the event pass (the
    evoke sacrifice, 702.74a)."""
    from app.rules.triggers import _zone

    card = plan.state.cards.get(card_id)
    if card is None:
        return None
    oid = plan.oid(card)
    batch = next((e.batch for e in reversed(plan.rules.events) if e.kind == "zone_change" and e.new_object_id == oid
                  and _zone(e.to_zone) == "battlefield"), 0)
    return TriggerEvent(kind="enter", batch=batch, count=1, objects=[ObjectRef(card=card.id, object_id=oid, zone=card.zone)])
