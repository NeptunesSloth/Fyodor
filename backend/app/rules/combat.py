"""Combat (milestone 15c): declaring attackers and blockers, and combat damage.

The attack/block markers on the table are the visible truth (a manual override that removes a
marker takes the creature out of combat). Rules state only remembers which attackers became
blocked (they stay blocked even if the blocker leaves), whether anyone attacked at all, and
whether first-strike damage has been dealt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, note_block
from app.game.state import CardInstance, GameState, zone_key
from app.rules import banding, protection, replace, scripts, selectors, wave110a_choosers, wave110f_cards
from app.rules import characteristics as chars
from app.rules import mana as M
from app.rules.casting import summoning_sick
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.layers import LAND_TYPES
from app.rules.plan import Plan, decide, live_players
from app.rules.sba import power, toughness
from app.rules.statics import rule_arg, rule_selectors
from app.rules.world_durations80 import native as world_native80

Round = Literal["only", "first", "second"]


# -- legality -------------------------------------------------------------------------
def attack_problem(state: GameState, card: CardInstance, ch: Characteristics) -> str | None:
    if not card.zone.endswith(":battlefield") or not ch.is_creature:
        return "Only creatures on the battlefield can attack"
    if card.controller != state.turn.active_player:
        return "Only the active player's creatures can attack"
    if card.tapped:
        return f"{ch.name} is tapped"
    rules = scripts.statics(ch)
    # -- conditional statics (wave 4B) -- "can attack as though it didn't have defender" (702.3b)
    from app.rules import previous_own_turns
    if "defender" in ch.keywords and "attack_despite_defender" not in rules:
        conditional = any(r.startswith(previous_own_turns.DEFENDER + ':') for r in rules)
        if not conditional or not previous_own_turns.eligible_player(state, card.controller):
            return f"{ch.name} has defender"
    if previous_own_turns.ATTACK in rules and previous_own_turns.attacked(state, card) is not False:
        return f"{ch.name} can't attack after attacking during its controller's last turn"
    if {"cant_attack", "cant_attack_or_block"} & rules:
        return f"{ch.name} can't attack"
    if state.rules is not None and state.rules.combat_tag == "only_land" and not ch.is_land:  # -- as long as (wave 100K) -- Bumi's combat phase
        return f"{ch.name} isn't a land creature: only land creatures can attack during this combat phase"
    if state.rules is not None and state.rules.combat_tag.startswith("only:") and state.rules.object_id(card.id) not in state.rules.combat_tag[5:].split(","):
        return f"{ch.name} isn't one of the chosen creatures: only they can attack during this combat phase"  # -- extra combat (wave 110D) --
    if state.rules is not None and any(e[0] == state.turn.number and e[1] == card.controller and state.rules.object_id(card.id) not in e[2] for e in state.rules.attack_piles):
        return f"{ch.name} is not in the pile chosen (700.3)"  # -- piles (wave 53D) -- Fight or Flight
    if "haste" not in ch.keywords and "attack_as_haste" not in rules and summoning_sick(state, card):  # (wave 100F: "can attack as though it had haste", 302.6)
        return f"{ch.name} has summoning sickness"
    return None


def block_problem(state: GameState, blocker: CardInstance, bch: Characteristics, attacker: CardInstance,
                  ach: Characteristics, info: CardInfo | None = None) -> str | None:
    if not blocker.zone.endswith(":battlefield") or not bch.is_creature:
        return "Only creatures on the battlefield can block"
    if blocker.tapped and "block_tapped" not in scripts.statics(bch):  # (wave 42A: Masako, "can block as though it were untapped", 509.1a)
        return f"{bch.name} is tapped"
    if {"cant_block", "cant_attack_or_block"} & scripts.statics(bch):
        return f"{bch.name} can't block"
    if "cant_block_if_goaded" in scripts.statics(bch):
        from app.rules.keyword_actions import goaded_by

        if goaded_by(bch):
            return f"{bch.name} is goaded and can't block"
    if "decayed" in bch.keywords:  # -- token & pump wordings (wave 6C) -- 702.147a: "This creature can't block."
        return f"{bch.name} has decayed: it can't block"
    if "cant_be_blocked" in scripts.statics(ach):
        return f"{ach.name} can't be blocked"
    # rules of the attacker about its blockers (evasion, 509.1b: flying is one of them) and of the
    # blocker about what it may block (app/rules/statics.py has the vocabulary), each evaluated
    # against the other creature in the block
    blocker_rules = scripts.statics(bch)
    for rule in sorted(evasion_rules(ach)):
        name, arg = rule_arg(rule)
        if name == "cant_be_blocked_by" and _any_selector(state, info, arg, blocker, bch, attacker):
            return f"{ach.name} can't be blocked by {_phrase(arg)}"
        if rule == KEYWORD_RULES["flying"] and "Dragon" in ach.subtypes and "block_dragons_reach" in blocker_rules:
            continue  # 609.4: reach for blocking this Dragon; not a granted ability.
        if name == "cant_be_blocked_except_by" and not _any_selector(state, info, arg, blocker, bch, attacker):
            return f"{ach.name} can't be blocked except by {_phrase(arg)}"
        if name == "cant_be_blocked_by_power" and (_power(bch) < _power(ach) if arg == "less" else _power(bch) > _power(ach)):
            return f"{ach.name} can't be blocked by creatures with {arg} power"
        if name == "cant_be_blocked_by_power_count" and info is not None:
            from app.rules import values
            who, _, key = arg.partition(":")
            count = values.evaluate(Plan.view(state, blocker.controller, info), {"controller": who}, {"count": key})
            if _power(bch) < count:
                return f"{ach.name} can't be blocked by creatures with power less than {count}"
        if name == "cant_be_blocked_unless_defender" and not _defender_condition(state, info, arg, blocker.controller):
            return f"{ach.name} can't be blocked unless the defending player's creatures meet its condition"
        if name == "cant_be_blocked_if_defender_controls" and _defender_controls(state, info, arg, blocker.controller):
            return f"{ach.name} can't be blocked while {state.players[blocker.controller].name} controls {_phrase(arg)}"
        if name == "cant_be_blocked_if_defender" and _defender_condition(state, info, arg, blocker.controller):  # -- as long as (wave 25A) --
            return f"{ach.name} can't be blocked while {state.players[blocker.controller].name} {arg.split(':')[0].replace('count', 'controls').replace('most', 'controls the most').replace('monarch', 'is the monarch')}"
        if name == "cant_be_blocked_by_if_defender":
            fact, _, sels = arg.partition("@@")
            if _defender_condition(state, info, fact, blocker.controller) and _any_selector(state, info, sels, blocker, bch, attacker):
                return f"{ach.name} can't be blocked by {_phrase(sels)} while {state.players[blocker.controller].name} meets the condition"
    for rule in sorted(scripts.statics(bch)):
        name, arg = rule_arg(rule)
        if name == "block_only" and not _any_selector(state, info, arg, attacker, ach, blocker):
            return f"{bch.name} can block only {_phrase(arg)}"
        if name == "cant_block_unless_more" and not _controls_more(state, info, arg.partition(":")[2], blocker.controller, attacker.controller):
            return f"{bch.name} can't block unless its controller controls more of them than the attacking player"  # (wave 21A)
        if name == "cant_block_sel" and _any_selector(state, info, arg, attacker, ach, blocker):
            return f"{bch.name} can't block {_phrase(arg)}"
        if name == "cant_block_power":
            if arg == "greater" and _power(ach) > _power(bch):
                return f"{bch.name} can't block creatures with greater power"
            if arg == "at_least_toughness":
                limit = toughness(blocker, bch)
                if limit is None or _power(ach) >= limit:
                    return f"{bch.name} can't block creatures whose power is at least its toughness"
        # -- block effects (wave 7E) -- "Target creature can't block this creature this turn" (app/rules/block_effects.py)
        if name == "cant_block_obj" and state.rules is not None and arg == state.rules.object_id(attacker.id):
            return f"{bch.name} can't block {ach.name} this turn"
    from app.rules import combat_rules  # -- combat (wave 5C) -- "can't block creatures you control"

    found = combat_rules.block_problem(state, blocker, bch, attacker, info)
    if found:
        return found
    # landwalk (702.14): unblockable while the defending player controls a land of that type
    for walk, land in LANDWALK.items():
        # (wave 26A: Great Wall, "Creatures with plainswalk can be blocked as though they didn't have plainswalk": the ability's
        # restriction is not applied, 702.14 / 509.1b)
        if (walk in ach.keywords and f"ignore_landwalk:{walk}" not in ach.imposed
                and "ignore_landwalk:all" not in ach.imposed and "block_landwalk" not in blocker_rules
                and _controls_land(state, blocker.controller, land, info)):
            return f"{ach.name} has {walk}: it can't be blocked while you control a {land}"
    if "shadow" in ach.keywords and "shadow" not in bch.keywords and "block_shadow" not in blocker_rules:
        return f"{ach.name} has shadow: only creatures with shadow can block it"
    if "shadow" in bch.keywords and "shadow" not in ach.keywords:
        return f"{bch.name} has shadow: it can only block creatures with shadow"
    if "horsemanship" in ach.keywords and "horsemanship" not in bch.keywords:
        return f"{ach.name} has horsemanship: only creatures with horsemanship can block it"
    if "fear" in ach.keywords and not ("Artifact" in bch.types or "B" in bch.colors):
        return f"{ach.name} has fear: only artifact and/or black creatures can block it"
    if "intimidate" in ach.keywords and not ("Artifact" in bch.types or ach.colors & bch.colors):
        return f"{ach.name} has intimidate: only artifact creatures and creatures that share a color with it can block it"
    if "skulk" in ach.keywords and _power(bch) > _power(ach):
        return f"{ach.name} has skulk: creatures with greater power can't block it"
    # -- counters & designations (wave 3E): the Ring-bearer's evasion (701.54c) --
    from app.rules import designations

    ring = designations.ring_block_problem(state, attacker, _power(ach), _power(bch))
    if ring:
        return ring
    if protection.protected_from(ach, bch):
        return f"{ach.name} has protection: {bch.name} can't block it"
    return None


def _power(ch: Characteristics) -> int:
    if ch.pt is not None:
        return ch.pt[0]
    try:
        return int(ch.power or 0)
    except ValueError:
        return 0


# Evasion keywords the engine reads as the rules the wording grammar produces (702.9b flying: "can't
# be blocked except by creatures with flying and/or reach"; 702.111b menace: "except by two or more
# creatures"). Shadow, horsemanship, fear, intimidate, skulk and landwalk aren't selector vocabulary
# and are checked by name in block_problem.
_FLYING_OR_REACH = "|".join(selectors.Selector(types=("Creature",), with_keywords=(kw,)).key() for kw in ("flying", "reach"))
KEYWORD_RULES: dict[str, str] = {"flying": f"cant_be_blocked_except_by:{_FLYING_OR_REACH}", "menace": "min_blockers:2"}


def evasion_rules(ach: Characteristics) -> set[str]:
    """The attacker's rules about what can block it: its statics, rules imposed on it, and its
    evasion keywords (509.1b: "different evasion abilities are cumulative")."""
    return scripts.statics(ach) | {rule for kw, rule in KEYWORD_RULES.items() if kw in ach.keywords}


def block_limit(plan: Plan, bch: Characteristics) -> int:
    """-- multiple blocks (wave 13B) -- 509.1a: one attacker per blocker, and one more for each "can block an additional
    creature" (``block_extra:N:<source>``, one per source, so several add up; "any number of creatures": a huge N)."""
    from app.rules import combat_equipment_blocks70

    return 1 + sum(int(arg.split(":")[0]) for name, arg in map(rule_arg, bch.imposed) if name == "block_extra") + combat_equipment_blocks70.extra(plan, bch)


