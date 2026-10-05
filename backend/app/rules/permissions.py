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
from app.rules import cost_changes, costs, selectors
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
# -- equip (wave 15E) -- "Equip abilities you activate cost {1} less to activate." (Bureau Headmaster), "Equip costs you pay cost
# {1} less." (Auriok Steelshaper), "Equip abilities you activate of other Equipment cost {1} less to activate." (Bladehold
# War-Whip): a cost modifier (601.2f) of equip abilities only (attachments.is_equip_text), the player's own
EQUIP_COST = re.compile(
    rf"^equip (?:abilities you activate(?P<other> of other equipment)?|costs you pay) costs? {_N} (?P<dir>less|more)(?: to activate)?$",
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
    r" from (?P<zone>your graveyard|the top of your library)"
    # -- cast from graveyard (wave 19C) -- 614.1a: "If a spell cast this way would be put into your graveyard, exile it instead."
    r"(?:\. If (?P<exile>a|an instant or sorcery) spell cast this way would be put into your graveyard, exile it instead)?$", re.IGNORECASE)
SELF_GY_BY = re.compile(r"^you may cast (?:this card|~) from your graveyard by (?P<cost>.+) in addition to paying its other costs"
                        r"(?P<exile>\. Then exile this card)?$")  # (-- casting extras (wave 18E) -- jump-start 702.133a: exiled as it leaves the stack)
# -- keyword grants (wave 17C) -- 702.81a: "Instant and sorcery cards in your graveyard have retrace." / "During your turn, nonland
# permanent cards in your graveyard have retrace." — a permission to cast those cards from the graveyard whose additional cost is
# discarding a land card (the granted keyword's meaning, as the card's own retrace line says it)
RETRACE_GRANT = re.compile(r"^(?P<during>during your turn, )?(?P<sel>[a-z][a-z' ,-]*?) cards in your graveyard have retrace$", re.IGNORECASE)
_GERUND = {"discarding": "discard", "paying": "pay", "sacrificing": "sacrifice", "exiling": "exile"}
# -- free_cast (wave 20D) -- "You may cast this card from exile." (Eternal Scourge), "… from your graveyard or from exile." (Squee, the
# Immortal): the card's own ability, functioning in those zones (113.6b), a permission to cast it from where it is
SELF_EXILE = re.compile(r"^you may cast (?:this card|~) from (?P<z>exile|your graveyard or from exile)$")
SELF_GY_WHILE = re.compile(r"^you may cast (?:this card|~) from your graveyard (?:as long as|if) (?P<cond>.+)$")  # (wave 4B; 16D: "if")
# "You may cast creature spells as though they had flash." (601.3b)
FLASH = re.compile(rf"^you may cast (?:{_SEL} )?spells as though they had flash$")
TOP_REVEAL = "play with the top card of your library revealed"
TOP_LOOK = "you may look at the top card of your library any time"
# 708.5 lets you look at your own face-down permanents only; these let you look at the others' (creatures: face-down spells aren't
# permanents). In Commander every other player is an opponent.
FACE_DOWN_LOOK = re.compile(r"^you may look at (?P<top>the top card of your library and at )?face-down creatures "
                            r"(?:you don't control|your opponents control) any time$")
# Effect sentences: "Exile the top card of your library. You may play that card this turn." — the
# pronoun ("that card" / "it" / "those cards") is bound by scripts.resolve_it to what an earlier
# instruction of the same ability moved (400.7j: found where it went); with no such instruction
# the ability stays manual. A bare "You may cast that card." (no duration) means "cast it now, as
# this resolves, ignoring timing" — not a permission that lasts: refused.
GRANT_THAT = re.compile(r"^(?:(?P<until>until end of turn|until the end of your next turn|until your next end step), )?you may (?P<verb>play|cast) "
                        r"(?P<what>that card|those cards|it)(?P<this_turn> this turn)?(?P<free> without paying (?:its|their) mana costs?)?$")
# -- refused grants/replacements (wave 3R2) -- "You may play that card until the end of your next turn."
_TRAILING_UNTIL = re.compile(r"^(?P<rest>you may (?:play|cast) (?:that card|those cards|it|them)(?: without paying (?:its|their) mana costs?)?) "
                             r"(?P<until>until end of turn|until the end of your next turn|until your next end step)$")
# -- end refused grants/replacements (wave 3R2) --
# "Until end of turn, you may play lands and cast spells from your graveyard." (Yawgmoth's Will)
GRANT_ZONE = re.compile(r"^(?:(?P<until>until end of turn), )?you may (?P<what>play lands and cast spells|play lands|cast spells)"
                        r" from your graveyard(?P<this_turn> this turn)?$")
# -- cast a copy (wave 13C) -- "You may cast the copy without paying its mana cost." (707.12; each copy is its own choice, 707.12a)
# (wave 18F: without "without paying …" the copy's mana cost is paid: 707.12 "You may cast the copy. (You still pay its costs.)")
FREE_COPY = re.compile(r"^(?:if you do, )?you may cast (?P<w>the copy|the copies|any number of the copies)(?P<free> without paying (?:its|their) mana costs?)?$")
# -- cast without paying (wave 3C) --
# "You may cast a spell with mana value 5 or less from your hand without paying its mana cost." (cast now,
# as this resolves: 608.2g) / "You may cast an instant or sorcery spell from your hand with mana value X
# or less without paying its mana cost."
FREE_HAND = re.compile(r"^(?:you may )?cast (?:a|an) (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?(?:spell|card)(?P<h1> from your hand)?"
                       r"(?: with mana value (?:(?P<n>\d+|X) or less|less than or equal to (?P<x2>[^,]+?)))?(?P<h2> from your hand)?"
                       r" without paying its mana cost$")
# "You may cast spells from your hand without paying their mana costs." (Omniscience) / "You may cast
# Dragon spells without paying their mana costs."
STATIC_FREE = re.compile(r"^you may cast (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells(?P<hand> from your hand)? without paying their mana costs$")
# "If you control a commander, you may cast this spell without paying its mana cost." (Fierce Guardianship)
SELF_FREE = re.compile(r"^if you control a commander, you may cast (?:this spell|~) without paying its mana cost$")
# -- end cast without paying (wave 3C) --
# -- refused look/cast-free (wave 3R5) -- casts made as the ability resolves (608.2g), with more
# instructions after them: "You may cast an instant or sorcery spell with mana value less than or
# equal to ~'s power from among them without paying its mana cost." (the cards looked at / exiled),
# "You may cast any number of spells with mana value X or less from among them without paying their
# mana costs.", "You may cast up to two sorcery spells …", "You may cast target instant or sorcery
# card with mana value 3 or less from your graveyard without paying its mana cost."
_FREE_MV = r"with mana value (?:(?P<n>\d+|X) or less|less than or equal to (?P<v>[^,]+?))"
FREE_AMONG = re.compile(
    r"^(?:you may )?cast (?:(?P<q>a|an|up to (?P<k>one|two|three)|any number of) )?(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?(?P<sp>spells?)"
    rf"(?: {_FREE_MV.replace('?P<n>', '?P<n1>').replace('?P<v>', '?P<v1>')})?"
    r" from among (?P<src>them|those cards|those nonland cards|cards revealed this way|the revealed cards|the exiled cards"
    r"|cards exiled this way|the cards exiled this way)"
    rf"(?: {_FREE_MV.replace('?P<n>', '?P<n2>').replace('?P<v>', '?P<v2>')})?"
    r" without paying (?:its|their) mana costs?$")
