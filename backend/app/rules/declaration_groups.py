"""Whole-declaration restrictions and legal, cost-free requirement completions."""
from __future__ import annotations

import re
from functools import cache
from itertools import combinations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

# The profile records only facts required by this grammar, never an unbounded subset.
# count<=3, highest power, greatest power needing a stronger companion,
# minimum group size, black/green count<=2, required black/green companions.
Profile = tuple[int, int | None, int | None, int, int, int]
EMPTY: Profile = (0, None, None, 0, 0, 0)


def parse(text: str) -> dict[str, Any] | None:
    from app.rules import statics

    m = re.fullmatch(r"(?:~|[Tt]his creature) can't (?P<mode>attack|block) unless (?P<condition>a creature with greater power also (?:attacks|blocks)|at least two other creatures (?:attack|block)|a black or green creature also attacks)\.", text)
    if m:
        condition = m['condition']
        kind = 'greater' if condition.startswith('a creature') else 'three' if condition.startswith('at least') else 'black_green'
        return statics._definition('self', None, [], rules=[f"declaration_group:{m['mode']}:{kind}"])
    if text == 'If a creature you control attacks, this creature also attacks if able.' or text == 'If a creature you control attacks, ~ also attacks if able.':
        return statics._definition('self', None, [], rules=['attack_with_others'])
    return None


def rules(plan: Plan, cid: str) -> set[str]:
    from app.rules import scripts

    return scripts.statics(plan.ch(plan.state.cards[cid]))


def relevant(plan: Plan, ids: set[str], mode: str) -> bool:
    return any(any(r.startswith(f'declaration_group:{mode}:') or r == f'cant_{mode}_alone' or (mode == 'attack' and (r == 'attack_with_others' or r.startswith(('conditional_attack67:', 'attack_at_least_one68:')))) for r in rules(plan, cid)) for cid in ids)


def add(plan: Plan, profile: Profile, cid: str, mode: str) -> Profile:
    from app.rules.combat import _power

    count, highest, needed_power, minimum, colored, need_color = profile
    ch = plan.ch(plan.state.cards[cid])
    own = rules(plan, cid)
    p = _power(ch)
    qualifies = bool({'B', 'G'} & set(ch.colors))
    if f'declaration_group:{mode}:greater' in own:
        needed_power = p if needed_power is None else max(needed_power, p)
    if f'declaration_group:{mode}:three' in own:
        minimum = max(minimum, 3)
    if f'cant_{mode}_alone' in own:
        minimum = max(minimum, 2)
    if f'declaration_group:{mode}:black_green' in own:
        need_color = max(need_color, 1 + int(qualifies))
    return min(3, count + 1), p if highest is None else max(highest, p), needed_power, minimum, min(2, colored + qualifies), need_color


def valid(profile: Profile) -> bool:
    count, highest, needed_power, minimum, colored, need_color = profile
    return count >= minimum and colored >= need_color and (needed_power is None or (highest is not None and highest > needed_power))


def legal(plan: Plan, ids: set[str], mode: str) -> bool:
    profile = EMPTY
    for cid in ids:
        profile = add(plan, profile, cid, mode)
    return valid(profile)


