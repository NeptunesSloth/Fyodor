"""Modal triggered and activated abilities (CR 700.2), researched against CR 2026-09-25.

A *modal* ability has two or more bulleted options preceded by an instruction to choose some of them
("Choose one —", 700.2). Modal spells are app/rules/casting.py; this module is the same for abilities:

* **Triggered (603.3c, 700.2b):** the controller announces the modes as the ability is put on the
  stack, before its targets (603.3d → 601.2c). A mode that can't be chosen — no legal target for what
  it targets (700.2b), or already chosen ("choose one that hasn't been chosen") — isn't offered. If
  no mode can be chosen (fewer than the instruction requires), or none is chosen ("choose up to one"),
  the ability is removed from the stack: it never goes on it.
* **Activated, loyalty (602.2b → 601.2b, 700.2a):** announced while activating, before targets and
  costs (601.2b, 601.2c, 601.2f-h): nothing is paid until the modes and their targets are chosen. If
  no mode can be chosen the ability can't be activated (602.2: an illegal activation).
* **Targets (700.2c, 700.2f, 601.2c):** a target for each chosen mode that has one, and only for it; the
  same object may be chosen for different modes. On resolution each mode's target is checked on its own
  (608.2b), the ability does nothing only if every target is illegal (app/rules/effects.py).
* **Order (608.2c):** chosen modes are carried out in the order they are printed, whatever the order
  they were chosen in.
* **"Choose one that hasn't been chosen [this turn]":** the CR has no rule for it; it is Oracle text, and
  the card rulings (Scryfall: Demonic Pact, Silent Hallcreeper, Kargan Intimidator, Gala Greeters,
  Monument to Endurance) say: it remembers the modes chosen for *that ability of that object* (not for
  the player, not for another copy of the card); a mode counts as chosen once it was announced, even if
  the ability is countered or its target becomes illegal; the memory dies with the object (400.7: if it
  leaves and returns it is a new object) but not with a change of controller; with "this turn" it
  starts over each turn; if every mode was chosen, a triggered ability is removed from the stack. The
  memory is ``RulesState.modes_chosen`` (saved with the game), written when the ability is actually put
  on the stack, never while the choice is still being made.

Reading the text is reuse, not a second grammar: each mode is read by the ordinary ability grammar
(``scripts.define``) as a one-line ability with the same header — "When ~ enters, <mode>" — so the
trigger condition, the pronouns ("it", "that player"), intervening "if", activation restrictions and
costs are exactly those of a non-modal ability. A wording it can't read makes the whole ability manual
(the coverage module's SUPPORTED_MODAL_ABILITIES lists the forms, each tested). Refused (never
guessed): "choose one at random", "each mode must target a different player", "you may choose both
instead", "choose X", reflexive "When you do, choose …" (603.12), a mode with "you may", several
targets or a division, a header with anything else after it, and "up to" / "any number" on an
activated ability (choosing no mode isn't modelled there).

Hidden information: the chosen modes go into the stack object's public annotations (they are announced,
601.2b/603.3c) — as text of the ability, which is public — except when the source is a card in a hidden
zone: then only "Mode N". The decision shows its labels only to the player who chooses (app/rules/view.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, PendingTrigger, RulesState, StackEntry, TargetRef
from app.game.visibility import publicly_visible
from app.rules import restrictions, selectors
from app.rules.oracle import AbilityText
from app.rules.plan import Plan, decide
from app.rules.targets import label as target_label
from app.rules.targets import legal_targets, ref, source_of

if TYPE_CHECKING:
    from app.game import actions as A
    from app.game.state import CardInstance
    from app.rules.casting import ChosenTargets
    from app.rules.characteristics import Characteristics

Definition = dict[str, Any]

# -- reading the text ---------------------------------------------------------------------------------
# How many modes may be chosen (fewest, most); most None: every mode ("one or more", "any number").
_COUNTS: dict[str, tuple[int, int | None]] = {
    "one": (1, 1), "two": (2, 2), "three": (3, 3), "four": (4, 4), "one or both": (1, 2), "one or more": (1, None),
    "any number": (0, None), "up to one": (0, 1), "up to two": (0, 2), "up to three": (0, 3), "up to four": (0, 4),
}
_HEADER = re.compile(
    r"^(?P<prefix>.*?)[Cc]hoose (?P<count>one or both|one or more|any number|up to (?:one|two|three|four)|one|two|three|four)"
    r"(?P<memory> that hasn['’]t been chosen(?: this turn)?)?(?P<end> —|\.)(?P<rest>.*)$")
# "…, if <condition>, " before the mode: a trigger's intervening "if" (603.4)
_INTERVENING = re.compile(r"^(?P<head>.+?), if (?P<cond>[^,]+), $")
# A line after the modes that belongs to the ability ("This ability triggers only once each turn.", "Activate
# only as a sorcery."): the limit would go unenforced, so the whole ability stays manual.
_TRAILER = re.compile(r"^(?:This ability|Activate\b|Do this only)")
# A mode's name ("• Solar Beam — The Vision gains double strike …"): a label, not rules text (207.2c).
_MODE_LABEL = re.compile(r"^[A-Z][\w'’\-]*(?: [\w'’\-]+){0,3} — (?=[A-Z0-9{])")


def definitions(ab: AbilityText, ch: Characteristics) -> dict[int, Definition]:
    """The definitions of a modal triggered / activated / loyalty ability whose header is ``ab`` and
    whose modes are all read: the ability itself (``modes`` and ``modal``) and a ``kind: "mode"`` stub
    for each of its bulleted lines (so they count as part of it). {} if it isn't one, or if any part
    isn't understood — the whole ability is then manual."""
    from app.rules import scripts  # (scripts reads an ability here: a leaf module over it)

    m = _HEADER.match(ab.text)
    if m is None or not _header_ok(ab, m["prefix"], m["end"], m["rest"].strip()):
        return {}
    bullets = _bullets(ch, ab.index)
    n = len(bullets)
    after = next((x for x in ch.abilities if x.index == (bullets[-1].index + 1 if bullets else -1)), None)
    if after is not None and _TRAILER.match(after.text):
        return {}  # (a sentence after the modes that is about this ability — a limit, a restriction — isn't read)
    lo, top = _COUNTS[m["count"]]
    hi = n if top is None else min(top, n)
    if n < 2 or lo > n or (m["count"] == "one or both" and n != 2):  # (700.2: two or more options)
        return {}
    if ab.kind != "triggered" and lo == 0:
        return {}  # (an activation with no mode chosen: not modelled)
    memory = None if not m["memory"] else ("turn" if m["memory"].endswith("this turn") else "game")
    rest = m["rest"].strip()
    prefix, intervening = m["prefix"], None
    if ab.kind == "triggered" and (im := _INTERVENING.match(prefix)) is not None:
        from app.rules import conditions

        intervening = conditions.parse(im["cond"])  # 603.4: an intervening "if" of the header, for every mode
        if intervening is None:
            return {}
        prefix = f"{im['head']}, "
    modes: list[Definition] = []
    shape: Definition | None = None
    for k, bullet in enumerate(bullets):
        text = bullet.text[2:].strip()
        body = _MODE_LABEL.sub("", text, count=1)
        if ab.kind == "triggered" and body.lower().startswith("if "):
            return {}  # (it would read as an intervening "if" of the trigger, 603.4, not of the mode)
        one = AbilityText(index=ab.index, kind=ab.kind, cost=ab.cost, text=f"{prefix}{body}" + (f" {rest}" if rest else ""))
        d = scripts.define(one, ch)  # the mode as a non-modal ability with this header
        if d is None or d["kind"] not in ("triggered", "activated") or d.get("optional") or d.get("targets") \
                or d.get("limit") == "do_once" or d.get("if") is not None or not d["effects"]:
            return {}  # ("you may", several targets or a division, "Do this only once each turn": not in a mode)
        found = {key: value for key, value in d.items() if key not in ("effects", "target")}
        if shape is None:
            shape = found
        elif found != shape:
            return {}  # (the header says the same to every mode)
        modes.append({"text": text, "effects": scripts.rename_bindings(d["effects"], f"m{k}_"), "target": d["target"]})
    assert shape is not None
    if intervening is not None:
        if scripts._trigger_antecedent(shape["trigger"], shape.get("cond")) != "self" \
                and scripts._condition_says_other(intervening):
            return {}  # ("another …" than which object? not modelled, as for a plain trigger)
        shape = {**shape, "if": intervening}
    modal = {"min": lo, "max": hi, "repeat": False, "condition": None, "memory": memory, "index": ab.index,
             "form": ab.kind}
    out: dict[int, Definition] = {ab.index: {**shape, "effects": [], "target": None, "optional": False,
                                              "modes": modes, "modal": modal}}
    for bullet in bullets:
        out[bullet.index] = {"kind": "mode", "of": ab.index, "form": ab.kind, "memory": memory, "effects": []}
    return out


