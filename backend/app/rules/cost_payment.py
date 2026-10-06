"""Paying the parts of an activation cost that aren't mana (app/rules/costs.py components).

CR 602.2b applies 601.2b-i to activated abilities: the total cost is locked in, then paid all at
once (601.2h: "Partial payments are not allowed. Unpayable costs can't be paid."). 118.3: a player
can't pay a cost without the resources to pay it fully — an untapped permanent to untap, a
creature to sacrifice, a card to discard. So:

* :func:`problem` says why a cost can't be paid right now (activation hints and refusals);
* :func:`choose` validates the objects the player chose for each part (``cost_choices`` on the
  intent) or opens a private ``choose_cards`` decision for the next part that needs a choice.
  Nothing has moved yet; choosing no cards cancels (the table is left exactly as it was);
* :func:`pay` carries out every non-mana part once the mana payment has been found.

Hidden information: the options of a discard choice are cards in the payer's hand, so the
decision (like every decision's options) goes only to the payer; the discarded card is public
once it's in the graveyard (701.9a).
"""

from __future__ import annotations

import secrets
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, PaymentRecord
from app.game.state import CardInstance, zone_key
from app.rules import costs as C
from app.rules import selectors
from app.rules.costs import AbilityCost, CostComponent
from app.rules.plan import Plan, decide
from app.rules.sba import power

_VERBS = {C.SACRIFICE: "sacrifice", C.DISCARD: "discard", C.EXILE_FROM_GRAVEYARD: "exile",
          C.RETURN_PERMANENT: "return to its owner's hand", C.TAP_OTHER: "tap", C.UNTAP_OTHER: "untap", C.REMOVE_COUNTER: "remove counters from"}
_VERBS["EXILE_FROM_HAND"] = "exile"
_VERBS[C.UNATTACH] = "unattach"
_VERBS["REVEAL_FROM_HAND"] = "reveal"  # (wave 15C)
_VERBS[C.BEHOLD] = "behold"  # (wave 17C) 701.4a
_VERBS[C.EXILE_TO_GY] = "put into its owner's graveyard"  # (wave 15C)
_VERBS["HAND_TO_BOTTOM"] = "put on the bottom of your library"  # -- if you do (wave 6F) --  # -- cost changers (wave 4I) -- "exile a blue card from your hand" (alt_costs.py)


def _reserved(cost: AbilityCost, comp: CostComponent, source: CardInstance) -> set[str]:
    """Objects a part can't use because another part of the same cost already does: the source
    when it's tapped ({T}) or leaves (sacrificed / exiled / returned) as part of the cost."""
    leaves = cost.sacrifice_self or any(c.selector is None and c.kind in (C.EXILE, C.RETURN_PERMANENT, C.EXILE_FROM_GRAVEYARD)
                                        for c in cost.components)
    if leaves or (comp.kind in (C.TAP_OTHER, C.UNTAP_OTHER, C.WATERBEND) and (cost.tap or cost.untap)):
        return {source.id}
    return set()


