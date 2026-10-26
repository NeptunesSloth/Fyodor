"""-- exiled with (wave 6D) -- "When ~ leaves the battlefield, return the exiled card to the battlefield under its owner's
control." (Oblivion Ring, Fiend Hunter, Journey to Nowhere, Tidehollow Sculler, Worldgorger Dragon …)

607.2a: an activated or triggered ability printed on an object that instructs a player to exile cards and an ability
printed on it that refers to "the exiled card(s)" or to cards "exiled with [this object]" are linked: the second refers
only to cards in exile that the first put there. Researched against CR 2026-09-25.

* The exiling ability's ``exile`` effects carry ``"link": True``; as one resolves, the objects it put into exile are
  recorded under the source object (``RulesState.exiled_with``, by object id). A source that already left the
  battlefield is still that object (its last known information, 608.2h): what it exiles then is recorded under the
  object that left, whose leaves-the-battlefield ability already resolved — the cards stay in exile for good (the
  well-known Oblivion Ring sequence, 607.2a + 603.10a). A copy of the object is a different object with its own record.
* The referring ability's ``who: "exiled_with"`` finds those cards while each is still the object that was exiled
  (400.7: one that left exile and came back is a new object).
* Read only when every other printed ability that exiles is understood (wave 30H: two exiling abilities feed one set, Rona's and Circu's
  rulings): anything else (an exiling ability the grammar doesn't read, "the exiled card's owner …") stays manual.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef
from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

WHO = "exiled_with"
# (-- resolution memory (wave 22D) -- "each creature card exiled with it", "all permanent cards exiled with ~": a kind of the linked cards)
_THE = r"(?:the exiled cards?|(?:all|each) (?:(?P<spec>[\w\-]+) )?cards? exiled with (?:it|~))"
_UNDER = (r"under (?:(?P<you>your) control|(?:its|their) owner(?:'s|s') control"
          r"|the control of (?:that card's|its|their) owners?(?:'s|s')?)")  # (Trove Warden: "under the control of that card's owner")
_BATTLEFIELD = re.compile(rf"^(?:return|put) {_THE} (?:to|onto) the battlefield(?P<tapped> tapped)?(?: (?P<specified>{_UNDER}))?$")
_HAND = re.compile(rf"^(?:return|put) {_THE} (?:to|into) (?:its|their) owner(?:'s|s') hands?$")  # (wave 20D: "Put all cards exiled with ~ into their owners' hands.")
_GRAVEYARD = re.compile(rf"^(?:put|return) {_THE} (?:into|to) (?:its|their) owner(?:'s|s') graveyards?$")  # (Currency Converter, Valakut Exploration, Gravegouger)
_REFERS = re.compile(r"\bthe exiled cards?\b|\bcards?(?: you own| they own)?(?: have been)? exiled with (?:it\b|~|this [A-Za-z]+)|\bthat was exiled with (?:it\b|~)")  # (wave 17D: "~" has no word boundary after it)
_OWNERS_RETURN = re.compile(r"^each player returns to (?P<where>the battlefield|their hand) all cards they own exiled with (?:it|~)$")


def _owners_return(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{'do': 'return_card', 'who': WHO, 'to': 'battlefield' if m['where'] == 'the battlefield' else 'hand',
             'under': 'owner', 'tapped': False}], None


# -- review (wave 6R) -- "Exile target creature. Return the exiled card to the battlefield under its owner's control at the
# beginning of the next end step." (Voyager Staff, Hide on the Ceiling): "the exiled card" there is what the same
# ability's own instruction exiled (608.2c), not a linked ability's (607.2a). Such an ability is read again without
# these templates (the pronoun reading it had before wave 6): ``_off_now()`` while that happens (per thread, review 29A: one thread's re-reading
# changed what another thread read, and the parse cache kept it).
def _off_now() -> bool:
    return getattr(_STATE, "off", False)


def _off(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    if not _off_now():
        return None
    from app.rules import language
    from app.rules.scripts import _NoMatch

    found = language.parse_sentence(m.group(0))  # ("the exiled card": the generic grammar's pronoun, language.ref)
    if found is None:
        raise _NoMatch
    return found


def _who(m: re.Match[str]) -> str:
    """The linked cards, or only those of the named kind ("each creature card exiled with it": a selector, 607.2a)."""
    from app.rules import selectors
    from app.rules.scripts import _NoMatch

    if not m["spec"]:
        return WHO
    if m["spec"] == "other":  # "each other card exiled with ~": not the card(s) this same resolution just exiled (608.2c, 607.2a)
        return f"{WHO}:other"
    sel = selectors.parse(f"{m['spec']} card")
    if sel is None or sel.player is not None or sel.zones or sel.controller is not None:
        raise _NoMatch
    return f"{WHO}:{sel.key()}"


def _battlefield(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_card", "who": _who(m), "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you" if m["you"] or not m["specified"] else "owner"}], None


def _hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_card", "who": _who(m), "to": "hand"}], None


def _graveyard(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_card", "who": _who(m), "to": "graveyard"}], None


# -- copied abilities (wave 18F) -- imprint (607.2a): "you may exile an instant card with mana value 2 or less from your hand" (the cost of
# an optional payment, public once in exile: 406.3), and "you may copy the exiled card" (707.12: the copy is made in exile, may be cast
# while this resolves; one not cast ceases to exist, 707.10a - so a copy not taken and a copy not cast are the same)
_IMPRINT = re.compile(r"^you may exile (?P<what>(?:an?|one) (?:[\w\-]+,? )*card(?: with mana value \d+ or (?:less|greater))?) from your hand$")  # (wave 51B: "a nonartifact, nonland card", Chrome Mox)
_COPY = re.compile(rf"^(?:you may )?copy {_THE}$")


def imprint(text: str) -> list[dict[str, Any]] | None:
    """The optional payment "you may exile an instant card … from your hand" as a whole sentence (its "you may" is the payer's choice
    here, not an optional trigger's), or None."""
    from app.rules import optional_payment

    m = _IMPRINT.match(text)
    cost = optional_payment.cost_text(f"exile {m['what']} from your hand") if m else None
    return [{"do": "optional_payment", "who": "you", "cost": cost, "bind": "pay0"}] if cost else None


def _copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "copy_cards", "who": _who(m)}], None


