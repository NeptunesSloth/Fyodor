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

import json
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
_TO = r"(?P<to>you|any target|target creature|enchanted creature)"  # (-- prevention riders (wave 17A) -- the recipient)
_NEXT_TO_YOU = re.compile(r"the next time (?:a|an) (?:(?P<props>[a-z ]+?) )?source of your choice would deal damage to " + _TO +
                          r" this turn, prevent that damage")
_ALL_BY = re.compile(r"prevent all damage (?:a|an) (?:(?P<props>[a-z ]+?) )?source of your choice would deal "
                     r"(?:to (?P<to>you|any target|target creature|enchanted creature) )?this turn")
_ALL_TO_YOU = re.compile(r"prevent all damage that would be dealt to " + _TO + r" this turn by (?:a|an) (?:(?P<props>[a-z ]+?) )?"
                         r"source of your choice")
_TURN = re.compile(r"damage can't be prevented this turn")
_RECIPIENTS = {"you": ("you", None), "any target": ("target", "any"), "target creature": ("target", "creature"),
               "enchanted creature": ("host", None), None: (None, None)}


def _shield(m: re.Match[str], *, once: bool) -> tuple[list[dict[str, Any]], str | None]:
    props = _props(m["props"])
    if props is None:
        from app.rules.scripts import _NoMatch

        raise _NoMatch
    to, target = _RECIPIENTS[m["to"]]
    return [{"do": "source_shield", "props": props, "once": once, "to": to}], target


