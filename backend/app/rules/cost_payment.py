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
from dataclasses import replace
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef, PaymentRecord
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
_VERBS[C.BEHOLD_EXILE] = "exile"
_VERBS[C.BEHOLD] = "behold"  # (wave 17C) 701.4a
_VERBS[C.EXILE_TO_GY] = "put into its owner's graveyard"  # (wave 15C)
_VERBS[C.HAND_TO_TOP] = 'put on top of your library'
_VERBS["HAND_TO_BOTTOM"] = "put on the bottom of your library"  # -- if you do (wave 6F) --  # -- cost changers (wave 4I) -- "exile a blue card from your hand" (alt_costs.py)


def _reserved(cost: AbilityCost, comp: CostComponent, source: CardInstance) -> set[str]:
    """Objects a part can't use because another part of the same cost already does: the source
    when it's tapped ({T}) or leaves (sacrificed / exiled / returned) as part of the cost.
    CR 601.2h: counters may be removed from that source before paying its leave cost."""
    leaves = cost.sacrifice_self or any(c.selector is None and c.kind in (C.EXILE, C.RETURN_PERMANENT, C.EXILE_FROM_GRAVEYARD)
                                        for c in cost.components)
    if (leaves and comp.kind != C.REMOVE_COUNTER) or (comp.kind in (C.TAP_OTHER, C.UNTAP_OTHER, C.WATERBEND) and (cost.tap or cost.untap)):
        return {source.id}
    return set()


def _spoken_for(plan: Plan) -> set[str]:
    """-- nested payment choices (wave 28D) -- while a mana ability's cost is chosen inside a payment prompt (605.3a), the objects the
    spell or ability being paid for already names (its targets, the creatures convoking, what its other costs chose) aren't offered:
    the payment is carried out again from its announcement, which needs them where they were."""
    from app.rules import cost_moves
    held = plan.rules.declaration_cost_reserved
    reserved = {cid for cid in held.objects if cost_moves.reserved(plan.state, held.payer, cid)} if held else set()
    outer = plan.rules.payment_outer
    if outer is None:
        return reserved
    after = (outer.resume or {}).get('paid_then') or {}
    if after.get('do') == 'paid_stage' and after.get('stage') == 'activation_announced':
        return reserved | set((outer.resume or {}).get('exclude') or ())
    if after.get('do') == 'paid_stage' and after.get('stage') in ('declare_attackers', 'declare_blockers', 'cost_moves'):
        # These declarations have exact-object prepared terminals. Their selected
        # creatures are not deferred nonmana costs reserved for a rerun.
        return reserved
    found: set[str] = set(reserved)
    stack: list[Any] = [(outer.resume or {}).get("intent")]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            if v in plan.state.cards:
                found.add(v)
        elif isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
    return found


def withheld(plan: Plan, comp: CostComponent, player: str, source: CardInstance) -> str:
    """-- review 28D -- what ``_spoken_for`` leaves out, said in the prompt or refusal (never silently): sacrificing the spell's own target
    mid-payment is legal (605.3a; the target is then illegal as it resolves, 608.2b), but this payment is replayed from its
    announcement, so here it's offered only before paying (activate the mana ability with priority, then cast)."""
    spoken = _spoken_for(plan)
    held = [c for c in _candidates(plan, comp, player, source) if c in spoken] if spoken else []
    if not held:
        return ""
    names = ", ".join(dict.fromkeys(plan.state.cards[c].name or "a card" for c in held))
    return (f" — not offered: {names} (what you're paying for already uses {'it' if len(held) == 1 else 'them'}; "
            "to use it, cancel and activate this before you start paying)")


def candidates(plan: Plan, comp: CostComponent, player: str, source: CardInstance) -> list[str]:
    """Objects that could pay ``comp`` (one part of a cost), in a stable order."""
    spoken = _spoken_for(plan) | plan.excluded  # (wave 47C: and what an earlier choice of the same resolution takes)
    found = _candidates(plan, comp, player, source)
    return [c for c in found if c not in spoken] if spoken else found


