"""-- counters & designations (wave 3E) -- Player counters with rules of their own and the
designations a player (or the game) can have. Researched against the Comprehensive Rules of
2026-09-25 (data/rules/comprehensive_rules/).

* Rad counters (728.1): an inherent triggered ability with no source, controlled by the active
  player — "At the beginning of each player's precombat main phase, if that player has one or more
  rad counters, that player mills a number of cards equal to the number of rad counters they have.
  For each nonland card milled this way, that player loses 1 life and removes one rad counter from
  themselves." The intervening "if" is checked as it triggers and again as it resolves (603.4).
* The monarch (725): the table designation ``table.monarch``; its two inherent triggers live in
  app/rules/triggers.py (``monarch_end_step`` / ``monarch_damaged``); "becomes the monarch" is the
  ``monarch`` effect; a change is a ``designation`` event (app/game/rules_state.track) — "whenever you
  become the monarch" triggers only for a player who wasn't the monarch.
* The initiative (726): ``table.initiative``; its three inherent triggers (726.2) — at the beginning
  of its holder's upkeep and whenever a player takes it, that player ventures into Undercity;
  whenever creatures a player controls deal combat damage to its holder, that player takes it.
  They have no source and are controlled by the player who had the initiative as they triggered
  (726.2), except the "takes the initiative" one (the player who took it). 726.5: taking it again
  triggers again.
* Dungeons (309, 701.49): a dungeon card isn't a deck card; venturing puts one into the command zone
  (``rules.dungeons``: the dungeon and the room the venture marker is on), moves the marker room by
  room (the player chooses the dungeon and each fork: decisions), and each room's ability triggers as
  the marker moves into it (309.4c: controlled by the dungeon's owner). The bottommost room's
  dungeon is completed (309.7, ``rules.completed_dungeons``) as a state-based action once its room
  ability has left the stack (309.6), or by venturing again from there (701.49c). "Venture into the
  dungeon" chooses among the Adventures in the Forgotten Realms dungeons; "venture into Undercity"
  only Undercity (701.49d) — Undercity is entered only that way.
* The Ring tempts you (701.54): the player's emblem (``rules.ring_tempted``: how many times the Ring
  tempted them) and their Ring-bearer (``rules.ring_bearers``: a creature they control, chosen each
  time; it stops being their Ring-bearer when another becomes it or another player gains control
  of it). The emblem's abilities by level (701.54c): legendary and "can't be blocked by creatures
  with greater power" (app/rules/combat.py); loot as it attacks; a creature blocking it is sacrificed
  at end of combat; combat damage to a player makes each opponent lose 3 life.

Everything here is deterministic: choices are decisions addressed to the player who makes them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Any

from app.game.rules_state import DecisionOption, DungeonMark, Event, emit
from app.game.state import CardInstance, TokenDef, zone_key
from app.rules.plan import Plan, decide

Context = dict[str, Any]


def status(plan: Plan, you: str, kind: str) -> bool:
    """Conditions about designations (app/rules/conditions.py ``{"status": kind}``)."""
    table = plan.state.table
    monarch = table.monarch if table.monarch in plan.live() else None
    if kind == "no_monarch":  # 725.1: "if there is no monarch"
        return monarch is None
    if kind == "opponent_monarch":
        return monarch is not None and monarch != you
    if kind == "not_monarch":
        return monarch != you
    if kind == "not_initiative":
        return table.initiative != you
    if kind == "completed_dungeon":  # 309.7
        r = plan.state.rules
        return bool(r is not None and r.completed_dungeons.get(you))
    if kind in ("day", "night"):  # 731.1
        return table.day_night == kind
    if kind == "neither_day_nor_night":
        return table.day_night is None
    return False


def _add_trigger(plan: Plan, controller: str, name: str, effects: list[dict[str, Any]], index: int = 0,
                 extra: dict[str, Any] | None = None) -> None:
    """An inherent / room triggered ability with no source object (725.2, 726.2, 728.1, 309.4c)."""
    from app.rules import triggers  # (triggers imports the effects that import this module)

    if controller not in plan.live():
        return
    definition = {"kind": "triggered", "trigger": "inherent", "effects": effects, "optional": False, "target": None,
                  **(extra or {})}
    triggers._add(plan, controller=controller, source_card="", source_object="", name=name, index=index, definition=definition)


# -- rad counters (728) -----------------------------------------------------------------------------
def rad_trigger(plan: Plan) -> None:
    """728.1: at the beginning of the active player's precombat main phase (505.1a: the first main
    phase), if they have one or more rad counters."""
    ap = plan.active
    if ap in plan.live() and plan.state.players[ap].resources.get("rad", 0) > 0:
        _add_trigger(plan, ap, "Rad counters", [{"do": "rad"}])


def rad(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """728.1 as it resolves: the player (the ability's controller: the active player, whose phase it
    is) mills as many cards as they have rad counters; for each nonland card milled this way, they
    lose 1 life and remove one rad counter."""
    pid = ctx["controller"]
    n = plan.state.players[pid].resources.get("rad", 0) if pid in plan.live() else 0
    if n <= 0:
        return True  # 603.4: no rad counters any more — the ability does nothing
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    milled = list(library[:n])
    if not milled:
        return True
    plan.do({"type": "mill", "player": pid, "count": len(milled)}, actor=pid)
    nonland = sum(1 for cid in milled if cid in plan.state.cards and plan.state.cards[cid].zone == zone_key(pid, "graveyard")
                  and not plan.ch(plan.state.cards[cid]).is_land)
    if nonland:
        plan.do({"type": "life", "player": pid, "delta": -nonland}, actor=pid)  # (728.1a: life lost "from radiation")
        plan.do({"type": "resource", "player": pid, "key": "rad", "delta": -min(nonland, n)}, actor=pid)
    return True


# -- the initiative (726) -----------------------------------------------------------------------------
def take_initiative(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """726.3: as a player takes the initiative, whoever had it ceases to; 726.5: taking it again
    triggers "whenever a player takes the initiative" (no second designation)."""
    from app.rules import effects

    for pid in effects._players(plan, ctx, e["who"]):
        if plan.state.table.initiative != pid:
            plan.do({"type": "set_initiative", "player": pid}, actor=pid)  # (a designation event: rules_state.track)
        else:
            emit(plan.state, "designation", player=pid, counter="initiative", from_zone=pid)
            plan.note(f"{plan.name(pid)} took the initiative again")
    return True


def initiative_upkeep(plan: Plan) -> None:
    """726.2: "At the beginning of the upkeep of the player who has the initiative, that player
    ventures into Undercity.\""""
    holder = plan.state.table.initiative
    if holder is not None and holder == plan.active and holder in plan.live():
        _add_trigger(plan, holder, "The initiative", [{"do": "venture", "who": "you", "into": "undercity"}], index=1)


def initiative_damaged(plan: Plan, dealt: list[tuple[str, str, int]]) -> None:
    """726.2: "Whenever one or more creatures a player controls deal combat damage to the player who
    has the initiative, the controller of those creatures takes the initiative." (one trigger per
    such player; controlled by the player who had the initiative)."""
    holder = plan.state.table.initiative
    if holder is None or holder not in plan.live():
        return
    controllers: list[str] = []
    for src, tgt, n in dealt:
        card = plan.state.cards.get(src)
        if tgt == holder and n > 0 and card is not None and card.controller != holder and card.controller not in controllers:
            controllers.append(card.controller)
    for pid in controllers:
        _add_trigger(plan, holder, "The initiative", [{"do": "initiative", "who": f"player:{pid}"}], index=2)


def on_events(plan: Plan, events: list[Event]) -> None:
    """726.2: "Whenever a player takes the initiative, that player ventures into Undercity." — and
    delayed triggers waiting for an opponent to become the monarch (Palace Jailer, 603.7)."""
    from app.rules import delayed

    r = plan.rules
    for e in events:
        if e.kind != "designation" or not e.player or e.manual:
            continue
        if e.counter == "initiative":
            _add_trigger(plan, e.player, "The initiative", [{"do": "venture", "who": "you", "into": "undercity"}], index=3)
        if e.counter == "monarch":
            due = [t for t in r.delayed if t.when.get("kind") == "designation" and t.when.get("what") == "monarch"
                   and t.controller != e.player]
            if due:
                r.delayed = [t for t in r.delayed if t not in due or not t.once]
                for t in due:
                    if not _return_until(plan, t):
                        delayed._fire(plan, t, None)


def _return_until(plan: Plan, t: Any) -> bool:
    """610.3: "exile … until an opponent becomes the monarch" (Palace Jailer) — the return is a one-shot
    effect created immediately after that event, not a triggered ability: the cards still in exile come
    back under their owners' control at once (610.3c), together (610.3d). False for any other deferred
    effect (it triggers as a delayed ability, 603.7)."""
    from app.rules import attachments, context

    if t.controller not in plan.live() or not t.effects or any(
            e.get("do") != "return_card" or e.get("to") != "battlefield" or e.get("under") != "owner" or e.get("tapped")
            or not str(e.get("who") or "").startswith(context.PREFIX) for e in t.effects):
        return False
    entries = []
    for e in t.effects:
        for cid in context.objects(plan, {"refs": t.refs}, str(e["who"])[len(context.PREFIX):]):
            card = plan.state.cards[cid]
            if card.zone.endswith(":exile") and card.owner in plan.live():
                entries.append({"card": cid, "player": card.owner, "actor": card.owner})
    if entries:
        attachments.enter(plan, entries, None)
    return True


def facts(plan: Plan, e: Event) -> list[Any]:
    """Trigger facts for app/rules/triggers.py from a ``designation`` event (app/rules/events.py)."""
    if e.counter == "monarch" and e.player:
        return [("become_monarch", None, None, e.player, {})]
    if e.counter == "initiative" and e.player:
        return [("take_initiative", None, None, e.player, {})]
    if e.counter == "ring" and e.player:
        out: list[Any] = [("ring_tempts", None, None, e.player, {})]
        if e.object_id:  # 701.54a: a creature was chosen as their Ring-bearer
            out.append(("ring_bearer", None, None, e.player, {"bearer": e.object_id}))
        return out
    if e.counter == "dungeon" and e.player:
        return [("complete_dungeon", None, None, e.player, {})]
    if e.counter in ("scry", "surveil") and e.player:  # -- looks (wave 8B) -- 701.22b, 701.25c (history.note_look)
        return [(e.counter, None, None, e.player, {"nth": e.amount})]
    if e.counter == "roll" and e.player:  # -- rolling dice (wave 13E) -- "Whenever you roll one or more dice" (app/rules/dice.py)
        return [("roll", None, None, e.player, {"high": e.amount})]
    if e.counter == "crime" and e.player:  # -- crimes (wave 6D) -- 700.13
        return [("commit_crime", None, None, e.player, {})]
    if e.counter in ("monstrous", "renowned") and e.card in plan.state.cards:  # -- becomes monstrous (wave 6D) --
        card = plan.state.cards[e.card]  # (701.37b / 702.112b: the permanent that became monstrous / renowned)
        if card.zone.endswith(":battlefield") and plan.oid(card) == e.object_id:
            return [(f"become_{e.counter}", card, plan.ch(card), card.controller, {"oid": e.object_id})]
        return []
    if e.counter == "level" and e.card in plan.state.cards:  # -- Class (wave 16A) -- 716.2a: the Class became level N
        card = plan.state.cards[e.card]
        if card.zone.endswith(":battlefield") and plan.oid(card) == e.object_id:
            return [("become_level", card, plan.ch(card), card.controller, {"oid": e.object_id, "level": e.amount})]
        return []
    if e.counter in ("day", "night") and e.from_zone:  # 731.1a: "day becomes night" / "night becomes day"
        return [("day_night", None, None, plan.active, {})]
    return []


# -- dungeons (309) and venturing (701.49) --------------------------------------------------------------
@dataclass(frozen=True)
class Room:
    name: str
    text: str  # the room ability's effect, as printed (309.4c)
    leads: tuple[str, ...] = ()  # the rooms its arrows point to (none: the bottommost room)


# Oracle text of the dungeon cards (nontraditional cards, 309.1): the topmost room first.
DUNGEONS: dict[str, tuple[Room, ...]] = {
    "Lost Mine of Phandelver": (
        Room("Cave Entrance", "Scry 1.", ("Goblin Lair", "Mine Tunnels")),
        Room("Goblin Lair", "Create a 1/1 red Goblin creature token.", ("Storeroom", "Dark Pool")),
        Room("Mine Tunnels", "Create a Treasure token.", ("Dark Pool", "Fungi Cavern")),
        Room("Storeroom", "Put a +1/+1 counter on target creature.", ("Temple of Dumathoin",)),
        Room("Dark Pool", "Each opponent loses 1 life and you gain 1 life.", ("Temple of Dumathoin",)),
        Room("Fungi Cavern", "Target creature gets -4/-0 until your next turn.", ("Temple of Dumathoin",)),
        Room("Temple of Dumathoin", "Draw a card."),
    ),
    "Dungeon of the Mad Mage": (
        Room("Yawning Portal", "You gain 1 life.", ("Dungeon Level",)),
        Room("Dungeon Level", "Scry 1.", ("Goblin Bazaar", "Twisted Caverns")),
        Room("Goblin Bazaar", "Create a Treasure token.", ("Lost Level",)),
        Room("Twisted Caverns", "Target creature can't attack until your next turn.", ("Lost Level",)),
        Room("Lost Level", "Scry 2.", ("Runestone Caverns", "Muiral's Graveyard")),
        Room("Runestone Caverns", "Exile the top two cards of your library. You may play them.", ("Deep Mines",)),
        Room("Muiral's Graveyard", "Create two 1/1 black Skeleton creature tokens.", ("Deep Mines",)),
        Room("Deep Mines", "Scry 3.", ("Mad Wizard's Lair",)),
        Room("Mad Wizard's Lair", "Draw three cards and reveal them. You may cast one of them without paying its mana cost."),
    ),
    "Tomb of Annihilation": (
        Room("Trapped Entry", "Each player loses 1 life.", ("Veils of Fear", "Oubliette")),
        Room("Veils of Fear", "Each player loses 2 life unless they discard a card.", ("Sandfall Cell",)),
        Room("Sandfall Cell", "Each player loses 2 life unless they sacrifice a creature, artifact, or land of their choice.",
             ("Cradle of the Death God",)),
        Room("Oubliette", "Discard a card and sacrifice a creature, an artifact, and a land.", ("Cradle of the Death God",)),
        Room("Cradle of the Death God", "Create The Atropal, a legendary 4/4 black God Horror creature token with deathtouch."),
    ),
    "Undercity": (
        Room("Secret Entrance", "Search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
             ("Forge", "Lost Well")),
        Room("Forge", "Put two +1/+1 counters on target creature.", ("Trap!", "Arena")),
        Room("Lost Well", "Scry 2.", ("Arena", "Stash")),
        Room("Trap!", "Target player loses 5 life.", ("Archives",)),
        Room("Arena", "Goad target creature.", ("Archives", "Catacombs")),
        Room("Stash", "Create a Treasure token.", ("Catacombs",)),
        Room("Archives", "Draw a card.", ("Throne of the Dead Three",)),
        Room("Catacombs", "Create a 4/1 black Skeleton creature token with menace.", ("Throne of the Dead Three",)),
        Room("Throne of the Dead Three", "Reveal the top ten cards of your library. Put a creature card from among them onto the "
             "battlefield with three +1/+1 counters on it. It gains hexproof until your next turn. Then shuffle."),
    ),
}
UNDERCITY = "Undercity"
VENTURE_DUNGEONS = tuple(d for d in DUNGEONS if d != UNDERCITY)  # 701.49a / Undercity: "venture into Undercity" only

# Room abilities the sentence grammar doesn't read but whose effect the primitives carry out as printed:
# Runestone Caverns: no duration is stated, so the permission lasts (611.2a) — while the cards remain
# exiled (they're new objects once they leave: 400.7); Veils of Fear / Sandfall Cell: "each player …
# unless they …" (118.12a: each may pay; 101.4: in APNAP order); Cradle of the Death God: a named
# legendary token (111.4).
_ROOM_EFFECTS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("Dungeon of the Mad Mage", "Runestone Caverns"): [
        {"do": "exile_top", "n": 2, "player": "you", "face_down": False, "as": "e0"},
        {"do": "grant_play", "who": "ref:e0", "play": True, "cast": True, "until": "permanent", "optional": True}],
    ("Tomb of Annihilation", "Veils of Fear"): [
        {"do": "each_unless", "who": "each_player", "cost": "Discard a card", "effects": [{"do": "lose_life", "n": 2}]}],
    ("Tomb of Annihilation", "Sandfall Cell"): [
        {"do": "each_unless", "who": "each_player", "cost": "Sacrifice a creature or artifact or land",
         "effects": [{"do": "lose_life", "n": 2}]}],
    ("Tomb of Annihilation", "Cradle of the Death God"): [
        {"do": "create_token", "who": "you", "n": 1, "token": {
            "name": "The Atropal", "power": "4", "toughness": "4", "colors": ["B"],
            "type_line": "Legendary Token Creature — God Horror", "text": "Deathtouch"}}],
    # Oubliette: discard, then one permanent of each type, different permanents, as many as possible
    # (the Release ruling, 2013-04-15, for the same "sacrifice an artifact, a creature, …" instruction)
    ("Tomb of Annihilation", "Oubliette"): [
        {"do": "discard", "who": "you", "n": 1}, {"do": "sacrifice_types", "types": ["Creature", "Artifact", "Land"]}],
    # Mad Wizard's Lair: the cards drawn are revealed (and seen by everyone), then one of them may be cast
    # without paying its mana cost (118.9) — the last instruction, as free_cast requires
    ("Dungeon of the Mad Mage", "Mad Wizard's Lair"): [
        {"do": "hand_mark", "as": "lair0"}, {"do": "draw", "who": "you", "n": 3},
        {"do": "reveal_drawn", "since": "lair0", "as": "lair1"},
        {"do": "free_cast", "zone": "ref", "who": "ref:lair1", "filter": None, "optional": True, "mv": None}],
}
# Throne of the Dead Three: the grammar reads it all but "with three +1/+1 counters on it" (122.6: it enters
# with them, app/rules/replacements.py)
_THRONE = ("Reveal the top ten cards of your library. Put a creature card from among them onto the battlefield. It gains "
           "hexproof until your next turn. Then shuffle.")
# Room abilities left to the players (a decision to resolve them by hand), and why: goad (701.15) is a
# combat requirement the engine doesn't enforce.
_BY_HAND = {("Undercity", "Arena")}


def room(dungeon: str, name: str) -> Room:
    return next(r for r in DUNGEONS[dungeon] if r.name == name)


@cache
def room_definition(dungeon: str, name: str) -> dict[str, Any] | None:
    """309.4c: "When you move your venture marker into this room, [effect]." — a triggered ability
    definition, or None when the players resolve it by hand."""
    from app.rules import scripts

    if (dungeon, name) in _BY_HAND:
        return None
    effects = _ROOM_EFFECTS.get((dungeon, name))
    if effects is not None:
        return {"kind": "triggered", "trigger": "room", "effects": effects, "optional": False, "target": None}
    throne = (dungeon, name) == (UNDERCITY, "Throne of the Dead Three")
    parsed = scripts.parse_effects(_THRONE if throne else room(dungeon, name).text)
    if parsed is None:
        return None
    found, target, optional = parsed
    if throne:
        picks = [x for x in found if x["do"] == "pick_looked"]
        if len(picks) != 1 or picks[0]["to"] != "battlefield":
            return None
        found = [{**x, "counter": "+1/+1", "counter_n": 3} if x is picks[0] else x for x in found]
    return {"kind": "triggered", "trigger": "room", "effects": found, "optional": optional, **scripts.target_fields(target)}


def dungeon_automated(dungeon: str) -> bool:
    """Every room ability of the dungeon is carried out by the engine (coverage)."""
    return all(room_definition(dungeon, r.name) is not None for r in DUNGEONS[dungeon])


def venture_automated(into: str) -> bool:
    return all(dungeon_automated(d) for d in ((UNDERCITY,) if into == "undercity" else VENTURE_DUNGEONS))


def room_label(dungeon: str, name: str) -> str:
    return f"{dungeon} — {name}"


def venture(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.49: venture into the dungeon / Undercity (each player the effect names, in turn order)."""
    from app.rules import effects

    players = [p for p in plan.apnap() if p in effects._players(plan, ctx, e.get("who", "you"))]
    return all(_venture_one(plan, ctx, e, pid) for pid in players)  # (False: a choice is open; its resume ventures the rest)


