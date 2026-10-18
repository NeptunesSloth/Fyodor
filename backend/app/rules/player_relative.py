"""-- player-relative selectors (wave 53A) -- objects chosen relative to a player an ability named earlier: "target creature that player
controls", "each other creature that player controls", "that player's graveyard / hand / library".

"That player" is one of: the player the trigger event is about (triggers.bind_that_player, older), the player a target group names, the
controller of an object a target group names ("Target creature an opponent controls deals damage … to another target creature that player
controls": Mutiny), or a player the ability iterates over ("for each player, choose …").

State: none new on the table. A target group that is relative to another carries ``of`` (the index of that earlier group); its selector keeps
the marker ``controller`` / ``zone_owner`` = ``that_player``, which ``bind_what`` turns into ``player:<id>`` from the targets chosen for
group ``of`` (the same binding the trigger event's player gets). Nothing is stored bound, so a copy of the spell that picks new targets for
the earlier group re-binds the later one (707.10c, 115.7d), and resolution binds again from the targets as they last were (608.2b, 608.2h).
Effects that act on "each creature that player controls" read ``controlled:tp:<group>|<selector>`` (effects._controlled_by); ``tp:<group>``
is the player reference: the player a group's target is, or the controller of the permanent it is (as it last existed, 608.2h).

Decisions: the group's chooser picks targets as always (601.2c, 603.3d): the options of the later group are the legal ones for the player
bound from the earlier pick. Hidden information: none (battlefield and graveyard objects are public).

Rules: 115.1 / 115.3 (each "target" is its own group), 601.2c (groups are chosen in order, so the later one can depend on the earlier), 608.2b
(a target no longer legal — here also "controlled by that player" — is illegal), 608.2h (last known information), 707.10c (a copy may choose
new targets), 109.4 / 108.3 (controller of a permanent, owner of a card).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

THAT = selectors.THAT_PLAYER
_MARKS = (f'"controller":"{THAT}"', f'"zone_owner":"{THAT}"')
_OPPONENT_STRINGS = ("creature_opponent_controls", "nonland_permanent_opp", "artifact_or_enchantment_opp", "creature_or_planeswalker_opp")
TP = "tp:"  # the player reference "the player (or the controller of the object) target group <n> names"


def marks(what: Any) -> bool:
    """Does a selector key say "that player controls / that player's graveyard" (unbound)?"""
    return isinstance(what, str) and what.startswith(selectors.PREFIX) and any(m in what for m in _MARKS)


def _names_player(group: dict[str, Any]) -> bool:
    """Can a later "that player" mean the player a group's one target is, or the opponent who controls it ("target creature an opponent controls": the
    phrase names that player)?"""
    from app.rules import scripts

    if group.get("max") != 1 or group.get("of") is not None:
        return False
    if scripts._is_player_group(group):
        return True
    what = group.get("what") or ""
    if what in _OPPONENT_STRINGS:
        return True
    if not isinstance(what, str) or not what.startswith(selectors.PREFIX):
        return False
    sel = selectors.from_key(what)
    return sel.player is None and not sel.card and sel.zones == ("battlefield",) and sel.controller == "opponent" and not sel.either


def link(groups: list[dict[str, Any]], *, event_player: bool) -> bool:
    """Parse time: tie each group that says "that player controls" to the earlier group that names the player. Groups are changed in place.
    False when the reading would be a guess (two groups could be the one meant, or the trigger's own player is also available)."""
    for k, g in enumerate(groups):
        if not marks(g.get("what")):
            continue
        named = [j for j in range(k) if _names_player(groups[j])]
        if event_player:
            if named:
                return False  # the trigger's player, or the player (the controller) a target names?
            continue  # the trigger event's player (triggers.bind_that_player)
        if len(named) > 1:
            return False  # two possible players
        if named:
            g["of"] = named[0]  # (none: left unbound, scripts._event_refs_ok refuses it)
    return True


def players_of(plan: Plan, refs: list[Any]) -> list[str]:
    """The players a group's targets stand for: a player target is itself, a permanent's is its controller (as it last existed if it left, 608.2h),
    any other card's its owner."""
    from app.rules import targets

    out: list[str] = []
    for t in refs:
        r = t if hasattr(t, "id") else targets.ref(plan, t)
        who: str | None
        if r.id in plan.state.players:
            who = r.id
        else:
            card, f = plan.state.cards.get(r.id), targets._facts(plan, r)
            if card is not None and (r.object_id is None or plan.oid(card) == r.object_id) and not card.zone.endswith((":battlefield", ":stack")) \
                    and card.zone != "stack":
                who = card.owner  # a card in a graveyard, hand, library, exile: its owner (108.3)
            else:
                who = f[1] if f is not None else card.owner if card is not None else None
        if who is not None and who not in out:
            out.append(who)
    return out


def bind_what(plan: Plan, spec: dict[str, Any], groups: list[list[Any]]) -> str:
    """The selector of a group with "that player" bound to the player group ``of`` names (unbound — nothing matches — when there isn't exactly one)."""
    what = str(spec["what"])
    j = spec.get("of")
    if j is None or not marks(what):
        return what
    who = players_of(plan, groups[j]) if j < len(groups) else []
    if len(who) != 1:
        return what
    for key in ("controller", "zone_owner"):
        what = what.replace(f'"{key}":"{THAT}"', f'"{key}":"player:{who[0]}"')
    return what


def room(plan: Plan, spec: dict[str, Any], specs: list[dict[str, Any]], legal: Any) -> int:
    """For "can this be cast / activated at all" checks: the most legal targets a group relative to another could have, over the targets the earlier group
    could have (``legal``: selector key -> the legal target ids now)."""
    j = spec.get("of")
    if j is None or not marks(spec["what"]):
        return len(legal(spec["what"]))
    best = 0
    for first in legal(specs[j]["what"]):
        for who in players_of(plan, [first]):
            taken = {first} if j in (spec.get("distinct_from") or []) else set()
            best = max(best, len([t for t in legal(bind_what(plan, spec, [[who]] * (j + 1))) if t not in taken]))
    return best


def players_in(plan: Plan, ctx: dict[str, Any], group: int) -> list[str]:
    """``tp:<group>`` as an effect reads it (effects._players): the players the targets still legal in that group stand for."""
    from app.game.rules_state import TargetRef
    from app.rules.effects import target_refs

    refs = target_refs(ctx, "target" if group == 0 and not ctx.get("groups") else f"target:{group}")
    return [p for p in players_of(plan, [TargetRef(**t) for t in refs]) if p in plan.live()]


def as_controlled(who: str) -> str:
    """An effect's "each other creature that player controls" (a selector with the controller unbound) in the form the pronoun reader binds
    (scripts.resolve_it): ``controlled:that_player|<selector>``."""
    return "controlled:that_player|" + selectors.replace(selectors.from_key(who), controller=None).key()


def other_than(ctx: dict[str, Any], players: str, sel: selectors.Selector) -> list[dict[str, Any]]:
    """"Each other creature that player controls" after "target creature an opponent controls": "other" is other than the target the player was taken from
    (``tp:<group>``); a source's own "other" is the selector's (selectors.candidates)."""
    from app.rules.effects import target_refs

    if not sel.other or not players.startswith(TP):
        return []
    return target_refs(ctx, "target" if players == f"{TP}0" and not ctx.get("groups") else f"target:{players[len(TP):]}")


# -- effects whose selector says "that player's graveyard / that player controls" (a ``sel``, a count): the player is tagged at parse time (``that``: a player reference,
# scripts.resolve_it) and read when the instruction is carried out (effects._continue_effects), so it is the player as the earlier instruction left it
_ANY = re.compile(r'\\"(?:controller|zone_owner)\\":\\"that_player\\"')


def has_marker(e: dict[str, Any]) -> bool:
    return _ANY.search(json.dumps(e)) is not None


def bind_effect(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> dict[str, Any]:
    """The effect with "that player" in its selectors replaced by the one player ``e["that"]`` names now (none, or several: left unbound - nothing matches)."""
    from app.rules.effects import _players

    who = _players(plan, ctx, e["that"])
    if len(who) != 1:
        return e
    raw = json.dumps(e)
    for key in ("controller", "zone_owner"):
        raw = raw.replace(f'\\"{key}\\":\\"{THAT}\\"', f'\\"{key}\\":\\"player:{who[0]}\\"')
    out: dict[str, Any] = json.loads(raw)
    return out
