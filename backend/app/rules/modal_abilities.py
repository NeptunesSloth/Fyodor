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
(the coverage module's SUPPORTED_MODAL_ABILITIES lists the forms, each tested). Read since wave 3R1
(tests/test_rules_refused_r1.py): "choose one at random" (a triggered ability: picked among the modes that
can be chosen as it goes on the stack, public — the Umaro ruling), "Each mode must target a different
player." (every mode targets a player of one kind), "Choose one. If [condition], [you may] choose both
instead." (checked as it goes on the stack — the Prophetic Titan ruling), reflexive "When you do, choose …"
(603.12: the modes belong to the reflexive ability, announced as IT goes on the stack). Refused (never
guessed): "choose X" / "up to X", "choose two at random", a mode with "you may", several targets or a
division (a mode has one target slot), a triggered ability's mode starting with "If" (Venser, Corpse Puppet
and Rankle and Torbran, the only such cards, need other grammar too), a header with anything else after it,
a limit or restriction line after the modes, and "up to" / "any number" on an activated ability (choosing
no mode isn't modelled there).

Definition shape (JSON-able, what ``scripts.definitions`` gives for the header line): the ability's
ordinary fields (``trigger`` / ``cond`` / ``if`` / ``limit``, or ``cost`` / ``restriction`` / ``loyalty``),
``"effects": []``, ``"modes": [{"text", "effects", "target": {"what": selector} | None}]`` and ``"modal":
{"min", "max", "repeat": False, "condition": None, "memory": None | "game" | "turn", "index", "form"}``. Each
bulleted line is ``{"kind": "mode", "of": <header index>, "form", "memory", "effects": []}``: it has no
behaviour, it only makes the line count as part of the ability (coverage, app/rules/engine.py).

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
    r"(?P<random> at random)?(?P<memory> that hasn['’]t been chosen(?: this turn)?)?(?P<end> —|\.)(?P<rest>.*)$")
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
    if m is not None and ab.kind == "triggered" and (rm := _REFLEXIVE.match(m["prefix"])) is not None:
        return _reflexive_definitions(ab, ch, rm["outer"], m)  # -- refused modal/conditional (wave 3R1) --
    # -- refused modal/conditional (wave 3R1) -- "choose one at random —"; "Choose one. If …, [you may] choose both
    # instead."; "Each mode must target a different player." after the header
    extra = _header_extra(ab, m) if m is not None else None
    if m is None or (extra is None and not _header_ok(ab, m["prefix"], m["end"], m["rest"].strip())):
        return {}
    if m["random"] and (ab.kind != "triggered" or m["count"] != "one" or m["memory"]):
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
    rest = "" if extra is not None else m["rest"].strip()
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
            # (it would read as an intervening "if" of the trigger, 603.4, not of the mode. Wave 3R1: kept refused —
            # the only two cards with such a mode, Venser, Corpse Puppet and Rankle and Torbran, need other grammar
            # too, so a reading of it couldn't be tested with a real card)
            return {}
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
    if m["random"]:
        modal["random"] = True  # -- refused modal/conditional (wave 3R1) --
    if extra is not None:  # -- refused modal/conditional (wave 3R1) --
        if "different_players" in extra:
            whats = {str((x["target"] or {}).get("what")) for x in modes}
            if len(whats) != 1 or any(x["target"] is None for x in modes) or not _player_selector(next(iter(whats))):
                return {}  # (only modes that all target a player of the same kind)
            modal["different_players"] = True
        if "instead" in extra:
            if n != 2 or m["count"] != "one" or ab.kind != "triggered":
                return {}
            modal["instead"] = extra["instead"]
    out: dict[int, Definition] = {ab.index: {**shape, "effects": [], "target": None, "optional": False,
                                              "modes": modes, "modal": modal}}
    for bullet in bullets:
        out[bullet.index] = {"kind": "mode", "of": ab.index, "form": ab.kind, "memory": memory, "effects": []}
    return out


# -- refused modal/conditional (wave 3R1) --
_BOTH_INSTEAD = re.compile(r"^If (?P<c>.+), (?P<may>you may )?choose both instead\.$")
_KICKED_CONDITION = re.compile(r"^(?:it|this spell|~) was kicked$")