def _candidates(plan: Plan, comp: CostComponent, player: str, source: CardInstance) -> list[str]:
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
    if plan.x_choice is None and comp.selector_x:
        # Availability hints precede X's announcement: some card must be able to
        # pay for some X. Actual payment runs with the announced X and keeps the filter.
        sel = replace(sel, compare=tuple(c for c in sel.compare if not (c[0] == "mv" and c[2] == selectors.X_VALUE)))
        if alt is not None:
            alt = replace(alt, compare=tuple(c for c in alt.compare if not (c[0] == "mv" and c[2] == selectors.X_VALUE)))
    if comp.kind in (C.DISCARD, "EXILE_FROM_HAND", "HAND_TO_BOTTOM", C.HAND_TO_TOP, "REVEAL_FROM_HAND"):  # (EXILE_FROM_HAND: wave 4I, alt_costs.py — Force of Will;
        # HAND_TO_BOTTOM: wave 6F, optional_payment.py)
        zone = zone_key(player, "hand")
    elif comp.kind == C.EXILE and "stack" in sel.zones:
        zone = "stack"
    elif comp.kind in (C.EXILE_FROM_GRAVEYARD, C.COLLECT_EVIDENCE):  # (collect evidence: wave 4H)
        zone = zone_key(player, "graveyard")
    else:
        zone = zone_key(player, "battlefield")
    out = []
    if comp.kind in (C.BEHOLD, C.BEHOLD_EXILE):  # -- static_other sweep (wave 17C) -- 701.4a: a card in your hand (the selector) or a permanent you control (alt)
        for z, s in ((zone_key(player, "hand"), sel), (zone_key(player, "battlefield"), alt)):
            for cid in plan.state.zones.get(z, []):
                card = plan.state.cards.get(cid)
                if card is not None and cid != source.id and (z.endswith(":hand") or (card.controller == player and plan.in_game(card))) \
                        and s is not None and selectors.matches(plan, s, card, plan.ch(card), player, source.id):
                    out.append(cid)
        return out
    if comp.kind == C.EXILE_TO_GY:  # -- if you do (wave 15C) -- a card an opponent owns, face up in exile (406.3), in a stable order
        linked = next((x for x in sel.extras if x == 'source_linked' or x.startswith('source_linked:')), None)
        if linked is not None:
            from app.rules import exiled_with

            ctx = {'controller': player, 'source_card': source.id, 'source_object': plan.oid(source),
                   'borrowed_link_scope': linked.partition(':')[2] or None}
            return [c for c in exiled_with.cards(plan, ctx) if not plan.state.cards[c].is_token]
        pool = [c for pid in plan.state.players if pid != player for c in plan.state.zones.get(zone_key(pid, "exile"), [])]
        return [c for c in pool if (x := plan.state.cards.get(c)) is not None and not x.face_down and x.owner != player
                and selectors.matches(plan, sel, x, plan.ch(x), player, source.id)]
    opponent_counters = comp.kind == C.PUT_COUNTER and sel.controller == "opponent"
    pool = ([cid for pid in plan.live() for cid in plan.state.zones.get(zone_key(pid, "battlefield"), [])]
            if opponent_counters else plan.state.zones.get(zone, []))
    suspended_counter_cost = comp.kind == C.REMOVE_COUNTER and bool(sel.either) and any(
        'suspended' in selectors.from_key(branch).extras for branch in sel.either)
    if suspended_counter_cost:
        pool = [*pool, *plan.state.zones.get(zone_key(player, 'exile'), [])]
    for cid in pool:
        card = plan.state.cards.get(cid)
        if card is None or (card.zone.endswith(":battlefield") and ((card.controller != player and not opponent_counters) or not plan.in_game(card))):
            continue
        if cid == source.id and not zone.endswith(":battlefield"):
            continue  # -- costs (wave 3$) -- a spell's additional cost can't discard / exile the spell being cast (601.2a)
        if not selectors.matches(plan, sel, card, plan.ch(card), player, source.id) and not (
                alt is not None and selectors.matches(plan, alt, card, plan.ch(card), player, source.id)):
            continue
        if comp.named_self and plan.ch(card).name != plan.ch(source).name:  # (wave 4H: grandeur)
            continue
        if comp.kind == C.UNTAP_OTHER and card.counters.get('stun', 0):
            from app.rules import prohibitions

            if prohibitions.cant_remove_counters(plan, cid, 'stun'):
                continue
        if comp.kind == C.REMOVE_COUNTER and removable_counters(plan, card, comp.counter) < (1 if comp.among else comp.amount):  # (any kind: wave 4H; among: 26C)
            continue
        if comp.kind == C.SACRIFICE:
            from app.rules import prohibitions

            if prohibitions.sacrifice_forbidden(plan, card):
                continue
        if comp.kind == C.UNATTACH and not _attached_host(plan, card):
            continue
        if comp.kind == C.SACRIFICE and not plan.resolution_cost:  # -- prohibitions (wave 22B) -- "Players can't … sacrifice creatures to cast
            from app.rules import prohibitions  # spells or activate abilities"

            if prohibitions.sacrifice_banned(plan.state, plan.info, card):
                continue
        if comp.kind == C.PUT_COUNTER:  # -- review 22B -- 614.17b: counters that can't be put can't pay (Solemnity ruling 2017-07-14)
            from app.rules import prohibitions

            if prohibitions.cant_counters(plan, cid, None, comp.counter):
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


def removable_counters(plan: Plan, card: CardInstance, kind: str | None) -> int:
    """Only counters whose removal is possible can pay a cost (614.17b)."""
    from app.rules import prohibitions

    return sum(n for k, n in card.counters.items() if n > 0 and kind in (C.ANY_COUNTER, k)
               and not prohibitions.cant_remove_counters(plan, card.id, k))


def objects_needed(comp: CostComponent, x: int | None) -> int:
    """The objects a chosen part takes: X of them for "Sacrifice X Treasures" (107.3a), else comp.objects."""
    if comp.kind == C.REMOVE_COUNTER and comp.selector is not None and not comp.among:
        return comp.objects
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
            from app.rules import prohibitions

            if prohibitions.cant_remove_counters(plan, cid, kind):
                continue
            for j in range(max(0, n)):
                out[_token(cid, kind, j)] = (cid, kind)
    return out


def _attached_host(plan: Plan, card: CardInstance) -> bool:
    from app.rules import attachments

    return bool(card.zone.endswith(":battlefield") and card.attached_to
                and attachments.host_problem(plan, card, card.attached_to, sba=True) is None)


def _new_part_problem(plan: Plan, comp: CostComponent, card: CardInstance, player: str, x: int | None) -> str | None:
    """118.3 for the parts this wave reads that name no chosen objects (None: payable, or not one of them)."""
    name = card.name or "It"
    if comp.kind == C.UNATTACH and comp.selector is None and not _attached_host(plan, card):
        return f"{name} isn't attached to a legal host"
    if comp.kind == C.REMOVE_COUNTER and comp.selector is None and (comp.x or comp.counter == C.ANY_COUNTER):
        need = (comp.amount if x is None else max(0, x)) if comp.x else comp.amount
        if removable_counters(plan, card, comp.counter) < need:
            what = "counters" if comp.counter == C.ANY_COUNTER else f"{comp.counter} counters"
            return f"{name} doesn't have {need} {what}"
    elif comp.kind == C.REVEAL_SECRET and (plan.rules.secret_choices.get(plan.oid(card)) or [""])[0] != player:  # -- group choices (wave 53D) -- the choice its controller made as it entered
        return f"You didn't choose anything as {name} entered"
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


