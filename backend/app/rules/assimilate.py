"""-- Star Trek mechanics (wave 112T) -- assimilate, a keyword action from the Star Trek release notes
(https://magic.wizards.com/en/news/feature/star-trek-release-notes). The Comprehensive Rules (2026-09-25) don't define it yet.
# Star Trek release notes (2026-11): re-check against the CR when it defines assimilate

* "The assimilate keyword action gives you control of a creature or puts a creature card onto the battlefield under your control. Either
  way, a +1/+1 counter is put on that creature, and it becomes a Borg artifact creature and loses its other creature types." The
  reminder texts: "(Gain control of it and put a +1/+1 counter on it. It's a Borg artifact creature and loses all other creature types.)"
  and "(Put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature …)".
* "The assimilated creature or creature card loses any other creature types it has, but it keeps any other supertypes, types, and
  subtypes it has" (Dryad Arbor: "Artifact Land Creature – Forest Borg"): a layer 4 effect (613.1d) setting the creature types to Borg
  and adding artifact and creature (205.1b), with no duration (611.2a); control is layer 2 (613.1b), also for good.
* A card: it enters with the counter (122.6) and as a Borg artifact creature (the entry characteristics of "It's a … " riders,
  ``entry_characteristics``, as Grave Betrayal's "It's a black Zombie in addition to its other colors and types"); a permanent: control,
  then the counter, then the type change, as the reminder text orders them (608.2c).
* "the Borg assimilated with this Saga" (The Best of Both Worlds III, 607.2a): what that object assimilated, still the same object on the
  battlefield (400.7), "even if it's no longer a Borg, no longer a creature, or no longer under your control", and all of them when it
  assimilated more than one (its rulings). ``RulesState.assimilated112t``: source object -> assimilated objects.

The wordings are read by rewriting the assimilate sentence as the reminder text says and reading that with the ordinary grammar
(``parse``): "assimilate target … card …" → "put … onto the battlefield under your control with a +1/+1 counter on it", "assimilate
target creature …" → "gain control of … Put a +1/+1 counter on it.", "assimilate a creature card exiled with it" → the choice of one such
card, then the put; "Assimilate that card." after "… exiles cards … until they exile a creature card" → the card found; Gift of
Perfection's "Assimilate one of the creature cards revealed this way" (several opponents' reveals) → ``gift112t``.
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import context

BECOME = {"do": "become", "types": ["Artifact", "Creature"], "retain": True, "creature_types": ["Borg"], "duration": "permanent",
          "label": "a Borg artifact creature"}
_PUT = re.compile(r"^(?P<pre>For each opponent, )?[Aa]ssimilate (?P<obj>(?:up to one )?target [^.]*?\bcard\b[^.]*)\.$")
_GAIN = re.compile(r"^[Aa]ssimilate (?P<obj>target [^.]*?(?:creature|permanent)[^.]*)\.$")
_LINKED = re.compile(r"^[Aa]ssimilate (?P<obj>an? [a-z ]*?card exiled with (?:it|~|this [a-z]+))\.(?: If you can't, (?P<rest>[^.]+\.))?$")
_FOUND = re.compile(r"^(?P<head>[Tt]arget opponent exiles cards from the top of their library until they exile an? [a-z ]+? card\.) Assimilate that card\. "
                    r"They put the rest on the bottom in a random order\.$")
GIFT = ("Each opponent reveals cards from the top of their library until they reveal a creature card. Assimilate one of the creature cards "
        "revealed this way. Then each opponent puts the other cards they revealed this way on the bottom of their library in a random order.")
_BORG_WITH = re.compile(r"^Exile the Borg assimilated with (?:this \w+|~), then return (?:it|them) to the battlefield under (?:its|their) owners?'s? control\.$")
_AS0, _AS1, _DID = "asm112t0", "asm112t1", "asm112t"


def _sentences(body: str) -> list[str]:
    return re.findall(r"[^.]+\.", body.strip())


def _after_put(as_: str) -> list[dict[str, Any]]:
    """The type change (hoisted into the card's entry by ``entry_characteristics.prepare_return``) and the link."""
    return [{**BECOME, "who": f"ref:{as_}", "entry_as": True}, {"do": "link112t", "who": f"ref:{as_}"}]


def _put_from(who: str) -> list[dict[str, Any]]:
    return [{"do": "return_card", "to": "battlefield", "tapped": False, "under": "you", "counter": "+1/+1", "who": who, "as": _AS1},
            *_after_put(_AS1)]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip()
    if "ssimilate" not in text:
        return None
    if text == GIFT:
        return [{"do": "gift112t"}], None, False
    if (m := _FOUND.fullmatch(text)) is not None:  # "Assimilate that card." — the card the exile stopped at (ctx["found"])
        native = scripts.parse_effects(f"{m['head'][:1].upper()}{m['head'][1:]} You may cast that card without paying its mana cost. Then that player puts the exiled cards that "
                                       "weren't cast this way on the bottom of their library in a random order.")
        if native is None or [e.get("do") for e in native[0]] != ["exile_top", "free_cast", "rest_exiled"] or native[0][1].get("zone") != "found":
            return None
        return [native[0][0], {"do": "found112t", "as": _AS0}, *_put_from(f"ref:{_AS0}"), native[0][2]], native[1], native[2]
    sentences = _sentences(text)
    if len(sentences) != 1 and not _LINKED.fullmatch(text):
        return None
    if (m := _LINKED.fullmatch(text)) is not None:  # "assimilate a creature card exiled with it[. If you can't, …]"
        native = scripts.parse_effects(f"Put {m['obj'].replace(' with it', ' with ~')} onto the battlefield under your control.")
        if native is None or len(native[0]) != 1 or native[0][0].get("do") != "return_choice" or native[1] is not None:
            return None
        choose = {**native[0][0], "to": "choose", "as": _AS0, "did": _DID}
        choose.pop("tapped", None)
        choose.pop("under", None)
        out = [choose, *_put_from(f"ref:{_AS0}")]
        if not m["rest"]:
            return out, None, False
        rest = scripts.parse_effects(m["rest"][:1].upper() + m["rest"][1:])
        if rest is None or rest[2]:
            return None
        linked = [{**e, "link": True} if e.get("do") == "exile" else e for e in rest[0]]  # (607.2a: what it exiles is "exiled with it")
        return [*out, {"do": "only_if", "cond": {"succeeded": _DID, "negate": True}, "skip": len(linked)}, *linked], rest[1], False
    if (m := _PUT.fullmatch(text)) is not None:
        native = scripts.parse_effects(f"{m['pre'] or ''}{'p' if m['pre'] else 'P'}ut {m['obj']} onto the battlefield under your control with a +1/+1 counter on it.")
        if native is None or len(native[0]) != 1 or native[0][0].get("do") != "return_card" or native[0][0].get("counter") != "+1/+1":
            return None
        return [{**native[0][0], "as": _AS1}, *_after_put(_AS1)], native[1], native[2]
    if (m := _GAIN.fullmatch(text)) is not None:
        native = scripts.parse_effects(f"Gain control of {m['obj']}. Put a +1/+1 counter on it.")
        if native is None or [e.get("do") for e in native[0]] != ["gain_control", "add_counters"]:
            return None
        who = native[0][0]["who"]
        return [*native[0], {**BECOME, "who": who}, {"do": "link112t", "who": who}], native[1], native[2]
    if (m := _BORG_WITH.fullmatch(text)) is not None:
        native = scripts.parse_effects("Exile target creature you control, then return it to the battlefield under its owner's control.")
        if native is None or [e.get("do") for e in native[0]] != ["blink"]:
            return None
        return [{"do": "linked112t", "as": _AS0}, {**native[0][0], "who": f"ref:{_AS0}"}], None, False
    return None


# -- resolution ------------------------------------------------------------------------------------------------------------------------
def link(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Record what was assimilated as linked to the source object (607.2a), as it is now on the battlefield."""
    from app.rules.effects import _cards

    src = ctx.get("source_object")
    done = [plan.oid(c) for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if src and done:
        plan.rules.assimilated112t[src] = [*plan.rules.assimilated112t.get(src, []), *done]
    return True


def linked(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind "the Borg assimilated with this <source>": each still on the battlefield as the same object (400.7), whatever it is now."""
    oids = set(plan.rules.assimilated112t.get(ctx.get("source_object") or "", []))
    cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) in oids]
    context.bind_objects(plan, ctx, e["as"], cards)
    return True


