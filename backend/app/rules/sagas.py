"""Sagas (CR 714) and read ahead (702.155), researched against CR 2026-09-25.

* **Chapter abilities (714.2):** "{rN}—[Effect]" is a triggered ability: "When one or more lore
  counters are put onto this Saga, if the number of lore counters on it was less than N and became at
  least N, [effect]" (714.2b); "{rN1}, {rN2}—" is one such ability per numeral (714.2c). The chapter
  line's effect uses the ordinary effect grammar (app/rules/scripts.py ``parse_effects``); a line it
  doesn't read stays manual (never a guess). A trigger carries a TriggerEvent of kind "chapter" (the
  Saga, the chapter number as ``amount``).
* **Lore counters (714.3):** a Saga enters with one lore counter (714.3a), or with read ahead the
  number its controller chooses between one and its final chapter number (714.3b, 702.155b): a
  replacement effect, so the counters go through the counter choke point as it enters
  (app/rules/replacements.py ``entering_counters``; "If an effect would put …" statics such as
  Doubling Season apply, 614.16). As its controller's precombat main phase begins, they put a lore
  counter on each Saga they control with one or more chapter abilities (714.3c, 505.4): a turn-based
  action, not an effect — only "If you would put …" statics apply to it (``replace.put_counters`` with
  ``effect=False``). Proliferate and "put a lore counter on …" effects add counters as any effect.
* **Read ahead (702.155a):** the turn it entered, a chapter ability triggers only if the Saga has
  exactly that chapter's number of lore counters ("skipped chapters don't trigger").
* **Sacrifice (714.4):** a state-based action — a Saga with chapter abilities whose lore counters are
  at least its final chapter number, and that isn't the source of a chapter ability that has triggered
  but not yet left the stack, is sacrificed by its controller (app/rules/sba.py). A copy of a chapter
  ability (707.10) isn't a chapter ability that triggered. A Saga creature (714.1a) is no exception.
  The engine applies it only to a Saga whose every chapter line it automates: with a chapter left to
  the players, the players also decide when to sacrifice it (never a guess).

Not yet: a Saga that's also a double-faced card turning into a creature ("Exile this Saga, then
return it to the battlefield transformed") is read by the effect grammar or refused there; "Sagas you
control have read ahead" (granted read ahead); "the final chapter ability of a Saga … resolves /
triggers"; "Whenever you put a lore counter on a Saga".
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import Event, TriggerEvent
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

LORE = "lore"
CHAPTER_EVENT = "chapter"  # TriggerEvent.kind of a chapter ability (714.2b)
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
_CHAPTER = re.compile(r"^(?P<n>[IVX]+(?:, [IVX]+)*) — (?P<body>.+)$", re.S)
# a chapter's flavor name ("IV — Mega Flare — This creature deals …", 207.2c-like: no rules meaning)
_FLAVOR = re.compile(r"^(?P<name>[A-Z][^—.:\"•]{0,40}?) — (?P<rest>.+)$", re.S)
READ_AHEAD = "read ahead"
CHAPTER_CHOICE = re.compile(r"^chapter number \(1-(?P<n>\d+)\)$")  # the read-ahead choice's ``what`` (702.155b)


def is_saga(ch: Characteristics) -> bool:
    return "Saga" in ch.subtypes


def chapters_of(text: str) -> list[int]:
    """The chapter numbers of one ability line ("I, II — …" → [1, 2]); [] if it isn't a chapter line."""
    m = _CHAPTER.match(text.strip())
    if m is None:
        return []
    out = [_ROMAN.get(r) for r in m["n"].split(", ")]
    return [n for n in out if n is not None] if all(out) else []


def _chapter_lines(ch: Characteristics) -> list[tuple[AbilityText, list[int]]]:
    if not is_saga(ch):
        return []
    return [(ab, ns) for ab in ch.abilities if ab.kind != "keywords" and (ns := chapters_of(ab.text))]


def final_chapter(ch: Characteristics) -> int:
    """714.2d: the greatest chapter number among its chapter abilities (0 without any)."""
    return max((n for _, ns in _chapter_lines(ch) for n in ns), default=0)


def has_read_ahead(ch: Characteristics) -> bool:
    return READ_AHEAD in ch.keywords