def min_blockers(ach: Characteristics) -> int:
    """509.1b / 702.111b: the fewest creatures that may block it together (menace: 2)."""
    n = 1
    for rule in evasion_rules(ach):
        name, arg = rule_arg(rule)
        if name == "min_blockers" and arg.isdigit():
            n = max(n, int(arg))
    return n


def _any_selector(state: GameState, info: CardInfo | None, arg: str, card: CardInstance, ch: Characteristics,
                  source: CardInstance) -> bool:
    """Does ``card`` match any of the rule's selectors? "You" is the controller of the creature the
    rule is on (a table-wide "Cowards can't block Warriors" has no "you" to read)."""
    if info is None:
        return False
    from app.rules.layers import _view

    view = _view(state, info)
    return any(selectors.matches(view, sel, card, ch, source.controller, source.id) for sel in rule_selectors(arg))


def _defender_controls(state: GameState, info: CardInfo | None, arg: str, defender: str) -> bool:
    if info is None:
        return False
    from app.rules.layers import _view

    view = _view(state, info)
    return any(selectors.candidates(view, selectors.replace(sel, controller="you"), defender) for sel in rule_selectors(arg))  # (wave 21A: the defender's own)


def _defender_condition(state: GameState, info: CardInfo | None, fact: str, defender: str) -> bool:
    """-- as long as (wave 25A) -- a fact about the defending player (statics._defender_fact), as it is as blockers are declared (509.1b)."""
    kind, _, rest = fact.partition(":")
    if info is None:
        return False
    if kind == "controls":
        return _defender_controls(state, info, rest, defender)
    if kind == "counters":
        return state.players[defender].resources.get(rest, 0) > 0
    if kind == "monarch":  # -- block events (wave 53C) -- 725.1: the defender is the monarch (a blocker is the monarch's: "creatures the monarch controls")
        return state.table.monarch == defender
    from app.rules.layers import _view

    view = _view(state, info)

    def count(sel: Any, who: str) -> int:
        return len(selectors.candidates(view, selectors.replace(sel, controller="you"), who))

    if kind == "shared_creature_type":
        from app.rules import values
        shared = values.evaluate(view, {"controller": defender},
                                 {"shared_type": 1, "of": selectors.Selector(types=("Creature",), controller="you").key()})
        return shared >= int(rest)
    if kind == "count":
        n, _, keys = rest.partition(":")
        return any(count(sel, defender) >= int(n) for sel in rule_selectors(keys))
    if kind == "most":
        mine = count(selectors.Selector(types=("Creature",)), defender)
        live = [p for p in state.seat_order if not state.players[p].left]
        return all(mine >= count(selectors.Selector(types=("Creature",)), p) for p in live)
    return False


def _phrase(arg: str) -> str:
    """A short reading of a rule's selectors for error messages ("creatures with power 2 or less")."""
    parts = []
    for sel in rule_selectors(arg):
        words = [*(c.lower() for c in sel.colors), *(t.lower() for t in sel.types), *sel.subtypes] or ["creatures"]
        text = " ".join(words)
        if not text.endswith("s"):
            text += "s"
        if sel.with_keywords:
            text += " with " + " and ".join(sel.with_keywords)
        for x in sel.extras:  # (wave 45D's either-keyword selector)
            if x.startswith("any_kw:"):
                text += " with " + " or ".join(x[7:].split(","))
        if sel.without_keywords:
            text += " without " + " and ".join(sel.without_keywords)
        for what, op, n in sel.compare:
            text += f" with {'mana value' if what == 'mv' else what} {n} or {'less' if op == '<=' else 'greater' if op == '>=' else 'equal'}"
        parts.append(text)
    return " or ".join(parts)


LANDWALK = {"plainswalk": "Plains", "islandwalk": "Island", "swampwalk": "Swamp", "mountainwalk": "Mountain",
            "forestwalk": "Forest", "desertwalk": "Desert",
            # -- landwalk variants (wave 12B) -- 702.14a/c: the type, supertype and/or subtype the land has, or (nonbasic) lacks
            "snow landwalk": "Snow", "nonbasic landwalk": "nonbasic", "legendary landwalk": "Legendary",
            "artifact landwalk": "Artifact", **{f"snow {w}walk": f"Snow {w.capitalize()}"
                                                for w in ("plains", "island", "swamp", "mountain", "forest")},
            # -- zones (wave 100G) -- any land type's (205.3i), snow or not: "landwalk of the chosen type" (Illusionary Presence, Barbarian Guides)
            **{f"{t.lower()}walk": t for t in sorted(LAND_TYPES)}, **{f"snow {t.lower()}walk": f"Snow {t}" for t in sorted(LAND_TYPES)}}


def _controls_land(state: GameState, player: str, kind: str, info: CardInfo | None) -> bool:
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = chars.of(card, info) if info is not None else None
        if ch is not None and ch.is_land and (
                "Basic" not in ch.supertypes if kind == "nonbasic" else set(kind.split()) <= {*ch.supertypes, *ch.types, *ch.subtypes}):
            return True
    return False


def attack_targets(state: GameState, attacker: str, info: CardInfo) -> list[str]:
    """Opponents, planeswalkers they control, and battles they protect (506.2, 508.1b; 310.9b: a
    Siege can be attacked by its own controller, never by its protector)."""
    from app.rules import battles
    from app.rules.layers import derive

    out = [p for p in live_players(state) if p != attacker]
    defenders = list(out)
    for pid in defenders:
        for cid in state.zones.get(zone_key(pid, "battlefield"), []):
            card = state.cards[cid]
            current = derive(state, card, chars.of(card, info), info)
            if card.controller == pid and "Planeswalker" in current.types and "cant_be_attacked" not in scripts.statics(current):
                out.append(cid)
    out += [cid for cid in battles.attackable(state, attacker, defenders, lambda c: derive(state, c, chars.of(c, info), info))
            if "cant_be_attacked" not in scripts.statics(derive(state, state.cards[cid], chars.of(state.cards[cid], info), info))]
    return out


def _label(state: GameState, target: str) -> str:
    return state.players[target].name if target in state.players else (state.cards[target].name or "Planeswalker")


def defender_of(state: GameState, target: A.AttackTarget | Any) -> str | None:
    if target is None:
        return None
    if target.kind == "player":
        return str(target.id)
    card = state.cards.get(target.id)
    if card is None:
        return None
    from app.rules import battles

    return battles.protector(state, card) or card.controller  # 310.9d: a battle's protector defends it


# -- declare attackers ------------------------------------------------------------------
def start_declare_attackers(plan: Plan) -> None:
    r = plan.rules
    r.no_attackers = False
    r.blocked = []
    r.attacking_bands = []
    r.blockers_pending = []
    r.combat_round = ""
    ap = plan.active
    eligible = [cid for cid in plan.state.zones.get(zone_key(ap, "battlefield"), [])
                if attack_problem(plan.state, plan.state.cards[cid], plan.ch(plan.state.cards[cid])) is None]
    targets = attack_targets(plan.state, ap, plan.info)
    if r.could_attack_turn110g != plan.state.turn.number:  # -- wave 110G -- 508.1a: who could attack this turn ("creatures that couldn't attack")
        r.could_attack110g, r.could_attack_turn110g = [], plan.state.turn.number
    r.could_attack110g = [*r.could_attack110g, *(plan.oid(c) for c in eligible)] if targets else r.could_attack110g
    if not eligible or not targets:
        r.no_attackers = True
        from app.rules import delayed

        delayed.at_step(plan, "declare_attackers")  # (wave 110B)
        return
    who = wave110a_choosers.chooser(plan, "attack", ap)  # -- declaration choosers (wave 110A) --
    decide(plan, player=ap, kind="declare_attackers", prompt="Declare attackers (or attack with nothing)", decider=who, blind=who is not None,
           options=[DecisionOption(id=f"a:{cid}", label=plan.state.cards[cid].name or "Creature", card_id=cid) for cid in eligible]
           + [DecisionOption(id=f"t:{t}", label=_label(plan.state, t), card_id=t if t in plan.state.cards else None)
              for t in targets],
           min_choices=0, max_choices=len(eligible), resume={"step": "declare_attackers"},
           display=banding.declaration_options(plan, eligible))


