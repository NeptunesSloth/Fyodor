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

Refused (stays manual): "targets only a single creature / only a player" (Muck Drubb, Rebound),
"the new target must be a creature" (Silver Wyvern), "that targets you or a creature you control"
(Siren Stormtamer), "Change any targets" / "choose new targets" by a player other than the copy's
controller.
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
_CHANGE = re.compile(rf"change (?P<which>the|a) target of (?P<what>target .+?)(?P<to> to {_SELF})?")


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
    if m["which"] == "the" and not single and not m["to"]:
        raise _NoMatch  # ("the target" of a spell that may have several: not read)
    if m["which"] == "the" and m["to"] and not single:
        raise _NoMatch
    if m["which"] == "a" and (single or not m["to"]):
        raise _NoMatch  # ("change a target of …" to anything else: which, and to what? not read)
    e: dict[str, Any] = {"do": "change_target", "who": "target", "to": "self" if m["to"] else None}
    return [e], group["what"]


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile("^" + _CHANGE.pattern + "$"), _change)]


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
_OUPHE = re.compile(r"(?i)\bcounter (target activated ability from an? artifact source) and destroy that artifact if it's on the battlefield")


def rewrite(body: str) -> str:
    """"Counter target activated ability from an artifact source and destroy that artifact if it's on the battlefield" (Ouphe Vandals):
    the artifact whose ability was countered, destroyed if it is still there — the rider of every such counter."""
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


# -- carrying it out -----------------------------------------------------------------------------------
def _legal(plan: Plan, entry: StackEntry, pos: Any, stack_id: str) -> list[str]:
    """What this target of the spell or ability could be now (its controller choosing, its source for
    "another" and protection; 115.5: never the spell itself)."""
    from app.rules import copying, selectors, targets

    spec = copying._spec(entry, pos)
    found = targets.legal_targets(plan, spec.get("what", "any"), entry.controller, targets.source_of(plan, entry.source_card),
                                  entry.source_card, selectors.attacker_of(entry.event))
    return [x for x in found if x != stack_id]


def _with(plan: Plan, entry: StackEntry, pos: Any, new: str) -> StackEntry | None:
    """The entry with this one target changed, if the final set of targets is legal (115.7e)."""
    from app.rules import copying, targets

    out = copying._retargeted(entry, [pos], [targets.ref(plan, new)])
    return out if copying._problem(plan, out) is None else None


def _source(plan: Plan, ctx: Context) -> str | None:
    """"this creature": the source, still that object on the battlefield (400.7)."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ctx.get("source_object"):
        return None
    return card.id


def change_target(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import copying
    from app.rules.effects import _stack_targets
    from app.rules.plan import decide

    me = ctx["controller"]
    for sid in _stack_targets(plan, ctx, e):
        entry = plan.rules.stack.get(sid)
        if entry is None:
            continue
        name = _label(plan, sid) or "that spell"  # (a face-down spell keeps its name hidden)
        positions = copying.positions(entry)
        if e.get("to") == "self":
            src = _source(plan, ctx)
            if src is None:
                plan.note(f"{name}: no target is changed (115.7)", actor=me)
                continue
            fits = [k for k, p in enumerate(positions)
                    if copying._current(entry, p).id != src and src in _legal(plan, entry, p, sid) and _with(plan, entry, p, src)]
            if not fits:
                plan.note(f"{name}: no target is changed (115.7)", actor=me)
                continue
            if len(fits) == 1:
                _apply(plan, sid, _with(plan, entry, positions[fits[0]], src))
                continue
            options = [DecisionOption(id=str(k), label=f"Its target {copying_label(plan, entry, positions[k])}"[:200])
                       for k in fits]
            decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name', '')}: which target of {name} to change",
                   options=options, resume={"step": "change_target", "ctx": ctx, "sid": sid, "oid": plan.oid(sid),
                                            "to": src})
            return False
        if len(positions) != 1:  # (608.2b would have left it unchanged: no longer a single target)
            continue
        pos = positions[0]
        current = copying._current(entry, pos).id
        legal = [x for x in _legal(plan, entry, pos, sid) if x != current and _with(plan, entry, pos, x)]
        if not legal:
            plan.note(f"{name}: no other legal target, so its target is unchanged (115.7a)", actor=me)
            continue
        if len(legal) == 1:
            _apply(plan, sid, _with(plan, entry, pos, legal[0]))
            continue

        options = [DecisionOption(id=x, label=_label(plan, x)[:200], card_id=x if x in plan.state.cards else None)
                   for x in legal]
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name', '')}: choose the new target of {name} (115.7a)",
               options=options, resume={"step": "change_target", "ctx": ctx, "sid": sid, "oid": plan.oid(sid)})
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
    entry = plan.rules.stack.get(sid)
    if entry is not None and plan.oid(sid) == r["oid"]:  # (still that spell or ability: 400.7)
        positions = copying.positions(entry)
        if r.get("to"):
            k = int(chosen[0])
            new = _with(plan, entry, positions[k], r["to"]) if k < len(positions) else None
        else:
            new = _with(plan, entry, positions[0], chosen[0]) if len(positions) == 1 and \
                chosen[0] in _legal(plan, entry, positions[0], sid) else None
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
    old = {t.id for t in plan.rules.stack[sid].targets}
    plan.rules.stack[sid] = new
    added = [t for t in new.targets if t.id not in old]
    for arrow in [a for a in plan.state.arrows if a.source == sid and a.kind == "target"]:
        plan.do({"type": "remove_arrow", "arrow_id": arrow.id}, actor=new.controller)
    ids = [t.id for t in new.targets
           if (t.id in plan.state.players and not plan.state.players[t.id].left)
           or (t.id in plan.state.cards and publicly_visible(plan.state, plan.state.cards[t.id]))]
    ids = list(dict.fromkeys(ids))
    if ids and len(plan.state.arrows) < 190:
        plan.do({"type": "create_arrow", "source": sid, "targets": ids, "kind": "target"}, actor=new.controller)
    plan.note(f"{_label(plan, sid) or 'It'} now targets {', '.join(_label(plan, t.id) for t in new.targets)}")
    targeted(plan, sid, new.controller, added, crime=False)


PRIMITIVES = {"change_target": change_target}
RESUME = {"change_target": resume_change_target}
