"""Camouflage (wave 110F): "This turn, instead of declaring blockers, each defending player chooses any number of creatures they control and divides them into a number of
piles equal to the number of attacking creatures for whom that player is the defending player. Creatures those players control that can block additional creatures may
likewise be put into additional piles. Assign each pile to a different one of those attacking creatures at random. Each creature in a pile that can block the creature
that pile is assigned to does so. (Piles can be empty.)"

509.1: the declaration of blockers is replaced, so none of its requirements or costs (509.1c, 509.1d) are applied; the restrictions of 509.1b decide whether a creature "can
block" the attacker its pile was assigned to (``combat.block_problem``; menace and similar minimums, 509.1b / 702.111b: fewer creatures than the minimum and none of the pile
blocks it). The players divide in turn order but the piles are assigned only once every one has divided theirs, at random (every pile to a different attacker, a
shuffle). Cases the table must decide by hand (an attacker that can't be blocked by more than one creature,
"can't block alone", a limit on the number of blockers, a companion restriction) fall back to the ordinary declaration for that player."""
from __future__ import annotations

import secrets
from typing import Any

from app.game.rules_state import DecisionOption


def spell(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    plan.rules.camouflage_turn110f = plan.state.turn.number
    return True


def ask(plan: Any, pid: str, attackers: list[Any], blockers: list[Any]) -> bool:
    """True when the player was asked to divide creatures (the declaration step waits), False when the ordinary declaration applies."""
    from app.rules import combat, combat_rules, declaration_groups, scripts

    r = plan.rules
    if r.camouflage_turn110f != plan.state.turn.number or not blockers:
        return False
    special = {"max_one_blocker", "block_by_all"}
    if any(special & scripts.statics(plan.ch(a)) for a in attackers) or any("cant_block_alone" in scripts.statics(plan.ch(b)) for b in blockers) \
            or r.block_caps.get(pid) is not None or combat_rules.limits(plan, combat_rules.BLOCK_LIMIT_ALL).get("*") is not None \
            or declaration_groups.relevant(plan, {b.id for b in blockers}, "block"):
        return False
    st = {"pid": pid, "n": len(attackers), "piles": [], "todo": []}
    _ask_choose(plan, st, blockers, combat)
    return True


def _ask_choose(plan: Any, st: dict[str, Any], blockers: list[Any], combat: Any) -> None:
    from app.rules.plan import decide

    decide(plan, player=st["pid"], kind="choose_cards", prompt=f"Camouflage: choose any number of creatures you control; you will divide them into {st['n']} pile"
           f"{'s' if st['n'] != 1 else ''}", options=[DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in blockers],
           min_choices=0, max_choices=len(blockers), resume={"step": "camo110f", "st": st, "phase": "choose"})


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import combat

    st = d.resume["st"]
    if d.resume["phase"] == "choose":
        st["piles"] = [[] for _ in range(st["n"])]
        st["todo"] = list(chosen)
    else:
        for i in chosen:
            st["piles"][int(i)].append(st["todo"][0])
        st["todo"].pop(0)
    while st["todo"]:
        cid = st["todo"][0]
        limit = min(st["n"], combat.block_limit(plan, plan.ch(plan.state.cards[cid])))
        if st["n"] == 1 or limit < 1:
            st["piles"][0].append(cid)
            st["todo"].pop(0)
            continue
        from app.rules.plan import decide

        decide(plan, player=st["pid"], kind="choose_cards", prompt=f"Camouflage: put {plan.state.cards[cid].name} into a pile"
               + (f" (it can block additional creatures: up to {limit} piles)" if limit > 1 else ""),
               options=[DecisionOption(id=str(i), label=f"Pile {i + 1}") for i in range(st["n"])], min_choices=1, max_choices=limit,
               resume={"step": "camo110f", "st": st, "phase": "pile"})
        return
    r = plan.rules
    r.camouflage110f[st["pid"]] = st["piles"]
    r.decision = None
    if r.blockers_pending and r.blockers_pending[0] == st["pid"]:
        r.blockers_pending.pop(0)
    combat.ask_next_blocker(plan)
    if r.decision is None:
        from app.rules.engine import advance

        combat.blocks_declared(plan)
        r.priority = plan.active
        r.passed = []
        advance(plan)


def apply(plan: Any) -> None:
    """Every defending player has divided theirs: each pile goes to a different one of the attackers at random and its creatures block it if they can (509.1b)."""
    from app.game import actions as A
    from app.rules import combat

    r = plan.rules
    if not r.camouflage110f:
        return
    done, r.camouflage110f = r.camouflage110f, {}
    blocks: list[A.BlockDeclaration] = []
    for pid, piles in done.items():
        attackers = [c for c in combat.attackers_on(plan.state) if combat.blocking_defender(plan.state, c) == pid]
        order = list(range(len(attackers)))
        (plan.rng or secrets.SystemRandom()).shuffle(order)
        for pile, i in zip(piles, order, strict=False):
            att = attackers[i]
            ach = plan.ch(att)
            fits = [b for b in (plan.state.cards.get(cid) for cid in pile) if b is not None and b.controller == pid
                    and combat.block_problem(plan.state, b, plan.ch(b), att, ach, plan.info) is None]
            if len(fits) >= combat.min_blockers(ach):  # (509.1b: menace and its kin; fewer than the minimum, nobody blocks it)
                blocks += [A.BlockDeclaration(blocker_id=b.id, attacker_id=att.id) for b in fits]
    combat.apply_blocks(plan, blocks)
