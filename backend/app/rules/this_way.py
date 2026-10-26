"""-- "this way" outcomes (wave 4A) -- counts of what an earlier instruction of the same spell or
ability actually did: "You gain 1 life for each creature destroyed this way" (Fumigate), "Draw a
card for each card discarded this way" (Syphon Mind), "For each creature card milled this way,
create …" (Tribune of Rot), "equal to the number of creatures you controlled that were destroyed
this way" (Kaya's Wrath), "for each permanent put into a graveyard this way" (Terastodon).

The grammar (``parse``) turns the phrase into a placeholder ``{"this_way": <kind>, "of": <selector
key> | None}``; ``scripts.resolve_it`` binds it to the instruction it names (the latest one of this
ability with that verb: its recorded binding, app/rules/context.py) as ``{"ref_count": <binding>,
"this_way": <kind>, "of": …}``; :func:`count` evaluates it when the instruction that uses it is
carried out (608.2h: the number is determined once, then).

What counts (CR 2026-09-25):

* "destroyed" / "sacrificed" / "returned" / "discarded" / "milled": the objects the instruction
  actually moved — the old object no longer exists where it was (400.7). A permanent that was
  indestructible or regenerated wasn't destroyed (701.8b, 701.19a: the destruction was replaced, so it
  never happened, 614.6); a creature destroyed and then put somewhere other than the graveyard by a
  replacement effect was still destroyed (701.8a moves it; the replacement only changes where it
  goes — the Oracle wording "put into a graveyard this way" exists to say the other thing).
* "exiled": the objects that are in exile after the instruction (the new objects, 400.7j).
* "created" (wave 30G): the tokens an instruction made, of the name it asked for (``named``: a Chatterfang's extra Squirrels aren't "this way",
  the Ajani, Nacatl Avenger ruling) — "Create a token. When you do, …" (603.12: the reflexive ability triggers once for each).
* "put into a/your/their graveyard" / "that died": the objects whose new object is in a graveyard
  ("your": the controller's) as the instruction finished (700.4: "dies" is battlefield → graveyard).
* The qualifier is read from the object as it last existed where it was for a permanent ("nontoken
  creature destroyed this way", "creatures you controlled": 608.2h, its last known information) and
  from the card where it went for a card ("creature card milled this way": 701.17c, 400.7j).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

# The verbs, each with the recording effects' verbs (scripts._RECORDING) that it may name.
_VERBS = {"destroyed": ("destroyed",), "exiled": ("exiled", "blinked"), "sacrificed": ("sacrificed",),  # (blinked, wave 46C: "Exile target creature you control, then return that card to the battlefield. If a Pirate was exiled this way, …", Siren's Ruse)
          "discarded": ("discarded",), "milled": ("milled",), "returned": ("returned", "blinked"), "your_hand": ("returned", "put_hand", "blinked"),
          "graveyard": ("destroyed", "sacrificed", "milled", "discarded", "put_graveyard"), "your_graveyard": ("destroyed", "sacrificed", "milled", "discarded", "put_graveyard"),  # (wave 52A: "Destroy all creatures. … a creature card put into your graveyard this way" - only those that went to your graveyard, _matched)
          "died": ("destroyed", "sacrificed"), "tapped": ("tapped",), "goaded": ("goaded",),  # (goaded: wave 50J)
          "drawn": ("drawn",),  # -- if you do (wave 52A) -- "each card drawn this way" (effects.draw marks what was drawn before; ``drawn`` reads the difference)
          "revealed": ("revealed",), "shuffled": ("shuffled",),  # (wave 10C: reveal_hand.py)
          "battlefield_put": ("put_battlefield",),  # -- most-played cards II (wave 45A) -- "If you put a Cave onto the battlefield this way" (put_from_hand)
          "created": ("created",)}  # -- reflexive this way (wave 30G) -- 603.12: "create a token. When you do, …" (the tokens it made)
_PHRASE = re.compile(
    r"^(?P<what>.+?) (?:(?P<ctl>you controlled|they controlled) )?(?:that (?:was|were) |who )?"
    r"(?P<verb>destroyed|exiled|sacrificed|discarded|milled|drawn|tapped|goaded|revealed|returned to (?:your|its owner's|their owner's|their owners') hands?|you put into your hand|you put onto the battlefield"
    r"|put into (?P<gy>a|your|their|its owner's|that player's|their owners') graveyards?|died|that died|returned) this way$")  # (wave 52A: a bare "returned", Arid Archway: to a hand)
_NOUN_ONLY = re.compile(r"^(?:cards?)$")
_GREATEST = re.compile(r"^the greatest number of cards a player (?P<verb>discarded|milled) this way$")
_TOTAL = re.compile(r"^the total (?P<stat>power|toughness) of the (?P<verb>sacrificed|tapped) (?P<what>.+)$")
_TOTAL_GOADED = re.compile(r"^the total (?P<stat>power|toughness) of (?P<what>.+?) goaded this way$")  # -- goad (wave 50J) -- Havoc Eater
_TOTAL_SACRIFICED = re.compile(r"^the total (?P<stat>power|toughness) of the (?P<what>creatures) sacrificed this way$")  # -- if you do (wave 100B) -- Reign of the Pit: each as it last existed (608.2h)
# -- this way (wave 110C) -- "the greatest power among creature cards exiled this way" (Szat's Will): the best of the cards the exile moved, as each last existed (608.2h)
_GREATEST_EXILED = re.compile(r"^the greatest (?P<stat>power|toughness) among (?P<what>.+?) exiled this way$")


def parse(phrase: str) -> dict[str, Any] | None:
    """"creature destroyed this way" / "nonland card discarded this way" / "creature card put into a
    graveyard this way" / "creatures you controlled that were destroyed this way" → the placeholder,
    or None (not this grammar, or a form that isn't read: a player-relative "they controlled")."""
    p = phrase.strip()
    if (total := _TOTAL.match(p)) is not None and (sel := selectors.parse(total["what"])) is not None and sel.player is None:  # -- any number as an additional cost (wave 48B) -- Corpse Cobble
        return {"this_way": total["verb"], "of": sel.key(), "stat": total["stat"]}  # ("the total power of the sacrificed creatures": as each last existed, 608.2h)
    if (tg := _TOTAL_GOADED.match(p)) is not None and (sel := selectors.parse(tg["what"])) is not None and sel.player is None:
        return {"this_way": "goaded", "of": sel.key(), "stat": tg["stat"]}
    if (ts := _TOTAL_SACRIFICED.match(p)) is not None and (sel := selectors.parse(ts["what"])) is not None and sel.player is None:
        return {"this_way": "sacrificed", "of": sel.key(), "stat": ts["stat"]}
    if (ge := _GREATEST_EXILED.match(p)) is not None and (sel := selectors.parse(ge["what"])) is not None and sel.player is None:
        return {"this_way": "exiled", "of": sel.key(), "stat": ge["stat"], "agg": "max"}
    most = _GREATEST.match(p)
    if most is not None:  # Windfall: "the greatest number of cards a player discarded this way" (each player's own)
        return {"this_way": most["verb"], "of": None, "max_by": "owner"}
    p = re.sub(r"^the number of ", "", p)
    if (dv := re.fullmatch(r"(?P<what>.+?) (?:it|~) devoured", p)) is not None and not re.fullmatch(r"creatures?", dv["what"]) \
            and (sel := selectors.parse(dv["what"])) is not None and sel.player is None:  # -- keyword mechanics (wave 48B) -- 702.82b: "twice the number of Goblins it devoured" (Voracious
        return {"this_way": "sacrificed", "of": sel.key(), "ref_count": DEVOURED}  # Dragon): the permanents its devour sacrificed as it entered, as they last existed (608.2h)
    if (types :=re.fullmatch(r"card types? among (cards? .+ this way)", p)) is not None:  # -- if you do (wave 44A) -- "a card for each card type among cards discarded this way" (Kefka)
        inner = parse(types[1])
        return {**inner, "distinct": "types"} if inner is not None and inner.get("of") is None else None
    if re.fullmatch(r"opponents? who drew (?:a|one or more) cards? this way", p):  # -- if you do (wave 52A) -- "a card for each opponent who drew a card this way" (Cut a Deal)
        return {"this_way": "drawn", "of": None, "players": "opponent"}
    m = _PHRASE.match(p)
    if m is None:
        return None
    if m["ctl"] == "they controlled":  # (Deadly Tempest: each player's own count; not read)
        return None
    what = m["what"].strip()
    what = re.sub(r" that$", "", what)  # ("creature that died this way")
    verb = m["verb"]
    if verb == "you put onto the battlefield":
        kind = "battlefield_put"
    elif verb.startswith("returned") or verb.startswith("you put"):
        kind = "your_hand" if verb.startswith(("returned to your", "you put")) else "returned"
    elif verb.startswith("put into"):
        kind = "your_graveyard" if m["gy"] == "your" else "graveyard"
    elif verb in ("died", "that died"):
        kind = "died"
    else:
        kind = verb
    if kind == "revealed" and (not (_NOUN_ONLY.match(m["what"].strip()) or re.search(r"\bcards?\b", m["what"])) or m["ctl"]):  # -- chosen filters (wave 53B) -- "card of the chosen type revealed this way"
        return None  # (-- if you do (wave 10C) -- only "cards revealed this way": a revealed card isn't a permanent or a moved object)
    of: str | None = None
    if not _NOUN_ONLY.match(what):
        if m["ctl"] == "you controlled":
            what = f"{what} you control"
        sel = selectors.parse(what)
        if sel is None or sel.player is not None or sel.zones not in ((), ("battlefield",)):
            return None
        if sel.other and (sel.card or kind not in ("returned", "your_hand", "exiled", "destroyed", "sacrificed", "died")):
            return None  # -- if you do (wave 52A) -- "another" is than the source (a permanent as it last existed): not read for a card in a hidden or other zone
        if kind == "revealed" and not sel.card:
            return None
        of = sel.key()
    elif m["ctl"]:
        return None
    return {"this_way": kind, "of": of, **({"public": True} if kind == "revealed" and of else {})}  # (wave 53B: the cards shown to everyone, 701.20a: their kind is known)


# -- resolution memory (wave 22D) -- the OBJECTS an earlier instruction moved: "Return each card put into a graveyard this way to the
# battlefield under your control" (Sorin), "Put all creature cards milled this way onto the battlefield" (Cyber-Controller),
# "returns all cards they exiled this way" — the new objects it made where they went (400.7j), only while each is still that object
# there (400.7). The qualifier is read from the card where it is (a card in a graveyard or exile has its printed characteristics);
# a controller / owner qualifier ("you controlled") is a last-known-information question and stays unread.
_OBJECT_ZONE = {"exiled": "exile", "destroyed": "graveyard", "sacrificed": "graveyard", "milled": "graveyard", "discarded": "graveyard",
                "graveyard": "graveyard", "your_graveyard": "graveyard", "died": "graveyard"}
_DET = re.compile(r"^(?:each|all|every) (?P<rest>.+)$")
_ONE = re.compile(r"^(?:an?|one) (?P<rest>.+)$")


def choice_who(phrase: str) -> str | None:
    """"a creature card put into a graveyard this way" (Necromantic Selection): ONE of those objects, chosen as it resolves (608.2d);
    the ``who`` is the same as ``objects_who``'s (the pool the choice is from)."""
    m = _ONE.match(phrase.strip())
    return objects_who(f"each {m['rest']}") if m else None


def objects_who(phrase: str) -> str | None:
    """"each creature card put into a graveyard this way" → the ``who`` "them:<kind>|<selector key>" (resolve_it binds it to the
    instruction that did <kind>, scripts.resolve_it), or None (not this wording / a form not read)."""
    m = _DET.match(phrase.strip())
    found = parse(m["rest"]) if m else None
    if found is None or found.get("max_by") or found["this_way"] not in _OBJECT_ZONE:
        return None
    sel = selectors.from_key(found["of"]) if found.get("of") else selectors.Selector()
    if sel.player is not None or sel.controller is not None or sel.owner is not None or sel.zone_owner is not None:
        return None
    sel = selectors.replace(sel, zones=(_OBJECT_ZONE[found["this_way"]],), card=True)
    if found["this_way"] == "your_graveyard":  # (-- if you do (wave 52A) -- "put into YOUR graveyard this way": the cards of that graveyard's owner, Starfall Invocation)
        sel = selectors.replace(sel, zone_owner="you")
    return f"them:{found['this_way']}|{sel.key()}"


def filtered(plan: Plan, ctx: dict[str, Any], cards: list[str], key: str) -> list[str]:
    """The bound cards that match the kind (and are in the zone) a "them:<kind>|<key>" names."""
    sel = selectors.from_key(key)
    return [c for c in cards if selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), ctx["controller"],
                                                  ctx.get("source_card"))]


