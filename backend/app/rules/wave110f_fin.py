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


_TASTER = ("When ~ enters, target opponent reveals X cards from their hand, where X is the number of Goblins you control. You choose one of those cards. "
           "That player exiles it. If an instant or sorcery card is exiled this way, you may cast it for as long as you control ~, and mana of any type can be spent to cast that spell.")


_DOCTOR = ("Whenever ~ attacks, choose a card in your hand. Defending player guesses whether that card's mana value is greater than the number of artifacts you control. "
           "If they guessed wrong, you may cast it without paying its mana cost. If you don't cast a spell this way, investigate.")


_SERV = ("When ~ enters, return target creature card from your graveyard to the battlefield.",
         "When the creature put onto the battlefield with ~ dies, exile it and return ~ to its owner's hand.",
         "When ~ leaves the battlefield, exile the creature put onto the battlefield with ~.")


_STAND = ("At the beginning of combat on your turn, for each defending player, separate all creatures that player controls into two piles and that player chooses one. "
          "Only creatures in the chosen piles can block this turn.")


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
    if ability.kind == "triggered" and text == _TASTER:  # 701.20a reveal, 701.13 exile, 611.2b "for as long as you control ~", 118.9/609.4b mana of any type; X once (ruling 2025-11-17)
        probe = scripts.define(replace(ability, text="When ~ enters, target opponent loses 1 life."), ch)
        if probe is None or probe["kind"] != "triggered":
            return {}
        sel = Selector(types=("Instant", "Sorcery"), card=True).key()
        goblins = scripts.parse_effects("Target opponent reveals X cards from their hand, where X is the number of Goblins you control.")
        assert goblins is not None
        return {**probe, "effects": [*goblins[0],
                                     {"do": "choose_from_hand", "who": "you", "sel": 'sel:{"card":true,"zones":[]}', "n": 1, "label": "card", "optional": False, "as": "e1"},
                                     {"do": "exile", "who": "ref:e1", "as": "e2"}, {"do": "only_if", "cond": {"object": "ref:e2", "is": sel}, "skip": 1},
                                     {"do": "grant_play", "who": "ref:e2", "play": False, "cast": True, "until": "source_controlled", "optional": True, "spend": "type"}]}
    if ability.kind == "triggered" and text == _DOCTOR:
        probe = scripts.define(replace(ability, text="Whenever ~ attacks, draw a card."), ch)
        cast = scripts.parse_effects("You may cast a spell from your hand without paying its mana cost. If you don't, investigate.")
        if probe is None or probe["kind"] != "triggered" or cast is None:
            return {}
        free, gate, investigate = cast[0]
        return {**probe, "effects": [{"do": "seventh110f"}, {"do": "only_if", "cond": {"succeeded": "wrong110f"}, "skip": 1},
                                     {**free, "zone": "that", "who": "ref:seventh110f"}, gate, investigate]}
    if ability.kind == "triggered" and text in _SERV:  # 607.2c: the creature this enchantment's enters ability put onto the battlefield, by object (400.7)
        if text == _SERV[0]:
            if _BUSY:
                return None
            _BUSY.append(1)
            try:
                native = scripts.define(ability, ch)
            finally:
                _BUSY.pop()
            if native is None or [x["do"] for x in native["effects"]] != ["return_card"]:
                return {}
            return {**native, "effects": [{**native["effects"][0], "as": "e0"}, {"do": "link_put110f"}]}
        probe = scripts.define(replace(ability, text=("Whenever a creature you control dies, exile it and return ~ to its owner's hand." if text == _SERV[1]
                                                     else "When ~ leaves the battlefield, you gain 1 life.")), ch)
        if probe is None:
            return {}
        return {**probe, "cond": {"event": "die", "subject": "put_with110f"}} if text == _SERV[1] else {**probe, "effects": [{"do": "servitude110f"}]}
    if ability.kind == "triggered" and text == _STAND:  # 802.2: every opponent is a defending player as the combat phase starts; 700.3: the piles; Fight or Flight's machinery (pile_groups)
        probe = scripts.define(replace(ability, text="At the beginning of combat on your turn, draw a card."), ch)
        if probe is None or probe["kind"] != "triggered":
            return {}
        sel = Selector(types=("Creature",)).key()
        return {**probe, "effects": [{"do": "pile_deal", "who": "each_opponent", "split": "you", "sel": sel, "zone": "battlefield", "pick": "owner", "n": 2,
                                      "chosen": "limit_block", "other": None, "say": "creatures"}]}
    return None