def _header_ok(ab: AbilityText, prefix: str, end: str, rest: str) -> bool:
    """Is the line one header and nothing else: "<trigger condition>, choose one —", "<cost>: Choose
    one —" (an activated ability may add its "Activate only …" sentences after "Choose one.", a
    triggered ability its limit)."""
    if ab.kind == "triggered":
        if not prefix.endswith(", ") or ". " in prefix:
            return False  # (a line with another sentence before it is a reflexive trigger, 603.12, or the like)
        return rest == "" if end == " —" else rest == "" or rest in restrictions.TRIGGER_LIMITS
    if ab.kind in ("activated", "loyalty") and ab.cost:
        if prefix != f"{ab.cost}: ":
            return False
        return rest == "" if end == " —" else rest == "" or restrictions.split(rest)[0] == ""
    return False


def _bullets(ch: Characteristics, index: int) -> list[AbilityText]:
    """The lines of bulleted modes directly after ability ``index``."""
    lines = ch.abilities
    at = next((i for i, x in enumerate(lines) if x.index == index), None)
    out: list[AbilityText] = []
    for line in lines[at + 1:] if at is not None else ():
        if not line.text.startswith("• "):
            break
        out.append(line)
    return out


# -- "choose one that hasn't been chosen [this turn]" ---------------------------------------------------
def _key(oid: str, index: int, memory: str, turn: int) -> str:
    return f"{oid}:{index}:game" if memory == "game" else f"{oid}:{index}:t{turn}"