# "Once during each of your turns, you may cast an instant or sorcery spell from your hand without paying its
# mana cost." (Zaffai and the Tempests): a static permission used up by the cast (``consume``), on its
# controller's own turns only, with the cast's normal timing (601.3: a permission, not a cast as something resolves)
ONCE_FREE = re.compile(r"^once during each of your turns, you may cast (?:a|an) (?:(?P<sel>[a-z][a-z' ,-]*?) )?spell from your hand "
                       r"without paying its mana cost$")
FREE_TARGET = re.compile(r"^(?:you may )?cast (?P<what>target .+?) without paying its mana cost$")
_FREE_COUNT = {"a": 1, "an": 1, "up to one": 1, "up to two": 2, "up to three": 3, "any number of": 99}


def free_mv(n: str | None, v: str | None) -> Any:
    """The mana value limit of a free cast: a number, "x" (the X of the spell or ability), or a
    value read as it resolves (608.2h): "~'s power", "that damage" (the trigger event's amount),
    "the number of Spirits you control" (app/rules/values.py). Raises ValueError if unread."""
    from app.rules import language

    if n is not None:
        return "x" if n == "X" else int(n)
    if v is None:
        return None
    if v == "X":
        return "x"
    if v in ("that damage", "the damage dealt", "the amount of damage dealt"):
        return {"event_amount": 1}
    try:
        value = language._stat(v.replace("this creature's", "~'s"), "self")
    except Exception as exc:  # noqa: BLE001  (language._Fail: a phrase the value grammar doesn't read)
        raise ValueError(v) from exc
    if not isinstance(value, dict) or "it" in value.values():
        raise ValueError(v)  # ("its power": whose? not bound here)
    return value


def _free_among(text: str) -> list[dict[str, Any]] | None:
    m = FREE_AMONG.fullmatch(text)
    if m is None:
        return None
    if (m["n1"] or m["v1"]) and (m["n2"] or m["v2"]):
        return None
    if m["q"] is None and m["sp"] != "spells":
        return None  # ("cast instant and sorcery spells … from among them": any number of them; "cast spell": not English)
    key = spell_filter(m["sel"]) if m["sel"] else None
    if m["sel"] and key is None:
        return None
    try:
        mv = free_mv(m["n1"] or m["n2"], m["v1"] or m["v2"])
    except ValueError:
        return None
    # "zone": "among" — resolved to the cards looked at (still in the library: "looked") or to the
    # cards an earlier instruction moved ("that", a binding) by scripts.resolve_it
    return [{"do": "free_cast", "zone": "among", "who": "them:card", "filter": key, "optional": True, "mv": mv,
             "n": _FREE_COUNT[m["q"] or "any number of"]}]


# "You may cast it without paying its mana cost if it's a spell with lesser mana value." (Rashmi, Eternities
# Crafter), "… if its mana value is odd." (Yennett), "… if that spell's mana value is 8 or less.", "… if the
# spell's mana value is less than the number of Mountains you control.", "… if it's an instant or sorcery spell."
FREE_IF = re.compile(r"^(?:then )?you may cast (?:it|that card|the exiled card|the revealed card) without paying its mana cost "
                     r"if (?P<cond>.+)$")
_MV_OF = r"(?:its|that spell's|the spell's) mana value is"
# "You may cast an instant or sorcery spell from your graveyard with mana value 4 or less without paying its mana
# cost." (Diviner of Mist) / "… from a graveyard …" (every graveyard: public, 400.2)
FREE_GY = re.compile(r"^(?:you may )?cast (?:a|an) (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spell(?P<g1> from (?P<w1>your|a) graveyard)?"
                     rf"(?: {_FREE_MV})?(?P<g2> from (?P<w2>your|a) graveyard)? without paying its mana cost$")


def _free_if(text: str) -> list[dict[str, Any]] | None:
    """The cast of the card just revealed / exiled, on a condition about the spell it would be: a mana
    value limit (``mv``: at most, ``mv_lt``: less than), its parity, or a kind of spell (``filter``)."""
    m = FREE_IF.fullmatch(text)
    if m is None:
        return None
    cond = m["cond"]
    e: dict[str, Any] = {"do": "free_cast", "zone": "that", "who": "it:card", "filter": None, "optional": True, "mv": None, "n": 1}
    try:
        if cond == "it's a spell with lesser mana value":  # (than the spell that triggered it: Rashmi)
            e["mv_lt"] = {"mana_value": "event"}
        elif (c := re.fullmatch(rf"(?:it's a spell with mana value|{_MV_OF}) (?:(?P<n>\d+) or less|less than or equal to "
                                r"(?P<v>.+)|less than (?P<lt>.+))", cond)):
            if c["lt"]:
                e["mv_lt"] = free_mv(None, c["lt"])
            else:
                e["mv"] = free_mv(c["n"], c["v"])
        elif (c := re.fullmatch(rf"{_MV_OF} (?P<p>odd|even)", cond)):
            e["parity"] = c["p"]
        elif (c := re.fullmatch(r"it's (?:a|an) (?P<sel>[a-z][a-z ,]*?) spell", cond)):
            e["filter"] = spell_filter(c["sel"])
            if e["filter"] is None:
                return None
        else:
            return None
    except ValueError:
        return None
    return [e]


def _free_gy(text: str) -> list[dict[str, Any]] | None:
    m = FREE_GY.fullmatch(text)
    if m is None or bool(m["g1"]) == bool(m["g2"]):
        return None
    key = spell_filter(m["sel"]) if m["sel"] else None
    if m["sel"] and key is None:
        return None
    try:
        mv = free_mv(m["n"], m["v"])
    except ValueError:
        return None
    return [{"do": "free_cast", "zone": "graveyard", "whose": "you" if (m["w1"] or m["w2"]) == "your" else "any",
             "filter": key, "optional": True, "mv": mv, "n": 1}]