def link_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """607.2c: the objects this ability put onto the battlefield (the new objects, 400.7)."""
    from app.rules import effects

    new = [c for c in effects._cards(plan, ctx, "ref:e0") if plan.state.cards[c].zone.endswith(":battlefield")]
    if new and ctx.get("source_object"):
        plan.rules.put_with110f.setdefault(ctx["source_object"], []).extend(plan.oid(c) for c in new)
    return True


def servitude(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Exile the creature put onto the battlefield with this enchantment": only while it still is that object on the battlefield (400.7, 2004-10-04 ruling)."""
    ids = [c for oid in plan.rules.put_with110f.get(ctx.get("source_object") or "", ()) if (c := oid.rsplit(".", 1)[0]) in plan.state.cards
           and plan.state.cards[c].zone.endswith(":battlefield") and plan.oid(c) == oid]
    if ids:
        plan.do({"type": "move", "card_ids": ids, "to": {"zone": "exile"}}, actor=ctx["controller"])
    return True


def seventh(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """608.2d: the controller picks a card in hand in secret (it is not named in the log), the defending player guesses (X is 0 in a hand, 202.3e)."""
    from app.rules import context, effects

    me = ctx["controller"]
    hand = list(plan.state.zones.get(f"{me}:hand", []))
    context.bind_payment(ctx, "wrong110f", False)
    context.bind_objects(plan, ctx, "seventh110f", [])
    if not hand or not effects._players(plan, ctx, "defending_player"):
        return True
    effects.decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: choose a card in your hand",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand], min_choices=1, max_choices=1,
                   resume={"step": "seventh110f", "ctx": ctx})
    return False


def resume_seventh(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in plan.state.zones.get(f"{d.player}:hand", []):
        raise ActionError("Choose a card in your hand")
    context.bind_objects(plan, ctx, "seventh110f", chosen)
    guesser = effects._players(plan, ctx, "defending_player")[0]
    effects.decide(plan, player=guesser, kind="choose_one", prompt=f"{ctx.get('name') or 'Guess'}: is the mana value of the chosen card greater than the number of artifacts they control?",
                   options=[DecisionOption(id="yes", label="Yes, greater"), DecisionOption(id="no", label="No, not greater")],
                   resume={"step": "seventh110f_guess", "ctx": ctx, "card": chosen[0]})


def resume_seventh_guess(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import characteristics as chars
    from app.rules import context, effects

    if len(chosen) != 1 or chosen[0] not in ("yes", "no"):
        raise ActionError("Choose yes or no")
    ctx = d.resume["ctx"]
    card = plan.state.cards[d.resume["card"]]
    artifacts = sum("Artifact" in plan.ch(plan.state.cards[c]).types for c in plan.state.zones.get(f"{ctx['controller']}:battlefield", []))
    wrong = (chars.of(card, plan.info).mana_value > artifacts) != (chosen[0] == "yes")
    plan.note(f"{plan.name(d.player)} guessed {'wrong' if wrong else 'right'}", actor=d.player)
    context.bind_payment(ctx, "wrong110f", wrong)
    effects.continue_effects(plan, ctx)


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


PRIMITIVES = {"master110f": master, "link_cost110f": link_cost, "seventh110f": seventh, "link_put110f": link_put, "servitude110f": servitude}
RESUME = {"master110f": resume_master, "seventh110f": resume_seventh, "seventh110f_guess": resume_seventh_guess}
