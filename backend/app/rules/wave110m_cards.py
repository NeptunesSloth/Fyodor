"""-- wave 110M -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "When one or more of your opponents are dealt combat damage during your turn, draw two cards. If your library has no cards in it, you win the game. "
    "Fblthp's owner shuffles him into their library.":
        ("When one or more of your opponents are dealt combat damage during your turn, draw two cards. If your library has no cards in it, you win the game. "
         "Fblthp's owner shuffles it into their library.", lambda d: d),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


_MEDDLE = "If target spell has only one target and that target is a creature, change that spell's target to another creature."


def parse(body: str) -> Any:
    """Spell bodies. Meddle: any spell may be targeted; whether it has one target and that target is a creature is judged as this resolves (115.7a, 608.2b)."""
    from app.rules import scripts

    if body.strip() == _MEDDLE:
        parsed = scripts.parse_effects("Counter target spell.")
        assert parsed is not None
        _, target, optional = parsed
        return [{"do": "change_target", "who": "target", "must": "creature", "creature110m": True}], target, optional
    if body.strip() == _DAMNATIONS:
        parsed = scripts.parse_effects("Target opponent loses 1 life.")
        assert parsed is not None
        return [{"do": "damnations110m"}], parsed[1], False
    if body.strip() in (_REVERSAL, f"{_REVERSAL} Exile ~."):  # (the spell's own second sentence, "Exile Stunning Reversal.", moves it out of the graveyard's way)
        return [{"do": "lose_shield110m"}, *([{"do": "exile", "who": "self"}] if body.strip().endswith("Exile ~.") else [])], None, False
    return None


def _crown(d: Def) -> Def:
    """Crown of Convergence: only the creatures that share a color with the top card get the bonus; with no top card the condition fails (nothing)."""
    from app.rules import selectors

    sel = selectors.from_key(d["who"])
    return {**d, "who": replace(sel, extras=(*sel.extras, "top_color110m")).key()}


_BUILD["As long as the top card of your library is a creature card, creatures you control that share a color with that card get +1/+1."] = (
    "As long as the top card of your library is a creature card, creatures you control get +1/+1.", _crown)
_BUILD["{G}{W}: Put the top card of your library on the bottom of your library."] = (
    "{G}{W}: Draw a card.", lambda d: {**d, "effects": [{"do": "top_to_bottom110m", "who": "you"}]})


def top_to_bottom(plan: Any, ctx: Def, e: Def) -> bool:
    """Put the top card of the controller's library on the bottom of it (no one learns what it was; an empty library: nothing)."""
    pid = ctx["controller"]
    if library := plan.state.zones.get(f"{pid}:library", []):
        plan.do({"type": "move", "card_ids": [library[0]], "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
        plan.note(f"{plan.name(pid)} puts the top card of their library on the bottom", actor=pid)
    return True


_FACES = ("Whenever a creature dies, tap all untapped creatures that share a creature type with it or untap all tapped creatures that share a creature type with it.")
_BUILD[_FACES] = ("Whenever a creature dies, draw a card.", lambda d: {**d, "effects": [{"do": "faces110m"}]})


def faces(plan: Any, ctx: Def, e: Def) -> bool:
    """Faces of the Past: its controller chooses as the trigger resolves; "it" is the creature as it last existed (608.2h), a changeling sharing with all (702.73a)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context, selectors
    from app.rules.plan import decide

    died = context.info(plan, ctx, context.EVENT)
    kinds = tuple(sorted(died[1].subtypes & selectors.CREATURE_TYPES)) if died is not None else ()
    if not kinds:
        return True  # (no creature type, so nothing shares one with it)
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name', '')}: tap or untap the creatures that share a creature type with {died[0].name if died else 'it'}",
           options=[DecisionOption(id="tap", label="Tap all untapped creatures that share a creature type with it"),
                    DecisionOption(id="untap", label="Untap all tapped creatures that share a creature type with it")],
           resume={"step": "faces110m", "ctx": ctx, "kinds": list(kinds)})
    return False


def resume_faces(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, selectors

    ctx = d.resume["ctx"]
    who = selectors.Selector(types=("Creature",), subtypes=tuple(d.resume["kinds"])).key()
    plan.note(f"{plan.name(d.player)} chooses to {chosen[0]} the creatures that share a creature type", actor=d.player)
    (effects.tap if chosen[0] == "tap" else effects.untap)(plan, ctx, {"who": who})
    effects.continue_effects(plan, ctx)


_REVERSAL = ("The next time you would lose the game this turn, instead draw seven cards and your life total becomes 1.")


def lose_shield(plan: Any, ctx: Def, e: Def) -> bool:
    """Stunning Reversal: a one-shot replacement of the controller's next loss of the game this turn (614.1a, 614.5); applied in wave110c_lose."""
    plan.rules.lose_shields110m.append({"player": ctx["controller"], "turn": plan.state.turn.number, "card": ctx.get("source_card")})
    return True


def lose_shields(plan: Any, pid: str) -> list[tuple[Any, Def]]:
    """The live shields of ``pid`` as replacement sources (the card that made them, exiled by then): only this turn's (610.3)."""
    return [(card, {"life": "reversal110m"}) for x in plan.rules.lose_shields110m
            if x["player"] == pid and x["turn"] == plan.state.turn.number and (card := plan.state.cards.get(x["card"] or "")) is not None]


_DAMNATIONS = ("Target opponent chooses a number. You may have that player lose that much life. If you don't, that player sacrifices all but that many "
               "permanents of their choice.")


def damnations(plan: Any, ctx: Def, e: Def) -> bool:
    """Choice of Damnations, step 1: the target opponent chooses a number (any number 0 or greater, announced to everyone, 107.1b)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.group_choice import NUMBER
    from app.rules.plan import decide

    opp = next(iter(effects._players(plan, ctx, "target")), None)
    if opp is None or opp not in plan.live():
        return True  # (an illegal target as it resolves: 608.2b)
    decide(plan, player=opp, kind="choose_one", prompt=f"{ctx.get('name', '')}: choose a number",
           options=[DecisionOption(id=NUMBER, label="Type a number ≥ 0", group="number")], resume={"step": "damnations110m", "ctx": ctx, "opp": opp})
    return False


def resume_damnations(plan: Any, d: Any, chosen: list[str]) -> None:
    """Step 2: its controller may have that player lose that much life."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    ctx, opp = d.resume["ctx"], d.resume["opp"]
    n = max(0, int(chosen[0])) if chosen and chosen[0].isdigit() else 0
    plan.note(f"{plan.name(opp)} chooses {n}", actor=opp)
    decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name', '')}: have {plan.name(opp)} lose {n} life? (If not, they sacrifice all but {n} permanents)",
           options=[DecisionOption(id="yes", label=f"{plan.name(opp)} loses {n} life"), DecisionOption(id="no", label=f"{plan.name(opp)} sacrifices all but {n} permanents")],
           resume={"step": "damnations110m_lose", "ctx": ctx, "opp": opp, "n": n})


def resume_damnations_lose(plan: Any, d: Any, chosen: list[str]) -> None:
    """Step 3: life lost, or the player keeps the number of permanents they chose (the rest are sacrificed together, 701.21a)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    ctx, opp, n = d.resume["ctx"], d.resume["opp"], d.resume["n"]
    if chosen and chosen[0] == "yes":
        if effects.lose_life(plan, ctx, {"do": "lose_life", "who": f"player:{opp}", "n": n}):
            effects.continue_effects(plan, ctx)
        return
    perms = [c.id for c in plan.state.cards.values() if c.zone == f"{opp}:battlefield" and c.controller == opp and plan.in_game(c)]
    if len(perms) > n > 0:
        decide(plan, player=opp, kind="choose_cards", prompt=f"{ctx.get('name', '')}: choose {n} permanents to keep; sacrifice the rest",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in perms],
               min_choices=n, max_choices=n, resume={"step": "damnations110m_keep", "ctx": ctx, "opp": opp, "perms": perms})
        return
    effects._sacrifice_cards(plan, perms if n == 0 else [], opp, ctx, None)
    effects.continue_effects(plan, ctx)


def resume_damnations_keep(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, opp = d.resume["ctx"], d.resume["opp"]
    keep = set(chosen)
    effects._sacrifice_cards(plan, [c for c in d.resume["perms"] if c not in keep], opp, ctx, None)
    effects.continue_effects(plan, ctx)


RESUME: dict[str, Any] = {"faces110m": resume_faces, "damnations110m": resume_damnations, "damnations110m_lose": resume_damnations_lose,
                          "damnations110m_keep": resume_damnations_keep}
PRIMITIVES: dict[str, Any] = {"top_to_bottom110m": top_to_bottom, "faces110m": faces, "lose_shield110m": lose_shield, "damnations110m": damnations}
