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
from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, GameState, zone_key
from app.rules import characteristics as chars
from app.rules import protection, replace, scripts, selectors
from app.rules.casting import summoning_sick
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.plan import Plan, decide, live_players
from app.rules.sba import power, toughness
from app.rules.statics import rule_arg, rule_selectors

Round = Literal["only", "first", "second"]


# -- legality -------------------------------------------------------------------------
def attack_problem(state: GameState, card: CardInstance, ch: Characteristics) -> str | None:
    if not card.zone.endswith(":battlefield") or not ch.is_creature:
        return "Only creatures on the battlefield can attack"
    if card.controller != state.turn.active_player:
        return "Only the active player's creatures can attack"
    if card.tapped:
        return f"{ch.name} is tapped"
    if "defender" in ch.keywords:
        return f"{ch.name} has defender"
    if {"cant_attack", "cant_attack_or_block"} & scripts.statics(ch):
        return f"{ch.name} can't attack"
    if "haste" not in ch.keywords and summoning_sick(state, card):
        return f"{ch.name} has summoning sickness"
    return None


def block_problem(state: GameState, blocker: CardInstance, bch: Characteristics, attacker: CardInstance,
                  ach: Characteristics, info: CardInfo | None = None) -> str | None:
    if not blocker.zone.endswith(":battlefield") or not bch.is_creature:
        return "Only creatures on the battlefield can block"
    if blocker.tapped:
        return f"{bch.name} is tapped"
    if {"cant_block", "cant_attack_or_block"} & scripts.statics(bch):
        return f"{bch.name} can't block"
    if "cant_be_blocked" in scripts.statics(ach):
        return f"{ach.name} can't be blocked"
    # rules of the attacker about its blockers (evasion, 509.1b: flying is one of them) and of the
    # blocker about what it may block (app/rules/statics.py has the vocabulary), each evaluated
    # against the other creature in the block
    for rule in sorted(evasion_rules(ach)):
        name, arg = rule_arg(rule)
        if name == "cant_be_blocked_by" and _any_selector(state, info, arg, blocker, bch, attacker):
            return f"{ach.name} can't be blocked by {_phrase(arg)}"
        if name == "cant_be_blocked_except_by" and not _any_selector(state, info, arg, blocker, bch, attacker):
            return f"{ach.name} can't be blocked except by {_phrase(arg)}"
        if name == "cant_be_blocked_by_power" and (_power(bch) < _power(ach) if arg == "less" else _power(bch) > _power(ach)):
            return f"{ach.name} can't be blocked by creatures with {arg} power"
        if name == "cant_be_blocked_if_defender_controls" and _defender_controls(state, info, arg, blocker.controller):
            return f"{ach.name} can't be blocked while {state.players[blocker.controller].name} controls {_phrase(arg)}"
    for rule in sorted(scripts.statics(bch)):
        name, arg = rule_arg(rule)
        if name == "block_only" and not _any_selector(state, info, arg, attacker, ach, blocker):
            return f"{bch.name} can block only {_phrase(arg)}"
        if name == "cant_block_sel" and _any_selector(state, info, arg, attacker, ach, blocker):
            return f"{bch.name} can't block {_phrase(arg)}"
        if name == "cant_block_power" and _power(ach) > _power(bch):
            return f"{bch.name} can't block creatures with greater power"
    # landwalk (702.14): unblockable while the defending player controls a land of that type
    for walk, land in LANDWALK.items():
        if walk in ach.keywords and _controls_land(state, blocker.controller, land, info):
            return f"{ach.name} has {walk}: it can't be blocked while you control a {land}"
    if "shadow" in ach.keywords and "shadow" not in bch.keywords:
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
    return any(selectors.candidates(view, sel, defender) for sel in rule_selectors(arg))


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
        if sel.without_keywords:
            text += " without " + " and ".join(sel.without_keywords)
        for what, op, n in sel.compare:
            text += f" with {'mana value' if what == 'mv' else what} {n} or {'less' if op == '<=' else 'greater' if op == '>=' else 'equal'}"
        parts.append(text)
    return " or ".join(parts)


LANDWALK = {"plainswalk": "Plains", "islandwalk": "Island", "swampwalk": "Swamp", "mountainwalk": "Mountain",
            "forestwalk": "Forest", "desertwalk": "Desert"}