def chosen_before(rules: RulesState, oid: str, index: int, memory: str | None, turn: int) -> tuple[int, ...]:
    """The modes already chosen for this ability of this object ("this turn": in ``turn``)."""
    return tuple(rules.modes_chosen.get(_key(oid, index, memory, turn), ())) if memory else ()


def _alive(rules: RulesState, key: str) -> bool:
    """Does the object a memory belongs to still exist (or did it just leave: its last known
    information is kept for a little while, 608.2h)?"""
    oid = key.rsplit(":", 2)[0]
    card_id = oid.rpartition(".")[0]
    return oid in rules.lki or rules.object_id(card_id) == oid


def remember(rules: RulesState, oid: str, index: int, memory: str | None, turn: int, modes: list[int]) -> None:
    """These modes were chosen for this ability of this object, as it was put on the stack. Earlier
    turns' memory and that of objects that are gone (400.7) is dropped: nothing reads it any more."""
    if memory is None:
        return
    rules.modes_chosen = {k: v for k, v in rules.modes_chosen.items()
                          if k.endswith(f":t{turn}") or (k.endswith(":game") and _alive(rules, k))}
    key = _key(oid, index, memory, turn)
    rules.modes_chosen[key] = sorted({*rules.modes_chosen.get(key, ()), *modes})


# -- what is announced -----------------------------------------------------------------------------------
def mode_effects(definition: Definition, chosen: list[int]) -> list[dict[str, Any]]:
    """The effects of the chosen modes in printed order (608.2c), each with its own target slot
    ("use_targets"); a trigger's intervening "if" is checked again as it resolves (603.4)."""
    out = [e for k, i in enumerate(chosen) for e in [{"do": "use_targets", "slot": k}, *definition["modes"][i]["effects"]]]
    if definition.get("if") is not None:
        out = [{"do": "only_if", "cond": definition["if"], "skip": len(out)}, *out]
    return out


def _public_texts(plan: Plan, source_card: str | None, definition: Definition, chosen: list[int]) -> list[str]:
    """The chosen modes as the table sees them: the ability's text, unless its source is a card the
    table can't see (then the text would say what it is)."""
    card = plan.state.cards.get(source_card or "")
    hidden = card is not None and not publicly_visible(plan.state, card)
    return [f"Mode {i + 1}" if hidden else definition["modes"][i]["text"] for i in chosen]


_WORDS = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _phrase(lo: int, hi: int, memory: str | None) -> str:
    """"one mode", "up to two modes", "one to three modes" (that hasn't been chosen [this turn])."""
    def word(n: int) -> str:
        return _WORDS.get(n, str(n))

    many = "mode" if hi == 1 else "modes"
    if lo == hi:
        how = f"{word(lo)} {many}"
    elif lo == 0:
        how = f"up to {word(hi)} {many}"
    else:
        how = f"{word(lo)} {'or' if hi == lo + 1 else 'to'} {word(hi)} {many}"
    return how + (" that hasn't been chosen" + (" this turn" if memory == "turn" else "") if memory else "")


