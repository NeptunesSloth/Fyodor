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
* "put into a/your/their graveyard" / "that died": the objects whose new object is in a graveyard
  ("your": the controller's) as the instruction finished (700.4: "dies" is battlefield → graveyard).
* The qualifier is read from the object as it last existed where it was for a permanent ("nontoken
  creature destroyed this way", "creatures you controlled": 608.2h, its last known information) and
  from the card where it went for a card ("creature card milled this way": 701.17c, 400.7j).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

# The verbs, each with the recording effects' verbs (scripts._RECORDING) that it may name.
_VERBS = {"destroyed": ("destroyed",), "exiled": ("exiled",), "sacrificed": ("sacrificed",),
          "discarded": ("discarded",), "milled": ("milled",), "returned": ("returned",), "your_hand": ("returned",),
          "graveyard": ("destroyed", "sacrificed", "milled", "discarded"), "your_graveyard": ("milled", "discarded"),
          "died": ("destroyed", "sacrificed"), "tapped": ("tapped",)}
_PHRASE = re.compile(
    r"^(?P<what>.+?) (?:(?P<ctl>you controlled|they controlled) )?(?:that (?:was|were) |who )?"
    r"(?P<verb>destroyed|exiled|sacrificed|discarded|milled|tapped|returned to (?:your|its owner's|their owner's|their owners') hands?"
    r"|put into (?P<gy>a|your|their|its owner's|that player's|their owners') graveyards?|died|that died) this way$")
_NOUN_ONLY = re.compile(r"^(?:cards?)$")
_GREATEST = re.compile(r"^the greatest number of cards a player (?P<verb>discarded|milled) this way$")


def parse(phrase: str) -> dict[str, Any] | None:
    """"creature destroyed this way" / "nonland card discarded this way" / "creature card put into a
    graveyard this way" / "creatures you controlled that were destroyed this way" → the placeholder,
    or None (not this grammar, or a form that isn't read: a player-relative "they controlled")."""
    p = phrase.strip()
    most = _GREATEST.match(p)
    if most is not None:  # Windfall: "the greatest number of cards a player discarded this way" (each player's own)
        return {"this_way": most["verb"], "of": None, "max_by": "owner"}
    p = re.sub(r"^the number of ", "", p)
    m = _PHRASE.match(p)
    if m is None:
        return None
    if m["ctl"] == "they controlled":  # (Deadly Tempest: each player's own count; not read)
        return None
    what = m["what"].strip()
    what = re.sub(r" that$", "", what)  # ("creature that died this way")
    verb = m["verb"]
    if verb.startswith("returned"):
        kind = "your_hand" if verb.startswith("returned to your") else "returned"
    elif verb.startswith("put into"):
        kind = "your_graveyard" if m["gy"] == "your" else "graveyard"
    elif verb in ("died", "that died"):
        kind = "died"
    else:
        kind = verb
    of: str | None = None
    if not _NOUN_ONLY.match(what):
        if m["ctl"] == "you controlled":
            what = f"{what} you control"
        sel = selectors.parse(what)
        if sel is None or sel.player is not None or sel.other or sel.zones not in ((), ("battlefield",)):
            return None
        of = sel.key()
    elif m["ctl"]:
        return None
    return {"this_way": kind, "of": of}


_IF_PASSIVE = re.compile(r"^(?:a|an|at least one|one or more|any) (?P<what>.+?) (?:is|was|were|are) (?P<rest>.+ this way)$")
_IF_THAT = re.compile(r"^that (?:creature|permanent) (?:(?:was|is) (?P<verb>destroyed|sacrificed|exiled)|(?P<dies>dies|died)) this way$")
_IF_YOU = re.compile(r"^you (?P<verb>sacrificed|exiled|discarded|milled|destroyed) (?:a|an|one or more) (?P<what>.+?) this way$")


def condition(text: str) -> dict[str, Any] | None:
    """"If a creature is destroyed this way, …" / "If a land card was milled this way, …" / "If that creature
    dies this way, …" / "If you sacrificed a creature this way, …": at least one object counted (a
    ``conditions`` quantity, judged as the resolution reaches it: 608.2c)."""
    m = _IF_PASSIVE.match(text)
    phrase = f"{m['what']} {m['rest']}" if m else None
    if m is None and (m := _IF_THAT.match(text)) is not None:
        phrase = "permanent " + ("died this way" if m["dies"] else f"{m['verb']} this way")
    if phrase is None and (m := _IF_YOU.match(text)) is not None:
        # (you sacrifice only what you control, 701.21a: "Each player sacrifices a creature. If you sacrificed a
        # creature this way" counts yours; an exile or destruction of your ability is yours; a player mills and
        # discards their own cards, so "you milled / discarded" after "each player …" isn't read)
        if m["verb"] in ("milled", "discarded"):
            return None
        ctl = " you controlled" if m["verb"] == "sacrificed" else ""
        phrase = f"{m['what']}{ctl} {m['verb']} this way"
    v = parse(phrase) if phrase is not None else None
    return {"value": v, "op": ">=", "n": 1} if v is not None else None


def verbs(kind: str) -> tuple[str, ...]:
    return _VERBS[kind]


def bind(v: Any, find: Any) -> Any:
    """Rewrite every placeholder in a value with the binding ``find(kinds)`` names (None: unbound →
    raises LookupError, the line stays manual)."""
    if isinstance(v, list):
        return [bind(x, find) for x in v]
    if not isinstance(v, dict):
        return v
    if "this_way" in v and "ref_count" not in v:
        name = find(_VERBS[v["this_way"]])
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
    if kind == "tapped":  # (tap_choice binds exactly the permanents it tapped)
        return True
    old_card = plan.state.cards.get(was["card"])
    moved = old_card is None or plan.oid(old_card) != was["object_id"] or new["object_id"] != was["object_id"]
    if not moved:
        return False
    dest = (new.get("zone") or "").rsplit(":", 1)[-1] if new["object_id"] != was["object_id"] else None
    if kind in ("returned", "your_hand"):  # (a hand is hidden: only the card's zone now tells where it went)
        return old_card is not None and old_card.zone == f"{you}:hand" if kind == "your_hand" else \
            old_card is not None and old_card.zone.endswith(":hand")
    if kind == "exiled":
        return dest == "exile"
    if kind in ("graveyard", "your_graveyard"):
        return dest == "graveyard"
    if kind == "died":
        return dest == "graveyard" and (was.get("zone") or "").endswith("battlefield")
    return True


def count(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """How many of the objects the bound instruction acted on it actually did this to (and that
    match the qualifier): see the module docstring. ``max_by: "owner"``: the most any one player had (a
    discarded or milled card is its owner's: 701.9a, 701.17a)."""
    found = _matched(plan, ctx, v)
    if v.get("max_by") == "owner":
        owners: dict[str, int] = {}
        for new, _ in found:
            card = plan.state.cards.get(new["card"])
            if card is not None:
                owners[card.owner] = owners.get(card.owner, 0) + 1
        return max(owners.values(), default=0)
    return len(found)


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
            (card.owner if card is not None else None)
        if pid is not None:
            out[pid] = out.get(pid, 0) + 1
    return out


def _still_there(plan: Plan, was: dict[str, Any]) -> tuple[Any, Any] | None:
    """The object, if it is still that object on the battlefield (a permanent this effect tapped)."""
    card = plan.state.cards.get(was["card"])
    if card is None or plan.oid(card) != was["object_id"] or not card.zone.endswith(":battlefield"):
        return None
    return card, plan.ch(card)


def _matched(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    from app.game.rules_state import ObjectRef
    from app.rules import context
    from app.rules.triggers import _snapshot_card  # (triggers imports effects, which imports values → this)

    b = (ctx.get("refs") or {}).get(v["ref_count"]) or {}
    news = b.get("objects") or []
    wases = b.get("was") or news
    you = ctx["controller"]
    sel = selectors.from_key(v["of"]) if v.get("of") else None
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for new, was in zip(news, wases, strict=False):
        if not _happened(plan, v["this_way"], new, was, you):
            continue
        if v["this_way"] == "your_graveyard" and not (new.get("zone") or "").startswith(f"{you}:"):
            continue
        if sel is not None:
            if sel.card:  # a card: where it went (a public zone, 400.7j / 701.17c)
                card = plan.state.cards.get(new["card"])
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
                if not selectors.matches(plan, sel, card, ch, you):
                    continue
        out.append((new, was))
    return out


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
