"""-- stack interaction (wave 5B) -- spells and abilities that act on other spells and abilities on the
stack, researched against CR 2026-09-25 (and the cards' current rulings).

* "Counter target spell. Its controller …" (An Offer You Can't Refuse, Swan Song, Countersquall):
  the counter records the object it countered (effects.counter, a binding like "destroy"'s), so "its
  controller" is the spell's controller as it last existed on the stack (608.2h; a countered spell
  goes to its owner's graveyard, 701.6a, where it has no controller, 108.4a — so the binding's last
  known information is read, never the card's owner). A spell that can't be countered stays on the
  stack, and the rest of the instructions still happen (608.2c; An Offer's ruling: its controller
  still creates the Treasures). If the target is illegal as it resolves, nothing happens (608.2b).
* "its mana value" / "that spell's mana value" of a spell on the stack includes the X chosen for it
  (202.3e); last known information keeps that X (``ObjectSnapshot.x``). Mana Drain's "At the
  beginning of your next main phase, add …" is a delayed trigger (603.7) on the next main phase of a
  turn of yours (505.1: precombat or postcombat; app/rules/delayed.py), the amount read from the
  countered spell's last known information.
* Changing targets (115.7): "Change the target of target spell [or ability] with a single target"
  (Shunt, Imp's Mischief, Willbender) — the target spell must have exactly one target (selectors
  "single_target", checked as it's targeted and again as this resolves, 608.2b); its target must be
  changed to another legal target if there is one (the rulings: "You must change the target if
  possible"), chosen by this spell's controller as it resolves; with none, it's unchanged (115.7a).
  "[You may] change the target of target … to this creature" (Hydroelectric Specimen) / "Change a
  target of target spell or ability to this creature" (Spellskite, Mizzium Meddler, 115.7b): only
  if this permanent is still on the battlefield and a legal target for it (the spell's controller
  as chooser, its source for "another" and protection); with several targets, this ability's
  controller chooses which one (Spellskite's ruling), and only one whose change leaves the final
  set of targets legal (115.7e). The new target becomes a target of that spell (115.10; "becomes
  the target" triggers and ward, 702.21a) — no crime is committed (700.13 is about casting).

* Countering an ability (701.6a: "counter target activated or triggered ability": the ability leaves the stack and simply stops
  existing; it isn't a card). "If a permanent's ability is countered this way, …" / "If an ability of an artifact, creature, or
  planeswalker is countered this way, …" (Trickbind, Tishana's Tidebinder, Green Slime, Teferi's Response) and Interdict's
  "That permanent's activated abilities can't be activated this turn": "that permanent" is the source of the countered ability,
  while it is still that object on the battlefield (400.7; ``effects.counter``'s ``perm_as`` binding): nothing if the ability
  wasn't countered or its source has left. "Counter target activated ability from an artifact source and destroy that artifact if
  it's on the battlefield" (Ouphe Vandals) is the same rider. "Counter target activated ability, triggered ability, or legendary
  spell" (Tale's End): any one object on the stack that is one of those (selectors.parse_stack_union).

* "You may choose new targets for target spell or ability." (Deflecting Swat, 115.7d): this spell's controller keeps or changes each target of it in
  turn, as for a copy (707.10c: copying.ask_targets); the new targets must be legal (for the spell's own controller and source) and, with the ones left
  unchanged, a legal set (115.7d-e); how many targets it has and how its effect is divided can't change (115.7f). With no targets nothing happens.

* -- retarget (wave 100O) -- "target spell that targets only this creature / only a single creature / only a player" (115.9c: one object or
  player, maybe chosen several times: selectors "targets_only:"): "change the target" changes every one of them to the same new target,
  legal for each, or none (Torchling's and Muck Drubb's rulings); "The new target must be a player / a creature" (Rebound, Silver Wyvern)
  narrows it. "Change the targets" (115.7a, Goblin Flectomancer's ruling): each target to another legal one, all or none (the "may": leave
  them all); "change any targets" (115.7c, Sideswipe) is asked as 115.7d (keep or change each, the final set legal, 115.7e). "Change the
  target to enchanted creature if able" (Captured by the Consulate): the Aura's host if it is a legal target, else unchanged (its ruling).
  "Choose new targets for that spell" (Speedball: the cast trigger's spell) / "for any number of other spells and/or abilities"
  (Boltbender: chosen as it resolves, none targeted, 115.10a; then each in turn as 115.7d).

Refused (stays manual): "Change any targets" / "choose new targets" by a player other than the copy's controller.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.rules_state import StackEntry
    from app.rules.plan import Plan

Context = dict[str, Any]


def mana_value(card: Any, ch: Any) -> int:
    """The mana value of an object (202.3): on the stack, each {X} in its cost counts as the X
    chosen for it (202.3e); elsewhere X is 0 (the printed mana value already counts it so)."""
    value = int(ch.mana_value)
    info = getattr(card, "stack_info", None)
    if card is not None and card.zone == "stack" and info is not None and info.x:
        value += info.x * (ch.mana_cost or "").count("{X}")
    return value


# -- the wording (first letter lower-cased, no final period) -------------------------------------------
_SELF = r"(?:~|this creature)"
_CHANGE = re.compile(rf"change (?P<which>the|a|any) (?P<pl>targets?) of (?P<what>target .+?)(?P<to> to {_SELF})?"
                     r"(?: and the new target must be an? (?P<must>creature|player))?")


def _change(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import copying, selectors
    from app.rules.scripts import _NoMatch

    group = copying._target_group(m["what"])
    if group is None or (group["min"], group["max"]) != (1, 1) or "another" in group \
            or not str(group["what"]).startswith(selectors.PREFIX):
        raise _NoMatch
    sel = selectors.from_key(group["what"])
    if sel.zones != ("stack",) or sel.player is not None:
        raise _NoMatch
    single = "single_target" in sel.extras
    only = any(x.startswith("targets_only:") for x in sel.extras)  # -- retarget (wave 100O) -- 115.9c: one object, maybe several times
    if m["pl"] == "targets":  # -- retarget (wave 100O) -- 115.7a "change the targets" (Goblin Flectomancer), 115.7c "change any targets" (Sideswipe)
        if m["which"] == "a" or m["to"] or m["must"] or single or only:
            raise _NoMatch
        return [{"do": "change_target", "who": "target", "each": True} if m["which"] == "the" else {"do": "choose_new_targets", "who": "target"}], group["what"]
    if m["which"] == "any" or (m["must"] and (m["which"] == "a" or m["to"])):
        raise _NoMatch
    if m["which"] == "the" and not (single or only):
        raise _NoMatch  # ("the target" of a spell that may have several: not read)
    if m["which"] == "a" and (single or only or not m["to"]):
        raise _NoMatch  # ("change a target of …" to anything else: which, and to what? not read)
    e: dict[str, Any] = {"do": "change_target", "who": "target", "to": "self" if m["to"] else None}
    if only and m["to"]:
        e["all"] = True  # (Muck Drubb's ruling: every one of those targets becomes this creature)
    if m["must"]:
        e["must"] = m["must"]  # ("The new target must be a player / a creature", Rebound, Silver Wyvern)
    return [e], group["what"]


# -- static_other (wave 36B) -- "You may choose new targets for target spell or ability." (Deflecting Swat, 115.7d)
_NEW_TARGETS = re.compile(r"choose new targets for (?P<what>target (?:spell or ability|spell|activated ability|triggered ability|activated or triggered ability))")


def _new_targets(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import copying, selectors
    from app.rules.scripts import _NoMatch

    group = copying._target_group(m["what"])
    if group is None or (group["min"], group["max"]) != (1, 1) or "another" in group or not str(group["what"]).startswith(selectors.PREFIX):
        raise _NoMatch
    sel = selectors.from_key(group["what"])
    if sel.zones != ("stack",) or sel.player is not None or "single_target" in sel.extras:
        raise _NoMatch
    return [{"do": "choose_new_targets", "who": "target"}], group["what"]


# -- retarget (wave 100O) -- "You may choose new targets for that spell." (Speedball: a cast trigger's spell, 603.2), "… for any number of other spells and/or
# abilities." (Boltbender: chosen as it resolves, none targeted, 115.10), "Change the target to enchanted creature if able." (Captured by the Consulate: a cast
# trigger's spell with a single target, the Aura's host as the new target, 115.7a)
_RETARGET_MORE: list[tuple[str, list[dict[str, Any]]]] = [
    ("choose new targets for that spell", [{"do": "choose_new_targets", "who": "event_spell"}]),
    ("choose new targets for any number of other spells and/or abilities", [{"do": "choose_new_targets", "who": "any_number"}]),
    ("change the target to enchanted creature if able", [{"do": "change_target", "who": "event_spell", "to": "host"}]),
]


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile("^" + _CHANGE.pattern + "$"), _change), (re.compile("^" + _NEW_TARGETS.pattern + "$"), _new_targets),
                                                *((re.compile("^" + re.escape(t) + "$"), lambda m, e=e: ([{**x} for x in e], None)) for t, e in _RETARGET_MORE)]


# -- countering an ability: the permanent it came from (wave 23B) ---------------------------------------------------
_COUNTERED = r"if (?:a permanent's ability|an ability of (?P<kinds>an artifact, creature, or planeswalker)) is countered this way, "
_PERM_RIDERS: dict[str, Any] = {
    "destroy that permanent": lambda who, name: [{"do": "destroy", "who": who}],
    "activated abilities of that permanent can't be activated this turn":
        lambda who, name: [{"do": "restrict", "who": who, "rules": ["cant_activate"]}],  # (602.5; mana abilities too, as for detain)
    "that permanent loses all abilities for as long as ~ remains on the battlefield":
        lambda who, name: [{"do": "become", "who": who, "types": [], "lose_abilities": True, "duration": "source_on_battlefield"}],  # 611.2b
}
_PERM_UNCONDITIONAL = {"that permanent's activated abilities can't be activated this turn": "activated abilities of that permanent can't be activated this turn"}
_NEW_MUST = re.compile(r"(\b[Cc]hange the target of target [^.]+?)\. The new target must be (an? (?:creature|player))\b")
_OUPHE = re.compile(r"(?i)\bcounter (target activated ability from an? artifact source) and destroy that artifact if it's on the battlefield")


def rewrite(body: str) -> str:
    """"Counter target activated ability from an artifact source and destroy that artifact if it's on the battlefield" (Ouphe Vandals):
    the artifact whose ability was countered, destroyed if it is still there — the rider of every such counter."""
    body = _NEW_MUST.sub(r"\1 and the new target must be \2", body)  # -- retarget (wave 100O) -- the second sentence restricts the change before it (Rebound)
    return _OUPHE.sub(lambda m: f"Counter {m[1]}. If a permanent's ability is countered this way, destroy that permanent", body)


def rider(text: str, effects: list[dict[str, Any]], prev_start: int, groups: list[dict[str, Any]]) -> bool | None:
    """A sentence about the permanent whose ability the counter before it countered: appended to ``effects`` (True), refused (False) or
    not one (None). Only right after a plain "counter target … ability" (the kinds of source the sentence names narrow it)."""
    from app.rules import selectors

    m = re.fullmatch(_COUNTERED + r"(?P<rest>.+)", text)
    rest = _PERM_UNCONDITIONAL.get(text) if m is None else m["rest"]
    if rest is None or rest not in _PERM_RIDERS:
        return None
    prev = effects[prev_start:]
    sel = selectors.from_key(groups[-1]["what"]) if groups and str(groups[-1].get("what", "")).startswith(selectors.PREFIX) else None
    if len(prev) != 1 or prev[0].get("do") != "counter" or not str(prev[0].get("who")).startswith("target") or prev[0].get("perm_as") \
            or sel is None or sel.zones != ("stack",) or not (sel.ability or sel.either):
        return False  # (a spell has no source permanent; several counters or targets: which "that permanent"?)
    name = f"p{sum(1 for e in effects if e.get('perm_as'))}"
    prev[0]["perm_as"] = name
    if m is not None and m["kinds"]:
        prev[0]["perm_types"] = ["Artifact", "Creature", "Planeswalker"]
    effects += _PERM_RIDERS[rest](f"ref:{name}", name)
    return True


def target_entry(plan: Plan, sid: str) -> StackEntry | None:
    """A spell's targets, including the separate Aura/mutate record, without changing resolution."""
    from app.game.rules_state import StackEntry
    from app.rules import attachments, merged

    entry = plan.rules.stack.get(sid)
    if entry is not None:
        return entry
    card = plan.state.cards.get(sid)
    target = plan.rules.aura_targets.get(sid)
    if card is None or card.zone != "stack" or target is None or card.ability is not None:
        return None
    ch = plan.ch(card)
    selector = merged.target_selector(card.owner) if plan.oid(card) in plan.rules.mutating else attachments.enchant_selector(ch)
    if selector is None:
        return None
    return StackEntry(kind="spell", controller=card.controller, source_card=sid, source_object=plan.oid(card), name=ch.name,
                      targets=[target], target_spec={"what": selector}, x=card.stack_info.x if card.stack_info else None)


