"""Target selectors and legality (CR 115, 601.2c, 608.2b).

A target is chosen when a spell is cast or an ability is put on the stack, and checked again on
resolution: a target that left its zone (it is a new object) or no longer matches is illegal,
and if every target is illegal the spell or ability does nothing (608.2b). Hexproof and shroud
(702.11, 702.18) and protection (702.16) are checked here. The server computes the legal choices; the chooser gets them
in their private decision, nobody else does.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.game.actions import MAX_TARGETS
from app.game.rules_state import TargetRef
from app.game.state import CardInstance
from app.rules import protection, selectors
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan

Check = Callable[[Plan, str, CardInstance, Characteristics], bool]


def _types(*types: str) -> Check:
    return lambda plan, who, card, ch: bool(ch.types & set(types))


SELECTORS: dict[str, tuple[bool, Check | None]] = {
    # selector: (players allowed, permanent check or None for "no permanents")
    "any": (True, _types("Creature", "Planeswalker", "Battle")),
    "creature": (False, _types("Creature")),
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
                                       and (card.attacking is not None or bool(card.blocking))),
    "attacking_creature": (False, lambda plan, who, card, ch: ch.is_creature and card.attacking is not None),
    "blocking_creature": (False, lambda plan, who, card, ch: ch.is_creature and bool(card.blocking)),
    "player": (True, None),
    "opponent": (True, None),
    # -- target forms (agent T) --  "target player or planeswalker" / "target opponent or planeswalker"
    # (a player, or any planeswalker: not only an opponent's)
    "player_or_planeswalker": (True, _types("Planeswalker")),
    "opponent_or_planeswalker": (True, _types("Planeswalker")),
    "permanent_or_player": (True, lambda plan, who, card, ch: True),  # -- counter kinds (wave 24C) -- "target permanent or player"
}
OPPONENTS_ONLY = ("opponent", "opponent_or_planeswalker")


SPELL_SELECTORS: dict[str, Callable[[Characteristics], bool]] = {
    "spell": lambda ch: True,
    "creature_spell": lambda ch: ch.is_creature,
    "noncreature_spell": lambda ch: not ch.is_creature,
    "instant_or_sorcery_spell": lambda ch: ch.is_instant_or_sorcery,
}


def can_target(plan: Plan, chooser: str, card: CardInstance, ch: Characteristics,
               source: Characteristics | None = None) -> bool:
    """Hexproof: not by opponents; shroud: by nobody; protection: not by a source with that quality."""
    if "shroud" in ch.keywords:
        return False
    if "hexproof" in ch.keywords and card.controller != chooser:
        return False
    for rule in ch.imposed:  # -- cant (wave 16F) -- "can't be the target of black spells or abilities from black sources"
        if rule.startswith("untargetable_by_opponents_of:") and chooser != rule.split(":", 1)[1]:
            return False  # (-- review 20A -- the Aura's controller's opponents; no teams: every other player, 102.2)
        if rule.startswith("untargetable:") and source is not None:
            _, opp, non, colors = rule.split(":")
            if (opp == "0" or card.controller != chooser) and bool(set(colors) & source.colors) != (non == "1"):
                return False
    return not protection.protected_from(ch, source)


def _more(plan: Plan, cond: str, pid: str) -> int:
    """-- activated other (wave 21E) -- what "has more life / controls more creatures / has more cards in hand" compares."""
    if cond == "life":
        return plan.state.players[pid].life
    if cond == "hand2":
        return len(plan.state.zones.get(f"{pid}:hand", []))
    return sum(1 for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c)
               and c.controller == pid and plan.ch(c).is_creature)


def legal_targets(plan: Plan, selector: str, chooser: str, source: Characteristics | None = None,
                  source_card: str | None = None, attacker: str | None = None) -> list[str]:
    """Player ids and card ids that ``chooser`` may target with ``selector`` right now
    (``source``: the spell or the ability's source, for protection; ``source_card``: that
    object, for "another target …"; ``attacker``: the creature an "attacks" trigger is about,
    whose defending player "defending player" means, 508.5)."""
    if selector.startswith("opponent_as:"):  # -- activated other (wave 21E) -- "target opponent who has more life than you do as you activate this ability" (601.2c)
        cond = selector.split(":", 1)[1]
        margin = 2 if cond == "hand2" else 1
        return [p for p in legal_targets(plan, "opponent", chooser, source, source_card, attacker)
                if _more(plan, cond, p) >= _more(plan, cond, chooser) + margin]
    if selector.startswith(selectors.PREFIX):  # a structured selector (app/rules/selectors.py)
        return _selector_targets(plan, selectors.from_key(selector), chooser, source, source_card, attacker)
    if selector.startswith("graveyard:"):  # "target Spirit card with mana value N or less from your graveyard"
        from app.rules import characteristics as chars

        _, sub, mv = selector.split(":")
        found: list[str] = []
        for cid in plan.state.zones.get(f"{chooser}:graveyard", []):
            g = chars.of(plan.state.cards[cid], plan.info)
            if (sub == "*" or sub in g.subtypes or sub in g.types) and g.mana_value <= int(mv):
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
                      source_card: str | None, attacker: str | None = None) -> list[str]:
    if sel.player is not None:  # 115.1: players
        from app.rules import player_shields  # -- player shields (wave 5E) -- 702.11c, 702.16b, 702.18a

        return [p for p in plan.live() if selectors.matches_player(plan, sel, p, chooser)
                and player_shields.can_target(plan, chooser, p, source)]
    out = []
    for cid in selectors.candidates(plan, sel, chooser, source_card, attacker):
        card = plan.state.cards[cid]
        on_field = card.zone.endswith(":battlefield") or card.zone == "stack"
        if on_field and not can_target(plan, chooser, card, plan.ch(card), source):  # hexproof / shroud / protection
            continue
        out.append(cid)
    return out


def ref(plan: Plan, target: str) -> TargetRef:
    return TargetRef(id=target, object_id=plan.oid(target) if target in plan.state.cards else None)


def still_legal(plan: Plan, selector: str, chooser: str, target: TargetRef, source: Characteristics | None = None,
                source_card: str | None = None, attacker: str | None = None) -> bool:
    """608.2b: is a chosen target still legal? A card that changed zones is a new object: illegal."""
    if selector.startswith("opponent_as:"):  # (wave 21E: "as you activate this ability" is only judged as it is chosen)
        selector = "opponent"
    if target.object_id is None:
        return target.id in plan.live() and target.id in legal_targets(plan, selector, chooser, source, source_card, attacker)
    card = plan.state.cards.get(target.id)
    if card is None or plan.oid(card) != target.object_id:
        return False
    return target.id in legal_targets(plan, selector, chooser, source, source_card, attacker)


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
    if isinstance(total, dict) and "plus" in total:  # -- X arithmetic (wave 34C) -- "X plus 1 damage divided as you choose" (Meteor Shower): the X announced, plus 1 (601.2d)
        return int(x or 0) + int(total["plus"][1])
    return int(total) if isinstance(total, int) else int(x or 0)


def where_x(plan: Plan, spec: dict[str, Any], chooser: str, source_card: str | None, source_object: str | None,
            event: dict[str, Any] | None = None) -> int:
    """-- X target counts (wave 27C) -- "up to X target …, where X is <a count>" (107.3c: the text defines X; 601.2c: the number of
    targets is what that count is as the targets are chosen, and doesn't change after)."""
    from app.rules import values

    card = plan.state.cards.get(source_card) if source_card else None
    ctx: dict[str, Any] = {"controller": chooser, "source_card": source_card, "source_object": source_object or (plan.oid(card) if card else None),
                           "targets": [], "event": event}  # (wave 28D: a trigger's event is known as it is put on the stack, 603.3d)
    return values.evaluate(plan, ctx, spec["x_value"])


def free_limits(spec: dict[str, Any], x: int | None) -> tuple[int, int]:
    """(min, max) targets of a group as the rules give them, before the engine's own limit; a divided group needs at most as many
    targets as there is to divide, and at least one (601.2d: each gets at least one)."""
    lo, hi = int(spec.get("min", 1)), int(spec.get("max", 1))
    if spec.get("x_count"):  # -- X sized by a count (wave 4K) -- "X target …" / "up to X target …" (601.2c: the number is
        hi = max(0, int(x or 0))  # determined with X, 601.2b, and doesn't change after; wave 29C: X alone limits it)
        lo = hi if spec["x_count"] == "exact" else 0
        if hi == 0:
            return 0, 0  # (X is 0: no targets, nothing to divide among them)
    total = divide_total(spec, x)
    if total is not None:
        lo, hi = max(lo, 1), min(hi, total)
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
                  source_object: str | None = None, event: dict[str, Any] | None = None) -> GroupChoice:
    """Check the choices made so far for each target group, in printed order (601.2c): the
    number of targets (``counts``: how many of ``targets`` are each group's), no object twice
    for one word "target" (115.3; the same object may be chosen for another group unless it says
    "another target"), each a legal target now; then each divided group's division (601.2d:
    at least one each, adding up to the total; one target gets it all). Raises ActionError for a
    wrong choice or when a group can't get enough legal targets; ``ask`` names the next missing
    choice."""
    from app.game.errors import ActionError

    if len(counts) > len(specs) or sum(counts) != len(targets):
        raise ActionError(f"Those aren't the right number of targets for {what}")
    out = GroupChoice(counts=list(counts))
    pos = 0
    for g, spec in enumerate(specs):
        banned = {t for d in spec.get("distinct_from") or [] if d < len(out.groups) for t in out.groups[d]}
        options = [t for t in legal_targets(plan, spec["what"], chooser, source, source_card, attacker)
                   if t not in exclude and t not in banned]
        shaped = {**spec, "x_count": "upto"} if "x_value" in spec else spec
        counted = where_x(plan, spec, chooser, source_card, source_object, event) if "x_value" in spec else x
        lo, hi = group_limits(shaped, counted)
        allowed = free_limits(shaped, counted)[1]
        if g >= len(out.counts) and hi == 0:  # -- kicked / instead (wave 4G) -- a group the spell doesn't require (601.2c)
            out.counts.append(0)
        if g >= len(out.counts):
            if len(options) < lo or hi < lo:
                raise ActionError(f"{what} has no legal target" if not options else f"{what} doesn't have enough legal targets")
            if lo == 0 and not options:
                out.counts.append(0)  # "up to one target …" with nothing to target: zero targets (115.6)
            else:
                out.ask = ("group", g, options, lo, min(hi, len(options)))
                out.capped = allowed if allowed > hi and len(options) > hi else 0  # (said in the prompt: ask_targets)
                return out
        count = out.counts[g]
        chosen = targets[pos:pos + count]
        pos += count
        if not lo <= len(chosen) <= hi:
            raise ActionError(f"Choose {lo if lo == hi else f'{lo} to {hi}'} target{'s' if hi != 1 else ''} for {what}")
        if len(set(chosen)) != len(chosen):
            raise ActionError("The same target can't be chosen twice for one “target”")  # 115.3
        if any(t in banned for t in chosen):
            raise ActionError("“Another target” can't be one you already chose")
        if any(t not in options for t in chosen):
            raise ActionError("That isn't a legal target")
        if spec.get("same_graveyard") and len({plan.state.cards[t].owner for t in chosen if t in plan.state.cards}) > 1:
            raise ActionError("Those targets must all be from a single graveyard")  # (400.1: one player's graveyard)
        if spec.get("total") and _total(plan, chosen, spec["total"][0]) > spec["total"][1]:  # -- refused zones/sized (wave 3R4)
            stat = spec["total"][0].replace("_", " ")  # -- "with total mana value 3 or less": checked as they're chosen (601.2c)
            raise ActionError(f"Those targets have a total {stat} over {spec['total'][1]}")
        if spec.get("different") and not _different(plan, chosen, spec["different"]):  # -- refused zones/sized (wave 3R4)
            raise ActionError(f"Those targets must have different {'names' if spec['different'] == 'name' else 'mana values'}")
        out.groups.append(chosen)
    given = list(division)
    for g, spec in enumerate(specs):
        total = divide_total(spec, x)
        if total is None or not out.groups[g]:
            out.division.append([])
            continue
        n = len(out.groups[g])
        if n == 1:
            out.division.append([total])  # one target: all of it (601.2d)
            continue
        if not given:
            out.ask = ("divide", g, total)
            return out
        amounts, given = given[:n], given[n:]
        if len(amounts) != n or any(a < 1 for a in amounts) or sum(amounts) != total:
            raise ActionError(f"Divide {total} among the {n} targets: at least 1 each, {total} in all")
        out.division.append(amounts)
    if given:
        raise ActionError("That division doesn't match the targets")
    return out


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


def source_of(plan: Plan, card_id: str | None) -> Characteristics | None:
    """The characteristics of a spell or of an ability's source, for protection checks."""
    card = plan.state.cards.get(card_id or "")
    return plan.ch(card) if card is not None else None


def label(plan: Plan, target: str) -> str:
    if target in plan.state.players:
        return plan.name(target)
    card = plan.state.cards.get(target)
    return card.name if card else "?"
