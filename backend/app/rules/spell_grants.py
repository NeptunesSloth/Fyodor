"""-- spell grants (wave 28C) -- abilities granted to spells. Researched against the Comprehensive Rules of 2026-09-25.

Two kinds of grant:

* A static ability of a permanent: "Instant and sorcery spells you control have lifelink." (Radiant Scrollwielder, Soulfire Grand Master,
  Heartflame Duelist, Firesong and Sunspeaker: red only), "Instant and sorcery spells you control have deathtouch." (Pestilent Spirit),
  "Instant and sorcery spells you control have split second." (Samut, Tyrant of Naktamun), "Noble creatures you control and Lesson spells
  you control have lifelink." (Lo and Li: the creatures part is an ordinary grant, the spells part is read here).
* An effect with a duration: "The next spell you cast this turn has improvise." (Archway of Innovation), "… has convoke." (Wand of the
  Worldsoul, Flockchaser Phantom), "… has affinity for artifacts." (Saheeli, the Gifted; "the next noncreature spell" Don & Raph),
  "The next noncreature spell you cast this turn has cascade." (Dark Apostle) and the same for storm: ``NextSpellGrant``.

Rules:

* 113.6, 604.1, 611.3a: a static ability that grants an ability to spells applies on the stack: the spell has the ability for as long
  as it is a spell on the stack and the static applies (layer 6, 613.1f), read afresh each time the spell is looked at. It is a spell
  the static's controller controls (a copy of a spell is a spell too, 707.10: "spells you control" includes copies; a copy isn't *cast*,
  so "spells you cast" grants don't reach it - they are read at the cast, cast_limits).
* 702.15b / 120.3f lifelink and 702.2b deathtouch: damage dealt by a source with the ability; a spell is the source of the damage it
  deals as it resolves (608.2h: the spell's characteristics as it was on the stack), so the damage gains its controller that much life
  (the gain is a separate event, 120.4b) and destroys a creature it damages (704.5h). Both work on any damage a source deals, not just
  combat damage (702.2c, 702.15a are about damage dealt by the source).
* 702.61a: split second is a static ability that functions only while the spell is on the stack, so it works for a granted one too
  (``split_second.on_stack`` reads the spell's characteristics with the grants).
* 601.2f-h, 702.51a, 702.126a, 702.41a: convoke, improvise and affinity matter while the spell is being cast: the "next spell" grant is
  there from the moment the player starts to cast it (601.2a: the spell is on the stack) until it has been cast, when the grant is
  used up (``consume``); it ends in cleanup (514.2). A grant naming a kind of spell ("the next noncreature spell") waits for one.
  702.85a / 702.40a: a cascade or storm the spell is given is an ability it has as it is cast, so it triggers (the engine's cast
  triggers read the grants as they do statics).

Everything it adds is a keyword ability added after the printed ones (indexes from 100, as every granted ability, 613.1f).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import NextSpellGrant
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.plan import Plan

KEYWORDS = ("lifelink", "deathtouch", "split second")
NEXT_KEYWORDS = ("convoke", "improvise", "cascade", "storm")

_SPELLS = re.compile(r"^(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells you control (?:has|have) (?P<kw>" + "|".join(KEYWORDS) + r")$", re.IGNORECASE)
_BOTH = re.compile(r"^(?P<bf>[A-Za-z][A-Za-z' ,-]*? you control) and (?P<sel>[A-Za-z][A-Za-z' ,-]*?) spells you control (?:has|have) (?P<kw>"
                   + "|".join(KEYWORDS) + r")$", re.IGNORECASE)
_NEXT = re.compile(r"^the next (?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spell you cast this turn (?:has|have) "
                   r"(?P<kw>convoke|improvise|cascade|storm|affinity for artifacts)$", re.IGNORECASE)
_NEXT_TWO = re.compile(r"^the next (?P<a>instant|sorcery|creature|noncreature) spell and the next (?P<b>instant|sorcery|creature|noncreature) spell "
                       r"you cast this turn each have (?P<kw>cascade|storm)$", re.IGNORECASE)


def _filter(phrase: str | None) -> tuple[bool, str | None]:
    """(understood, the spell selector key) for "<phrase> spells" (None: any spell)."""
    from app.rules import selectors

    if not phrase:
        return True, None
    sel = selectors.parse(re.sub(r"\band\b", "or", phrase.strip()) + " spell")
    if sel is None or sel.player is not None or sel.zones != ("stack",) or sel.card:
        return False, None
    return True, sel.key()


# -- static grants -------------------------------------------------------------------------------------------------------------
def static_definition(text: str) -> dict[str, Any] | None:
    """The static of a grant line to spells ("Instant and sorcery spells you control have lifelink."), or None."""
    t = text.strip().rstrip(".")
    both = _BOTH.fullmatch(t)
    m = _SPELLS.fullmatch(t) if both is None else None
    if m is None and both is None:
        return None
    mm = both or m
    ok, key = _filter(mm["sel"])
    if not ok:
        return None
    grant = {"keyword": mm["kw"].lower(), "filter": key}
    if both is None:
        return {"kind": "static", "static": "spell_grant", "spell_grants": [grant], "effects": []}
    from app.rules import scripts

    creatures = scripts.parse_anthem(f"{both['bf']} have {both['kw']}.")  # (the battlefield part: an ordinary grant)
    if creatures is None or creatures.get("static") != "grant":
        return None
    return {**creatures, "spell_grants": [grant]}


def _sources(state: GameState, info: CardInfo) -> list[tuple[CardInstance, dict[str, Any]]]:
    """(permanent, grant) for every spell grant of a permanent on the battlefield, confirmed with its current abilities (613.1f)."""
    from app.rules import cast_limits
    from app.rules import characteristics as chars
    from app.rules import scripts
    from app.rules.layers import derive

    out: list[tuple[CardInstance, dict[str, Any]]] = []
    for cid, index, _d in cast_limits._scan(state, info):
        if not _d.get("spell_grants"):
            continue
        card = state.cards[cid]
        now = scripts.definitions(derive(state, card, chars.of(card, info), info)).get(index, {})
        out += [(card, g) for g in now.get("spell_grants") or ()]
    return out


def apply(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo) -> Characteristics:
    """The characteristics of a spell on the stack with the keywords the statics on the table give it."""
    from app.rules import selectors
    from app.rules.plan import Plan
    from app.rules.scripts import parse_abilities

    found = _sources(state, info)
    if not found:
        return ch
    extra: list[Any] = []
    view = None
    for src, g in found:
        if src.controller != card.controller or g["keyword"] in ch.keywords:
            continue
        view = view or Plan.view(state, src.controller, info)
        if g["filter"] is not None and not selectors.matches(view, selectors.from_key(g["filter"]), card, ch, src.controller, src.id):
            continue
        parsed = parse_abilities(g["keyword"].capitalize())
        if len(parsed) == 1 and parsed[0].kind == "keywords" and not any(g["keyword"] in x.keywords for x in extra):
            extra.append(replace(parsed[0], index=max([a.index for a in ch.abilities], default=99) + 1 + len(extra)))
    return replace(ch, abilities=ch.abilities + tuple(extra)) if extra else ch


# -- "the next spell you cast this turn has …" ---------------------------------------------------------------------------------
def clause(text: str) -> tuple[list[dict[str, Any]], None] | None:
    """The instruction of "The next [noncreature] spell you cast this turn has convoke.", or None."""
    t = text.strip().rstrip(".")
    two = _NEXT_TWO.fullmatch(t)
    if two is not None:
        grants = [{"keyword": two["kw"].lower(), "what": "", "filter": _filter(two[x])[1]} for x in ("a", "b")]
        return [{"do": "next_spell_grant", "grants": grants}], None
    m = _NEXT.fullmatch(t)
    if m is None:
        return None
    ok, key = _filter(m["sel"])
    if not ok:
        return None
    kw = m["kw"].lower()
    return [{"do": "next_spell_grant", "grants": [{"keyword": kw.split()[0], "what": "artifacts" if kw.startswith("affinity") else "",
                                                   "filter": key}]}], None


def next_spell_grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import NextSpellGrant

    player = ctx["controller"]
    for g in e["grants"]:
        plan.rules.next_spell_grants.append(NextSpellGrant(
            id=secrets.token_hex(4), player=player, keyword=g["keyword"], what=g.get("what") or "", filter=g.get("filter"),
            turn=plan.state.turn.number, source=ctx.get("source_object"), label=(ctx.get("name") or "An effect")[:120]))
    words = " and ".join(f"the next {'spell' if g.get('filter') is None else 'matching spell'} has {g['keyword']}" for g in e["grants"])
    plan.note(f"{plan.name(player)}: {words} this turn ({ctx.get('name') or 'an effect'})")
    return True


PRIMITIVES = {"next_spell_grant": next_spell_grant}


def pending(state: GameState, player: str, card: CardInstance, spell: Characteristics, info: CardInfo | None,
            keyword: str) -> list[NextSpellGrant]:
    """The "next spell" grants of ``keyword`` the spell ``player`` is casting now gets (it matches their selector)."""
    r = state.rules
    if r is None or not r.next_spell_grants or info is None:
        return []
    from app.rules.permissions import spell_matches

    return [g for g in r.next_spell_grants if g.player == player and g.keyword == keyword and g.turn == state.turn.number
            and (g.filter is None or spell_matches(state, player, card, spell, g.filter, info))]


def consume(plan: Plan, card: Any, ch: Characteristics) -> None:
    """The spell ``card`` was cast (601.2i): every "next spell" grant of its caster that it matched is used up."""
    r = plan.rules
    if not r.next_spell_grants:
        return
    from app.rules.permissions import spell_matches

    player, turn = card.controller, plan.state.turn.number
    r.next_spell_grants = [g for g in r.next_spell_grants if g.turn == turn and not (
        g.player == player and (g.filter is None or spell_matches(plan.state, player, card, ch, g.filter, plan.info)))]


def expire(plan: Plan) -> None:
    """514.2: "this turn" ends in cleanup."""
    plan.rules.next_spell_grants = []