# -- carrying it out -----------------------------------------------------------------------------------
def _legal(plan: Plan, entry: StackEntry, pos: Any, stack_id: str) -> list[str]:
    """What this target of the spell or ability could be now (its controller choosing, its source for
    "another" and protection; 115.5: never the spell itself)."""
    from app.rules import copying, selectors, targets

    spec = copying._spec(entry, pos)
    found = targets.legal_targets(plan, spec.get("what", "any"), entry.controller, targets.source_of(plan, entry.source_card, entry.kind == "spell", object_id=entry.source_object),
                                  entry.source_card, selectors.attacker_of(entry.event), source_object=entry.source_object)
    return [x for x in found if x != stack_id]


def _with(plan: Plan, entry: StackEntry, pos: list[Any], new: str) -> StackEntry | None:
    """The entry with these targets changed to ``new``, if the final set of targets is legal (115.7e)."""
    from app.rules import copying, targets

    out = copying._retargeted(entry, pos, [targets.ref(plan, new)] * len(pos))
    return out if copying._problem(plan, out) is None else None


def _fits(plan: Plan, entry: StackEntry, pos: list[Any], new: str, sid: str, must: str | None = None) -> StackEntry | None:
    """-- retarget (wave 100O) -- ``new`` as every one of these targets: legal for each (115.7a), "the new target must be a player / a creature",
    and a legal final set (115.7e)."""
    card = plan.state.cards.get(new)
    if must == "player" and new not in plan.state.players or must == "creature" and (
            card is None or not card.zone.endswith(":battlefield") or "Creature" not in plan.ch(card).types):
        return None
    return _with(plan, entry, pos, new) if pos and all(new in _legal(plan, entry, p, sid) for p in pos) else None