def declare_attackers(plan: Plan, a: A.DeclareAttackers) -> None:
    r = plan.rules
    d = r.decision
    # -- combat (wave 5C) -- the declaration again, once the attack cost's mana is in the pool (508.1h-j, casting._rerun)
    locked: M.ManaCost | None = None
    paying = d is None and plan.locked_cost is not None and plan.state.turn.phase == "declare_attackers" \
        and plan.actor == plan.active and not r.no_attackers and not attackers_on(plan.state)
    if paying:
        locked = M.parse_cost(plan.locked_cost or "{0}")
        plan.locked_cost = None
        eligible = {cid for cid in plan.state.zones.get(zone_key(plan.active, "battlefield"), [])
                    if attack_problem(plan.state, plan.state.cards[cid], plan.ch(plan.state.cards[cid])) is None}
        targets = set(attack_targets(plan.state, plan.active, plan.info))
    else:
        if d is None or d.kind != "declare_attackers":
            raise ActionError("Attackers are declared at the start of the declare attackers step")
        if d.player != plan.actor:
            raise ActionError(f"{plan.name(d.player)} is declaring attackers")
        eligible = {o.id[2:] for o in d.options if o.id.startswith("a:")}
        targets = {o.id[2:] for o in d.options if o.id.startswith("t:")}
    current_targets = set(attack_targets(plan.state, plan.active, plan.info)) if a.attackers else set()
    seen: set[str] = set()
    for decl in a.attackers:
        card = plan.state.cards.get(decl.card_id)
        if decl.card_id not in eligible or card is None:
            raise ActionError("That creature can't attack now")
        problem = attack_problem(plan.state, card, plan.ch(card))
        if problem:
            raise ActionError(problem)
        if decl.target not in targets or decl.target not in current_targets:
            raise ActionError(f"{card.name} can't attack that")
        if attack_forbidden(plan, plan.ch(card), decl.target):  # -- attached events (wave 4L) -- (508.1c)
            raise ActionError(f"{card.name} can't attack {_label(plan.state, decl.target)}")
        if "attack_needs_island" in scripts.statics(plan.ch(card)):
            defender = decl.target if decl.target in plan.state.players else \
                defender_of(plan.state, A.AttackTarget(kind="card", id=decl.target))
            if not _controls_land(plan.state, defender or "", "Island", plan.info):
                raise ActionError(f"{card.name} can't attack unless defending player controls an Island")
        if _attacked_before(plan, card, plan.ch(card), decl.target):  # -- static_other sweep (wave 19A) -- 508.1c (Port Razer)
            raise ActionError(f"{card.name} can't attack a player it has already attacked this turn")
        if decl.card_id in seen:
            raise ActionError(f"{card.name} can only attack once")
        seen.add(decl.card_id)
        if "cant_attack_alone" in scripts.statics(plan.ch(card)) and len(a.attackers) == 1:
            raise ActionError(f"{card.name} can't attack alone")  # 506.5 / 508.1c
    # -- combat (wave 5C) -- 508.1c: "No more than two creatures can attack you each combat"
    from app.rules import combat_rules

    declared = [(x.card_id, x.target) for x in a.attackers]
    from app.rules import declaration_groups

    grouped = declaration_groups.relevant(plan, eligible, 'attack')
    if grouped and not declaration_groups.legal(plan, seen, 'attack'):
        raise ActionError('The attacking creatures do not satisfy their companion restrictions')
    caps = combat_rules.limits(plan)
    limit = combat_rules.limit_problem(plan, declared, caps)
    if limit:
        raise ActionError(limit)
    if grouped:
        problem = declaration_groups.attack_requirements(plan, eligible, targets, dict(declared), caps)
        if problem:
            raise ActionError(problem)
    elif "*" in caps or any(cap_player in targets for cap_player in caps):  # 508.1d weighed over the whole declaration
        problem = combat_rules.requirements_problem(plan, eligible, _required_places(plan, eligible, targets, dict(declared)),
                                                    {x.card_id: x.target for x in a.attackers}, caps)
        if problem:
            raise ActionError(problem)
    else:
        # 508.1d: a creature that "attacks each combat if able" must attack when it can
        for cid in eligible - seen:
            card = plan.state.cards.get(cid)
            if card is not None and "must_attack" in scripts.statics(plan.ch(card)) and \
                    attack_problem(plan.state, card, plan.ch(card)) is None and \
                    any(not _closed(plan, plan.ch(card), t, card) for t in targets):  # (wave 4L: 508.1d; wave 5C: costs)
                raise ActionError(f"{card.name} attacks each combat if able")
        goad_problem = goad_requirements(plan, eligible, targets, {x.card_id: x.target for x in a.attackers})
        if goad_problem:  # -- keyword actions & face-down (wave 3F) --
            raise ActionError(goad_problem)
    banding.validate(plan, a, locked=paying)
    from app.game.rules_state import DeclarationCostReservation
    from app.rules import nonmana_combat_costs

    additional = nonmana_combat_costs.prepare(plan, a, seen, 'attack')
    if additional is None:
        return
    if additional:
        r.declaration_cost_reserved = DeclarationCostReservation(payer=plan.actor, objects={cid: oid for event in additional for cid, oid in event.objects.items()})
    # -- combat (wave 5C) -- 508.1h-j: the total cost to attack, locked in, then paid (mana abilities allowed meanwhile);
    # creatures declared as attackers are tapped before it's paid (508.1f), so they don't tap for it
    tax = combat_rules.attack_cost(plan, declared)
    life = combat_rules.attack_life(plan, declared)  # -- life attack costs (wave 49D) -- 508.1h: paid with the mana (508.1j); 119.4: only with the life to pay it
    if life:
        from app.rules import life_lock

        if plan.state.players[plan.actor].life < life or life_lock.pay_problem(plan.state, plan.info, plan.actor, life) is not None:
            raise ActionError(f"Attacking costs {life} life (508.1h): {plan.name(plan.actor)} can't pay it")
    frame = PaidAttackers(a, life, {x.card_id: plan.oid(plan.state.cards[x.card_id]) for x in a.attackers},
                          {x.target: plan.oid(plan.state.cards[x.target]) for x in a.attackers if x.target in plan.state.cards},
                          [x.card_id for x in a.attackers if 'vigilance' not in plan.ch(plan.state.cards[x.card_id]).keywords])
    if tax or (locked is not None and not locked.is_free):
        from app.rules import casting

        cost = locked if locked is not None else M.parse_cost(tax)
        exclude = tuple(x.card_id for x in a.attackers if "vigilance" not in plan.ch(plan.state.cards[x.card_id]).keywords)
        exclude = tuple(dict.fromkeys([*exclude, *(cid for event in additional if event.kind == 'tap' for cid in event.objects)]))
        if not casting.can_pay(plan.state, plan.actor, cost, plan.info, exclude=exclude):
            raise ActionError(f"Attacking costs {cost.text()} (508.1h): {plan.name(plan.actor)} can't pay it")
        if not paying:
            r.decision = None
        from app.rules import payment_continuations as pc

        after = nonmana_combat_costs.after(plan, additional, pc.continuation(plan, 'declare_attackers', frame))
        if casting.payment_step(plan, a, cost, "attacking", exclude=exclude):  # type: ignore[arg-type]
            assert r.decision is not None and r.decision.resume is not None
            r.decision.resume['paid_then'] = after
            return
        casting.pay_then(plan, plan.actor, cost, f"paid {cost.text()} to attack", then=after,
                         sources=a.sources, exclude=exclude)
        return
    if additional:
        _pc.finish(plan, nonmana_combat_costs.after(plan, additional, _pc.continuation(plan, 'declare_attackers', frame)), None)
    else:
        _finish_attackers(plan, frame, None)


@dataclass
class PaidAttackers:
    declaration: A.DeclareAttackers
    life: int
    objects: dict[str, str] = field(default_factory=dict)
    targets: dict[str, str] = field(default_factory=dict)
    tap: list[str] | None = None


def _finish_attackers(plan: Plan, payload: PaidAttackers, payment: M.Payment | None) -> None:
    """Commit the locked declaration after all mana-source riders finish."""
    from app.rules.engine import advance

    a, life = payload.declaration, payload.life
    # Declaration restrictions/costs were already locked before mana abilities.
    # A departed object cannot be resurrected as an attacker by a saved reference.
    selected = []
    for decl in a.attackers:
        card = plan.state.cards.get(decl.card_id)
        if card is None or not card.zone.endswith(':battlefield') or card.controller != plan.actor or not plan.in_game(card):
            continue
        if payload.objects and plan.oid(card) != payload.objects.get(card.id):
            continue
        if not plan.ch(card).is_creature:
            continue
        if decl.target not in plan.live():
            defender = plan.state.cards.get(decl.target)
            if defender is None or not defender.zone.endswith(':battlefield') or not plan.in_game(defender):
                continue
            if payload.targets and plan.oid(defender) != payload.targets.get(defender.id):
                continue
        selected.append(decl)
    surviving = {decl.card_id for decl in selected}
    a = a.model_copy(update={'attackers': selected,
                             'bands': [[cid for cid in band if cid in surviving] for band in a.bands
                                       if sum(cid in surviving for cid in band) >= 2]})
    r = plan.rules
    if life:
        from app.rules import replace as _replace_life

        _replace_life.lose_life(plan, [(plan.actor, life)], actor=plan.actor, paid=True)
        plan.note(f"{plan.name(plan.actor)} paid {life} life to attack")
    # -- end combat (wave 5C) --
    r.decision = None
    from app.rules import delayed

    delayed.at_step(plan, "declare_attackers")  # -- delayed triggers (wave 110B) -- 603.7: "at the beginning of the declare attackers step" (Meandering Towershell), once the declaration is made
    if not a.attackers:
        r.no_attackers = True
        plan.note(f"{plan.name(plan.actor)} doesn't attack")
    else:
        to_tap = [x.card_id for x in a.attackers if x.card_id in payload.tap] if payload.tap is not None else [
            x.card_id for x in a.attackers if 'vigilance' not in plan.ch(plan.state.cards[x.card_id]).keywords]
        if to_tap:
            plan.do({"type": "tap", "card_ids": to_tap, "tapped": True, "declared": True})
        by_target: dict[str, list[str]] = {}
        for decl in a.attackers:
            by_target.setdefault(decl.target, []).append(decl.card_id)
        for target, ids in by_target.items():
            kind = "player" if target in plan.state.players else "card"
            plan.do({"type": "attack", "card_ids": ids, "target": {"kind": kind, "id": target}})
        banding.remember(plan, a.bands)
        from app.game.rules_state import note_attack
        from app.rules import triggers  # triggers → plan; imported late

        plan.rules.attacked_players[plan.actor] = sorted({x.target for x in a.attackers if x.target in plan.state.players})  # (melee: 18E)
        plan.rules.attack_power[plan.actor] = sum((plan.ch(plan.state.cards[x.card_id]).pt or (0, 0))[0]  # (wave 25B: 508.1)
                                                  for x in a.attackers)

        note_attack(plan.state, plan.actor,  # (wave 4D: the attacking objects)
                    [plan.oid(plan.state.cards[x.card_id]) for x in a.attackers],  # 508.1: "if you attacked this turn" (conditional clauses, wave 1B)
                    [x.target for x in a.attackers])
        from app.rules import (
            wave110j_cards,  # -- battles (wave 110J) -- "attacked a battle this turn" (War Historian)
        )

        wave110j_cards.note_battle_attacks(plan, a.attackers)
        wave110j_cards.note_engaged(plan, [x.card_id for x in a.attackers])
        # -- static wordings (wave 6E) -- 508.1g / 701.43d: "You may exert this creature as it attacks" (app/rules/exert.py)
        from app.rules import exert

        if exert.ask(plan, [plan.state.cards[x.card_id] for x in a.attackers]):
            return
        from app.rules import (
            enlist,  # -- casting extras (wave 18E) -- 702.154a: an optional cost to attack (508.1g)
        )

        if enlist.ask(plan, [plan.state.cards[x.card_id] for x in a.attackers], []):
            return
        triggers.attacked(plan, [plan.state.cards[x.card_id] for x in a.attackers])
    r.priority = plan.active
    r.passed = []
    advance(plan)


