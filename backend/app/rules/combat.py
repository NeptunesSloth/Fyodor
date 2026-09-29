"""Combat (milestone 15c): declaring attackers and blockers, and combat damage.

The attack/block markers on the table are the visible truth (a manual override that removes a
marker takes the creature out of combat). Rules state only remembers which attackers became
blocked (they stay blocked even if the blocker leaves), whether anyone attacked at all, and
whether first-strike damage has been dealt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, GameState, zone_key
from app.rules import characteristics as chars
from app.rules.casting import summoning_sick
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.plan import Plan, decide, live_players
from app.rules.sba import power, toughness

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
    if "haste" not in ch.keywords and summoning_sick(state, card):
        return f"{ch.name} has summoning sickness"
    return None


def block_problem(state: GameState, blocker: CardInstance, bch: Characteristics, attacker: CardInstance,
                  ach: Characteristics) -> str | None:
    if not blocker.zone.endswith(":battlefield") or not bch.is_creature:
        return "Only creatures on the battlefield can block"
    if blocker.tapped:
        return f"{bch.name} is tapped"
    if "flying" in ach.keywords and not ({"flying", "reach"} & bch.keywords):
        return f"{ach.name} has flying: only creatures with flying or reach can block it"
    return None


def attack_targets(state: GameState, attacker: str, info: CardInfo) -> list[str]:
    """Opponents, and planeswalkers they control (battles arrive later)."""
    out = [p for p in live_players(state) if p != attacker]
    for pid in list(out):
        for cid in state.zones.get(zone_key(pid, "battlefield"), []):
            card = state.cards[cid]
            if card.controller == pid and "Planeswalker" in chars.of(card, info).types:
                out.append(cid)
    return out


def _label(state: GameState, target: str) -> str:
    return state.players[target].name if target in state.players else (state.cards[target].name or "Planeswalker")


def defender_of(state: GameState, target: A.AttackTarget | Any) -> str | None:
    if target is None:
        return None
    if target.kind == "player":
        return str(target.id)
    card = state.cards.get(target.id)
    return card.controller if card else None


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
        if decl.card_id in seen:
            raise ActionError(f"{card.name} can only attack once")
        seen.add(decl.card_id)
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
        from app.rules import triggers  # triggers → plan; imported late

        triggers.attacked(plan, [plan.state.cards[x.card_id] for x in a.attackers])
    r.priority = plan.active
    r.passed = []
    advance(plan)


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
        problem = block_problem(plan.state, blocker, plan.ch(blocker), attacker, plan.ch(attacker))
        if problem:
            raise ActionError(problem)
        per_attacker[decl.attacker_id] = per_attacker.get(decl.attacker_id, 0) + 1
    for aid, n in per_attacker.items():
        ach = plan.ch(plan.state.cards[aid])
        if "menace" in ach.keywords and n < 2:
            raise ActionError(f"{ach.name} has menace: it can't be blocked except by two or more creatures")
    r.decision = None
    if r.blockers_pending and r.blockers_pending[0] == plan.actor:
        r.blockers_pending.pop(0)
    for decl in a.blocks:
        plan.do({"type": "block", "card_id": decl.blocker_id, "attacker_id": decl.attacker_id})
    r.blocked = list(dict.fromkeys([*r.blocked, *per_attacker]))
    if not a.blocks:
        plan.note(f"{plan.name(plan.actor)} doesn't block")
    ask_next_blocker(plan)
    if r.decision is None:
        r.priority = plan.active
        r.passed = []
        advance(plan)


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
    lifelink: dict[str, int] = field(default_factory=dict)
    commander: dict[tuple[str, str], int] = field(default_factory=dict)
    deathtouched: list[str] = field(default_factory=list)
    dealt: list[tuple[str, str, int]] = field(default_factory=list)  # (source card, target card/player, amount)

    @property
    def empty(self) -> bool:
        return not (self.creatures or self.players or self.walkers)


def compute_combat_damage(plan: Plan, rnd: Round) -> CombatDamage:
    state = plan.state
    r = plan.rules
    out = CombatDamage()

    def hit_creature(source_card: CardInstance, source: Characteristics, target: CardInstance, n: int) -> None:
        out.creatures[target.id] = out.creatures.get(target.id, 0) + n
        out.dealt.append((source_card.id, target.id, n))
        if "deathtouch" in source.keywords:
            out.deathtouched.append(target.id)

    def gain(source_card: CardInstance, source: Characteristics, n: int) -> None:
        if n > 0 and "lifelink" in source.keywords:
            out.lifelink[source_card.controller] = out.lifelink.get(source_card.controller, 0) + n

    def hit_target(att: CardInstance, n: int) -> None:
        tgt = att.attacking
        if tgt is None or n <= 0:
            return
        if tgt.kind == "player":
            if tgt.id in state.players:
                out.players[tgt.id] = out.players.get(tgt.id, 0) + n
                out.dealt.append((att.id, tgt.id, n))
                if att.commander_key:
                    key = (tgt.id, att.commander_key)
                    out.commander[key] = out.commander.get(key, 0) + n
        elif tgt.id in state.cards and state.cards[tgt.id].zone.endswith(":battlefield"):
            out.walkers[tgt.id] = out.walkers.get(tgt.id, 0) + n
            out.dealt.append((att.id, tgt.id, n))

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
                    lethal = max(0, t - b.damage - out.creatures.get(b.id, 0))
                last = i == len(blockers) - 1
                amount = remaining if last and "trample" not in ach.keywords else min(remaining, lethal)
                if amount > 0:
                    hit_creature(att, ach, b, amount)
                    dealt += amount
                    remaining -= amount
            if remaining > 0 and "trample" in ach.keywords:
                hit_target(att, remaining)
                dealt += remaining
        else:
            hit_target(att, p)
            dealt = p
        gain(att, ach, dealt)
    for b in blockers_all:
        bch = plan.ch(b)
        p = power(b, bch)
        blocked = state.cards.get(b.blocking or "")
        if blocked is None or blocked.attacking is None or not _deals(bch, rnd) or p is None or p <= 0:
            continue
        hit_creature(b, bch, blocked, p)
        gain(b, bch, p)
    return out


def damage_preview(plan: Plan, rnd: Round) -> str:
    """A compact public summary of the damage about to be dealt (for ASSISTED confirmation)."""
    dmg = compute_combat_damage(plan, rnd)
    parts = []
    for source, target, n in dmg.dealt:
        who = plan.state.players[target].name if target in plan.state.players else plan.state.cards[target].name
        parts.append(f"{plan.state.cards[source].name} → {who} {n}")
    return "; ".join(parts) or "none"


def deal_combat_damage(plan: Plan, rnd: Round) -> None:
    dmg = compute_combat_damage(plan, rnd)
    if dmg.empty:
        return
    plan.do({
        "type": "rules_damage", "creatures": dmg.creatures, "players": dmg.players, "planeswalkers": dmg.walkers,
        "lifelink": dmg.lifelink, "first_strike": rnd == "first",
        "commander": [{"player": pid, "commander": key, "amount": n} for (pid, key), n in dmg.commander.items()],
        "dealt": [{"source": plan.oid(src), "target": tgt, "amount": n,
                   "target_object": plan.oid(tgt) if tgt in plan.state.cards else None} for src, tgt, n in dmg.dealt],
    }, actor=plan.active)
    plan.rules.deathtouched = list(dict.fromkeys([*plan.rules.deathtouched, *dmg.deathtouched]))
    monarch = plan.state.table.monarch
    if monarch and dmg.players.get(monarch):
        from app.rules import triggers  # triggers → plan; imported late

        hitters = [plan.state.cards[src] for src, tgt, n in dmg.dealt if tgt == monarch and n > 0 and src in plan.state.cards]
        triggers.monarch_damaged(plan, hitters[:1])  # one trigger per combat damage event


def end_combat(plan: Plan) -> None:
    if any(c.attacking is not None or c.blocking for c in plan.state.cards.values()):
        plan.do({"type": "clear_combat"}, actor=plan.active)
    r = plan.rules
    r.blocked = []
    r.no_attackers = False
    r.combat_round = ""