def _free_target(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """"You may cast target instant or sorcery card [with mana value N or less] from your graveyard
    without paying its mana cost": a target card in a graveyard (public: 400.2), cast as this
    resolves if it's still a legal target (608.2b)."""
    m = FREE_TARGET.fullmatch(text)
    if m is None:
        return None
    phrase = m["what"][len("target "):]
    mv = re.search(rf" {_FREE_MV}(?= from )", phrase)
    if mv and mv["v"] is not None:
        return None  # (a limit read as it resolves: the target's legality would change with it; not modelled)
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones != ("graveyard",) or not sel.card:
        return None
    return [{"do": "free_cast", "zone": "target", "filter": None, "optional": True, "mv": None, "n": 1}], sel.key()
# -- end refused look/cast-free (wave 3R5) --


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
    # (-- cost changers (wave 20E) -- "red or green creature": any of those colors, and the type: the colors are one list, 105.1)
    colors_then_type = re.fullmatch(r"(?:white|blue|black|red|green)(?:(?: or|,) (?:white|blue|black|red|green))+ [a-z]+", text, re.I)
    if re.search(r"\bor\b|,", text) and not sel.union and kinds > 1 and not (colors_then_type and len(sel.colors) > 1 and sel.types):
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
    # -- cost changers (wave 4I) -- "This spell costs {X} less to cast, where X is …" / "… for each …" / "… if …" / "{G} less"
    # (app/rules/cost_changes.py: read as the total cost is determined, 601.2f)
    # -- static_other sweep (wave 16B) -- strive (207.2c ability word) / Fireball: "This spell costs {1}{W} more to cast for each target beyond the
    # first." — an additional cost determined once the targets are chosen (601.2b, 601.2f: total_cost reads them)
    if (sv := _PER_TARGET.fullmatch(t)) is not None:
        pc = M.parse_cost(sv["cost"])
        if pc.hybrid or pc.phyrexian or pc.x or pc.unsupported or pc.is_free:
            return None
        return {"kind": "static", "static": "self_cost", "per_target": sv["cost"], "effects": []}
    if cost_changes.is_self(t):
        change = cost_changes.self_change(t)
        return {"kind": "static", "static": "self_cost", "change": change, "effects": []} if change else None
    # -- mana provenance (wave 18B) -- K'rrik: each {B} of any cost may be paid with 2 life instead (118.1: life is paid like a Phyrexian
    # symbol; 601.2h: while the cost is paid, casting.life_for_mana)
    if t == "for each {B} in a cost, you may pay 2 life rather than pay that mana":
        return {"kind": "static", "static": "life_for_mana", "sym": "B", "life": 2, "effects": []}
    if " have prowl " in t and kind == "static":  # -- static_other sweep (wave 17C) -- granted prowl (702.76a)
        from app.rules import alt_costs

        return alt_costs.grant_prowl(t)
    if " rather than pay " in t or (" without paying its mana cost" in t and t.startswith("if ") and "commander" not in t):  # alternative costs (118.9): app/rules/alt_costs.py
        from app.rules import alt_costs

        found_alt = alt_costs.define(t)
        if found_alt is not None and (kind == "static" or not found_alt.get("table")):
            return found_alt
    if kind == "static" and t.startswith("as an additional cost to cast "):  # Defiler of Vigor (cost_changes.py)
        return cost_changes.optional_definition(t)
    # -- end cost changers (wave 4I) --
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
    # -- cost alt (wave 16F) -- "You may cast this card from your graveyard by discarding a card in addition to paying its other
    # costs." (Alien Symbiosis): a permission to cast it from there whose additional cost (601.2b) is paid with its mana cost
    m = SELF_GY_BY.fullmatch(t)
    if m:
        extra = re.sub(r"\b(discarding|paying|sacrificing|exiling)\b", lambda g: _GERUND[g[1]], m["cost"])
        if costs.parse_additional_cost(extra) is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False, "flash": False, "self": True,
                "play": False, "cast": True, "filter": None, "extra": extra, "effects": [], **({"exile": True} if m["exile"] else {})}
    if kind != "static":
        return None
    # -- small wordings (wave 11E) -- "Creature spells you control can't be countered." (101.2, 701.6)
    # (-- cant restrictions (wave 20F) -- "Creature spells can't be countered" (Gaea's Herald), "Creature spells you cast …", "… you control
    # with power 5 or greater …": whose spells, and a with-tail; 101.2, 701.6)
    m = re.fullmatch(r"(?:(?P<sel>[\w ,'-]+?) )?spells(?: (?P<own>you control|you cast))?(?: (?P<with>with (?:power|toughness) "
                     r"\d+ or (?:greater|less)))? can't be countered", t)  # (not "mana value": a spell's X, 107.3f, isn't read here)
    if m:
        key = spell_filter(m["sel"], m["with"]) if m["sel"] or m["with"] else None
        if (m["sel"] or m["with"]) and key is None:
            return None
        return {"kind": "static", "static": "spells_uncounterable", "filter": key, "effects": [], **({} if m["own"] else {"any_player": True})}
    m = STATIC_FREE.fullmatch(t)
    if m:
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "hand" if m["hand"] else "any", "once": False, "flash": False,
                "self": False, "free": True, "play": False, "cast": True, "filter": key, "effects": []}
    m = ONCE_FREE.fullmatch(t)  # -- refused look/cast-free (wave 3R5) -- a once-each-turn free cast from the hand
    if m:
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "hand", "once": True, "flash": False,
                "self": False, "free": True, "play": False, "cast": True, "filter": key, "effects": []}
    # -- end cast without paying (wave 3C) --
    t = re.sub(r"^(\w+) spells and (\w+) spells ", r"\1 or \2 spells ", t)  # "kithkin spells and soldier spells you cast"
    # -- cost changers (wave 20E) -- "Red creature spells and green creature spells cost {1} more" is "red or green creature spells"; a
    # leading "As long as ~ is tapped, creature spells you cast cost {2} less to cast" is the same sentence with its condition last
    t = re.sub(r"^(\w+) (\w+) spells and (\w+) \2 spells ", r"\1 or \3 \2 spells ", t, flags=re.I)
    t = re.sub(r"^as long as (?P<c>[^,]+), (?P<r>.+ costs? \{[^}]+\} (?:less|more) to cast)$", r"\g<r> as long as \g<c>", t, flags=re.I)
    if cost_changes.special(t):  # -- cost changers (wave 4I) -- a turn, the chosen type, a zone, "for each", X, colored
        return cost_changes.static_definition(t, lines)
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
    m = EQUIP_COST.fullmatch(t)
    if m:
        return {"kind": "static", "static": "ability_cost_modifier", "delta": int(m["n"]) * (-1 if m["dir"] == "less" else 1),
                "filter": other.key() if m["other"] and (other := selectors.parse("other Equipment")) else None, "who": "you", "floor": False,
                "equip": True, "effects": []}
    m = ABILITY_COST.fullmatch(t)
    if m:  # -- costs (wave 3$) -- the source permanent is matched at the cost, relative to the ability's controller
        key = None
        if m["sel"]:
            sel = selectors.parse(m["sel"])
            if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.controller == "opponent" \
                    or sel.extras or sel.attacking or sel.blocking:
                return None
            key = sel.key()
        return {"kind": "static", "static": "ability_cost_modifier", "delta": int(m["n"]) * (-1 if m["dir"] == "less" else 1),
                "filter": key, "who": "you" if m["yours"] or (m["sel"] and "you control" in m["sel"]) else "any",
                "floor": bool(m["floor"]), "effects": []}
    # -- conditional statics (wave 4B) -- "You may cast this card from your graveyard as long as you control a Zombie."
    # (Gravecrawler; 113.6f: functions from the graveyard; 611.3a: checked whenever the cast is offered or begun)
    m = RETRACE_GRANT.fullmatch(t)
    if m:
        key = spell_filter(m["sel"])
        if key is None:
            return None
        return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False, "flash": False, "self": False,
                "play": False, "cast": True, "filter": key, "extra": "discard a land card", "own": True,
                **({"during": "your_turn"} if m["during"] else {}), "effects": []}
    if (m := SELF_EXILE.fullmatch(t)) is not None:
        return {"kind": "static", "static": "permission", "zone": "exile", "zones": ["graveyard", "exile"] if "graveyard" in m["z"] else ["exile"],
                "once": False, "flash": False, "self": True, "play": False, "cast": True, "filter": None, "effects": []}
    m = SELF_GY_WHILE.fullmatch(t)
    if m:
        from app.rules import conditions

        cond = conditions.parse(m["cond"])
        if cond is None or "succeeded" in cond or "flag" in cond:
            return None
        return {"kind": "static", "static": "permission", "zone": "graveyard", "once": False, "flash": False, "self": True,
                "play": False, "cast": True, "filter": None, "while": cond, "effects": []}
    # -- top of library (wave 5I) -- "You may cast Dragon spells / artifact spells and colorless spells / creature spells of
    # the chosen type … from the top of your library", Radha's look-and-play line (app/rules/top_library.py)
    from app.rules import escape, top_library

    if (top := top_library.permission(t, lines)) is not None:
        return top
    if t.lower().startswith(("escape—", "each ", "you may cast ~ from your graveyard by", "you may cast this c")) and (found_escape := escape.define_static(t)) is not None:
        return found_escape  # (702.138a: a printed escape cost, or "Each nonland card in your graveyard has escape. …")
    # -- end top of library (wave 5I) --
    m = PERMISSION.fullmatch(t)
    if m:
        what = _permission_what(m["what"], m["sel"], m["qual"])
        if what is None:
            return None
        zone = "graveyard" if m["zone"] == "your graveyard" else "library_top"
        if (what.get("self") and zone != "graveyard") or (m["exile"] and (zone != "graveyard" or what.get("self"))):
            return None
        if zone == "library_top" and not any(_lower_first(x.strip().rstrip(".")) in (TOP_REVEAL, TOP_LOOK) for x in lines):
            # The engine offers a cast from the top of the library only when the player can see
            # that card (401.5; app/rules/view.hints): without a reveal / look line on the same
            # card the permission could never be used — refused rather than claimed
            return None
        return {"kind": "static", "static": "permission", "zone": zone, "once": bool(m["once"]), "flash": False,
                "self": bool(what.get("self")), "play": what["play"], "cast": what["cast"], "filter": what["filter"],
                "effects": [], **({"exile_gy": "is" if m["exile"] == "an instant or sorcery" else "all"} if m["exile"] else {})}
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
    m = FACE_DOWN_LOOK.fullmatch(t)  # -- hidden exile (wave 18A) -- Found Footage, Keeper of the Lens, Lens of Clarity
    if m:
        return {"kind": "static", "static": "top_reveal", "to": "owner" if m["top"] else "none", "face_down": True, "effects": []}
    # -- cast limits (wave 5E) -- "Your opponents can't cast spells during your turn.", "Any player may cast spells as though
    # they had flash.", "You may activate abilities of creatures you control as though those creatures had haste."
    from app.rules import cast_limits

    return cast_limits.static_definition(text)