def _venture_one(plan: Plan, ctx: Context, e: dict[str, Any], pid: str) -> bool:
    r = plan.rules
    into = e.get("into", "dungeon")
    mark = r.dungeons.get(pid)
    if mark is not None and not room(mark.dungeon, mark.room).leads:
        _complete(plan, pid)  # 701.49c: from the bottommost room, the dungeon is completed first
        mark = None
    if mark is None:  # 701.49a / 309.5b: choose a dungeon (the appropriate one: 701.49d) and enter its topmost room
        choices = [UNDERCITY] if into == "undercity" else list(VENTURE_DUNGEONS)
        if len(choices) == 1:
            _enter(plan, pid, choices[0], DUNGEONS[choices[0]][0].name)
            return True
        decide(plan, player=pid, kind="choose_one", prompt="Venture into the dungeon: choose a dungeon",
               options=[DecisionOption(id=d, label=d) for d in choices],
               resume={"step": "venture", "what": "dungeon", "player": pid, "ctx": ctx, "e": e})
        return False
    leads = room(mark.dungeon, mark.room).leads  # 701.49b: an adjacent room, following an arrow
    if len(leads) == 1:
        _enter(plan, pid, mark.dungeon, leads[0])
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"{mark.dungeon}: from {mark.room}, venture into which room?",
           options=[DecisionOption(id=n, label=f"{n} — {room(mark.dungeon, n).text}"[:200]) for n in leads],
           resume={"step": "venture", "what": "room", "player": pid, "ctx": ctx, "e": e})
    return False