_IF_PASSIVE = re.compile(r"^(?:a|an|(?P<another>another)|at least one|one or more|any) (?P<what>.+?) (?:is|was|were|are) (?P<rest>.+ this way)$")  # (wave 52A: another)
_IF_THAT = re.compile(r"^that (?:creature|permanent) (?:(?:was|is) (?P<verb>destroyed|sacrificed|exiled)|(?P<dies>dies|died)) this way$")
_IF_YOU_PUT = re.compile(r"^you put (?:a|an|one or more) (?P<what>.+?) (?P<dest>into your hand|onto the battlefield) this way$")  # (wave 45A)
_IF_YOU = re.compile(r"^you (?P<verb>sacrificed|exiled|discarded|milled|destroyed|sacrifice|exile|discard|mill|destroy) (?:a|an|one or more) (?P<what>.+?) this way$")
# -- if you do (wave 100B) -- "If you sacrifice an Island this way" (Serendib Djinn), "If you discard a land card this way" (Silvan Reveler): the same question as the past tense
_PAST = {"sacrifice": "sacrificed", "exile": "exiled", "discard": "discarded", "mill": "milled", "destroy": "destroyed"}
_EITHER = re.compile(r"^(?:a|an) (?P<a>.+?) or (?:a|an) (?P<b>.+?) (?P<rest>(?:is|was) .+ this way)$")  # -- if you do (wave 100B) -- Break the Spell: either kind
_YOU_RETURN_N = re.compile(r"^you return (?P<n>two|three|four|five) or more (?P<what>[a-z ]+?) you control this way$")  # -- if you do (wave 100B) -- Flood of Tears