# -- activated other (wave 42C) -- "Put a creature card exiled with ~ onto the battlefield under your control." (Sisters of Stone Death, Yggdrasil, Rebirth Engine): ONE of the linked
# cards, chosen by the ability's controller as it resolves (608.2d; nothing is targeted). Only the battlefield (a card exiled face down would be named by the choice)
_PICK = re.compile(r"^(?:return|put) an? (?:(?P<spec>[\w\-]+) )?card exiled with (?:it|~) (?:to|onto) the battlefield(?P<tapped> tapped)?(?P<you> under your control)?"
                   r"(?: with (?P<cn>\w+) additional (?P<ck>\+1/\+1) counters? on it)?$")  # (-- piles (wave 53D) -- Sothera, the Supervoid: "with two additional +1/+1 counters on it", 122.6)


_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4}


# -- group choices (wave 53D) -- Foreboding Steamboat: "put a card exiled with it into its owner's graveyard" -- ONE of the linked cards, chosen by the controller as it resolves
_PICK_HAND = re.compile(r"^(?:return|put) an? (?:(?P<spec>instant or sorcery|creature|permanent) )?card(?P<own> you own)? exiled with (?:it|~) (?:to|into) (?:its owner's|your) hand$")
_OWN_HAND = re.compile(r"^(?:return|put) all cards you own exiled with (?:it|~) (?:to|into) your hand$")
_TARGET_HAND = re.compile(r"^(?:return|put) target (?:(?P<spec>creature|permanent) )?card exiled with (?:it|~) (?:to|into) its owner's hand$")


def _pick_hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    who = _who(m)
    if m['own']:
        from app.rules import selectors

        sel = selectors.parse((m['spec'] + ' ' if m['spec'] else '') + 'card you own')
        assert sel is not None
        who = f'{WHO}:{sel.key()}'
    return [{"do": "return_choice", "who": who, "n": 1, "upto": False, "random": False, "label": "card", "to": "hand"}], None


