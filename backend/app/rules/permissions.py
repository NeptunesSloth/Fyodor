"""Cast / play permissions and cost modifiers: the generic infrastructure behind "you may cast
creature spells from the top of your library", "you may play that card this turn", "spells you
cast cost {1} less to cast" and friends.

Rules (stored Comprehensive Rules, 2026-09-25):

* 601.3 — a player can begin to cast a spell only if a rule or effect allows it. By default that
  is a card in their hand (601.2), a commander in the command zone (903.6), flashback (702.34).
  Everything else is a *permission*: a static ability of a permanent on the table (read from the
  table, never stored), or one granted by a resolved spell or ability (a ``Permission`` record in
  ``RulesState.permissions``).
* 400.7h/i — "you may play that card this turn" follows the specific *object* the effect found:
  once the card changes zones it is a new object and the permission no longer applies. Such a
  permission carries the object id; it is never matched by card.
* 601.3b — "as though it had flash": only the timing changes.
* 118.9 — "without paying its mana cost" is an alternative cost of {0}; only one alternative cost
  per spell (118.9a); additional costs (kicker, buyback), increases and reductions still apply to
  it (118.9d).
* 601.2f / 118.7 — total cost = mana cost or alternative cost, plus additional costs and cost
  increases, minus reductions; reductions by generic amounts touch only the generic component
  (118.7a) and never take it below {0}. Commander tax is a cost increase (903.8).
* 401.5 — "play with the top card of your library revealed" / "you may look at the top card of
  your library any time": what the table makes public (``RulesState.top_reveals``, checked by
  ``app.game.visibility``). Casting from the top of the library is only offered when the player
  can see that card; the card becomes public as it moves to the stack, nothing else is revealed.

The grammar (``define_static`` for ability lines, ``parse_clause`` for effect sentences) is a
closed list of wordings; anything else stays manual.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import CostModifier, Permission, TopReveal
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import characteristics as chars
from app.rules import costs, selectors
from app.rules import mana as M
from app.rules.characteristics import CardInfo, Characteristics

if TYPE_CHECKING:
    from app.rules.plan import Plan

Definition = dict[str, Any]

# -- grammar ---------------------------------------------------------------------------------------
_SEL = r"(?P<sel>[a-z][a-z' ,-]*?)"
_N = r"\{(?P<n>\d+)\}"
# "Creature spells you cast cost {1} less to cast." / "Spells your opponents cast cost {2} more to
# cast." / "Noncreature spells cost {1} more to cast." (any caster)
# -- costs (wave 3$) -- also "Aura and Equipment spells you cast cost {1} less" (subtypes are capitalized), "Kithkin spells and
# Soldier spells you cast …", "Each spell you cast that's red or green costs {1} less", "Creature spells you cast with power 4
# or greater cost {2} less", "Historic spells you cast cost {1} less"
_WITH = r"with (?:mana value|power|toughness) \d+ or (?:less|greater|more)"
STATIC_COST = re.compile(
    rf"^(?:each )?(?:{_SEL} )?spells? (?P<who>you cast |your opponents cast )?(?:that's (?:an? )?(?P<thats>[a-z][a-z' ,-]*?) )?"
    rf"(?:(?P<with>{_WITH}) )?costs? {_N} (?P<dir>less|more) to cast$", re.IGNORECASE)
# -- costs (wave 3$) -- "Activated abilities of creatures you control cost {2} less to activate. This effect can't reduce the
# mana in that cost to less than one mana." / "Abilities you activate that aren't mana abilities cost {2} less to activate."
ABILITY_COST = re.compile(
    rf"^(?:activated abilities(?: of (?P<sel>[a-z][a-z' ,-]*?))?|(?P<yours>abilities you activate that aren't mana abilities)) "
    rf"costs? {_N} (?P<dir>less|more) to activate(?:\. (?P<floor>this effect can't reduce the mana in that cost to less than one mana))?$",
    re.IGNORECASE)
# An effect's cost modifier with a duration (611.2a): "Artifact, instant, and sorcery spells you cast this turn cost {2}
# less to cast." (Urza, Planeswalker) / "Until your next turn, instant and sorcery spells you cast cost {1} less to cast."
# (Ral, Leyline Prodigy)
STORED_COST = re.compile(
    rf"^(?P<until>until your next turn, )?{_SEL} spells you cast (?P<this_turn>this turn )?cost {_N} (?P<dir>less|more) to cast$",
    re.IGNORECASE)
# "This spell costs {1} less to cast for each creature card in your graveyard."
SELF_PER = re.compile(rf"^(?:this spell|~) costs {_N} less to cast for each (?P<what>.+)$")
# "This spell costs {1} less to cast if you control a Wizard."
SELF_IF = re.compile(rf"^(?:this spell|~) costs {_N} less to cast if (?P<cond>.+)$")
# "You may cast creature spells from the top of your library." / "You may play lands from your
# graveyard." / "Once during each of your turns, you may cast a creature spell from your graveyard."
PERMISSION = re.compile(
    r"^(?P<once>once during each of your turns, )?you may "
    r"(?P<what>play lands and cast spells|play lands|cast spells|play a land|"
    r"cast (?:a |an )?(?P<sel>[a-z][a-z' ,-]*?) spells?(?P<qual> with mana value \d+ or less)?|cast (?:this card|~))"
    r" from (?P<zone>your graveyard|the top of your library)$")
# "You may cast creature spells as though they had flash." (601.3b)
FLASH = re.compile(rf"^you may cast (?:{_SEL} )?spells as though they had flash$")
TOP_REVEAL = "play with the top card of your library revealed"
TOP_LOOK = "you may look at the top card of your library any time"
# Effect sentences: "Exile the top card of your library. You may play that card this turn." — the
# pronoun ("that card" / "it" / "those cards") is bound by scripts.resolve_it to what an earlier
# instruction of the same ability moved (400.7j: found where it went); with no such instruction
# the ability stays manual. A bare "You may cast that card." (no duration) means "cast it now, as
# this resolves, ignoring timing" — not a permission that lasts: refused.
GRANT_THAT = re.compile(r"^(?:(?P<until>until end of turn|until the end of your next turn), )?you may (?P<verb>play|cast) "
                        r"(?P<what>that card|those cards|it)(?P<this_turn> this turn)?(?P<free> without paying (?:its|their) mana costs?)?$")
# "Until end of turn, you may play lands and cast spells from your graveyard." (Yawgmoth's Will)
GRANT_ZONE = re.compile(r"^(?:(?P<until>until end of turn), )?you may (?P<what>play lands and cast spells|play lands|cast spells)"
                        r" from your graveyard(?P<this_turn> this turn)?$")
# -- cast without paying (wave 3C) --
# "You may cast a spell with mana value 5 or less from your hand without paying its mana cost." (cast now,
# as this resolves: 608.2g) / "You may cast an instant or sorcery spell from your hand with mana value X
# or less without paying its mana cost."
FREE_HAND = re.compile(r"^(?:you may )?cast (?:a|an) (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?(?:spell|card)(?P<h1> from your hand)?"
                       r"(?: with mana value (?:(?P<n>\d+|X) or less|less than or equal to (?P<x2>X)))?(?P<h2> from your hand)?"
                       r" without paying its mana cost$")
# "You may cast spells from your hand without paying their mana costs." (Omniscience) / "You may cast
# Dragon spells without paying their mana costs."
STATIC_FREE = re.compile(r"^you may cast (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells(?P<hand> from your hand)? without paying their mana costs$")
# "If you control a commander, you may cast this spell without paying its mana cost." (Fierce Guardianship)
SELF_FREE = re.compile(r"^if you control a commander, you may cast (?:this spell|~) without paying its mana cost$")
# -- end cast without paying (wave 3C) --


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s[:1].isupper() else s


def spell_filter(phrase: str | None, tail: str | None = None) -> str | None:
    """A selector key for "<phrase> spells [<tail>]" ("creature", "instant and sorcery", "Aura or Equipment";
    tail: "with power 4 or greater"), or None when the grammar doesn't read it (the ability then stays manual)."""
    if phrase is None and tail is None:
        return None
    text = re.sub(r"\band\b", "or", (phrase or "").strip()).strip()
    if text.lower() == "historic":  # 700.6: an artifact, a legendary or a Saga
        sel = selectors.parse("spell")
        sel = replace(sel, extras=("historic",)) if sel is not None else None
    else:
        sel = selectors.parse(f"{text} spell {tail or ''}".replace("  ", " ").strip())
    if sel is None or sel.player is not None or sel.zones != ("stack",):
        return None
    kinds = sum(bool(x) for x in (sel.types, sel.subtypes, sel.colors, sel.supertypes, sel.not_types, sel.colorless))
    if re.search(r"\bor\b|,", text) and not sel.union and kinds > 1:
        return None  # "red or creature" can't be one selector: a list of one kind only
    return sel.key()