# -- definitions (app/rules/scripts.py) ---------------------------------------------------------
def chapter_definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    """A chapter line as a triggered ability (714.2b-c), or None (not one, or not read: manual)."""
    if not is_saga(ch) or ability.kind == "keywords":
        return None
    numbers = chapters_of(ability.text)
    if not numbers:
        return None
    from app.rules import scripts

    body = _CHAPTER.match(ability.text.strip())["body"]  # type: ignore[index]
    flavor = _FLAVOR.match(body)
    if flavor is not None and not re.search(r"\bchoose\b", flavor["name"], re.IGNORECASE):
        body = flavor["rest"]
    body = re.sub(r"\b[Tt]his Saga\b", "~", scripts.self_text(body, ch.name))
    from app.rules import wave110c_misc  # -- chapters read as other wordings (wave 110C) --

    body = wave110c_misc.CHAPTERS.get(body, body)
    if body.rstrip().endswith("—"):
        return None  # (a modal chapter "Choose one —" with bulleted modes: not read here)
    # (-- saga (wave 20F) -- a chapter's leading "If …" is no intervening "if" (603.4: only "When/Whenever/At, if"): an instruction
    # checked as the chapter ability resolves, 608.2c — the plain conditional sentence)
    parsed = scripts.parse_effects(body)
    if parsed is None:
        return None
    effects, target, optional = parsed
    return {"kind": "triggered", "trigger": "chapter", "chapters": numbers, "effects": effects, "optional": optional,
            **scripts.target_fields(target)}


def read_ahead_definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    """702.155b: "As this Saga enters, choose a number between one and this Saga's final chapter
    number" — an "As ~ enters, choose" replacement (614.12a), asked before it enters."""
    if ability.kind != "keywords" or READ_AHEAD not in ability.keywords or not is_saga(ch):
        return None
    if ability.text.strip().rstrip(".").lower() != READ_AHEAD:
        return None
    final = final_chapter(ch)
    if final < 1:
        return None
    return {"kind": "replacement", "replacement": "enters_choice", "read_ahead": True,
            "effects": [{"do": "choose_value", "what": f"chapter number (1-{final})"}]}


def choice_options(what: str) -> list[tuple[str, str]] | None:
    """The options of the read-ahead choice (702.155b), or None if ``what`` isn't it."""
    m = CHAPTER_CHOICE.match(what)
    if m is None:
        return None
    return [(str(n), f"{n} lore counter{'s' if n > 1 else ''}") for n in range(1, int(m["n"]) + 1)]


def entering_lore(ch: Characteristics, choices: dict[str, str] | None) -> int:
    """The lore counters a Saga enters with (714.3a-b)."""
    if not is_saga(ch):
        return 0
    if not has_read_ahead(ch):
        return 1
    final = final_chapter(ch)
    for what, value in (choices or {}).items():
        m = CHAPTER_CHOICE.match(what)
        if m is not None and str(value).isdigit():
            return max(1, min(int(value), final or 1))
    return 1  # (no recorded choice: the least it can be)


# -- the turn-based action (714.3c, 505.4) --------------------------------------------------------
def precombat_main(plan: Plan) -> None:
    """As the active player's precombat main phase begins, they put a lore counter on each Saga they
    control with one or more chapter abilities (doesn't use the stack)."""
    from app.rules import replace

    ap = plan.active
    puts = []
    for card in plan.state.cards.values():
        if card.controller != ap or not card.zone.endswith(":battlefield") or not plan.in_game(card) or plan.manual(card):
            continue
        if final_chapter(plan.ch(card)) > 0:
            puts.append((card.id, LORE, 1))
    if puts:
        replace.put_counters(plan, puts, by=ap, effect=False)  # (not an effect: 714.3c, 614.16)


# -- chapter abilities triggering (714.2b, 702.155a) ---------------------------------------------
def _entered_this_turn(plan: Plan, oid: str) -> bool:
    """Did this object enter the battlefield this turn? (The event log only keeps what the last
    intents did: the entering is also marked per turn, ``RulesState.once_per_turn``, as it's seen.)"""
    turn = plan.state.turn.number
    return plan.rules.once_per_turn.get(f"entered:{oid}") == turn or any(
        e.kind == "zone_change" and e.new_object_id == oid and e.turn == turn
        and (e.to_zone or "").endswith(":battlefield") for e in plan.rules.events)


def _mark_entered(plan: Plan, events: list[Event]) -> None:
    turn = plan.state.turn.number
    for e in events:
        if e.kind == "zone_change" and e.new_object_id and e.turn == turn and (e.to_zone or "").endswith(":battlefield") \
                and not (e.from_zone or "").endswith(":battlefield"):
            card = plan.state.cards.get(e.card or "")
            if card is not None and plan.oid(card) == e.new_object_id and has_read_ahead(plan.ch(card)):
                plan.rules.once_per_turn[f"entered:{e.new_object_id}"] = turn