from app.rules import payment_continuations as _pc  # noqa: E402

_pc.register("declare_attackers", PaidAttackers, _finish_attackers)

# -- combat (wave 5C) --------------------------------------------------------------------------
def _attacked_before(plan: Plan, card: CardInstance, ch: Characteristics, target: str) -> bool:
    """508.1c: "can't attack a player it has already attacked this turn" (Port Razer)."""
    log = plan.rules.turn_log
    return "cant_attack_attacked" in ch.imposed and log.turn == plan.state.turn.number \
        and target in log.attacked_who.get(plan.oid(card), ())


def _closed(plan: Plan, ch: Characteristics, target: str, card: CardInstance, *, declared: bool = False) -> bool:
    """508.1d: a place a requirement can't send the creature: a restriction forbids it, or attacking there has a
    cost not already accepted by declaring this creature (508.1d)."""
    from app.rules import combat_rules

    return attack_forbidden(plan, ch, target) or _attacked_before(plan, card, ch, target) or combat_rules.taxed(plan, ch, target, card.id, declared=declared)


def _required_places(plan: Plan, eligible: set[str], targets: set[str], declared: dict[str, str]) -> dict[str, list[str]]:
    """Creatures with attack requirements (attacks each combat if able, goaded, "attack a player other than you if
    able") and where each could attack without accepting an additional cost."""
    from app.rules.keyword_actions import goaded_by

    out: dict[str, list[str]] = {}
    for cid in sorted(eligible):
        card = plan.state.cards.get(cid)
        if card is None:
            continue
        ch = plan.ch(card)
        st = scripts.statics(ch)
        from app.rules import attack_requirements

        if not (attack_requirements.counts(ch) or goaded_by(ch)) \
                or attack_problem(plan.state, card, ch):
            continue
        if "cant_attack_alone" in st and len(eligible) == 1:
            continue
        out[cid] = [t for t in sorted(targets) if ("attack_needs_island" not in st or _controls_land(
            plan.state, t if t in plan.state.players else plan.state.cards[t].controller, "Island", plan.info))
            and not _closed(plan, ch, t, card, declared=cid in declared)]
    return out


# -- keyword actions & face-down (wave 3F) ------------------------------------------------------
def goad_requirements(plan: Plan, eligible: set[str], targets: set[str], declared: dict[str, str]) -> str | None:
    """701.15b / 508.1d for goaded creatures: a goaded creature attacks each combat if able, and
    attacks a player other than each player who goaded it if able (701.15c: one requirement per
    goading player; attacking a planeswalker obeys none of those). The declaration must obey as many
    of each creature's requirements as it could without breaking a restriction (508.1d); each
    goaded creature's requirements are judged on its own, against the places it may attack.
    Costs to attack are never required (508.1d). Declaring a creature voluntarily accepts its global cost;
    destination-specific costs remain optional (wave 5C). "Attack a player other
    than you if able" from an effect (Kardur, ``attack_other_than:<player>``) is weighed the same way."""
    from app.rules import combat_rules  # -- combat (wave 5C) --
    from app.rules.keyword_actions import goaded_by

    live = set(plan.live())
    for cid in sorted(eligible):
        card = plan.state.cards.get(cid)
        if card is None:
            continue
        ch = plan.ch(card)
        goaders = goaded_by(ch)
        others_only = combat_rules.other_than(ch) - goaders
        wants = combat_rules.attack_players(ch) & live  # -- casting extras (wave 18E) -- encore: attacks that player if able
        from app.rules import attack_requirements

        if not (goaders or others_only or wants or attack_requirements.counts(ch)) or attack_problem(plan.state, card, ch) is not None:
            continue
        st = scripts.statics(ch)
        if "cant_attack_alone" in st and len(eligible) == 1:
            continue  # (it can't attack at all: alone is the only way it could)
        places = [t for t in targets if ("attack_needs_island" not in st
                  or _controls_land(plan.state, t if t in plan.state.players else plan.state.cards[t].controller,
                                    "Island", plan.info)) and not _closed(plan, ch, t, card, declared=cid in declared)]  # (wave 4L; wave 5C: costs)
        if not places:
            continue

        from app.rules import attack_requirements

        def obeyed(place: str | None, ch: Characteristics = ch) -> int:
            return attack_requirements.score(plan, ch, place)

        best = max(obeyed(t) for t in places)
        if wants and not (goaders or others_only) and obeyed(declared.get(cid)) < best:
            return f"{card.name} attacks {' or '.join(sorted(plan.name(w) for w in wants))} this turn if able"
        if obeyed(declared.get(cid)) < best:
            who = " or ".join(sorted(plan.name(g) for g in (goaders | others_only) & live)) or "anyone"
            what = "is goaded: it" if goaders else "must"
            if cid not in declared:
                return f"{card.name} {what} attacks each combat if able" if goaders else \
                    f"{card.name} attacks each combat if able"
            return f"{card.name} {what} attack{'s' if goaders else ''} a player other than {who} if able"
    return None


def _defender_fact(plan: Plan, arg: str, defender: str) -> bool:
    """-- static_other sweep (wave 21A) -- one fact about the defending player (a rule's argument): "controls:<selector>", "poisoned",
    "monarch", "graveyard:<n>" (n or more cards in their graveyard), "outnumbers:<player>:<selector>" (that player controls more of
    them than the defender)."""
    kind, _, rest = arg.partition(":")
    state = plan.state
    if kind == "controls":
        return _defender_controls(state, plan.info, rest, defender)
    if kind == "acted110e":  # -- wave 110E -- Arboria: the defender's last completed turn (none yet: no)
        summary = state.rules.completed_own_turns.get(defender) if state.rules is not None else None
        return summary is not None and summary.acted110e
    if kind == "poisoned":
        return int(state.players[defender].resources.get("poison", 0)) > 0
    if kind == "monarch":
        return state.table.monarch == defender
    if kind == "graveyard":
        return len(state.zones.get(zone_key(defender, "graveyard"), ())) >= int(rest)
    who, _, sel = rest.partition(":")  # outnumbers
    return _controls_more(state, plan.info, sel, who, defender)


def _controls_more(state: GameState, info: CardInfo | None, sel: str, a: str, b: str) -> bool:
    """-- static_other sweep (wave 21A) -- does player ``a`` control more of what the selector names than player ``b``?"""
    if info is None:
        return False
    from app.rules.layers import _view

    view = _view(state, info)
    return any(len(selectors.candidates(view, (one := selectors.replace(s, controller="you")), a))
               > len(selectors.candidates(view, one, b)) for s in rule_selectors(sel))


def attack_forbidden(plan: Plan, ch: Characteristics, target: str) -> bool:
    """-- attached events (wave 4L) -- 508.1c: "can't attack you [or planeswalkers you control]" (rules
    ``cant_attack_player:<player>`` / ``cant_attack_player_pw:<player>`` / ``cant_attack_player_perm:<player>`` (wave 32B), "you" being the static's controller); -- static_other sweep
    (wave 21A) -- "can't attack unless / if defending player …" (``cant_attack_unless_def:<fact>`` / ``cant_attack_if_def:<fact>``)."""
    from app.rules import previous_own_turns, timed_damage_replacements

    if (target in plan.state.players and not ({'flying', 'islandwalk'} & set(ch.keywords))
            and any(rec.get('kind') == 'draw_attack_gate' and rec.get('controller') == target
                    and timed_damage_replacements.active(plan, rec) for rec in plan.rules.replacements)):
        return True
    own = scripts.statics(ch)
    from app.rules import combat_teyo66

    if combat_teyo66.forbidden(plan, own, target):
        return True
    if "defender" in ch.keywords and "attack_despite_defender" not in own:
        for rule in own:
            if rule.startswith(previous_own_turns.DEFENDER + ':'):
                protected = rule.partition(':')[2]
                if target not in plan.state.players or previous_own_turns.attacked_player(plan.state, target, protected) is not True:
                    return True
    for rule in ch.imposed:
        name, _, who = rule.partition(":")
        if name in ("cant_attack_unless_def", "cant_attack_if_def"):
            defender = target if target in plan.state.players else defender_of(plan.state, A.AttackTarget(kind="card", id=target))
            if defender in plan.state.players and _defender_fact(plan, who, defender) == (name == "cant_attack_if_def"):
                return True
            continue
        if name not in ("cant_attack_player", "cant_attack_player_pw", "cant_attack_player_perm"):
            continue
        if target == who:
            return True
        card = plan.state.cards.get(target)
        if name == "cant_attack_player_pw" and card is not None and card.controller == who                 and "Planeswalker" in plan.ch(card).types:
            return True
        # -- attack restrictions (wave 32B) -- "can't attack you or permanents you control": a planeswalker or a battle (506.3) the player controls
        # (the battle's controller, 110.2 — not its protector)
        if name == "cant_attack_player_perm" and card is not None and card.controller == who:
            return True
    return False


# -- declare blockers -------------------------------------------------------------------
def attackers_on(state: GameState) -> list[CardInstance]:
    return [c for c in state.cards.values() if c.is_attacking and c.zone.endswith(":battlefield")]


def sync_attacking(plan: Plan) -> None:
    """506.4/506.4c: derived type changes remove a participant or its attack target."""
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or not (card.is_attacking or card.is_blocking):
            continue
        ch = plan.ch(card)
        if not ch.is_creature or "Battle" in ch.types:
            if card.is_attacking:
                plan.do({"type": "attack", "card_ids": [card.id], "target": None})
            if card.is_blocking:
                plan.do({"type": "block", "card_id": card.id, "attacker_id": None})
            continue
        if not card.is_attacking:
            continue
        target = card.attacking
        if target is None or target.kind == "player":
            continue
        attacked = plan.state.cards.get(target.id)
        if attacked is None or not attacked.zone.endswith(":battlefield") or not ({"Planeswalker", "Battle"} & plan.ch(attacked).types):
            defender = defender_of(plan.state, target)
            if defender is not None:
                plan.do({"type": "attack", "card_ids": [card.id], "target": None, "attacking_without_target": defender})