def _permission_what(what: str, sel: str | None, qual: str | None) -> dict[str, Any] | None:
    if what in ("play lands and cast spells",):
        return {"play": True, "cast": True, "filter": None}
    if what in ("play lands", "play a land"):
        return {"play": True, "cast": False, "filter": None}
    if what == "cast spells":
        return {"play": False, "cast": True, "filter": None}
    if what in ("cast this card", "cast ~"):
        return {"play": False, "cast": True, "filter": None, "self": True}
    key = spell_filter(f"{sel}{qual or ''}")
    if key is None:
        return None
    return {"play": False, "cast": True, "filter": key}


def define_static(text: str, kind: str, lines: tuple[str, ...] = ()) -> Definition | None:
    """The definition of one ability line (``scripts.define`` calls this for "static" lines, and
    for the "spell" lines of instants and sorceries so a cost-reduction line on a spell is
    understood). ``text`` is the line with the card's own name written as ~; ``lines`` are all
    the card's ability lines (a permission to cast from the top of the library is only usable
    when the card also reveals that card, or lets its owner look at it)."""
    t = _lower_first(text.strip().rstrip("."))
    if kind not in ("static", "spell"):
        return None
    # -- costs (wave 3$) -- "As an additional cost to cast this spell, sacrifice a creature." (601.2b): paid with the
    # rest of the cost as the spell is cast (casting.cast_spell); a wording the cost grammar can't pay stays manual
    extra = costs.additional_cost_text(t)
    if extra is not None:
        ok = costs.parse_additional_cost(extra) is not None
        return {"kind": "static", "static": "additional_cost", "cost": extra, "effects": []} if ok else None
    m = SELF_PER.fullmatch(t)
    if m:
        what = m["what"]
        if what == "opponent":
            return {"kind": "static", "static": "self_cost", "n": int(m["n"]), "per": "opponent", "effects": []}
        sel = selectors.parse(what)
        if sel is None or sel.player is not None:
            return None
        return {"kind": "static", "static": "self_cost", "n": int(m["n"]), "per": sel.key(), "effects": []}
    m = SELF_IF.fullmatch(t)
    if m:
        from app.rules import conditions

        cond = conditions.parse(m["cond"])
        if cond is None or "succeeded" in cond:
            return None
        return {"kind": "static", "static": "self_cost", "n": int(m["n"]), "cond": cond, "effects": []}
    # -- cast without paying (wave 3C) --
    if SELF_FREE.fullmatch(t):
        return {"kind": "static", "static": "permission", "zone": "hand", "once": False, "flash": False, "self": True, "free": True,
                "cond": "commander", "play": False, "cast": True, "filter": None, "effects": []}
    if kind != "static":
        return None
    m = STATIC_FREE.fullmatch(t)
    if m:
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "hand" if m["hand"] else "any", "once": False, "flash": False,
                "self": False, "free": True, "play": False, "cast": True, "filter": key, "effects": []}
    # -- end cast without paying (wave 3C) --
    t = re.sub(r"^(\w+) spells and (\w+) spells ", r"\1 or \2 spells ", t)  # "kithkin spells and soldier spells you cast"
    m = STATIC_COST.fullmatch(t)
    if m:
        if m["sel"] and m["thats"]:
            return None
        phrase = m["sel"] or m["thats"]
        key = spell_filter(phrase, m["with"]) if phrase or m["with"] else None
        if (phrase or m["with"]) and key is None:
            return None
        caster = {None: "any", "you cast ": "you", "your opponents cast ": "opponent"}[m["who"]]
        delta = int(m["n"]) * (-1 if m["dir"] == "less" else 1)
        return {"kind": "static", "static": "cost_modifier", "delta": delta, "caster": caster, "filter": key, "effects": []}
    m = ABILITY_COST.fullmatch(t)
    if m:  # -- costs (wave 3$) -- the source permanent is matched at the cost, relative to the ability's controller
        key = None
        if m["sel"]:
            sel = selectors.parse(m["sel"])
            if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.controller == "opponent" \
                    or sel.extras or sel.attacking or sel.blocking:
                return None
            key = sel.key()
        if m["dir"] == "less" and not m["floor"]:
            return None  # (only the printed wording with its floor is known; never guess a bare reduction)
        return {"kind": "static", "static": "ability_cost_modifier", "delta": int(m["n"]) * (-1 if m["dir"] == "less" else 1),
                "filter": key, "who": "you" if m["yours"] or (m["sel"] and "you control" in m["sel"]) else "any",
                "floor": bool(m["floor"]), "effects": []}
    m = PERMISSION.fullmatch(t)
    if m:
        what = _permission_what(m["what"], m["sel"], m["qual"])
        if what is None:
            return None
        zone = "graveyard" if m["zone"] == "your graveyard" else "library_top"
        if what.get("self") and zone != "graveyard":
            return None
        if zone == "library_top" and not any(_lower_first(x.strip().rstrip(".")) in (TOP_REVEAL, TOP_LOOK) for x in lines):
            # The engine offers a cast from the top of the library only when the player can see
            # that card (401.5; app/rules/view.hints): without a reveal / look line on the same
            # card the permission could never be used — refused rather than claimed
            return None
        return {"kind": "static", "static": "permission", "zone": zone, "once": bool(m["once"]), "flash": False,
                "self": bool(what.get("self")), "play": what["play"], "cast": what["cast"], "filter": what["filter"],
                "effects": []}
    m = FLASH.fullmatch(t)
    if m:
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "any", "once": False, "flash": True, "self": False,
                "play": False, "cast": True, "filter": key, "effects": []}
    if t == TOP_REVEAL:
        return {"kind": "static", "static": "top_reveal", "to": "all", "effects": []}
    if t == TOP_LOOK:
        return {"kind": "static", "static": "top_reveal", "to": "owner", "effects": []}
    return None