# -- as long as (wave 9B) -- 611.2b: the permission lasts for as long as the card (the object an earlier instruction exiled,
# 400.7h) is still in exile; a card that leaves is a new object. "mana of any type can be spent" (118.14) and "you may spend
# mana as though it were mana of any color" (609.4b) are about the mana spent to cast the spell with this permission.
_RIDER = (r"(?:, and (?:mana of any type can be spent to cast (?P<t>that spell|it|them|those spells)|you may spend mana as though "
          r"it were mana of any (?P<k>color|type) to cast (?P<t2>that spell|it|them|those spells)))")
GRANT_EXILED = re.compile(
    r"^(?:for as long as (?P<d1>it|they|that card|those cards) remains? exiled, )?you may (?P<verb>play|cast) "
    r"(?P<what>that card|those cards|it|them)(?P<free> without paying (?:its|their) mana costs?)?"
    r"(?: for as long as (?P<d2>it|they|that card|those cards) remains? exiled)?" + _RIDER + r"?$")


def _grant_exiled(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    if bool(m["d1"]) == bool(m["d2"]):
        return None  # (exactly one duration)
    plural = m["what"] in ("those cards", "them")
    # the duration and the rider name the same card(s) the permission is for
    if (m["d1"] or m["d2"]) not in (("they", "those cards") if plural else ("it", "that card")):
        return None
    rider = m["t"] or m["t2"]
    if rider and rider not in (("them", "those spells") if plural else ("it", "that spell")):
        return None
    spend = "type" if m["t"] else (m["k"] if m["t2"] else "")
    if m["free"] and spend:
        return None  # (a free cast spends no mana: no card words it so)
    return [{"do": "grant_play", "who": "them:card" if plural else "it:card", "play": m["verb"] == "play", "cast": True,
             "until": "permanent", "optional": True, **({"free": True} if m["free"] else {}),
             **({"spend": spend} if spend else {})}], None


# -- hidden exile (wave 18A) -- cards exiled face down that "you may look at" (406.3a: a face-down exiled card has no characteristics,
# but the spell or ability that exiled it may let a player look at it and play it): the looker alone sees them (``revealed_to``,
# which ends when the card leaves exile, 400.7). Printed wordings, read as two plain sentences:
#   "You may look at and play those cards for as long as they remain exiled."   (look at + play)
#   "You may play it for as long as it remains exiled. Mana of any type can be spent to cast a spell this way."  (one permission)
LOOK_EXILED = re.compile(r"^you may look at (?P<what>it|that card|those cards|them) for as long as (?:it|they|that card|those cards) "
                         r"remains? exiled$")
_LOOK_AND_PLAY = re.compile(r"You may look at and (?P<v>play|cast) (?P<w>that card|those cards|it|them)(?P<free> without paying "
                            r"(?:its|their) mana costs?)? for as long as (?P<d>it|they) (?P<r>remains?) exiled")
_PLAY_RIDER = re.compile(r"(?P<g>You may (?:play|cast) (?P<w>that card|those cards|it|them)[^.]*?)\. (?:(?P<a>Mana of any type can be "
                         r"spent to cast (?:a spell|spells) this way)|(?P<b>If you cast a spell this way, you may spend mana as though it "
                         r"were mana of any type to cast it))\.")


def join_exile_play(body: str) -> str:
    """The wordings above as the sentences the permission grammar reads (permissions.GRANT_EXILED, LOOK_EXILED)."""
    # (Ugin, the Ineffable: "Exile the top card of your library face down and look at it." — 406.3: whoever looked may go on looking;
    # "put the exiled card into your hand" is the return of that card, 400.3)
    body = re.sub(r"([Ee]xile the top card of your library face down) and look at it\b", r"\1. You may look at it for as long as it remains exiled",
                  body)
    body = re.sub(r"\b([Pp])ut the exiled card into your hand\b", lambda m: ("R" if m[1] == "P" else "r") + "eturn the exiled card to your hand", body)
    body = re.sub(r"Look at (target player's hand), (the top card of that player's library), and any face-down creatures they control\.",
                  r"Look at \1. Look at \2. Look at all face-down creatures that player controls.", body)  # (Spy Network: 701.20e each)
    body = re.sub(r"Reveal (target face-down permanent)\. If it's a creature card, you may turn it face up\.",
                  r"Reveal \1 and you may turn it face up if it's a creature card.", body)  # (Hauntwoods Shrieker)
    body = re.sub(r"(cloak those cards)\. They enter tapped\.", r"\1 tapped.", body)  # (Become Anonymous)
    body = re.sub(r"\b([Ee]xile it) face down\. (It becomes foretold\.)", r"\1. \2", body)  # (The Foretold Soldier: the foretell zone is face down)
    body = re.sub(r"\bIt becomes foretold\. Its foretell cost is its mana cost reduced by (\{\d+\})\.",
                  r"It becomes foretold with a foretell cost of its mana cost reduced by \1.", body)  # (Ethereal Valkyrie: 702.143d)
    body = re.sub(r"(You may (?:look at and )?(?:play|cast) )the exiled (card|cards)\b",
                  lambda m: m[1] + ("that card" if m[2] == "card" else "those cards"), body)
    body = _LOOK_AND_PLAY.sub(lambda m: f"You may look at {m['w']} for as long as {m['d']} {m['r']} exiled. You may {m['v']} {m['w']}"
                              f"{m['free'] or ''} for as long as {m['d']} {m['r']} exiled", body)

    def rider(m: re.Match[str]) -> str:
        plural = m["w"] in ("those cards", "them")
        spell = "those spells" if plural else "that spell"
        tail = f"mana of any type can be spent to cast {spell}" if m["a"] else \
            f"you may spend mana as though it were mana of any type to cast {spell}"
        return f"{m['g']}, and {tail}."

    return _PLAY_RIDER.sub(rider, body)


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
    m = LOOK_EXILED.fullmatch(text)  # -- hidden exile (wave 18A) --
    if m:
        return [{"do": "look_exiled", "who": "them:card" if m["what"] in ("those cards", "them") else "it:card", "optional": True}], None
    m = FREE_COPY.fullmatch(text)  # -- cast a copy (wave 13C) --
    if m:
        many = m["w"] != "the copy"
        return [{"do": "free_cast", "zone": "that", "who": "them:copy" if many else "it:copy", "filter": None, "optional": True,
                 "mv": None, "n": 99 if many else 1, **({} if m["free"] else {"paid": True})}], None
    among = _free_among(text)  # -- refused look/cast-free (wave 3R5) --
    if among is not None:
        return among, None
    target = _free_target(text)
    if target is not None:
        return target
    conditional = _free_if(text) or _free_gy(text)
    if conditional is not None:
        return conditional, None
    m = FREE_HAND.fullmatch(text)  # -- cast without paying (wave 3C) --
    if m:
        if bool(m["h1"]) == bool(m["h2"]):
            return None
        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        try:  # -- refused look/cast-free (wave 3R5) -- "less than or equal to that damage / ~'s power …"
            mv = free_mv(m["n"], m["x2"])
        except ValueError:
            return None
        return [{"do": "free_cast", "zone": "hand", "filter": key, "optional": True, "mv": mv}], None
    # -- refused grants/replacements (wave 3R2) -- the same permission with its duration at the end ("You may play it
    # until the end of your next turn.": 611.2a, the duration is the one stated, wherever the sentence states it) and
    # "them" for "those cards" ("You may play them until the end of your next turn.")
    trailing = _TRAILING_UNTIL.fullmatch(text)
    if trailing:
        text = f"{trailing['until']}, {trailing['rest']}"
    text = re.sub(r"^((?:until [a-z ]+, )?you may (?:play|cast)) them\b", r"\1 those cards", text)
    # -- end refused grants/replacements (wave 3R2) --
    # -- as long as (wave 9B) -- "You may cast that card for as long as it remains exiled, and mana of any type can be spent
    # to cast that spell." (Gonti, Hostage Taker, Thief of Sanity)
    m = GRANT_EXILED.fullmatch(text)
    if m and (m["d1"] or m["d2"]):
        return _grant_exiled(m)
    m = GRANT_THAT.fullmatch(text)
    if m and m["free"] and not (m["until"] or m["this_turn"]):
        if m["verb"] != "cast" or m["what"] == "those cards":
            return None  # (several cards at once, or playing a land as this resolves: not modelled)
        return [{"do": "free_cast", "zone": "that", "who": "it:card", "filter": None, "mv": None, "optional": True}], None
    if m:
        if (m["until"] and m["this_turn"]) or not (m["until"] or m["this_turn"]):
            return None  # (a bare "you may cast that card": cast it as this resolves, not modelled)
        free = bool(m["free"])  # (wave 3C) "... without paying its mana cost" (118.9)
        until = {"until the end of your next turn": "end_of_next_turn", "until your next end step": "next_end_step"}.get(m["until"], "end_of_turn")
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
    spend: str = ""  # -- as long as (wave 9B) -- "" | "type" | "color": how mana may be spent casting with it (118.14, 609.4b)
    once_key: str | None = None  # a static "once during each of your turns" ability's key
    sorcery: bool = False  # -- keywords (wave 15E) -- plot 702.170d: only in your main phase with an empty stack, whatever it is
    extra: str = ""  # -- cost alt (wave 16F) -- an additional cost the permission names ("discard a card"), paid with the rest (601.2b)
    exile_gy: str = ""  # -- cast from graveyard (wave 19C) -- 614.1a: "all" | "is" (instants and sorceries only): "If a spell cast this way would be put into your graveyard, exile it instead"
    exile: bool = False  # -- casting extras (wave 18E) -- jump-start 702.133a: exile the card instead of putting it anywhere else as it leaves the stack


def _view(state: GameState, player: str, info: CardInfo) -> Plan:
    from app.rules.plan import Plan

    return Plan.view(state, player, info)


def spell_matches(state: GameState, player: str, card: CardInstance, ch: Characteristics, key: str, info: CardInfo,
                  source: str | None = None) -> bool:
    """Would the spell this card becomes match the selector ("creature spells", "red spells")? (``source``: the
    permanent whose "chosen type" the selector reads, wave 5I)"""
    probe = card.model_copy(update={"zone": STACK, "controller": player})
    return selectors.matches(_view(state, player, info), selectors.from_key(key), probe, ch, player, source)


def spell_uncounterable(state: GameState, info: CardInfo, card: CardInstance, ch: Characteristics) -> bool:
    """-- small wordings (wave 11E) -- does a static on the table say this spell, controlled by its caster, can't be
    countered (101.2, 701.6)?"""
    return any((d.get("any_player") or src.controller == card.controller) and (not d["filter"] or spell_matches(state, card.controller, card, ch, d["filter"], info))
               for src, _, d in _table_statics(state, info, {"spells_uncounterable"}))


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
        if p.player != player or not _wants(p, verb) or (p.once and p.used_turn == turn) or (p.after_turn and turn <= p.after_turn):
            continue
        if p.object_id is not None:
            if p.object_id != oid:
                continue  # a new object since (400.7): the permission was for the one it was
        elif p.zone != "any" and p.zone != where:
            continue
        if p.filter and verb == "cast" and not spell_matches(state, player, card, ch, p.filter, info):
            continue
        zone_ok = p.object_id is not None or p.zone != "any"  # (a flash-only permission grants no zone)
        out.append(Grant("permission", p.label, zone_ok=zone_ok, free=p.free, flash=p.flash, permission=p.id, spend=p.spend,
                         sorcery=p.sorcery))
    if verb == "cast" and where in ("graveyard", "exile") and card.owner == player and not card.face_down:
        for index, d in _definitions(ch).items():  # the card's own ability, functioning in the graveyard (113.6) / exile (wave 20D)
            if d.get("static") == "permission" and d.get("self") and where in d.get("zones", [d["zone"]]):
                key = f"{card.id}:permission:{index}"
                if d["once"] and r.once_per_turn.get(key) == turn:
                    continue
                if d.get("while") is not None and not _while_holds(state, info, player, card, d["while"]):
                    continue  # -- conditional statics (wave 4B) -- "as long as you control a Zombie"
                out.append(Grant("permission", f"{ch.name}: cast it from {'exile' if where == 'exile' else 'your graveyard'}", once_key=key if d["once"] else None,
                                 extra=d.get("extra") or "", exile=bool(d.get("exile"))))
    if verb == "cast" and where == "hand":  # -- cast without paying (wave 3C) -- the card's own "cast this spell without paying"
        for d in _definitions(ch).values():
            if d.get("static") == "permission" and d.get("self") and d.get("free") and d["zone"] == "hand" \
                    and (d.get("cond") != "commander" or _controls_commander(state, player)):
                out.append(Grant("permission", f"{ch.name}: cast it without paying its mana cost", free=True))
    if verb == "cast":  # -- cast limits (wave 5E) -- 601.3d: "You may cast this spell as though it had flash if …"
        from app.rules import cast_limits

        if (label := cast_limits.self_flash(state, player, card, ch, info)) is not None:
            out.append(Grant("permission", label, zone_ok=False, flash=True))
    for src, index, d in _table_statics(state, info, {"permission"}):
        # -- cast limits (wave 5E) -- "Any player may cast …" / "During each opponent's end step, you may cast …"
        if (src.controller != player and not d.get("any_player")) or d.get("self") or not d[verb]:
            continue
        if d.get("during"):
            from app.rules import cast_limits

            if not cast_limits.permission_during_ok(state, d, player):
                continue
        if d.get("own") and card.owner != player:  # ("Creature cards you own …")
            continue
        if d["zone"] != "any" and d["zone"] != where:
            continue
        if d["filter"] and verb == "cast" and not spell_matches(state, player, card, ch, d["filter"], info):
            continue
        # -- top of library (wave 5I) -- "artifact spells and colorless spells", the chosen type, historic lands
        from app.rules import top_library

        if not top_library.static_ok(state, player, card, ch, info, d, src, verb):
            continue
        key = f"{src.id}:permission:{index}"
        if d["once"] and (r.once_per_turn.get(key) == turn or (state.turn.active_player != player and not d.get("once_any"))):
            continue  # "once during each of your turns" ("once each turn": any turn, wave 5I)
        out.append(Grant("permission", src.name, zone_ok=d["zone"] != "any", flash=d["flash"], free=bool(d.get("free")),
                         once_key=key if d["once"] else None, extra=d.get("extra") or "", exile_gy=d.get("exile_gy", "")))
    # -- top of library (wave 5I) -- the player picks the permission they use (601.3): a once-each-turn one is offered
    # last, so a cast another permission also allows doesn't use it up
    out.sort(key=lambda g: g.once_key is not None)
    return out


def _while_holds(state: GameState, info: CardInfo, player: str, card: CardInstance, cond: dict[str, Any]) -> bool:
    """-- conditional statics (wave 4B) -- the condition of a card's own "as long as …" permission, read now
    (611.3a); "you" is the card's owner, who is casting it (108.4a)."""
    from app.rules import conditions
    from app.rules.layers import _view

    return conditions.holds(_view(state, info), {"controller": player, "source_card": card.id}, cond)


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


def modifiers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo,
              targets: tuple[str, ...] = ()) -> list[CostModifier]:
    """The cost modifiers that apply to ``player`` casting this spell: static abilities on the
    table ("Creature spells you cast cost {1} less to cast", "Spells your opponents cast cost {2}
    more to cast") and stored ones with a duration."""
    r = state.rules
    if r is None:
        return []
    found: list[CostModifier] = []
    for src, index, d in _table_statics(state, info, {"cost_modifier"}):
        # -- cost changers (wave 4I) -- per count, with a turn, of the chosen type, from a zone, colored (cost_changes.py)
        delta = cost_changes.static_delta(state, info, src, d, player, card, ch, targets)
        if delta is None:
            continue
        found.append(CostModifier(id=f"{src.id}:{index}", controller=src.controller, delta=delta, caster=d["caster"],
                                  filter=d["filter"], until="permanent", source=r.object_id(src.id), label=src.name,
                                  mana=cost_changes.stored_mana(d)))
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