def _names_fit(plan: Plan, comp: CostComponent, ids: list[str]) -> bool:
    """201.2a–b: nameless objects never qualify; split cards can have several names."""
    from app.rules.card_names import names_of

    if not comp.names:
        return True
    groups = [set(names_of(plan.ch(plan.state.cards[c]))) for c in ids]
    if not groups or any(not g for g in groups):
        return False
    if comp.names == "same":
        return bool(set.intersection(*groups))
    return sum(map(len, groups)) == len(set.union(*groups))


def _names_payable(plan: Plan, comp: CostComponent, ids: list[str], need: int) -> bool:
    """118.3: test availability before offering an activation or paying any component."""
    from collections import Counter

    from app.rules.card_names import names_of

    if not comp.names:
        return len(ids) >= need
    groups = [frozenset(names_of(plan.ch(plan.state.cards[c]))) for c in ids]
    if comp.names == "same":
        counts = Counter(n for g in groups for n in g)
        return any(n >= need for n in counts.values())
    # Equal name sets cannot both occur in a different-names group. Deduplicate them
    # before the bounded search, including when a player owns many identical tokens.
    distinct = list(dict.fromkeys(g for g in groups if g))

    def fit(start: int, left: int, used: frozenset[str]) -> bool:
        if left == 0:
            return True
        for i in range(start, len(distinct) - left + 1):
            g = distinct[i]
            if not used.intersection(g) and fit(i + 1, left - 1, used | g):
                return True
        return False

    return fit(0, need, frozenset())


def problem(plan: Plan, cost: AbilityCost, card: CardInstance, player: str, x: int | None = None) -> str | None:
    """Why the non-mana parts of ``cost`` can't be paid now (118.3), or None. ``x``: the X chosen
    for "Pay X {E}" (unknown yet: 0)."""
    from app.rules import cast_limits  # -- cast limits (wave 5E) --
    from app.rules.casting import summoning_sick  # casting imports this module

    name = card.name or "It"
    from app.rules import (
        opponent_gain_costs44,
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17 / 119.4: "Players can't pay life or sacrifice creatures …"
    )

    if (gain_problem := opponent_gain_costs44.problem(plan, cost, player)) is not None:
        return gain_problem
    for kind, n in cost.remove_counters:
        if n and (why := prohibitions.cant_remove_counters(plan, card.id, kind)):
            return f"{why}: {kind} counters can't be removed from {name}"
    for comp in cost.components:
        from app.rules import counter_x_costs43

        if (counter_x_problem := counter_x_costs43.one_holder_problem(
                plan, comp, card, player, x, tuple(_reserved(cost, comp, card)))) is not None:
            return counter_x_problem
        if comp.kind == C.REMOVE_COUNTER and comp.selector is None and comp.counter != C.ANY_COUNTER:
            need = (x or 0) if comp.x else comp.amount
            if need and (why := prohibitions.cant_remove_counters(plan, card.id, comp.counter or "")):
                return f"{why}: counters can't be removed from {name}"
        if comp.kind == C.REMOVE_COUNTER and comp.x and comp.more and x is not None and x < comp.amount:
            return f"You must remove at least {comp.amount} counter to pay this cost (118.3)"
        if comp.kind == C.PAY_LIFE and (comp.amount or comp.life_rule) and not plan.resolution_cost \
                and (why := prohibitions.life_banned(plan.state, plan.info)):
            return f"{why}: players can't pay life to cast spells or activate abilities"
        if comp.kind == C.PAY_LIFE and (comp.amount or comp.life_rule):  # -- can't lose life (wave 29D) -- 119.8, 614.17b: any payment, a resolving one too
            from app.rules import life_lock

            if (why := life_lock.pay_problem(plan.state, plan.info, player, life_amount(plan, comp, player))):
                return why
        if comp.kind == C.SACRIFICE and comp.selector is None and prohibitions.sacrifice_forbidden(plan, card):
            return f"{name} can't be sacrificed"
        if comp.kind == C.SACRIFICE and comp.selector is None and not plan.resolution_cost \
                and (why := prohibitions.sacrifice_banned(plan.state, plan.info, card)):
            return f"{why}: {name} can't be sacrificed to pay a cost"
        if comp.kind == C.PUT_COUNTER and comp.selector is None and (why := prohibitions.cant_counters(plan, card.id, None, comp.counter)):
            return f"{why}: counters can't be put on {name}"  # -- review 22B -- 614.17b (Solemnity, Devoted Druid)
        if comp.kind == C.UNTAP:  # 107.6: an untapped permanent can't be untapped to pay; 302.6 / 602.5a
            if not card.tapped:
                return f"{name} isn't tapped"
            if card.counters.get("stun", 0) and (why := prohibitions.cant_remove_counters(plan, card.id, "stun")):
                return f"{why}: the stun counter cannot be removed to pay the untap cost"
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
            need = (comp.amount if x is None else max(0, x)) if comp.x else comp.amount
            if sum(removable_counters(plan, plan.state.cards[c], comp.counter) for c in holders) < need:
                return f"You can't pay “{comp.text}”"
        elif comp.selector is not None and comp.kind not in (C.COLLECT_EVIDENCE, C.WATERBEND):  # (collect evidence: _new_part_problem, wave 4H; waterbend: any number, even none)
            usable = [c for c in candidates(plan, comp, player, card) if c not in _reserved(cost, comp, card)]
            if comp.all_objects:
                if set(required_all(plan, comp, player, card)) - set(usable):
                    return f"You can't pay “{comp.text}”" + withheld(plan, comp, player, card)
            elif not _names_payable(plan, comp, usable, objects_needed(comp, x)) and not comp.up_to:  # (X / one permanent for its counters: wave 4H)
                return f"You can't pay “{comp.text}”" + withheld(plan, comp, player, card)
    # -- cast keywords (wave 43D) -- a part paid more than once (a kicker / squad / replicate cost paid twice, escalate's) takes its energy and its
    # objects once for each time (118.3: no partial payments); each object pays one part only (choose)
    energy_total = sum(energy_amount(c, x) for c in cost.components if c.kind == C.PAY_ENERGY)
    if energy_total > plan.state.players[player].resources.get("energy", 0):
        return f"You don't have {energy_total} energy to pay"
    same: dict[tuple[str, str | None], list[CostComponent]] = {}
    for comp in cost.components:
        if comp.selector is not None and not comp.up_to and not comp.all_objects and comp.kind in (C.SACRIFICE, C.DISCARD, C.EXILE_FROM_GRAVEYARD, C.RETURN_PERMANENT,
                                                                         C.TAP_OTHER):
            same.setdefault((comp.kind, comp.selector), []).append(comp)
    for group in same.values():
        if len(group) > 1 and len([c for c in candidates(plan, group[0], player, card) if c not in _reserved(cost, group[0], card)]) \
                < sum(objects_needed(c, x) for c in group):
            return f"You can't pay “{group[0].text}” {len(group)} times"
    return None