def _controls_land(state: GameState, player: str, subtype: str, info: CardInfo | None) -> bool:
    for cid in state.zones.get(zone_key(player, "battlefield"), []):
        card = state.cards[cid]
        if card.controller != player:
            continue
        ch = chars.of(card, info) if info is not None else None
        if ch is not None and ch.is_land and subtype in ch.subtypes:
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
            if card.controller == pid and "Planeswalker" in chars.of(card, info).types:
                out.append(cid)
    out += battles.attackable(state, attacker, defenders, lambda c: derive(state, c, chars.of(c, info), info))
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
    r.blockers_pending = []
    r.combat_round = ""
    ap = plan.active
    eligible = [cid for cid in plan.state.zones.get(zone_key(ap, "battlefield"), [])
                if attack_problem(plan.state, plan.state.cards[cid], plan.ch(plan.state.cards[cid])) is None]
    targets = attack_targets(plan.state, ap, plan.info)
    if not eligible or not targets:
        r.no_attackers = True
        return
    decide(plan, player=ap, kind="declare_attackers", prompt="Declare attackers (or attack with nothing)",
           options=[DecisionOption(id=f"a:{cid}", label=plan.state.cards[cid].name or "Creature", card_id=cid) for cid in eligible]
           + [DecisionOption(id=f"t:{t}", label=_label(plan.state, t), card_id=t if t in plan.state.cards else None)
              for t in targets],
           min_choices=0, max_choices=len(eligible), resume={"step": "declare_attackers"})


def declare_attackers(plan: Plan, a: A.DeclareAttackers) -> None:
    from app.rules.engine import advance  # the engine imports this module

    r = plan.rules
    d = r.decision
    if d is None or d.kind != "declare_attackers":
        raise ActionError("Attackers are declared at the start of the declare attackers step")
    if d.player != plan.actor:
        raise ActionError(f"{plan.name(d.player)} is declaring attackers")
    eligible = {o.id[2:] for o in d.options if o.id.startswith("a:")}
    targets = {o.id[2:] for o in d.options if o.id.startswith("t:")}
    seen: set[str] = set()
    for decl in a.attackers:
        card = plan.state.cards.get(decl.card_id)
        if decl.card_id not in eligible or card is None:
            raise ActionError("That creature can't attack now")
        problem = attack_problem(plan.state, card, plan.ch(card))
        if problem:
            raise ActionError(problem)
        if decl.target not in targets:
            raise ActionError(f"{card.name} can't attack that")
        if "attack_needs_island" in scripts.statics(plan.ch(card)):
            defender = decl.target if decl.target in plan.state.players else \
                defender_of(plan.state, A.AttackTarget(kind="card", id=decl.target))
            if not _controls_land(plan.state, defender or "", "Island", plan.info):
                raise ActionError(f"{card.name} can't attack unless defending player controls an Island")
        if decl.card_id in seen:
            raise ActionError(f"{card.name} can only attack once")
        seen.add(decl.card_id)
        if "cant_attack_alone" in scripts.statics(plan.ch(card)) and len(a.attackers) == 1:
            raise ActionError(f"{card.name} can't attack alone")  # 506.5 / 508.1c
    # 508.1d: a creature that "attacks each combat if able" must attack when it can
    for cid in eligible - seen:
        card = plan.state.cards.get(cid)
        if card is not None and "must_attack" in scripts.statics(plan.ch(card)) and \
                attack_problem(plan.state, card, plan.ch(card)) is None and targets:
            raise ActionError(f"{card.name} attacks each combat if able")
    goad_problem = goad_requirements(plan, eligible, targets, {x.card_id: x.target for x in a.attackers})
    if goad_problem:  # -- keyword actions & face-down (wave 3F) --
        raise ActionError(goad_problem)
    r.decision = None
    if not a.attackers:
        r.no_attackers = True
        plan.note(f"{plan.name(plan.actor)} doesn't attack")
    else:
        to_tap = [x.card_id for x in a.attackers if "vigilance" not in plan.ch(plan.state.cards[x.card_id]).keywords]
        if to_tap:
            plan.do({"type": "tap", "card_ids": to_tap, "tapped": True})
        by_target: dict[str, list[str]] = {}
        for decl in a.attackers:
            by_target.setdefault(decl.target, []).append(decl.card_id)
        for target, ids in by_target.items():
            kind = "player" if target in plan.state.players else "card"
            plan.do({"type": "attack", "card_ids": ids, "target": {"kind": kind, "id": target}})
        from app.game.rules_state import note_attack
        from app.rules import triggers  # triggers → plan; imported late

        note_attack(plan.state, plan.actor)  # 508.1: "if you attacked this turn" (conditional clauses, wave 1B)
        triggers.attacked(plan, [plan.state.cards[x.card_id] for x in a.attackers])
    r.priority = plan.active
    r.passed = []
    advance(plan)


