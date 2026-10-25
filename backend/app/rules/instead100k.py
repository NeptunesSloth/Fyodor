"""-- instead (wave 100K) -- "If C, you may Y instead." and a few exact "instead" wordings.

* "If that creature is attacking, you may put it on top of its owner's library instead." (Sweep Away, Ether Well, Expel from
  Orazca, Whirlpool Whelm): C is judged once as that part resolves (608.2c); only when it holds does the controller choose
  (608.2d: "you may" is the controller's choice, made on resolution: Ether Well's 2004-10-04 ruling) between Y and the
  replaced instruction. No, or C false: the replaced instruction happens (Expel from Orazca's 2018-01-19 ruling).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

# "Clash with an opponent, then return target creature to its owner's hand." (Whirlpool Whelm): two instructions in order, so the
# "If you win, … instead" sentence after it replaces only the return (the 2007-10-01 ruling: the creature goes to its owner's hand
# unless you win; you choose after the clash)
_SPLITS = {"Clash with an opponent, then return target creature to its owner's hand.":
           "Clash with an opponent. Return target creature to its owner's hand.",
           # Golden Demise: "instead only creatures your opponents control get -2/-2" is those creatures' -2/-2 in place of all creatures'
           "instead only creatures your opponents control get -2/-2 until end of turn.":
           "instead creatures your opponents control get -2/-2 until end of turn.",
           # Gideon's Triumph: the edict's tail where the edict grammar reads it (scripts: "of their choice" last)
           "sacrifices a creature of their choice that attacked or blocked this turn.": "sacrifices a creature that attacked or blocked this turn of their choice.",
           # Dewdrop Cure: "each with" restates that every chosen card has that mana value (one target group)
           "target creature cards each with mana value 2 or less": "target creature cards with mana value 2 or less",
           # Turncoat Kunoichi: "choose target … . Exile that creature until …" is the one targeted exile (the chosen creature is the target)
           "choose target creature an opponent controls. Exile that creature until ~ leaves the battlefield. If ~'s sneak cost was paid, instead exile the chosen creature.":
           "exile target creature an opponent controls until ~ leaves the battlefield. If ~'s sneak cost was paid, instead exile that creature.",
           # Rangers of Ithilien: "lesser power" than the Rangers as the target is chosen and again as it resolves (its 2023-06-16 ruling), so its power then
           "gain control of up to one target creature with lesser power for as long as you control ~":
           "gain control of up to one target creature with power less than ~'s power for as long as you control ~",
           # Walking Desecration: the type is chosen as the ability resolves (608.2d), then those creatures must attack (508.1d)
           "Creatures of the creature type of your choice attack this turn if able.": "Choose a creature type. Creatures of the chosen type attack this turn if able.",
           # Bumi, Unleashed: "that combat phase" is the one just added (combat_rules: its own tag)
           "After this phase, there is an additional combat phase. Only land creatures can attack during that combat phase.":
           "After this phase, there is an additional combat phase in which only land creatures can attack."}


def normalize(text: str) -> str:
    for old, new in _SPLITS.items():
        text = text.replace(old, new)
    return text


def whole_loot(base: list[dict[str, Any]], alt: list[dict[str, Any]]) -> bool:
    """"draw a card, then discard a card. If you have a full party, instead draw three cards." (The Destined Thief): the draw
    takes the place of the whole sentence (its 2025-10-02 ruling: "you won't discard at all")."""
    return base == [{"do": "draw", "who": "you", "n": 1}, {"do": "discard", "who": "you", "n": 1}] and alt == [{"do": "draw", "who": "you", "n": 3}]


def may_branch(effects: list[dict[str, Any]], prev_start: int, cond: dict[str, Any], base: list[dict[str, Any]],
               alt: list[dict[str, Any]], flag: str, text: str) -> list[dict[str, Any]]:
    """[X]. If C, you may [Y] instead: C, then (only if it held) the choice, then exactly one of X and Y."""
    return [*effects[:prev_start], {"do": "only_if", "cond": cond, "skip": 1, "bind": flag},
            {"do": "may_instead100k", "bind": flag, "text": text},
            {"do": "only_if", "cond": {"flag": flag, "negate": True}, "skip": len(base)}, *base,
            {"do": "only_if", "cond": {"flag": flag}, "skip": len(alt)}, *alt]


def ask(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name') or 'It'}: you may {e['text']} instead",
           options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
           resume={"step": "may_instead100k", "ctx": ctx, "bind": e["bind"]})
    return False


def answer(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    context.bind_flag(ctx, d.resume["bind"], chosen[0] == "yes")
    plan.note(f"{plan.name(d.player)} chose {'to' if chosen[0] == 'yes' else 'not to'}")
    continue_effects(plan, ctx)


PRIMITIVES = {"may_instead100k": ask}
RESUME = {"may_instead100k": answer}
