"""Role tokens (wave 6C): "Create a Monster Role token attached to target creature you control."

A Role is a colorless Aura Role enchantment token with enchant creature (111.10j-r, 303.7; the glossary's "Role").
Creating one "attached to" an object puts it onto the battlefield attached to that object (303.4f: the effect names
what it enchants); if that object can't legally be enchanted by it, or there is none ("up to one target creature" with
no target chosen, or the target gone), the token isn't created (303.4i). A token-doubling replacement (614.16) makes
more of them, each attached to the same creature. 303.7a / 704.5z: if a permanent has more than one Role controlled by
the same player attached to it, each of them except the one with the most recent timestamp is put into its owner's
graveyard (a state-based action: ``stale_roles``).

Read for one object only ("it", "that creature", a single target): "For each of those creatures, create a Role token
attached to it" stays manual.
"""

from __future__ import annotations

import re
from dataclasses import replace as dc_replace
from functools import cache
from typing import Any

from app.game.state import CardInstance
from app.rules.plan import Plan

Effects = list[dict[str, Any]]

# 111.10j-r: each Role's name and rules text (with its enchant creature ability)
ROLES: dict[str, str] = {
    "Cursed": "Enchanted creature has base power and toughness 1/1.",
    "Monster": "Enchanted creature gets +1/+1 and has trample.",
    "Royal": "Enchanted creature gets +1/+1 and has ward {1}.",
    "Sorcerer": "Enchanted creature gets +1/+1 and has \"Whenever this creature attacks, scry 1.\"",
    "Virtuous": "Enchanted creature gets +1/+1 for each enchantment you control.",
    # (111.10q says "this token": written as the object's own type, how the templates know it means itself — the
    # token is that enchantment, so this is the same ability)
    "Wicked": "Enchanted creature gets +1/+1.\n"
              "When this enchantment is put into a graveyard from the battlefield, each opponent loses 1 life.",
    "Young Hero": "Enchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, "
                  "put a +1/+1 counter on it.\"",
}
TYPE_LINE = "Token Enchantment — Aura Role"
# -- block events (wave 53C) -- an Aura token that is no Role, made attached to a target: Scriv, the Obligator's "a white Aura enchantment token named Contract attached to target creature an
# opponent controls. The token has enchant creature and "…"" (read as "a Contract Aura token", block_events.rewrite): its colors and its abilities after "Enchant creature"
NAMED: dict[str, tuple[list[str], str]] = {
    "Contract": (["W"], "Whenever enchanted creature attacks, it gets +2/+0 until end of turn if it's attacking one of your opponents. Otherwise, its controller loses 2 life."),
    # -- named Aura tokens (wave 110D) -- The Rani, Preston Garvey (a text starting "Enchant " carries its own enchant line; wave110d_named.py reads the Oracle sentences)
    "Mark of the Rani": (["R"], "Enchanted creature gets +2/+2 and is goaded."),
    "Mask": (["W"], "Enchant permanent\numbra armor"),  # (wave 110A) Estrid, the Masked
    "Settlement": (["G"], 'Enchant land\nEnchanted land has "{T}: Add one mana of any color."'),
}
_CLAUSE = re.compile(rf"create an? (?:(?P<role>{'|'.join(ROLES)}) Role|(?P<named>{'|'.join(NAMED)}) Aura) token attached to (?P<o>.+)")


def token(role: str) -> dict[str, Any]:
    """The token spec of a Role (111.10j-r: named after the Role, colorless) or of a named Aura token."""
    if role in NAMED:
        colors, text = NAMED[role]
        return {"name": role, "power": None, "toughness": None, "colors": colors, "type_line": "Token Enchantment — Aura", "text": text if text.startswith("Enchant ") else f"Enchant creature\n{text}"}
    return {"name": role, "power": None, "toughness": None, "colors": [], "type_line": TYPE_LINE,
            "text": f"Enchant creature\n{ROLES[role]}"}


