"""Independent attack requirements (508.1d), retaining their continuous-effect origins.

Plain rules stay available to existing legality checks and old saves. Auxiliary markers
retain multiplicity after Characteristics.imposed is projected to a set. Goad is counted
separately by player, as explicitly required by 701.15c-d.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

PREFIX = 'attack_requirement:'


def is_requirement(rule: str) -> bool:
    return rule in ('must_attack', 'attack_player_any') or rule.startswith(('conditional_attack67:', 'attack_player:', 'attack_other_than:', 'attack_host_controller:', 'attack_most_life:', 'attack_object:'))


def instances(rules: Iterable[str], origin: str) -> set[str]:
    return {PREFIX + json.dumps([origin, index, rule], separators=(',', ':'))
            for index, rule in enumerate(rules) if is_requirement(rule)}


def counts(ch: Characteristics) -> Counter[str]:
    from app.rules import scripts

    result: Counter[str] = Counter()
    for marker in ch.imposed:
        if marker.startswith(PREFIX):
            _, _, rule = json.loads(marker[len(PREFIX):])
            result[rule] += 1
    tagged = set(result)
    # Printed/derived abilities remain separate from externally imposed rules.
    for definition in scripts.definitions(ch).values():
        if definition.get('kind') == 'static' and definition.get('static') == 'must_attack':
            result['must_attack'] += 1
    # Old saves and existing producers without origin metadata retain their rule.
    for rule in ch.imposed:
        if is_requirement(rule) and rule not in tagged:
            result[rule] += 1
    return result


def score(plan: Plan, ch: Characteristics, place: str | None) -> int:
    if place is None:
        return 0
    from app.rules.keyword_actions import goaded_by

    live = set(plan.live())
    goaders = goaded_by(ch) & live
    result = len(goaders) + sum(place in plan.state.players and place != pid for pid in goaders)
    for rule, number in counts(ch).items():
        if rule == 'must_attack':
            result += number
        elif rule == 'attack_player_any':
            result += number * int(place in live)
        elif rule.startswith('attack_player:'):
            result += number * int(rule[len('attack_player:'):] == place)
        elif rule.startswith('attack_host_controller:'):
            aura = plan.state.cards.get(rule[len('attack_host_controller:'):])
            host = plan.state.cards.get(aura.attached_to or '') if aura is not None else None
            if host is not None and host.zone.endswith(':battlefield'):
                result += number * int(place == host.controller)
        elif rule.startswith('attack_most_life:'):
            cid, _, name = rule[len('attack_most_life:'):].partition('|')
            source = plan.state.cards.get(cid)
            if source is not None:
                opponents = live - {source.controller}
                named = any(c.zone.endswith(':battlefield') and c.controller == source.controller
                            and plan.ch(c).name == name and 'Creature' in plan.ch(c).types
                            for c in plan.state.cards.values())
                if opponents and not named:
                    highest = max(plan.state.players[pid].life for pid in opponents)
                    result += number * int(place in opponents and plan.state.players[place].life == highest)
        elif rule.startswith('attack_object:'):
            target = plan.state.cards.get(place)
            result += number * int(target is not None and plan.rules.object_id(place) == rule[len('attack_object:'):])
        elif rule.startswith('attack_other_than:'):
            pid = rule[len('attack_other_than:'):]
            result += number * int(pid in live and place in plan.state.players and place != pid)
    return result