def _next_to_you(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return _shield(m, once=True)


def _all_by(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return _shield(m, once=False)


def _all_to_you(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return _shield(m, once=False)


def _turn(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    return [{"do": "unpreventable_turn"}], None


# 615.7 shields beyond the generic template (app/rules/scripts.py ``_prevent``: "any target", "target creature",
# "target player", "~"): "Prevent the next 2 damage that would be dealt to you this turn." (Esper Battlemage),
# "… to target legendary creature …" (Eiganjo Castle), "… to target artifact creature …", "… to target player or
# planeswalker …" (Noble Vestige). The same shield (effects.prevent, ``RulesState.prevention``).
_NEXT_N = re.compile(r"prevent the next (?P<n>\d+|one|two|three|four|five|X) damage that would be dealt (?P<early>this turn )?to "
                     r"(?P<to>you|any target|target player or planeswalker|~|this creature|enchanted creature|"
                     r"each creature you control|each creature and each player|any number of targets, divided as you choose|"
                     r"target (?P<sel>[a-z ]+?))(?P<late> this turn)?")


def _next_n(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, scripts, selectors

    if bool(m["early"]) == bool(m["late"]):
        raise scripts._NoMatch  # ("this turn" once)
    n: Any = {"x": 1} if m["n"] == "X" else scripts.num(m["n"])
    to = m["to"]
    if to.startswith("any number of targets"):  # 601.2d: divided as the spell or ability is put on the stack
        try:
            return [{"do": "prevent", "who": "target", "n": {"divided": 0}}], language._divided("any number of targets", "damage", n)
        except language._Fail:
            raise scripts._NoMatch from None
    if isinstance(n, dict):
        raise scripts._NoMatch  # (X only divided: elsewhere the amount is not read yet)
    if to in ("you", "enchanted creature", "~", "this creature"):
        return [{"do": "prevent", "who": {"you": "you", "enchanted creature": "host"}.get(to, "self"), "n": n}], None
    if to == "any target":
        return [{"do": "prevent", "who": "target", "n": n}], "any"
    if to == "target player or planeswalker":
        return [{"do": "prevent", "who": "target", "n": n}], "player_or_planeswalker"
    if to in ("each creature you control", "each creature and each player"):
        creatures = selectors.parse("creatures" if to.endswith("player") else "creatures you control")
        assert creatures is not None
        return [{"do": "prevent", "who": creatures.key(), "n": n}, *([{"do": "prevent", "who": "each_player", "n": n}]
                                                                    if to.endswith("player") else [])], None
    if m["sel"] == "player":
        return [{"do": "prevent", "who": "target", "n": n}], "player"
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
            # 609.7a: a permanent spell covers the permanent it becomes (400.7: a new object, numbered only as it
            # enters, so the shield names it by the spell object: app/game/rules_state._diff adds the new id)
            add(card.id, oid, [BECOMES + oid] if permanent else None)
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
    to = {"you": "you ", "target": "the target ", "host": "the enchanted creature ", None: ""}[e.get("to")]
    if e.get("once"):
        return f"the next time {what} of your choice would deal damage to {to}this turn, prevent that damage"
    return f"prevent all damage {what} of your choice would deal {'to ' + to if to else ''}this turn"


def source_shield(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The controller chooses the source as the effect is created (609.7a), among those with the
    property; with only one, it is that one."""
    from app.rules.plan import decide

    pid = ctx["controller"]
    if _recipient(plan, ctx, e) is None:  # (-- prevention riders (wave 17A) -- the target it protects is gone: 608.2b)
        plan.note(f"{plan.name(pid)}: nothing is left for the effect to protect", actor=pid)
        return True
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


# -- prevention riders (wave 17A) -- the sources a "prevent all damage … by [them]" effect names (609.7c: any source with the
# property, on the battlefield or not): "red sources", "black and/or red sources", "black sources and red sources", "non-Human
# sources", "artifact sources", "colorless sources", "sources you don't control", "sources your opponents control", "instant and
# sorcery spells" → a spec for replace._source_matches (``alts`` for several descriptions)
_SRC = re.compile(r"^(?P<what>.*?) ?(?P<noun>sources?|creatures)(?P<ctl> you control| you don't control| your opponents control| an opponent controls)?$")


def source_scope(phrase: str) -> dict[str, Any] | None:
    p = phrase.strip()
    if p == "instant and sorcery spells":
        return {"spell": True, "types": ["Instant", "Sorcery"]}
    alts = []
    for part in re.split(r"(?<=sources) and (?=\w)|(?<=creatures) and (?=\w)", p):
        m = _SRC.fullmatch(part)
        if m is None:
            return None
        spec: dict[str, Any] = {"types": ["Creature"]} if m["noun"] == "creatures" else {}
        if m["ctl"]:
            spec["controller"] = "you" if m["ctl"] == " you control" else "opponent"
        words = [w for w in re.split(r" and/or | or ", m["what"]) if w]
        if len(words) > 1 and not all(w in _COLORS for w in words):
            return None  # (a union of colors only)
        for w in words:
            if w in _COLORS:
                spec.setdefault("colors", []).append(_COLORS[w])
            elif w in _TYPES:
                spec["types"] = [_TYPES[w]]
            elif w == "colorless":
                spec["colorless"] = True
            elif w.startswith("non-") and w[4:5].isupper() and w[4:].isalpha():
                spec["not_subtypes"] = [w[4:]]
            else:
                return None
        alts.append(spec)
    return alts[0] if len(alts) == 1 else {"alts": alts}


# -- prevention riders (wave 17A) -- 615.5: "Some prevention effects also include an additional effect, which may refer to
# the amount of damage that was prevented. The prevention takes place at the time the original event would have happened;
# the rest of the effect takes place immediately afterward." The additional effect is a ``rider`` on the prevention effect
# (a shield's ``prevention_riders``, a record's or a static's op): the damage events it prevented some of carry it
# (``ev["riders"]``, replace._damage_apply), and replace.do_damage carries it out once the damage is dealt (``run_rider``),
# "the damage prevented this way" being that effect's own amount. 615.12: a static's rider still happens for damage that can't
# be prevented (nothing is prevented then). Read: "You gain life equal to the damage prevented this way.", "If damage is
# prevented this way, ~ deals that much damage to that source's controller.", "For each 1 damage prevented this way, put a
# +1/+1 counter on that creature.", "Remove a +1/+1 counter from this creature." (a static's). Refused: "When damage is
# prevented this way, …" (a reflexive trigger, 603.12), choices and targets in the rider ("deals that much damage to any
# target"), riders after "of your choice" shields to several recipients.
RIDER_DOS = frozenset({"gain_life", "damage", "add_counters", "remove_counters", "create_token", "mill", "exile_top", "lose_life"})
PREVENTIONS = frozenset({"source_shield", "prevent", "prevent_all"})
_RIDER_IF = re.compile(r"^if damage(?: from (?P<col>an? (?:white|blue|black|red|green) source))? is prevented this way, (?P<body>.+)$")
_ANAPHORS = (("that source's controller", "target player", "from_ctrl"), ("the source's controller", "target player", "from_ctrl"),
             ("that creature", "target creature", "to"))
_READING: list[int] = []
_WHO_OK = frozenset({"you", "self", "each_opponent", "each_player"})
_COLORS_BY_WORD = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def rider_body(body: str, it: str | None = None) -> list[dict[str, Any]] | None:
    """The effects of a rider sentence (first letter lower-cased, no final period), or None (not read). ``it``: what "it" /
    "him" / "her" mean in a static's rider: "self" (the permanent itself) or "to" (the creature the damage was dealt to)."""
    from app.rules import scripts

    text, target = body, None
    if it:
        text = re.sub(r"\b(?:it|him|her)\b", "this creature" if it == "self" else "that creature", text)
    lead = re.match(r"^for each 1 damage prevented this way, (?P<rest>.+)$", text)
    if lead:
        text = f"{lead['rest']} for each 1 damage prevented this way"
    for phrase, surrogate, name in _ANAPHORS:
        if phrase in text:
            if target is not None:
                return None
            text, target = text.replace(phrase, surrogate), (surrogate, name)
    text = re.sub(r"\bthat much (damage|life)\b", r"X \1", text)
    text = re.sub(r"\bthat many\b", "X", text)
    if re.search(r"\bX\b", text):
        text += ", where X is the damage prevented this way"
    _READING.append(1)  # (the rider is read as a sentence of its own: rider() must not look for a prevention before it)
    try:
        found = scripts.parse_effects(text[:1].upper() + text[1:] + ".")
    finally:
        _READING.pop()
    if found is None:
        return None
    effects, spec, optional = found
    if optional or spec != ({"from_ctrl": "player", "to": 'sel:{"types":["Creature"]}'}[target[1]] if target else None):
        return None
    out = []
    for e in effects:
        if e.get("do") not in RIDER_DOS or e.get("optional") or e.get("may"):
            return None
        who = e.get("who")
        if who == "target" and target is not None:
            e = {**e, "who": f"ref:{target[1]}"}
        elif who is not None and who not in _WHO_OK and e.get("do") != "create_token":
            return None
        out.append(e)
    return out


def rider(text: str, effects: list[dict[str, Any]]) -> bool | None:
    """Scripts' sentence hook: a sentence about "the damage prevented this way" after a prevention effect: attach it to that
    effect. None: not such a sentence. False: such a sentence that isn't read (the whole text stays manual)."""
    if _READING or "prevented this way" not in text and not text.startswith("when damage"):
        return None
    if text.startswith("when damage"):
        return False
    m = _RIDER_IF.match(text)
    body = m["body"] if m else text
    if effects == [] or effects[-1].get("do") not in PREVENTIONS or effects[-1].get("rider"):
        return False
    last = effects[-1]
    scope = last.get("scope") or {}
    receives = last["do"] == "prevent" or (last["do"] == "prevent_all" and not any(k.startswith("by_") for k in scope)
                                           and any(k.startswith("to_") for k in scope))
    found = rider_body(body)
    if found is None or (not receives and "ref:to" in json.dumps(found)):  # ("that creature": the one the damage was dealt to)
        return False
    cols = [_COLORS_BY_WORD[m["col"].split()[1]]] if m and m["col"] else []
    effects[-1]["rider"] = {"effects": found, "if": bool(m), **({"colors": cols} if cols else {})}
    return True


def run_rider(plan: Plan, r: dict[str, Any]) -> None:
    """Carry out a prevention effect's additional effect (615.5) after the damage it prevented some of."""
    from app.rules import context, effects

    rider_, ev, n = r["rider"], r["ev"], int(r["n"])
    if rider_.get("if") and n <= 0:
        return
    if rider_.get("colors") and not set(rider_["colors"]) & set((ev.get("src") or {}).get("colors") or ()):
        return
    ctx: Context = {"controller": r["by"], "source_card": r["card"], "source_object": r["oid"], "name": r["name"],
                    "effects": rider_["effects"], "next": 0, "stack_id": ""}
    context.bind_amount(ctx, "prevented", n)
    to = ev["target"]
    if to in plan.state.players:
        context.bind_players(ctx, "to", [to])
    else:
        context.bind_objects(plan, ctx, "to", [to])
    context.bind_players(ctx, "from_ctrl", [p for p in [(ev.get("src") or {}).get("controller")] if p in plan.live()])
    for e in rider_["effects"]:
        effects.PRIMITIVES[e["do"]](plan, ctx, e)


BECOMES = "becomes:"  # (an "oids" entry: the permanent the spell object after it becomes)


def _recipient(plan: Plan, ctx: Context, e: dict[str, Any]) -> dict[str, Any] | None:
    """What the shield protects: nothing named (any recipient), you, or the target / the enchanted creature as the effect is
    created (its object: 400.7; None: it is gone)."""
    to = e.get("to")
    if to is None:
        return {}
    if to == "you":
        return {"players": "you"}
    from app.rules import effects

    cards = effects._cards(plan, ctx, to)
    if cards:
        return {"objects": {"oids": [plan.oid(cards[0])]}}
    players = effects._players(plan, ctx, "target") if to == "target" else []
    return {"pids": [players[0]]} if players else None


def _record(plan: Plan, ctx: Context, e: dict[str, Any], oids: list[str], label: str) -> None:
    from app.rules import replace

    pid = ctx["controller"]
    match: dict[str, Any] = {"source": {"oids": list(oids), **(e.get("props") or {})}, "to": _recipient(plan, ctx, e)}
    op: dict[str, Any] = {"do": "prevent_all", "prevention": True, **({"once": True} if e.get("once") else {}),
                          **({"rider": e["rider"]} if e.get("rider") else {})}  # (wave 17A) 615.5
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