def _crossed(plan: Plan, e: Event) -> tuple[CardInstance, Characteristics, list[tuple[int, dict[str, Any], int]]] | None:
    """The chapter abilities one lore-counter event makes trigger: (the Saga as it was, its
    characteristics, [(ability index, definition, chapter number)])."""
    if e.kind != "counters" or e.counter != LORE or e.amount <= 0 or e.manual or not e.object_id:
        return None
    from app.rules import triggers

    got = triggers._object_then(plan, e.card, e.object_id)
    if got is None:
        return None
    card, ch = got
    if not is_saga(ch) or plan.rules.card_mode(card.id) == "manual":
        return None
    # the count right after this event: the count now (or as it last existed) less what was put or
    # removed on that object since
    live = plan.state.cards.get(card.id)
    if live is not None and live.zone.endswith(":battlefield") and plan.oid(live) == e.object_id:
        now = live.counters.get(LORE, 0)
    else:
        snap = plan.rules.lki.get(e.object_id)
        now = snap.counters.get(LORE, 0) if snap is not None else 0
    later = sum(x.amount for x in plan.rules.events if x.kind == "counters" and x.counter == LORE
                and x.object_id == e.object_id and x.batch > e.batch)
    after = now - later
    before = after - e.amount
    exact = has_read_ahead(ch) and _entered_this_turn(plan, e.object_id)  # 702.155a
    out = []
    for i, d in triggers.abilities(plan, ch, "chapter"):
        for n in d.get("chapters") or []:
            if before < n <= after and (not exact or n == after):
                out.append((i, d, n))
    return card, ch, out


def lore_triggers(plan: Plan, events: list[Event]) -> None:
    """Chapter abilities triggered by the lore counters these events put on Sagas (603.2, 714.2b)."""
    from app.game.rules_state import ObjectRef, TriggerEvent
    from app.rules import triggers

    _mark_entered(plan, events)
    for e in events:
        found = _crossed(plan, e)
        if found is None:
            continue
        card, ch, crossed = found
        for i, d, n in crossed:
            event = TriggerEvent(kind=CHAPTER_EVENT, batch=e.batch, amount=n, count=1,
                                 objects=[ObjectRef(card=card.id, object_id=e.object_id or "", zone=card.zone)])
            triggers._add(plan, controller=card.controller, source_card=card.id, source_object=e.object_id or "",
                          name=ch.name, index=i, definition=d, event=event)
            chapter_event(plan, event, "triggers")


def chapter_event(plan: Plan, event: TriggerEvent, when: str) -> None:
    """-- saga events (wave 45C) -- 714.2d: the chapter ability ``event`` is about is its Saga's final one (the greatest chapter number): "Whenever the
    final chapter ability of a Saga you control triggers / resolves" (Historian's Boon; Tom Bombadil, Narci: after it left the stack, per their
    rulings), asked of the Saga as it is or as it last existed (603.10a). ponytail: a copy of a chapter ability (707.10) isn't one, so it is skipped."""
    from app.rules import triggers

    ref = event.objects[0]
    got = triggers._object_then(plan, ref.card, ref.object_id)
    if got is None or event.amount != final_chapter(got[1]):
        return
    snap = None if triggers._live(plan, got[0]) else plan.rules.lki.get(ref.object_id)
    triggers._fire_generic(plan, [("final_chapter", got[0], got[1], got[0].controller,
                                   {"oid": ref.object_id, "when": when, "snap": snap})], -1, {})


# -- the state-based action (714.4) -----------------------------------------------------------------
def _automated(ch: Characteristics) -> bool:
    """Every chapter line of it is an automated chapter ability."""
    from app.rules import coverage, scripts

    defs = scripts.definitions(ch)
    return all(ab.index in defs and coverage.definition_supported(defs[ab.index]) for ab, _ in _chapter_lines(ch))


def chapter_waiting(plan: Plan, oid: str) -> bool:
    """Is it the source of a chapter ability that has triggered but not yet left the stack? (Waiting
    to be put on the stack, on the stack — not a copy, 707.10 — or not yet collected from the events.)"""
    r = plan.rules
    if any(t.source_object == oid and t.event is not None and t.event.kind == CHAPTER_EVENT for t in r.pending_triggers):
        return True
    stack = set(plan.state.zones.get("stack", []))
    if any(k in stack and s.kind == "trigger" and s.copy_of is None and s.source_object == oid and s.event is not None
           and s.event.kind == CHAPTER_EVENT for k, s in r.stack.items()):
        return True
    return any(e.batch > r.trigger_batch and e.object_id == oid and (found := _crossed(plan, e)) is not None and found[2]
               for e in r.events if e.kind == "counters")


def must_sacrifice(plan: Plan, card: CardInstance, ch: Characteristics) -> bool:
    """714.4 for one permanent on the battlefield."""
    final = final_chapter(ch)
    if final < 1 or card.counters.get(LORE, 0) < final or plan.manual(card) or not _automated(ch):
        return False
    return not chapter_waiting(plan, plan.oid(card))


SACRIFICE_REASON = "a Saga with its final chapter reached (714.4): sacrificed"