def blocking_defender(state: GameState, card: CardInstance) -> str | None:
    return card.attacking_without_target if card.attacking_without_target is not None else defender_of(state, card.attacking)


def start_declare_blockers(plan: Plan) -> None:
    r = plan.rules
    r.blocked = []
    attacked = {blocking_defender(plan.state, c) for c in attackers_on(plan.state)}
    order = plan.state.seat_order
    start = order.index(plan.active)
    r.blockers_pending = [p for p in order[start + 1:] + order[:start] if p in attacked and p in plan.live()]
    ask_next_blocker(plan)
    if r.decision is None:
        blocks_declared(plan)


def blocks_declared(plan: Plan) -> None:
    """Every defending player has declared blockers (509.1): "Whenever ~ attacks and isn't blocked"
    triggers for each attacking creature no creature was declared as a blocker for (509.3g, 509.1h)."""
    from app.rules import triggers  # triggers → plan; imported late

    triggers.unblocked(plan, [c for c in attackers_on(plan.state) if c.id not in plan.rules.blocked])


def ask_next_blocker(plan: Plan) -> None:
    r = plan.rules
    state = plan.state
    while r.blockers_pending:
        pid = r.blockers_pending[0]
        attackers = [c for c in attackers_on(state) if blocking_defender(state, c) == pid]
        blockers = [state.cards[cid] for cid in state.zones.get(zone_key(pid, "battlefield"), [])
                    if state.cards[cid].controller == pid and plan.ch(state.cards[cid]).is_creature
                    and (not state.cards[cid].tapped or "block_tapped" in scripts.statics(plan.ch(state.cards[cid])))]  # (wave 42A: Masako)
        if not attackers or not blockers:
            r.blockers_pending.pop(0)
            continue
        who = wave110a_choosers.chooser(plan, "block", pid)  # -- declaration choosers (wave 110A) --
        decide(plan, player=pid, kind="declare_blockers", prompt="Declare blockers (or block with nothing)", decider=who, blind=who is not None,
               options=[DecisionOption(id=f"b:{c.id}", label=c.name or "Creature", card_id=c.id) for c in blockers]
               + [DecisionOption(id=f"a:{c.id}", label=c.name or "Attacker", card_id=c.id) for c in attackers],
               min_choices=0, max_choices=len(blockers), resume={"step": "declare_blockers"})
        return


def declare_blockers(plan: Plan, a: A.DeclareBlockers) -> None:
    r = plan.rules
    d = r.decision
    if d is None or d.kind != "declare_blockers":
        raise ActionError("Blockers are declared at the start of the declare blockers step")
    if d.player != plan.actor:
        raise ActionError(f"{plan.name(d.player)} is declaring blockers")
    blockers = {o.id[2:] for o in d.options if o.id.startswith("b:")}
    attackers = {o.id[2:] for o in d.options if o.id.startswith("a:")}
    used: dict[str, list[str]] = {}
    per_attacker: dict[str, int] = {}
    for decl in a.blocks:
        blocker = plan.state.cards.get(decl.blocker_id)
        attacker = plan.state.cards.get(decl.attacker_id)
        if decl.blocker_id not in blockers or blocker is None:
            raise ActionError("That creature can't block now")
        if decl.attacker_id not in attackers or attacker is None:
            raise ActionError(f"{blocker.name} can't block that")
        if decl.attacker_id in used.get(decl.blocker_id, []):
            raise ActionError(f"{blocker.name} can't block {attacker.name} twice")
        if len(used.get(decl.blocker_id, [])) >= block_limit(plan, plan.ch(blocker)):  # (-- multiple blocks (wave 13B) -- 509.1a)
            raise ActionError(f"{blocker.name} can only block one attacker")
        used.setdefault(decl.blocker_id, []).append(decl.attacker_id)
        problem = block_problem(plan.state, blocker, plan.ch(blocker), attacker, plan.ch(attacker), plan.info)
        if problem:
            raise ActionError(problem)
        per_attacker[decl.attacker_id] = per_attacker.get(decl.attacker_id, 0) + 1
    cap = r.block_caps.get(plan.actor)  # -- commander sweep (wave 49B) -- 509.1b: "Each opponent can't block with more than one creature this combat." (Mirri)
    if cap is not None and len(used) > cap:
        raise ActionError(f"You can't block with more than {cap} creature{'s' if cap != 1 else ''} this combat")
    for aid, n in per_attacker.items():
        ach = plan.ch(plan.state.cards[aid])
        least = min_blockers(ach)
        if n < least:
            raise ActionError(f"{ach.name} can't be blocked except by {least} or more creatures"
                              + (" (menace)" if "menace" in ach.keywords else ""))
        if "max_one_blocker" in scripts.statics(ach) and n > 1:
            raise ActionError(f"{ach.name} can't be blocked by more than one creature")
        # -- commanders (wave 47A) -- 509.1b, Tromokratis (2014-02-01): "can't be blocked unless all creatures defending player controls block it" — every creature the
        # declaring player controls, a tapped one included, which can't then (so it can't be blocked). ponytail: a "must be blocked if able" on it isn't reconciled
        if "block_by_all" in scripts.statics(ach) and n < sum(1 for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == plan.actor
                                                     and plan.ch(c).is_creature):
            raise ActionError(f"{ach.name} can't be blocked unless all creatures you control block it")
    from app.rules import declaration_groups

    if declaration_groups.relevant(plan, blockers, 'block') and not declaration_groups.legal(plan, set(used), 'block'):
        raise ActionError('The blocking creatures do not satisfy their companion restrictions')
    if len(used) == 1:  # 506.5: blocking alone (one creature declared as a blocker, however many attackers it blocks)
        lone = plan.state.cards[a.blocks[0].blocker_id]
        if "cant_block_alone" in scripts.statics(plan.ch(lone)):
            raise ActionError(f"{lone.name} can't block alone")
    # -- static_other sweep (wave 16B) -- 509.1b: "No more than one creature can block each combat." (all the blockers, every player's)
    from app.rules import combat_rules

    cap = combat_rules.limits(plan, combat_rules.BLOCK_LIMIT_ALL).get("*")
    if cap is not None and len(used) + sum(1 for c in plan.state.cards.values() if c.is_blocking) > cap:
        raise ActionError(f"No more than {cap} creature{'s' if cap != 1 else ''} can block each combat")
    expanded = banding.expand_blocks(plan, a.blocks)
    effective_counts: dict[str, int] = {}
    for block in expanded:
        effective_counts[block.attacker_id] = effective_counts.get(block.attacker_id, 0) + 1
    problem = block_requirements(plan, a, blockers, attackers, used, effective_counts)
    if problem:
        raise ActionError(problem)
    from app.rules import wave110f_cards  # -- (wave 110F) -- Heat Wave: the life to block (509.1d)

    if (why := wave110f_cards.block_life_problem(plan, expanded)) is not None:
        raise ActionError(why)
    from app.game.rules_state import DeclarationCostReservation
    from app.rules import nonmana_combat_costs

    additional = nonmana_combat_costs.prepare(plan, a, set(used), 'block')
    if additional is None:
        return
    if additional:
        r.declaration_cost_reserved = DeclarationCostReservation(payer=plan.actor, objects={cid: oid for event in additional for cid, oid in event.objects.items()})
    frame = PaidBlockers(expanded, {cid: plan.oid(plan.state.cards[cid]) for cid in used},
                         {cid: plan.oid(plan.state.cards[cid]) for cid in effective_counts})
    from app.rules import (
        wave110m_cards,  # -- (wave 110M) -- Awesome Presence: a cost to block that attacker, for each blocker (509.1d)
    )

    cost = M.parse_cost(combat_rules.block_cost(plan, set(used)) + wave110m_cards.block_tax_for(plan, expanded))
    if not cost.is_free:
        from app.rules import casting

        if not casting.can_pay(plan.state, plan.actor, cost, plan.info):
            raise ActionError(f"Blocking costs {cost.text()} (509.1d): {plan.name(plan.actor)} can't pay it")
        after = nonmana_combat_costs.after(plan, additional, _pc.continuation(plan, 'declare_blockers', frame))
        r.decision = None
        exclude = tuple(cid for event in additional if event.kind == 'tap' for cid in event.objects)
        if casting.payment_step(plan, a, cost, 'blocking', exclude=exclude):  # type: ignore[arg-type]
            assert r.decision is not None and r.decision.resume is not None
            r.decision.resume['paid_then'] = after
            return
        casting.pay_then(plan, plan.actor, cost, f'paid {cost.text()} to block', sources=a.sources, exclude=exclude, then=after)
        return
    if additional:
        _pc.finish(plan, nonmana_combat_costs.after(plan, additional, _pc.continuation(plan, 'declare_blockers', frame)), None)
    else:
        _finish_blockers(plan, frame, None)


@dataclass
class PaidBlockers:
    blocks: list[A.BlockDeclaration]
    blockers: dict[str, str]
    attackers: dict[str, str]