_PER_TARGET = re.compile(r"^(?:this spell|~) costs (?P<cost>(?:\{[^}]+\})+) more to cast for each target beyond the first$")


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
        if d.get("static") != "self_cost" or "change" in d or "per_target" in d:  # (wave 4I: a "change" is cost_changes.own_changes')
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
               base: M.ManaCost, additional: tuple[M.ManaCost, ...] = (), tax: int = 0, affinity: int = 0,
               targets: tuple[str, ...] = ()) -> M.ManaCost:
    """601.2f: the mana cost or alternative cost (``base``), plus additional costs (kicker,
    buyback: 118.8) and cost increases (commander tax, "cost {N} more"), minus cost reductions
    (affinity, "cost {N} less", the spell's own). Reductions affect only the generic component
    (118.7a) and can't take it below {0}."""
    cost = base
    for extra in additional:
        cost = _add(cost, extra)
    increase = tax
    reduction = affinity
    changes = cost_changes.Changes()  # -- cost changers (wave 4I) -- colored increases / reductions (118.7b/c)
    if info is not None:
        for m in modifiers(state, player, card, ch, info, targets):  # (targets: wave 4I, "spells that target …")
            if m.mana:
                changes.add(m.delta, m.mana)
            elif m.delta > 0:
                increase += m.delta
            else:
                reduction -= m.delta
        reduction += self_reduction(state, player, card, ch, info)
        own = cost_changes.own_changes(state, player, card, ch, info, _definitions(ch))
        increase += own.increase
        reduction += own.reduction
        changes.colored_more += own.colored_more
        changes.colored_less += own.colored_less
        for d in _definitions(ch).values():  # -- static_other sweep (wave 16B) -- strive: for each target beyond the first
            if d.get("static") == "self_cost" and d.get("per_target"):
                more, each = max(0, len(targets) - 1), M.parse_cost(d["per_target"])
                increase += each.generic * more
                changes.colored_more += tuple(each.colored) * more
    cost = cost_changes.add_colored(cost.plus_generic(increase), changes.colored_more)
    cost = cost_changes.reduce_colored(cost, changes.colored_less)  # (colored first: what's left over reduces generic, 118.7c)
    return cost.plus_generic(-min(cost.generic, reduction))