def required_all(plan: Plan, comp: CostComponent, player: str, source: CardInstance) -> list[str]:
    """Every matching controlled permanent, before sacrifice prohibitions are applied."""
    assert comp.selector is not None
    sel = selectors.from_key(comp.selector)
    return [cid for cid in selectors.candidates(plan, sel, player, source.id)
            if plan.state.cards[cid].controller == player and plan.state.cards[cid].zone.endswith(":battlefield")
            and plan.in_game(plan.state.cards[cid])]


def choose(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers, cost: AbilityCost, card: CardInstance, what: str, *, compatible_tap: bool = False, counter_first: bool = False, component_excluded: dict[int, set[str]] | None = None) -> dict[int, list[str]] | None:
    """The validated objects for every part of ``cost`` that needs a choice, by component index;
    None while waiting for the payer's (private) choice. Each object pays for one part only."""
    given: dict[int, list[str]] = {}
    for c in a.cost_choices:
        if c.component == C.EITHER_SLOT and isinstance(a, A.CastSpell | A.ActivateAbility):  # -- static wordings (wave 6E) -- (either_costs; wave 43D: equip)
            continue
        if c.component in given:
            raise ActionError("Choose the objects for each part of the cost once")
        given[c.component] = list(c.cards)
    from app.rules import counter_cost_order70

    counter_index = counter_cost_order70.index(cost) if counter_first else None
    parts = dict(cost.choices)
    if set(given) - set(parts):
        raise ActionError("That ability's cost has no such part to choose for")
    out: dict[int, list[str]] = {}
    used: set[str] = set()
    x = getattr(a, "x_value", None)  # (wave 4H: "Sacrifice X Treasures" — X announced as it's activated, 107.3a)
    ordered = sorted(cost.choices, key=lambda item: item[0] != counter_index) if counter_index is not None else cost.choices
    for i, comp in ordered:
        part_used = used
        if counter_index is not None and comp.kind == C.REMOVE_COUNTER:
            part_used = {resource for j, resources in out.items() for resource in resources}
        if comp.kind == C.OPPONENT_GAIN_LIFE:
            from app.rules import opponent_gain_costs44

            if not isinstance(a, A.CastSpell):
                raise ActionError('That opponent-gain cost is not supported for this action')
            gained = opponent_gain_costs44.choose(plan, a, i, comp, card, given.get(i), what)
            if gained is None:
                if counter_index is not None:
                    counter_cost_order70.retain_choice72(plan, cost, out)
                return None
            out[i] = gained
            continue
        if comp.kind == C.WATERBEND:  # -- activated sweep (wave 17B) -- up to N artifacts / creatures, each paying {1} (701.67a)
            found = _choose_waterbend(plan, a, i, comp, cost, card, what, given.get(i), used)
        elif comp.kind == "TAP_POWER":  # -- static_other sweep (wave 17C) -- one choice of creatures, validated as a whole
            found = _choose_power(plan, a, i, comp, cost, card, what, given.get(i), used)
        elif comp.kind == C.CRAFT:  # -- casting extras (wave 18E) -- the materials: one choice of at least ``amount`` objects
            found = _choose_craft(plan, a, i, comp, cost, card, what, given.get(i), used)
        elif comp.anyn:  # -- cost reductions paid with objects (wave 47C) -- any number, none too
            found = _choose_any(plan, a, i, comp, cost, card, what, given.get(i), part_used)
        if comp.kind in (C.WATERBEND, "TAP_POWER", C.CRAFT) or comp.anyn:
            if found is None:
                if counter_index is not None:
                    counter_cost_order70.retain_choice72(plan, cost, out)
                return None
            out[i] = found
            if counter_index is not None and comp.kind == C.REMOVE_COUNTER:
                used |= set(found) | {token.rsplit(":", 2)[0] for token in found}
            continue
        if comp.counter == C.ANY_COUNTER or comp.among or comp.kind in (C.COLLECT_EVIDENCE, C.FORAGE):  # -- activation costs (wave 4H) --
            chooser = _choose_counters if comp.counter == C.ANY_COUNTER or comp.among else _choose_flexible
            found = chooser(plan, a, i, comp, cost, card, what, given.get(i), part_used)
            if found is None:
                if counter_index is not None:
                    counter_cost_order70.retain_choice72(plan, cost, out)
                return None
            out[i] = found
            if counter_index is not None and comp.kind == C.REMOVE_COUNTER:
                used |= set(found) | {token.rsplit(":", 2)[0] for token in found}
            continue
        need = objects_needed(comp, x)
        blocked = used
        if compatible_tap:
            blocked = {cid for j, ids in out.items() for cid in ids
                       if not ({comp.kind, parts[j].kind} & {C.TAP_OTHER} and
                               {comp.kind, parts[j].kind} & {C.SACRIFICE, C.RETURN_PERMANENT})}
        candidate_plan = plan
        if counter_index is not None and counter_cost_order70.fixed_sacrifice(comp):
            # Counter tokens and a sacrifice consume different resources. Other objects
            # remain reserved; a holder cannot satisfy two sacrifice components.
            candidate_plan = counter_cost_order70.preview(plan, cost, out)
            removed_holders = {token.rsplit(':', 2)[0] for token in out[counter_index]}
            other_claims = {cid for j, ids in out.items() if j != counter_index for cid in ids}
            blocked = (used - removed_holders) | other_claims
        usable = [c for c in candidates(candidate_plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card)
                  and c not in blocked and c not in (component_excluded or {}).get(i, set())]
        if comp.all_objects:
            required = required_all(candidate_plan, comp, plan.actor, card)
            if set(required) - set(usable):
                raise ActionError(f"You can't pay “{comp.text}”")
            need = len(required)
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
        elif len(usable) == need and not comp.up_to and not withheld(plan, comp, plan.actor, card):  # (review 28D: something left out: asked, with the note)
            chosen = usable  # (no choice to make)
        else:
            verb = _VERBS.get(comp.kind, "use")
            decide(plan, player=plan.actor, kind="choose_cards",
                   prompt=f"{what}: choose {'up to ' if comp.up_to else ''}{need} to {verb} (“{comp.text}”), or "
                          + ("none to pay without" if comp.up_to else "none to cancel") + withheld(plan, comp, plan.actor, card),
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in usable],
                   min_choices=0, max_choices=need,
                   resume={"step": "ability_cost", "component": i, "amount": None if comp.up_to else need, "empty_ok": comp.up_to,
                           "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
                   source=card)
            if counter_index is not None:
                counter_cost_order70.retain_choice72(plan, cost, out)
            return None
        if not _names_fit(candidate_plan, comp, list(chosen)):
            raise ActionError(f"Choose objects satisfying “{comp.text}”")  # 601.2h: no partial payments
        out[i] = list(chosen)
        used |= set(chosen)
    return out