def _header_extra(ab: AbilityText, m: re.Match[str]) -> dict[str, Any] | None:
    """What a triggered ability's header says after "Choose one." that the engine reads: "If [condition], [you may]
    choose both instead." (the condition checked as the ability is put on the stack, the Prophetic Titan ruling;
    "it was kicked": the spell a "When you cast this spell" ability is about, 702.33d) or "Each mode must target a
    different player." — or None (anything else: see _header_ok)."""
    from app.rules import conditions

    if ab.kind != "triggered" or m["end"] != "." or not _header_ok(ab, m["prefix"], " —", ""):
        return None
    rest = m["rest"].strip()
    if rest == "Each mode must target a different player.":
        return {"different_players": True}
    both = _BOTH_INSTEAD.match(rest)
    if both is None:
        return None
    cond = ({"object": "self", "cast": {"kicked": True}} if _KICKED_CONDITION.match(both["c"])
            else conditions.parse(both["c"], objects=True))
    if cond is None or set(conditions.objects_in(cond)) - {"self"}:
        return None  # (a condition about another object: which one isn't read here)
    return {"instead": {"cond": cond, "min": 1 if both["may"] else 2, "max": 2}}


_PLAYER_WHATS = frozenset({"player", "opponent"})


def _player_selector(what: str) -> bool:
    """"target player" / "target opponent" (the plain player selectors)."""
    return what in _PLAYER_WHATS
# -- end refused modal/conditional (wave 3R1) --


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


# -- refused modal/conditional (wave 3R1) -- "Whenever you attack, you may sacrifice another creature. When you do,
# choose two —" (Caesar, Legion's Emperor): the modes belong to a reflexive triggered ability (603.12), announced as
# IT is put on the stack (603.3c) — after the payment, never with the ability that created it.
_REFLEXIVE = re.compile(r"^(?P<outer>.+?\.) When you do, $")
_NEUTRAL_HEADER = "At the beginning of your upkeep, "  # (a trigger with no object: "it" in a mode isn't read)


def _reflexive_definitions(ab: AbilityText, ch: Characteristics, outer: str, m: re.Match[str]) -> dict[int, Definition]:
    from app.rules import scripts

    if m["end"] != " —" or m["rest"].strip() or m["memory"]:
        return {}
    bullets = _bullets(ch, ab.index)
    lo, top = _COUNTS[m["count"]]
    n = len(bullets)
    hi = n if top is None else min(top, n)
    if n < 2 or lo > n or lo == 0 or (m["count"] == "one or both" and n != 2):
        return {}
    after = next((x for x in ch.abilities if x.index == bullets[-1].index + 1), None)
    if after is not None and _TRAILER.match(after.text):
        return {}
    probe = AbilityText(index=ab.index, kind=ab.kind, cost=ab.cost, text=f"{outer} When you do, draw a card.")
    d = scripts.define(probe, ch)
    if d is None or d.get("kind") != "triggered" or not d["effects"] or d["effects"][-1]["do"] != "reflexive" \
            or d["effects"][-1]["ability"]["effects"] != [{"do": "draw", "who": "you", "n": 1}] or d.get("modes"):
        return {}
    modes: list[Definition] = []
    for k, bullet in enumerate(bullets):
        text = bullet.text[2:].strip()
        body = _MODE_LABEL.sub("", text, count=1)
        if body.lower().startswith("if "):
            return {}
        one = scripts.define(AbilityText(index=ab.index, kind="triggered", cost=None, text=_NEUTRAL_HEADER + body), ch)
        if one is None or one["kind"] != "triggered" or one.get("optional") or one.get("targets") or one.get("if") is not None \
                or one.get("limit") or not one["effects"]:
            return {}
        modes.append({"text": text, "effects": scripts.rename_bindings(one["effects"], f"m{k}_"), "target": one["target"]})
    modal = {"min": lo, "max": hi, "repeat": False, "condition": None, "memory": None, "index": ab.index, "form": "triggered"}
    ability = {"kind": "triggered", "trigger": "reflexive", "effects": [], "target": None, "optional": False,
               "modes": modes, "modal": modal}
    out: dict[int, Definition] = {ab.index: {**d, "effects": [*d["effects"][:-1], {**d["effects"][-1], "ability": ability}]}}
    for bullet in bullets:
        out[bullet.index] = {"kind": "mode", "of": ab.index, "form": "triggered", "memory": None, "effects": []}
    return out