def _source(plan: Plan, ctx: Context) -> str | None:
    """"this creature": the source, still that object on the battlefield (400.7)."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ctx.get("source_object"):
        return None
    return card.id


def change_target(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import copying
    from app.rules.effects import _cards, _stack_targets
    from app.rules.plan import decide

    me = ctx["controller"]
    for sid in _stack_targets(plan, ctx, e):
        entry = target_entry(plan, sid)
        if entry is None:
            continue
        if e.get("each"):  # -- retarget (wave 100O) -- 115.7a "change the targets": each to another legal target, all or none
            if not _ask_new_targets(plan, ctx, sid, [], each="may" if e.get("optional") else True):
                return False
            continue
        name = _label(plan, sid) or "that spell"  # (a face-down spell keeps its name hidden)
        positions = copying.positions(entry)
        current = {copying._current(entry, p).id for p in positions}
        if e.get("to"):
            src = _source(plan, ctx) if e["to"] == "self" else next(iter(_cards(plan, ctx, "host")), None)  # ("enchanted creature": the Aura's host now)
            if e.get("all") or e["to"] == "host":  # -- retarget (wave 100O) -- "the target" of a spell on one object: all of them or none (115.7a)
                new = _fits(plan, entry, positions, src, sid) if src is not None and src not in current else None
                if new is None:
                    plan.note(f"{name}: no target is changed (115.7)", actor=me)
                    continue
                _apply(plan, sid, new)
                continue
            if src is None:
                plan.note(f"{name}: no target is changed (115.7)", actor=me)
                continue
            fits = [k for k, p in enumerate(positions) if copying._current(entry, p).id != src and _fits(plan, entry, [p], src, sid)]
            if not fits:
                plan.note(f"{name}: no target is changed (115.7)", actor=me)
                continue
            if len(fits) == 1:
                _apply(plan, sid, _with(plan, entry, [positions[fits[0]]], src))
                continue
            options = [DecisionOption(id=str(k), label=f"Its target {copying_label(plan, entry, positions[k])}"[:200])
                       for k in fits]
            decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name', '')}: which target of {name} to change",
                   options=options, resume={"step": "change_target", "ctx": ctx, "sid": sid, "oid": plan.oid(sid),
                                            "to": src})
            return False
        if len(current) != 1:  # (608.2b would have left it unchanged: no longer a single target; 115.9c: one object, maybe several times)
            continue
        legal = [x for x in _legal(plan, entry, positions[0], sid) if x not in current and _fits(plan, entry, positions, x, sid, e.get("must"))]
        if not legal:
            plan.note(f"{name}: no other legal target, so its target is unchanged (115.7a)", actor=me)
            continue
        if len(legal) == 1:
            _apply(plan, sid, _with(plan, entry, positions, legal[0]))
            continue

        options = [DecisionOption(id=x, label=_label(plan, x)[:200], card_id=x if x in plan.state.cards else None)
                   for x in legal]
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name', '')}: choose the new target of {name} (115.7a)",
               options=options, resume={"step": "change_target", "ctx": ctx, "sid": sid, "oid": plan.oid(sid), "must": e.get("must")})
        return False
    return True


def copying_label(plan: Plan, entry: StackEntry, pos: Any) -> str:
    from app.rules import copying

    return _label(plan, copying._current(entry, pos).id)


def _label(plan: Plan, target: str) -> str:
    """A target's name, never a hidden one's (a face-down permanent: 708.5)."""
    from app.game.visibility import publicly_visible
    from app.rules import targets

    card = plan.state.cards.get(target)
    if card is not None and not publicly_visible(plan.state, card):
        return "a face-down card"
    return targets.label(plan, target)


def resume_change_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import copying
    from app.rules.effects import continue_effects

    r = d.resume
    ctx, sid = r["ctx"], r["sid"]
    entry = target_entry(plan, sid)
    if entry is not None and plan.oid(sid) == r["oid"]:  # (still that spell or ability: 400.7)
        positions = copying.positions(entry)
        if r.get("to"):
            k = int(chosen[0])
            new = _with(plan, entry, [positions[k]], r["to"]) if k < len(positions) else None
        else:
            new = _fits(plan, entry, positions, chosen[0], sid, r.get("must")) if len({copying._current(entry, p).id for p in positions}) == 1 else None
        if new is not None:
            _apply(plan, sid, new)
    continue_effects(plan, ctx)


def _apply(plan: Plan, sid: str, new: StackEntry | None) -> None:
    """The spell or ability now has these targets: the arrow follows, and each new target becomes its
    target (115.10, 603.2e: "becomes the target" triggers, ward 702.21a)."""
    from app.game.visibility import publicly_visible
    from app.rules.triggers import targeted

    if new is None:
        return
    before = target_entry(plan, sid)
    if before is None:
        return
    old = {t.id for t in before.targets}
    if sid in plan.rules.stack:
        plan.rules.stack[sid] = new
    elif sid in plan.rules.aura_targets and new.targets:
        plan.rules.aura_targets[sid] = new.targets[0]

    added = [t for t in new.targets if t.id not in old]
    for arrow in [a for a in plan.state.arrows if a.source == sid and a.kind == "target"]:
        plan.do({"type": "remove_arrow", "arrow_id": arrow.id}, actor=new.controller)
    ids = [t.id for t in new.targets
           if (t.id in plan.state.players and not plan.state.players[t.id].left)
           or (t.id in plan.state.cards and publicly_visible(plan.state, plan.state.cards[t.id]))]
    plan.target_arrows(sid, ids, actor=new.controller)
    plan.note(f"{_label(plan, sid) or 'It'} now targets {', '.join(_label(plan, t.id) for t in new.targets)}")
    targeted(plan, sid, new.controller, added, crime=False)


def choose_new_targets(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """115.7d: the controller of this effect keeps or changes each target of the spell or ability in turn (``choose_one``: "keep" or a legal new target)."""
    from app.rules import copying
    from app.rules.effects import _stack_targets
    from app.rules.plan import decide

    if e.get("who") == "any_number":  # -- retarget (wave 100O) -- "any number of other spells and/or abilities" (Boltbender): chosen as it resolves
        pool = [c for c in plan.state.zones.get("stack", []) if c != ctx.get("stack_id") and (t := target_entry(plan, c)) is not None and copying.positions(t)]
        if pool:
            decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name', '')}: choose new targets for which spells and abilities?",
                   options=[DecisionOption(id=c, label=_label(plan, c)[:200] or "Spell", card_id=c) for c in pool], min_choices=0, max_choices=len(pool),
                   resume={"step": "new_targets_pick", "ctx": ctx})
            return False
        return True
    for sid in _stack_targets(plan, ctx, e):
        return _ask_new_targets(plan, ctx, sid, [], plan.state.cards[sid].controller if e.get("by") == "spell_controller" else None)
    return True


def resume_new_targets_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    queue = [[c, plan.oid(c)] for c in chosen]  # (each still that object when its turn comes, 400.7)
    if _next_queued(plan, d.resume["ctx"], queue):
        continue_effects(plan, d.resume["ctx"])


def _next_queued(plan: Plan, ctx: Context, queue: list[list[str]]) -> bool:
    while queue:
        sid, oid = queue.pop(0)
        if target_entry(plan, sid) is not None and plan.oid(sid) == oid and not _ask_new_targets(plan, ctx, sid, [], queue=queue):
            return False
    return True


def _ask_new_targets(plan: Plan, ctx: Context, sid: str, picks: list[str], chooser: str | None = None, each: bool | str = False,
                     queue: list[list[str]] | None = None) -> bool:
    """True once every target has been kept or changed (the changed entry applied); False while a question is open. ``each``
    (wave 100O): 115.7a "change the targets" — every target to another legal one, or none changes (no "keep"). ``queue``: the
    spells and abilities still to go after this one (Boltbender)."""
    from app.rules import copying, targets
    from app.rules.plan import decide

    entry = target_entry(plan, sid)
    if entry is None:
        return _next_queued(plan, ctx, queue or [])
    me = chooser or ctx["controller"]
    positions = copying.positions(entry)
    name = _label(plan, sid) or "that spell"
    if each and "keep" in picks:  # ("You may change the targets": the player changes none of them)
        return _next_queued(plan, ctx, queue or [])
    while len(picks) < len(positions):
        k = len(picks)
        kind, g, _ = positions[k]
        so_far = [(q, copying._current(entry, q).id if p == "keep" else p) for p, q in zip(picks, positions, strict=False)]
        others = set(copying._spec(entry, positions[k]).get("distinct_from") or []) if kind == "group" else set()  # (115.3: not twice for one "target")
        taken = {x for q, x in so_far if q[0] == kind and (q[1] == g or q[1] in others)}
        current = copying._current(entry, positions[k]).id
        legal = [x for x in _legal(plan, entry, positions[k], sid) if x != current and x not in taken]
        if not legal and each:  # (115.7a: one target can't be changed to another legal target, so none is changed)
            plan.note(f"{name}: a target can't be changed to another legal target, so none is changed (115.7a)", actor=me)
            return _next_queued(plan, ctx, queue or [])
        if not legal:  # nothing else it could target: it keeps this one
            picks.append("keep")
            continue
        keep = [DecisionOption(id="keep", label="Leave every target unchanged")] if each == "may" else [] if each else \
            [DecisionOption(id="keep", label=f"Keep {_label(plan, current)}"[:200], card_id=current if current in plan.state.cards else None)]
        options = [*keep, *(DecisionOption(id=x, label=_label(plan, x)[:200], card_id=x if x in plan.state.cards else None) for x in legal)]
        count = f" ({k + 1} of {len(positions)})" if len(positions) > 1 else ""
        ask = f"choose a new target for {name}{count} (115.7a)" if each else f"keep the target of {name}{count} or choose a new one (115.7d)"
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name', '')}: {ask}",
               options=options, resume={"step": "choose_new_targets", "ctx": ctx, "sid": sid, "oid": plan.oid(sid), "picks": picks, "chooser": me,
                                        **({"each": each} if each else {}), **({"queue": queue} if queue else {})})
        return False
    if all(p == "keep" for p in picks):
        return _next_queued(plan, ctx, queue or [])
    refs = [copying._current(entry, q) if p == "keep" else targets.ref(plan, p) for p, q in zip(picks, positions, strict=True)]
    new = copying._retargeted(entry, positions, refs)
    problem = copying._problem(plan, new)
    if problem is not None and each:  # (115.7a, 115.7e: that final set isn't legal, so none is changed)
        plan.note(f"Those targets aren't legal together: {problem}. None is changed (115.7a)", actor=me)
        return _next_queued(plan, ctx, queue or [])
    if problem is not None:  # 115.7e: only the final set is judged: choose again
        plan.note(f"Those targets aren't legal together: {problem}. Choose again", actor=me)
        return _ask_new_targets(plan, ctx, sid, [], chooser, queue=queue)
    _apply(plan, sid, new)
    return _next_queued(plan, ctx, queue or [])


def resume_choose_new_targets(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    if target_entry(plan, r["sid"]) is None or plan.oid(r["sid"]) != r["oid"]:  # (gone, or a new object: 400.7)
        if _next_queued(plan, r["ctx"], list(r.get("queue") or [])):
            continue_effects(plan, r["ctx"])
        return
    if _ask_new_targets(plan, r["ctx"], r["sid"], [*r["picks"], chosen[0]], r.get("chooser"), r.get("each") or False, list(r.get("queue") or [])):
        continue_effects(plan, r["ctx"])


PRIMITIVES = {"change_target": change_target, "choose_new_targets": choose_new_targets}
RESUME = {"change_target": resume_change_target, "choose_new_targets": resume_choose_new_targets, "new_targets_pick": resume_new_targets_pick}