def _choose_waterbend(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers, i: int, comp: CostComponent, cost: AbilityCost,
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


def _choose_any(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers, i: int, comp: CostComponent, cost: AbilityCost, card: CardInstance,
                what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- cost reductions paid with objects (wave 47C) -- "you may sacrifice any number of creatures. This spell costs {2} less to cast for each" (601.2b): the payer picks
    any number of the objects, none too; the cost is worked out from the pick (``reduction``, 601.2f) and paid with the rest (601.2h). Cards of the hand are asked
    about even when there are none, so that skipping the question doesn't tell the others what the hand holds."""
    usable = [c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
    shown = {c: (c, plan.state.cards[c].name or "Card") for c in usable}
    if comp.among:  # (counters: each one is a pick, 122.1 — "Remove any number of +1/+1 counters from among creatures you control")
        shown = {t: (cid, f"{kind} counter on {plan.state.cards[cid].name or 'it'}") for t, (cid, kind) in counter_tokens(plan, usable).items()
                 if comp.counter in (C.ANY_COUNTER, kind) and t not in used}
        usable = list(shown)
    if given is not None:
        if len(set(given)) != len(given) or any(c not in usable for c in given) or (comp.more and len(given) < comp.amount):
            raise ActionError(f"Choose from what can pay “{comp.text}”")
        used |= set(given)
        return list(given)
    if comp.more and len(usable) < comp.amount:  # (wave 48B: "one or more": at least one, 118.3)
        raise ActionError(f"You can't pay “{comp.text}”")
    if not usable and comp.kind != "EXILE_FROM_HAND":
        return []
    decide(plan, player=plan.actor, kind="choose_cards",
           prompt=f"{what}: choose {'one or more' if comp.more else 'any number'} to {_VERBS.get(comp.kind, 'use')} (“{comp.text}”)"
                  + (f", each taking {{{comp.reduces}}} off the cost" if comp.reduces else "") + (", or none to cancel" if comp.more else ", or none"),
           options=[DecisionOption(id=t, label=label, card_id=cid) for t, (cid, label) in shown.items()],
           min_choices=0, max_choices=len(usable),
           resume={"step": "ability_cost", "component": i, "amount": None, "empty_ok": not comp.more,
                   "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
           source=card)
    return None


def reduction(cost: AbilityCost, chosen: dict[int, list[str]]) -> int:
    """-- cost reductions paid with objects (wave 47C) -- 601.2f: the generic mana the objects chosen for the parts that reduce the total cost take off it."""
    return sum(c.reduces * len(chosen.get(i, [])) for i, c in enumerate(cost.components))


def _choose_power(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers, i: int, comp: CostComponent, cost: AbilityCost, card: CardInstance,
                  what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- static_other sweep (wave 17C) -- teamwork N (702.194a): any number of untapped creatures you control with total power N or
    more; the payer picks them (validated as a whole, 601.2h)."""
    options = [c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
    total = lambda ids: sum(power(plan.state.cards[c], plan.ch(plan.state.cards[c])) or 0 for c in ids)  # noqa: E731
    if given is not None:
        if len(set(given)) != len(given) or any(c not in options for c in given) or total(given) < comp.amount:
            raise ActionError(f"Those creatures don't pay “{comp.text}”")
        chosen = list(given)
    elif sum(max(0, power(plan.state.cards[c], plan.ch(plan.state.cards[c])) or 0) for c in options) < comp.amount:
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


def _choose_craft(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers, i: int, comp: CostComponent, cost: AbilityCost, card: CardInstance,
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


def _choose_counters(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers, i: int, comp: CostComponent, cost: AbilityCost,
                     card: CardInstance, what: str, given: list[str] | None, used: set[str]) -> list[str] | None:
    """-- activation costs (wave 4H) -- "Remove two counters from this creature" / "Remove a counter from a creature you
    control": the payer picks the counters (122.1: any kinds; one permanent). Counters are public, but the pick is still
    the payer's own decision. Nothing moves until the whole cost is paid (601.2h)."""
    holders = [card.id] if comp.selector is None else [
        c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
    tokens = {token: pair for token, pair in counter_tokens(plan, holders).items() if token not in used}
    need = max(0, getattr(a, "x_value", None) or 0) if comp.x else comp.amount
    if comp.among:  # -- activated sweep (wave 26C) -- "from among creatures you control": each counter of that kind on any of them (122.1)
        need = max(0, getattr(a, "x_value", None) or 0) if comp.x else comp.amount
        tokens = {t: v for t, v in tokens.items() if comp.counter == C.ANY_COUNTER or v[1] == comp.counter}
    if given is not None:
        if len(given) != need or len(set(given)) != len(given) or any(t not in tokens for t in given) \
                or (need > 0 and not comp.among and len({tokens[t][0] for t in given}) != 1):
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
                       "counter_objects": {cid: ObjectRef(card=cid, object_id=plan.oid(cid), zone=plan.state.cards[cid].zone).model_dump(mode='json')
                                           for cid in dict.fromkeys(cid for cid, _ in tokens.values())},
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
        if d.resume.get('declaration_decision') is not None:
            from app.game.rules_state import Decision
            plan.rules.decision = Decision.model_validate(d.resume['declaration_decision'])
        else:
            plan.hold = d.player
        return
    if d.resume["amount"] is not None and len(chosen) != d.resume["amount"]:  # (None: validated as a whole, wave 4H)
        raise ActionError(f"Choose {d.resume['amount']}")
    if d.resume.get('hybrid_power_up71') is not None:
        from app.rules import hybrid_power_up71

        hybrid_power_up71.guard_source(plan, d.resume['hybrid_power_up71'])
    if d.resume.get('counter_objects'):
        for token in chosen:
            cid = token.rsplit(':', 2)[0]
            raw = d.resume['counter_objects'].get(cid)
            ref = ObjectRef.model_validate(raw) if raw is not None else None
            current = plan.state.cards.get(cid)
            if ref is None or current is None or plan.oid(current) != ref.object_id or current.zone != ref.zone:
                raise ActionError('The selected counter holder is no longer the original object')
    saved_counter72 = d.resume.get("counter_choice72")
    if saved_counter72 is not None:
        from app.rules import counter_cost_order70

        counter_cost_order70.guard_original(plan, [ObjectRef.model_validate(ref) for ref in saved_counter72["originals"]] if saved_counter72.get("originals") is not None else None)
    intent = A.parse_action(d.resume["intent"])
    assert isinstance(intent, A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers)
    if saved_counter72 is not None and not any(c.component == saved_counter72["component"] for c in intent.cost_choices):
        intent.cost_choices.append(A.CostChoice(component=saved_counter72["component"], cards=saved_counter72["tokens"]))
    intent.cost_choices = [*intent.cost_choices, A.CostChoice(component=d.resume["component"], cards=chosen)]
    plan.rules.passed = []
    if isinstance(intent, A.DeclareAttackers | A.DeclareBlockers):
        from app.game.rules_state import Decision
        plan.rules.decision = Decision.model_validate(d.resume['declaration_decision'])
    INTENTS[intent.type](plan, intent)


def excluded(cost: AbilityCost, card: CardInstance, chosen: dict[int, list[str]]) -> tuple[str, ...]:
    """Permanents that can't also pay mana: the source when it taps, untaps or leaves as part of
    the cost, and every object chosen for another part (it's sacrificed, tapped, returned …)."""
    out = [c for i, ids in chosen.items() if cost.components[i].kind != C.OPPONENT_GAIN_LIFE for c in ids]
    source_part = any(c.selector is None and c.kind in (C.REMOVE_COUNTER, C.PUT_COUNTER, C.REVEAL_SELF, C.DISCARD)
                      for c in cost.components)
    if cost.tap or cost.untap or bool(cost.loyalty) or cost.loyalty_x or any(n > 0 for _, n in cost.remove_counters) or source_part or _reserved(cost, CostComponent(C.OTHER), card):
        out.append(card.id)
    return tuple(dict.fromkeys(out))


def pay(plan: Plan, cost: AbilityCost, card: CardInstance, chosen: dict[int, list[str]], record: PaymentRecord) -> None:
    """Carry out the non-mana parts other than {T}, loyalty, life and the source's own counters
    (the caller pays those as before), recording what was used (the payment record)."""
    player = plan.actor
    # Individual counters are named before any component removes them. Later
    # components must use that original mapping rather than renumbered tokens.
    picked_tokens72 = [token for i, part in enumerate(cost.components)
                       if part.kind == C.REMOVE_COUNTER and (part.counter == C.ANY_COUNTER or part.among)
                       for token in chosen.get(i, [])]
    counter_map72 = counter_tokens(plan, list(dict.fromkeys(token.rsplit(":", 2)[0] for token in picked_tokens72)))
    if len(set(picked_tokens72)) != len(picked_tokens72) or any(token not in counter_map72 for token in picked_tokens72):
        raise ActionError("Each selected original counter can pay only once")
    sacrifice: list[str] = [card.id] if cost.sacrifice_self else []
    library_parts: list[CostComponent] = []  # (wave 4H) 601.2h: moving cards out of the library is paid last
    for i, comp in enumerate(cost.components):
        ids = chosen.get(i, [])
        if comp.kind in (C.MILL, C.EXILE_LIBRARY):
            library_parts.append(comp)
        elif comp.kind == C.FORAGE and ids and plan.state.cards[ids[0]].zone.endswith(":battlefield"):
            sacrifice += ids  # (wave 4H) 701.61a: the Food, sacrificed with the cost's other sacrifices
        elif _pay_new_part(plan, comp, card, ids, record, counter_map72):  # -- activation costs (wave 4H) --
            continue
        elif comp.kind == 'REVEAL_HAND':
            shown = list(plan.state.zones.get(zone_key(player, 'hand'), []))
            from app.rules import mana_named_land_profiles

            mana_named_land_profiles.register_reveal(plan, record.card, shown)
            if shown:
                plan.do({'type': 'reveal', 'card_ids': shown}, actor=player)
                record.revealed += shown
            from app.rules import payment_card_facts

            payment_card_facts.record(plan, record, 'revealed', shown)
        elif comp.kind == C.REVEAL_SELF:  # -- forecast (wave 24C) -- 702.57a: shown to everyone (701.20a: in the log), then hidden again: the card
            plan.do({"type": "reveal", "card_ids": [card.id]}, actor=player)  # stays in the hand and a reveal doesn't last
            plan.do({"type": "hide", "card_ids": [card.id]}, actor=player)
            record.revealed.append(card.id)
            from app.rules import payment_card_facts

            payment_card_facts.record(plan, record, "revealed", [card.id])
        elif comp.kind in ("REVEAL_FROM_HAND", C.BEHOLD):  # -- static_other sweep (wave 17C) -- revealed to everyone (701.20a); a beheld permanent just is
            shown = [c for c in ids if plan.state.cards[c].zone.endswith(":hand")]
            if shown:
                if comp.kind == 'REVEAL_FROM_HAND' and comp.x:
                    from app.rules import mana_named_land_profiles

                    mana_named_land_profiles.register_reveal(plan, record.card, shown)
                plan.do({"type": "reveal", "card_ids": shown}, actor=player)
                record.revealed += shown
                from app.rules import payment_card_facts

                payment_card_facts.record(plan, record, "revealed", shown)
        elif comp.kind == C.UNTAP:
            from app.rules import keyword_actions

            ids_to_untap = keyword_actions.untap_stunned(plan, [card.id], player)
            if ids_to_untap:
                plan.do({"type": "tap", "card_ids": ids_to_untap, "tapped": False})
        elif comp.kind == C.PAY_ENERGY and energy_amount(comp, record.x):  # (107.14: remove that many energy counters)
            plan.do({"type": "resource", "player": player, "key": "energy", "delta": -energy_amount(comp, record.x)})
        elif comp.kind in (C.TAP_OTHER, C.WATERBEND, "TAP_POWER"):  # (wave 17B: waterbend 701.67a — tapped to help pay; 17C teamwork)
            if ids:
                plan.do({"type": "tap", "card_ids": ids, "tapped": True})
            record.tapped_for_cost += ids
            record.tapped_objects += [plan.oid(c) for c in ids]  # (review 26C: last known information, 608.2h)
        elif comp.kind == C.UNTAP_OTHER:  # -- activated sweep (wave 17B) -- 701.26b
            from app.rules import keyword_actions

            ids_to_untap = keyword_actions.untap_stunned(plan, ids, player)
            if ids_to_untap:
                plan.do({"type": "tap", "card_ids": ids_to_untap, "tapped": False})
        elif comp.kind == C.REMOVE_COUNTER and comp.selector is not None:
            from app.rules import counter_removal_results

            for cid in ids:
                if counter_removal_results.remove(plan, cid, comp.counter or "", comp.amount, by=player) != comp.amount:
                    raise ActionError("The selected counters cannot pay this cost")
        elif comp.kind == C.UNATTACH:  # -- granted from object (wave 18F) -- 701.3d: the granting Equipment stays on the battlefield
            plan.do({"type": "detach", "card_ids": ids if comp.selector is not None else [card.id]})
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
            from app.rules import payment_card_facts

            payment_card_facts.record(plan, record, "discarded", ids)
            record.discarded += ids
            record.discarded_objects += [plan.oid(cid) for cid in ids]
            record.discarded_mana_values.update({plan.oid(cid): int(plan.ch(plan.state.cards[cid]).mana_value) for cid in ids})
        elif comp.kind == C.EXILE_TO_GY:  # -- if you do (wave 15C) -- each to its owner's graveyard (400.3)
            plan.do({"type": "move", "card_ids": ids, "to": {"zone": "graveyard"}})
            if comp.selector and any(x == 'source_linked' or x.startswith('source_linked:') for x in selectors.from_key(comp.selector).extras):
                from app.rules import card_names

                record.moved_exile_names = [*(record.moved_exile_names or []),
                    *(name for cid in ids if cid in plan.state.cards for name in card_names.names_of(plan.ch(plan.state.cards[cid])))]
        elif comp.kind in (C.EXILE, C.EXILE_FROM_GRAVEYARD, "EXILE_FROM_HAND", C.CRAFT, C.BEHOLD_EXILE):  # (wave 4I: from the hand, public in exile, 406.3)
            if comp.kind == C.BEHOLD_EXILE:
                shown = [cid for cid in ids if plan.state.cards[cid].zone.endswith(':hand')]
                if shown:
                    plan.do({'type': 'reveal', 'card_ids': shown}, actor=player)
                    record.revealed += shown
            ids = ids if comp.selector is not None or comp.kind == C.CRAFT else [card.id]
            from app.rules import payment_card_facts

            stack_exile = comp.kind == C.EXILE and comp.selector is not None and "stack" in selectors.from_key(comp.selector).zones
            if stack_exile:
                payment_card_facts.record(plan, record, "exiled", ids)
            was = [plan.oid(c) for c in ids]  # (wave 48B)
            if ids:  # (wave 25D: "exile X cards from your graveyard" with X = 0)
                plan.do({"type": "move", "card_ids": ids, "to": {"zone": "exile"}})
            record.exiled += ids
            record.exiled_was += was
            record.exiled_objects += [plan.oid(c) for c in ids]  # (-- as long as (wave 37A) -- 400.7j: the new objects)
            from app.rules import payment_card_facts

            if not stack_exile:
                payment_card_facts.record(plan, record, "exiled", ids)
        elif comp.kind == C.EXILE_TOP_OWN_GY:
            from app.rules import fixed_top_graveyard_cost46

            fixed_top_graveyard_cost46.pay(plan, card, record)
        elif comp.kind == C.HAND_TO_TOP:
            from app.rules import ordered_zone_costs46

            ordered_zone_costs46.pay_hand_to_top(plan, ids, player)
        elif comp.kind == C.RETURN_PERMANENT:
            ids = ids if comp.selector is not None else [card.id]
            record.returned_objects = [*(record.returned_objects or []), *(plan.oid(cid) for cid in ids)]
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
            from app.rules import replace as _replace_mill  # (wave 28B: 701.17a)

            more = sum(k for _, k in _replace_mill.mill_counts(plan, [(player, comp.amount)]) or [(player, comp.amount)])
            milled = list(plan.state.zones.get(zone_key(player, "library"), [])[:more])
            old_objects = {cid: plan.oid(cid) for cid in milled}
            plan.do({"type": "mill", "player": player, "count": min(more, len(plan.state.zones.get(zone_key(player, "library"), [])))},
                    actor=player)
            from app.rules import payment_card_facts

            payment_card_facts.record(plan, record, "milled", [cid for cid in milled
                if cid in plan.state.cards and plan.oid(cid) != old_objects[cid]])
        else:
            was = [plan.oid(cid) for cid in top]
            plan.do({"type": "move", "card_ids": top, "to": {"zone": "exile"}})
            record.exiled += top
            record.exiled_was += was
            record.exiled_objects += [plan.oid(cid) for cid in top]
            from app.rules import payment_card_facts

            payment_card_facts.record(plan, record, "exiled", top)
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


def _choose_flexible(plan: Plan, a: A.ActivateAbility | A.CastSpell | A.TurnFaceUp | A.DeclareAttackers | A.DeclareBlockers, i: int, comp: CostComponent, cost: AbilityCost,
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


def _pay_new_part(plan: Plan, comp: CostComponent, card: CardInstance, ids: list[str], record: PaymentRecord, counter_map72: dict[str, tuple[str, str]] | None = None) -> bool:
    """-- activation costs (wave 4H) -- pay one of this wave's parts (True), or leave it to :func:`pay` (False)."""
    player = plan.actor
    x = record.x or 0
    if comp.kind == C.OPPONENT_GAIN_LIFE:
        if ((comp.gain_scope != 'each_other_player' and len(ids) != 1)
                or len(ids) != len(set(ids))
                or any(not any(r.recipient == pid and r.nominal_amount == comp.amount for r in record.opponent_gain_costs) for pid in ids)):
            raise ActionError('The opponent-gain cost has not been paid')
        return True
    if comp.kind == C.REMOVE_COUNTER and (comp.counter == C.ANY_COUNTER or comp.among):  # (among: wave 26C)
        tokens = counter_map72 if counter_map72 is not None else counter_tokens(plan, list(dict.fromkeys(t.rsplit(":", 2)[0] for t in ids)))
        removed: dict[tuple[str, str], int] = {}
        for t in ids:
            removed[tokens[t]] = removed.get(tokens[t], 0) + 1
        for (cid, kind), n in removed.items():
            from app.rules import counter_removal_results

            if counter_removal_results.remove(plan, cid, kind, n, by=player) != n:
                raise ActionError("The selected counters cannot pay this cost")
        return True
    if comp.kind == C.REMOVE_COUNTER and comp.x and comp.selector is None:
        if x:
            from app.rules import counter_removal_results

            counter_removal_results.remove(plan, card.id, comp.counter or "", x, by=player)
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
    if comp.kind == C.REVEAL_SECRET:  # -- group choices (wave 53D) -- 701.20a: shown to all players as the cost is paid; the choice itself stays (it is read by the ability's effect)
        value = plan.rules.secret_choices[plan.oid(card)][1]
        plan.note(f"{plan.name(player)} reveals the {'player' if value in plan.state.players else 'creature type'} they chose for {card.name or 'it'}: "
                  f"{plan.name(value) if value in plan.state.players else value}", actor=player)
        return True
    if comp.kind == C.EXERT:  # 701.43a-b: it won't untap during your next untap step (exerted again: the same one)
        from app.rules import exert

        exert.perform(plan, card, player)
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
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(player, amount)])
            record.life += amount
        return True
    return False