def found(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind the card an "until they exile a … card" instruction stopped at, while it is still in exile (400.7)."""
    cid = ctx.get("found")
    card = plan.state.cards.get(cid or "")
    context.bind_objects(plan, ctx, e["as"], [cid] if card is not None and card.zone.endswith(":exile") else [])
    return True


def gift(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Gift of Perfection: each opponent (APNAP, 101.4) reveals from the top until a creature card (701.20a: they stay in the library); the
    controller chooses one of the creature cards revealed (608.2d) and assimilates it; then each opponent puts their other revealed cards on
    the bottom of their library in a random order."""
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _first_match, decide

    sel = "sel:" + '{"card":true,"types":["Creature"],"zones":[]}'
    revealed: dict[str, list[str]] = {}
    creatures: list[str] = []
    for pid in [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]:
        library = list(plan.state.zones.get(f"{pid}:library", []))
        at = _first_match(plan, ctx, library, sel, ctx["controller"])
        cards = library if at is None else library[:at + 1]
        if cards:
            plan.do({"type": "reveal", "card_ids": cards}, actor=pid)
        revealed[pid] = cards
        if at is not None:
            creatures.append(library[at])
    ctx["gift112t"] = revealed
    if len(creatures) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Gift of Perfection'}: choose a creature card to assimilate",
               options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name} ({plan.name(plan.state.cards[c].owner)})", card_id=c) for c in creatures],
               resume={"step": "gift112t", "ctx": ctx, "e": e})
        return False
    _gift_then(plan, ctx, creatures)
    return True


