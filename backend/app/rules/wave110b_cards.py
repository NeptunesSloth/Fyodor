"""-- wave 110B -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly (plural names and "and/or" included) and nothing else; any other wording stays
unsupported. Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def firebending(line: str) -> int | None:
    """702.189a: N of the one "firebending N" piece of a keyword line ("Trample, firebending 4, haste"), else None."""
    pieces = [p.strip() for p in re.split(r"[,;]\s*", re.sub(r"\s*\([^()]*\)", "", line).strip().rstrip("."))]
    found = [re.fullmatch(r"firebending (\d+)", p.lower()) for p in pieces if p.lower().startswith("firebending")]
    return int(found[0][1]) if len(found) == 1 and found[0] else None


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Plague Reaver: "each other creature you control" is "all other creatures you control" (701.21a)
    "At the beginning of your end step, sacrifice each other creature you control.":
        "At the beginning of your end step, sacrifice all other creatures you control.",
    # Ran and Shaw: one object with a plural name (201.5); "Dragon and/or Lesson" is a card with either subtype
    "When Ran and Shaw enter, if you cast them and there are three or more Dragon and/or Lesson cards in your graveyard, create a token that's a copy "
    "of Ran and Shaw, except it's not legendary.":
        "When this creature enters, if you cast it and there are three or more Dragon or Lesson cards in your graveyard, create a token that's a copy "
        "of this creature, except it's not legendary.",
    # Longhorn Sharpshooter: "it" is the plotted card itself (a source of damage in exile, 120.1)
    "When this card becomes plotted, it deals 2 damage to any target.": "When this card becomes plotted, this creature deals 2 damage to any target.",
    # Prince of Thralls: "that opponent" is the opponent whose permanent went to the graveyard, as "that player"
    "Whenever a permanent an opponent controls is put into a graveyard, put that card onto the battlefield under your control unless that opponent pays 3 life.":
        "Whenever a permanent an opponent controls is put into a graveyard, put that card onto the battlefield under your control unless that player pays 3 life.",
}


def _swap_value(d: Def, old: Def, new: Def) -> Def:
    """The native definition with the one condition value ``old`` read as ``new``."""
    hit = [c for c in d["conditions"] if c.get("value") == old]
    assert len(hit) == 1
    return {**d, "conditions": [{**c, "value": new} if c is hit[0] else c for c in d["conditions"]]}


def _gated(n: int) -> Callable[[Def], Def]:
    """The one kicked gate (a promised gift is a kicked spell, 702.174k) covers the ``n`` instructions after it."""
    return lambda d: {**d, "effects": [{**e, "n": n} if e["do"] == "kicked_gate" else e for e in d["effects"]]}


def _reaver(d: Def) -> Def:
    return {**d, "effects": [{"do": "reaver110b"}]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # Perch Protection: all three instructions are conditional on the promised gift (608.2c: one sentence)
    "Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out, and until your next turn, "
    "your life total can't change and you gain protection from everything.":
        ("Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out. Until your next turn, "
         "your life total can't change. You gain protection from everything until your next turn.", _gated(3)),
    # Marvo: the clash he won (701.30d), as Entangling Trap's "if you won" reads it
    "Whenever you win a clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.":
        ("Whenever you clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.",
         lambda d: {**d, "if": {"clash_won100a": True}}),
    # Oath of Lim-Dul: one sacrifice-unless-discard for each 1 life lost (the event's amount), each time its own choice (608.2c)
    "Whenever you lose life, for each 1 life you lost, sacrifice a permanent other than this enchantment unless you discard a card.":
        ("Whenever you lose life, sacrifice a permanent other than this enchantment unless you discard a card.",
         lambda d: {**d, "effects": [{"do": "repeat", "n": {"event_amount": 1}, "span": len(d["effects"])}, *d["effects"]]}),
    # Plague Reaver: the chosen opponent's next upkeep returns the sacrificed card under that player's control (603.7, 110.2a)
    "Discard two cards, Sacrifice this creature: Choose target opponent. Return this creature to the battlefield under that player's control at the "
    "beginning of their next upkeep.":
        ("Discard two cards, Sacrifice this creature: Target opponent gains 1 life.", _reaver),
    # Divine Intervention: the effect states that the game is a draw (104.4c)
    "When you remove the last intervention counter from this enchantment, the game is a draw.":
        ("When the last intervention counter is removed from this enchantment, draw a card.",
         lambda d: {**d, "effects": [{"do": "draw_game110b"}]}),
    # Ozai: the mana a player would lose stays in the pool as red mana (614.1a, 500.4)
    "If you would lose unspent mana, that mana becomes red instead.":
        ("If you would lose unspent mana, that mana becomes colorless instead.", lambda d: {**d, "to": "R"}),
    # Ozai: unspent mana of any type, in the pool and in units with restrictions (106.4)
    "Ozai has flying and indestructible as long as you have six or more unspent mana.":
        ("Ozai has flying and indestructible as long as you have six or more cards in your hand.",
         lambda d: _swap_value(d, {"hand": "you"}, {"unspent": ""})),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(text)) is not None:
        native = scripts.define(replace(ability, text=built[0]), ch)
        return None if native is None else built[1](native)
    return None


_VINCENT = ('Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s '
            'control" and has the chosen base power and toughness.')
_TIER = re.compile(r"• (?P<label>[^—{}]+) — (?P<cost>(?:\{[^}]+\})+) — (?P<p>\d+)/(?P<t>\d+)\.")


def tiered(ch: Any, lines: list[Any]) -> Def | None:
    """Vincent's Limit Break (702.183a): the line above the tiers is the spell, each tier gives the base power and toughness it names (613.4b)."""
    from app.rules import scripts

    found = [_TIER.fullmatch(ab.text) for ab in lines[1:]]
    if len(lines) != 4 or lines[0].text != _VINCENT or None in found:
        return None
    modes = []
    for m in found:
        assert m is not None
        parts = [scripts.define(replace(lines[0], text=t), ch) for t in (
            'Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s control."',
            f"Until end of turn, target creature you control has base power and toughness {m['p']}/{m['t']}.")]
        if None in parts or [d["target"] for d in parts if d] != [parts[0]["target"]] * 2:  # type: ignore[index]
            return None
        assert parts[0] is not None and parts[1] is not None
        modes.append({"text": f"{m['label']} — {m['cost']} — {m['p']}/{m['t']}.", "effects": [*parts[0]["effects"], *parts[1]["effects"]],
                      "target": parts[0]["target"], "cost": m["cost"]})
    return {"kind": "spell", "effects": [], "target": None, "modes": modes, "modal": {"min": 1, "max": 1, "repeat": False, "condition": None}}