# -- if you do (wave 10C) -- "If a player / a Dragon / a nonred permanent is dealt damage this way, …" (Play with Fire, The Black Arrow,
# Redcap Melee): the damage instruction just before, read after prevention and replacement (120.3, 615): a recipient is "dealt
# damage" when some damage was actually dealt to it (damage that was all prevented dealt none, 615.1), and what it is is judged as
# it was when the damage was dealt (608.2h).
HIT = "dealt_hit"
_HIT_WHO = re.compile(r"^(?:target(?::\d+)?|it|event|you)$")  # (one recipient: the trigger event's object is one; wave 100B: you)
_DEALT_THIS_WAY = re.compile(r"^(?:a|an) (?P<what>.+?) (?:is|was) dealt damage this way$")
_DEALT_YOU = re.compile(r"^(?:it|~|this creature) deals damage to you this way$")  # -- if you do (wave 100B) -- Mishra's War Machine, Minion of Leshrac


def hit_condition(text: str) -> dict[str, Any] | None:
    if _DEALT_YOU.match(text.strip()):  # (the source's damage to you: ``hit_to``, checked by dealt_to against the damage instruction)
        return {"value": {"ref_amount": HIT}, "op": ">=", "n": 1, "hit_is": selectors.Selector(player="any").key(), "hit_to": "you"}
    m = _DEALT_THIS_WAY.match(text.strip())
    if m is None:
        return None
    sel = selectors.parse(m["what"])
    if sel is None or sel.other or sel.zones != ("battlefield",) or sel.card or sel.controller is not None or sel.owner is not None:
        return None
    if sel.player is not None and sel.player != "any":
        return None  # ("an opponent is dealt damage this way": whose, relative to what? not read)
    return {"value": {"ref_amount": HIT}, "op": ">=", "n": 1, "hit_is": sel.key()}


def _own_json(effects: list[dict[str, Any]]) -> str:
    """-- reflexive excess (wave 42D) -- 603.12: the effects as JSON without the ability they hold (a reflexive trigger's body). That body went through
    ``parse_effects`` itself, so its "dealt damage / damage dealt / excess damage this way" readers are bound to ITS damage instruction already: the
    outer ability has none of its own to bind ("When you do, ~ deals damage equal to that creature's power to another target creature. If excess damage
    was dealt this way, amass Goblins X, where X is that excess damage." — Bolg of the North)."""
    import json

    return json.dumps([{k: v for k, v in e.items() if k != "ability"} for e in effects])