def _gift_then(plan: Any, ctx: dict[str, Any], chosen: list[str]) -> None:
    context.bind_objects(plan, ctx, _AS0, chosen)
    ctx["effects"][ctx["next"]:ctx["next"]] = [*_put_from(f"ref:{_AS0}"), {"do": "gift_rest112t", "chosen": chosen}]


def resume_gift(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    allowed = {c for cards in ctx["gift112t"].values() for c in cards}
    if len(chosen) != 1 or chosen[0] not in allowed:
        raise ValueError("not a revealed creature card")
    _gift_then(plan, ctx, chosen)
    continue_effects(plan, ctx)


def gift_rest(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import bottom_at_random

    for pid, cards in (ctx.get("gift112t") or {}).items():
        rest = [c for c in cards if c not in e["chosen"] and plan.state.cards[c].zone == f"{pid}:library"]
        if rest:
            bottom_at_random(plan, pid, rest)
    return True


PRIMITIVES = {"link112t": link, "linked112t": linked, "found112t": found, "gift112t": gift, "gift_rest112t": gift_rest}
RESUME = {"gift112t": resume_gift}


_OWN_POOL = re.compile(r"^(?P<head>(?:When|Whenever) [^,]+), (?P<body>assimilate an? [a-z ]*?card exiled with it\. If you can't, (?P<rest>[^.]+\.))$")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Borg Cube: one ability both assimilates a card exiled with it and, if it can't, exiles a creature — the set it reads accumulates what its
    own earlier resolutions exiled (607.2a; ``accumulating_link``), the target chosen as the trigger is put on the stack (603.3d)."""
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != "triggered" or ability.index >= 100 or (m := _OWN_POOL.fullmatch(scripts.self_text(ability.text, ch.name))) is None:
        return None
    base = scripts.define(replace(ability, text=f"{m['head']}, {m['rest']}"), ch)
    body = parse(m["body"][:1].upper() + m["body"][1:])
    if base is None or body is None or base.get("kind") != "triggered":
        return None
    return {**base, "effects": body[0], "accumulating_link": True}
