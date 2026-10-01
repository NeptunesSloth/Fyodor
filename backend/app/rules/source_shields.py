"""-- refused grants/replacements (wave 3R2) -- Damage from a source of a player's choice (609.7,
615.8, 615.9) and damage that can't be prevented (615.12). Researched against the Comprehensive
Rules of 2026-09-25 (data/rules/comprehensive_rules/).

**Source-of-your-choice shields.** "{1}: The next time a red source of your choice would deal
damage to you this turn, prevent that damage." (Circle of Protection: Red), "Prevent all damage a
source of your choice would deal this turn." (Pay No Heed), "Prevent all damage that would be dealt
to you this turn by a source of your choice." (Consulate Surveillance):

* 609.7a: the source is chosen as the effect is created (as the spell or ability resolves): a
  permanent, a spell on the stack, an object an object on the stack refers to (its source, its
  targets, what it triggered on), the source of a delayed trigger or of a replacement / prevention
  effect waiting to apply, or a face-up object in the command zone. A chosen permanent spell also
  covers the permanent it becomes (609.7a). A source doesn't need to be able to deal damage.
* The choice is restricted to sources with the stated property ("a red source"); when the source
  would deal damage, the shield checks the property again (609.7b, 615.9): no longer red, the
  damage isn't prevented and the shield isn't used up.
* "The next time …" (615.8) prevents the next instance of damage from that source to the shielded
  recipient, however much it is, then is used up; "Prevent all damage … this turn" lasts the turn.
  Both are records of app/rules/replace.py (``add_record``; this turn only: 611.2a), applied in
  the 616.1 loop with every other prevention and replacement effect, chosen by the affected player.
* Refused (the sentence stays manual): riders on the prevented damage ("If damage is prevented this
  way, ~ deals that much damage …", 615.5), redirection ("that damage is dealt to … instead", 614.9),
  "half that damage", a target as the recipient ("to any target", "to target creature"), a shield
  with no recipient ("would deal damage this turn": UNVERIFIED whether one instance covers damage to
  several recipients at once), "of the chosen color", "that shares a color with …".

**Damage that can't be prevented** (615.12). "Damage can't be prevented." (Leyline of Punishment),
"Combat damage can't be prevented.", "Damage that would be dealt by ~ can't be prevented."
(Malignus), "Combat damage that would be dealt by creatures you control can't be prevented."
(Questing Beast), "Damage can't be prevented this turn." (Skullcrack: a record for this turn) and a
spell's own "… deals 4 damage to target creature. The damage can't be prevented." (Pinpoint
Avalanche): prevention effects still apply to such damage but prevent none of it, and shields
aren't reduced (615.12). No prevention effect the engine applies has an additional effect yet (the
riders are refused above), so applying one to unpreventable damage does nothing at all: the engine
doesn't apply it. Protection's damage prevention (702.16e) is a prevention effect too.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_TYPES = {"artifact": "Artifact", "creature": "Creature", "land": "Land", "enchantment": "Enchantment"}


def _props(words: str | None) -> dict[str, list[str]] | None:
    """"red" / "black or red" / "artifact" → the property a chosen source must have; None: not read."""
    if not words:
        return {}
    colors: list[str] = []
    types: list[str] = []
    for w in re.split(r" or ", words.strip()):
        if w in _COLORS:
            colors.append(_COLORS[w])
        elif w in _TYPES:
            types.append(_TYPES[w])
        else:
            return None
    if colors and types:
        return None  # ("an artifact or red source": a union of two kinds, not read)
    return {"colors": colors} if colors else {"types": types} if types else {}


# -- grammar: effect sentences (first letter lower-cased, no final period) ----------------------------
_NEXT_TO_YOU = re.compile(r"the next time (?:a|an) (?:(?P<props>[a-z ]+?) )?source of your choice would deal damage to you "
                          r"this turn, prevent that damage")
_ALL_BY = re.compile(r"prevent all damage (?:a|an) (?:(?P<props>[a-z ]+?) )?source of your choice would deal (?P<you>to you )?"
                     r"this turn")
_ALL_TO_YOU = re.compile(r"prevent all damage that would be dealt to you this turn by (?:a|an) (?:(?P<props>[a-z ]+?) )?"
                         r"source of your choice")
_TURN = re.compile(r"damage can't be prevented this turn")


def _shield(m: re.Match[str], *, once: bool, to_you: bool) -> tuple[list[dict[str, Any]], None]:
    props = _props(m["props"])
    if props is None:
        from app.rules.scripts import _NoMatch

        raise _NoMatch
    return [{"do": "source_shield", "props": props, "once": once, "to": "you" if to_you else None}], None


def _next_to_you(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    return _shield(m, once=True, to_you=True)


def _all_by(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    return _shield(m, once=False, to_you=bool(m["you"]))


def _all_to_you(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    return _shield(m, once=False, to_you=True)


def _turn(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    return [{"do": "unpreventable_turn"}], None


# 615.7 shields beyond the generic template (app/rules/scripts.py ``_prevent``: "any target", "target creature",
# "target player", "~"): "Prevent the next 2 damage that would be dealt to you this turn." (Esper Battlemage),
# "… to target legendary creature …" (Eiganjo Castle), "… to target artifact creature …", "… to target player or
# planeswalker …" (Noble Vestige). The same shield (effects.prevent, ``RulesState.prevention``).
_NEXT_N = re.compile(r"prevent the next (?P<n>\d+|one|two|three|four|five) damage that would be dealt to "
                     r"(?P<to>you|target player or planeswalker|target (?!(?:creature|player) this turn$)(?P<sel>[a-z ]+?)) this turn")


def _next_n(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import scripts, selectors

    n = scripts.num(m["n"])
    if m["to"] == "you":
        return [{"do": "prevent", "who": "you", "n": n}], None
    if m["to"] == "target player or planeswalker":
        return [{"do": "prevent", "who": "target", "n": n}], "player_or_planeswalker"
    sel = selectors.parse(m["sel"] or "")
    if sel is None or sel.zones != ("battlefield",) or sel.player is not None or sel.card or "Creature" not in sel.types:
        raise scripts._NoMatch  # (a creature selector only: what can be dealt damage, 120.1)
    return [{"do": "prevent", "who": "target", "n": n}], sel.key()


# (registered first in app/rules/scripts.py EFFECTS: "prevent all damage that would be dealt …" is the
# generic "prevent all" template's, which refuses the "source of your choice" wording)
TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile("^" + _NEXT_TO_YOU.pattern + "$"), _next_to_you),
    (re.compile("^" + _ALL_BY.pattern + "$"), _all_by),
    (re.compile("^" + _ALL_TO_YOU.pattern + "$"), _all_to_you),
    (re.compile("^" + _TURN.pattern + "$"), _turn),
    (re.compile("^" + _NEXT_N.pattern + "$"), _next_n),
]
THE_DAMAGE = "the damage can't be prevented"  # (a sentence about the damage of the sentence before it)


# -- grammar: static abilities -------------------------------------------------------------------------
_STATICS: dict[str, dict[str, Any]] = {
    "Damage can't be prevented.": {},
    "Combat damage can't be prevented.": {"combat": True},
    "Damage that would be dealt by ~ can't be prevented.": {"self": True},
    "Combat damage that would be dealt by creatures you control can't be prevented.": {
        "combat": True, "controller": "you", "types": ["Creature"]},
}


def static_definition(text: str) -> Definition | None:
    """A static "… can't be prevented." line of a permanent (615.12), or a redirection static, or None."""
    scope = _STATICS.get(text.strip())
    if scope is None:
        return redirect_definition(text)
    return {"kind": "static", "static": "unpreventable", "scope": dict(scope), "effects": []}


# -- redirection statics (614.9) ---------------------------------------------------------------------------
# "All damage that would be dealt to you is dealt to enchanted creature instead." (Pariah), "… to equipped creature"
# (Pariah's Shield), "… to ~ instead." (Empyrial Archangel, Protector of the Crown), "All damage that would be dealt
# to you and other permanents you control is dealt to ~ instead." (Palisade Giant), "All damage that would be dealt
# to enchanted creature is dealt to its controller instead." (Treacherous Link). A replacement static of
# app/rules/replace.py (event "damage", op "redirect"): the affected player or controller orders it with the others
# (616.1); it applies once to an event (614.5) and the redirected event goes through the loop again (616.1f).
_REDIRECT = re.compile(r"All damage that would be dealt to (?P<to>you|you and other permanents you control|enchanted creature) "
                       r"is dealt to (?P<new>enchanted creature|equipped creature|~|its controller) instead\.")


def redirect_definition(text: str) -> Definition | None:
    m = _REDIRECT.fullmatch(text.strip())
    if m is None:
        return None
    to, new = m["to"], m["new"]
    if (to == "enchanted creature") != (new == "its controller"):
        return None
    if to == "you":
        match: dict[str, Any] = {"to": {"players": "you"}}
    elif to == "enchanted creature":
        match = {"to": {"objects": {"attached": True}}}
    else:
        from app.rules import selectors

        sel = selectors.parse("other permanents you control")
        assert sel is not None
        match = {"to": {"players": "you", "objects": {"sel": sel.key()}}}
    into = {"enchanted creature": "attached", "equipped creature": "attached", "~": "self",
            "its controller": "attached_controller"}[new]
    return {"kind": "static", "static": "replace", "event": "damage", "match": match, "op": {"do": "redirect", "to": into},
            "effects": []}


def redirect_target(plan: Plan, c: Any, ev: dict[str, Any]) -> str | None:
    """Where a redirection static sends this damage now — or None: 614.9, the new recipient is no
    longer on the battlefield or no longer a creature, planeswalker or battle (or the player has
    left the game), and the effect does nothing."""
    holder = plan.state.cards.get(c.source_card or "")
    if holder is None or not holder.zone.endswith(":battlefield") or plan.oid(holder) != c.source_oid:
        return None
    into = c.op.get("to")
    if into == "self":
        new = holder.id
    else:
        attached = plan.state.cards.get(holder.attached_to or "")
        if attached is None or not attached.zone.endswith(":battlefield"):
            return None
        new = attached.id if into == "attached" else attached.controller
    if new in plan.state.players:
        return new if new in plan.live() and new != ev["target"] else None
    ch = plan.ch(plan.state.cards[new])
    if not ({"Creature", "Planeswalker", "Battle"} & ch.types) or new == ev["target"]:
        return None
    return new


def redirect(plan: Plan, c: Any, ev: dict[str, Any]) -> dict[str, Any]:
    """The redirected event: the same damage from the same source to the new recipient; its
    protection from the source prevents it (702.16e) unless it can't be prevented (615.12)."""
    from app.rules import protection

    new = redirect_target(plan, c, ev)
    assert new is not None
    out = {**ev, "target": new, "target_oid": plan.oid(new) if new in plan.state.cards else None}
    src = plan.state.cards.get(ev.get("source_card") or "")
    if new in plan.state.cards and src is not None and not ev.get("unpreventable") \
            and protection.protected_from(plan.ch(plan.state.cards[new]), plan.ch(src)):
        out["prevented"] = int(ev.get("prevented") or 0) + int(ev["amount"])
        out["amount"] = 0
    return out