def _own_hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import selectors

    sel = selectors.parse('card you own')
    assert sel is not None
    return [{'do': 'return_card', 'who': f'{WHO}:{sel.key()}', 'to': 'hand'}], None


def _target_hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{'do': 'return_card', 'who': 'target', 'to': 'hand'}], _who(m)


_PICK_GRAVEYARD = re.compile(r"^put an? (?:(?P<spec>[\w\-]+) )?card exiled with (?:it|~) into (?:its|their) owner(?:'s|s') graveyard$")


def _pick_graveyard(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_choice", "who": _who(m), "n": 1, "upto": False, "random": False, "label": f"{m['spec']} card" if m["spec"] else "card", "to": "graveyard"}], None


def _pick(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    from app.rules.scripts import _NoMatch

    counters = {} if not m["cn"] else {"counter": m["ck"], "counter_n": _COUNT.get(m["cn"], 0)}
    if m["cn"] and not counters["counter_n"]:
        raise _NoMatch
    return [{"do": "return_choice", "who": _who(m), "n": 1, "upto": False, "random": False, "label": f"{m['spec']} card" if m["spec"] else "card",
             "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you", **counters}], None


# CR 607.2b: a targeted linked return announces its card before resolution.
_TARGET_BATTLEFIELD = re.compile(r"^(?:return|put) target (?:(?P<spec>[\w-]+) )?card exiled with (?:it|~) (?:to|onto) the battlefield"
                                 r"(?P<tapped> tapped)? under your control(?: with (?P<cn>\w+) additional (?P<ck>\+1/\+1) counters? on it)?$")


def _target_battlefield(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    from app.rules.scripts import _NoMatch

    counters = {} if not m["cn"] else {"counter": m["ck"], "counter_n": int(m["cn"]) if m["cn"].isdigit() else _COUNT.get(m["cn"], 0)}
    if m["cn"] and not counters["counter_n"]:
        raise _NoMatch
    return [{"do": "return_card", "who": "target", "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you", **counters}], _who(m)


# -- cost reductions paid with objects (wave 47C) -- "choose a card at random exiled with Gorex and put that card into its owner's hand": the table picks one of the linked cards (recorded
# as the move, so a replay is the same; return_choice's ``random``)
_PICK_RANDOM = re.compile(r"^choose a card at random exiled with (?:it|~) and put (?:that card|it) into its owner's hand$")


def _pick_random(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_choice", "who": WHO, "n": 1, "upto": False, "random": True, "label": "card", "to": "hand"}], None


# -- piles (wave 53D) -- 607.2a: "put the top card of the pile you exiled into your hand" (Parallel Thoughts), "put the top card of the exiled pile into its owner's hand" (Mangara's
# Tome): the pile is what the linked search exiled face down and shuffled (pile_groups.pile_shuffle); its top card is the first of the cards still in it
_TOP_OF_PILE = re.compile(r"^put the top card of (?:the pile you exiled|the exiled pile) into (?:your|its owner's) hand$")
REFERS_PILE = re.compile(r"\bthe (?:pile you exiled|exiled pile)\b")


def _top_of_pile(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "pile_top_hand"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_TARGET_HAND, _target_hand), (_OWN_HAND, _own_hand), (_PICK_HAND, _pick_hand), (_OWNERS_RETURN, _owners_return), (_TARGET_BATTLEFIELD, _target_battlefield), (_BATTLEFIELD, _battlefield), (_HAND, _hand), (_GRAVEYARD, _graveyard), (_COPY, _copy), (_PICK, _pick), (_PICK_RANDOM, _pick_random),
                                                (_TOP_OF_PILE, _top_of_pile), (_PICK_GRAVEYARD, _pick_graveyard)]

# -- linked casting (wave 30H) -- 607.2a, 608.2g: in an ability that only refers to what another exiled, "cast a spell from among cards exiled with ~
# [without paying its mana cost]" casts from the linked cards (the ones ``linked_cards`` binds, as "them"), as this ability resolves
_AMONG = re.compile(r"\bfrom among (?:the )?cards exiled with (?:it\b|~)")
_ANY_CARDS = re.compile(r"\b([Cc]ast any number of) cards exiled with (?:it\b|~) (without paying their mana costs)")


_CAST_A_CARD = re.compile(r"\b([Cc]ast) a card exiled with (?:it\b|~)")  # -- activation words (wave 48C) -- Krang & Shredder: what is cast from exile is a spell


def among(body: str) -> str:
    """The sentence(s) of a linked-referring ability with "cards exiled with ~" read as "them" (see the free-cast grammar, permissions.FREE_AMONG)."""
    return _ANY_CARDS.sub(r"\1 spells from among them \2", _AMONG.sub("from among them", _CAST_A_CARD.sub(r"\1 a spell from among cards exiled with ~", body)))


def _exiles(d: dict[str, Any] | None) -> bool:
    if d is not None and d.get('static') == 'replace' and d.get('event') == 'draw' and (d.get('op') or {}).get('do') == 'body':
        return _exiles({'effects': d['op'].get('effects') or []})
    if d is not None and d.get('static') == 'additional_cost':
        from app.rules import costs

        extra = costs.parse_additional_cost(d.get('cost') or '')
        if extra is not None and any(c.kind == costs.BEHOLD_EXILE for c in extra.components):
            return True
    # (-- champion (wave 12B) -- also a payment: "sacrifice it unless you exile another Merfolk you control", recorded by
    # optional_payment._pay)
    return d is not None and (d.get("static") == "exile_instead" or (d.get("static") == "own_optional" and d.get("optional") in ("reduce", "exile") and d["cost"].startswith("Exile "))
                              or any(  # (-- linked exile (wave 30H) -- 607.2b: a replacement effect that exiles; -- cost reductions paid with objects (wave 47C) -- 607.2q: a cost that exiles)
        e.get("do") in ("exile", "exile_top", "exile_until", "exile_on_resolve", "linked_graveyard_choice") or (e.get('do') == 'temporary_hand_exile' and e.get('mode') == 'amnesia') or e.get("exile") or _picks_to_exile(e)
        or (e.get("do") == "optional_payment" and str(e.get("cost")).startswith("Exile ")) for e in d.get("effects") or []))


def _picks_to_exile(e: dict[str, Any]) -> bool:
    """-- resolution memory (wave 22D) -- "search your library for an artifact card, exile it" / "look at …, exile one of them" (Hoarding Dragon)"""
    return e.get("do") == "exile_hand_down" or (e.get("do") in ("search", "pick_looked", "discard", "return_choice") and e.get("to") == "exile")


def link(d: dict[str, Any] | None, ability: Any, ch: Any) -> dict[str, Any] | None:
    """The definition with its link (607.2a) checked and marked; None when a reference has no single linked ability."""
    if d is None:
        return None
    active = _STATE.__dict__.setdefault("active", set())
    key = (ch.name, ability.index)
    if key in active and not _off_now():  # (the _off_now() re-reading of the same ability is deliberate: _link)
        return None  # (two abilities that each refer to the other's exile: no single linked ability, 607.2a)
    active.add(key)
    try:
        return _link(d, ability, ch)
    finally:
        active.discard(key)


def _link(d: dict[str, Any], ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    refers = WHO in json.dumps(d, default=str) or "linked_cards" in json.dumps(d, default=str) or "linked_pool" in json.dumps(d, default=str)
    if "samename_exiled_with" in json.dumps(d, default=str) and ability.kind == "activated":
        return None  # -- same name (wave 32A) -- "Counter target spell with the same name as a card exiled with this creature" (Mindreaver) sacrifices the source
        # as a cost: its target is judged on resolution against the cards of an object that is gone (selectors._same_name_now reads a source that stays)
    others = [ab for ab in ch.abilities if ab.index != ability.index and ab.kind in ("triggered", "activated")]
    borrowed = getattr(ability, 'borrowed_origin', ())
    if borrowed:
        others = [ab for ab in others if getattr(ab, 'borrowed_origin', ())[:-1] == borrowed[:-1]]
    if refers and _exiles(d) and d.get('accumulating_link'):
        return d
    if refers and _exiles(d) and any(e.get("do") == "copy_cards" and e.get("who") == WHO and e.get("source_link") for e in d.get("effects") or []):
        return d  # 607.2a: an explicit accumulating source-linked set, including this resolution
    if refers and _exiles(d) and 'linked_pool' in json.dumps(d, default=str):
        return {**d, 'effects': [{**e, 'link': True} if e.get('do') in ('exile', 'discard', 'optional_payment') else e for e in d.get('effects') or []]}
    if refers and _exiles(d):  # -- review (wave 6R) -- its own exiled card (see _off_now)
        if _off_now():
            return None  # (-- wave 22D -- read again without the templates and it still refers to a linked card: not read)
        _STATE.off = True
        try:
            return scripts.define(ability, ch)
        finally:
            _STATE.off = False
    if refers:
        if borrowed:
            return d  # 607.5: a newly acquired, independently scoped link may have no exiling half
        exiling = [ab for ab in others if re.search(r"\bexiles?\b", ab.text, re.IGNORECASE)]  # (-- linked casting (wave 30H) -- "each player exiles the top X cards": Jeleva)
        exiling += [ab for ab in ch.abilities if ab.index != ability.index and ab.kind == "static"  # (607.2b: a replacement effect that exiles)
                    and (scripts.define(ab, ch) or {}).get("static") in ("exile_instead", "own_optional", "additional_cost", "replace") and _exiles(scripts.define(ab, ch))]  # (wave 47C: 607.2q, Gorex's cost)
        from app.rules import hideaway

        if hideaway.exiles(ch):  # -- hideaway (wave 29D) -- 702.75a: the keyword is the exiling ability (and the only one: 607.2a)
            return None if exiling else hideaway.each(d)
        # Opposite-face text validates the link; it never grants those abilities.
        # The runtime pool remains this exact physical source incarnation.
        other_face = [ab for ab in ch.linked_other_face if re.search(r'\bexiles?\b', ab.text, re.IGNORECASE)]
        if not exiling and other_face and all(_exiles(scripts.define(ab, ch)) for ab in other_face):
            return d
        exiling += [ab for ab in ch.abilities if ab.index != ability.index and ab.kind == 'static'
                    and (scripts.define(ab, ch) or {}).get('trigger') == 'chapter' and _exiles(scripts.define(ab, ch))]
        printed_delve = any(ab.index < 100 and ab.kind == 'keywords' and 'delve' in ab.keywords for ab in ch.abilities)
        if (not exiling and not printed_delve) or not all(_exiles(scripts.define(ab, ch)) for ab in exiling):  # (-- linked exile (wave 30H) -- every exiling ability feeds the set, and each must be read: Rona's ruling)
            return None
        return d
    if ability.kind not in ("triggered", "activated", "static") or not _exiles(d):
        return d
    referring = [ab for ab in ch.abilities if ab.index != ability.index and (not borrowed or getattr(ab, "borrowed_origin", ())[:-1] == borrowed[:-1]) and (_REFERS.search(scripts.self_text(ab.text, ch.name)) or REFERS_PILE.search(ab.text) or "until you exile another card with ~" in scripts.self_text(ab.text, ch.name))]
    if not referring and not any(e.get("stop_on_linked_exile") for e in d.get("effects", [])):
        return d
    if d.get('static') == 'replace' and d.get('event') == 'draw' and (d.get('op') or {}).get('do') == 'body':
        return {**d, 'op': {**d['op'], 'effects': [{**e, 'link': True} if e.get('do') in ('exile', 'exile_top') else e
                                                  for e in d['op']['effects']]}}
    if d.get("static") == "exile_instead":  # -- linked exile (wave 30H) -- 607.2b: the replacement effect is the exiling half; replacements.py records what it exiles
        return {**d, "link": True}
    return {**d, "effects": [{**e, "link": True, **({"blind": True} if e.get("do") == "exile_hand_down" else {})} if e.get("do") in ("exile", "exile_top", "exile_until", "exile_on_resolve") or e.get("exile") or _picks_to_exile(e) else e
                                     for e in d["effects"]]}


# -- resolution memory (wave 22D) -- 607.2a: a referring ability that does more than return / put the cards ("the exiled card's owner
# creates an X/X token, where X is the mana value of the exiled card": Skyclave Apparition, Hoarding Dragon, Unidentified Hovership)
# reads the linked cards through a leading pseudo-instruction ``linked_cards`` that binds them (as the objects they were put into
# exile as: their owner and mana value are the same wherever they have gone since, 608.2h), so the ordinary pronoun grammar
# ("the exiled card", "its owner", "that card's mana value") finds them. ``linked()`` is true while such an ability is read.
_STATE = threading.local()  # (per thread: games may parse cards concurrently)
_EXILES = re.compile(r"\bexiles?\b|\bexiling\b", re.IGNORECASE)


def linked() -> bool:
    return getattr(_STATE, "on", False)


@contextmanager
def reading(ability: Any, text: str) -> Iterator[None]:
    """While the ability (its text, ~ for itself) is read: does it only refer to what another ability exiled?"""
    _STATE.on = ability.kind in ("triggered", "activated") and _REFERS.search(text) is not None and _EXILES.search(text) is None
    try:
        yield
    finally:
        _STATE.on = False


def linked_cards(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind the cards the linked ability exiled (a token that was exiled has ceased to exist, 111.8: not found)."""
    if e.get("as"):
        found = [ObjectRef(card=cid, object_id=oid, zone=f"{plan.state.cards[cid].owner}:exile")
                 for oid in plan.rules.exiled_with.get(link_key(ctx), []) if (cid := oid.rsplit(".", 1)[0]) in plan.state.cards]
        context.refs(ctx)[e["as"]] = {"kind": "objects", "objects": [r.model_dump(mode="json") for r in found]}
    return True


def link_key(ctx: dict[str, Any]) -> str:
    source = ctx.get('source_object') or ''
    scope = ctx.get('borrowed_link_scope')
    return f'{source}|borrowed:{scope}' if source and scope else source


def borrowed_link_scope(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    ctx['borrowed_link_scope'] = e['scope']
    return True


PRIMITIVES = {"linked_cards": linked_cards, "borrowed_link_scope": borrowed_link_scope}


def record(plan: Plan, ctx: dict[str, Any], cards: list[str]) -> None:
    """The objects these cards became in exile, under the source object (as it is, or was: 608.2h)."""
    key = link_key(ctx)
    if not key:
        return
    kept = [oid for oid in plan.rules.exiled_with.get(key, []) if _in_exile(plan, oid)]
    now = [plan.oid(c) for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
    new_cards = [oid for oid in now if oid not in kept
                 and not plan.state.cards[oid.rsplit(".", 1)[0]].is_token]
    ctx.setdefault("exiled_now", []).extend(o.rsplit(".", 1)[0] for o in new_cards)
    if new_cards:
        # The stated duration says "you": a later controller's exile is a different player's action.
        plan.rules.permissions = [p for p in plan.rules.permissions
                                  if p.stop_on_linked_exile != key or p.player != ctx.get("controller")]
    plan.rules.exiled_with[key] = [*kept, *(o for o in now if o not in kept)]


def _in_exile(plan: Plan, oid: str) -> bool:
    cid = oid.rsplit(".", 1)[0]
    card = plan.state.cards.get(cid)
    return card is not None and card.zone.endswith(":exile") and plan.oid(cid) == oid


def cards(plan: Plan, ctx: dict[str, Any], who: str = WHO) -> list[str]:
    """The cards the linked ability exiled, while each is still that object in exile (400.7); only those of the kind
    "exiled_with:<selector>" names ("each creature card exiled with it")."""
    found = [oid.rsplit(".", 1)[0] for oid in plan.rules.exiled_with.get(link_key(ctx), []) if _in_exile(plan, oid)]
    if who == f"{WHO}:other":
        return [c for c in found if c not in ctx.get("exiled_now", [])]
    if ":" not in who:
        return found
    from app.rules import selectors

    sel = selectors.from_key(who.split(":", 1)[1])
    return [c for c in found if selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), ctx["controller"],
                                                  ctx.get("source_card"))]