def resume_venture(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    res = d.resume
    pid, ctx, e = res["player"], res["ctx"], res["e"]
    if res["what"] == "dungeon":
        _enter(plan, pid, chosen[0], DUNGEONS[chosen[0]][0].name)
    else:
        mark = plan.rules.dungeons.get(pid)
        if mark is not None and chosen[0] in room(mark.dungeon, mark.room).leads:
            _enter(plan, pid, mark.dungeon, chosen[0])
    rest = [p for p in plan.apnap() if p in effects._players(plan, ctx, e.get("who", "you"))]
    for p in rest[rest.index(pid) + 1:] if pid in rest else []:
        if not _venture_one(plan, ctx, e, p):
            return
    effects.continue_effects(plan, ctx)


def _enter(plan: Plan, pid: str, dungeon: str, name: str) -> None:
    """Move the venture marker into a room (309.4a: the topmost one as the dungeon enters the command
    zone): its room ability triggers (309.4c), controlled by the dungeon's owner."""
    r = plan.rules
    first = pid not in r.dungeons
    r.dungeons[pid] = DungeonMark(dungeon=dungeon, room=name)
    plan.note(f"{plan.name(pid)} " + (f"ventured into {dungeon}: {name}" if first else f"moved into {name} ({dungeon})"))
    definition = room_definition(dungeon, name)
    index = [x.name for x in DUNGEONS[dungeon]].index(name)
    if definition is None:
        definition = {"kind": "triggered", "trigger": "room", "optional": False, "target": None,
                      "effects": [{"do": "room_by_hand", "text": room(dungeon, name).text}]}
    _add_trigger(plan, pid, room_label(dungeon, name), [], index=100 + index, extra=definition)


def _complete(plan: Plan, pid: str) -> None:
    """309.7: the dungeon card is removed from the game; its owner completed it."""
    r = plan.rules
    mark = r.dungeons.pop(pid, None)
    if mark is None:
        return
    r.completed_dungeons.setdefault(pid, []).append(mark.dungeon)
    emit(plan.state, "designation", player=pid, counter="dungeon")
    plan.note(f"{plan.name(pid)} completed {mark.dungeon}")


def room_by_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A room ability the engine doesn't carry out: its controller resolves it by hand."""
    decide(plan, player=ctx["controller"], kind="manual_resolution",
           prompt=f"Resolve {ctx.get('name') or 'the room'} by hand: “{e['text']}”. Then press Done"[:300],
           options=[DecisionOption(id="done", label="Done")], resume={"step": "room_by_hand", "ctx": ctx})
    return False


def resume_room_by_hand(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume["ctx"])


def each_unless(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Each player [effect] unless they [cost]" (118.12a): each player in turn order may pay
    (101.4); the effect happens to each one who didn't. Spliced into this resolution as one optional
    payment per player, then the effect for each player who didn't pay."""
    from app.rules import effects

    players = [p for p in plan.apnap() if p in effects._players(plan, ctx, e["who"])]
    at = ctx["next"]
    tag = f"u{at}_"
    added: list[dict[str, Any]] = [{"do": "optional_payment", "who": f"player:{p}", "cost": e["cost"], "bind": f"{tag}{i}"}
                                   for i, p in enumerate(players)]
    for i, p in enumerate(players):
        inner = [{**x, "who": f"player:{p}"} for x in e["effects"]]
        added += [{"do": "only_if", "cond": {"succeeded": f"{tag}{i}", "negate": True}, "skip": len(inner)}, *inner]
    # a new list (the definition's own may be shared): the resolution goes on from here with it
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    effects.continue_effects(plan, ctx)
    return False


def pay_energy_any(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"You may pay any amount of {E}" (107.14): the controller chooses how many energy counters to
    remove (0 to all they have) as it resolves; the amount is bound for "that much" / "for each {E}
    paid this way"."""
    from app.rules import context

    pid = ctx["controller"]
    have = max(0, plan.state.players[pid].resources.get("energy", 0)) if pid in plan.live() else 0
    if have == 0:
        context.bind_amount(ctx, e["as"], 0)
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: pay how much {{E}}? (you have {have})",
           options=[DecisionOption(id=str(n), label=f"Pay {n} {{E}}") for n in range(min(have, 60), -1, -1)],
           resume={"step": "pay_energy_any", "ctx": ctx, "e": e})
    return False


def resume_pay_energy_any(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    n = int(chosen[0])
    if n > plan.state.players[d.player].resources.get("energy", 0):
        raise ActionError("You don't have that much energy")
    if n:
        plan.do({"type": "resource", "player": d.player, "key": "energy", "delta": -n}, actor=d.player)
    context.bind_amount(ctx, e["as"], n)
    plan.note(f"{plan.name(d.player)} paid {n} {{E}}")
    effects.continue_effects(plan, ctx)


def hand_mark(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Remember the cards in the controller's hand (what "draw three cards and reveal them" draws is
    what joins it)."""
    from app.rules import context

    context.refs(ctx)[e["as"]] = {"kind": "probe", "hand": list(plan.state.zones.get(zone_key(ctx["controller"], "hand"), []))}
    return True


def reveal_drawn(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… and reveal them": the cards drawn since the mark are revealed to everyone (701.16a) and
    bound as "them"; the reveal ends once everyone has seen them (they stay in the hand, hidden)."""
    from app.rules import context

    pid = ctx["controller"]
    before = set((context.refs(ctx).get(e["since"]) or {}).get("hand") or [])
    drawn = [c for c in plan.state.zones.get(zone_key(pid, "hand"), []) if c not in before]
    context.bind_objects(plan, ctx, e["as"], drawn)
    if drawn:
        plan.do({"type": "reveal", "card_ids": drawn}, actor=pid)
        plan.do({"type": "hide", "card_ids": drawn}, actor=pid)
    return True


def sacrifice_types(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Sacrifice a creature, an artifact, and a land": one permanent of each listed type, different
    permanents, as many as possible (the Release ruling of 2013-04-15: a permanent with two of the
    types counts for one of them only); the player chooses which (701.21a), all sacrificed at once."""
    pid = ctx["controller"]
    pool, best = _type_pool(plan, pid, e["types"])
    if best == 0:
        return True
    sets = _max_sets(pool, e["types"], best)
    if len(sets) == 1:
        return _sacrifice_set(plan, ctx, pid, sorted(sets[0]))
    options = sorted({c for s in sets for c in s})
    decide(plan, player=pid, kind="choose_cards",
           prompt=f"Sacrifice {', '.join('an ' + t.lower() if t[0] in 'AEIOU' else 'a ' + t.lower() for t in e['types'])} "
                  "(different permanents, as many as you can)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in options],
           min_choices=best, max_choices=best, resume={"step": "sacrifice_types", "ctx": ctx, "e": e})
    return False


def resume_sacrifice_types(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    pool, best = _type_pool(plan, d.player, e["types"])
    if frozenset(chosen) not in {frozenset(s) for s in _max_sets(pool, e["types"], best)}:
        raise ActionError("Choose one permanent for each type, different permanents, as many as you can")
    if _sacrifice_set(plan, ctx, d.player, sorted(chosen)):
        effects.continue_effects(plan, ctx)


def _type_pool(plan: Plan, pid: str, types: list[str]) -> tuple[dict[str, set[str]], int]:
    pool: dict[str, set[str]] = {}
    for c in plan.state.cards.values():
        if c.zone == zone_key(pid, "battlefield") and c.controller == pid and plan.in_game(c):
            has = {t for t in types if t in plan.ch(c).types}
            if has:
                pool[c.id] = has
    sets = _max_sets(pool, types, None)
    return pool, max((len(s) for s in sets), default=0)


def _max_sets(pool: dict[str, set[str]], types: list[str], size: int | None) -> list[set[str]]:
    """Every set of different permanents that can stand for different listed types (all of the
    biggest size, or of ``size``)."""
    from itertools import permutations

    found: set[frozenset[str]] = set()
    ids = sorted(pool)
    for n in range(len(types), 0, -1):
        for order in permutations(types, n):
            def pick(i: int, used: frozenset[str], order: tuple[str, ...] = order) -> None:
                if i == len(order):
                    found.add(used)
                    return
                for c in ids:
                    if c not in used and order[i] in pool[c]:
                        pick(i + 1, used | {c})
            pick(0, frozenset())
        if found and size is None:
            break
    best = size if size is not None else max((len(s) for s in found), default=0)
    return [set(s) for s in found if len(s) == best]


def _sacrifice_set(plan: Plan, ctx: Context, pid: str, cards: list[str]) -> bool:
    from app.rules import effects

    effects._sacrifice_cards(plan, cards, pid, ctx)
    return True


def sba(plan: Plan) -> bool:
    """State-based checks of this module: 309.6 (a dungeon whose venture marker is on its bottommost
    room is removed — completed — once its room ability isn't waiting to trigger or on the stack) and
    701.54a (a Ring-bearer another player gained control of, or that left the battlefield, isn't the
    Ring-bearer any more). True if anything happened."""
    r = plan.rules
    happened = False
    for pid, mark in list(r.dungeons.items()):
        if pid not in plan.live():
            r.dungeons.pop(pid, None)  # (800.4a: it left the game with its owner)
            continue
        if room(mark.dungeon, mark.room).leads:
            continue
        label = room_label(mark.dungeon, mark.room)
        waiting = any(t.name == label and t.controller == pid for t in r.pending_triggers) or \
            any(s.name == label and s.controller == pid for s in r.stack.values())
        if not waiting:
            _complete(plan, pid)
            happened = True
    for pid in list(r.ring_bearers):
        if _bearer_card(plan, pid) is None:
            _set_bearer(plan, pid, None)
            happened = True
    return happened


# -- the Ring tempts you (701.54) -----------------------------------------------------------------------
RING_LABEL = "The Ring: your Ring-bearer is legendary"


def _bearer_card(plan: Plan, pid: str) -> CardInstance | None:
    """701.54e: the creature that is ``pid``'s Ring-bearer — on the battlefield under their control."""
    oid = plan.rules.ring_bearers.get(pid)
    if not oid:
        return None
    card = plan.state.cards.get(oid.rsplit(".", 1)[0])
    if card is None or not card.zone.endswith(":battlefield") or card.controller != pid or plan.oid(card) != oid:
        return None
    return card


def ring_bearer_of(state: Any, card: CardInstance) -> bool:
    """Is this permanent its controller's Ring-bearer? (701.54e)"""
    r = state.rules
    return bool(r is not None and r.ring_bearers.get(card.controller) == r.object_id(card.id) and card.zone.endswith(":battlefield"))


def ring_level(plan: Plan, pid: str) -> int:
    return plan.rules.ring_tempted.get(pid, 0)


def _set_bearer(plan: Plan, pid: str, card: CardInstance | None) -> None:
    from app.rules import layers

    r = plan.rules
    r.effects = [x for x in r.effects if not (x.label == RING_LABEL and x.controller == pid)]
    if card is None:
        r.ring_bearers.pop(pid, None)
        return
    oid = plan.oid(card)
    r.ring_bearers[pid] = oid
    # 701.54c: "Your Ring-bearer is legendary" (a type-changing effect, 613.1d), for as long as it's the Ring-bearer
    layers.add_effect(plan, affected=[oid], layer="4", source=None, controller=pid, duration="permanent",
                      label=RING_LABEL, add_supertypes=["Legendary"])


def ring_tempts(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.54a-d: the player gets the emblem if they have none (701.54c), chooses a creature they
    control as their Ring-bearer, and the Ring has tempted them once more — even if they control no
    creature (701.54d)."""
    from app.rules import effects

    for pid in effects._players(plan, ctx, e.get("who", "you")):
        creatures = sorted(c.id for c in plan.state.cards.values()
                           if c.zone == zone_key(pid, "battlefield") and c.controller == pid and plan.in_game(c) and plan.ch(c).is_creature)
        if len(creatures) > 1:
            decide(plan, player=pid, kind="choose_cards", prompt="The Ring tempts you: choose your Ring-bearer",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in creatures],
                   min_choices=1, max_choices=1, resume={"step": "ring_tempts", "player": pid, "ctx": ctx})
            return False
        _tempted(plan, pid, creatures[0] if creatures else None)
    return True


def resume_ring_tempts(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    pid, ctx = d.resume["player"], d.resume["ctx"]
    card = plan.state.cards.get(chosen[0]) if chosen else None
    ok = card is not None and card.zone == zone_key(pid, "battlefield") and card.controller == pid and plan.ch(card).is_creature
    _tempted(plan, pid, chosen[0] if ok else None)
    effects.continue_effects(plan, ctx)


def _tempted(plan: Plan, pid: str, bearer: str | None) -> None:
    r = plan.rules
    card = plan.state.cards.get(bearer) if bearer else None
    if card is not None:
        _set_bearer(plan, pid, card)
    r.ring_tempted[pid] = r.ring_tempted.get(pid, 0) + 1
    emit(plan.state, "designation", player=pid, counter="ring", object_id=plan.oid(card) if card is not None else None)
    level = r.ring_tempted[pid]
    who = f"{card.name} is {plan.name(pid)}'s Ring-bearer" if card is not None else f"{plan.name(pid)} has no Ring-bearer"
    plan.note(f"The Ring tempts {plan.name(pid)} ({level} time{'s' if level != 1 else ''}): {who}", [card.id] if card else [])


def ring_block_problem(state: Any, attacker: CardInstance, attacker_power: int, blocker_power: int) -> str | None:
    """701.54c: "Your Ring-bearer … can't be blocked by creatures with greater power.\""""
    r = state.rules
    if r is None or r.ring_tempted.get(attacker.controller, 0) < 1 or not ring_bearer_of(state, attacker):
        return None
    if blocker_power > attacker_power:
        return f"{attacker.name} is a Ring-bearer: creatures with greater power can't block it"
    return None


RING_LOOT = [{"do": "draw", "who": "you", "n": 1}, {"do": "discard", "who": "you", "n": 1}]
RING_DRAIN = [{"do": "lose_life", "who": "each_opponent", "n": 3}]


def ring_attacks(plan: Plan, attackers: list[CardInstance]) -> None:
    """701.54c (tempted two or more times): "Whenever your Ring-bearer attacks, draw a card, then discard a card.\""""
    for card in attackers:
        if ring_level(plan, card.controller) >= 2 and ring_bearer_of(plan.state, card):
            _add_trigger(plan, card.controller, "The Ring", RING_LOOT, index=2)


def ring_blocked(plan: Plan, pairs: list[tuple[CardInstance, CardInstance]]) -> None:
    """701.54c (three or more times): "Whenever your Ring-bearer becomes blocked by a creature, the
    blocking creature's controller sacrifices it at end of combat." — once per blocking creature
    (509.3d); the sacrifice is a delayed trigger (603.7) at the end of combat step (511.2)."""
    for attacker, blocker in pairs:
        if ring_level(plan, attacker.controller) >= 3 and ring_bearer_of(plan.state, attacker):
            _add_trigger(plan, attacker.controller, "The Ring",
                         [{"do": "ring_blocker", "card": blocker.id, "object": plan.oid(blocker)}], index=3)


def ring_damage(plan: Plan, sources: list[CardInstance]) -> None:
    """701.54c (four or more times): "Whenever your Ring-bearer deals combat damage to a player, each
    opponent loses 3 life.\""""
    for card in sources:
        if ring_level(plan, card.controller) >= 4 and ring_bearer_of(plan.state, card):
            _add_trigger(plan, card.controller, "The Ring", RING_DRAIN, index=4)


def ring_blocker(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The Ring's third ability resolving: at end of combat, the blocking creature's controller sacrifices it."""
    import secrets

    from app.game.rules_state import DelayedTrigger

    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=None, source_object=None, name="The Ring",
        when={"kind": "step", "step": "end_combat", "whose": "next"},
        effects=[{"do": "sacrifice_object", "card": e["card"], "object": e["object"]}],
        turn=plan.state.turn.number, step=plan.state.turn.phase))
    return True


def sacrifice_object(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Its controller sacrifices it": that object, if it's still on the battlefield (400.7)."""
    from app.rules import effects

    card = plan.state.cards.get(e["card"])
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != e["object"]:
        return True
    effects._sacrifice_cards(plan, [card.id], card.controller, ctx)
    return True


# -- day and night (731, 702.145) ---------------------------------------------------------------------------
def untap_day_night(plan: Plan, prev_active: str, prev_turn: int) -> None:
    """502.2 / 731.2: in the untap step, if it's day and the previous turn's active player cast no
    spells that turn, it becomes night; if it's night and they cast two or more, it becomes day."""
    current = plan.state.table.day_night
    if current is None:
        return  # 731.2c
    cast = plan.rules.spells_this_turn(prev_active, prev_turn)
    if current == "day" and cast == 0:
        become(plan, "night")
    elif current == "night" and cast >= 2:
        become(plan, "day")


def become(plan: Plan, value: str) -> None:
    """"It becomes day / night" (731.1); then daybound / nightbound permanents transform (702.145b, e)."""
    if plan.state.table.day_night != value:
        plan.do({"type": "set_day_night", "value": value}, actor=plan.active)
    day_night_sync(plan)


def day_night(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"It becomes day" / "it becomes night" (731.1)."""
    become(plan, e["value"])
    return True


def _bound(plan: Plan) -> tuple[list[CardInstance], list[CardInstance], bool]:
    """Daybound and nightbound permanents, and whether one says "If it's neither day nor night, it
    becomes day as ~ enters" (once it's day or night it stays one of them, 731.1: read any time)."""
    from app.rules import scripts

    day: list[CardInstance] = []
    night: list[CardInstance] = []
    as_enters = False
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        if "daybound" in ch.keywords:
            day.append(c)
        if "nightbound" in ch.keywords:
            night.append(c)
        if plan.state.table.day_night is None and "day as" in ch.oracle_text:
            as_enters = as_enters or any(d.get("static") == "day_as_enters" for d in scripts.definitions(ch).values())
    return day, night, as_enters


def day_night_sync(plan: Plan) -> bool:
    """702.145c-d, f-g ("any time", not state-based actions): with a daybound permanent and neither
    day nor night, it becomes day; with only nightbound ones, night; at night a daybound permanent
    front face up transforms, by day a nightbound one back face up does (701.27). True if anything
    changed. Run before triggers are looked at, so a daybound permanent entering at night is its
    back face for its "enters" triggers (702.145b: it enters transformed)."""
    table = plan.state.table
    day, night, as_enters = _bound(plan)
    if not day and not night and not as_enters:
        return False
    changed = False
    if table.day_night is None:
        value = "day" if day or as_enters else "night"  # 702.145d / 702.145g
        plan.do({"type": "set_day_night", "value": value}, actor=plan.active)
        changed = True
    if table.day_night == "night":
        flip = [c for c in day if c.face == 0]
        to = 1
    else:
        flip = [c for c in night if c.face == 1]
        to = 0
    for c in flip:
        plan.do({"type": "set_face", "card_id": c.id, "face": to, "faces": 2}, actor=c.controller)
        changed = True
    return changed


# -- coverage ------------------------------------------------------------------------------------------
_VENTURE_WORDS = re.compile(r"\b(?:venture into|take the initiative|takes the initiative)\b", re.IGNORECASE)


def unautomated(definition: dict[str, Any]) -> str | None:
    """Why a definition that ventures (or takes the initiative: 726.2 ventures into Undercity) isn't
    fully automated: a room it may lead into is resolved by hand. None when it's all automated."""
    text = str(definition)
    if "'do': 'venture'" not in text and "'do': 'initiative'" not in text:
        return None
    wants = set()
    for x in _walk(definition):
        if x.get("do") == "venture":
            wants.add(x.get("into", "dungeon"))
        elif x.get("do") == "initiative":
            wants.add("undercity")
    for into in sorted(wants):
        if not venture_automated(into):
            return "a dungeon room is resolved by hand (" + ", ".join(
                f"{d}: {n}" for d, n in sorted(_BY_HAND) if (d == UNDERCITY) == (into == "undercity")) + ")"
    return None


def _walk(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        out.append(value)
        for v in value.values():
            out += _walk(v)
    elif isinstance(value, list):
        for v in value:
            out += _walk(v)
    return out


# -- emblems (wave 13A) -----------------------------------------------------------------------------------
# 114: "You get an emblem with "…"" puts an object in its owner's command zone (114.1) — a card instance whose type line is
# "Emblem" and whose text is the quoted abilities (114.2: no characteristics besides them), owned and controlled by the
# player who got it (114.3); it stays (114.4). Its abilities are read by the ordinary static and trigger grammar, only
# those the engine runs from the command zone: static grants and anthems (app/rules/layers.py ``statics``), and triggered
# abilities the watchers read (app/rules/triggers.py ``_watchers``, ``at_step``). Anything else is not a template match.
# Not a token (111.7 doesn't apply: app/game/handlers/cards.py), and no replacement doubles it (it isn't a token creation).
_EMBLEM_TRIGGERS = ("event", "landfall", "enters_other", "cast_you", "upkeep_you", "end_step_you")


def emblem_card(card: CardInstance) -> bool:
    return card.zone.endswith(":command") and card.token is not None and card.token.type_line == "Emblem"


def emblem_text_ok(text: str) -> bool:
    """Is every ability of this emblem text one the engine runs from the command zone?"""
    from app.rules import characteristics as chars
    from app.rules import coverage, scripts
    from app.rules.statics import zone_static

    ch = chars.of(CardInstance(id="probe", owner="", controller="", zone="p:command",
                               token=TokenDef(name="Emblem", type_line="Emblem", text=text)), {})
    if not ch.abilities or coverage.of_characteristics(ch).level != "FULL":
        return False
    for d in scripts.definitions(ch).values():
        if d.get("kind") == "static":
            if d.get("static") != "grant" or zone_static(d) or d.get("also"):
                return False
        elif d.get("kind") != "triggered" or not (d.get("trigger") in _EMBLEM_TRIGGERS or str(d.get("trigger")).startswith("step:")):
            return False
    return True


def emblem(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """114.1: each player named gets an emblem with the quoted abilities."""
    from app.rules import effects

    src = plan.state.cards.get(ctx.get("source_card") or "")
    name = f"{src.name} Emblem" if src is not None and src.name and not src.ability else "Emblem"
    for pid in effects._players(plan, ctx, e["who"]):
        plan.do({"type": "create_token", "player": pid, "count": 1, "stacked": False,
                 "token": {"name": name, "type_line": "Emblem", "text": e["text"]}}, actor=pid)
    return True


PRIMITIVES: dict[str, Any] = {"emblem": emblem, "rad": rad, "initiative": take_initiative, "venture": venture, "room_by_hand": room_by_hand,
                              "each_unless": each_unless, "ring_tempts": ring_tempts, "ring_blocker": ring_blocker,
                              "sacrifice_object": sacrifice_object, "day_night": day_night, "hand_mark": hand_mark,
                              "reveal_drawn": reveal_drawn, "sacrifice_types": sacrifice_types, "pay_energy_any": pay_energy_any}
RESUME: dict[str, Any] = {"venture": resume_venture, "room_by_hand": resume_room_by_hand, "ring_tempts": resume_ring_tempts,
                          "sacrifice_types": resume_sacrifice_types, "pay_energy_any": resume_pay_energy_any}