def _finish_blockers(plan: Plan, frame: PaidBlockers, payment: M.Payment | None) -> None:
    from app.rules.engine import advance

    r = plan.rules
    blocks = [b for b in frame.blocks if (blocker := plan.state.cards.get(b.blocker_id)) is not None
              and blocker.zone.endswith(':battlefield') and blocker.controller == plan.actor
              and plan.oid(blocker) == frame.blockers.get(b.blocker_id)
              and (attacker := plan.state.cards.get(b.attacker_id)) is not None
              and attacker.is_attacking and attacker.zone.endswith(':battlefield')
              and plan.oid(attacker) == frame.attackers.get(b.attacker_id)]
    per_attacker = dict.fromkeys(b.attacker_id for b in blocks)
    r.decision = None
    from app.rules import wave110f_cards  # -- (wave 110F) -- Heat Wave

    wave110f_cards.pay_block_life(plan, blocks)
    if r.blockers_pending and r.blockers_pending[0] == plan.actor:
        r.blockers_pending.pop(0)
    done: set[str] = set()
    for decl in blocks:
        plan.do({"type": "block", "card_id": decl.blocker_id, "attacker_id": decl.attacker_id, "also": decl.blocker_id in done})
        done.add(decl.blocker_id)
    r.blocked = list(dict.fromkeys([*r.blocked, *per_attacker]))
    note_block(plan.state, [plan.oid(plan.state.cards[b]) for b in dict.fromkeys(x.blocker_id for x in blocks)],  # (wave 27A)
               [(plan.oid(plan.state.cards[x.blocker_id]), plan.oid(plan.state.cards[x.attacker_id])) for x in blocks])  # (wave 31D)
    if blocks:
        from app.rules import (
            triggers,  # triggers → plan; imported late
            wave110j_cards,  # -- (wave 110J) -- blocked or was blocked, for "since your last upkeep"
        )

        wave110j_cards.note_engaged(plan, [x for d in blocks for x in (d.blocker_id, d.attacker_id)])
        triggers.blocked(plan, [plan.state.cards[d.blocker_id] for d in blocks],
                         [plan.state.cards[aid] for aid in per_attacker])
        triggers.flanking(plan, [(plan.state.cards[d.blocker_id], plan.state.cards[d.attacker_id]) for d in blocks])
    if not blocks:
        plan.note(f"{plan.name(plan.actor)} doesn't block")
    ask_next_blocker(plan)
    if r.decision is None:
        blocks_declared(plan)
        r.priority = plan.active
        r.passed = []
        advance(plan)


_pc.register('declare_blockers', PaidBlockers, _finish_blockers)

def block_requirements(plan: Plan, a: A.DeclareBlockers, blockers: set[str], attackers: set[str],
                       used: dict[str, list[str]], per_attacker: dict[str, int]) -> str | None:
    """509.1c requirements the declaration disobeys although it could obey them: "~ blocks each
    combat if able" (must_block, on a creature of the defending player) and "~ must be blocked if
    able" (must_be_blocked, on an attacker). Each requirement is judged on its own, against the
    blocks declared (one more block that no restriction forbids, 509.1b), not as the maximum over
    every combination of blocks the rule describes; a creature that can't block alone counts as
    able only once something else blocks."""
    from app.rules import declaration_groups

    if declaration_groups.relevant(plan, blockers, 'block'):
        return declaration_groups.block_requirements(plan, blockers, attackers, used)
    state = plan.state
    effective = banding.expand_blocks(plan, a.blocks)
    covered: dict[str, set[str]] = {}
    for block in effective:
        covered.setdefault(block.blocker_id, set()).add(block.attacker_id)
    idle = [state.cards[b] for b in blockers if b not in used]
    att = [state.cards[x] for x in attackers]
    from app.rules import combat_rules, wave110m_cards

    cap = combat_rules.limits(plan, combat_rules.BLOCK_LIMIT_ALL).get("*")  # -- static_other sweep (wave 16B) -- no more blockers once at it
    at_cap = cap is not None and len(used) + sum(1 for c in state.cards.values() if c.is_blocking) >= cap

    def could(blocker: CardInstance, attacker: CardInstance, *, joined: int) -> bool:
        if at_cap and blocker.id not in used:
            return False
        bch, ach = plan.ch(blocker), plan.ch(attacker)
        if blocker.id not in used and combat_rules.has_block_cost(plan, blocker.id, bch):
            return False  # 509.1c: a requirement never forces an additional payment.
        if wave110m_cards.attacker_tax(ach):  # -- (wave 110M) -- Awesome Presence: blocking that attacker costs mana (509.1c)
            return False
        if block_problem(state, blocker, bch, attacker, ach, plan.info) is not None:
            return False
        if "cant_block_alone" in scripts.statics(bch) and not a.blocks:
            return False
        return min_blockers(ach) <= joined

    def joined(b: CardInstance, x: CardInstance) -> int:
        """How many creatures could block ``x`` together with ``b``: those blocking it, and (-- review (wave 14R) -- 509.1c: the
        most requirements that could be obeyed counts any legal declaration) every other one with a block to spare that may."""
        return 1 + per_attacker.get(x.id, 0) + sum(
            1 for i in blockers if i != b.id and x.id not in used.get(i, []) and len(used.get(i, [])) < block_limit(plan, plan.ch(state.cards[i]))
            and (i in used or not combat_rules.has_block_cost(plan, i, plan.ch(state.cards[i])))
            and not wave110m_cards.attacker_tax(plan.ch(x))  # (wave 110M)
            and block_problem(state, state.cards[i], plan.ch(state.cards[i]), x, plan.ch(x), plan.info) is None)

    for b in idle:
        if "must_block" in scripts.statics(plan.ch(b)) and any(could(b, x, joined=joined(b, x)) for x in att):
            return f"{b.name} blocks each combat if able"
    for b in (state.cards[i] for i in blockers):  # -- combat (wave 110E) -- 509.1c: "blocks each attacking creature this turn if able" (Blaze of Glory)
        if "must_block_all110e" in scripts.statics(plan.ch(b)):
            for x in att:
                if x.id not in covered.get(b.id, set()) and len(used.get(b.id, [])) < block_limit(plan, plan.ch(b)) \
                        and could(b, x, joined=joined(b, x)):
                    return f"{b.name} blocks {x.name} this turn if able"
    # -- block effects (wave 7E) -- "blocks this creature this turn if able": judged for the creatures that block nothing, and
    # for those blocking another attacker unless that block meets a requirement of its own (509.1c)
    for b in (state.cards[i] for i in blockers):
        wanted = [arg for name, arg in map(rule_arg, scripts.statics(plan.ch(b))) if name == "must_block_obj"]
        # -- lure (wave 12B) -- 509.1c: "All creatures able to block ~ do so": every blocker has "blocks it if able"
        lures = [(y, arg) for y in att for name, arg in map(rule_arg, scripts.statics(plan.ch(y))) if name == "lure"]
        wanted = list(dict.fromkeys([*wanted, *(plan.oid(y) for y, arg in lures
                                                if not arg or _any_selector(state, plan.info, arg, b, plan.ch(b), y))]))
        for x in (y for y in att if plan.oid(y) in wanted):
            blocks = used.get(b.id, [])  # (-- multiple blocks (wave 13B) -- a blocker with a block to spare could add this one)
            # (at its limit, a block that obeys a requirement of its own isn't traded for this one: -- review (wave 14R) -- one
            # that obeys none is no excuse)
            if x.id in covered.get(b.id, set()) or (blocks and len(blocks) >= block_limit(plan, plan.ch(b)) and any(
                    plan.oid(state.cards[i]) in wanted or "must_be_blocked" in scripts.statics(plan.ch(state.cards[i])) for i in blocks)):
                continue
            if could(b, x, joined=joined(b, x)):
                return f"{b.name} blocks {x.name} this turn if able"
    for x in att:
        # -- counters (wave 44C) -- 509.1c: "~ must be blocked by two or more creatures if able" (Gorm the Great): blocked by one is short while another creature could join it
        two = "must_be_blocked_two" in scripts.statics(plan.ch(x))
        have = per_attacker.get(x.id, 0)
        if (have and not two) or have >= 2 or not ("must_be_blocked" in scripts.statics(plan.ch(x)) or two):
            continue
        # creatures free to block it: idle ones, and ones blocking an attacker that needn't be blocked
        # (-- review (wave 7R) -- 509.1c: not one whose own requirement that block obeys: "blocks each combat if able" or
        # "blocks this creature if able": taking it away would only trade one obeyed requirement for another)
        def obeying(d: A.BlockDeclaration) -> bool:
            blocker, target = plan.ch(state.cards[d.blocker_id]), state.cards[d.attacker_id]
            return "must_block" in scripts.statics(blocker) or any(name == "lure" for name, _ in map(rule_arg, scripts.statics(plan.ch(target)))) or any(
                name == "must_block_obj" and arg == plan.oid(target) for name, arg in map(rule_arg, scripts.statics(blocker)))

        spare = [state.cards[b] for b, ids in used.items() if len(ids) < block_limit(plan, plan.ch(state.cards[b]))]
        free = idle + spare + [state.cards[d.blocker_id] for d in a.blocks
                               if state.cards[d.blocker_id] not in spare
                               and "must_be_blocked" not in scripts.statics(plan.ch(state.cards[d.attacker_id])) and not obeying(d)]
        able = [b for b in free if x.id not in used.get(b.id, []) and could(b, x, joined=len(free))]  # (wave 44C: not one already blocking it)
        if len(able) >= (1 if have else min_blockers(plan.ch(x))):
            return f"{x.name} must be blocked {'by two or more creatures ' if have else ''}if able"
    # -- block events (wave 53C) -- 509.1c: "~ must be blocked by a Dalek if able" (Ace's Baseball Bat), "must be blocked by an Eldrazi if able" (Slayer's Cleaver): at least one creature
    # of that kind must block it when one can; a block by another creature doesn't meet it (a creature blocking something else is free to block it instead unless that block
    # meets a requirement of its own)
    for x in att:
        for name, arg in map(rule_arg, scripts.statics(plan.ch(x))):
            if name != "must_be_blocked_by":
                continue
            if any(_any_selector(state, plan.info, arg, state.cards[d.blocker_id], plan.ch(state.cards[d.blocker_id]), x) for d in effective if d.attacker_id == x.id):
                continue
            swappable = [state.cards[d.blocker_id] for d in a.blocks if d.attacker_id != x.id and len(used.get(d.blocker_id, [])) == 1
                         and "must_be_blocked" not in scripts.statics(plan.ch(state.cards[d.attacker_id])) and not any(
                             n == "must_be_blocked_by" for n, _ in map(rule_arg, scripts.statics(plan.ch(state.cards[d.attacker_id]))))]
            spare = [state.cards[b] for b, ids in used.items() if 0 < len(ids) < block_limit(plan, plan.ch(state.cards[b]))]
            if any(x.id not in used.get(b.id, []) and _any_selector(state, plan.info, arg, b, plan.ch(b), x) and could(b, x, joined=1)
                   for b in {c.id: c for c in [*idle, *spare, *swappable]}.values()):
                return f"{x.name} must be blocked by {_phrase(arg)} if able"
    return None


# -- combat damage ----------------------------------------------------------------------
def _deals(ch: Characteristics, rnd: Round) -> bool:
    first = "first strike" in ch.keywords
    double = "double strike" in ch.keywords
    if rnd == "only":
        return True
    if rnd == "first":
        return first or double
    return not first or double