def parse_clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """An effect sentence of the permission grammar (see ``scripts._one_clause``), or None.
    ("Exile the top card of your library" itself is the library grammar's: app/rules/language.py.)"""
    m = STORED_COST.fullmatch(text)
    if m and bool(m["until"]) != bool(m["this_turn"]):
        key = spell_filter(m["sel"])
        if key is None:
            return None
        return [{"do": "cost_modifier", "delta": int(m["n"]) * (-1 if m["dir"] == "less" else 1), "filter": key,
                 "until": "next_turn" if m["until"] else "end_of_turn"}], None
    m = FREE_HAND.fullmatch(text)  # -- cast without paying (wave 3C) --
    if m:
        if bool(m["h1"]) == bool(m["h2"]):
            return None
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        return [{"do": "free_cast", "zone": "hand", "filter": key, "optional": True, "mv": "x" if (m["n"] or m["x2"]) == "X" else
                 int(m["n"]) if m["n"] else None}], None
    m = GRANT_THAT.fullmatch(text)
    if m and m["free"] and not (m["until"] or m["this_turn"]):
        if m["verb"] != "cast" or m["what"] == "those cards":
            return None  # (several cards at once, or playing a land as this resolves: not modelled)
        return [{"do": "free_cast", "zone": "that", "who": "it:card", "filter": None, "mv": None, "optional": True}], None
    if m:
        if (m["until"] and m["this_turn"]) or not (m["until"] or m["this_turn"]):
            return None  # (a bare "you may cast that card": cast it as this resolves, not modelled)
        free = bool(m["free"])  # (wave 3C) "... without paying its mana cost" (118.9)
        until = "end_of_next_turn" if m["until"] == "until the end of your next turn" else "end_of_turn"
        # "who": a pronoun for scripts.resolve_it — the object(s) the preceding instruction moved
        # ("that card": a card — never a token the same sentence created, 111.1: scripts.resolve_it)
        return [{"do": "grant_play", "who": "them:card" if m["what"] == "those cards" else "it:card", "play": m["verb"] == "play",
                 "cast": True, "until": until, "optional": True, **({"free": True} if free else {})}], None
    m = GRANT_ZONE.fullmatch(text)
    if m:
        if m["until"] and m["this_turn"]:
            return None
        what = _permission_what(m["what"], None, None)
        assert what is not None
        return [{"do": "grant_play", "zone": "graveyard", "play": what["play"], "cast": what["cast"], "until": "end_of_turn",
                 "optional": True}], None
    return None