def candidates(plan: Plan, comp: CostComponent, player: str, source: CardInstance) -> list[str]:
    """Objects that could pay ``comp`` (one part of a cost), in a stable order."""
    if comp.kind == C.CRAFT:  # -- casting extras (wave 18E) -- 702.167a-b: permanents you control (selector) and/or cards in your graveyard (alt)
        out = []
        for z, key in ((zone_key(player, "battlefield"), comp.selector), (zone_key(player, "graveyard"), comp.alt)):
            sel = selectors.from_key(key) if key else None
            for cid in plan.state.zones.get(z, []):
                card = plan.state.cards.get(cid)
                if sel is not None and card is not None and cid != source.id and (z.endswith(":graveyard") or (
                        card.controller == player and plan.in_game(card))) \
                        and selectors.matches(plan, sel, card, plan.ch(card), player, source.id):
                    out.append(cid)
        return out
    assert comp.selector is not None
    sel = selectors.from_key(comp.selector)
    alt = selectors.from_key(comp.alt) if comp.alt else None  # (wave 4H: "another creature or an artifact")
    if comp.kind in (C.DISCARD, "EXILE_FROM_HAND", "HAND_TO_BOTTOM", "REVEAL_FROM_HAND"):  # (EXILE_FROM_HAND: wave 4I, alt_costs.py — Force of Will;
        # HAND_TO_BOTTOM: wave 6F, optional_payment.py)
        zone = zone_key(player, "hand")
    elif comp.kind in (C.EXILE_FROM_GRAVEYARD, C.COLLECT_EVIDENCE):  # (collect evidence: wave 4H)
        zone = zone_key(player, "graveyard")
    else:
        zone = zone_key(player, "battlefield")
    out = []
    if comp.kind == C.BEHOLD:  # -- static_other sweep (wave 17C) -- 701.4a: a card in your hand (the selector) or a permanent you control (alt)
        for z, s in ((zone_key(player, "hand"), sel), (zone_key(player, "battlefield"), alt)):
            for cid in plan.state.zones.get(z, []):
                card = plan.state.cards.get(cid)
                if card is not None and cid != source.id and (z.endswith(":hand") or (card.controller == player and plan.in_game(card))) \
                        and s is not None and selectors.matches(plan, s, card, plan.ch(card), player, source.id):
                    out.append(cid)
        return out
    if comp.kind == C.EXILE_TO_GY:  # -- if you do (wave 15C) -- a card an opponent owns, face up in exile (406.3), in a stable order
        pool = [c for pid in plan.state.players if pid != player for c in plan.state.zones.get(zone_key(pid, "exile"), [])]
        return [c for c in pool if (x := plan.state.cards.get(c)) is not None and not x.face_down and x.owner != player
                and selectors.matches(plan, sel, x, plan.ch(x), player, source.id)]
    for cid in plan.state.zones.get(zone, []):
        card = plan.state.cards.get(cid)
        if card is None or (zone.endswith(":battlefield") and (card.controller != player or not plan.in_game(card))):
            continue
        if cid == source.id and not zone.endswith(":battlefield"):
            continue  # -- costs (wave 3$) -- a spell's additional cost can't discard / exile the spell being cast (601.2a)
        if not selectors.matches(plan, sel, card, plan.ch(card), player, source.id) and not (
                alt is not None and selectors.matches(plan, alt, card, plan.ch(card), player, source.id)):
            continue
        if comp.named_self and plan.ch(card).name != plan.ch(source).name:  # (wave 4H: grandeur)
            continue
        if comp.kind == C.REMOVE_COUNTER and counters_on(card, comp.counter) < (1 if comp.among else comp.amount):  # (any kind: wave 4H; among: 26C)
            continue
        if comp.kind == C.SACRIFICE and not plan.resolution_cost:  # -- prohibitions (wave 22B) -- "Players can't … sacrifice creatures to cast
            from app.rules import prohibitions  # spells or activate abilities"

            if prohibitions.sacrifice_banned(plan.state, plan.info, card):
                continue
        if comp.kind == C.PUT_COUNTER:  # -- review 22B -- 614.17b: counters that can't be put can't pay (Solemnity ruling 2017-07-14)
            from app.rules import prohibitions

            if prohibitions.cant_counters(plan, cid, None):
                continue
        out.append(cid)
    return out


def energy_amount(comp: C.CostComponent, x: int | None) -> int:
    """-- counters & designations (wave 3E) -- the energy a PAY_ENERGY part removes ("Pay X {E}": X)."""
    return max(0, x or 0) if comp.x else comp.amount


# -- activation costs (wave 4H) ------------------------------------------------------------------------------
def counters_on(card: CardInstance, kind: str | None) -> int:
    """Counters of ``kind`` on ``card`` (C.ANY_COUNTER: of every kind, 122.1)."""
    if kind == C.ANY_COUNTER:
        return sum(n for n in card.counters.values() if n > 0)
    return card.counters.get(kind or "", 0)


def objects_needed(comp: CostComponent, x: int | None) -> int:
    """The objects a chosen part takes: X of them for "Sacrifice X Treasures" (107.3a), else comp.objects."""
    return max(0, x or 0) if comp.x else comp.objects