def _slots(specs: list[Definition | None], picked: list[str], plan: Plan) -> list[list[TargetRef]]:
    out: list[list[TargetRef]] = []
    at = 0
    for spec in specs:
        out.append([ref(plan, picked[at])] if spec else [])
        at += 1 if spec else 0
    return out


# -- a modal triggered ability goes on the stack (603.3c) --------------------------------------------------
def _pending(plan: Plan, trigger_id: str) -> PendingTrigger | None:
    return next((p for p in plan.rules.pending_triggers if p.id == trigger_id), None)


def _name(plan: Plan, t: PendingTrigger) -> str:
    """How prompts and the log call the source: by name, unless it is a card the table can't see."""
    card = plan.state.cards.get(t.source_card)
    return t.name if t.name and (card is None or publicly_visible(plan.state, card)) else "A triggered ability"


def _remove(plan: Plan, t: PendingTrigger, why: str) -> None:
    plan.rules.pending_triggers = [p for p in plan.rules.pending_triggers if p.id != t.id]
    who = _name(plan, t)
    plan.note(f"{who}'s ability {why} and is removed" if who != "A triggered ability" else f"{who} {why} and is removed")


def put_trigger(plan: Plan, t: PendingTrigger, picks: dict[str, Any] | None = None) -> bool:
    """Put one modal triggered ability on the stack: its modes first (603.3c, 700.2b), then a target for
    each chosen mode that has one (603.3d → 601.2c). False while waiting for its controller's choice;
    True once it is on the stack or was removed. ``picks``: the choices so far ("modes", "targets")."""
    r, d = plan.rules, t.ability
    modes, modal = d["modes"], d["modal"]
    picks = picks or {}
    src = source_of(plan, t.source_card)
    attacker = selectors.attacker_of(t.event)
    card = plan.state.cards.get(t.source_card)

    def legal(i: int) -> list[str]:
        spec = modes[i]["target"]
        return legal_targets(plan, spec["what"], t.controller, src, t.source_card, attacker) if spec else []

    chosen: list[int] | None = picks.get("modes")
    if chosen is None:
        done = chosen_before(r, t.source_object, modal["index"], modal["memory"], plan.state.turn.number)
        allowed = [i for i, m in enumerate(modes) if i not in done and (not m["target"] or legal(i))]
        lo, hi = modal["min"], min(modal["max"], len(allowed))
        if not allowed or len(allowed) < lo:  # 700.2b: no mode can be chosen: removed from the stack
            _remove(plan, t, "has no mode that can be chosen")
            return True
        decide(plan, player=t.controller, kind="choose_cards",
               prompt=f"{_name(plan, t)}: choose {_phrase(lo, hi, modal['memory'])}",
               options=[DecisionOption(id=f"{i}:0", label=modes[i]["text"][:120]) for i in allowed],
               min_choices=lo, max_choices=hi, resume={"step": "trigger_modes", "trigger": t.id}, source=card)
        return False
    if not chosen:  # 700.2b: "If no mode is chosen, the ability is removed from the stack."
        _remove(plan, t, "has no mode chosen")
        return True
    if len(set(chosen)) != len(chosen) or any(not 0 <= i < len(modes) for i in chosen):
        raise ActionError("Choose each mode at most once")
    targets: list[str] = list(picks.get("targets") or [])
    need = [i for i in chosen if modes[i]["target"]]
    if len(targets) < len(need):  # 601.2c: the next chosen mode's target
        i = need[len(targets)]
        options = legal(i)
        if not options:  # (it was offered only with a legal target, and nothing has changed since)
            _remove(plan, t, "has no legal target")
            return True
        decide(plan, player=t.controller, kind="choose_one",
               prompt=f"{_name(plan, t)}: choose a target ({modes[i]['text'][:60]})",
               options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None)
                        for x in options],
               resume={"step": "trigger_slot_target", "trigger": t.id, "modes": chosen, "targets": targets}, source=card)
        return False
    return _on_the_stack(plan, t, chosen, targets)