# -- what the table grants -------------------------------------------------------------------------
@dataclass(frozen=True)
class Grant:
    """One way a player may cast (or play) a card right now."""

    how: str  # "hand" | "command" | "flashback" | "permission"
    label: str = ""
    zone_ok: bool = True  # it allows the cast from where the card is (a flash-only grant doesn't)
    free: bool = False  # cast without paying its mana cost (118.9)
    flash: bool = False  # as though it had flash (601.3b)
    permission: str | None = None  # the stored Permission's id
    once_key: str | None = None  # a static "once during each of your turns" ability's key


def _view(state: GameState, player: str, info: CardInfo) -> Plan:
    from app.rules.plan import Plan

    return Plan.view(state, player, info)


def spell_matches(state: GameState, player: str, card: CardInstance, ch: Characteristics, key: str, info: CardInfo) -> bool:
    """Would the spell this card becomes match the selector ("creature spells", "red spells")?"""
    probe = card.model_copy(update={"zone": STACK, "controller": player})
    return selectors.matches(_view(state, player, info), selectors.from_key(key), probe, ch, player)


def _table_statics(state: GameState, info: CardInfo, kinds: set[str]) -> list[tuple[CardInstance, int, Definition]]:
    """(permanent, ability index, definition) for the static abilities of the named kinds on the
    battlefield (manual cards and face-down permanents excepted)."""
    from app.rules import scripts
    from app.rules.layers import derive
    from app.rules.plan import live_players

    r = state.rules
    if r is None:
        return []
    live = set(live_players(state))
    out = []
    for card in state.cards.values():
        if not card.zone.endswith(":battlefield") or card.face_down or card.controller not in live \
                or r.card_mode(card.id) == "manual":
            continue
        ch = derive(state, card, chars.of(card, info), info)
        for index, d in scripts.definitions(ch).items():
            if d.get("kind") == "static" and d.get("static") in kinds:
                out.append((card, index, d))
    return out