def dealt_to(found: Any) -> Any:
    """Bind every "dealt damage this way" condition of the ability to the one plain damage instruction before it: that
    instruction counts, as it is dealt, the recipients that match (effects._deal). Anything else — no such instruction, two
    of them, a damage chain (several recipients in one sentence), another reader of that damage — leaves the ability manual."""
    if found is None or '"hit_is"' not in _own_json(found[0]):
        return found
    effects = list(found[0])
    gates = [e for e in effects if e.get("do") == "only_if" and "hit_is" in e["cond"]]
    if len(gates) != _own_json(effects).count('"hit_is"') or len({g["cond"]["hit_is"] for g in gates}) != 1:
        return None  # (the condition inside an "and" / "or", or two different questions about it)
    dmg = [i for i, e in enumerate(effects) if e.get("do") == "damage"]
    if len(dmg) != 1 or any(effects.index(g) < dmg[0] for g in gates):
        return None
    d = effects[dmg[0]]
    if d.get("with_next") or any(d.get(k) for k in ("dealt_as", "bind_hit", "bind_dealt", "bind_excess", "excess")) \
            or not _HIT_WHO.match(str(d.get("who"))) or (dmg[0] > 0 and effects[dmg[0] - 1].get("with_next")):
        return None
    if (gates[0]["cond"].get("hit_to") or d.get("who")) == "you" and d.get("who") != gates[0]["cond"].get("hit_to"):
        return None  # -- if you do (wave 100B) -- "If it deals damage to you this way": that instruction's damage to you, and nothing else's
    effects[dmg[0]] = {**d, "bind_hit": HIT, "hit_is": gates[0]["cond"]["hit_is"]}
    return effects, found[1], found[2]


def hits(plan: Plan, ctx: dict[str, Any], events: list[dict[str, Any]], key: str) -> int:
    """How many of the damage events (after prevention and replacement) dealt damage to a recipient the selector names,
    judged before the damage is recorded."""
    sel = selectors.from_key(key)
    n = 0
    for ev in events:
        if int(ev["amount"]) <= 0:
            continue
        if ev["target"] in plan.state.players:
            n += sel.player == "any"
            continue
        card = plan.state.cards.get(ev["target"])
        if sel.player is None and card is not None and card.zone.endswith(":battlefield") and selectors.matches(
                plan, sel, card, plan.ch(card), ctx["controller"], ctx.get("source_card")):
            n += 1
    return n


def condition(text: str) -> dict[str, Any] | None:
    """"If a creature is destroyed this way, …" / "If a land card was milled this way, …" / "If that creature
    dies this way, …" / "If you sacrificed a creature this way, …": at least one object counted (a
    ``conditions`` quantity, judged as the resolution reaches it: 608.2c)."""
    m = _IF_PASSIVE.match(text)
    phrase = f"{'another ' if m['another'] else ''}{m['what']} {m['rest']}" if m else None  # (-- if you do (wave 52A) -- "If another Desert was returned this way" (Arid Archway): other than the source)
    if m is None and (m := _IF_THAT.match(text)) is not None:
        phrase = "permanent " + ("died this way" if m["dies"] else f"{m['verb']} this way")
    if phrase is None and (m := _IF_YOU.match(text)) is not None:
        # (you sacrifice only what you control, 701.21a: "Each player sacrifices a creature. If you sacrificed a
        # creature this way" counts yours; an exile or destruction of your ability is yours; a player mills and
        # discards their own cards, so "you milled / discarded" after "each player …" isn't read)
        # (wave 19C: counted by owner — "each player discards a card. If you discarded a card this way": 701.9a, the card is its owner's)
        verb = _PAST.get(m["verb"], m["verb"])
        ctl = " you controlled" if verb == "sacrificed" else ""
        phrase = f"{m['what']}{ctl} {verb} this way"
        if verb in ("milled", "discarded") and (v := parse(phrase)) is not None:
            return {"value": {**v, "by": "you"}, "op": ">=", "n": 1}
    if phrase is None and (m := _IF_YOU_PUT.match(text)) is not None:  # -- most-played cards II (wave 45A) -- "If you put a Town card into your hand this way" (Town Greeter), "a Cave onto the battlefield" (Spelunking)
        phrase = f"{m['what']} you put {m['dest']} this way"
    v = parse(phrase) if phrase is not None else None
    if v is None and (many := _YOU_RETURN_N.match(text)) is not None:  # -- if you do (wave 100B) -- "If you return four or more nontoken permanents you control this way"
        counted = parse(f"{many['what']} you controlled returned this way")  # (as each last existed, 608.2h; returned to a hand, so not a commander put into the command zone instead)
        if counted is not None and counted.get("of"):
            return {"value": counted, "op": ">=", "n": {"two": 2, "three": 3, "four": 4, "five": 5}[many["n"]]}
    if v is None and (either := _EITHER.match(text)) is not None:  # -- if you do (wave 100B) -- "a permanent you controlled or a token was destroyed this way"
        parts = [condition(f"a {either['a']} {either['rest']}"), condition(f"a {either['b']} {either['rest']}")]
        if all(p is not None and "value" in p and "this_way" in p["value"] for p in parts):
            return {"any": parts}
    if v is None:
        return hit_condition(text)  # -- if you do (wave 10C) --
    return {"value": v, "op": ">=", "n": 1} if v is not None else None