def has_first_strike_round(plan: Plan) -> bool:
    return any(
        (c.is_attacking or c.is_blocking) and c.zone.endswith(":battlefield")
        and bool({"first strike", "double strike"} & plan.ch(c).keywords)
        for c in plan.state.cards.values()
    )


@dataclass
class CombatDamage:
    """All combat damage of one round, computed before any of it is dealt (it is simultaneous)."""

    creatures: dict[str, int] = field(default_factory=dict)
    players: dict[str, int] = field(default_factory=dict)
    walkers: dict[str, int] = field(default_factory=dict)
    lifelink: dict[str, int] = field(default_factory=dict)  # source card -> life its controller gains (702.15e)
    wither: dict[str, int] = field(default_factory=dict)  # -1/-1 counters (wither, infect)
    poison: dict[str, int] = field(default_factory=dict)  # poison counters (infect)
    commander: dict[tuple[str, str], int] = field(default_factory=dict)
    deathtouched: list[str] = field(default_factory=list)
    dealt: list[tuple[str, str, int]] = field(default_factory=list)  # (source card, target card/player, amount)

    @property
    def empty(self) -> bool:
        return not (self.creatures or self.players or self.walkers or self.wither or self.poison)


# -- damage wordings (wave 6B) --
def _assigns(card: CardInstance, ch: Characteristics) -> int | None:
    """510.1a: the combat damage a creature assigns is its power — or its toughness while a static says so ("Each
    creature assigns combat damage equal to its toughness rather than its power", Doran: the rule assign_toughness)."""
    if "assign_none" in ch.imposed:  # -- no combat damage (wave 19E) -- "assigns no combat damage this turn"
        return 0
    if "assign_toughness" in ch.imposed:
        return toughness(card, ch)
    # -- counters (wave 44C) -- 510.1a: "assigns combat damage as though its power were positive" (Loot, the Anomaly): only the amount assigned changes, not its power; a toughness-based assignment wins
    p = power(card, ch)
    if "assign_toughness_if_tougher" in ch.imposed:
        t = toughness(card, ch)
        if p is not None and t is not None and t > p:
            return t
    return abs(p) if p is not None and "assign_abs_power" in ch.imposed else p
# -- end damage wordings (wave 6B) --


def compute_combat_damage(plan: Plan, rnd: Round, pending: list[tuple[CardInstance, list[CardInstance], list[int]]] | None = None,
                          *, protection_preview: bool = False) -> CombatDamage:
    """``pending`` (if given) collects the attackers whose division is still to be chosen (510.1c): (attacker, its blockers,
    the lethal damage for each), in order, each with the damage the earlier attackers assign already counted."""
    state = plan.state
    r = plan.rules
    out = CombatDamage()

    def _protection_prevents(source_card: CardInstance, source: Characteristics, target: str) -> bool:
        """-- refused grants/replacements (wave 3R2) -- 615.12: not combat damage that can't be prevented."""
        if not protection_preview:
            return False
        from app.rules import source_shields

        ev = {"source_card": source_card.id, "source_oid": plan.oid(source_card), "target": target, "combat": True, "attacking_player": plan.active,
              "src": replace.source_info(plan, source_card.id, plan.oid(source_card), source, source_card.controller)}
        return source_shields.protection_applies(plan, ev)

    def hit_creature(source_card: CardInstance, source: Characteristics, target: CardInstance, n: int) -> int:
        """Assign ``n`` damage to a creature; returns how much is dealt (protection prevents it, 702.16e)."""
        if protection.protected_from(plan.ch(target), wave110f_cards.damage_colors(plan, source)) and _protection_prevents(source_card, source, target.id):
            return 0
        into = out.wither if {"wither", "infect"} & source.keywords else out.creatures
        into[target.id] = into.get(target.id, 0) + n
        out.dealt.append((source_card.id, target.id, n))
        if "deathtouch" in source.keywords:
            out.deathtouched.append(target.id)
        return n

    def gain(source_card: CardInstance, source: Characteristics, n: int) -> None:
        if n > 0 and "lifelink" in source.keywords:
            out.lifelink[source_card.id] = out.lifelink.get(source_card.id, 0) + n

    def hit_target(att: CardInstance, ach: Characteristics, n: int, tgt: Any = None) -> int:
        tgt = tgt or att.attacking  # (-- wave 110F -- ``tgt``: Butcher Orgg's defending player when it attacks a planeswalker)
        if tgt is None or n <= 0:
            return 0
        if tgt.kind == "player":
            if tgt.id not in state.players:
                return 0
            # -- player shields (wave 5E) -- 702.16e, 702.16j
            from app.rules import player_shields

            if player_shields.protected_from(plan, tgt.id, wave110f_cards.damage_colors(plan, ach)) is not None and _protection_prevents(att, ach, tgt.id):
                return 0
            into = out.poison if "infect" in ach.keywords else out.players
            into[tgt.id] = into.get(tgt.id, 0) + n
            toxic = sum(int(x) for ab in ach.abilities if ab.kind == "keywords" and "toxic" in ab.keywords
                        for x in re.findall(r"toxic (\d+)", ab.text.lower()))
            if toxic:  # 702.164: combat damage to a player also gives N poison counters
                out.poison[tgt.id] = out.poison.get(tgt.id, 0) + toxic
            out.dealt.append((att.id, tgt.id, n))
            if att.commander_key:
                key = (tgt.id, att.commander_key)
                out.commander[key] = out.commander.get(key, 0) + n
        elif tgt.id in state.cards and state.cards[tgt.id].zone.endswith(":battlefield"):
            if protection.protected_from(plan.ch(state.cards[tgt.id]), wave110f_cards.damage_colors(plan, ach)) and _protection_prevents(att, ach, tgt.id):
                return 0
            out.walkers[tgt.id] = out.walkers.get(tgt.id, 0) + n
            out.dealt.append((att.id, tgt.id, n))
        else:
            return 0
        return n

    def lethal(b: CardInstance, source: Characteristics, cap: int) -> int:
        """702.2c / 702.19b: the damage that is lethal to ``b``, counting damage already marked and what is assigned so far."""
        t = toughness(b, plan.ch(b))
        if "deathtouch" in source.keywords:
            return 1
        return cap if t is None else max(0, t - b.damage - out.creatures.get(b.id, 0) - out.wither.get(b.id, 0))

    blockers_all = [c for c in state.cards.values() if c.blocking and c.zone.endswith(":battlefield")]
    for att in attackers_on(state):
        ach = plan.ch(att)
        p = _assigns(att, ach)  # (wave 6B: 510.1a)
        if not _deals(ach, rnd) or p is None or p <= 0:
            continue
        blockers = [b for b in blockers_all if b.blocks(att.id)]
        dealt = 0
        if (shares := wave110f_cards.divided_shares(plan, att, ach)) is not None:  # -- wave 110F -- Butcher Orgg, Cunning Giant: as its controller chose
            for tid, n in shares.items():
                if n <= 0:
                    continue
                if tid in state.players:
                    dealt += hit_target(att, ach, n, A.AttackTarget(kind="player", id=tid))
                elif (c := state.cards.get(tid)) is not None and c.zone.endswith(":battlefield") and "Creature" in plan.ch(c).types:
                    dealt += hit_creature(att, ach, c, n)
        elif att.id in r.blocked and not r.assign_unblocked.get(att.id):  # (wave 19A: 510.1c "as though it weren't blocked": all to what it attacks)
            trample = "trample" in ach.keywords
            need = [lethal(b, ach, p) for b in blockers]
            shares = r.block_split.get(att.id)
            if shares is None and pending is not None and (len(blockers) > 1 or trample and blockers and p > sum(need)):
                # (-- review (wave 14R) -- 702.19d: with no blocker left, a trampler's damage all goes where it attacks: no choice)
                pending.append((att, blockers, need))  # 510.1c / 702.19b: its controller divides it (asked: ``ask_split``)
            if shares is not None:  # as its controller chose; 702.19b: the rest of a trampler's goes to what it attacks
                for b in blockers:
                    dealt += hit_creature(att, ach, b, shares[b.id]) if shares.get(b.id, 0) > 0 else 0
                if trample and att.attacking is not None:
                    dealt += hit_target(att, ach, shares.get(att.attacking.id, 0))
            else:  # nothing to choose: lethal to each blocker in order, the rest to the last (or, trampling, what it attacks)
                remaining = p
                for i, (b, lethal_b) in enumerate(zip(blockers, need, strict=True)):
                    amount = remaining if i == len(blockers) - 1 and not trample else min(remaining, lethal_b)
                    if amount > 0:
                        dealt += hit_creature(att, ach, b, amount)
                        remaining -= amount
                if remaining > 0 and trample:
                    dealt += hit_target(att, ach, remaining)
        else:
            dealt = hit_target(att, ach, p)
        gain(att, ach, dealt)
    for b in blockers_all:
        bch = plan.ch(b)
        p = _assigns(b, bch)  # (wave 6B: 510.1a)
        if not _deals(bch, rnd) or p is None or p <= 0:
            continue
        blocked = blocked_by(state, b)
        shares = r.block_split.get(b.id)  # 510.1d: divided as its controller chose (asked first: ``ask_split``)
        parts = [(t, shares.get(t.id, 0)) for t in blocked] if len(blocked) > 1 and shares else [(t, p) for t in blocked[:1]]
        gain(b, bch, sum(hit_creature(b, bch, t, n) for t, n in parts if n > 0))
    return out


# -- multiple blocks (wave 13B) -- 510.1d
def blocked_by(state: GameState, b: CardInstance) -> list[CardInstance]:
    """The attackers a blocker is blocking now (510.1d: those still attacking and on the battlefield)."""
    found = (state.cards.get(i) for i in [b.blocking or "", *b.blocking_more])
    return [t for t in found if t is not None and t.is_attacking and t.zone.endswith(":battlefield")]