# -- keyword actions & face-down (wave 3F) ------------------------------------------------------
def goad_requirements(plan: Plan, eligible: set[str], targets: set[str], declared: dict[str, str]) -> str | None:
    """701.15b / 508.1d for goaded creatures: a goaded creature attacks each combat if able, and
    attacks a player other than each player who goaded it if able (701.15c: one requirement per
    goading player; attacking a planeswalker obeys none of those). The declaration must obey as many
    of each creature's requirements as it could without breaking a restriction (508.1d); each
    goaded creature's requirements are judged on its own, against the places it may attack.
    Costs to attack are never required (508.1d), and none are modelled here."""
    from app.rules.keyword_actions import goaded_by

    live = set(plan.live())
    for cid in sorted(eligible):
        card = plan.state.cards.get(cid)
        if card is None:
            continue
        ch = plan.ch(card)
        goaders = goaded_by(ch)
        if not goaders or attack_problem(plan.state, card, ch) is not None:
            continue
        st = scripts.statics(ch)
        if "cant_attack_alone" in st and len(eligible) == 1:
            continue  # (it can't attack at all: alone is the only way it could)
        places = [t for t in targets if "attack_needs_island" not in st
                  or _controls_land(plan.state, t if t in plan.state.players else plan.state.cards[t].controller,
                                    "Island", plan.info)]
        if not places:
            continue

        def obeyed(place: str | None, others: set[str] = goaders & live) -> int:
            if place is None:
                return 0
            return 1 + sum(1 for g in others if place in plan.state.players and place != g)

        best = max(obeyed(t) for t in places)
        if obeyed(declared.get(cid)) < best:
            who = " or ".join(sorted(plan.name(g) for g in goaders & live)) or "anyone"
            if cid not in declared:
                return f"{card.name} is goaded: it attacks each combat if able"
            return f"{card.name} is goaded: it attacks a player other than {who} if able"
    return None


# -- declare blockers -------------------------------------------------------------------
def attackers_on(state: GameState) -> list[CardInstance]:
    return [c for c in state.cards.values() if c.attacking is not None and c.zone.endswith(":battlefield")]


def start_declare_blockers(plan: Plan) -> None:
    r = plan.rules
    r.blocked = []
    attacked = {defender_of(plan.state, c.attacking) for c in attackers_on(plan.state)}
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
        attackers = [c for c in attackers_on(state) if defender_of(state, c.attacking) == pid]
        blockers = [state.cards[cid] for cid in state.zones.get(zone_key(pid, "battlefield"), [])
                    if state.cards[cid].controller == pid and not state.cards[cid].tapped
                    and plan.ch(state.cards[cid]).is_creature]
        if not attackers or not blockers:
            r.blockers_pending.pop(0)
            continue
        decide(plan, player=pid, kind="declare_blockers", prompt="Declare blockers (or block with nothing)",
               options=[DecisionOption(id=f"b:{c.id}", label=c.name or "Creature", card_id=c.id) for c in blockers]
               + [DecisionOption(id=f"a:{c.id}", label=c.name or "Attacker", card_id=c.id) for c in attackers],
               min_choices=0, max_choices=len(blockers), resume={"step": "declare_blockers"})
        return