def clause(text: str) -> tuple[Effects, Any] | None:
    """"create a <Role> Role token attached to <one object>" → a ``create_role`` effect, or None."""
    m = _CLAUSE.fullmatch(text)
    if m is None or not supported(m["role"] or m["named"]):
        return None
    from app.rules import language

    try:
        kind, key, group = language.ref(m["o"])
    except language._Fail:
        return None
    if kind not in ("target", "it", "self") or (kind == "it" and key):
        return None
    if group is not None and (group.get("max", 1) != 1):
        return None  # (one object: "up to one" / one target)
    return [{"do": "create_role", "role": m["role"] or m["named"], "who": language._who(kind, key)}], language._one(group)


@cache
def supported(role: str) -> bool:
    """Does the engine carry out every ability of this Role? (A Role whose abilities it doesn't — the Young Hero's
    granted trigger with an intervening "if" — keeps the instruction manual: never a token that half works.)"""
    from app.rules import coverage

    return coverage.of_characteristics(_characteristics(role)).level == "FULL"


def _characteristics(role: str) -> Any:
    from app.rules.characteristics import printed_from_data

    spec = token(role)
    return printed_from_data({"id": f"role:{role}", "name": spec["name"], "type_line": spec["type_line"],
                              "oracle_text": spec["text"], "colors": spec["colors"]})  # (cached per "printing": one per Role)


def _host_ok(plan: Plan, card: CardInstance, role_ch: Any) -> bool:
    """Could the Role enchant this permanent as it enters (303.4i)? Enchant creature (702.5a), and protection
    (702.16c: it can't be enchanted by what it has protection from). Hexproof doesn't matter: nothing targets it."""
    from app.rules import protection

    if not card.zone.endswith(":battlefield") or not plan.in_game(card):
        return False
    hch = plan.ch(card)
    kind_ok = True if role_ch.name == "Mask" else "Land" in hch.types if role_ch.name == "Settlement" else hch.is_creature  # (wave 110D: "enchant land")
    return kind_ok and not protection.protected_from(hch, role_ch)


def create_role(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Create the Role attached to the object (see the module docstring)."""
    from app.rules import attachments, context, effects, replace

    role_ch = dc_replace(_characteristics(e["role"]), object_controller=ctx["controller"], object_owner=ctx["controller"])
    hosts = [c for c in effects._cards(plan, ctx, e["who"]) if _host_ok(plan, plan.state.cards[c], role_ch)]
    name = e.get("did")  # -- block events (wave 53C) -- "Create a Monster Role token attached to target creature you control. When you do, …" (603.12): done if a Role is attached to it
    if len(hosts) != 1:
        plan.note(f"No {e['role']} {'Aura ' if e['role'] in NAMED else 'Role '}token is created: nothing it could enchant (303.4i)", actor=ctx["controller"])
        if name:
            context.refs(ctx)[name] = {"kind": "probe", "attached": {}}
        return True
    host = hosts[0]
    source = ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None
    made = replace.create_tokens(plan, ctx["controller"], token(e["role"]), 1, source=source, ctx=ctx,
                                 then=replace.rerun_then(ctx, e))
    if made is None:
        return False  # (the creating player orders replacement effects first: this runs again, 616.1)
    for tid in made:  # (all of them, if a replacement effect made more: each enters attached to it, 303.4f)
        attachments.attach(plan, tid, host, ctx["controller"])
    if name:
        context.refs(ctx)[name] = {"kind": "probe", "attached": {tid: host for tid in made}}
    return True


def stale_roles(plan: Plan) -> list[CardInstance]:
    """704.5z: the Roles to put into their owners' graveyards — of the Roles one player controls attached to one
    permanent, all but the one with the most recent timestamp (613.7e: an Aura's timestamp is from when it became
    attached)."""
    from app.rules import layers

    groups: dict[tuple[str, str], list[CardInstance]] = {}
    for card in plan.state.cards.values():
        if not card.zone.endswith(":battlefield") or not card.attached_to or not plan.in_game(card):
            continue
        ch = plan.ch(card)
        if "Role" in ch.subtypes and "Aura" in ch.subtypes:
            groups.setdefault((card.attached_to, card.controller), []).append(card)
    out: list[CardInstance] = []
    for cards in groups.values():
        if len(cards) > 1:
            newest = max(cards, key=lambda c: (layers.timestamp(plan.state, c.id), c.id))
            out += [c for c in cards if c is not newest]
    return out


PRIMITIVES = {"create_role": create_role}