# -- end refused modal/conditional (wave 3R1) --


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
def _key(oid: str, index: int, memory: str, turn: int, face: int = 0) -> str:
    """The memory of one ability: its index on the face that is up (a double-faced permanent is one object, but
    its faces' abilities are different abilities), for the game or for one turn."""
    slot = str(index) if not face else f"{index}.{face}"
    return f"{oid}:{slot}:game" if memory == "game" else f"{oid}:{slot}:t{turn}"


def chosen_before(rules: RulesState, oid: str, index: int, memory: str | None, turn: int, face: int = 0) -> tuple[int, ...]:
    """The modes already chosen for this ability of this object ("this turn": in ``turn``)."""
    return tuple(rules.modes_chosen.get(_key(oid, index, memory, turn, face), ())) if memory else ()


def _alive(rules: RulesState, key: str) -> bool:
    """Does the object a memory belongs to still exist (or did it just leave: its last known
    information is kept for a little while, 608.2h)?"""
    oid = key.rsplit(":", 2)[0]
    card_id = oid.rpartition(".")[0]
    return oid in rules.lki or rules.object_id(card_id) == oid


def remember(rules: RulesState, oid: str, index: int, memory: str | None, turn: int, modes: list[int],
             face: int = 0) -> None:
    """These modes were chosen for this ability of this object, as it was put on the stack. Earlier
    turns' memory and that of objects that are gone (400.7) is dropped: nothing reads it any more."""
    if memory is None:
        return
    rules.modes_chosen = {k: v for k, v in rules.modes_chosen.items()
                          if k.endswith(f":t{turn}") or (k.endswith(":game") and _alive(rules, k))}
    key = _key(oid, index, memory, turn, face)
    rules.modes_chosen[key] = sorted({*rules.modes_chosen.get(key, ()), *modes})


# -- what is announced -----------------------------------------------------------------------------------
def printed_order(definition: Definition, modes: list[int], targets: list[str]) -> tuple[list[int], list[str]]:
    """``modes`` in printed order (608.2c: the instructions are followed in the order written, whatever the
    order the modes were chosen in), with the targets given for them kept with their modes: ``targets`` has one
    per chosen mode that has a target, in the order the modes were given. Raises ActionError when only some
    targets were given for modes out of order (which modes they belong to would be a guess)."""
    if modes == sorted(modes):
        return list(modes), list(targets)
    specs = definition["modes"]
    if any(specs[i].get("groups") for i in modes):  # -- static_other sweep (wave 16B) -- a mode with several target groups: which are whose?
        if targets:
            raise ActionError("List the modes in printed order when you give targets for a mode with several targets")
        return sorted(modes), []
    need = [i for i in modes if specs[i]["target"]]
    if len(targets) > len(need):
        return sorted(modes), list(targets)  # (too many: the target choice refuses them)
    given = iter(targets)
    pairs = [(i, next(given, None) if specs[i]["target"] else None) for i in modes]
    if targets and len(targets) < len(need):
        raise ActionError("List the modes in printed order when you give only some of their targets")
    ordered = sorted(pairs, key=lambda pair: pair[0])
    return [i for i, _ in ordered], [t for _, t in ordered if t is not None]


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