def _card_zone(state: GameState, player: str, card: CardInstance) -> str | None:
    """Which permission zone the card is in for ``player``: their graveyard, exile (their own
    card), hand, or the top of their library."""
    if card.zone == zone_key(player, "graveyard") and card.owner == player:
        return "graveyard"
    if card.zone == zone_key(player, "hand"):
        return "hand"
    if card.zone.endswith(":exile") and card.owner == player:
        return "exile"
    if card.zone == zone_key(player, "library"):
        library = state.zones.get(card.zone) or []
        return "library_top" if library and library[0] == card.id else None
    return None


def _wants(p: Permission, verb: str) -> bool:
    return p.play if verb == "play" else p.cast


def grants(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo, *,
           verb: str = "cast") -> list[Grant]:
    """Every permission that applies to ``player`` casting (``verb`` "cast") or playing as a land
    ("play") this card from where it is now: stored permissions first, then static abilities of
    permanents they control and the card's own "you may cast this card from your graveyard"."""
    r = state.rules
    if r is None or not ch.types:
        return []
    turn = state.turn.number
    where = _card_zone(state, player, card)
    oid = r.object_id(card.id)
    out: list[Grant] = []
    for p in r.permissions:
        if p.player != player or not _wants(p, verb) or (p.once and p.used_turn == turn):
            continue
        if p.object_id is not None:
            if p.object_id != oid:
                continue  # a new object since (400.7): the permission was for the one it was
        elif p.zone != "any" and p.zone != where:
            continue
        if p.filter and verb == "cast" and not spell_matches(state, player, card, ch, p.filter, info):
            continue
        zone_ok = p.object_id is not None or p.zone != "any"  # (a flash-only permission grants no zone)
        out.append(Grant("permission", p.label, zone_ok=zone_ok, free=p.free, flash=p.flash, permission=p.id))
    if verb == "cast" and where == "graveyard" and card.owner == player:
        for index, d in _definitions(ch).items():  # the card's own ability, functioning in the graveyard (113.6)
            if d.get("static") == "permission" and d.get("self") and d["zone"] == "graveyard":
                key = f"{card.id}:permission:{index}"
                if d["once"] and r.once_per_turn.get(key) == turn:
                    continue
                out.append(Grant("permission", f"{ch.name}: cast it from your graveyard", once_key=key if d["once"] else None))
    if verb == "cast" and where == "hand":  # -- cast without paying (wave 3C) -- the card's own "cast this spell without paying"
        for d in _definitions(ch).values():
            if d.get("static") == "permission" and d.get("self") and d.get("free") and d["zone"] == "hand" \
                    and (d.get("cond") != "commander" or _controls_commander(state, player)):
                out.append(Grant("permission", f"{ch.name}: cast it without paying its mana cost", free=True))
    for src, index, d in _table_statics(state, info, {"permission"}):
        if src.controller != player or d.get("self") or not d[verb]:
            continue
        if d["zone"] != "any" and d["zone"] != where:
            continue
        if d["filter"] and verb == "cast" and not spell_matches(state, player, card, ch, d["filter"], info):
            continue
        key = f"{src.id}:permission:{index}"
        if d["once"] and (r.once_per_turn.get(key) == turn or state.turn.active_player != player):
            continue  # "once during each of your turns"
        out.append(Grant("permission", src.name, zone_ok=d["zone"] != "any", flash=d["flash"], free=bool(d.get("free")),
                         once_key=key if d["once"] else None))
    return out