def ask_split(plan: Plan, rnd: Round, then: str) -> bool:
    """510.1c-d: an attacker blocked by two or more creatures — or a trampler with damage beyond lethal (702.19b) — and a
    blocker blocking two or more attackers assign their combat damage divided as their controller chooses (any share may be
    0; a trampler's damage may go to what it attacks only once every blocker has lethal). Asks the first creature (attackers
    first, 510.1) whose division isn't known yet; False: none is missing."""
    from app.rules import group_unblocked

    r = plan.rules
    for att in attackers_on(plan.state):  # -- static_other sweep (wave 19A) -- 510.1c: "You may have this creature assign its combat damage as though it weren't blocked"
        ach = plan.ch(att)
        if att.id in r.blocked and att.id not in r.assign_unblocked and group_unblocked.allows(plan, att, ach) and _deals(ach, rnd) \
                and (_assigns(att, ach) or 0) > 0:
            decide(plan, player=att.controller, kind="confirm",
                   prompt=f"Have {att.name} assign its combat damage as though it weren't blocked?",
                   options=[DecisionOption(id="yes", label="As though it weren't blocked"), DecisionOption(id="no", label="Among its blockers")],
                   resume={"step": "assign_unblocked", "round": rnd, "then": then, "creature": att.id})
            return True
    for att in attackers_on(plan.state):  # -- wave 110F -- Butcher Orgg, Cunning Giant (510.1 as the card changes it)
        if wave110f_cards.ask_divide(plan, att, rnd, then, _deals(plan.ch(att), rnd), _assigns(att, plan.ch(att))):
            return True
    todo: list[tuple[CardInstance, list[CardInstance], list[int]]] = []
    compute_combat_damage(plan, rnd, todo)
    if todo:
        a, blockers, need = todo[0]
        tgt, free = a.attacking, None
        options = [DecisionOption(id=t.id, label=t.name or "Blocker", card_id=t.id) for t in blockers]
        if "trample" in plan.ch(a).keywords and tgt is not None and (tgt.id in plan.state.players or tgt.id in plan.state.cards):
            free = len(options)
            options.append(DecisionOption(id=tgt.id, label=plan.state.players[tgt.id].name if tgt.id in plan.state.players
                                          else plan.state.cards[tgt.id].name or "Planeswalker"))
        p = _assigns(a, plan.ch(a)) or 0
        lethal = need if free is not None else []
        decide(plan, player=banding.damage_chooser(plan, a, blockers), kind="divide", prompt=f"Divide {a.name}'s {p} combat damage among the creatures blocking it"
               + (" and what it attacks" if free is not None else ""), options=options, min_choices=len(options), max_choices=len(options),
               display={"kind": "divide", "total": p, "what": "damage", "least": 0, "lethal": lethal},
               resume={"step": "block_split", "round": rnd, "then": then, "creature": a.id, "total": p, "least": 0,
                       "lethal": lethal, "free": free})
        return True
    for b in plan.state.cards.values():
        if not (b.blocking and b.blocking_more) or b.id in r.block_split or not b.zone.endswith(":battlefield"):
            continue
        bch, bp = plan.ch(b), _assigns(b, plan.ch(b))
        targets = blocked_by(plan.state, b)
        if len(targets) < 2 or bp is None or bp <= 0 or not _deals(bch, rnd):
            continue
        decide(plan, player=banding.damage_chooser(plan, b, targets), kind="divide", prompt=f"Divide {b.name}'s {bp} combat damage among the creatures it blocks",
               options=[DecisionOption(id=t.id, label=t.name or "Attacker", card_id=t.id) for t in targets],
               min_choices=len(targets), max_choices=len(targets), display={"kind": "divide", "total": bp, "what": "damage", "least": 0},
               resume={"step": "block_split", "round": rnd, "then": then, "creature": b.id, "total": bp, "least": 0})
        return True
    return False


def damage_preview(plan: Plan, rnd: Round) -> str:
    """A compact public summary of the damage about to be dealt (for ASSISTED confirmation)."""
    dmg = compute_combat_damage(plan, rnd, protection_preview=True)
    parts = []
    for source, target, n in dmg.dealt:
        who = plan.state.players[target].name if target in plan.state.players else plan.state.cards[target].name
        parts.append(f"{plan.state.cards[source].name} → {who} {n}")
    return "; ".join(parts) or "none"


_DAMAGE_KEYWORDS = frozenset({"lifelink", "deathtouch", "wither", "infect"})


def _toxic(sch: Characteristics) -> int:
    return sum(int(x) for ab in sch.abilities if ab.kind == "keywords" and "toxic" in ab.keywords
               for x in re.findall(r"toxic (\d+)", ab.text.lower()))


def combat_damage_events(plan: Plan, dmg: CombatDamage) -> list[dict[str, Any]]:
    """-- replacement effects stage 2 (wave 2E) -- The round's assignments (source, recipient,
    amount) as damage events for app/rules/replace.py, each with what its source is (609.7c), its
    damage keywords, whose lifelink gain it is (702.15e: per source) and its toxic value
    (702.164c: combat damage to a player)."""
    events = []
    for src, tgt, n in dmg.dealt:
        card = plan.state.cards.get(src)
        if card is None or n <= 0:
            continue
        sch = plan.ch(card)
        events.append({"source_card": src, "source_oid": plan.oid(src), "target": tgt, "amount": n, "combat": True, "attacking_player": plan.active,
                       "src": replace.source_info(plan, src, plan.oid(src), sch, card.controller),
                       "kw": sorted(sch.keywords & _DAMAGE_KEYWORDS), "lkey": src,
                       "toxic": _toxic(sch) if tgt in plan.state.players else 0})
    return events


def deal_combat_damage(plan: Plan, rnd: Round, shield_order: list[str] | None = None,
                       answers: dict[str, str] | None = None) -> bool:
    """Deal this round's combat damage, all at once (510.2): the assignments as damage events
    through the replacement and prevention effects (614, 615, 616 — app/rules/replace.py), then
    their results (120.3; lifelink, wither / infect counters and poison through their own
    replacement effects, 120.4c). False: a choice is open — which effect applies first (616.1) or
    which source's damage a shield prevents (615.7); the round is dealt again with the answers
    (``shield_order``, ``answers``: replace.resume_site)."""
    dmg = compute_combat_damage(plan, rnd)
    events = combat_damage_events(plan, dmg)
    out = replace.damage_outcome(plan, events, answers=dict(answers or {}), order=shield_order, ask=True)
    if isinstance(out, replace.ShieldAsk):
        replace.ask_shield(plan, out, {"round": rnd, "answers": dict(answers or {})}, list(shield_order or []))
        return False
    if not isinstance(out, replace.DamageOutcome):
        replace.ask(plan, out, dict(answers or {}), {"round": rnd, "order": list(shield_order or [])})
        return False
    commander: dict[tuple[str, str], int] = {}
    for ev in out.events:  # 903.10a: combat damage a commander dealt to a player (as dealt)
        source = plan.state.cards.get(ev["source_card"])
        if ev["target"] in plan.state.players and source is not None and source.commander_key:
            key = (ev["target"], source.commander_key)
            commander[key] = commander.get(key, 0) + int(ev["amount"])
    plan.rules.block_split = {}
    plan.rules.assign_unblocked = {}
    dealt = [(ev["source_card"], ev["target"], int(ev["amount"])) for ev in out.events]
    if not replace.do_damage(plan, out, actor=plan.active, combat=True, extra={
        "first_strike": rnd == "first",
        "commander": [{"player": pid, "commander": key, "amount": n} for (pid, key), n in commander.items()]},
        then={"do": "combat_damage_tail", "dealt": dealt}):
        return False
    after_damage(plan, dealt)
    return True


def after_damage(plan: Plan, dealt: list[tuple[str, str, int]]) -> None:
    hit_players = [plan.state.cards[src] for src, tgt, n in dealt
                   if tgt in plan.state.players and n > 0 and src in plan.state.cards]
    if hit_players:
        from app.rules import triggers  # triggers → plan; imported late

        hit: dict[str, list[str]] = {}  # (wave 43A: the players each hit, for a trigger multiplier: Felix Five-Boots)
        for src, tgt, n in dealt:
            if tgt in plan.state.players and n > 0 and src in plan.state.cards and tgt not in hit.setdefault(src, []):
                hit[src].append(tgt)
        triggers.dealt_combat_damage_to_player(plan, list({c.id: c for c in hit_players}.values()), hit)
    monarch = plan.state.table.monarch
    # (-- review 29D -- 725.2: combat damage dealt to the monarch, whether or not it made them lose life: 119.8, 120.3a)
    if monarch and any(tgt == monarch and n > 0 for _src, tgt, n in dealt):
        from app.rules import triggers  # triggers → plan; imported late

        hitters = [plan.state.cards[src] for src, tgt, n in dealt if tgt == monarch and n > 0 and src in plan.state.cards]
        triggers.monarch_damaged(plan, hitters[:1])  # one trigger per combat damage event
    # -- counters & designations (wave 3E): 726.2 the initiative changes hands --
    from app.rules import designations

    designations.initiative_damaged(plan, dealt)
    from app.rules import triggers

    # 603.2: capture abilities as the completed damage event happens, before a
    # later SBA detaches equipment or removes a conditional source ability.
    # Ordering, targets and stack placement still wait until SBAs finish.
    triggers.collect(plan)


@world_native80
def end_combat(plan: Plan) -> None:
    from app.rules import permissions

    permissions.expire_combat(plan)
    if any(c.is_attacking or c.is_blocking or c.attack_defender_lost for c in plan.state.cards.values()):
        plan.do({"type": "clear_combat"}, actor=plan.active)
    r = plan.rules
    if any(e.duration == "end_of_combat" for e in r.effects):  # -- review (wave 18E) -- "this combat" (provoke, 702.39a) ends here
        r.effects = [e for e in r.effects if e.duration != "end_of_combat"]
        for card in list(plan.state.cards.values()):
            for marker in [m for m in card.effects if m.text == "this combat"]:
                plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": marker.id}, actor=plan.active)
    r.replacements = [x for x in r.replacements if x.get("until") != "end_of_combat"]  # -- one-shot shields (wave 35A) -- "this combat"
    r.delayed = [t for t in r.delayed if not t.until_combat]  # -- block events (wave 53C) -- "whenever … this combat" stops watching (500.5)
    r.blocked = []
    r.attacking_bands = []
    r.block_split = {}
    r.assign_unblocked = {}
    r.block_caps = {}  # (wave 49B) "this combat"
    r.declare_choosers = {k: v for k, v in r.declare_choosers.items() if not v.get("combat")}  # (wave 110A)
    r.no_attackers = False
    r.combat_round = ""


def _resume_damage_tail(plan: Plan, then: dict[str, Any]) -> None:
    from app.rules.engine import _after_resolution

    after_damage(plan, [(str(a), str(b), int(n)) for a, b, n in then['dealt']])
    _after_resolution(plan)


replace.THEN['combat_damage_tail'] = _resume_damage_tail