# -- 615.12: is this damage event unpreventable? ---------------------------------------------------------
def _scope_matches(scope: dict[str, Any], ev: dict[str, Any], controller: str, source_oid: str | None) -> bool:
    if scope.get("combat") and not ev.get("combat"):
        return False
    if scope.get("self") and (source_oid is None or ev.get("source_oid") != source_oid):
        return False
    src = ev.get("src") or {}
    if scope.get("controller") == "you" and src.get("controller") != controller:
        return False
    return not (scope.get("types") and not set(scope["types"]) & set(src.get("types") or ()))


def unpreventable(plan: Plan, ev: dict[str, Any]) -> bool:
    """615.12: the damage of this event (source → recipient) can't be prevented — its own spell
    says so ("The damage can't be prevented."), an effect this turn does, or a static ability of a
    permanent on the battlefield does (a face-down one has none; a manual card is left to the
    players)."""
    if ev.get("unpreventable"):
        return True
    turn = plan.state.turn.number
    for rec in plan.rules.replacements:
        if rec.get("kind") == "unpreventable" and rec.get("turn") == turn and rec.get("controller") in plan.live() \
                and _scope_matches(rec.get("scope") or {}, ev, rec["controller"], None):
            return True
    return any(_scope_matches(scope, ev, controller, oid) for scope, controller, oid in _statics(plan))