def _controls_commander(state: GameState, player: str) -> bool:
    """"If you control a commander": a commander (of any player) on the battlefield under your control."""
    return any(c.commander_key is not None and c.controller == player and c.zone.endswith(":battlefield")
               for c in state.cards.values())


def _definitions(ch: Characteristics) -> dict[int, Definition]:
    from app.rules import scripts

    return scripts.definitions(ch)


def consume(plan: Plan, grant: Grant | None) -> None:
    """The spell was cast (or the land played) this way: a once-per-turn permission is used up."""
    if grant is None:
        return
    r = plan.rules
    turn = plan.state.turn.number
    if grant.once_key:
        r.once_per_turn[grant.once_key] = turn
    if grant.permission:
        for p in r.permissions:
            if p.id == grant.permission and p.once:
                p.used_turn = turn
        # "you may play that card": the card is a new object on the stack / battlefield now (400.7)
        r.permissions = [p for p in r.permissions if not (p.id == grant.permission and p.object_id is not None)]


# -- costs (601.2f) --------------------------------------------------------------------------------
def _add(a: M.ManaCost, b: M.ManaCost) -> M.ManaCost:
    return M.ManaCost(a.generic + b.generic, a.colored + b.colored, a.hybrid + b.hybrid, a.phyrexian + b.phyrexian,
                      a.x, a.unsupported + b.unsupported)


def modifiers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[CostModifier]:
    """The cost modifiers that apply to ``player`` casting this spell: static abilities on the
    table ("Creature spells you cast cost {1} less to cast", "Spells your opponents cast cost {2}
    more to cast") and stored ones with a duration."""
    r = state.rules
    if r is None:
        return []
    found: list[CostModifier] = []
    for src, index, d in _table_statics(state, info, {"cost_modifier"}):
        found.append(CostModifier(id=f"{src.id}:{index}", controller=src.controller, delta=d["delta"], caster=d["caster"],
                                  filter=d["filter"], until="permanent", source=r.object_id(src.id), label=src.name))
    found += [m for m in r.cost_modifiers  # ("until your next turn": over once its controller's next turn began)
              if not (m.until == "next_turn" and r.turn_started.get(m.controller, 0) > m.turn)]
    out = []
    for m in found:
        if m.caster == "you" and m.controller != player:
            continue
        if m.caster == "opponent" and m.controller == player:
            continue
        if m.filter and not spell_matches(state, player, card, ch, m.filter, info):
            continue
        out.append(m)
    return out