def declare_blockers(plan: Plan, a: A.DeclareBlockers) -> None:
    from app.rules.engine import advance

    r = plan.rules
    d = r.decision
    if d is None or d.kind != "declare_blockers":
        raise ActionError("Blockers are declared at the start of the declare blockers step")
    if d.player != plan.actor:
        raise ActionError(f"{plan.name(d.player)} is declaring blockers")
    blockers = {o.id[2:] for o in d.options if o.id.startswith("b:")}
    attackers = {o.id[2:] for o in d.options if o.id.startswith("a:")}
    used: set[str] = set()
    per_attacker: dict[str, int] = {}
    for decl in a.blocks:
        blocker = plan.state.cards.get(decl.blocker_id)
        attacker = plan.state.cards.get(decl.attacker_id)
        if decl.blocker_id not in blockers or blocker is None:
            raise ActionError("That creature can't block now")
        if decl.attacker_id not in attackers or attacker is None:
            raise ActionError(f"{blocker.name} can't block that")
        if decl.blocker_id in used:
            raise ActionError(f"{blocker.name} can only block one attacker")
        used.add(decl.blocker_id)
        problem = block_problem(plan.state, blocker, plan.ch(blocker), attacker, plan.ch(attacker), plan.info)
        if problem:
            raise ActionError(problem)
        per_attacker[decl.attacker_id] = per_attacker.get(decl.attacker_id, 0) + 1
    for aid, n in per_attacker.items():
        ach = plan.ch(plan.state.cards[aid])
        least = min_blockers(ach)
        if n < least:
            raise ActionError(f"{ach.name} can't be blocked except by {least} or more creatures"
                              + (" (menace)" if "menace" in ach.keywords else ""))
        if "max_one_blocker" in scripts.statics(ach) and n > 1:
            raise ActionError(f"{ach.name} can't be blocked by more than one creature")
    if len(a.blocks) == 1:  # 506.5: blocking alone
        lone = plan.state.cards[a.blocks[0].blocker_id]
        if "cant_block_alone" in scripts.statics(plan.ch(lone)):
            raise ActionError(f"{lone.name} can't block alone")
    problem = block_requirements(plan, a, blockers, attackers, used, per_attacker)
    if problem:
        raise ActionError(problem)
    r.decision = None
    if r.blockers_pending and r.blockers_pending[0] == plan.actor:
        r.blockers_pending.pop(0)
    for decl in a.blocks:
        plan.do({"type": "block", "card_id": decl.blocker_id, "attacker_id": decl.attacker_id})
    r.blocked = list(dict.fromkeys([*r.blocked, *per_attacker]))
    if a.blocks:
        from app.rules import triggers  # triggers → plan; imported late

        triggers.blocked(plan, [plan.state.cards[d.blocker_id] for d in a.blocks],
                         [plan.state.cards[aid] for aid in per_attacker])
        triggers.flanking(plan, [(plan.state.cards[d.blocker_id], plan.state.cards[d.attacker_id]) for d in a.blocks])
    if not a.blocks:
        plan.note(f"{plan.name(plan.actor)} doesn't block")
    ask_next_blocker(plan)
    if r.decision is None:
        blocks_declared(plan)
        r.priority = plan.active
        r.passed = []
        advance(plan)


def block_requirements(plan: Plan, a: A.DeclareBlockers, blockers: set[str], attackers: set[str],
                       used: set[str], per_attacker: dict[str, int]) -> str | None:
    """509.1c requirements the declaration disobeys although it could obey them: "~ blocks each
    combat if able" (must_block, on a creature of the defending player) and "~ must be blocked if
    able" (must_be_blocked, on an attacker). Each requirement is judged on its own, against the
    blocks declared (one more block that no restriction forbids, 509.1b), not as the maximum over
    every combination of blocks the rule describes; a creature that can't block alone counts as
    able only once something else blocks."""
    state = plan.state
    idle = [state.cards[b] for b in blockers if b not in used]
    att = [state.cards[x] for x in attackers]

    def could(blocker: CardInstance, attacker: CardInstance, *, joined: int) -> bool:
        bch, ach = plan.ch(blocker), plan.ch(attacker)
        if block_problem(state, blocker, bch, attacker, ach, plan.info) is not None:
            return False
        if "cant_block_alone" in scripts.statics(bch) and not a.blocks:
            return False
        return min_blockers(ach) <= joined

    for b in idle:
        if "must_block" in scripts.statics(plan.ch(b)) and any(could(b, x, joined=1 + per_attacker.get(x.id, 0)) for x in att):
            return f"{b.name} blocks each combat if able"
    for x in att:
        if x.id in per_attacker or "must_be_blocked" not in scripts.statics(plan.ch(x)):
            continue
        # creatures free to block it: idle ones, and ones blocking an attacker that needn't be blocked
        free = idle + [state.cards[d.blocker_id] for d in a.blocks
                       if "must_be_blocked" not in scripts.statics(plan.ch(state.cards[d.attacker_id]))]
        able = [b for b in free if could(b, x, joined=len(free))]
        if len(able) >= min_blockers(plan.ch(x)):
            return f"{x.name} must be blocked if able"
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
        (c.attacking is not None or c.blocking) and c.zone.endswith(":battlefield")
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


