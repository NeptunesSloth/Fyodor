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
    # Campsite Cuisine: the enchantment itself is no creature, so "a legendary creature you control" is another one; X Foods are "any number of Foods" and
    # X targets are "that many" (the number sacrificed, set as the reflexive trigger is put on the stack, 603.12)
    "Whenever this enchantment or a legendary creature you control enters, create a Food token.":
        "Whenever this enchantment or another legendary creature you control enters, create a Food token.",
    "Whenever you attack, you may sacrifice X Foods. When you do, up to X target attacking creatures each get +3/+3 and gain trample and indestructible "
    "until end of turn.":
        "Whenever you attack, you may sacrifice any number of Foods. When you do, up to that many target attacking creatures each get +3/+3 and gain "
        "trample and indestructible until end of turn.",
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


def _quake(d: Def) -> Def:
    """Quakebringer (113.6b-style zones): works on the battlefield, or from the graveyard while its controller controls a Giant (603.4 as it triggers)."""
    here = {"object": "self", "test": "on_battlefield"}
    cond = {"any": [here, d["if"]]}
    return {**d, "if": cond, "gy_watch": True, "gy_bf110b": True, "effects": [{**e, "cond": cond} if e["do"] == "only_if" else e for e in d["effects"]]}


def _skyguard(d: Def) -> Def:
    return {**d, "if": {"skyguard110b": True},
            "effects": [{**e, "duration": "end_of_combat"} if e["do"] == "prevent_all" else e for e in d["effects"]]}


def skyguard_holds(plan: Any, ctx: dict[str, Any]) -> bool:
    """Suppressor Skyguard: the attacking player (the active player, 508.1) has an opponent other than the Skyguard's controller who is not being
    attacked (508.3d: a player is attacked by a creature attacking them or a planeswalker or battle they control)."""
    me, atk = ctx["controller"], plan.active
    attacked = set()
    for c in plan.state.cards.values():
        if c.attacking is not None and c.controller == atk:
            attacked.add(c.attacking.id if c.attacking.kind == "player" else plan.state.cards[c.attacking.id].controller)
    return any(p != atk and p != me and not plan.state.players[p].left and p not in attacked for p in plan.state.players)


def _still_here(d: Def) -> Def:
    """The delayed trigger has an intervening "if" this creature is still on the battlefield (603.4, 603.7)."""
    hit = [e for e in d["effects"] if e["do"] == "delayed"]
    assert len(hit) == 1
    hit[0]["when"] = {**hit[0]["when"], "if": {"object": "self", "test": "on_battlefield"}}
    return d


def _lich(d: Def) -> Def:
    """Lich's Mastery: one exile per life lost (608.2c), of a permanent, a card in hand or a card in the graveyard."""
    return {**d, "effects": [{"do": "repeat", "n": {"event_amount": 1}, "span": 1}, {"do": "exile_own110b"}]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # The Chain Veil: each planeswalker you control may be activated one more time this turn (606.3 as though none were activated)
    "{4}, {T}: For each planeswalker you control, you may activate one of its loyalty abilities once this turn as though none of its loyalty abilities "
    "have been activated this turn.":
        ("{4}, {T}: Draw a card.", lambda d: {**d, "effects": [{"do": "veil110b"}]}),
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
    # Quakebringer: the trigger works from the battlefield, or from the graveyard with a Giant under your control
    "At the beginning of your upkeep, Quakebringer deals 2 damage to each opponent. This ability triggers only if Quakebringer is on the battlefield or "
    "if Quakebringer is in your graveyard and you control a Giant.":
        ("At the beginning of your upkeep, if this card is in your graveyard and you control a Giant, this creature deals 2 damage to each opponent.",
         _quake),
    # Suppressor Skyguard: prevention lasts through this combat only (500.5); the attacker needs another opponent nobody attacks
    "Whenever a player attacks you, if that player has another opponent who isn't being attacked, prevent all combat damage that would be dealt to you "
    "this combat.":
        ("Whenever a player attacks you, prevent all combat damage that would be dealt to you this turn.", _skyguard),
    # Shirei: the delayed return happens only if Shirei is still on the battlefield when the next end step begins
    "Whenever a creature with power 1 or less is put into your graveyard from the battlefield, you may return that card to the battlefield at the "
    "beginning of the next end step if Shirei is still on the battlefield.":
        ("Whenever a creature with power 1 or less is put into your graveyard from the battlefield, you may return that card to the battlefield at the "
         "beginning of the next end step.", _still_here),
    # Lich's Mastery: for each 1 life you lost, exile a permanent you control or a card from your hand or graveyard
    "Whenever you lose life, for each 1 life you lost, exile a permanent you control or a card from your hand or graveyard.":
        ("Whenever you lose life, exile a permanent you control.", _lich),
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


def veil(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The Chain Veil: every planeswalker its controller controls gets one more loyalty activation this turn (the "twice" allowance, cast_limits.loyalty_rule)."""
    for c in plan.state.cards.values():
        if c.controller == ctx["controller"] and c.zone.endswith(":battlefield") and "Planeswalker" in plan.ch(c).types:
            plan.rules.once_per_turn[f"loyalty_veil110b:{c.id}"] = plan.state.turn.number
    return True


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


def exile_own(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Exile a permanent you control or a card from your hand or graveyard": the controller picks one as it resolves (608.2d); none: nothing."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me = ctx["controller"]
    mine = [c for c in plan.state.cards.values() if (c.zone == f"{me}:hand" or c.zone == f"{me}:graveyard" and c.owner == me)
            or (c.zone.endswith(":battlefield") and c.controller == me)]
    if not mine:
        return True
    decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Exile'}: exile a permanent you control or a card from your hand or graveyard",
           options=[DecisionOption(id=c.id, label=c.name or "Card", card_id=c.id) for c in mine], min_choices=1, max_choices=1,
           resume={"step": "exile_own110b", "ctx": ctx})
    return False


def resume_exile_own(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    ok = {o.id for o in d.options}
    if len(chosen) != 1 or chosen[0] not in ok:
        raise ActionError("Choose one of the cards offered")
    plan.note(f"{plan.name(d.player)} exiles {plan.state.cards[chosen[0]].name}", actor=d.player)
    effects.exile_cards(plan, ctx, {}, chosen)
    effects.continue_effects(plan, ctx)


RESUME: dict[str, Any] = {"exile_own110b": resume_exile_own}
PRIMITIVES: dict[str, Any] = {"draw_game110b": draw_game, "reaver110b": reaver, "veil110b": veil, "exile_own110b": exile_own}