def _face(plan: Plan, t: PendingTrigger) -> int:
    """The face of its source that has the ability: as it last was if it left (608.2h), else as it is."""
    snap = plan.rules.lki.get(t.source_object)
    card = plan.state.cards.get(t.source_card)
    return snap.face if snap is not None else card.face if card is not None else 0


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
        done = chosen_before(r, t.source_object, modal["index"], modal["memory"], plan.state.turn.number, _face(plan, t))
        allowed = [i for i, m in enumerate(modes) if i not in done and (not m["target"] or legal(i))]
        lo, hi = modal["min"], min(modal["max"], len(allowed))
        # -- refused modal/conditional (wave 3R1) --
        if modal.get("instead") is not None and _instead_holds(plan, t, modal["instead"]["cond"]):
            lo, hi = modal["instead"]["min"], min(modal["instead"]["max"], len(allowed))
        if modal.get("different_players") and allowed:  # each chosen mode needs a player no other one targets
            hi = min(hi, len(legal(allowed[0])))
        if not allowed or len(allowed) < lo or hi < lo:  # 700.2b: no mode can be chosen: removed from the stack
            _remove(plan, t, "has no mode that can be chosen")
            return True
        if modal.get("random"):  # "choose one at random": among the modes that can be chosen (Umaro ruling), public
            import secrets

            pick = (plan.rng or secrets.SystemRandom()).choice(allowed)
            plan.note(f"{_name(plan, t)}: mode chosen at random — {_public_texts(plan, t.source_card, d, [pick])[0]}")
            return put_trigger(plan, t, {"modes": [pick], "targets": []})
        # -- end refused modal/conditional (wave 3R1) --
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
        if modal.get("different_players"):  # -- refused modal/conditional (wave 3R1) -- not a player already chosen
            options = [x for x in options if x not in targets]
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
    from app.rules.triggers import cast_x, targeted

    r, d = plan.rules, t.ability
    specs = [d["modes"][i]["target"] for i in chosen]
    slots = _slots(specs, picked, plan)
    flat = [x for slot in slots for x in slot]
    r.pending_triggers = [p for p in r.pending_triggers if p.id != t.id]
    source = t.source_card if t.source_card in plan.state.cards else None
    who = _name(plan, t)
    text = f"{who}’s ability" if who != "A triggered ability" else "Triggered ability"  # (a hidden source isn't named)
    created = plan.do({"type": "create_ability", "text": text, "source_id": source, "kind": "triggered"}, actor=t.controller)
    new_ids = getattr(created, "r", None)
    ability_id = new_ids.ids[0] if new_ids is not None else None
    if ability_id is None:
        return True
    r.stack[ability_id] = StackEntry(kind="trigger", controller=t.controller, source_card=t.source_card,
                                     source_object=t.source_object, name=t.name, effects=mode_effects(d, chosen),
                                     targets=flat, target_spec=None, event=t.event, modes=chosen, slots=slots,
                                     slot_specs=specs, x=cast_x(plan, t))  # (x: wave 4J, 107.3m)
    remember(r, t.source_object, d["modal"]["index"], d["modal"]["memory"], plan.state.turn.number, chosen, _face(plan, t))
    plan.do({"type": "set_stack_info", "card_id": ability_id, "modes": _public_texts(plan, t.source_card, d, chosen)},
            actor=t.controller)
    if flat:
        plan.target_arrows(ability_id, [x.id for x in flat], actor=t.controller)
        targeted(plan, ability_id, t.controller, flat)
    return True


# -- refused modal/conditional (wave 3R1) --
def _instead_holds(plan: Plan, t: PendingTrigger, cond: dict[str, Any]) -> bool:
    """"If [condition], choose both instead.": checked as the ability is put on the stack (the Prophetic Titan
    ruling: a later change doesn't take the second mode away)."""
    from app.rules import conditions

    ctx = {"controller": t.controller, "source_card": t.source_card, "source_object": t.source_object,
           "event": t.event.model_dump(mode="json") if t.event is not None else None}
    return conditions.holds(plan, ctx, cond)
# -- end refused modal/conditional (wave 3R1) --


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
    done = chosen_before(plan.rules, oid, index, modal["memory"], plan.state.turn.number, card.face)
    a.modes, a.targets = printed_order(definition, a.modes, a.targets)  # (608.2c: the targets go with their modes)
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
    remember(plan.rules, oid, found.index, found.definition["modal"]["memory"], plan.state.turn.number, found.modes, card.face)
    plan.do({"type": "set_stack_info", "card_id": ability_id,
             "modes": _public_texts(plan, card.id, found.definition, found.modes)}, actor=plan.actor)