def draw_game(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """104.4c: "the game is a draw" (a Commander game does not use the limited range of influence option, 104.4e)."""
    plan.rules.draw_reason = "An effect states that the game is a draw (104.4c)"
    plan.rules.priority = None
    plan.rules.decision = None
    plan.note("The game is a draw (104.4c)")
    return False


def reaver(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Plague Reaver: delayed trigger (603.7a) at the chosen opponent's next upkeep returns the sacrificed card (still the same object, 603.7c) to the
    battlefield under that opponent's control (110.2a)."""
    from app.game.rules_state import DelayedTrigger
    from app.rules import context
    from app.rules.effects import _players

    who = _players(plan, ctx, "target")
    card = ctx.get("source_card")
    if len(who) != 1 or card is None or plan.state.cards[card].zone.endswith(":battlefield"):
        return True
    refs: dict[str, Any] = {}
    context.bind_objects(plan, {"refs": refs}, "reaver", [card])
    context.bind_players({"refs": refs}, "opp", who)
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=card, source_object=ctx.get("source_object"), name=ctx.get("name") or "",
        when={"kind": "step", "step": "upkeep", "whose": "payer", "player": who[0]},
        effects=[{"do": "return_card", "who": "ref:reaver", "to": "battlefield", "tapped": False, "under": "ref:opp"}], refs=refs,
        turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=plan.rules.step_serial))
    plan.note(f"{ctx.get('name')} will return at {who[0]}'s next upkeep")
    return True


PRIMITIVES: dict[str, Any] = {"draw_game110b": draw_game, "reaver110b": reaver}