def _statics(plan: Plan) -> list[tuple[dict[str, Any], str, str]]:
    """The "can't be prevented" statics on the battlefield: (scope, controller, source object) — read
    once per table state of this plan (a damage batch asks for each of its events)."""
    cached = getattr(plan, "_unpreventable_statics", None)
    if cached is not None and cached[0] == len(plan.steps):
        return list(cached[1])
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    found: list[tuple[dict[str, Any], str, str]] = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        if "Room" in ch.subtypes:
            continue  # (a Room door is unlocked or not: not modelled)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i not in skip and d.get("kind") == "static" and d.get("static") == "unpreventable":
                found.append((dict(d.get("scope") or {}), c.controller, plan.oid(c)))
    plan._unpreventable_statics = (len(plan.steps), found)  # type: ignore[attr-defined]
    return list(found)


def protection_applies(plan: Plan, ev: dict[str, Any]) -> bool:
    """Does protection's prevention (702.16e) still prevent this damage? Not when it can't be
    prevented (615.12)."""
    return not unpreventable(plan, ev)


def unpreventable_turn(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Damage can't be prevented this turn." (615.12, 611.2a: until the turn ends)."""
    import secrets

    plan.rules.replacements.append({"id": secrets.token_hex(4), "kind": "unpreventable", "turn": plan.state.turn.number,
                                    "controller": ctx["controller"], "source": ctx.get("source_object"), "scope": {}})
    plan.note("Damage can't be prevented this turn", actor=ctx["controller"])
    return True


# -- 609.7a: the sources a player may choose ------------------------------------------------------------
def _label(plan: Plan, card_id: str | None, oid: str) -> tuple[str, str | None]:
    """A public name for the object and the card id to show (only while the card is public)."""
    from app.game.visibility import publicly_visible

    card = plan.state.cards.get(card_id or "")
    if card is not None and plan.oid(card) == oid:
        if not publicly_visible(plan.state, card):
            return "a face-down permanent", None
        return card.name or "a source", card.id
    snap = plan.rules.lki.get(oid)
    if snap is not None and not snap.face_down:
        return f"{snap.name or 'a source'} (as it last existed)", None
    return "a source", None


def _ch_of(plan: Plan, card_id: str | None, oid: str) -> Any:
    card = plan.state.cards.get(card_id or "")
    if card is not None and plan.oid(card) == oid:
        return plan.ch(card)
    snap = plan.rules.lki.get(oid)
    if snap is not None:
        from app.rules.triggers import _snapshot_card  # (triggers → effects → this module)

        return _snapshot_card(plan, snap)[1]
    return None


def choosable(plan: Plan, props: dict[str, Any]) -> list[tuple[str, list[str], str | None]]:
    """(label, the object ids the choice covers, card id to show) for each source the player may
    choose (609.7a) that has the stated property now (609.7b checks it again later)."""
    found: dict[str, tuple[str | None, list[str]]] = {}  # oid -> (card id, the oids it covers)

    def add(card_id: str | None, oid: str | None, also: list[str] | None = None) -> None:
        if oid and oid not in found:
            found[oid] = (card_id, [oid, *(also or [])])

    r = plan.rules
    for c in plan.state.cards.values():
        zone = c.zone.split(":")[-1]
        if plan.in_game(c) and (zone == "battlefield" or (zone == "command" and not c.face_down)):
            add(c.id, plan.oid(c))
    for sid in plan.state.zones.get("stack", []):
        card = plan.state.cards.get(sid)
        entry = r.stack.get(sid)
        if card is None:
            continue
        if card.ability is None:
            oid = plan.oid(card)
            permanent = bool({"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"} & plan.ch(card).types)
            n = int(oid.rsplit(".", 1)[1])
            # 609.7a: a permanent spell covers the permanent it becomes (the next object of the card, 400.7)
            add(card.id, oid, [f"{card.id}.{n + 1}"] if permanent else None)
        elif entry is not None:
            add(entry.source_card, entry.source_object)
        if entry is None:
            continue
        for t in [*entry.targets, *(t for g in entry.groups for t in g), *(t for s in entry.slots for t in s)]:
            if t.object_id:
                add(t.id, t.object_id)
        if entry.event is not None:
            for ref in [*entry.event.objects, *([entry.event.source] if entry.event.source else [])]:
                add(ref.card, ref.object_id)
    for dt in r.delayed:
        add(dt.source_card, dt.source_object)
    for rec in r.replacements:
        if rec.get("turn") == plan.state.turn.number:
            add(rec.get("source_card"), rec.get("source"))
    out = []
    for oid, (card_id, oids) in found.items():
        ch = _ch_of(plan, card_id, oid)
        if props.get("colors") and (ch is None or not set(props["colors"]) & set(ch.colors)):
            continue
        if props.get("types") and (ch is None or not set(props["types"]) & set(ch.types)):
            continue
        label, shown = _label(plan, card_id, oid)
        out.append((label, oids, shown))
    return sorted(out, key=lambda x: (x[0], x[1][0]))


def _describe(e: dict[str, Any]) -> str:
    kind = " or ".join(w for w, v in {**_COLORS, **_TYPES}.items()
                       if v in (e["props"].get("colors") or []) + (e["props"].get("types") or []))
    what = f"{'an' if kind[:1] in 'aeiou' and kind else 'a'} {kind + ' ' if kind else ''}source"
    if e.get("once"):
        return f"the next time {what} of your choice would deal damage to you this turn, prevent that damage"
    return f"prevent all damage {what} of your choice would deal {'to you ' if e.get('to') else ''}this turn"


def source_shield(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The controller chooses the source as the effect is created (609.7a), among those with the
    property; with only one, it is that one."""
    from app.rules.plan import decide

    pid = ctx["controller"]
    options = choosable(plan, e.get("props") or {})
    if not options:
        plan.note(f"{plan.name(pid)} has no source to choose: the effect does nothing", actor=pid)
        return True
    if len(options) == 1:
        _record(plan, ctx, e, options[0][1], options[0][0])
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"Choose a source: {_describe(e)} (609.7a)",
           options=[DecisionOption(id=f"s{i}", label=label[:120], card_id=shown) for i, (label, _, shown) in enumerate(options)],
           resume={"step": "source_shield", "ctx": ctx, "e": e,
                   "map": {f"s{i}": [oids, label] for i, (label, oids, _) in enumerate(options)}})
    return False


def _record(plan: Plan, ctx: Context, e: dict[str, Any], oids: list[str], label: str) -> None:
    from app.rules import replace

    pid = ctx["controller"]
    match: dict[str, Any] = {"source": {"oids": list(oids), **(e.get("props") or {})},
                             "to": {"players": "you"} if e.get("to") == "you" else {}}
    op: dict[str, Any] = {"do": "prevent_all", "prevention": True, **({"once": True} if e.get("once") else {})}
    replace.add_record(plan, event="damage", match=match, op=op, controller=pid, source=ctx.get("source_object"),
                       source_card=ctx.get("source_card"), label=ctx.get("name") or "a prevention effect")
    plan.note(f"{plan.name(pid)} chose {label}: {_describe(e)}", actor=pid)


def resume_source_shield(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    oids, label = d.resume["map"][chosen[0]]
    _record(plan, ctx, e, oids, label)
    continue_effects(plan, ctx)


PRIMITIVES = {"source_shield": source_shield, "unpreventable_turn": unpreventable_turn}
RESUME = {"source_shield": resume_source_shield}