def attack_requirements(plan: Plan, eligible: set[str], targets: set[str], declared: dict[str, str], caps: dict[str, int]) -> str | None:
    from app.game import actions as A
    from app.rules import combat

    ids = sorted(eligible)
    order = sorted(caps)
    weights: list[dict[str, int]] = []
    from app.rules import combat_at_least_one68

    one_groups = combat_at_least_one68.groups(plan, eligible)
    actual_mask = 0
    for target in declared.values():
        actual_mask |= combat_at_least_one68.hit(one_groups, target)
    obeyed = combat_at_least_one68.value(one_groups, actual_mask)
    for cid in ids:
        card = plan.state.cards[cid]
        ch = plan.ch(card)
        own = rules(plan, cid)
        from app.rules import attack_requirements

        # A conditional requirement does not force its own condition to become true.
        companions = int('attack_with_others' in own and bool(set(declared) - {cid}))

        def score(target: str | None, ch: Characteristics = ch, companions: int = companions) -> int:
            from app.rules import combat_conditional_requirements67

            return (attack_requirements.score(plan, ch, target) + (companions if target is not None else 0)
                    + combat_conditional_requirements67.score(plan, ch, declared, target))

        obeyed += score(declared.get(cid))
        places: dict[str, int] = {}
        if combat.attack_problem(plan.state, card, ch) is None:
            for target in targets:
                if combat._closed(plan, ch, target, card, declared=cid in declared) and declared.get(cid) != target:
                    continue
                if 'attack_needs_island' in own:
                    defender = target if target in plan.state.players else combat.defender_of(plan.state, A.AttackTarget(kind='card', id=target)) or ''
                    if not combat._controls_land(plan.state, defender, 'Island', plan.info):
                        continue
                places[target] = score(target)
        weights.append(places)

    if not one_groups and not any(weight for places in weights for weight in places.values()):
        return None

    @cache
    def best(i: int, left: tuple[int, ...], profile: Profile, mask: int) -> int:
        if i == len(ids):
            return combat_at_least_one68.value(one_groups, mask) if valid(profile) else -10**9
        top = best(i + 1, left, profile, mask)
        for target, weight in weights[i].items():
            pools = [j for j, cap in enumerate(order) if cap in (target, '*')]
            if any(left[j] <= 0 for j in pools):
                continue
            top = max(top, weight + best(i + 1, tuple(n - int(j in pools) for j, n in enumerate(left)), add(plan, profile, ids[i], 'attack'), mask | combat_at_least_one68.hit(one_groups, target)))
        return top

    return 'The attack does not obey as many attack requirements as it could (508.1d)' if obeyed < best(0, tuple(caps[p] for p in order), EMPTY, 0) else None


