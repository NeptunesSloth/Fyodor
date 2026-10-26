"""Target selectors and legality (CR 115, 601.2c, 608.2b).

A target is chosen when a spell is cast or an ability is put on the stack, and checked again on
resolution: a target that left its zone (it is a new object) or no longer matches is illegal,
and if every target is illegal the spell or ability does nothing (608.2b). Hexproof and shroud
(702.11, 702.18) and protection (702.16) are checked here. The server computes the legal choices; the chooser gets them
in their private decision, nobody else does.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from app.game.actions import MAX_TARGETS
from app.game.errors import ActionError
from app.game.rules_state import TargetRef
from app.game.state import CardInstance
from app.rules import player_relative, protection, selectors
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan

Check = Callable[[Plan, str, CardInstance, Characteristics], bool]


def _types(*types: str) -> Check:
    return lambda plan, who, card, ch: bool(ch.types & set(types))


SELECTORS: dict[str, tuple[bool, Check | None]] = {
    # selector: (players allowed, permanent check or None for "no permanents")
    "any": (True, _types("Creature", "Planeswalker", "Battle")),
    "creature_planeswalker_or_player": (True, _types("Creature", "Planeswalker")),
    "creature": (False, _types("Creature")),
    "creature_or_player": (True, _types("Creature")),  # (wave 110M)
    "creature_you_control": (False, lambda plan, who, card, ch: ch.is_creature and card.controller == who),
    "creature_opponent_controls": (False, lambda plan, who, card, ch: ch.is_creature and card.controller != who),
    "creature_or_planeswalker": (False, _types("Creature", "Planeswalker")),
    "artifact": (False, _types("Artifact")),
    "enchantment": (False, _types("Enchantment")),
    "artifact_or_enchantment": (False, _types("Artifact", "Enchantment")),
    "land": (False, _types("Land")),
    "land_you_control": (False, lambda plan, who, card, ch: ch.is_land and card.controller == who),
    "artifact_you_control": (False, lambda plan, who, card, ch: "Artifact" in ch.types and card.controller == who),
    "artifact_or_creature": (False, _types("Artifact", "Creature")),
    "planeswalker": (False, _types("Planeswalker")),
    "permanent": (False, lambda plan, who, card, ch: True),
    "nonland_permanent": (False, lambda plan, who, card, ch: not ch.is_land),
    "nonland_permanent_opp": (False, lambda plan, who, card, ch: not ch.is_land and card.controller != who),
    "artifact_or_enchantment_opp": (False, lambda plan, who, card, ch: bool(ch.types & {"Artifact", "Enchantment"})
                                    and card.controller != who),
    "creature_or_planeswalker_opp": (False, lambda plan, who, card, ch: bool(ch.types & {"Creature", "Planeswalker"})
                                     and card.controller != who),
    "attacking_or_blocking_creature": (False, lambda plan, who, card, ch: ch.is_creature
                                       and (card.is_attacking or card.is_blocking)),
    "attacking_creature": (False, lambda plan, who, card, ch: ch.is_creature and card.is_attacking),
    "blocking_creature": (False, lambda plan, who, card, ch: ch.is_creature and card.is_blocking),
    "player": (True, None),
    "opponent": (True, None),
    # -- target forms (agent T) --  "target player or planeswalker" / "target opponent or planeswalker"
    # (a player, or any planeswalker: not only an opponent's)
    "player_or_planeswalker": (True, _types("Planeswalker")),
    "player_planeswalker_or_sliver": (True, lambda plan, who, card, ch: "Planeswalker" in ch.types or ch.is_creature and "Sliver" in ch.subtypes),
    "opponent_or_planeswalker": (True, _types("Planeswalker")),
    # -- damage sized by a count (wave 42D) -- "target opponent or battle" (Ayara), "target player or battle" (Onakke Javelineer): a player, or any battle
    "player_or_battle": (True, _types("Battle")),
    "opponent_or_battle": (True, _types("Battle")),
    "opponent_or_creature_or_planeswalker_opp": (True, lambda plan, who, card, ch:
        bool(ch.types & {"Creature", "Planeswalker"}) and card.controller != who),
    "permanent_or_opponent": (True, lambda plan, who, card, ch: True),
    "artifact_creature_planeswalker_or_opponent": (True, _types("Artifact", "Creature", "Planeswalker")),
    "permanent_or_player": (True, lambda plan, who, card, ch: True),  # -- counter kinds (wave 24C) -- "target permanent or player"
    "creature_token_player_or_planeswalker": (True, lambda plan, who, card, ch: "Planeswalker" in ch.types or ch.is_creature and card.is_token),  # (wave 100I: Coalborn Entity)
}
OPPONENTS_ONLY = ("permanent_or_opponent", "artifact_creature_planeswalker_or_opponent", "opponent_or_creature_or_planeswalker_opp", "opponent", "opponent_or_planeswalker", "opponent_or_battle")


SPELL_SELECTORS: dict[str, Callable[[Characteristics], bool]] = {
    "spell": lambda ch: True,
    "creature_spell": lambda ch: ch.is_creature,
    "noncreature_spell": lambda ch: not ch.is_creature,
    "instant_or_sorcery_spell": lambda ch: ch.is_instant_or_sorcery,
}


def can_target(plan: Plan, chooser: str, card: CardInstance, ch: Characteristics,
               source: Characteristics | None = None) -> bool:
    """Hexproof: not by opponents; shroud: by nobody; protection: not by a source with that quality."""
    from app.rules import prohibitions

    if card.zone.endswith(":battlefield") and prohibitions.no_targets110f(plan):  # -- wave 110F -- Peace Talks: 115.2
        return False
    if prohibitions.untargetable(plan, chooser, card):  # -- cant restrictions (wave 50G) -- 115.2: "Lands on the battlefield … can't be the targets of spells or abilities your opponents control"
        return False
    on_battlefield = card.zone.endswith(":battlefield")
    if on_battlefield and "shroud" in ch.keywords:
        from app.rules import wave110n_cards  # -- (wave 110N) -- Autumn Willow: 702.18a, 609.4

        if not wave110n_cards.ignores_shroud(plan, chooser, card):
            return False
    from app.rules import hexproof_targeting

    target_source = replace(source, targeting_controller=chooser) if source is not None else Characteristics(name='', targeting_controller=chooser)
    protected_by_hexproof = on_battlefield and card.controller != chooser and ("hexproof" in ch.keywords or protection.hexproof_from(ch, target_source))
    if protected_by_hexproof and not hexproof_targeting.ignores(plan, chooser, card=card, ch=ch):
        return False
    for rule in ch.imposed:  # -- cant (wave 16F) -- "can't be the target of black spells or abilities from black sources"
        if rule == "untargetable_artifact_abilities106" and source is not None and source.is_ability and "Artifact" in source.types:
            return False
        if rule.startswith("only_aura106:") and source is not None and source.is_spell and "Aura" in source.subtypes:
            return False
        if rule.startswith("untargetable_by_opponents_of:") and chooser != rule.split(":", 1)[1]:
            return False  # (-- review 20A -- the Aura's controller's opponents; no teams: every other player, 102.2)
        if rule.startswith("untargetable_spells") and source is not None and source.is_spell:  # -- cant (wave 49C) -- 115.2: no spell (of those colors) may target it; an ability still may
            colors = rule.partition(":")[2]
            if not colors or set(colors) & source.colors:
                return False
        if rule.startswith("untargetable_opp_spells") and source is not None and source.is_spell and card.controller != chooser:  # -- instead (wave 100K) --
            colors = rule.partition(":")[2]
            if not colors or set(colors) & source.colors:
                return False
        if rule == "untargetable_opp_abilities" and source is not None and source.is_ability and card.controller != chooser:  # -- instead (wave 100K) --
            return False
        if rule == "untargetable_aura_spells" and source is not None and source.is_spell and "Aura" in source.subtypes:  # -- cant restrictions (wave 50G) -- 115.2: an Aura spell
            return False
        if rule.startswith("untargetable:") and source is not None:
            _, opp, non, colors = rule.split(":")
            if (opp == "0" or card.controller != chooser) and bool(set(colors) & source.colors) != (non == "1"):
                return False
    return not on_battlefield or not protection.protected_from(ch, target_source)


def _more(plan: Plan, cond: str, pid: str) -> int:
    """-- activated other (wave 21E) -- what "has more life / controls more creatures / has more cards in hand" compares."""
    if cond == "life":
        return plan.state.players[pid].life
    if cond == "hand2":
        return len(plan.state.zones.get(f"{pid}:hand", []))
    return sum(1 for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c)
               and c.controller == pid and plan.ch(c).is_creature)


def legal_targets(plan: Plan, selector: str, chooser: str, source: Characteristics | None = None,
                  source_card: str | None = None, attacker: str | None = None, *,
                  source_object: str | None = None) -> list[str]:
    """Player ids and card ids that ``chooser`` may target with ``selector`` right now
    (``source``: the spell or the ability's source, for protection; ``source_card``: that
    object, for "another target …"; ``attacker``: the creature an "attacks" trigger is about,
    whose defending player "defending player" means, 508.5)."""
    if selector.startswith('source_loyalty_lt:'):
        from app.rules import values

        base = selector.removeprefix('source_loyalty_lt:')
        ctx = {'controller': chooser, 'source_card': source_card, 'source_object': source_object}
        loyalty = values.evaluate(plan, ctx, {'counters': 'loyalty', 'on': 'self'})
        return [cid for cid in legal_targets(plan, base, chooser, source, source_card, attacker, source_object=source_object)
                if cid in plan.state.cards and plan.ch(plan.state.cards[cid]).mana_value < loyalty]
    borrowed_scope = None
    if selector.startswith('borrowed_exiled|'):
        _, borrowed_scope, selector = selector.split('|', 2)
    if selector == 'spell_name_exiled_with':
        from app.rules import card_names, exiled_with

        oid = source_object or (plan.oid(source_card) if source_card is not None and source_card in plan.state.cards else None)
        if oid is None:
            return []
        linked = exiled_with.cards(plan, {'source_object': oid, 'source_card': source_card, 'controller': chooser,
                                         'borrowed_link_scope': borrowed_scope})
        legal = legal_targets(plan, 'spell', chooser, source, source_card, attacker, source_object=source_object)
        return [cid for cid in legal if any(card_names.share(plan.ch(plan.state.cards[cid]), plan.ch(plan.state.cards[other])) for other in linked)]
    if selector == "exiled_with" or selector.startswith("exiled_with:"):
        from app.rules import exiled_with, prohibitions

        oid = source_object or (plan.oid(source_card) if source_card is not None and source_card in plan.state.cards else None)
        if oid is None:
            return []
        return [cid for cid in exiled_with.cards(plan, {"source_object": oid, "source_card": source_card, "controller": chooser, "borrowed_link_scope": borrowed_scope}, selector)
                if plan.in_game(plan.state.cards[cid]) and not prohibitions.untargetable(plan, chooser, plan.state.cards[cid])]
    if selector == "opponent_active110n":  # -- (wave 110N) -- "target opponent whose turn it is" (The Beamtown Bullies): 500.1, the active player, if they are an opponent
        return [p for p in legal_targets(plan, "opponent", chooser, source, source_card, attacker) if p == plan.state.turn.active_player]
    if selector.startswith("opponent_as:"):  # -- activated other (wave 21E) -- "target opponent who has more life than you do as you activate this ability" (601.2c)
        cond = selector.split(":", 1)[1]
        if cond == "gy2_110j":  # -- cards (wave 110J) -- Keeper of the Dead: "at least two fewer creature cards in their graveyard than you do"
            def _gy(p: str) -> int:
                return sum(1 for c in plan.state.zones.get(f"{p}:graveyard", []) if plan.ch(plan.state.cards[c]).is_creature)

            return [p for p in legal_targets(plan, "opponent", chooser, source, source_card, attacker) if _gy(p) <= _gy(chooser) - 2]
        margin = 2 if cond == "hand2" else 1
        return [p for p in legal_targets(plan, "opponent", chooser, source, source_card, attacker)
                if _more(plan, cond, p) >= _more(plan, cond, chooser) + margin]
    if selector == "any_not_host100e":  # -- xdamage (wave 100E) -- "enchanted creature deals … to any other target" (Pain for All): any target but
        host = plan.state.cards[source_card].attached_to if source_card in plan.state.cards else None  # the creature the source is attached to (115.4)
        return [t for t in legal_targets(plan, "any", chooser, source, source_card, attacker, source_object=source_object) if t != host]
    if selector == "any_hurt110a":  # -- spells (wave 110A) -- Needle Drop: any target that was dealt damage this turn (115.4; 120.3: a player, a permanent)
        from app.rules import damage_history, history

        hurt = {f.player for f in history.log_for(plan, False).facts if f.kind == "damage" and f.amount > 0 and f.player}
        return [t for t in legal_targets(plan, "any", chooser, source, source_card, attacker, source_object=source_object)
                if t in hurt or (t in plan.state.cards and damage_history.matches(plan, plan.state.cards[t], damage_history.WAS_DEALT, chooser))]
    if selector == "cast_creature110j":  # -- cards (wave 110J) -- Cycle of Life: "target creature you cast this turn" (the permanent its spell became, 608.3)
        from app.rules import history

        became = {n.became for n in history.log_for(plan).casts if n.player == chooser and n.became}
        return [c for c in legal_targets(plan, "creature", chooser, source, source_card, attacker, source_object=source_object) if plan.oid(c) in became]
    if selector == "opponent_or_other_battle110f":  # -- cards (wave 110F) -- "another target battle or opponent" (Invasion of Regatha): not the battle itself
        return [t for t in legal_targets(plan, "opponent_or_battle", chooser, source, source_card, attacker, source_object=source_object) if t != source_card]
    if selector == "opponent_or_other_permanent110l":  # -- (wave 110L) -- "another target permanent or opponent" (Etched Slith): not the source itself
        return [t for t in legal_targets(plan, "permanent_or_opponent", chooser, source, source_card, attacker, source_object=source_object) if t != source_card]
    if selector == "any_other":  # -- damage sized by a count (wave 34D) -- 115.4: "deals that much damage to any other target" (Black Panther): any target
        excluded = source_card if source_object is None or source_card in plan.state.cards and plan.oid(source_card) == source_object else None
        return [t for t in legal_targets(plan, "any", chooser, source, source_card, attacker, source_object=source_object) if t != excluded]
    if selector.startswith(selectors.PREFIX):  # a structured selector (app/rules/selectors.py)
        return _selector_targets(plan, selectors.from_key(selector), chooser, source, source_card, attacker, source_object)
    if selector.startswith("graveyard:"):  # "target Spirit card with mana value N or less from your graveyard"
        from app.rules import characteristics as chars

        _, sub, mv = selector.split(":")
        found: list[str] = []
        for cid in plan.state.zones.get(f"{chooser}:graveyard", []):
            g = chars.of(plan.state.cards[cid], plan.info)
            if (sub == "*" or sub in g.subtypes or sub in g.types) and g.mana_value <= int(mv):
                from app.rules import prohibitions

                if not prohibitions.untargetable(plan, chooser, plan.state.cards[cid]):  # (wave 50G)
                    found.append(cid)
        return found
    if selector in SPELL_SELECTORS:  # spells on the stack (115.1)
        check_spell = SPELL_SELECTORS[selector]
        return [cid for cid in plan.state.zones.get("stack", []) if cid in plan.state.cards
                and plan.state.cards[cid].ability is None and check_spell(plan.ch(plan.state.cards[cid]))]
    check: Check | None
    if selector.startswith("any_not:"):  # -- activated sweep (wave 17B) -- "any target that isn't a commander / a Dragon": any target
        # (115.1) but a permanent that is one (players never are)
        kind = selector[len("any_not:"):]
        players_ok = True
        check = lambda plan, who, card, ch: bool(ch.types & {"Creature", "Planeswalker", "Battle"}) and not (  # noqa: E731
            card.commander_key if kind == "commander" else kind in ch.subtypes)
    else:
        players_ok, check = SELECTORS[selector]
    out: list[str] = []
    if players_ok:
        from app.rules import player_shields  # -- player shields (wave 5E) -- 702.11c, 702.16b, 702.18a

        for pid in plan.live():
            if selector in OPPONENTS_ONLY and pid == chooser:
                continue
            if not player_shields.can_target(plan, chooser, pid, source):
                continue
            out.append(pid)
    if check is not None:
        for card in plan.state.cards.values():
            if not card.zone.endswith(":battlefield") or not plan.in_game(card):
                continue
            ch = plan.ch(card)
            if check(plan, chooser, card, ch) and can_target(plan, chooser, card, ch, source):
                out.append(card.id)
    return out


def _selector_targets(plan: Plan, sel: selectors.Selector, chooser: str, source: Characteristics | None,
                      source_card: str | None, attacker: str | None = None, source_object: str | None = None) -> list[str]:
    if sel.player is not None:  # 115.1: players
        from app.rules import player_shields  # -- player shields (wave 5E) -- 702.11c, 702.16b, 702.18a

        oid = source_object
        if oid is None and source_card is not None and source_card in plan.state.cards:
            oid = plan.oid(plan.state.cards[source_card])
        return [p for p in plan.live() if selectors.matches_player(plan, sel, p, chooser, source_object=oid)
                and player_shields.can_target(plan, chooser, p, source)]
    from app.rules import crew_saddle_readers81, prohibitions

    if source_object is not None:
        sel = crew_saddle_readers81.bound_target(sel, source_object)
    other_dropped = False
    if sel.other and source_card is not None and source_object is not None and (source_card not in plan.state.cards or plan.oid(source_card) != source_object):
        sel = selectors.replace(sel, other=False)
        other_dropped = True
    out = []
    for cid in selectors.candidates(plan, sel, chooser, source_card, attacker):
        if cid == source_card and other_dropped:  # (wave 110C) "another" still excludes the source card after it changed zones (Relentless Dead, LKI identity)
            continue
        card = plan.state.cards[cid]
        on_field = card.zone.endswith(":battlefield") or card.zone == "stack"
        if on_field and not can_target(plan, chooser, card, plan.ch(card), source):  # hexproof / shroud / protection
            continue
        if not on_field and prohibitions.untargetable(plan, chooser, card):  # -- cant restrictions (wave 50G) -- "Cards in graveyards can't be the targets of spells or abilities"
            continue
        out.append(cid)
    return out


def ref(plan: Plan, target: str) -> TargetRef:
    return TargetRef(id=target, object_id=plan.oid(target) if target in plan.state.cards else None)


def still_legal(plan: Plan, selector: str, chooser: str, target: TargetRef, source: Characteristics | None = None,
                source_card: str | None = None, attacker: str | None = None, *,
                source_object: str | None = None) -> bool:
    """608.2b: is a chosen target still legal? A card that changed zones is a new object: illegal."""
    if selector.startswith("opponent_as:"):  # (wave 21E: "as you activate this ability" is only judged as it is chosen)
        selector = "opponent"
    was, plan.peace_exempt110f = plan.peace_exempt110f, True  # -- wave 110F -- Peace Talks bars choosing, not a target chosen earlier (608.2b)
    try:
        return _still_legal(plan, selector, chooser, target, source, source_card, attacker, source_object)
    finally:
        plan.peace_exempt110f = was


def _still_legal(plan: Plan, selector: str, chooser: str, target: TargetRef, source: Characteristics | None, source_card: str | None,
                 attacker: str | None, source_object: str | None) -> bool:
    if target.object_id is None:
        return target.id in plan.live() and target.id in legal_targets(plan, selector, chooser, source, source_card, attacker, source_object=source_object)
    card = plan.state.cards.get(target.id)
    if card is None or plan.oid(card) != target.object_id:
        return False
    return target.id in legal_targets(plan, selector, chooser, source, source_card, attacker, source_object=source_object)



class BadPick(ActionError):
    """-- X from the triggering object (wave 34C) -- a choice of targets that breaks a rule of the group (the wrong number, one twice, not legal,
    over a total): an ActionError for whoever chose it. For a trigger that is a bad choice to make again, not "no legal target" (603.3d: that
    removes the ability)."""


@dataclass
class GroupChoice:
    """Where choosing the targets of a spell or ability with target groups stands (601.2c-d):
    ``ask`` = ("group", g, options, lo, hi) or ("divide", g, total) while a choice is missing;
    else the chosen ``groups`` and each group's ``division`` (empty if it isn't divided)."""

    groups: list[list[str]] = field(default_factory=list)
    division: list[list[int]] = field(default_factory=list)
    ask: tuple[Any, ...] | None = None
    counts: list[int] = field(default_factory=list)  # targets per group so far (groups with nothing to target: 0)
    capped: int = 0  # -- target limits (wave 29C) -- with ``ask``: how many targets the rules allow when that is more than MAX_TARGETS


def divide_total(spec: dict[str, Any], x: int | None) -> int | None:
    """What a divided group divides: a number, or X (the chosen value)."""
    divide = spec.get("divide")
    if not divide:
        return None
    total = divide["total"]
    if isinstance(total, dict) and "x_threshold_multiplier" in total:
        rule = total["x_threshold_multiplier"]
        announced = int(x or 0)
        return announced * (int(rule["times"]) if announced >= int(rule["at_least"]) else 1)
    if isinstance(total, dict) and "plus" in total:  # -- X arithmetic (wave 34C) -- "X plus 1 damage divided as you choose" (Meteor Shower): the X announced, plus 1 (601.2d)
        return int(x or 0) + int(total["plus"][1])
    return int(total) if isinstance(total, int) else int(x or 0)


def where_x(plan: Plan, spec: dict[str, Any], chooser: str, source_card: str | None, source_object: str | None,
            event: dict[str, Any] | None = None, groups: list[list[str]] | None = None) -> int:
    """-- X target counts (wave 27C) -- "up to X target …, where X is <a count>" (107.3c: the text defines X; 601.2c: the number of
    targets is what that count is as the targets are chosen, and doesn't change after)."""
    from app.rules import values

    card = plan.state.cards.get(source_card) if source_card else None
    ctx: dict[str, Any] = {"controller": chooser, "source_card": source_card, "source_object": source_object or (plan.oid(card) if card else None),
                           "targets": [], "event": event}  # (wave 28D: a trigger's event is known as it is put on the stack, 603.3d)
    if groups:  # -- (wave 110N) -- Reap: "up to X target cards …, where X is the number of black permanents target opponent controls": the earlier groups, as chosen
        ctx["groups"] = [[ref(plan, t).model_dump() for t in g] for g in groups]
        ctx["targets"] = ctx["groups"][0]
    return values.evaluate(plan, ctx, spec["x_value"])


def divide_x(plan: Plan, spec: dict[str, Any], chooser: str, source_card: str | None, source_object: str | None,
             event: dict[str, Any] | None, x: int | None) -> int | None:
    """-- damage sized by a count (wave 34D) -- "deals X damage divided as you choose among …, where X is the number of lands you control" (Ureni, Jaws of
    Stone): the total is the count as the spell is cast or the ability put on the stack (601.2d: the division is announced then; 608.2d: "the amount and
    division were determined as the spell or ability was put onto the stack"), the cast X otherwise."""
    value = (spec.get("divide") or {}).get("value")
    return x if value is None else where_x(plan, {"x_value": value}, chooser, source_card, source_object, event)


def free_limits(spec: dict[str, Any], x: int | None) -> tuple[int, int]:
    """(min, max) targets of a group as the rules give them, before the engine's own limit; a divided group needs at most as many
    targets as there is to divide, and at least one (601.2d: each gets at least one)."""
    lo, hi = int(spec.get("min", 1)), int(spec.get("max", 1))
    if spec.get("x_count"):  # -- X sized by a count (wave 4K) -- "X target …" / "up to X target …" (601.2c: the number is
        hi = max(0, int(x or 0)) * int(spec.get("x_count_multiplier", 1))  # determined with X, 601.2b, and doesn't change after; wave 29C: X alone limits it)
        lo = hi if spec["x_count"] == "exact" else 0
        if hi == 0:
            return 0, 0  # (X is 0: no targets, nothing to divide among them)
    total = divide_total(spec, x)
    if total is not None:
        lo, hi = lo if ((spec.get("divide") or {}).get("value") is not None or
                        (spec.get("divide") or {}).get("allow_zero_targets")) else max(lo, 1), min(hi, total)  # (wave 41B: a counted total says how few, language._divided)
        if total == 0 and ((spec.get("divide") or {}).get("value") is not None or
                           (spec.get("divide") or {}).get("allow_zero_targets")):
            return 0, 0  # -- damage sized by a count (wave 34D) -- a total counted as it's put on the stack may be 0: nothing to divide, no targets (601.2d)
    return lo, hi


def group_limits(spec: dict[str, Any], x: int | None) -> tuple[int, int]:
    """(min, max) targets of a group the engine takes: ``free_limits`` cut at ``MAX_TARGETS`` (wave 29C: the most one choice carries; the
    prompt says so when that is fewer than the rules allow). An exact "X target …" over it is refused, not shortened: fewer targets than
    X would be another spell (601.2c, 107.3a)."""
    lo, hi = free_limits(spec, x)
    if hi > MAX_TARGETS:
        if lo > MAX_TARGETS:
            from app.game.errors import ActionError

            raise ActionError(f"X is {lo}, but at most {MAX_TARGETS} targets can be chosen at once: choose a smaller X")
        hi = MAX_TARGETS
    return lo, hi


def choose_groups(plan: Plan, specs: list[dict[str, Any]], chooser: str, source: Characteristics | None,
                  source_card: str | None, targets: list[str], counts: list[int], division: list[int],
                  x: int | None, what: str, exclude: tuple[str, ...] = (), attacker: str | None = None,
                  source_object: str | None = None, event: dict[str, Any] | None = None,
                  required_any: frozenset[str] = frozenset()) -> GroupChoice:
    """Check the choices made so far for each target group, in printed order (601.2c): the
    number of targets (``counts``: how many of ``targets`` are each group's), no object twice
    for one word "target" (115.3; the same object may be chosen for another group unless it says
    "another target"), each a legal target now; then each divided group's division (601.2d:
    at least one each, adding up to the total; one target gets it all). Raises ActionError for a
    wrong choice or when a group can't get enough legal targets; ``ask`` names the next missing
    choice."""
    from app.game.errors import ActionError

    random_only = len(specs) == 1 and bool(specs[0].get("random"))  # -- random choices (wave 47B) -- "target … chosen at random": the table picks (601.2c; each
    if random_only:  # legal target equally likely: Scab-Clan Giant ruling 2013-04-15); nobody is asked, and a choice sent along is not read
        targets, counts = [], []
    if len(counts) > len(specs) or sum(counts) != len(targets):
        raise ActionError(f"Those aren't the right number of targets for {what}")
    out = GroupChoice(counts=list(counts))
    pos = 0
    for g, spec in enumerate(specs):
        banned = {t for d in spec.get("distinct_from") or [] if d < len(out.groups) for t in out.groups[d]}
        options = [t for t in legal_targets(plan, player_relative.bind_what(plan, spec, out.groups), chooser, source, source_card, attacker, source_object=source_object)
                   if t not in exclude and t not in banned]  # (-- player-relative selectors (wave 53A) -- "target creature that player controls": that player from the earlier group)
        if (owner := spec.get("graveyard_of")) is not None and owner < len(out.groups):  # -- shuffle target cards (wave 46B) -- "target cards from their graveyard":
            options = [t for t in options if plan.state.cards[t].owner in out.groups[owner]]  # the graveyard of the player chosen for that group
        from app.rules import permanent_exchanges

        options = permanent_exchanges.viable_first(plan, specs, g, options,
            lambda w: legal_targets(plan, w, chooser, source, source_card, attacker, source_object=source_object))
        shaped = {**spec, "x_count": "upto"} if "x_value" in spec else spec
        counted = where_x(plan, spec, chooser, source_card, source_object, event, out.groups) if "x_value" in spec else divide_x(
            plan, spec, chooser, source_card, source_object, event, x)
        lo, hi = group_limits(shaped, counted)
        allowed = free_limits(shaped, counted)[1]
        if random_only and required_any.intersection(options):
            options = [t for t in options if t in required_any]
        if random_only and options and (lo, hi) == (1, 1):
            import secrets

            targets = [(plan.rng or secrets.SystemRandom()).choice(sorted(options))]
            out.counts.append(1)
        if g >= len(out.counts) and hi == 0:  # -- kicked / instead (wave 4G) -- a group the spell doesn't require (601.2c)
            out.counts.append(0)
        room = relation_room(plan, spec, options)  # (wave 51A) how many of the options can be chosen together
        if g >= len(out.counts):
            if room < lo or hi < lo:
                raise ActionError(f"{what} has no legal target" if not options else f"{what} doesn't have enough legal targets")
            if lo == 0 and not options:
                out.counts.append(0)  # "up to one target …" with nothing to target: zero targets (115.6)
            else:
                out.ask = ("group", g, options, lo, min(hi, room))
                out.capped = allowed if allowed > hi and len(options) > hi else 0  # (said in the prompt: ask_targets)
                return out
        count = out.counts[g]
        chosen = targets[pos:pos + count]
        pos += count
        if not lo <= len(chosen) <= hi:
            raise BadPick(f"Choose {lo if lo == hi else f'{lo} to {hi}'} target{'s' if hi != 1 else ''} for {what}")
        if len(set(chosen)) != len(chosen):
            raise BadPick("The same target can't be chosen twice for one “target”")  # 115.3
        if any(t in banned for t in chosen):
            raise BadPick("“Another target” can't be one you already chose")
        if any(t not in options for t in chosen):
            raise BadPick("That isn't a legal target")
        if spec.get("same_graveyard") and len({plan.state.cards[t].owner for t in chosen if t in plan.state.cards}) > 1:
            raise BadPick("Those targets must all be from a single graveyard")  # (400.1: one player's graveyard)
        limit = int(x or 0) if spec.get("total") and spec["total"][1] == "X" else spec.get("total", [0, 0])[1]  # (wave 34C: "total mana value X or less": the X announced)
        if spec.get("total") and _total(plan, chosen, spec["total"][0]) > limit:  # -- refused zones/sized (wave 3R4)
            stat = spec["total"][0].replace("_", " ")  # -- "with total mana value 3 or less": checked as they're chosen (601.2c)
            raise BadPick(f"Those targets have a total {stat} over {limit}")
        if not relation_ok(plan, spec, [ref(plan, t) for t in chosen]):  # -- group relations (wave 51A) -- "that share a creature type" / "controlled by different players" (601.2c)
            raise BadPick("Those targets must have equal toughness" if spec.get("same_toughness110a") else "Those targets must share no " + spec["shares_none"].replace("_", " ") + "s" if spec.get("shares_none") else "Those targets must share a " + spec["shares"].replace("_", " ") if spec.get("shares") else "Those targets must be controlled by the same player" if spec.get("same_controller") else "Those targets must be controlled by different players")
        if spec.get("different") and not _different(plan, chosen, spec["different"]):  # -- refused zones/sized (wave 3R4)
            raise BadPick(f"Those targets must have different {'names' if spec['different'] == 'name' else 'mana values'}")
        out.groups.append(chosen)
    given = list(division)
    for g, spec in enumerate(specs):
        total = divide_total(spec, divide_x(plan, spec, chooser, source_card, source_object, event, x))
        if total is None or not out.groups[g]:
            out.division.append([])
            continue
        n = len(out.groups[g])
        upto = bool((spec.get("divide") or {}).get("upto110b"))  # -- one-card wordings (wave 110B) -- "distribute up to that many" (Lathiel): fewer than the total may be divided
        if n == 1 and not (upto and total > 1):
            out.division.append([total])  # one target: all of it (601.2d)
            continue
        if not given:
            out.ask = ("divide", g, total)
            return out
        amounts, given = given[:n], given[n:]
        if len(amounts) != n or any(a < 1 for a in amounts) or sum(amounts) > total or (sum(amounts) != total and not upto):
            raise BadPick(f"Divide {total} among the {n} targets: at least 1 each, {total} in all")
        out.division.append(amounts)
    if given:
        raise BadPick("That division doesn't match the targets")
    return out


# -- group relations (wave 51A) -- 601.2c: a restriction on the targets together ("two target creatures that share a creature type", "… controlled by different
# players"); 608.2b: judged again as the spell resolves, a target that left counted as it last existed (608.2h; rulings: Return from Extinction, Run Away Together)
def _facts(plan: Plan, t: TargetRef) -> tuple[Characteristics, str] | None:
    card = plan.state.cards.get(t.id)
    if card is not None and (t.object_id is None or plan.oid(card) == t.object_id):
        return plan.ch(card), card.controller
    from app.rules.triggers import _snapshot_card

    snap = plan.rules.lki.get(t.object_id or "")
    return None if snap is None else (_snapshot_card(plan, snap)[1], snap.controller)


def _kinds(ch: Characteristics, kind: str) -> frozenset[str]:
    from app.rules.characteristics import PERMANENT_TYPES
    from app.rules.creature_types import CREATURE_TYPES

    return ch.subtypes & CREATURE_TYPES if kind == "creature_type" else ch.types & PERMANENT_TYPES if kind == "permanent_type" else ch.types


def relation_ok(plan: Plan, spec: dict[str, Any], refs: list[TargetRef]) -> bool:
    facts = [f for t in refs if (f := _facts(plan, t))]
    if spec.get("shares") and len(facts) > 1 and not frozenset.intersection(*(_kinds(ch, spec["shares"]) for ch, _ in facts)):
        return False
    if spec.get("shares_none") and len(facts) > 1:  # -- wave 110F -- "that share no creature types" (Rivals' Duel): pairwise disjoint
        kinds = [_kinds(ch, spec["shares_none"]) for ch, _ in facts]
        if sum(map(len, kinds)) != len(frozenset().union(*kinds)):
            return False
    if spec.get("typed110i") and any(not _kinds(ch, spec["shares"]) for ch, _ in facts):  # -- cards (wave 110I) -- Aphetto Dredging: a creature type must be chosen (it has one)
        return False
    if spec.get("same_controller") and len({c for _, c in facts}) > 1:
        return False
    if spec.get("same_toughness110a") and len({ch.pt[1] if ch.pt else None for ch, _ in facts}) > 1:  # -- cards (wave 110A) -- V.A.T.S.
        return False
    return not spec.get("controllers") or len({c for _, c in facts}) == len(facts)


def relation_room(plan: Plan, spec: dict[str, Any], options: list[str]) -> int:
    """How many of the legal ``options`` can be chosen together under the group's relation (all of them without one)."""
    if not (spec.get("shares") or spec.get("controllers") or spec.get("same_controller") or spec.get("shares_none") or spec.get("same_toughness110a")):
        return len(options)
    facts = [f for t in options if (f := _facts(plan, ref(plan, t)))]
    if spec.get("same_toughness110a"):  # -- cards (wave 110A) -- the largest set of equal toughness
        from collections import Counter

        return max(Counter(ch.pt[1] if ch.pt else None for ch, _ in facts).values(), default=0)
    if spec.get("shares_none"):  # (wave 110F: pairs only) two can be chosen when some two share nothing
        ks = [_kinds(ch, spec["shares_none"]) for ch, _ in facts]
        return 2 if any(not (a & b) for i, a in enumerate(ks) for b in ks[i + 1:]) else min(1, len(ks))
    if spec.get("controllers"):
        return len({c for _, c in facts})
    if spec.get("same_controller"):
        return max((sum(other == controller for _, other in facts) for _, controller in facts), default=0)
    kinds = [_kinds(ch, spec["shares"]) for ch, _ in facts]
    return max([1 if kinds else 0, *(sum(k in ks for ks in kinds) for k in frozenset().union(*kinds))])


def _total(plan: Plan, chosen: list[str], stat: str) -> int:
    """-- refused zones/sized (wave 3R4) -- the chosen cards' total mana value / power (as they are now)."""
    out = 0
    for t in chosen:
        card = plan.state.cards.get(t)
        if card is None:
            continue
        ch = plan.ch(card)
        out += int(ch.mana_value) if stat == "mana_value" else max(0, ch.pt[0]) if ch.pt is not None else 0
    return out


def _different(plan: Plan, chosen: list[str], what: str) -> bool:
    """-- refused zones/sized (wave 3R4) -- no two chosen cards share a name / a mana value."""
    seen = []
    for t in chosen:
        card = plan.state.cards.get(t)
        if card is None:
            continue
        ch = plan.ch(card)
        seen.append((ch.name or "").lower() if what == "name" else int(ch.mana_value))
    return len(set(seen)) == len(seen)


def source_of(plan: Plan, card_id: str | None, spell: bool = False, *, object_id: str | None = None,
              x: int | None = None, face: int | None = None, fused: bool = False) -> Characteristics | None:
    """The spell or ability source, current or last known (608.2h), for protection checks."""
    card = plan.state.cards.get(card_id or "")
    actual_x = 0
    if object_id is not None and (card is None or plan.oid(card) != object_id):
        from app.rules.triggers import _lki_characteristics

        snap = plan.rules.lki.get(object_id)
        ch = _lki_characteristics(plan, snap) if snap is not None else None
        actual_x = (snap.x or 0) if snap is not None and snap.zone == "stack" else 0
    else:
        ch = plan.ch(card) if card is not None else None
        if card is not None and card.zone == "stack" and card.stack_info is not None:
            actual_x = card.stack_info.x or 0
        elif card is not None and spell and (face is not None or fused):
            from app.rules import characteristics

            ch = characteristics.provenance(card, characteristics.as_cast(card, plan.info, face, fused))
    from app.rules import source_qualities

    return replace(source_qualities.source(ch, actual_x if x is None else x), is_spell=spell, is_ability=not spell) if ch is not None else None


def as_spell(ch: Characteristics, x: int | None = None) -> Characteristics:
    from app.rules import source_qualities

    return replace(source_qualities.source(ch, x), is_spell=True, is_ability=False)


def label(plan: Plan, target: str) -> str:
    if target in plan.state.players:
        return plan.name(target)
    card = plan.state.cards.get(target)
    return card.name if card else "?"