def life_amount(plan: Plan, comp: CostComponent, player: str) -> int | None:
    """The life a PAY_LIFE part costs now (None: it can't be paid — 903.4f, no commander)."""
    life = plan.state.players[player].life
    if comp.life_rule == "half":  # 107.1a: "rounded up"; 119.4b: 0 can always be paid
        return max(0, -(-life // 2))
    if comp.life_rule == "commander_colors":  # 903.4: the commanders' combined color identity
        from app.rules import commander as cmdr

        found = [plan.info.get(c.card_id) for c in plan.state.cards.values()
                 if c.owner == player and c.commander_key and c.card_id]
        datas = [d for d in found if d]
        return len(cmdr.deck_identity(datas)) if datas else None
    return comp.amount


def _token(cid: str, kind: str, j: int) -> str:
    """A choice id for one counter (Id-safe: "+1/+1" → "p1_p1")."""
    return f"{cid}:{kind.replace('+', 'p').replace('-', 'm').replace('/', '_')}:{j}"


def counter_tokens(plan: Plan, cards: list[str]) -> dict[str, tuple[str, str]]:
    """Every counter on ``cards`` as a choice: id → (card id, kind)."""
    out: dict[str, tuple[str, str]] = {}
    for cid in cards:
        card = plan.state.cards[cid]
        for kind, n in sorted(card.counters.items()):
            for j in range(max(0, n)):
                out[_token(cid, kind, j)] = (cid, kind)
    return out


def _new_part_problem(plan: Plan, comp: CostComponent, card: CardInstance, player: str, x: int | None) -> str | None:
    """118.3 for the parts this wave reads that name no chosen objects (None: payable, or not one of them)."""
    name = card.name or "It"
    if comp.kind == C.REMOVE_COUNTER and comp.selector is None and (comp.x or comp.counter == C.ANY_COUNTER):
        need = max(0, x or 0) if comp.x else comp.amount
        if counters_on(card, comp.counter) < need:
            what = "counters" if comp.counter == C.ANY_COUNTER else f"{comp.counter} counters"
            return f"{name} doesn't have {need} {what}"
    elif comp.kind in (C.PUT_COUNTER, C.EXERT) and comp.selector is None and not card.zone.endswith(":battlefield"):
        return f"{name} isn't on the battlefield"  # (122.6; 701.43c)
    elif comp.kind in (C.MILL, C.EXILE_LIBRARY) and len(plan.state.zones.get(zone_key(player, "library"), [])) < comp.amount:
        return f"You don't have {comp.amount} card{'s' if comp.amount != 1 else ''} in your library"  # 701.17b, 118.3
    elif comp.kind in (C.COLLECT_EVIDENCE, C.FORAGE) and not _flexible_options(plan, comp, card, player, set())[1]:
        return f"You can't pay “{comp.text}”"  # 701.59b; 701.61a
    elif comp.kind == C.PAY_LIFE and comp.life_rule is not None:
        amount = life_amount(plan, comp, player)
        if amount is None:
            return "You have no commander, so that cost can't be paid (903.4f)"
        if plan.state.players[player].life < amount:  # 119.4
            return f"You don't have {amount} life to pay"
    return None
# -- end activation costs (wave 4H) --


def problem(plan: Plan, cost: AbilityCost, card: CardInstance, player: str, x: int | None = None) -> str | None:
    """Why the non-mana parts of ``cost`` can't be paid now (118.3), or None. ``x``: the X chosen
    for "Pay X {E}" (unknown yet: 0)."""
    from app.rules import cast_limits  # -- cast limits (wave 5E) --
    from app.rules.casting import summoning_sick  # casting imports this module

    name = card.name or "It"
    from app.rules import (
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17 / 119.4: "Players can't pay life or sacrifice creatures …"
    )

    for comp in cost.components:
        if comp.kind == C.PAY_LIFE and (comp.amount or comp.life_rule) and not plan.resolution_cost \
                and (why := prohibitions.life_banned(plan.state, plan.info)):
            return f"{why}: players can't pay life to cast spells or activate abilities"
        if comp.kind == C.SACRIFICE and comp.selector is None and not plan.resolution_cost \
                and (why := prohibitions.sacrifice_banned(plan.state, plan.info, card)):
            return f"{why}: {name} can't be sacrificed to pay a cost"
        if comp.kind == C.PUT_COUNTER and comp.selector is None and (why := prohibitions.cant_counters(plan, card.id, None)):
            return f"{why}: counters can't be put on {name}"  # -- review 22B -- 614.17b (Solemnity, Devoted Druid)
        if comp.kind == C.UNTAP:  # 107.6: an untapped permanent can't be untapped to pay; 302.6 / 602.5a
            if not card.tapped:
                return f"{name} isn't tapped"
            ch = plan.ch(card)
            if ch.is_creature and "haste" not in ch.keywords and summoning_sick(plan.state, card) \
                    and not cast_limits.as_though_haste(plan.state, card, plan.info):  # -- cast limits (wave 5E) --
                return f"{name} has summoning sickness"
        elif comp.kind == C.PAY_ENERGY and plan.state.players[player].resources.get("energy", 0) < energy_amount(comp, x):
            return f"You don't have {energy_amount(comp, x)} energy to pay"
        elif (why := _new_part_problem(plan, comp, card, player, x)) is not None:  # (wave 4H)
            return why
        elif comp.kind == "TAP_POWER":  # -- static_other sweep (wave 17C) -- teamwork 702.194a: untapped creatures with total power N or more
            usable = [c for c in candidates(plan, comp, player, card) if c not in _reserved(cost, comp, card)]
            if sum(max(0, power(plan.state.cards[c], plan.ch(plan.state.cards[c])) or 0) for c in usable) < comp.amount:
                return f"You can't pay “{comp.text}”"
        elif comp.kind == C.CRAFT:  # -- casting extras (wave 18E) -- enough materials (the other parts' choices are checked as a whole)
            if len([c for c in candidates(plan, comp, player, card) if c not in _reserved(cost, comp, card)]) < comp.amount:
                return f"You can't pay “{comp.text}”"
        elif comp.kind == C.REMOVE_COUNTER and comp.among:  # -- activated sweep (wave 26C) -- enough counters among the permanents (118.3)
            holders = [c for c in candidates(plan, comp, player, card) if c not in _reserved(cost, comp, card)]
            if sum(counters_on(plan.state.cards[c], comp.counter) for c in holders) < (max(0, x or 0) if comp.x else comp.amount):
                return f"You can't pay “{comp.text}”"
        elif comp.selector is not None and comp.kind not in (C.COLLECT_EVIDENCE, C.WATERBEND):  # (collect evidence: _new_part_problem, wave 4H; waterbend: any number, even none)
            usable = [c for c in candidates(plan, comp, player, card) if c not in _reserved(cost, comp, card)]
            if len(usable) < objects_needed(comp, x) and not comp.up_to:  # (X / one permanent for its counters: wave 4H)
                return f"You can't pay “{comp.text}”"
    return None


def choose(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp, cost: AbilityCost, card: CardInstance, what: str) -> dict[int, list[str]] | None:
    """The validated objects for every part of ``cost`` that needs a choice, by component index;
    None while waiting for the payer's (private) choice. Each object pays for one part only."""
    given: dict[int, list[str]] = {}
    for c in a.cost_choices:
        if c.component == C.EITHER_SLOT and isinstance(a, A.CastSpell):  # -- static wordings (wave 6E) -- (either_costs)
            continue
        if c.component in given:
            raise ActionError("Choose the objects for each part of the cost once")
        given[c.component] = list(c.cards)
    parts = dict(cost.choices)
    if set(given) - set(parts):
        raise ActionError("That ability's cost has no such part to choose for")
    out: dict[int, list[str]] = {}
    used: set[str] = set()
    x = getattr(a, "x_value", None)  # (wave 4H: "Sacrifice X Treasures" — X announced as it's activated, 107.3a)
    for i, comp in cost.choices:
        if comp.kind == C.WATERBEND:  # -- activated sweep (wave 17B) -- up to N artifacts / creatures, each paying {1} (701.67a)
            found = _choose_waterbend(plan, a, i, comp, cost, card, what, given.get(i), used)
        elif comp.kind == "TAP_POWER":  # -- static_other sweep (wave 17C) -- one choice of creatures, validated as a whole
            found = _choose_power(plan, a, i, comp, cost, card, what, given.get(i), used)
        elif comp.kind == C.CRAFT:  # -- casting extras (wave 18E) -- the materials: one choice of at least ``amount`` objects
            found = _choose_craft(plan, a, i, comp, cost, card, what, given.get(i), used)
        if comp.kind in (C.WATERBEND, "TAP_POWER", C.CRAFT):
            if found is None:
                return None
            out[i] = found
            continue
        if comp.counter == C.ANY_COUNTER or comp.among or comp.kind in (C.COLLECT_EVIDENCE, C.FORAGE):  # -- activation costs (wave 4H) --
            chooser = _choose_counters if comp.counter == C.ANY_COUNTER or comp.among else _choose_flexible
            found = chooser(plan, a, i, comp, cost, card, what, given.get(i), used)
            if found is None:
                return None
            out[i] = found
            continue
        need = objects_needed(comp, x)
        usable = [c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
        if i in given:
            chosen = given[i]
            if (len(chosen) > need if comp.up_to else len(chosen) != need) or len(set(chosen)) != len(chosen) \
                    or any(c not in usable for c in chosen):
                raise ActionError(f"Choose {'up to ' if comp.up_to else ''}{need} to pay “{comp.text}”"
                                  + (" (each object pays one part of the cost)" if any(c in used for c in chosen) else ""))
        elif len(usable) < need and not comp.up_to:
            raise ActionError(f"You can't pay “{comp.text}”")  # 118.3
        elif need == 0 or (comp.up_to and not usable):  # -- review (Codex) -- X announced as 0 (107.3a): nothing to choose, and an empty pick would cancel
            chosen = []
        elif len(usable) == need and not comp.up_to:
            chosen = usable  # (no choice to make)
        else:
            verb = _VERBS.get(comp.kind, "use")
            decide(plan, player=plan.actor, kind="choose_cards",
                   prompt=f"{what}: choose {'up to ' if comp.up_to else ''}{need} to {verb} (“{comp.text}”), or "
                          + ("none to pay without" if comp.up_to else "none to cancel"),
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in usable],
                   min_choices=0, max_choices=need,
                   resume={"step": "ability_cost", "component": i, "amount": None if comp.up_to else need, "empty_ok": comp.up_to,
                           "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
                   source=card)
            return None
        out[i] = list(chosen)
        used |= set(chosen)
    return out


def _choose_waterbend(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp, i: int, comp: CostComponent, cost: AbilityCost,
                      card: CardInstance, what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- activated sweep (wave 17B) -- "Waterbend {N}": the untapped artifacts and creatures the payer taps, at most N, each paying for
    {1} of it (701.67a); none at all is a choice (the mana pays it). Tapping them isn't a {T} cost: a creature that came under the
    payer's control this turn can be tapped (302.6 is about the {T} and {Q} symbols)."""
    usable = [c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
    if given is not None:
        if len(given) > comp.amount or len(set(given)) != len(given) or any(c not in usable for c in given):
            raise ActionError(f"Choose at most {comp.amount} untapped artifacts and creatures to pay for “{comp.text}”")
        used |= set(given)
        return list(given)
    if not usable:
        return []
    decide(plan, player=plan.actor, kind="choose_cards",
           prompt=f"{what}: tap up to {comp.amount} untapped artifacts and creatures you control, each paying for {{1}} of “{comp.text}”"
                  " (none: pay with mana only)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in usable],
           min_choices=0, max_choices=min(comp.amount, len(usable)),
           resume={"step": "ability_cost", "component": i, "amount": None, "empty_ok": True,
                   "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
           source=card)
    return None


def _choose_power(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp, i: int, comp: CostComponent, cost: AbilityCost, card: CardInstance,
                  what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- static_other sweep (wave 17C) -- teamwork N (702.194a): any number of untapped creatures you control with total power N or
    more; the payer picks them (validated as a whole, 601.2h)."""
    options = [c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
    total = lambda ids: sum(max(0, power(plan.state.cards[c], plan.ch(plan.state.cards[c])) or 0) for c in ids)  # noqa: E731
    if given is not None:
        if len(set(given)) != len(given) or any(c not in options for c in given) or total(given) < comp.amount:
            raise ActionError(f"Those creatures don't pay “{comp.text}”")
        chosen = list(given)
    elif total(options) < comp.amount:
        raise ActionError(f"You can't pay “{comp.text}”")  # 118.3
    else:
        decide(plan, player=plan.actor, kind="choose_cards",
               prompt=f"{what}: choose the creatures to tap (“{comp.text}”), or none to cancel",
               options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name or 'Creature'} ({total([c])})", card_id=c) for c in options],
               min_choices=0, max_choices=len(options),
               resume={"step": "ability_cost", "component": i, "amount": None,
                       "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
               source=card)
        return None
    used |= set(chosen)
    return chosen


def _choose_craft(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp, i: int, comp: CostComponent, cost: AbilityCost, card: CardInstance,
                  what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- casting extras (wave 18E) -- craft's materials for one description (702.167a): exactly ``amount`` of them ("or more": at least);
    each object pays one part only. The payer picks (the graveyard cards are public, the permanents are on the table)."""
    options = [c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]

    def fits(ids: list[str]) -> bool:
        return len(set(ids)) == len(ids) and all(c in options for c in ids) and (len(ids) >= comp.amount if comp.more else len(ids) == comp.amount)

    if given is not None:
        if not fits(given):
            raise ActionError(f"Choose {'at least ' if comp.more else ''}{comp.amount} to pay “{comp.text}”")
        chosen = list(given)
    elif len(options) < comp.amount:
        raise ActionError(f"You can't pay “{comp.text}”")  # 118.3
    elif len(options) == comp.amount:
        chosen = options  # (no choice to make)
    else:
        decide(plan, player=plan.actor, kind="choose_cards",
               prompt=f"{what}: choose {'at least ' if comp.more else ''}{comp.amount} to exile (“{comp.text}”), or none to cancel",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
               min_choices=0, max_choices=len(options) if comp.more else comp.amount,
               resume={"step": "ability_cost", "component": i, "amount": None,
                       "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
               source=card)
        return None
    used |= set(chosen)
    return chosen


def _choose_counters(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp, i: int, comp: CostComponent, cost: AbilityCost,
                     card: CardInstance, what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- activation costs (wave 4H) -- "Remove two counters from this creature" / "Remove a counter from a creature you
    control": the payer picks the counters (122.1: any kinds; one permanent). Counters are public, but the pick is still
    the payer's own decision. Nothing moves until the whole cost is paid (601.2h)."""
    holders = [card.id] if comp.selector is None else [
        c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
    tokens = counter_tokens(plan, holders)
    need = comp.amount
    if comp.among:  # -- activated sweep (wave 26C) -- "from among creatures you control": each counter of that kind on any of them (122.1)
        need = max(0, getattr(a, "x_value", None) or 0) if comp.x else comp.amount
        tokens = {t: v for t, v in tokens.items() if comp.counter == C.ANY_COUNTER or v[1] == comp.counter}
    if given is not None:
        if len(given) != need or len(set(given)) != len(given) or any(t not in tokens for t in given) \
                or (not comp.among and len({tokens[t][0] for t in given}) != 1):
            raise ActionError(f"Choose {need} counter{'s' if need != 1 else ''}{'' if comp.among else ' on one permanent'} to pay “{comp.text}”")
        chosen = list(given)
    elif len(tokens) < need:
        raise ActionError(f"You can't pay “{comp.text}”")  # 118.3
    elif need == 0:
        chosen = []  # (X announced as 0, 107.3a: nothing to remove)
    elif len(set(tokens.values())) == 1 or (len(tokens) == need and (len(holders) == 1 or comp.among)):
        chosen = list(tokens)[:need]  # (one kind on one permanent, or exactly that many: no choice to make)
    else:
        decide(plan, player=plan.actor, kind="choose_cards",
               prompt=f"{what}: choose {need} counter{'s' if need != 1 else ''} to remove (“{comp.text}”), or none to cancel",
               options=[DecisionOption(id=t, label=f"{kind} counter on {plan.state.cards[cid].name or 'it'}", card_id=cid)
                        for t, (cid, kind) in tokens.items()],
               min_choices=0, max_choices=need,
               resume={"step": "ability_cost", "component": i, "amount": need,
                       "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
               source=card)
        return None
    if comp.selector is not None:
        used |= {tokens[t][0] for t in chosen}
    return chosen


def resume_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The payer chose the objects for one part (or none: cancel — nothing was paid)."""
    from app.rules.engine import INTENTS  # the engine imports this module

    assert d.resume is not None
    plan.rules.priority = d.player
    if not chosen and not d.resume.get("empty_ok"):
        plan.note(f"{plan.name(d.player)} cancelled")
        plan.hold = d.player
        return
    if d.resume["amount"] is not None and len(chosen) != d.resume["amount"]:  # (None: validated as a whole, wave 4H)
        raise ActionError(f"Choose {d.resume['amount']}")
    intent = A.parse_action(d.resume["intent"])
    assert isinstance(intent, A.ActivateAbility | A.CastSpell | A.TurnFaceUp)
    intent.cost_choices = [*intent.cost_choices, A.CostChoice(component=d.resume["component"], cards=chosen)]
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def excluded(cost: AbilityCost, card: CardInstance, chosen: dict[int, list[str]]) -> tuple[str, ...]:
    """Permanents that can't also pay mana: the source when it taps, untaps or leaves as part of
    the cost, and every object chosen for another part (it's sacrificed, tapped, returned …)."""
    out = [c for ids in chosen.values() for c in ids]
    if cost.tap or cost.untap or _reserved(cost, CostComponent(C.OTHER), card):
        out.append(card.id)
    return tuple(dict.fromkeys(out))


def pay(plan: Plan, cost: AbilityCost, card: CardInstance, chosen: dict[int, list[str]], record: PaymentRecord) -> None:
    """Carry out the non-mana parts other than {T}, loyalty, life and the source's own counters
    (the caller pays those as before), recording what was used (the payment record)."""
    player = plan.actor
    sacrifice: list[str] = [card.id] if cost.sacrifice_self else []
    library_parts: list[CostComponent] = []  # (wave 4H) 601.2h: moving cards out of the library is paid last
    for i, comp in enumerate(cost.components):
        ids = chosen.get(i, [])
        if comp.kind in (C.MILL, C.EXILE_LIBRARY):
            library_parts.append(comp)
        elif comp.kind == C.FORAGE and ids and plan.state.cards[ids[0]].zone.endswith(":battlefield"):
            sacrifice += ids  # (wave 4H) 701.61a: the Food, sacrificed with the cost's other sacrifices
        elif _pay_new_part(plan, comp, card, ids, record):  # -- activation costs (wave 4H) --
            continue
        elif comp.kind == C.REVEAL_SELF:  # -- forecast (wave 24C) -- 702.57a: shown to everyone (701.20a: in the log), then hidden again: the card
            plan.do({"type": "reveal", "card_ids": [card.id]}, actor=player)  # stays in the hand and a reveal doesn't last
            plan.do({"type": "hide", "card_ids": [card.id]}, actor=player)
            record.revealed.append(card.id)
        elif comp.kind in ("REVEAL_FROM_HAND", C.BEHOLD):  # -- static_other sweep (wave 17C) -- revealed to everyone (701.20a); a beheld permanent just is
            shown = [c for c in ids if plan.state.cards[c].zone.endswith(":hand")]
            if shown:
                plan.do({"type": "reveal", "card_ids": shown}, actor=player)
                record.revealed += shown
        elif comp.kind == C.UNTAP:
            plan.do({"type": "tap", "card_ids": [card.id], "tapped": False})
        elif comp.kind == C.PAY_ENERGY and energy_amount(comp, record.x):  # (107.14: remove that many energy counters)
            plan.do({"type": "resource", "player": player, "key": "energy", "delta": -energy_amount(comp, record.x)})
        elif comp.kind in (C.TAP_OTHER, C.WATERBEND, "TAP_POWER"):  # (wave 17B: waterbend 701.67a — tapped to help pay; 17C teamwork)
            if ids:
                plan.do({"type": "tap", "card_ids": ids, "tapped": True})
            record.tapped_for_cost += ids
        elif comp.kind == C.UNTAP_OTHER:  # -- activated sweep (wave 17B) -- 701.26b
            plan.do({"type": "tap", "card_ids": ids, "tapped": False})
        elif comp.kind == C.REMOVE_COUNTER and comp.selector is not None:
            plan.do({"type": "counter", "card_ids": ids, "kind": comp.counter, "delta": -comp.amount})
        elif comp.kind == C.UNATTACH:  # -- granted from object (wave 18F) -- 701.3d: the granting Equipment stays on the battlefield
            plan.do({"type": "detach", "card_ids": ids})
        elif comp.kind == C.SACRIFICE and comp.selector is not None:
            sacrifice += ids
        elif comp.kind == C.DISCARD:
            if comp.random:  # (the choice is recorded as the move, so replays repeat it)
                pool = [c for c in candidates(plan, comp, player, card)]
                need = objects_needed(comp, record.x)  # (wave 25D: "discard X cards at random")
                if len(pool) < need:
                    raise ActionError(f"You can't pay “{comp.text}”")
                ids = secrets.SystemRandom().sample(pool, need)
            if comp.selector is None:  # -- ability words (wave 4F) -- "Discard this card" (channel)
                ids = [card.id]
            if ids:  # (wave 25D: X may be 0, 107.3a: nothing to discard)
                plan.do({"type": "move", "card_ids": ids, "to": {"zone": "graveyard"}})  # 701.9a
            record.discarded += ids
        elif comp.kind == C.EXILE_TO_GY:  # -- if you do (wave 15C) -- each to its owner's graveyard (400.3)
            plan.do({"type": "move", "card_ids": ids, "to": {"zone": "graveyard"}})
        elif comp.kind in (C.EXILE, C.EXILE_FROM_GRAVEYARD, "EXILE_FROM_HAND", C.CRAFT):  # (wave 4I: from the hand, public in exile, 406.3)
            ids = ids if comp.selector is not None or comp.kind == C.CRAFT else [card.id]
            if ids:  # (wave 25D: "exile X cards from your graveyard" with X = 0)
                plan.do({"type": "move", "card_ids": ids, "to": {"zone": "exile"}})
            record.exiled += ids
        elif comp.kind == C.RETURN_PERMANENT:
            ids = ids if comp.selector is not None else [card.id]
            for rid in ids:  # (wave 15E) ninjutsu 702.49c: what the creature attacked, before it leaves combat
                target = plan.state.cards[rid].attacking
                if target is not None:
                    record.returned_attacking[rid] = target.id
            if ids:  # (wave 25D: "return X Swamps" with X = 0)
                plan.do({"type": "move", "card_ids": ids, "to": {"zone": "hand"}})
            record.returned += ids
    if sacrifice:  # 701.21a: to their owners' graveyards, all at once
        from app.rules.triggers import sacrificing  # (the event "whenever you sacrifice …" triggers on)

        sacrificing(plan, sacrifice)
        record.sacrificed_objects += [plan.oid(c) for c in sacrifice]  # (wave 3D: "the sacrificed creature's power", 608.2h)
        plan.do({"type": "move", "card_ids": sacrifice, "to": {"zone": "graveyard"}})
        record.sacrificed += sacrifice
    for comp in library_parts:  # -- activation costs (wave 4H) -- 601.2h: last; 701.17a mill, 701.13a exile
        top = list(plan.state.zones.get(zone_key(player, "library"), [])[: comp.amount])
        if len(top) < comp.amount:
            raise ActionError(f"You can't pay “{comp.text}”")  # (118.3; checked before anything was paid)
        if comp.kind == C.MILL:
            plan.do({"type": "mill", "player": player, "count": comp.amount}, actor=player)
        else:
            plan.do({"type": "move", "card_ids": top, "to": {"zone": "exile"}})
            record.exiled += top
    for comp in cost.components:  # -- if you do (wave 26C) -- "Whenever you forage / collect evidence" (701.61, 701.59): the cost was paid
        if comp.kind in (C.FORAGE, C.COLLECT_EVIDENCE):
            from app.game.rules_state import emit

            emit(plan.state, "designation", counter="forage" if comp.kind == C.FORAGE else "collect_evidence", player=player)


def _flexible_options(plan: Plan, comp: CostComponent, card: CardInstance, player: str,
                      used: set[str]) -> tuple[list[str], bool]:
    """-- activation costs (wave 4H) -- the cards a collect-evidence / forage part may use, and whether it can be paid
    at all (701.59b: total mana value N or more in the graveyard; 701.61a: three graveyard cards or a Food)."""
    gy = [c for c in plan.state.zones.get(zone_key(player, "graveyard"), []) if c != card.id and c not in used]
    if comp.kind == C.COLLECT_EVIDENCE:
        return gy, sum(plan.ch(plan.state.cards[c]).mana_value for c in gy) >= comp.amount
    food = selectors.from_key(C._selector("Food", zone="battlefield") or "")
    foods = [c for c in plan.state.zones.get(zone_key(player, "battlefield"), [])
             if c not in used and (x := plan.state.cards.get(c)) is not None and x.controller == player
             and selectors.matches(plan, food, x, plan.ch(x), player, card.id)]
    return gy + foods, len(gy) >= 3 or bool(foods)


def _flexible_ok(plan: Plan, comp: CostComponent, chosen: list[str]) -> bool:
    if comp.kind == C.COLLECT_EVIDENCE:  # 701.59a: total mana value N or greater
        return bool(chosen) and sum(plan.ch(plan.state.cards[c]).mana_value for c in chosen) >= comp.amount
    zones = {plan.state.cards[c].zone.rsplit(":", 1)[-1] for c in chosen}  # 701.61a: three from the graveyard, or a Food
    return (len(chosen) == 3 and zones == {"graveyard"}) or (len(chosen) == 1 and zones == {"battlefield"})


def _choose_flexible(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp, i: int, comp: CostComponent, cost: AbilityCost,
                     card: CardInstance, what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- activation costs (wave 4H) -- collect evidence N (any number of graveyard cards, total mana value N or more) /
    forage (three graveyard cards, or one Food): one choice of the cards, validated as a whole (601.2h)."""
    options, payable = _flexible_options(plan, comp, card, plan.actor, used)
    if given is not None:
        if len(set(given)) != len(given) or any(c not in options for c in given) or not _flexible_ok(plan, comp, given):
            raise ActionError(f"Those cards don't pay “{comp.text}”")
        chosen = list(given)
    elif not payable:
        raise ActionError(f"You can't pay “{comp.text}”")  # 118.3
    else:
        label = (lambda c: f"{plan.state.cards[c].name or 'Card'} (mana value {plan.ch(plan.state.cards[c]).mana_value:g})") \
            if comp.kind == C.COLLECT_EVIDENCE else (lambda c: plan.state.cards[c].name or "Card")
        decide(plan, player=plan.actor, kind="choose_cards",
               prompt=f"{what}: choose the cards for “{comp.text}”" + (
                   f" (total mana value {comp.amount} or more)" if comp.kind == C.COLLECT_EVIDENCE
                   else " (three cards from your graveyard to exile, or a Food to sacrifice)") + ", or none to cancel",
               options=[DecisionOption(id=c, label=label(c), card_id=c) for c in options],
               min_choices=0, max_choices=len(options) if comp.kind == C.COLLECT_EVIDENCE else 3,
               resume={"step": "ability_cost", "component": i, "amount": None,
                       "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
               source=card)
        return None
    used |= set(chosen)
    return chosen


def _pay_new_part(plan: Plan, comp: CostComponent, card: CardInstance, ids: list[str], record: PaymentRecord) -> bool:
    """-- activation costs (wave 4H) -- pay one of this wave's parts (True), or leave it to :func:`pay` (False)."""
    player = plan.actor
    x = record.x or 0
    if comp.kind == C.REMOVE_COUNTER and (comp.counter == C.ANY_COUNTER or comp.among):  # (among: wave 26C)
        tokens = counter_tokens(plan, list(dict.fromkeys(t.rsplit(":", 2)[0] for t in ids)))
        removed: dict[tuple[str, str], int] = {}
        for t in ids:
            removed[tokens[t]] = removed.get(tokens[t], 0) + 1
        for (cid, kind), n in removed.items():
            plan.do({"type": "counter", "card_ids": [cid], "kind": kind, "delta": -n})
        return True
    if comp.kind == C.REMOVE_COUNTER and comp.x and comp.selector is None:
        if x:
            plan.do({"type": "counter", "card_ids": [card.id], "kind": comp.counter, "delta": -x})
        return True
    if comp.kind == C.PUT_COUNTER:  # 122.6; a cost isn't an effect (614.16: Doubling Season doesn't apply)
        from app.rules import replace

        target = ids[0] if comp.selector is not None else card.id
        replace.put_counters(plan, [(target, comp.counter or "", comp.amount)], by=player, effect=False)
        return True
    if comp.kind in (C.COLLECT_EVIDENCE, C.FORAGE):  # 701.59a / 701.61a: exiled from the graveyard (a Food: pay())
        plan.do({"type": "move", "card_ids": ids, "to": {"zone": "exile"}})
        record.exiled += ids
        return True
    if comp.kind == C.EXERT:  # 701.43a-b: it won't untap during your next untap step (exerted again: the same one)
        plan.rules.exerted[plan.oid(card)] = player
        plan.note(f"{plan.name(player)} exerted {card.name or 'it'}")
        return True
    if comp.kind == C.DISCARD_HAND:  # 701.9a: every card in it (none is fine: Bomat Courier ruling, 2016-09-20)
        hand = list(plan.state.zones.get(zone_key(player, "hand"), []))
        if hand:
            plan.do({"type": "move", "card_ids": hand, "to": {"zone": "graveyard"}})
            record.discarded += hand
        return True
    if comp.kind == C.PAY_LIFE and comp.life_rule is not None:
        amount = life_amount(plan, comp, player)
        if amount is None:
            raise ActionError("You have no commander, so that cost can't be paid (903.4f)")
        if amount:
            plan.do({"type": "life", "player": player, "delta": -amount})
            record.life += amount
        return True
    return False