def block_requirements(plan: Plan, blockers: set[str], attackers: set[str], used: dict[str, list[str]]) -> str | None:
    """Maximum over legal native declarations, including optional support creatures."""
    from app.game import actions as A
    from app.rules import banding, combat, combat_rules
    from app.rules.statics import rule_arg

    ids, targets = sorted(blockers), sorted(attackers)
    if not any(r == 'must_block' or r.startswith('must_block_obj:') for cid in ids for r in rules(plan, cid)) and not any(
            r in ('must_be_blocked', 'must_be_blocked_two') or r.startswith(('lure', 'must_be_blocked_by:'))
            for cid in targets for r in rules(plan, cid)):
        return None
    index = {cid: i for i, cid in enumerate(targets)}
    # Every bit denotes one native requirement that can be met by any qualifying blocker.
    collective: list[tuple[int, str]] = []
    wanted: dict[str, set[str]] = {}
    for cid in ids:
        wants = {arg for name, arg in map(rule_arg, rules(plan, cid)) if name == 'must_block_obj'}
        b = plan.state.cards[cid]
        for target in targets:
            a = plan.state.cards[target]
            if any(name == 'lure' and (not arg or combat._any_selector(plan.state, plan.info, arg, b, plan.ch(b), a)) for name, arg in map(rule_arg, rules(plan, target))):
                wants.add(plan.oid(a))
        wanted[cid] = wants
    for target in targets:
        for name, arg in map(rule_arg, rules(plan, target)):
            if name == 'must_be_blocked_by':
                collective.append((index[target], arg))
    # Counts are truncated only beyond every threshold used by restrictions/requirements.
    minima, maxima, thresholds = [], [], []
    for target in targets:
        ch = plan.ch(plan.state.cards[target])
        own = rules(plan, target)
        minimum = combat.min_blockers(ch)
        if 'block_by_all' in own:
            minimum = max(minimum, sum(c.zone.endswith(':battlefield') and c.controller == plan.actor and plan.ch(c).is_creature for c in plan.state.cards.values()))
        minima.append(minimum)
        maxima.append(1 if 'max_one_blocker' in own else len(ids))
        thresholds.append(max(minimum, 2))
    cap = combat_rules.limits(plan, combat_rules.BLOCK_LIMIT_ALL).get('*', len(ids))
    cap -= sum(c.is_blocking for c in plan.state.cards.values())
    cap = min(cap, plan.rules.block_caps.get(plan.actor, len(ids)))
    cap = max(0, cap)

    def option(cid: str, chosen: tuple[str, ...]) -> tuple[tuple[int, ...], tuple[int, ...], int, int]:
        raw = tuple(int(t in chosen) for t in targets)
        effective = banding.expand_blocks(plan, [A.BlockDeclaration(blocker_id=cid, attacker_id=t) for t in chosen])
        expanded = {d.attacker_id for d in effective}
        counts = tuple(int(t in expanded) for t in targets)
        own = rules(plan, cid)
        reward = int(bool(chosen) and 'must_block' in own) + sum(plan.oid(plan.state.cards[t]) in wanted[cid] for t in expanded)
        mask = 0
        b = plan.state.cards[cid]
        for bit, (j, selector) in enumerate(collective):
            if targets[j] in expanded and combat._any_selector(plan.state, plan.info, selector, b, plan.ch(b), plan.state.cards[targets[j]]):
                mask |= 1 << bit
        return raw, counts, reward, mask

    options: list[list[tuple[tuple[str, ...], tuple[tuple[int, ...], tuple[int, ...], int, int]]]] = []
    for cid in ids:
        b = plan.state.cards[cid]
        available = [t for t in targets if combat.block_problem(plan.state, b, plan.ch(b), plan.state.cards[t], plan.ch(plan.state.cards[t]), plan.info) is None]
        may_add = cid in used or not combat_rules.has_block_cost(plan, cid, plan.ch(b))
        choices: list[tuple[str, ...]] = [()]
        if may_add:
            for n in range(1, min(combat.block_limit(plan, plan.ch(b)), len(available)) + 1):
                choices.extend(combinations(available, n))
        options.append([(chosen, option(cid, chosen)) for chosen in choices])

    def final_reward(counts: tuple[int, ...], mask: int) -> int:
        total = mask.bit_count()
        for j, cid in enumerate(targets):
            own = rules(plan, cid)
            total += int('must_be_blocked' in own and counts[j] > 0)
            total += int('must_be_blocked_two' in own and counts[j] >= 2)
        return total

    actual_counts = [0] * len(targets)
    actual_reward = actual_mask = 0
    for cid, chosen in used.items():
        _, counts, reward, mask = option(cid, tuple(chosen))
        actual_reward += reward
        actual_mask |= mask
        actual_counts = [a+b for a,b in zip(actual_counts, counts, strict=True)]
    obeyed = actual_reward + final_reward(tuple(actual_counts), actual_mask)

    @cache
    def best(i: int, remaining: int, raw: tuple[int, ...], expanded: tuple[int, ...], mask: int, profile: Profile) -> int:
        if i == len(ids):
            if not valid(profile) or any(n and n < minima[j] for j,n in enumerate(raw)):
                return -10**9
            return final_reward(expanded, mask)
        top = -10**9
        for chosen, (delta, effective, reward, bits) in options[i]:
            if chosen and remaining <= 0:
                continue
            new_raw = tuple(min(thresholds[j], n + delta[j]) for j,n in enumerate(raw))
            if any(raw[j] + delta[j] > maxima[j] for j in range(len(targets))):
                continue
            new_expanded = tuple(min(thresholds[j], n + effective[j]) for j,n in enumerate(expanded))
            top = max(top, reward + best(i + 1, remaining - bool(chosen), new_raw, new_expanded, mask | bits,
                                        add(plan, profile, ids[i], 'block') if chosen else profile))
        return top

    empty = (0,) * len(targets)
    return 'The blocks do not obey as many blocking requirements as they could (509.1c)' if obeyed < best(0, cap, empty, empty, 0, EMPTY) else None