def _on_the_stack(plan: Plan, t: PendingTrigger, chosen: list[int], picked: list[str]) -> bool:
    from app.rules.triggers import targeted

    r, d = plan.rules, t.ability
    specs = [d["modes"][i]["target"] for i in chosen]
    slots = _slots(specs, picked, plan)
    flat = [x for slot in slots for x in slot]
    r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
    source = t.source_card if t.source_card in plan.state.cards else None
    text = t.name + "’s ability" if t.name else "Triggered ability"
    created = plan.do({"type": "create_ability", "text": text, "source_id": source, "kind": "triggered"}, actor=t.controller)
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    if ability_id is None:
        return True
    r.stack[ability_id] = StackEntry(kind="trigger", controller=t.controller, source_card=t.source_card,
                                     source_object=t.source_object, name=t.name, effects=mode_effects(d, chosen),
                                     targets=flat, target_spec=None, event=t.event, modes=chosen, slots=slots,
                                     slot_specs=specs)
    remember(r, t.source_object, d["modal"]["index"], d["modal"]["memory"], plan.state.turn.number, chosen)
    plan.do({"type": "set_stack_info", "card_id": ability_id, "modes": _public_texts(plan, t.source_card, d, chosen)},
            actor=t.controller)
    if flat:
        plan.do({"type": "create_arrow", "source": ability_id, "targets": [x.id for x in flat], "kind": "target"},
                actor=t.controller)
        targeted(plan, ability_id, t.controller, flat)
    return True


def resume_trigger_modes(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The modes of a triggered ability were chosen: its targets next, or onto the stack."""
    from app.rules.triggers import flush

    t = _pending(plan, d.resume["trigger"])
    if t is not None and not put_trigger(plan, t, {"modes": sorted({int(c.split(":")[0]) for c in chosen}),
                                                   "targets": []}):
        return
    flush(plan)


def resume_trigger_slot(plan: Plan, d: Any, chosen: list[str]) -> None:
    """A chosen mode's target was chosen: the next one, or onto the stack."""
    from app.rules.triggers import flush

    res = d.resume
    t = _pending(plan, res["trigger"])
    if t is not None and not put_trigger(plan, t, {"modes": list(res["modes"]), "targets": [*res["targets"], chosen[0]]}):
        return
    flush(plan)


# -- a modal ability is activated (602.2b → 601.2b-c) -------------------------------------------------------
@dataclass
class Announced:
    """What activating a modal ability announced: its modes (printed order), each one's target slot
    and the effects to carry out."""

    targets: ChosenTargets
    modes: list[int]
    slots: list[list[TargetRef]]
    specs: list[Definition | None]
    effects: list[dict[str, Any]]
    definition: Definition
    index: int  # the ability's index on its source

    @property
    def entry(self) -> dict[str, Any]:
        """The StackEntry fields for it."""
        return {"effects": self.effects, "targets": self.targets.flat, "target_spec": None, "modes": self.modes,
                "slots": self.slots, "slot_specs": self.specs}


def announce(plan: Plan, a: A.ActivateAbility, card: CardInstance, definition: Definition, index: int, oid: str,
             what: str) -> Announced | None:
    """The modes of an ability being activated (validated if given in ``a.modes``, else asked), then a
    target for each mode that has one. Nothing is paid before both are chosen. None while waiting for a
    choice; raises ActionError if no mode can be chosen (the ability can't be activated)."""
    from app.rules import casting

    modal = definition["modal"]
    done = chosen_before(plan.rules, oid, index, modal["memory"], plan.state.turn.number)
    a.modes = sorted(a.modes)  # (printed order, 608.2c: ``a.targets`` then follows the modes in that order)
    modes = casting.choose_modes(plan, a, definition, what, exclude=done)
    if modes is None:
        return None
    specs = [definition["modes"][i]["target"] for i in modes]
    slots = casting.choose_slot_targets(plan, a, specs, what)
    if slots is None:
        return None
    return Announced(targets=casting.ChosenTargets(flat=[t for slot in slots for t in slot]), modes=modes, slots=slots,
                     specs=specs, effects=mode_effects(definition, modes), definition=definition, index=index)


def announced(plan: Plan, ability_id: str, card: CardInstance, found: Announced, oid: str) -> None:
    """The ability is on the stack: the modes chosen are public (601.2b) and, for "hasn't been chosen",
    remembered for that ability of that object."""
    remember(plan.rules, oid, found.index, found.definition["modal"]["memory"], plan.state.turn.number, found.modes)
    plan.do({"type": "set_stack_info", "card_id": ability_id,
             "modes": _public_texts(plan, card.id, found.definition, found.modes)}, actor=plan.actor)