# -- costs (wave 3$) -- cost modifiers for activated abilities (602.2b -> 601.2f, 118.7) ---------------------
def ability_mana(state: GameState, player: str, card: CardInstance, ch: Characteristics, mana: str, info: CardInfo,
                 own: int = 0, ability_text: str = "") -> str:
    """The mana part of an activated ability's cost after "Activated abilities of creatures you control cost {2} less to
    activate" and its increases: increases first, then reductions on the generic component only (118.7a, 601.2f), and with
    "can't reduce the mana in that cost to less than one mana" never below one mana. Costs with {X} are left alone."""
    mods = [(src, d) for src, _, d in _table_statics(state, info, {"ability_cost_modifier"})]
    if not mods and not own:  # (own: the ability's "This ability costs {1} less …", wave 4I)
        return mana
    cost = M.parse_cost(mana)
    if cost.x or cost.unsupported:
        return mana
    view = None
    increase, reduction = max(0, own), max(0, -own)
    floor = False
    from app.rules import attachments

    for src, d in mods:
        if d["who"] == "you" and src.controller != player:
            continue
        if d.get("equip") and not attachments.is_equip_text(ability_text):  # -- equip (wave 15E) --
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
    # -- cost changers (wave 4I) -- the floor ("can't reduce … to less than one mana") limits only its own effect; the
    # player orders reductions (601.2f), so the floored ones go first and the ability's own reduction after them
    own_cut = max(0, -own)
    cut = reduction - own_cut
    if floor:
        symbols = cost.generic + len(cost.colored) + len(cost.hybrid) + len(cost.phyrexian)
        cut = min(cut, max(0, symbols - 1))
    cut = min(cost.generic, cut + own_cut)
    out = cost.plus_generic(-cut)
    return mana if not mana and out.is_free else out.text()  # (wave 4I: "{T}: …" taxed {2} becomes "{2}, {T}: …")


