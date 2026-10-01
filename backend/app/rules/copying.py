"""The copy system (CR 707, 613.2 layer 1), researched against CR 2026-09-25.

One model for every kind of copy: a **recipe** (``CopyRecipe``, app/game/rules_state.py) — the
printed values of a card (the face that is up, 707.8) or the values a token's creating effect
defined (111.3), then each copy effect's exceptions in order (707.9). Never a snapshot of a live
object: counters, status and non-copy effects aren't copied (707.2), a later change to the
original doesn't reach the copy (707.2b), and a copy of a copy starts from the first copy's recipe
and adds its own exceptions (707.3).

* **Layer 1** (613.2): a copy effect is a ``ContinuousEffect`` with ``layer="1"`` and ``copy`` set,
  locked to the objects it affects (400.7); the latest by timestamp gives an object's copiable
  values (613.2a, 613.7). A face-down object keeps its face-down characteristics (613.2b, 708.2).
  :func:`layer1` is the first step of ``app.rules.layers.derive``; ``layers.copiable`` stops there
  (613.2c) and is what static abilities are read from, so a copy of an anthem works.
* **Copies of spells and abilities** (707.10): real stack objects. A spell copy is a card object on
  the stack (the ``copy_card`` table action: a spell, owned and controlled by the player who put it
  there, targetable and counterable like any spell); an ability copy is an ability object with the
  original's source (707.10b). Each gets a copy of the original's ``StackEntry``: its modes (700.2g),
  targets and their division (601.2d, 115.7f), X, kicker (702.33d), a triggered ability's trigger
  event. A copy isn't cast (no cast triggers, not counted by storm); the objects used to pay the
  original's costs are the copy's too, the mana isn't (707.10). "You may choose new targets"
  (707.10c, 115.7d): for each target, keep it (even if illegal now) or choose a new legal one; a
  division stays as announced (115.7f); the final set must obey 115.3 and "another target", else
  the choice starts over. A copy of a permanent spell becomes a token as it resolves (608.3f,
  707.10f). "Can't be copied" (113.6g) is obeyed. Storm (702.40) uses this path.
* **Token copies** ("create a token that's a copy of …"): one helper, :func:`token_copy_request`,
  on the token choke point (``replace.create_token_batch``: the ``create_token`` table action, then
  the entry replacements of app/rules/replacements.py), with the copy effect on each token before
  anything looks at it; a 616.1 order prompt pauses :func:`token_copy`, which runs again with it.
* **Entering as a copy** (707.5, 614.1c, 614.12a): a replacement effect whose choice is made
  before the permanent enters (:func:`entering`, called by ``replacements.entry_plan``); the
  permanent's other entry replacements are then read from the copied text (707.5), its "as
  enters" choices are made anew (707.6) and its enters abilities trigger. The copy effect is
  locked to the object the card becomes on the battlefield.
* **Becoming a copy** (707.4): a layer-1 effect on a permanent already there: no enters or leaves
  abilities trigger, and its other effects keep applying.

Refused — the engine asks for the copy to be made by hand, never guesses: face-down sources
(707.2, 708.2), double-faced or melded sources of token copies and of permanent-spell copies
(707.8a, 707.10g), Aura spells, "for each player or object it could target" (707.10d), a copy
that specifies its new target (707.10e), casting a copy (707.12), Garth One-Eye and Magar of the
Magic Strings (707.13-707.14), exceptions that are additional effects (707.9e) and copies of
linked abilities (707.7) — the grammar doesn't read those wordings, so the cards stay manual.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal

from app.game.rules_state import (
    ENTERING_COPY,
    CopyExcept,
    CopyRecipe,
    DecisionOption,
    StackEntry,
    TargetRef,
    copy_recipe_of,
    emit,
)
from app.game.state import CardInstance, TokenDef
from app.rules import characteristics as chars
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.oracle import parse_abilities

if TYPE_CHECKING:
    from app.game.rules_state import RulesState
    from app.game.state import GameState
    from app.rules.plan import Plan

Context = dict[str, Any]
Job = dict[str, Any]
Position = tuple[str, int, int]  # ("plain" | "slot" | "group", slot or group, index)

ENTERING = ENTERING_COPY  # ContinuousEffect.source of the copy effect of a permanent entering as a copy
TO_COPY = " to copy"  # the end of an "enter as a copy" choice's name ("creature to copy")
NONE = "none"  # the answer "copy nothing" (the permanent enters as itself)
DOUBLE_FACED = ("transform", "modal_dfc", "meld", "reversible_card")
_CH_CACHE: dict[str, Characteristics] = {}
_CH_MAX = 4000


# -- recipes and characteristics (707.2, 707.9, 613.2) ---------------------------------------------
def base_recipe(card: CardInstance) -> CopyRecipe:
    """The copiable values of an object no copy effect applies to: its printed values (the face
    that is up, 707.8) or, for a token without a printing, what its creating effect defined (111.3)."""
    token = None
    if card.token is not None and not card.card_id:
        t = card.token
        token = {"name": t.name, "power": t.power, "toughness": t.toughness, "colors": list(t.colors),
                 "type_line": t.type_line, "text": t.text}
    return CopyRecipe(printing=card.card_id, face=card.face, token=token, source=card.name[:200])


def recipe_of(plan: Plan, card: CardInstance) -> CopyRecipe:
    """707.2 / 707.3: this object's copiable values as a recipe to copy from — the recipe of the
    copy effect that applies to it (with that effect's exceptions), else its printed values."""
    found = copy_recipe_of(plan.rules, plan.oid(card))
    return found.model_copy(deep=True) if found is not None else base_recipe(card)


def with_excepts(recipe: CopyRecipe, excepts: list[CopyExcept]) -> CopyRecipe:
    """The recipe of a copy made with these exceptions (707.9a-b: they join the copiable values)."""
    kept = [ex for ex in excepts if ex != CopyExcept()]
    return recipe.model_copy(update={"excepts": [*recipe.excepts, *kept]}) if kept else recipe


def characteristics(recipe: CopyRecipe, info: CardInfo) -> Characteristics:
    """The characteristics a recipe defines: its base, then each exception in order (707.9)."""
    key = recipe.model_dump_json()
    hit = _CH_CACHE.get(key)
    if hit is not None:
        return hit
    ch = _base(recipe, info)
    for ex in recipe.excepts:
        ch = _apply(ch, ex)
    if len(_CH_CACHE) > _CH_MAX:
        _CH_CACHE.clear()
    _CH_CACHE[key] = ch
    return ch


def _base(recipe: CopyRecipe, info: CardInfo) -> Characteristics:
    if recipe.printing:
        data = info.get(recipe.printing)
        if data is not None:
            return chars.printed_from_data(data, recipe.face)
    if recipe.token is not None:
        t = recipe.token
        probe = CardInstance(id="copy-probe", owner="", controller="", zone="", is_token=True,
                             token=TokenDef(name=str(t.get("name") or ""), power=t.get("power"), toughness=t.get("toughness"),
                                            colors=list(t.get("colors") or []), type_line=str(t.get("type_line") or ""),
                                            text=str(t.get("text") or "")))
        return chars.of(probe, info)
    return Characteristics(name=recipe.source)  # (unknown to the card database: typeless, as chars.of)


def _apply(ch: Characteristics, ex: CopyExcept) -> Characteristics:
    """One copy effect's exceptions (707.9a-d)."""
    from app.rules import scripts
    from app.rules.layers import _subtype_fits

    kept = [a for a in ch.abilities if not a.intrinsic]
    rewrite = bool(ex.add_text)
    if ex.power is not None or ex.toughness is not None:
        # 707.9d: a characteristic-defining ability that defines the power and toughness isn't copied
        cda = {i for i, d in scripts.definitions(ch).items() if d.get("static") == "cda"}
        if cda:
            kept = [a for a in kept if a.index not in cda]
            rewrite = True
    supertypes = (ch.supertypes | frozenset(ex.add_supertypes)) - frozenset(ex.remove_supertypes)
    types = ch.types | frozenset(ex.add_types)
    subtypes = frozenset(s for s in ch.subtypes | frozenset(ex.add_subtypes) if _subtype_fits(s, types))
    text = "\n".join([*(a.text for a in kept), *ex.add_text]) if rewrite else ch.oracle_text
    if rewrite:
        abilities = chars.with_intrinsic_mana(parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"})), subtypes)
    elif subtypes != ch.subtypes:
        abilities = chars.with_intrinsic_mana(kept, subtypes)
    else:
        abilities = ch.abilities
    return replace(ch, name=ex.name if ex.name is not None else ch.name, supertypes=supertypes, types=types,
                   subtypes=chars.changeling(subtypes, abilities),
                   power=ex.power if ex.power is not None else ch.power,
                   toughness=ex.toughness if ex.toughness is not None else ch.toughness,
                   colors=(frozenset(ex.set_colors) if ex.set_colors is not None else ch.colors) | frozenset(ex.add_colors),
                   oracle_text=text, abilities=abilities, oracle_id=None if rewrite else ch.oracle_id)


def type_line(ch: Characteristics) -> str:
    left = " ".join([*sorted(ch.supertypes), *sorted(ch.types)])
    return f"{left} — {' '.join(sorted(ch.subtypes))}" if ch.subtypes else left


# -- layer 1 (613.2) ------------------------------------------------------------------------------
def layer1(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """613.2a: the copy effect that applies to the object gives its copiable values (the latest
    by timestamp, 613.7); 613.2b: a face-down object keeps its face-down characteristics (708.2),
    which ``characteristics.of`` already gave. ``ch`` is the object's printed (or defined) values."""
    r = state.rules
    if r is None or not r.effects or info is None or card.face_down:
        return ch
    recipe = copy_recipe_of(r, r.object_id(card.id))
    return ch if recipe is None else characteristics(recipe, info)


def copy_index(rules: RulesState | None) -> dict[str, tuple[int, str]]:
    """Object id → (timestamp, recipe) of the latest copy effect that applies to it (for caches keyed
    by what's on the battlefield: a copy effect changes an object's abilities, 613.2a). The recipe is
    part of the key: after an undo, a new choice can reuse the same object id and timestamp."""
    out: dict[str, tuple[int, str]] = {}
    if rules is None:
        return out
    for e in rules.effects:
        if e.layer == "1" and e.copy_recipe is not None:
            for oid in e.affected:
                if oid not in out or e.timestamp >= out[oid][0]:
                    out[oid] = (e.timestamp, e.copy_recipe.model_dump_json())
    return out


def lki(plan: Plan, snap: Any, ch: Characteristics) -> Characteristics:
    """An object's last known information (608.2h) with its copiable values as they were: a dying
    Clone has the copied abilities (603.10a). ``snap`` is its ObjectSnapshot."""
    recipe = getattr(snap, "copy_recipe", None)
    if recipe is None or snap.face_down:
        return ch
    return characteristics(recipe, plan.info)


def add_copy_effect(plan: Plan, affected: list[str], recipe: CopyRecipe, controller: str, *,
                    duration: Literal["end_of_turn", "permanent"] = "permanent", source: str | None = None) -> None:
    """A layer-1 copy effect (613.2a) on these objects, timestamped now (613.7)."""
    from app.rules import layers

    layers.add_effect(plan, affected=affected, layer="1", source=source, controller=controller, duration=duration,
                      label=f"Copy of {recipe.source}" if recipe.source else "Copy", copy_recipe=recipe)


def supported_source(plan: Plan, card: CardInstance, *, token: bool = False) -> str | None:
    """Why this object's copiable values aren't copied automatically (None: they are). Face-down
    objects (707.2: a copy of one is a nameless 2/2 — not modelled), and for a token or a copy of
    a permanent spell, double-faced ones (707.8a, 707.10g: the copy would be double-faced too)."""
    if card.face_down:
        return "a face-down object (707.2)"
    data = plan.info.get(card.card_id) if card.card_id else None
    layout = (data or {}).get("layout")
    if layout == "meld" and card.face:
        return "a melded permanent (707.8)"
    if token and layout in DOUBLE_FACED:
        return "a double-faced object (707.8a)"
    return None


# -- copying spells and abilities (707.10) --------------------------------------------------------------
def new_job(ctx: Context | None, *, controller: str, objects: list[tuple[str, str, int]], retarget: bool,
            label: str, excepts: list[CopyExcept] | None = None) -> Job:
    """A copying in progress, as JSON (it waits in a decision's resume): the objects to copy (card,
    the object it must still be, how many copies), who controls the copies, whether new targets
    may be chosen (707.10c), and the resolving ability's context to go on with afterwards."""
    return {"ctx": ctx, "controller": controller, "retarget": retarget, "label": label, "mode": None,
            "excepts": [ex.model_dump(mode="json") for ex in excepts or [] if ex != CopyExcept()],
            "queue": [{"object": c, "oid": oid, "left": n} for c, oid, n in objects if n > 0]}


def run(plan: Plan, job: Job) -> bool:
    """Put the job's copies on the stack, one after another (each on top, 707.10). True when
    they're all there (the caller goes on); False while a decision is pending — its resume goes on
    with the job, then with the resolving ability (``job["ctx"]``)."""
    while job["queue"]:
        cur = job["queue"][0]
        card = plan.state.cards.get(cur["object"])
        if card is None or card.zone != "stack" or plan.oid(card) != cur["oid"]:
            plan.note(f"{job['label']}: the spell or ability to copy is no longer on the stack", actor=job["controller"])
            _next(job)
            continue
        refused = uncopyable(plan, card)
        if refused is not None:
            _next(job)
            if refused:
                _manual(plan, job, refused)
                return False
            continue
        entry = plan.rules.stack.get(card.id)
        choosing = job["retarget"] and entry is not None and bool(positions(entry))
        if choosing and job["mode"] is None and cur["left"] > 1:
            name = entry.name if entry is not None and entry.name else card.name or "it"
            plan_decide(plan, player=job["controller"], kind="choose_one", prompt=f"{job['label']}: {cur['left']} copies of {name}",
                        options=[DecisionOption(id="same", label="Keep the targets for every copy"),
                                 DecisionOption(id="choose", label="Choose new targets for each copy")],
                        resume={"step": "copy_mode", "job": job})
            return False
        copy_id = make_copy(plan, card, job["controller"], [CopyExcept.model_validate(x) for x in job["excepts"]])
        same = job["mode"] == "same"
        cur["left"] -= 1
        if cur["left"] <= 0:
            _next(job)
        if copy_id is None:
            continue
        if choosing and not same:
            if ask_targets(plan, job, copy_id, []):
                return False
            continue
        finalize(plan, copy_id, job["controller"])
    return True


def _next(job: Job) -> None:
    job["queue"].pop(0)
    job["mode"] = None


def plan_decide(plan: Plan, **kw: Any) -> None:
    from app.rules.plan import decide

    decide(plan, **kw)


def _manual(plan: Plan, job: Job, prompt: str) -> None:
    plan_decide(plan, player=job["controller"], kind="manual_resolution", prompt=prompt[:300],
                options=[DecisionOption(id="done", label="Done")], resume={"step": "copy_manual", "job": job})


def go_on(plan: Plan, job: Job) -> None:
    """The copies are on the stack: the resolving spell or ability goes on (608.2c)."""
    if job.get("ctx") is not None:
        from app.rules.effects import continue_effects

        continue_effects(plan, job["ctx"])


def resume_mode(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    job["mode"] = chosen[0]
    if run(plan, job):
        go_on(plan, job)


def resume_manual(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    plan.note(f"{plan.name(d.player)} finished the copy by hand", actor=d.player)
    if run(plan, job):
        go_on(plan, job)


def uncopyable(plan: Plan, card: CardInstance) -> str | None:
    """None: the engine copies this spell or ability. "": it can't be copied (113.6g), nothing
    happens. Otherwise: why the copy is made by hand (the prompt of that manual step)."""
    if card.ability is not None:
        if re.search(r"\bcan't be copied\b", card.ability.text, re.IGNORECASE):
            plan.note(f"{card.ability.source_name or 'That ability'}: this ability can't be copied (113.6g)", actor=plan.actor)
            return ""
        return None
    if card.face_down:
        return "Copying a face-down spell isn't automated (707.2): make the copy by hand, then press Done"
    ch = plan.ch(card)
    if any(re.search(r"\bcan't be copied\b", a.text, re.IGNORECASE) for a in ch.abilities):
        plan.note(f"{ch.name or 'That spell'} can't be copied (113.6g)", [card.id], actor=plan.actor)
        return ""
    if "Aura" in ch.subtypes:
        return f"Copying an Aura spell ({ch.name}) isn't automated: make the copy by hand, then press Done"
    if ch.is_permanent_card and supported_source(plan, card, token=True) is not None:
        return f"Copying {ch.name}, a double-faced permanent spell, isn't automated (707.10g): make the copy by hand, then press Done"
    return None


def make_copy(plan: Plan, card: CardInstance, controller: str, excepts: list[CopyExcept]) -> str | None:
    """Put one copy of this spell or ability onto the stack under ``controller``'s control (707.10)."""
    if card.ability is not None:
        return _copy_ability(plan, card, controller)
    return _copy_spell(plan, card, controller, excepts)


def _copy_spell(plan: Plan, card: CardInstance, controller: str, excepts: list[CopyExcept]) -> str | None:
    r = plan.rules
    orig_oid = plan.oid(card)
    entry = r.stack.get(card.id)
    recipe = with_excepts(recipe_of(plan, card), excepts)
    created = plan.do({"type": "copy_card", "card_id": card.id, "player": controller, "count": 1}, actor=controller)
    new_ids = getattr(created, "r", None)
    if new_ids is None or not new_ids.ids:
        return None
    copy_id = new_ids.ids[0]
    oid = plan.oid(copy_id)
    add_copy_effect(plan, [oid], recipe, controller)
    if entry is not None:
        r.stack[copy_id] = _entry_copy(entry, controller=controller, source=(copy_id, oid), orig=orig_oid)
    _payment_alias(plan, orig_oid, oid, copy_id, controller)
    info = card.stack_info
    payload: dict[str, Any] = {"type": "set_stack_info", "card_id": copy_id,
                               "tags": ["Copy", *(t for t in (info.tags if info else []) if t.startswith(("Kicked", "Evoked")))]}
    if info is not None and info.x is not None:
        payload["x"] = info.x
    if info is not None and info.modes:
        payload["modes"] = list(info.modes)
    plan.do(payload, actor=controller)
    # 707.10: the copy has the original's alternative costs: an evoked or dashed permanent spell's
    # copy is too (702.74a, 702.109a)
    for marks in (r.evoked, r.dashed):
        if card.id in marks:
            marks.append(copy_id)
    emit(plan.state, "spell_copied", object_id=oid, card=copy_id, player=controller, source=orig_oid)
    return copy_id


def _copy_ability(plan: Plan, card: CardInstance, controller: str) -> str | None:
    r = plan.rules
    ab = card.ability
    assert ab is not None
    orig_oid = plan.oid(card)
    entry = r.stack.get(card.id)
    source = ab.source_id if ab.source_id and ab.source_id in plan.state.cards else None
    created = plan.do({"type": "create_ability", "text": (ab.text or "Ability")[:500], "source_id": source, "kind": ab.kind},
                      actor=controller)
    new_ids = getattr(created, "r", None)
    if new_ids is None or not new_ids.ids:
        return None
    copy_id = new_ids.ids[0]
    oid = plan.oid(copy_id)
    if entry is not None:  # 707.10b: the same source as the original
        r.stack[copy_id] = _entry_copy(entry, controller=controller, source=None, orig=orig_oid)
    _payment_alias(plan, orig_oid, oid, copy_id, controller)
    if card.stack_info is not None and card.stack_info.x is not None:
        plan.do({"type": "set_stack_info", "card_id": copy_id, "x": card.stack_info.x, "tags": ["Copy"]}, actor=controller)
    return copy_id


def _entry_copy(entry: StackEntry, *, controller: str, source: tuple[str, str] | None, orig: str) -> StackEntry:
    """The copy's rules metadata: everything decided for the original (707.10, 700.2g, 601.2d)."""
    out = entry.model_copy(deep=True)
    out.controller = controller
    if source is not None:  # a spell copy is itself the spell ("~ deals 3 damage": the copy deals it)
        out.source_card, out.source_object = source
    out.copy_of = orig
    return out


def _payment_alias(plan: Plan, orig_oid: str, oid: str, copy_id: str, controller: str) -> None:
    """707.10: an effect of the copy that refers to objects used to pay its costs uses the objects
    that paid for the original (the sacrificed creature, the creatures that convoked it); mana
    isn't an object and isn't copied (the Dawnglow Infusion example), nor is life."""
    record = plan.rules.payments.get(orig_oid)
    if record is not None:
        plan.rules.payments[oid] = record.model_copy(
            deep=True, update={"card": copy_id, "controller": controller, "mana_spent": {}, "life": 0, "tapped": [],
                               "total_cost": "", "cast_from": None, "cast_main": False})  # (wave 3R1: a copy wasn't cast)


# -- choosing new targets (707.10c, 115.7d-f) ------------------------------------------------------
def positions(entry: StackEntry) -> list[Position]:
    """Every target of a spell or ability, in order: each chosen mode's (700.2c), each target
    group's (601.2c), or its one plain target."""
    if entry.slot_specs:
        return [("slot", k, i) for k, (refs, spec) in enumerate(zip(entry.slots, entry.slot_specs, strict=False)) if spec
                for i in range(len(refs))]
    if entry.group_specs:
        return [("group", g, i) for g, refs in enumerate(entry.groups) for i in range(len(refs))]
    if entry.target_spec and entry.targets:
        return [("plain", 0, i) for i in range(len(entry.targets))]
    return []


def _spec(entry: StackEntry, pos: Position) -> dict[str, Any]:
    kind, g, _ = pos
    spec = entry.slot_specs[g] if kind == "slot" else entry.group_specs[g] if kind == "group" else entry.target_spec
    return spec or {}


def _current(entry: StackEntry, pos: Position) -> TargetRef:
    kind, g, i = pos
    return (entry.slots[g] if kind == "slot" else entry.groups[g] if kind == "group" else entry.targets)[i]


def _retargeted(entry: StackEntry, pos: list[Position], refs: list[TargetRef]) -> StackEntry:
    out = entry.model_copy(deep=True)
    for (kind, g, i), ref in zip(pos, refs, strict=True):
        if kind == "slot":
            out.slots[g][i] = ref
        elif kind == "group":
            out.groups[g][i] = ref
        else:
            out.targets[i] = ref
    if out.slot_specs:
        out.targets = [t for slot in out.slots for t in slot]
    elif out.group_specs:
        out.targets = [t for grp in out.groups for t in grp]
    return out


def _problem(plan: Plan, entry: StackEntry) -> str | None:
    """Is the final set of targets legal together (115.7d-e)? No object twice for one word
    "target" (115.3), "another target" not one of the earlier group's, one graveyard."""
    for g, (refs, spec) in enumerate(zip(entry.groups, entry.group_specs, strict=False)):
        ids = [t.id for t in refs]
        if len(set(ids)) != len(ids):
            return "the same target can't be chosen twice for one “target” (115.3)"
        banned = {t.id for d in spec.get("distinct_from") or [] if d < len(entry.groups) and d != g for t in entry.groups[d]}
        if banned & set(ids):
            return "“another target” can't be one of the other targets (115.3)"
        if spec.get("same_graveyard") and len({plan.state.cards[t].owner for t in ids if t in plan.state.cards}) > 1:
            return "those targets must be in a single graveyard"
    return None


def _options(plan: Plan, entry: StackEntry, pos: Position, controller: str, copy_id: str,
             taken: set[str]) -> list[DecisionOption]:
    from app.rules import selectors, targets

    spec = _spec(entry, pos)
    current = _current(entry, pos)
    legal = targets.legal_targets(plan, spec.get("what", "any"), controller, targets.source_of(plan, entry.source_card),
                                  entry.source_card, selectors.attacker_of(entry.event))
    keep = DecisionOption(id="keep", label=f"Keep {targets.label(plan, current.id)}"[:200],
                          card_id=current.id if current.id in plan.state.cards else None)
    # (115.5: a spell or ability on the stack is an illegal target for itself)
    return [keep, *(DecisionOption(id=x, label=targets.label(plan, x), card_id=x if x in plan.state.cards else None)
                    for x in legal if x not in (current.id, copy_id) and x not in taken)]


def ask_targets(plan: Plan, job: Job, copy_id: str, picks: list[str]) -> bool:
    """707.10c: the copy's controller keeps or changes each target in turn (``picks``: the answers
    so far). True while a question is open; False once the copy has its targets."""
    from app.rules import targets

    entry = plan.rules.stack.get(copy_id)
    if entry is None:
        return False
    pos = positions(entry)
    controller = job["controller"]
    while len(picks) < len(pos):
        k = len(picks)
        kind, g, _ = pos[k]
        chosen = [(q, _current(entry, q).id if p == "keep" else p) for p, q in zip(picks, pos, strict=False)]
        # (115.3: not twice for this word "target", nor the object an earlier "another target" names)
        others = set(_spec(entry, pos[k]).get("distinct_from") or []) if kind == "group" else set()
        taken = {x for q, x in chosen if q[0] == kind and (q[1] == g or q[1] in others)}
        options = _options(plan, entry, pos[k], controller, copy_id, taken)
        if len(options) == 1:  # nothing else it could target: it keeps this one
            picks.append("keep")
            continue
        name = entry.name or "the spell"
        count = f" ({k + 1} of {len(pos)})" if len(pos) > 1 else ""
        plan_decide(plan, player=controller, kind="choose_one",
                    prompt=f"Copy of {name}: keep its target{count} or choose a new one (707.10c)", options=options,
                    resume={"step": "copy_target", "job": job, "copy": copy_id, "picks": picks})
        return True
    refs = [_current(entry, p) if pick == "keep" else targets.ref(plan, pick) for p, pick in zip(pos, picks, strict=True)]
    new = _retargeted(entry, pos, refs)
    problem = _problem(plan, new)
    if problem is not None:
        plan.note(f"Those targets aren't legal together: {problem}. Choose again", actor=controller)
        return ask_targets(plan, job, copy_id, [])
    plan.rules.stack[copy_id] = new
    finalize(plan, copy_id, controller)
    return False


def resume_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    if ask_targets(plan, job, d.resume["copy"], [*d.resume["picks"], chosen[0]]):
        return
    if run(plan, job):
        go_on(plan, job)


def finalize(plan: Plan, copy_id: str, controller: str) -> None:
    """The copy is on the stack with its targets: they become its targets (115.10, 603.2e: "becomes
    the target" triggers, ward), shown with an arrow."""
    from app.game.visibility import publicly_visible
    from app.rules.triggers import targeted

    entry = plan.rules.stack.get(copy_id)
    if entry is None or not entry.targets:
        return
    ids = [t.id for t in entry.targets
           if (t.id in plan.state.players and not plan.state.players[t.id].left)
           or (t.id in plan.state.cards and publicly_visible(plan.state, plan.state.cards[t.id]))]
    ids = list(dict.fromkeys(ids))
    if ids and len(plan.state.arrows) < 190:
        plan.do({"type": "create_arrow", "source": copy_id, "targets": ids, "kind": "target"}, actor=controller)
    targeted(plan, copy_id, controller, entry.targets)


# -- effect primitives ---------------------------------------------------------------------------------
def _retarget_follows(ctx: Context) -> bool:
    """"You may choose new targets for the copy." is the sentence right after the copy (a marker
    effect the grammar leaves there)."""
    effects = ctx.get("effects") or []
    k = int(ctx.get("next") or 0)
    return k < len(effects) and effects[k].get("do") == "copy_new_targets"


def _stack_objects(plan: Plan, ctx: Context, who: str) -> list[str]:
    from app.rules.effects import target_refs

    return [t["id"] for t in target_refs(ctx, who) if t and t["id"] in plan.state.cards
            and plan.state.cards[t["id"]].zone == "stack" and plan.oid(t["id"]) == t.get("object_id")]


def copy_stack_object(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Copy target instant or sorcery spell [, except …]" / "Copy target triggered ability you
    control" (707.10), then "You may choose new targets for the copy" (707.10c)."""
    from app.rules import values

    n = values.evaluate(plan, ctx, e.get("n", 1))
    excepts = [CopyExcept.model_validate(x) for x in e.get("excepts") or []]
    objects = [(sid, plan.oid(sid), n) for sid in _stack_objects(plan, ctx, e.get("who") or "target")]
    job = new_job(ctx, controller=ctx["controller"], objects=objects, retarget=_retarget_follows(ctx),
                  label=ctx.get("name") or "Copy", excepts=excepts)
    return run(plan, job)


def new_targets_marker(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    return True  # read by the copy before it (``_retarget_follows``)


def storm(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.40a: "copy it for each other spell that was cast before it this turn. If the spell has
    any targets, you may choose new targets for any of the copies." The spell must still be the
    object it was when it was cast (UNVERIFIED: whether storm copies a spell that has left the
    stack isn't in the CR; the engine doesn't)."""
    sid = e["spell"]
    card = plan.state.cards.get(sid)
    if card is None or card.zone != "stack" or plan.oid(sid) != e["object"] or plan.manual(card):
        plan.note("Storm: the spell is gone (or handled by hand), so there is nothing to copy")
        return True
    job = new_job(ctx, controller=ctx["controller"], objects=[(sid, e["object"], int(e["n"]))], retarget=True, label="Storm")
    return run(plan, job)


def resume_storm(plan: Plan, d: Any, chosen: list[str]) -> None:
    """A storm decision saved before this module existed ({"spell", "left", "mode"}): the same
    questions, now answered through the copy system."""
    r = d.resume
    ctx, sid = r["ctx"], r["spell"]
    card = plan.state.cards.get(sid)
    if card is None or card.zone != "stack":
        go_on(plan, {"ctx": ctx})
        return
    left = int(r["left"])
    job = new_job(ctx, controller=d.player, objects=[(sid, plan.oid(sid), left)], retarget=True, label="Storm")
    if r.get("mode") is None:
        job["mode"] = chosen[0]
    else:  # a target chosen for one copy (the old per-copy question)
        copy_id = make_copy(plan, card, d.player, [])
        job["queue"][0]["left"] -= 1
        job["mode"] = "choose"
        entry = plan.rules.stack.get(copy_id or "")
        if copy_id is not None and entry is not None and entry.target_spec and len(entry.targets) == 1:
            from app.rules.targets import ref

            plan.rules.stack[copy_id] = _retargeted(entry, [("plain", 0, 0)], [ref(plan, chosen[0])])
        if copy_id is not None:
            finalize(plan, copy_id, d.player)
        if job["queue"][0]["left"] <= 0:
            _next(job)
    if run(plan, job):
        go_on(plan, job)


# -- token copies ("create a token that's a copy of …") --------------------------------------------
def token_copy_request(plan: Plan, ctx: Context, controller: str, recipe: CopyRecipe, count: int, *,
                       tapped: bool = False, notes: list[str] | None = None
                       ) -> tuple[str, dict[str, Any], int, str | None, bool] | None:
    """THE one way the engine makes a token copy's creation request — for the token choke point
    (``replace.create_token_batch``): the copied object's printing (or a token's own definition,
    111.3) as the token's base, entering tapped if the copied text says so (614.1d), and the recipe
    (``_copy``) the token's layer-1 copy effect is made from before anything looks at it (707.2),
    then its "enters with" part (``replacements.after_entry``: counters, a planeswalker's loyalty,
    707.5). 111.5: a copy of an instant or sorcery card creates no token (None, a line in ``notes``)."""
    from app.rules import replacements

    if count <= 0:
        return None
    ch = characteristics(recipe, plan.info)
    if ch.is_instant_or_sorcery:
        (notes if notes is not None else []).append(f"No token is created: a copy of an instant or sorcery card (111.5, {ch.name})")
        return None
    if recipe.printing and plan.info.get(recipe.printing) is not None:
        spec: dict[str, Any] = {"card_id": recipe.printing, "name": (ch.name or "Token")[:80]}
    elif recipe.token is not None:
        spec = {k: recipe.token.get(k) for k in ("name", "power", "toughness", "colors", "type_line", "text")}
    else:
        (notes if notes is not None else []).append(f"{recipe.source or 'That object'} isn't in the card database: no copy is created")
        return None
    probe = {"name": ch.name, "power": ch.power, "toughness": ch.toughness, "colors": sorted(ch.colors),
             "type_line": type_line(ch), "text": ch.oracle_text}
    tapped = tapped or replacements.token_enters_tapped(plan, controller, probe)
    source = ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None
    # (the copy's types as it's created, for type-restricted token replacements — Ojer Taq; 614.16, 707.2)
    return (controller, {**spec, "type_line": probe["type_line"], "_copy": recipe.model_dump(mode="json")}, count, source, tapped)


def _entry_choice(plan: Plan, card_id: str) -> str | None:
    """An "As ~ enters, choose …" of a token copy's copied text (707.6: made anew): today's token
    path doesn't ask it, so it is left to the player."""
    from app.rules import scripts

    card = plan.state.cards.get(card_id)
    if card is None:
        return None
    for d in scripts.definitions(plan.ch(card)).values():
        if d.get("kind") == "replacement" and d.get("replacement") == "enters_choice":
            return str(next((e.get("what") for e in d.get("effects") or [] if e.get("what")), "value"))
    return None


def token_copy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Create a token that's a copy of target creature [, except …]" / "… of ~" / "… of it"
    (707.1; 111.4 example: its name is the copied object's): the copied object's copiable values
    as it is now (707.2; a card in a graveyard or exile: its printed values), plus the effect's
    exceptions (707.9). The tokens are recorded for "Sacrifice it at the beginning of the next
    end step" and friends."""
    from app.rules import effects, values
    from app.rules import replace as replace_

    count = values.evaluate(plan, ctx, e.get("n", 1))
    excepts = [CopyExcept.model_validate(x) for x in e.get("excepts") or []]
    requests: list[tuple[str, dict[str, Any], int, str | None, bool]] = []
    notes: list[str] = []
    refused: list[str] = []
    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        zone = card.zone.rsplit(":", 1)[-1]
        if zone in ("hand", "library", "stack"):
            continue  # (never a card in a hidden zone; a spell isn't what these copy)
        problem = supported_source(plan, card, token=True)
        if problem is None and "Aura" in plan.ch(card).subtypes:
            problem = "an Aura: it would have to attach as it enters, 303.4f"
        if problem is not None:
            refused.append(f"a copy of {plan.ch(card).name or 'it'} ({problem})")
            continue
        recipe = recipe_of(plan, card) if zone == "battlefield" else base_recipe(card).model_copy(update={"face": 0})
        req = token_copy_request(plan, ctx, ctx["controller"], with_excepts(recipe, excepts), count,
                                 tapped=bool(e.get("tapped")), notes=notes)
        if req is not None:
            requests.append(req)
    # one creation event per copied object, at once (616.1: the creator orders non-commuting
    # replacements — the choice pauses here and the whole instruction runs again with the answer,
    # so the tokens, the binding and the 707.6 check below all follow it)
    made: list[str] = []
    if requests:
        out = replace_.create_token_batch(plan, requests, ctx=ctx, bind=None, then=replace_.rerun_then(ctx, e))
        if out is None:
            return False
        made = out
    for n in notes:
        plan.note(n, actor=ctx["controller"])
    effects._remember(plan, ctx, e, made)
    for tid in made:
        what = _entry_choice(plan, tid)
        if what is not None:
            refused.append(f"the {what} chosen for the token copy of {plan.ch(plan.state.cards[tid]).name} (707.6)")
    if refused:
        _manual(plan, new_job(ctx, controller=ctx["controller"], objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                f"{ctx.get('name') or 'Copy'}: do this by hand — {'; '.join(refused)} — then press Done")
        return False
    return True


# -- entering as a copy (707.5, 614.1c, 614.12a) --------------------------------------------------
def _own(plan: Plan, card: CardInstance) -> Characteristics:
    """The entering card's characteristics without the copy effect it is entering with."""
    oid = plan.oid(card)
    best = None
    for e in plan.rules.effects:
        if e.layer == "1" and e.copy_recipe is not None and oid in e.affected and not (e.source or "").startswith(ENTERING) \
                and (best is None or e.timestamp > best.timestamp):
            best = e
    if best is not None and best.copy_recipe is not None:
        return characteristics(best.copy_recipe, plan.info)
    return chars.of(card, plan.info)


def enter_definition(plan: Plan, card: CardInstance) -> dict[str, Any] | None:
    """The card's own "You may have ~ enter as a copy of …" replacement effect, if any."""
    from app.rules import scripts

    if plan.manual(card) or card.face_down:
        return None
    for d in scripts.definitions(_own(plan, card)).values():
        if d.get("kind") == "replacement" and d.get("replacement") == "enter_as_copy":
            return d
    return None


def entry_candidates(plan: Plan, controller: str, what: str) -> list[str]:
    """What an entering permanent may copy ("any creature on the battlefield", "a creature or
    planeswalker you control"): objects on the battlefield (public), never a hidden one. Face-down
    ones (707.2) and Auras (they'd have to attach as they enter) aren't offered."""
    from app.rules import selectors

    sel = selectors.parse(what[: -len(TO_COPY)] if what.endswith(TO_COPY) else what)
    if sel is None or sel.player is not None:
        return []
    out = []
    for cid in selectors.candidates(plan, sel, controller):
        card = plan.state.cards[cid]
        if card.zone.endswith(":battlefield") and supported_source(plan, card) is None and "Aura" not in plan.ch(card).subtypes:
            out.append(cid)
    return out


def entry_options(plan: Plan, controller: str, what: str) -> list[DecisionOption]:
    """The options of an "enter as a copy" choice (614.12a), for ``effects._choice_options``."""
    ids = entry_candidates(plan, controller, what)
    if not ids:
        return []
    options = [DecisionOption(id=cid, label=f"{plan.ch(plan.state.cards[cid]).name or 'A permanent'} "
                                            f"({plan.name(plan.state.cards[cid].controller)})"[:200], card_id=cid) for cid in ids]
    return [*options, DecisionOption(id=NONE, label="Don't copy anything (it enters as itself)")]


def _drop_entering(plan: Plan, card: CardInstance) -> None:
    oid = plan.oid(card)
    r = plan.rules
    r.effects = [e for e in r.effects if not (e.layer == "1" and (e.source or "") == ENTERING + card.id and oid in e.affected)]


def entering(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str] | None, out: dict[str, Any]) -> bool:
    """``replacements.entry_plan``'s hook for "You may have ~ enter as a copy of …" (707.5, a
    replacement effect: 614.1c). Its choice is made before the permanent enters (614.12a): with no
    answer yet, ``out["choice"]`` asks for it and True stops the rest of the plan (asked through
    the usual entry-choice prompts). With an answer, the copy effect is set up — on the object as it
    is now, so the rest of the plan reads the permanent's other entry replacements from the copied
    text as it would exist on the battlefield (707.5, 614.12); it follows the card onto the
    battlefield, to the object it becomes there (``rules_state._diff``) — and False lets the plan
    go on. Nothing to copy: no choice, it enters as itself."""
    d = enter_definition(plan, card)
    if d is None:
        return False
    what = str(d["what"])
    answer = (answers or {}).get(what)
    _drop_entering(plan, card)
    if answer is None:
        if not entry_candidates(plan, controller, what):
            return False
        out["choice"] = {"what": what}
        return True
    if answer in ("", NONE):
        return False
    source = plan.state.cards.get(answer)
    if source is None or answer not in entry_candidates(plan, controller, what):
        plan.note(f"{card.name or 'It'}: what it was to copy is gone, so it enters as itself", actor=controller)
        return False
    excepts = [CopyExcept.model_validate(x) for x in d.get("excepts") or []]
    recipe = with_excepts(recipe_of(plan, source), excepts)
    # (on the object as it is now; it follows the card to the object it becomes as it enters,
    # whatever its number: rules_state._diff — never a predicted id, 400.7)
    add_copy_effect(plan, [plan.oid(card)], recipe, controller, source=ENTERING + card.id)
    return False


# -- becoming a copy (707.4) -------------------------------------------------------------------------
def become_copy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"~ becomes a copy of target creature [until end of turn]" (707.4): a layer-1 effect on the
    permanent where it is — no enters or leaves abilities trigger, its other effects keep applying.
    The copied values are fixed as the effect begins (707.2b, 611.2c)."""
    from app.rules import effects

    who = [c for c in effects._cards(plan, ctx, e.get("who") or "self") if plan.state.cards[c].zone.endswith(":battlefield")]
    of = effects._cards(plan, ctx, e["with"])
    if not who or len(of) != 1:
        plan.note(f"{ctx.get('name') or 'It'}: nothing becomes a copy (the permanent or what it would copy is gone)",
                  actor=ctx["controller"])
        return True
    source = plan.state.cards[of[0]]
    problem = supported_source(plan, source)
    if problem is not None:
        _manual(plan, new_job(ctx, controller=ctx["controller"], objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                f"{ctx.get('name') or 'Copy'}: becoming a copy of {problem} isn't automated — do it by hand, then press Done")
        return False
    recipe = with_excepts(recipe_of(plan, source), [CopyExcept.model_validate(x) for x in e.get("excepts") or []])
    duration: Literal["end_of_turn", "permanent"] = "end_of_turn" if e.get("duration") == "end_of_turn" else "permanent"
    add_copy_effect(plan, [plan.oid(c) for c in who], recipe, ctx["controller"], duration=duration)
    plan.note(f"{', '.join(plan.state.cards[c].name for c in who)} becomes a copy of {recipe.source or 'it'}"
              + (" until end of turn" if duration == "end_of_turn" else ""), who, actor=ctx["controller"])
    return True


def resolved(plan: Plan, card_id: str, old_oid: str) -> None:
    """608.3f / 707.10f: a copy of a permanent spell became a token permanent as it resolved; the
    values its copy effect defined are that token's (613.1), so its copy effect follows it onto
    the battlefield (the new object, 400.7)."""
    card = plan.state.cards.get(card_id)
    if card is None or not card.is_token or not card.zone.endswith(":battlefield"):
        return
    new_oid = plan.oid(card)
    for e in plan.rules.effects:
        if e.layer == "1" and e.copy_recipe is not None and old_oid in e.affected and new_oid not in e.affected \
                and not (e.source or "").startswith(ENTERING):
            e.affected.append(new_oid)


# -- state-based actions (704.5d, 704.5e) -------------------------------------------------------------
def ceases_to_exist(plan: Plan, card: CardInstance) -> bool:
    """704.5d: a token outside the battlefield ceases to exist — on the stack, only a copy of a
    spell is shown as a token (it isn't one: 707.10); 704.5e: a copy of a spell outside the stack
    ceases to exist (on the battlefield: an instant or sorcery copy put there by hand; a permanent
    spell's copy became a token as it resolved, 608.3f)."""
    if not card.is_token or card.ability is not None:
        return False
    if card.zone == "stack":
        return card.copy_of is None
    if card.zone.endswith(":battlefield") and card.copy_of is not None:
        return plan.ch(card).is_instant_or_sorcery
    return False


# -- grammar (the templates are registered in app/rules/scripts.py) ------------------------------------
_COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_SUBJECT = r"(?:(?:that )?(?:it|the token|the tokens|the copy|the copies|they) )?"
_QUOTE = re.compile(r'"[^"]*"')


def parse_excepts(text: str | None) -> CopyExcept | None:
    """A copy effect's exceptions (707.9) in the closed wording the engine carries out: "it has
    haste [and "…"]" (707.9a), "it isn't legendary", "it's an artifact / a Spirit in addition to
    its other types" (707.9b; 707.9d: type-defining abilities stay), "it's 7/7" (707.9b; 707.9d:
    a P/T-defining ability isn't copied), "the copy is red" (707.9d), joined by commas and "and".
    None for anything else (the ability stays manual)."""
    ex = CopyExcept()
    if not text:
        return ex
    quotes = _QUOTE.findall(text)
    masked = _QUOTE.sub("\x00", text)
    parts = re.split(r",? and (?=(?:it|it's|it is|is|has|the token|the copy|they)\b)|, (?=(?:it|the token|the copy|they)\b)",
                     masked)
    for part in parts:
        restored = part
        while "\x00" in restored and quotes:
            restored = restored.replace("\x00", quotes.pop(0), 1)
        if "\x00" in restored or not _except_clause(restored.strip(), ex):
            return None
    return ex


def _except_clause(clause: str, ex: CopyExcept) -> bool:
    from app.rules import token_grammar
    from app.rules.creature_types import CREATURE_TYPES

    c = re.sub(r"\bit's\b", "it is", clause)
    c = re.sub(r"\bthey're\b", "they are", c)
    c = c.replace("isn't", "is not").replace("aren't", "are not")
    if re.fullmatch(_SUBJECT + r"(?:is|are) not legendary(?: if (?:the|that) (?:spell|creature|permanent) is legendary)?", c):
        ex.remove_supertypes = sorted({*ex.remove_supertypes, "Legendary"})
        return True
    m = re.fullmatch(_SUBJECT + r"(?:has|have) (?P<abil>.+)", c)
    if m:
        found = token_grammar._with(m["abil"])
        if found is None:
            return False
        kws, quoted = found
        ex.add_text = [*ex.add_text, *(k.capitalize() for k in kws), *([quoted] if quoted else [])]
        return bool(kws or quoted)
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?P<p>\d+)/(?P<t>\d+)", c)
    if m:
        ex.power, ex.toughness = m["p"], m["t"]
        return True
    # "it's a 1/1 red Balloon creature [with flying] in addition to its other [colors and] types" (707.9b):
    # P/T set, the creature type(s) and card types added, the colors set — or added with "colors and"
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?:an? )?(?P<p>\d+)/(?P<t>\d+) (?P<colors>(?:white|blue|black|red|green)"
                                r"(?:,? (?:and )?(?:white|blue|black|red|green))* )?(?P<subs>(?:[A-Z][A-Za-z'-]* )*)"
                                r"(?P<types>(?:artifact )?creatures?)(?: with (?P<kws>[^\"]+?))? in addition to "
                                r"(?:its|their) other (?P<both>colors and )?types", c)
    if m:
        artifact = m["types"].startswith("artifact")
        subs = [s[:-1] if s.endswith("s") and s[:-1] in CREATURE_TYPES and s not in CREATURE_TYPES else s
                for s in m["subs"].split()]
        allowed = CREATURE_TYPES | (token_grammar.ARTIFACT_TYPES if artifact else frozenset())
        with_kws = token_grammar._with(m["kws"]) if m["kws"] else ([], None)
        if with_kws is None or with_kws[1] is not None or not all(s in allowed for s in subs):
            return False
        colors = [_COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["colors"] or "")]
        if colors and m["both"]:
            ex.add_colors = sorted({*ex.add_colors, *colors})
        elif colors:
            ex.set_colors = colors
        ex.power, ex.toughness = m["p"], m["t"]
        ex.add_types = sorted({*ex.add_types, "Creature", *(["Artifact"] if artifact else [])})
        ex.add_subtypes = sorted({*ex.add_subtypes, *subs})
        ex.add_text = [*ex.add_text, *(k.capitalize() for k in with_kws[0])]
        return True
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?:an? )?(?P<t>artifact|enchantment)s? in addition to (?:its|their) other types", c)
    if m:
        ex.add_types = sorted({*ex.add_types, m["t"].capitalize()})
        return True
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?:an? )?(?P<s>[A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*)*?) in addition to "
                                r"(?:its|their) other (?:creature )?types", c)
    if m and all(s in CREATURE_TYPES for s in m["s"].split(" ")):
        ex.add_subtypes = sorted({*ex.add_subtypes, *m["s"].split(" ")})
        return True
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?P<c>white|blue|black|red|green)", c)
    if m:
        ex.set_colors = [_COLOR_WORDS[m["c"]]]
        return True
    return False


def _dump(ex: CopyExcept) -> dict[str, Any]:
    return {"excepts": [ex.model_dump(mode="json", exclude_defaults=True)]} if ex != CopyExcept() else {}


def _target_group(phrase: str) -> dict[str, Any] | None:
    """The target group a phrase names (app/rules/language.py), None if it isn't one it reads."""
    from app.rules import language

    try:
        return language.target_group(phrase)
    except language._Fail:
        return None


def parse_copy_target(what: str, exc: str | None) -> tuple[list[dict[str, Any]], Any] | None:
    """"copy target instant or sorcery spell [you control] [, except that the copy is red]" /
    "copy target triggered ability you control" (707.10): the effect and its target."""
    from app.rules import selectors

    group = _target_group("target " + what)
    if group is None or (group["min"], group["max"]) != (1, 1) or "another" in group:
        return None
    sel = selectors.from_key(group["what"]) if group["what"].startswith(selectors.PREFIX) else None
    if sel is None or sel.zones != ("stack",):
        return None
    ex = parse_excepts(exc)
    if ex is None or (sel.ability is not None and exc):
        return None  # (an ability has no characteristics to except)
    do = "copy_ability" if sel.ability is not None else "copy_spell"
    return [{"do": do, "who": "target", **_dump(ex)}], group["what"]


_SOURCES = {"~": "self", "it": "it", "that creature": "it", "that permanent": "it", "that artifact": "it",
            "that token": "it", "that card": "it", "equipped creature": "host", "enchanted creature": "host",
            "enchanted permanent": "host", "enchanted artifact": "host"}


def parse_token_copy(n: str, tapped: bool, src: str, exc: str | None) -> tuple[list[dict[str, Any]], Any] | None:
    """"create [N] [tapped] token(s) that's a copy / are copies of <source> [, except …]": the source
    is a target, the source itself (~), what an earlier instruction or the trigger was about ("it",
    "that creature") or the permanent the source is attached to."""
    from app.rules import token_grammar

    word = n.lower()
    if word not in token_grammar.NUMBERS and not word.isdigit() and word != "x":
        return None
    ex = parse_excepts(exc)
    if ex is None:
        return None
    effect: dict[str, Any] = {"do": "token_copy", "n": token_grammar._qty(word), **_dump(ex)}
    if tapped:
        effect["tapped"] = True
    if src in _SOURCES:
        return [{**effect, "who": _SOURCES[src]}], None
    group = _target_group(src)
    if group is None or group["max"] != 1:
        return None
    return [{**effect, "who": "target"}], group


def parse_become(what: str, until: bool, exc: str | None) -> tuple[list[dict[str, Any]], Any] | None:
    """"~ becomes a copy of target <permanent> [until end of turn] [, except …]" (707.4)."""
    from app.rules import selectors

    group = _target_group("target " + what)
    if group is None or (group["min"], group["max"]) != (1, 1) or "another" in group:
        return None
    sel = selectors.from_key(group["what"]) if group["what"].startswith(selectors.PREFIX) else None
    if sel is None or sel.zones != ("battlefield",) or sel.player is not None:
        return None
    ex = parse_excepts(exc)
    if ex is None:
        return None
    effect: dict[str, Any] = {"do": "become_copy", "who": "self", "with": "target", **_dump(ex)}
    if until:
        effect["duration"] = "end_of_turn"
    return [effect], group["what"]


_CLONE = re.compile(r"^You may have ~ enter as a copy of (?:any|a|an) (?P<rest>.+)$")


def define_static(text: str) -> dict[str, Any] | None:
    """"You may have ~ enter as a copy of any creature on the battlefield [, except …]." (707.5;
    a replacement effect, 614.1c): the definition ``replacements.entry_plan`` reads through
    :func:`entering`. Its choice is named "<what> to copy" (the prompt: "as it enters, choose a
    creature to copy")."""
    from app.rules import selectors

    m = _CLONE.match(text)
    if m is None:
        return None
    rest = m["rest"]
    if rest.endswith("."):
        rest = rest[:-1]
    elif not rest.endswith('."'):  # (a quoted ability can end the sentence: its period is inside the quotes)
        return None
    what, _, exc = rest.partition(", except ")
    what = what.removesuffix(" on the battlefield")
    sel = selectors.parse(what)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.other:
        return None
    if not sel.types or "Enchantment" in sel.types:
        return None  # (it could copy an Aura, which would have to attach as it enters, 303.4f: not modelled)
    ex = parse_excepts(exc or None)
    if ex is None:
        return None
    return {"kind": "replacement", "replacement": "enter_as_copy", "optional": True, "what": what + TO_COPY,
            "effects": [], **_dump(ex)}


PRIMITIVES = {"copy_spell": copy_stack_object, "copy_ability": copy_stack_object, "copy_new_targets": new_targets_marker,
              "token_copy": token_copy, "become_copy": become_copy}
RESUME = {"copy_mode": resume_mode, "copy_target": resume_target, "copy_manual": resume_manual}