def verbs(kind: str) -> tuple[str, ...]:
    return _VERBS[kind]


# -- any number as an additional cost (wave 48B) -- 601.2h: "As an additional cost to cast this spell, sacrifice any number of creatures. Target creature gets +2/+2 until end of turn for each
# creature sacrificed this way.": no instruction of the spell sacrificed them, its cost did. The verbs of the spell's any-number cost (read while its text is defined) bind to the payment record.
COST = "cost"
DEVOURED = "devoured"
_PAID: ContextVar[frozenset[str]] = ContextVar("paid_kinds", default=frozenset())
_PAID_VERBS = {"SACRIFICE": "sacrificed", "TAP_OTHER": "tapped", "EXILE_FROM_GRAVEYARD": "exiled", "EXILE_FROM_HAND": "exiled"}


def paid() -> frozenset[str]:
    return _PAID.get()


@contextmanager
def paid_by(cost: Any) -> Iterator[None]:
    """The verbs of the any-number parts of ``cost`` (a spell's additional cost, or an activated ability's cost), while its text is read."""
    token = _PAID.set(frozenset(_PAID_VERBS[c.kind] for c in cost.components if c.anyn and c.kind in _PAID_VERBS) if cost is not None else frozenset())
    try:
        yield
    finally:
        _PAID.reset(token)


def bind(v: Any, find: Any) -> Any:
    """Rewrite every placeholder in a value with the binding ``find(kinds)`` names (None: unbound →
    raises LookupError, the line stays manual)."""
    if isinstance(v, list):
        return [bind(x, find) for x in v]
    if not isinstance(v, dict):
        return v
    if "this_way" in v and "ref_count" not in v:
        name = find(_VERBS[v["this_way"]]) or (COST if v["this_way"] in _PAID.get() else None)
        if name is None:
            raise LookupError(v["this_way"])
        return {**v, "ref_count": name}
    return {k: bind(x, find) for k, x in v.items()}


def unbound(v: Any) -> bool:
    """Is a placeholder left that no instruction bound? (a "this way" outside a resolution)"""
    if isinstance(v, list):
        return any(unbound(x) for x in v)
    if not isinstance(v, dict):
        return False
    if "this_way" in v and "ref_count" not in v:
        return True
    return any(unbound(x) for x in v.values())


def _happened(plan: Plan, kind: str, new: dict[str, Any], was: dict[str, Any], you: str) -> bool:
    if kind in ("tapped", "revealed", "created", "goaded"):  # (wave 50J: goaded, ``_matched`` keeps those it goaded; tap_choice binds exactly the permanents it tapped; reveal_hand: the cards it showed, which stay put; create_token: the tokens it made)
        return True
    old_card = plan.state.cards.get(was["card"])
    if kind == "shuffled":  # (-- static_other sweep (wave 16B) -- a library shuffle gives its cards new ids: gone from where it was, or in a library)
        return old_card is None or old_card.zone.endswith(":library")
    moved = old_card is None or plan.oid(old_card) != was["object_id"] or new["object_id"] != was["object_id"]
    if not moved:
        return False
    dest = (new.get("zone") or "").rsplit(":", 1)[-1] if new["object_id"] != was["object_id"] else None
    if old_card is None and dest is None:  # -- review 40 -- a token went where it was sent, then ceased to exist (111.7): the turn log keeps where (Siren's Ruse 2017-09-29)
        from app.rules import history

        dest = next((d.to for d in reversed(history.log_for(plan).left) if d.object_id == was["object_id"]), None)
    if kind in ("returned", "your_hand"):  # (a hand is hidden: only the card's zone now tells where it went)
        return old_card is not None and old_card.zone == f"{you}:hand" if kind == "your_hand" else \
            old_card is not None and old_card.zone.endswith(":hand")
    if kind == "exiled":
        return dest in ("exile", "battlefield")  # (wave 46C: a blinked permanent came back as a new object, 400.7, but it was exiled)
    if kind == "battlefield_put":
        return dest == "battlefield"
    if kind in ("graveyard", "your_graveyard"):
        return dest == "graveyard"
    if kind == "died":
        return dest == "graveyard" and (was.get("zone") or "").endswith("battlefield")
    return True