# -- effects ---------------------------------------------------------------------------------------
def grant_play(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"You may play that card this turn" (the objects an earlier instruction of this ability
    moved — bound by scripts.resolve_it, found where they went: 400.7h/j) or "Until end of turn,
    you may play lands and cast spells from your graveyard"."""
    from app.rules import context

    pid = ctx["controller"]
    r = plan.rules
    turn = plan.state.turn.number
    if e["until"] == "next_end_step" and plan.active == pid and plan.state.turn.phase in ("end", "cleanup"):
        turn += 1  # (granted in its own end step or later: the next one is the following turn's)
    when = "until the end of their next turn" if e["until"] == "end_of_next_turn" else \
        "until their next end step" if e["until"] == "next_end_step" else \
        "for as long as it remains there" if e["until"] == "permanent" else "this turn"  # (permanent: wave 3E, 611.2a)
    verb = "play" if e["play"] else "cast"
    if e.get("who"):
        if not str(e["who"]).startswith(context.PREFIX):
            return True  # (an unbound pronoun never reaches here: resolve_it refuses the ability)
        for cid in context.objects(plan, ctx, e["who"][len(context.PREFIX):]):
            card = plan.state.cards[cid]
            r.permissions.append(Permission(id=secrets.token_hex(4), player=pid, play=e["play"], cast=e["cast"], zone="any",
                                            object_id=plan.oid(card), card=cid, until=e["until"], turn=turn, free=bool(e.get("free")), spend=e.get("spend", ""),
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


def expire_end_step(plan: Plan) -> None:
    """-- trigger tail (wave 15B) -- "until your next end step" (611.2a): the permission ends as that player's end step begins
    (``turn`` is the first turn whose end step may end it: grant_play), before anything is played in it."""
    turn = plan.state.turn.number
    plan.rules.permissions = [p for p in plan.rules.permissions
                              if not (p.until == "next_end_step" and p.player == plan.active and turn >= p.turn)]


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
                found.append(TopReveal(source=card.id, player=card.controller, to=d["to"], face_down=bool(d.get("face_down"))))
            elif d.get("kind") == "static" and d.get("static") == "permission" and d.get("look"):  # (wave 5I: Radha)
                found.append(TopReveal(source=card.id, player=card.controller, to="owner"))
    if found != r.top_reveals:
        r.top_reveals = found


# -- cast without paying (wave 3C) --
def free_cast(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"You may cast a spell with mana value N or less from your hand without paying its mana cost" /
    "you may cast that card without paying its mana cost": as this resolves (608.2g) its controller
    picks one eligible card (or none); the engine then lets them cast it for {0} (118.9: X is 0,
    107.3b; kicker and other additional costs may still be paid, 118.9d). Nothing is kept: a card
    not cast now can't be cast this way later.

    -- refused look/cast-free (wave 3R5) -- The cast happens during the resolution (608.2g: the spell
    becomes the topmost object and the resolving spell or ability continues), so instructions after it
    follow the cast ("Put the rest on the bottom of your library"). ``zone``: "hand", "that" (the
    cards a binding names), "looked" (the cards looked at, still in the library), "found" (the card a
    "… until you exile / reveal a …" stopped at), "target" (the ability's target card); ``n``: how
    many spells may be cast this way (one at a time, each cast before the next is chosen: 608.2g
    "which may include casting other spells this way"); the cards cast are ctx["free_cast_done"]."""
    from app.game.rules_state import DecisionOption
    from app.rules import characteristics as chars
    from app.rules import values
    from app.rules.effects import decide

    pid = ctx["controller"]
    done = ctx.setdefault("free_cast_done", [])
    if sum(1 for c in done if c not in (ctx.get("free_cast_before") or [])) >= int(e.get("n", 1)):
        return _free_cast_over(ctx, e)
    pool = _free_pool(plan, ctx, e)
    if e.get("paid") and any(M.parse_cost(chars.of(plan.state.cards[c], plan.info).mana_cost).x for c in pool):
        from app.rules import (
            copying,  # -- cast a copy (wave 18F) -- X is announced as a spell is cast (601.2b): not automated for a paid cast of a copy
        )

        job = copying.new_job(ctx, controller=pid, objects=[], retarget=False, label=ctx.get("name") or "Copy")
        copying.plan_decide(plan, player=pid, kind="manual_resolution", options=[DecisionOption(id="done", label="Done")],
                            prompt="Casting a copy of an X spell isn't automated (601.2b): cast it by hand if you want to, then press Done",
                            resume={"step": "copy_manual", "job": job})
        return False
    limit = None
    if e.get("mv") is not None:
        limit = values.evaluate(plan, ctx, {"x": 1} if e["mv"] == "x" else e["mv"])
    below = values.evaluate(plan, ctx, e["mv_lt"]) if e.get("mv_lt") is not None else None  # (wave 3R5: "lesser")
    options = []
    for cid in pool:
        card = plan.state.cards[cid]
        ch = chars.of(card, plan.info)
        if not ch.types or ch.is_land or plan.rules.card_mode(cid) == "manual" or cid in done:
            continue
        if limit is not None and ch.mana_value > limit:
            continue
        if e.get("paid") and not ch.mana_cost:
            continue  # (review 18F) 118.6: no mana cost is an unpayable cost (Living End's copy can't be cast by paying it)
        if below is not None and ch.mana_value >= below:
            continue
        if e.get("parity") and ch.mana_value % 2 != (1 if e["parity"] == "odd" else 0):
            continue
        if e.get("filter") and not spell_matches(plan.state, pid, card, ch, e["filter"], plan.info):
            continue
        # -- cast limits (wave 5E) -- a cast no rule or effect prohibits (601.3)
        from app.rules import cast_limits

        if cast_limits.free_cast_blocked(plan, pid, cid) is not None:
            continue
        options.append(DecisionOption(id=cid, label=card.name or "Card", card_id=cid))
    # (cards in a hand or a library are hidden: whether a choice appears mustn't tell the other
    # players whether one was eligible, so the looker is asked whenever there were cards to look at)
    hidden = e["zone"] in ("hand", "looked") and bool(pool)
    if not options and not hidden:
        plan.note(f"{plan.name(pid)} has nothing to cast" + ("" if e.get("paid") else " without paying its mana cost"))
        return _free_cast_over(ctx, e)
    many = int(e.get("n", 1)) > 1
    decide(plan, player=pid, kind="choose_cards",
           prompt="Choose a spell to cast" + ("" if e.get("paid") else " without paying its mana cost") + (" (one at a time)" if many else "")
                  + " (or none)",
           options=options, min_choices=0, max_choices=1, resume={"step": "free_cast_pick", "ctx": ctx, "e": e})
    return False


def _free_cast_over(ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """This free cast is over: "If you don't cast it, …" reads whether it cast anything (``did``)."""
    from app.rules import context

    done, before = ctx.get("free_cast_done") or [], ctx.get("free_cast_before") or []
    if e.get("did"):
        context.refs(ctx)[e["did"]] = {"kind": "payment", "ok": len(done) > len(before)}
    ctx["free_cast_before"] = list(done)  # (a later free cast of the same ability counts afresh)
    return True


def found_to(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- refused look/cast-free (wave 3R5) -- "If you don't cast it, put it into your hand": the card a
    "… until you exile / reveal a …" stopped at, or the one card revealed, if it is still there."""
    pid = ctx["controller"]
    owner = ctx.get("looked_owner") or pid
    found = ctx.get("found")
    looked = [c for c in ctx.get("looked") or [] if c in plan.state.zones.get(zone_key(owner, "library"), [])]
    cid = found if found else (looked[0] if len(looked) == 1 else None)
    card = plan.state.cards.get(cid or "")
    if card is None or not card.zone.endswith((":exile", ":library")):
        return True
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": pid, "zone": e["to"]}}, actor=pid)
    return True


def _free_pool(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> list[str]:
    """The cards a free cast may choose from (their current objects only, 400.7)."""
    from app.rules import context

    pid = ctx["controller"]
    zone = e["zone"]
    if zone == "hand":
        return list(plan.state.zones.get(zone_key(pid, "hand"), []))
    if zone == "looked":  # still in the library they were looked at in
        owner = ctx.get("looked_owner") or pid
        library = plan.state.zones.get(zone_key(owner, "library"), [])
        return [c for c in ctx.get("looked") or [] if c in library]
    if zone == "found":
        found = ctx.get("found")
        card = plan.state.cards.get(found or "")
        return [found] if found is not None and card is not None and card.zone.endswith((":exile", ":library")) else []
    if zone == "target":
        return [t["id"] for t in ctx.get("targets") or [] if t.get("id") in plan.state.cards
                and plan.state.cards[t["id"]].zone.endswith(":graveyard")]
    if zone == "graveyard":  # your graveyard, or every graveyard (public zones)
        whose = [pid] if e.get("whose") == "you" else plan.live()
        return [c for p in whose for c in plan.state.zones.get(zone_key(p, "graveyard"), [])]
    who = str(e.get("who") or "")
    return context.objects(plan, ctx, who[len(context.PREFIX):]) if who.startswith(context.PREFIX) else []


def resume_free_cast(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The spell chosen is cast now, while the ability is still resolving (608.2g); the resolution
    goes on once that cast is done (``free_cast_done``, from casting.cast_free) or abandoned
    (cancelled while paying: ``free_cast_abandoned``, from engine.settle)."""
    from app.game import actions as A
    from app.rules import effects
    from app.rules.casting import cast_spell

    ctx = d.resume["ctx"]
    e = d.resume.get("e") or {"n": 1}
    if not chosen:
        _free_cast_over(ctx, e)
        effects.continue_effects(plan, ctx)
        return
    r = plan.rules
    r.free_casts.append(chosen[0])
    r.free_cast_then = {"card": chosen[0], "ctx": ctx, "e": e}
    prev = plan.actor
    plan.actor = d.player
    try:
        cast_spell(plan, A.CastSpell(card_id=chosen[0], free=True))
    finally:
        plan.actor = prev


def free_cast_done(plan: Plan, card_id: str, *, cast: bool) -> None:
    """A free cast made during a resolution is over (cast, or abandoned): carry on resolving."""
    from app.rules import effects

    r = plan.rules
    pending = r.free_cast_then
    if pending is None or pending["card"] != card_id:
        return
    r.free_cast_then = None
    ctx, e = pending["ctx"], pending["e"]
    if not cast:
        r.free_casts = [c for c in r.free_casts if c != card_id]
        _free_cast_over(ctx, e)
        effects.continue_effects(plan, ctx)
        return
    ctx.setdefault("free_cast_done", []).append(card_id)
    if e.get("exile_gy") and (e["exile_gy"] is True or plan.ch(plan.state.cards[card_id]).is_instant_or_sorcery):
        r.exile_if_graveyard.append(plan.oid(card_id))  # "If that spell would be put into your graveyard, exile it instead" (614.1a; wave 19C: "an instant or sorcery spell" only)
    if int(e.get("n", 1)) > 1 and not free_cast(plan, ctx, e):
        return  # the next one is being chosen
    _free_cast_over(ctx, e)
    effects.continue_effects(plan, ctx)


def free_cast_abandoned(plan: Plan) -> None:
    """After an intent (engine.settle): a free cast begun during a resolution that no longer waits
    for any choice and never reached the stack was cancelled (a payment cancelled: 601.2h, nothing
    was paid); the resolution goes on without it."""
    pending = plan.rules.free_cast_then
    if pending is None or plan.rules.decision is not None:
        return
    card = plan.state.cards.get(pending["card"])
    if card is not None and card.zone == STACK:
        free_cast_done(plan, pending["card"], cast=True)  # (defensive: it did reach the stack)
        return
    plan.note(f"{plan.name(pending['ctx']['controller'])} doesn't cast it")
    free_cast_done(plan, pending["card"], cast=False)


def rest_exiled(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- refused look/cast-free (wave 3R5) -- "Put the rest / the exiled cards not cast this way on
    the bottom of your library in a random order" / "… into your graveyard / hand": the cards an
    earlier instruction exiled that are still those objects in exile (400.7: the ones cast are on
    the stack now). A library is the card's owner's; "a random order" is the table's randomness,
    recorded as moves (replay is deterministic)."""
    from app.rules import context

    pid = ctx["controller"]
    who = str(e["who"])
    cards = [c for c in context.objects(plan, ctx, who[len(context.PREFIX):]) if plan.state.cards[c].zone.endswith(":exile")]
    if not cards:
        return True
    if e["to"] == "bottom_random":
        order = list(cards)
        (plan.rng or secrets.SystemRandom()).shuffle(order)
        for cid in order:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"},
                     "position": "bottom"}, actor=pid)
        return True
    for cid in cards:
        to = pid if e["to"] == "hand" else plan.state.cards[cid].owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": to, "zone": e["to"]}}, actor=pid)
    return True
# -- end cast without paying (wave 3C) --