def compute_combat_damage(plan: Plan, rnd: Round) -> CombatDamage:
    state = plan.state
    r = plan.rules
    out = CombatDamage()

    def _protection_prevents(source_card: CardInstance, source: Characteristics, target: str) -> bool:
        """-- refused grants/replacements (wave 3R2) -- 615.12: not combat damage that can't be prevented."""
        from app.rules import source_shields

        ev = {"source_card": source_card.id, "source_oid": plan.oid(source_card), "target": target, "combat": True,
              "src": replace.source_info(plan, source_card.id, plan.oid(source_card), source, source_card.controller)}
        return source_shields.protection_applies(plan, ev)

    def hit_creature(source_card: CardInstance, source: Characteristics, target: CardInstance, n: int) -> int:
        """Assign ``n`` damage to a creature; returns how much is dealt (protection prevents it, 702.16e)."""
        if protection.protected_from(plan.ch(target), source) and _protection_prevents(source_card, source, target.id):
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

    def hit_target(att: CardInstance, ach: Characteristics, n: int) -> int:
        tgt = att.attacking
        if tgt is None or n <= 0:
            return 0
        if tgt.kind == "player":
            if tgt.id not in state.players:
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
            if protection.protected_from(plan.ch(state.cards[tgt.id]), ach) and _protection_prevents(att, ach, tgt.id):
                return 0
            out.walkers[tgt.id] = out.walkers.get(tgt.id, 0) + n
            out.dealt.append((att.id, tgt.id, n))
        else:
            return 0
        return n

    blockers_all = [c for c in state.cards.values() if c.blocking and c.zone.endswith(":battlefield")]
    for att in attackers_on(state):
        ach = plan.ch(att)
        p = power(att, ach)
        if not _deals(ach, rnd) or p is None or p <= 0:
            continue
        blockers = [b for b in blockers_all if b.blocking == att.id]
        dealt = 0
        if att.id in r.blocked:
            remaining = p
            for i, b in enumerate(blockers):
                bch = plan.ch(b)
                t = toughness(b, bch)
                if "deathtouch" in ach.keywords:
                    lethal = 1
                elif t is None:
                    lethal = remaining
                else:
                    lethal = max(0, t - b.damage - out.creatures.get(b.id, 0) - out.wither.get(b.id, 0))
                last = i == len(blockers) - 1
                amount = remaining if last and "trample" not in ach.keywords else min(remaining, lethal)
                if amount > 0:
                    dealt += hit_creature(att, ach, b, amount)
                    remaining -= amount
            if remaining > 0 and "trample" in ach.keywords:
                dealt += hit_target(att, ach, remaining)
        else:
            dealt = hit_target(att, ach, p)
        gain(att, ach, dealt)
    for b in blockers_all:
        bch = plan.ch(b)
        p = power(b, bch)
        blocked = state.cards.get(b.blocking or "")
        if blocked is None or blocked.attacking is None or not _deals(bch, rnd) or p is None or p <= 0:
            continue
        gain(b, bch, hit_creature(b, bch, blocked, p))
    return out


def damage_preview(plan: Plan, rnd: Round) -> str:
    """A compact public summary of the damage about to be dealt (for ASSISTED confirmation)."""
    dmg = compute_combat_damage(plan, rnd)
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
        events.append({"source_card": src, "source_oid": plan.oid(src), "target": tgt, "amount": n, "combat": True,
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
    replace.do_damage(plan, out, actor=plan.active, combat=True, extra={
        "first_strike": rnd == "first",
        "commander": [{"player": pid, "commander": key, "amount": n} for (pid, key), n in commander.items()]})
    dealt = [(ev["source_card"], ev["target"], int(ev["amount"])) for ev in out.events]
    hit_players = [plan.state.cards[src] for src, tgt, n in dealt
                   if tgt in plan.state.players and n > 0 and src in plan.state.cards]
    if hit_players:
        from app.rules import triggers  # triggers → plan; imported late

        triggers.dealt_combat_damage_to_player(plan, list({c.id: c for c in hit_players}.values()))
    monarch = plan.state.table.monarch
    if monarch and (out.players.get(monarch) or out.poison.get(monarch)):
        from app.rules import triggers  # triggers → plan; imported late

        hitters = [plan.state.cards[src] for src, tgt, n in dealt if tgt == monarch and n > 0 and src in plan.state.cards]
        triggers.monarch_damaged(plan, hitters[:1])  # one trigger per combat damage event
    # -- counters & designations (wave 3E): 726.2 the initiative changes hands --
    from app.rules import designations

    designations.initiative_damaged(plan, dealt)
    return True


def end_combat(plan: Plan) -> None:
    if any(c.attacking is not None or c.blocking for c in plan.state.cards.values()):
        plan.do({"type": "clear_combat"}, actor=plan.active)
    r = plan.rules
    r.blocked = []
    r.no_attackers = False
    r.combat_round = ""