def count(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """How many of the objects the bound instruction acted on it actually did this to (and that
    match the qualifier): see the module docstring. ``max_by: "owner"``: the most any one player had (a
    discarded or milled card is its owner's: 701.9a, 701.17a)."""
    if v["this_way"] == "drawn":
        return drawn(plan, ctx, v)
    found = _matched(plan, ctx, v)
    if v.get("stat"):  # -- any number as an additional cost (wave 48B) -- "the total power of the sacrificed creatures": each as it is, or as it last existed (608.2h)
        from app.game.rules_state import ObjectRef
        from app.rules import context, sba
        from app.rules.triggers import _snapshot_card

        got = [_still_there(plan, was) or (_snapshot_card(plan, snap) if (snap := context.snapshot(plan, ObjectRef.model_validate(was))) else None) for _, was in found]
        stat = sba.power if v["stat"] == "power" else sba.toughness  # (wave 100B: its power with every layer and counter applied, 613.4c — not the printed number)
        if v.get("agg") == "max":
            return max([0, *(stat(g[0], g[1]) or 0 for g in got if g)])
        return max(0, sum(stat(g[0], g[1]) or 0 for g in got if g))  # (107.1b: a total below 0 is 0)
    if v.get("distinct"):  # "card types among cards discarded this way": the different types the cards have where they went (205.2a)
        from app.rules import values

        return len({"Kindred" if t == "Tribal" else t for new, _ in found if (c := plan.state.cards.get(new["card"])) is not None
                    for t in plan.ch(c).types if t in values.CARD_TYPES})
    if v.get("delta"):  # -- static_other sweep (wave 16B) -- "draws that many cards plus / minus one"
        return max(0, len(found) + int(v["delta"]))
    if v.get("max_by") == "owner":
        owners: dict[str, int] = {}
        for new, _ in found:
            card = plan.state.cards.get(new["card"])
            if card is not None:
                owners[card.owner] = owners.get(card.owner, 0) + 1
        return max(owners.values(), default=0)
    return len(found)


# -- if you do (wave 52A) -- "You draw a card for each card drawn this way." (Struggle for Project Purity), "… for each opponent who drew a card this way." (Cut a Deal): 121.2 the cards the
# draw instruction made each player draw, as the turn's own record of cards drawn (history: it counts what the instruction drew, a draw a replacement effect replaced or
# a prohibition stopped was not drawn, 121.2a / 614.11) less what each player had drawn when the instruction began.
def mark_drawn(plan: Plan, ctx: dict[str, Any], name: str) -> None:
    from app.rules import context, history

    context.refs(ctx)[name] = {"kind": "drew", "drew": dict(history.log_for(plan).drew)}


def drawn(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    from app.rules import history

    mark = (ctx.get("refs") or {}).get(v["ref_count"])
    if mark is None:
        return 0  # -- if you do (wave 100B) -- the draw instruction never ran (a condition before it skipped it): it drew nothing (Trade Route Envoy)
    before = mark.get("drew") or {}
    now = history.log_for(plan).drew
    each = {p: max(0, n - before.get(p, 0)) for p, n in now.items() if p in plan.live()}
    if v.get("players") == "you":
        return each.get(ctx["controller"],0)
    if v.get("players") == "opponent":
        return sum(1 for p, n in each.items() if n and p != ctx["controller"])
    return sum(each.values())


def by_controller(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> dict[str, int]:
    """"For each permanent destroyed this way, its controller creates …": how many of them each player
    controlled, as each last existed on the battlefield (608.2h); a card that wasn't a permanent has no
    controller — its owner is used (108.4a)."""
    from app.game.rules_state import ObjectRef
    from app.rules import context

    out: dict[str, int] = {}
    for new, was in _matched(plan, ctx, v):
        here = _still_there(plan, was)
        snap = context.snapshot(plan, ObjectRef.model_validate(was))
        card = plan.state.cards.get(new["card"])
        pid = here[0].controller if here is not None else snap.controller if snap is not None else \
            (card.owner if card is not None else (new.get("zone") or "").split(":")[0] or None)  # (a card put in a library is re-keyed: its old zone's owner)
        if pid is not None:
            out[pid] = out.get(pid, 0) + 1
    return out


def _still_there(plan: Plan, was: dict[str, Any]) -> tuple[Any, Any] | None:
    """The object, if it is still that object on the battlefield (a permanent this effect tapped)."""
    card = plan.state.cards.get(was["card"])
    if card is None or plan.oid(card) != was["object_id"] or not card.zone.endswith(":battlefield"):
        return None
    return card, plan.ch(card)


def cost_objects(plan: Plan, ctx: dict[str, Any], source: str, kind: str) -> dict[str, Any]:
    """-- any number as an additional cost (wave 48B) -- what the spell's cost sacrificed or tapped, from its payment record (a copy has the original's, 707.10); or what the
    source devoured as it entered (702.82b)."""
    sid = ctx.get("stack_id")
    record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if record is None and src is not None and src.zone == "stack":  # a cast trigger of the spell itself (601.2i): its cost's record
        record = plan.rules.payments.get(plan.oid(src))
    if kind == "exiled":  # (the cards it exiled are in exile now, new objects: 400.7j)
        pairs = [] if record is None else list(zip(record.exiled_objects, record.exiled_was, strict=False))
        news = [{"card": o.rsplit(".", 1)[0], "object_id": o, "zone": f"{plan.state.cards[o.rsplit('.', 1)[0]].owner}:exile"} for o, _ in pairs if o.rsplit(".", 1)[0] in plan.state.cards]
        return {"objects": news, "was": [{"card": w.rsplit(".", 1)[0], "object_id": w, "zone": None} for o, w in pairs if o.rsplit(".", 1)[0] in plan.state.cards]}
    oids = plan.rules.devoured_ids.get(ctx.get("source_object") or "", []) if source == DEVOURED else \
        [] if record is None else record.sacrificed_objects if kind == "sacrificed" else record.tapped_objects
    return {"objects": [{"card": o.rsplit(".", 1)[0], "object_id": o, "zone": None} for o in oids]}


def _matched(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    from app.game.rules_state import ObjectRef
    from app.rules import context
    from app.rules.triggers import _snapshot_card  # (triggers imports effects, which imports values → this)

    b = cost_objects(plan, ctx, v["ref_count"], v["this_way"]) if v["ref_count"] in (COST, DEVOURED) else (ctx.get("refs") or {}).get(v["ref_count"]) or {}
    news = b.get("objects") or []
    wases = b.get("was") or news
    you = ctx["controller"]
    sel = selectors.from_key(v["of"]) if v.get("of") else None
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for new, was in zip(news, wases, strict=False):
        if not _happened(plan, v["this_way"], new, was, you):
            continue
        if v["this_way"] == "goaded" and new["object_id"] not in ctx.get("goaded", []):
            continue  # -- goad (wave 50J) -- 701.15d: goading a creature the same player already goaded has no effect, so it wasn't goaded this way
        if v.get("named") and getattr(plan.state.cards.get(new["card"]), "name", None) != v["named"]:
            continue  # -- reflexive this way (wave 30G) -- the tokens this instruction asked for, by name (a Chatterfang's extra Squirrels aren't)
        if v.get("by") == "you" and getattr(plan.state.cards.get(new["card"]), "owner", None) != you:
            continue  # (wave 19C: only the cards the controller discarded / milled)
        if v["this_way"] == "your_graveyard" and not (new.get("zone") or "").startswith(f"{you}:"):
            continue
        if sel is not None and v["this_way"] == "battlefield_put":  # -- most-played cards II (wave 45A) -- the permanent it became: what it is now that it is there ("a Cave", "a land card")
            now = plan.state.cards.get(new["card"])
            if now is None or plan.oid(now) != new["object_id"] or not now.zone.endswith(":battlefield") or not selectors.matches(
                    plan, selectors.replace(sel, card=False, zones=("battlefield",)), now, plan.ch(now), you):
                continue
        elif sel is not None:
            if sel.card:  # a card: where it went (a public zone, 400.7j / 701.17c)
                card = plan.state.cards.get(new["card"])
                if v.get("public") and card is not None and not card.is_token and new["object_id"] == was["object_id"]:
                    # (wave 45A: a card put into the hand that was public before - milled, revealed: its printed kind; scripts.py checked the look before it)
                    if not selectors.matches(plan, sel, card, plan.ch(card), you):
                        continue
                    out.append((new, was))
                    continue
                if card is None or new["object_id"] == was["object_id"] or card.is_token:
                    continue  # (a hidden zone, or gone: nothing to read; a token isn't a card, 111.1)
                then = card if card.zone == new.get("zone") else card.model_copy(update={"zone": new.get("zone") or card.zone})
                from app.rules import characteristics

                ch = characteristics.of(then, plan.info) if then is not card else plan.ch(card)
                if not selectors.matches(plan, sel, then, ch, you):
                    continue
            else:  # a permanent: as it is while it's still there, else as it last existed on the battlefield (608.2h)
                here = _still_there(plan, was)
                snap = context.snapshot(plan, ObjectRef.model_validate(was)) if here is None else None
                if here is None and snap is None:
                    continue
                card, ch = here if here is not None else _snapshot_card(plan, snap)  # type: ignore[arg-type]
                if not selectors.matches(plan, sel, card, ch, you, ctx.get("source_card")):  # (wave 52A: "another" is than the ability's source)
                    continue
        out.append((new, was))
    return out


# -- if you do (wave 5G) -- "~ deals 2 damage to each other player. You gain life equal to the damage dealt this way."
DAMAGE_DEALT = "damage_dealt"


def damage_dealt(found: Any) -> Any:
    """"You gain life equal to the damage dealt this way." (Syphon Soul, Creeping Bloodsucker): the total damage the
    damage instruction just before actually dealt — after prevention and replacement (615.6, 120.4: the damage events
    as they are dealt), all recipients together. Only right after one plain damage instruction; anything else in
    between, or no such instruction, leaves the ability manual."""
    if found is None or f'"{DAMAGE_DEALT}"' not in _own_json(found[0]):
        return found
    effects = found[0]
    for i, e in enumerate(effects):
        if f'"{DAMAGE_DEALT}"' not in _own_json([e]):
            continue
        prev = effects[i - 1] if i else None
        if prev is None or prev.get("do") != "damage" or prev.get("with_next") or prev.get("bind_dealt") \
                or e.get("do") != "gain_life" or (i > 1 and effects[i - 2].get("with_next")):
            return None
        effects = [*effects[:i - 1], {**prev, "bind_dealt": DAMAGE_DEALT}, *effects[i:]]
    return effects, found[1], found[2]


# -- as long as (wave 9B) -- "Create a number of Treasure tokens equal to the amount of excess damage dealt to that creature this way."
EXCESS_DEALT = "excess_dealt"
_SINGLE = re.compile(r"^(?:target(?::\d+)?|it)$")


def excess_dealt(found: Any) -> Any:
    """120.10: the excess damage the damage instruction just before dealt (the damage actually dealt, after prevention and
    replacement, above lethal damage — a planeswalker's loyalty, a battle's defense — to the permanent it was dealt to, as it was
    before the damage). Bound to the nearest plain damage instruction before the first thing that reads it; that instruction
    must name one target (several recipients: "to that creature" would be ambiguous). Anything else leaves the line manual."""
    if found is None or f'"{EXCESS_DEALT}"' not in _own_json(found[0]):
        return found
    effects = list(found[0])
    first = next(i for i, e in enumerate(effects) if f'"{EXCESS_DEALT}"' in _own_json([e]))
    prev = next((i for i in range(first - 1, -1, -1) if effects[i].get("do") == "damage"), None)
    if prev is None:
        return None
    d = effects[prev]
    if d.get("with_next") or d.get("bind_excess") or d.get("dealt_as") or not _SINGLE.match(str(d.get("who"))) \
            or (prev > 0 and effects[prev - 1].get("with_next")) or d.get("excess"):
        return None
    effects[prev] = {**d, "bind_excess": EXCESS_DEALT}
    return effects, found[1], found[2]


def excess_by_target(plan: Plan, events: list[dict[str, Any]], *, note: bool = True) -> dict[str, int]:
    """120.10: the damage dealt by these events to permanents, in excess of what was lethal (a creature: its toughness less the
    damage marked before this damage; a planeswalker: its loyalty; a battle: its defense; several of those types: the greatest),
    all sources together, for each permanent that was dealt some. Read before the damage is recorded. -- review (wave 10C) -- 120.4a: "Any
    amount of damage greater than 1 is excess damage if the source dealing that damage to a creature has deathtouch" (702.2c: any
    nonzero deathtouch damage is lethal for excess): a deathtouch source's damage beyond 1 is excess (all of it once the creature
    has already been dealt lethal). Wither and infect (120.3d) deal the same damage, as counters: lethal damage is unchanged.
    Deathtouch mixed with other sources on one creature: how the lethal share splits is unsettled (noted)."""
    total: dict[str, int] = {}
    dt: dict[str, int] = {}  # damage to a target from deathtouch sources, and how many such hits
    dt_hits: dict[str, int] = {}
    for ev in events:
        if ev["target"] in plan.state.cards and int(ev["amount"]) > 0:
            n = int(ev["amount"])
            total[ev["target"]] = total.get(ev["target"], 0) + n
            if "deathtouch" in set(ev.get("kw") or ()):
                dt[ev["target"]] = dt.get(ev["target"], 0) + n
                dt_hits[ev["target"]] = dt_hits.get(ev["target"], 0) + 1
    mixed = [cid for cid in dt if dt[cid] != total[cid] and plan.ch(plan.state.cards[cid]).is_creature]
    if mixed and note:  # (``note`` False: the trigger record of every damage event, wave 39B, which asks nobody)
        plan.note("Damage from a deathtouch source and from other sources was dealt to the same creature together: the excess is "
                  "counted as the damage beyond its toughness — adjust by hand if it should differ", mixed)
    excess: dict[str, int] = {}  # -- trigger damage (wave 39B) -- per permanent: do_damage records it on the damage event (a trigger reads it)
    for cid, n in total.items():
        card = plan.state.cards[cid]
        if not card.zone.endswith(":battlefield"):
            continue
        ch = plan.ch(card)
        over = []
        if ch.is_creature and ch.pt is not None:
            from app.rules import (
                wave110a_zilortha,  # -- wave 110A -- Zilortha: the excess over lethal damage (120.10) counts power
            )

            left = max(0, (wave110a_zilortha.basis(plan, card, ch, ch.pt[1]) or 0) - card.damage)
            # only deathtouch sources: 120.4a, each source's damage beyond 1 (all of it if lethal damage is already marked)
            over.append((n if left == 0 else n - dt_hits[cid]) if dt.get(cid) == n else n - left)
        if "Planeswalker" in ch.types:
            over.append(n - card.counters.get("loyalty", 0))
        if "Battle" in ch.types:
            over.append(n - card.counters.get("defense", 0))
        excess[cid] = max(0, max(over, default=0))
    return excess


def excess_of(plan: Plan, events: list[dict[str, Any]]) -> int:
    """120.10: the excess damage of these events, summed over the permanents they dealt damage to (``excess_by_target``)."""
    return sum(excess_by_target(plan, events).values())


_SWAP = re.compile(r"^each player exiles all (?P<cards>creature) cards from their graveyard, then sacrifices all (?P<perms>creatures) "
                   r"they control, then puts all cards they exiled this way onto the battlefield$")


def graveyard_swap(text: str) -> list[dict[str, Any]] | None:
    """-- if you do (wave 5G) -- "Each player exiles all creature cards from their graveyard, then sacrifices all
    creatures they control, then puts all cards they exiled this way onto the battlefield." (Living Death, Living
    End): three instructions, each done by every player at once (101.4: nothing to choose, so simultaneously) —
    every graveyard's creature cards exiled together (406.3), every creature sacrificed by its controller together
    (701.21a), then the cards that exile moved put onto the battlefield together, each under its owner's control
    (the player who exiled it; 400.7: the cards as they are in exile, 603.6a: one event, 614.12)."""
    m = _SWAP.match(text)
    if m is None:
        return None
    cards = selectors.parse("creature cards in graveyards")
    perms = selectors.parse("creatures")
    if cards is None or perms is None:
        return None
    return [{"do": "exile", "who": cards.key(), "as": "swap0"},
            {"do": "sacrifice", "who": perms.key(), "by": "controller"},
            {"do": "return_card", "who": "ref:swap0", "to": "battlefield", "tapped": False, "under": "owner"}]


# -- "Tap any number of untapped creatures you control. … for each creature tapped this way" ----------------------
def tap_choice(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The controller chooses any number (0 or more) of the untapped permanents they control that match, and taps
    them (701.26a); the binding (``as``) is what it tapped. False while the choice is open."""
    from app.rules.plan import decide

    you = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    mine = [c for c in selectors.candidates(plan, sel, you, ctx.get("source_card"))
            if plan.state.cards[c].controller == you and plan.state.cards[c].zone.endswith(":battlefield")
            and not plan.state.cards[c].tapped]
    if not mine:
        _tap_chosen(plan, ctx, e, [])
        return True
    decide(plan, player=you, kind="choose_cards", prompt=f"{ctx.get('name', '') or 'Tap'}: tap any number of them",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in mine],
           min_choices=0, max_choices=len(mine), resume={"step": "tap_choice", "ctx": ctx, "e": e})
    return False


def _tap_chosen(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], chosen: list[str]) -> None:
    from app.rules import context

    cards = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")
             and plan.state.cards[c].controller == ctx["controller"] and not plan.state.cards[c].tapped]
    if e.get("as"):
        context.bind_objects(plan, ctx, e["as"], cards)
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": True}, actor=ctx["controller"])


def resume_tap_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    _tap_chosen(plan, ctx, d.resume["e"], chosen)
    continue_effects(plan, ctx)
