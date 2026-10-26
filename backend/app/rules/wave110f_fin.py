"""Wave 110F final pass: whole-ability definitions read onto existing machinery (one exact wording each)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.selectors import Selector

_MASTER = ("Whenever a nontoken artifact creature you control dies, you may exile it. If you do, choose an opponent with the most life among your "
           "opponents. That player faces a villainous choice — They lose 4 life, or you create a token that's a copy of that card.")


_ANIMATE = "As long as enchanted artifact isn't a creature, it's an artifact creature with power and toughness each equal to its mana value."


_BUSY: list[int] = []  # (reading the same ability natively once)
_VOLT_COST = "Collect evidence 6: ~ becomes an artifact creature until end of turn."
_VOLT_ATTACK = ("Whenever ~ attacks, you may cast an instant or sorcery spell from among cards exiled with it. "
                "If that spell would be put into a graveyard, put it on the bottom of its owner's library instead.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts
    from app.rules.token_copy_outcomes import ORIGINAL

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "triggered" and text == _MASTER:
        probe = scripts.define(replace(ability, text=_MASTER.split(" If you do,")[0]), ch)
        if probe is None or probe["kind"] != "triggered":
            return {}
        return {**probe, "effects": [{**probe["effects"][0], "as": ORIGINAL}, {"do": "master110f"}]}
    if ability.kind == "static" and text == _ANIMATE:  # 613.1d, 613.4b: the type is added whatever the host is; its P/T only when it was no creature (2008-08-01 ruling)
        probe = scripts.define(replace(ability, text="Enchanted artifact has flying."), ch)
        if probe is None or probe.get("who") != "attached":
            return {}
        return {**probe, "keywords": [], "layered": True, "base_mv": True, "animate_mv110f": True, "layer4": {"add_types": ["Artifact", "Creature"]}}
    if ability.kind == "activated" and text == _VOLT_COST:  # 607.2a: the collected cards are exiled by this activated ability's cost: they are "exiled with it"
        if _BUSY:
            return None
        _BUSY.append(1)
        try:
            probe = scripts.define(ability, ch)
        finally:
            _BUSY.pop()
        return None if probe is None else {**probe, "effects": [{"do": "link_cost110f"}, *probe["effects"]]}
    if ability.kind == "triggered" and text == _VOLT_ATTACK:  # 608.2g (2024-02-02 ruling): cast during resolution, paying costs; 614.1a: a graveyard destination becomes the library's bottom
        probe = scripts.define(replace(ability, text="Whenever this Vehicle attacks, you may draw a card."), ch)
        if probe is None or probe["kind"] != "triggered":
            return {}
        sel = Selector(types=("Instant", "Sorcery"), zones=("stack",)).key()
        return {**probe, "optional": False, "effects": [{"do": "linked_cards", "as": "e0"}, {"do": "free_cast", "zone": "that", "who": "ref:e0", "filter": sel, "optional": True, "mv": None, "n": 1,
                                                                           "paid": True, "graveyard_destination": "library_bottom"}]}
    return None


def link_cost(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, exiled_with

    exiled_with.record(plan, ctx, effects._cards(plan, ctx, "cost:exiled"))
    return True


def master(plan: Any, ctx: dict[str, Any], e: dict[str, Any], pick: str | None = None) -> bool:
    """608.2c "If you do": only if the card really was exiled (608.2h its object is in exile now). 701.55a-b: the chosen opponent chooses an option."""
    from app.rules import context
    from app.rules.plan import decide
    from app.rules.token_copy_outcomes import ORIGINAL
    from app.rules.token_copy_sources import copy

    if pick is None:
        if not any(plan.state.cards[c].zone.endswith(":exile") for c in context.objects(plan, ctx, ORIGINAL) if c in plan.state.cards):
            return True
        opps = [p for p in plan.live() if p != ctx["controller"]]
        if not opps:
            return True
        top = max(plan.state.players[p].life for p in opps)
        best = [p for p in opps if plan.state.players[p].life == top]
        if len(best) > 1:  # "choose an opponent with the most life": a tie is the controller's choice (101.4)
            decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose an opponent with the most life",
                   options=[DecisionOption(id=p, label=plan.name(p)) for p in best], resume={"step": "master110f", "ctx": ctx, "e": e})
            return False
        pick = best[0]
    lose = [{"do": "lose_life", "who": "player:" + pick, "n": 4}]
    added = [{"do": "villain", "who": "player:" + pick, "a": lose, "b": [copy("ref:" + ORIGINAL)],
              "labels": ["They lose 4 life", "You create a token that's a copy of that card"]}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    return True


def resume_master(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if master(plan, d.resume["ctx"], d.resume["e"], chosen[0]):
        effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {"master110f": master, "link_cost110f": link_cost}
RESUME = {"master110f": resume_master}