def self_reduction(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> int:
    """The spell's own reductions: "costs {1} less to cast for each …" / "… if …", undaunted (702.125)."""
    from app.rules import conditions
    from app.rules.plan import live_players

    total = 0
    opponents = sum(1 for p in live_players(state) if p != player)
    if "undaunted" in ch.keywords:
        total += opponents
    view = None
    for d in _definitions(ch).values():
        if d.get("static") != "self_cost":
            continue
        if d.get("per") == "opponent":
            total += d["n"] * opponents
            continue
        view = view or _view(state, player, info)
        if d.get("per"):
            total += d["n"] * len(selectors.candidates(view, selectors.from_key(d["per"]), player, card.id))
        elif d.get("cond") is not None and conditions.holds(view, {"controller": player, "source_card": card.id}, d["cond"]):
            total += d["n"]
    return total


def total_cost(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo | None, *,
               base: M.ManaCost, additional: tuple[M.ManaCost, ...] = (), tax: int = 0, affinity: int = 0) -> M.ManaCost:
    """601.2f: the mana cost or alternative cost (``base``), plus additional costs (kicker,
    buyback: 118.8) and cost increases (commander tax, "cost {N} more"), minus cost reductions
    (affinity, "cost {N} less", the spell's own). Reductions affect only the generic component
    (118.7a) and can't take it below {0}."""
    cost = base
    for extra in additional:
        cost = _add(cost, extra)
    increase = tax
    reduction = affinity
    if info is not None:
        for m in modifiers(state, player, card, ch, info):
            if m.delta > 0:
                increase += m.delta
            else:
                reduction -= m.delta
        reduction += self_reduction(state, player, card, ch, info)
    cost = cost.plus_generic(increase)
    return cost.plus_generic(-min(cost.generic, reduction))


# -- costs (wave 3$) -- cost modifiers for activated abilities (602.2b -> 601.2f, 118.7) ---------------------
def ability_mana(state: GameState, player: str, card: CardInstance, ch: Characteristics, mana: str, info: CardInfo) -> str:
    """The mana part of an activated ability's cost after "Activated abilities of creatures you control cost {2} less to
    activate" and its increases: increases first, then reductions on the generic component only (118.7a, 601.2f), and with
    "can't reduce the mana in that cost to less than one mana" never below one mana. Costs with {X} are left alone."""
    mods = [(src, d) for src, _, d in _table_statics(state, info, {"ability_cost_modifier"})]
    if not mods or not mana:
        return mana
    cost = M.parse_cost(mana)
    if cost.x or cost.unsupported:
        return mana
    view = None
    increase = reduction = 0
    floor = False
    for src, d in mods:
        if d["who"] == "you" and src.controller != player:
            continue
        if d["filter"]:
            view = view or _view(state, player, info)
            if not selectors.matches(view, selectors.from_key(d["filter"]), card, ch, src.controller, src.id):
                continue
        if d["delta"] > 0:
            increase += d["delta"]
        else:
            reduction -= d["delta"]
            floor = floor or d["floor"]
    if not increase and not reduction:
        return mana
    cost = cost.plus_generic(increase)
    cut = min(cost.generic, reduction)
    if floor:
        symbols = cost.generic + len(cost.colored) + len(cost.hybrid) + len(cost.phyrexian)
        cut = min(cut, max(0, symbols - 1))
    return cost.plus_generic(-cut).text()


# -- effects ---------------------------------------------------------------------------------------
def grant_play(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"You may play that card this turn" (the objects an earlier instruction of this ability
    moved — bound by scripts.resolve_it, found where they went: 400.7h/j) or "Until end of turn,
    you may play lands and cast spells from your graveyard"."""
    from app.rules import context

    pid = ctx["controller"]
    r = plan.rules
    turn = plan.state.turn.number
    when = "until the end of their next turn" if e["until"] == "end_of_next_turn" else \
        "for as long as it remains there" if e["until"] == "permanent" else "this turn"  # (permanent: wave 3E, 611.2a)
    verb = "play" if e["play"] else "cast"
    if e.get("who"):
        if not str(e["who"]).startswith(context.PREFIX):
            return True  # (an unbound pronoun never reaches here: resolve_it refuses the ability)
        for cid in context.objects(plan, ctx, e["who"][len(context.PREFIX):]):
            card = plan.state.cards[cid]
            r.permissions.append(Permission(id=secrets.token_hex(4), player=pid, play=e["play"], cast=e["cast"], zone="any",
                                            object_id=plan.oid(card), card=cid, until=e["until"], turn=turn, free=bool(e.get("free")),
                                            source=ctx.get("source_object"), label=f"{ctx.get('name') or 'An effect'}: {verb} it {when}" + (" without paying its mana cost" if e.get("free") else "")))
            plan.note(f"{plan.name(pid)} may {verb} {card.name} {when}", [cid])
        return True
    r.permissions.append(Permission(id=secrets.token_hex(4), player=pid, play=e["play"], cast=e["cast"], zone=e["zone"],
                                    until=e["until"], turn=turn, source=ctx.get("source_object"),
                                    label=f"{ctx.get('name') or 'An effect'}: {verb} from your {e['zone']} {when}"))
    what = "play lands and cast spells" if e["play"] and e["cast"] else "play lands" if e["play"] else "cast spells"
    plan.note(f"{plan.name(pid)} may {what} from their {e['zone']} {when}")
    return True


def expire(plan: Plan) -> None:
    """514.2: "this turn" / "until end of turn" permissions and modifiers end in the cleanup step;
    "until the end of your next turn" ones at the end of that player's next turn; a permission
    for an object that is gone (400.7) is dropped too."""
    r = plan.rules
    turn = plan.state.turn.number
    active = plan.active
    keep = []
    for p in r.permissions:
        if p.until == "end_of_turn":
            continue
        if p.until == "end_of_next_turn" and p.player == active and turn > p.turn:
            continue
        if p.object_id is not None and (p.card not in plan.state.cards or r.object_id(p.card) != p.object_id):
            continue
        keep.append(p)
    r.permissions = keep
    r.cost_modifiers = [m for m in r.cost_modifiers if m.until != "end_of_turn"
                        and not (m.until == "next_turn" and r.turn_started.get(m.controller, 0) > m.turn)]


def cost_modifier(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"<Spells> you cast this turn cost {N} less to cast" / "Until your next turn, <spells> you cast
    cost {N} less to cast": a cost modifier for its controller's spells with that duration (601.2f,
    611.2a; generic mana only, 118.7a), read with the table's static ones (``modifiers``)."""
    pid = ctx["controller"]
    plan.rules.cost_modifiers.append(CostModifier(
        id=secrets.token_hex(4), controller=pid, delta=int(e["delta"]), caster="you", filter=e.get("filter"),
        until=e["until"], turn=plan.state.turn.number, source=ctx.get("source_object"),
        label=(ctx.get("name") or "An effect")[:120]))
    amount = f"{{{abs(int(e['delta']))}}} {'less' if int(e['delta']) < 0 else 'more'}"
    plan.note(f"{plan.name(pid)}'s spells cost {amount} to cast "
              + ("until their next turn" if e["until"] == "next_turn" else "this turn") + f" ({ctx.get('name') or 'an effect'})")
    return True


def refresh_reveals(state: GameState, info: CardInfo) -> None:
    """Recompute which cards of the game have a "play with the top card of your library revealed"
    / "you may look at the top card of your library any time" ability (401.5): every card, in
    whatever zone, since the view (``app.game.visibility``, which has no card database) reads the
    *table* for the rest — whether the source is on a battlefield right now, face up, and under
    whose control — so a source put onto the battlefield, taken or removed by hand reveals the
    right library at once, with no engine action in between. Pure: a function of the cards and
    the database, so replay reproduces it. ``player`` records the controller as listed, for
    information only."""
    from app.rules import scripts
    from app.rules.layers import derive

    r = state.rules
    if r is None:
        return
    found = []
    for card in state.cards.values():
        if card.ability is not None:
            continue
        ch = chars.of(card, info)
        if card.zone.endswith(":battlefield") and not card.face_down:
            ch = derive(state, card, ch, info)
        for d in scripts.definitions(ch).values():
            if d.get("kind") == "static" and d.get("static") == "top_reveal":
                found.append(TopReveal(source=card.id, player=card.controller, to=d["to"]))
    if found != r.top_reveals:
        r.top_reveals = found


# -- cast without paying (wave 3C) --
def free_cast(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"You may cast a spell with mana value N or less from your hand without paying its mana cost" /
    "you may cast that card without paying its mana cost": as this resolves (608.2g) its controller
    picks one eligible card (or none); the engine then lets them cast it for {0} (118.9: X is 0,
    107.3b; kicker and other additional costs may still be paid, 118.9d). Nothing is kept: a card
    not cast now can't be cast this way later."""
    from app.game.rules_state import DecisionOption
    from app.rules import characteristics as chars
    from app.rules import context, values
    from app.rules.effects import decide

    pid = ctx["controller"]
    if e["zone"] == "hand":
        pool = list(plan.state.zones.get(zone_key(pid, "hand"), []))
    else:
        who = str(e.get("who") or "")
        pool = context.objects(plan, ctx, who[len(context.PREFIX):]) if who.startswith(context.PREFIX) else []
    limit = None
    if e.get("mv") is not None:
        limit = values.evaluate(plan, ctx, {"x": 1}) if e["mv"] == "x" else int(e["mv"])
    options = []
    for cid in pool:
        card = plan.state.cards[cid]
        ch = chars.of(card, plan.info)
        if not ch.types or ch.is_land or plan.rules.card_mode(cid) == "manual":
            continue
        if limit is not None and ch.mana_value > limit:
            continue
        if e.get("filter") and not spell_matches(plan.state, pid, card, ch, e["filter"], plan.info):
            continue
        options.append(DecisionOption(id=cid, label=card.name or "Card", card_id=cid))
    if not options:
        plan.note(f"{plan.name(pid)} has nothing to cast without paying its mana cost")
        return True
    decide(plan, player=pid, kind="choose_cards", prompt="Choose a spell to cast without paying its mana cost (or none)",
           options=options, min_choices=0, max_choices=1, resume={"step": "free_cast_pick", "ctx": ctx})
    return False


def resume_free_cast(plan: Plan, d: Any, chosen: list[str]) -> None:
    from types import SimpleNamespace

    from app.rules import effects

    ctx = d.resume["ctx"]
    if not chosen:
        effects.continue_effects(plan, ctx)
        return
    plan.rules.free_casts.append(chosen[0])
    effects.resume_suspend_cast(plan, SimpleNamespace(resume={"ctx": ctx, "card": chosen[0]}, player=d.player), ["yes"])
# -- end cast without paying (wave 3C) --
