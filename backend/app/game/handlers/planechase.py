"""-- planechase (CR 901, Commander's single shared planar deck, 901.15) -- the planar deck, the planar die and planeswalking.

An optional table mode (``GameSettings.planechase``, off by default). The table shares one planar deck of distinct planes and,
if the host wants them, phenomena, dealt and shuffled on the server when the game is created (``factory.new_game``) or when the
host deals one at the table (``planar_start``). Its top card is face up: the plane the table is on.

What is automated is the table's procedure: the active player rolls the planar die (901.9; the die has one planeswalker face,
one chaos face and four blank; the first roll in a turn costs {0}, each further roll that turn {1} more), a planeswalker result
planeswalks (the face-up card goes to the bottom, the next is turned face up), and the planes visited are logged. What a plane or phenomenon
*does* (its static and chaos abilities, a phenomenon's encounter trigger) is applied by the players by hand: the tables show the
card and its text, and a phenomenon waits face up until a player planeswalks away from it ("Done — planeswalk"). The die's mana
cost: with rules automation running the plaque rolls through the rules engine (``roll_planar_die``, app/rules/planar_die.py), which
charges it from the roller's mana pool (or opens the "tap your mana" prompt) and then applies this ``planar_roll`` as one of its
recorded steps; on a manual table it is shown, and players pay it from their pool by hand.

The server decides every outcome and records it on the action (``resolve``): the dealt deck's order on ``planar_start`` (or in the
game's base state), the die's face on ``planar_roll``; planeswalking itself is deterministic. Replays, saves and undo keep it.
No view holds the deck's order (``app.game.views.planechase_view``): only the face-up card, how many cards are in the deck, and
the planes already visited (they went to the bottom face up, in front of everyone).

-- planechase automation -- with a rules engine (``state.rules``), the face-up card is also a rules object (311.4, 312.4, 901.7):
a card instance in ``state.cards`` (``Planechase.face_id``, id ``planar-…``) whose printing is the face-up card's, in the planar
controller's command zone (311.2, 901.4), owned and controlled by the planar controller (311.5, 901.6, 901.15b), kept in no zone
list (views and the table's zone tools never see it: ``planechase_view`` stays what the client shows). ``sync`` keeps it so: a new
object each time a card is turned face up (901.7a), the same object changing controller as the turn passes. Its abilities are read
by the rules engine like an emblem's (app/rules/planar.py). The table's steps record what happened for the engine's triggers
(``emit``: a "planar" event: ``chaos`` 311.7/901.9b, ``walk_roll`` 901.8, ``from`` / ``to`` / ``encounter`` 701.31d, 312.5);
the starting plane is turned face up without any (901.5).

-- planechase deck (wave D) -- several cards may be face up at once (901.11c: Spatial Merging, Norn's Seedcore): ``deck[:face_count]``,
each its own object (``face_id`` then ``face_ids``); planeswalking leaves all of them (``_away``, keeping each one's last known
information, 608.2h). A rules effect changes the planar deck only through the server-built ``planar_deck_op`` (``deck_op``; app/rules/
planar_deck.py): reveal, put back (a random order decided by ``resolve``), planeswalk to revealed planes, shuffle.
"""

from __future__ import annotations

from typing import Any, Literal

from app.game import actions as A
from app.game.errors import ActionError
from app.game.ops import log, pname, text
from app.game.rules_state import emit
from app.game.state import ALL, CardInstance, GameState, LogPart, PlanarCard, PlanarRoll, Planechase, zone_key

DIE_FACES = 6  # one planeswalker symbol, one chaos symbol, four blank faces
VISITED_KEPT = 100  # the planes-visited history a table keeps


def is_phenomenon(type_line: str | None) -> bool:
    return (type_line or "").startswith("Phenomenon")


def is_planar(type_line: str | None) -> bool:
    t = type_line or ""
    return t.startswith("Plane ") or t == "Plane" or is_phenomenon(t)


def face_of(n: int) -> Literal["planeswalker", "chaos", "blank"]:
    """The planar die's face for the server's d6: 1 the planeswalker symbol, 2 the chaos symbol, 3-6 blank."""
    return "planeswalker" if n == 1 else "chaos" if n == 2 else "blank"


def deal(pool: list[PlanarCard], count: int, phenomena: bool, rng: Any) -> list[PlanarCard]:
    """A planar deck of ``count`` distinct cards from ``pool`` (one printing each), shuffled with ``rng``, top first. It always holds
    a plane, and a phenomenon on top goes to the bottom until a plane is (as setting up a planar deck does)."""
    eligible = list({c.name: c for c in pool if phenomena or not c.phenomenon}.values())
    planes = [c for c in eligible if not c.phenomenon]
    if not planes:
        raise ActionError("The card database has no planes: update it to play Planechase")
    rng.shuffle(eligible)
    deck = eligible[:max(1, count)]
    if all(c.phenomenon for c in deck):  # (a tiny deck of phenomena only: one of them becomes a plane)
        deck[-1] = planes[int(rng.randint(0, len(planes) - 1))]
    while deck[0].phenomenon:
        deck.append(deck.pop(0))
    return [c.model_copy() for c in deck]


def pool_of(cards: Any) -> list[PlanarCard]:
    """Every plane and phenomenon of a card source (``CardRepository.planar_cards``); none without one."""
    fetch = getattr(cards, "planar_cards", None)
    rows = fetch() if callable(fetch) else []
    return [PlanarCard(printing_id=r["id"], name=r["name"], phenomenon=is_phenomenon(r.get("type_line"))) for r in rows]


def card_part(c: PlanarCard) -> LogPart:
    return LogPart(name=c.name, card_id=c.printing_id, visible_to=[ALL])


def roll_cost(state: GameState) -> int:
    """What the active player's next planar die roll costs (901.9): {0} the first time in a turn, then {1} more each time."""
    pc = state.planechase
    return pc.rolls if pc is not None and pc.roll_turn == state.turn.number else 0


def roll_refusal(state: GameState, actor: str) -> str | None:
    """Why ``actor`` may not roll the planar die now, or None."""
    pc = state.planechase
    if pc is None or not pc.deck:
        return "The table isn't playing Planechase"
    if actor != state.turn.active_player:
        return "Only the active player rolls the planar die"
    if pc.deck[0].phenomenon:
        return f"Planeswalk away from {pc.deck[0].name} first"
    return None


def _table(state: GameState) -> Planechase:
    if state.planechase is None or not state.planechase.deck:
        raise ActionError("The table isn't playing Planechase")
    return state.planechase


def _walk(state: GameState, actor: str | None, ts: float, bottom: list[str] | None = None) -> None:
    """Planeswalk (701.31b): each face-up card goes to the bottom of the planar deck and the next card is turned face up (901.11c:
    away from every face-up plane; ``bottom``: the order their owner chose, top first — else the order they were turned face up)."""
    pc = _table(state)
    gone = _away(state, pc, bottom)
    now = pc.deck[0]
    parts = [text("The table planeswalked to "), card_part(now)]
    if now.phenomenon:
        parts.append(text(" (a phenomenon: resolve it, then planeswalk)"))
    log(state, actor, ts, parts, kind="planar")
    # -- planechase automation -- 901.7a: the card turned face down is gone as an object, the one turned face up is a new one
    drop_face(state)
    sync(state)
    walker = planar_controller(state)
    _emit_from(state, gone, walker)
    face = state.cards.get(pc.face_id or "")
    if face is not None and state.rules is not None:  # 701.31d the plane planeswalked to; 312.5 a phenomenon encountered
        emit(state, "planar", counter="encounter" if now.phenomenon else "to", card=face.id, object_id=state.rules.object_id(face.id),
             printing=now.printing_id, player=walker)


# -- planechase deck (wave D) -- several face-up cards (901.11c) and a rules effect's steps on the planar deck --------------------------
def face_count(pc: Planechase) -> int:
    """How many cards are face up (``deck[:face_count]``): at least one, never more than the deck holds."""
    return max(1, min(pc.face_count, len(pc.deck)))


def all_face_ids(pc: Planechase) -> list[str]:
    """The face-up cards' rules objects, in ``deck`` order."""
    return [i for i in [pc.face_id, *pc.face_ids] if i]


Gone = list[tuple[str | None, str | None, str]]


def _away(state: GameState, pc: Planechase, bottom: list[str] | None) -> Gone:
    """Put every face-up card on the bottom of the planar deck (701.31b), in ``bottom``'s order when it names each of them; the cards
    planeswalked away from: (object's card id, object id, printing). Each object's last known information is kept first (608.2h: Mount
    Keralia's "it deals damage equal to the number of pressure counters on it", as it last existed)."""
    n = face_count(pc)
    left = pc.deck[:n]
    ids = all_face_ids(pc)
    gone: Gone = []
    for i, c in enumerate(left):
        cid = ids[i] if i < len(ids) and ids[i] in state.cards else None
        oid = state.rules.object_id(cid) if cid is not None and state.rules is not None else None
        if cid is not None and oid is not None and state.rules is not None:
            from app.game.rules_state import snapshot

            state.rules.lki[oid] = snapshot(state, cid)
        gone.append((cid, oid, c.printing_id))
    if bottom and sorted(bottom) == sorted(c.printing_id for c in left):
        left = sorted(left, key=lambda c: bottom.index(c.printing_id))
    pc.deck = [*pc.deck[n:], *left]
    pc.face_count = 1
    pc.visited = [*pc.visited, *left][-VISITED_KEPT:]
    pc.walks += 1
    pc.revealed = []
    return gone


def _emit_from(state: GameState, gone: Gone, walker: str | None) -> None:
    for cid, oid, printing in gone:  # 701.31d: each plane (or phenomenon) planeswalked away from
        if cid is not None:
            emit(state, "planar", counter="from", card=cid, object_id=oid, printing=printing, player=walker)


def emit_chaos(state: GameState, player: str | None) -> None:
    """Chaos ensues (311.7): the chaos ability of each face-up plane triggers (Spatial Merging's ruling: both of them)."""
    pc = state.planechase
    ids: list[str | None] = [*all_face_ids(pc)] if pc is not None else []
    for fid in ids or [None]:
        emit(state, "planar", counter="chaos", card=fid, player=player)


def _find(cards: list[PlanarCard], printing: str) -> PlanarCard:
    got = next((c for c in cards if c.printing_id == printing), None)
    if got is None:
        raise ActionError("That card isn't in the planar deck")
    return got


def _names(cards: list[PlanarCard], sep: str) -> list[LogPart]:
    out: list[LogPart] = []
    for i, c in enumerate(cards):
        out += [text(sep if i else ""), card_part(c)]
    return out


def deck_op(state: GameState, a: A.PlanarDeckOp) -> None:
    """A rules effect's step on the planar deck (``actions.PlanarDeckOp``; app/rules/planar_deck.py). The log names the cards revealed
    (public, 701.20) and the planes planeswalked to, never the order cards are put back in."""
    pc = _table(state)
    n = face_count(pc)
    below = pc.deck[n:]
    who = [text(f"{a.by}: ")] if a.by else []
    if a.op == "reveal":
        got: list[PlanarCard] = []
        for c in below:
            if (sum(not x.phenomenon for x in got) >= a.planes) if a.planes else len(got) >= a.count:
                break
            got.append(c)
        pc.revealed = [c.model_copy() for c in got]
        if got:
            log(state, a.actor, a.ts, [*who, text("revealed "), *_names(got, ", "), text(" from the top of the planar deck")], kind="planar")
        else:
            log(state, a.actor, a.ts, [*who, text("revealed no cards from the planar deck")], kind="planar")
    elif a.op == "arrange":
        top = [_find(below, p) for p in a.top]
        bottom = [_find(below, p) for p in a.bottom]
        rnd = [_find(below, p) for p in a.random]
        perm = a.r.perm if a.r is not None else []
        if sorted(perm) != list(range(len(rnd))):
            raise ActionError("unresolved planar deck order")
        moved = {c.printing_id for c in [*top, *bottom, *rnd]}
        if len(moved) != len(top) + len(bottom) + len(rnd):
            raise ActionError("A card can't be put back twice")
        pc.deck = [*pc.deck[:n], *top, *[c for c in below if c.printing_id not in moved], *bottom, *[rnd[i] for i in perm]]
        pc.revealed = []
        put = [f"{len(top)} on top" if top else "", f"{len(bottom) + len(rnd)} on the bottom" if bottom or rnd else ""]
        if top or bottom or rnd:
            log(state, a.actor, a.ts, [*who, text("put " + " and ".join(x for x in put if x) + " of the planar deck")], kind="planar")
    elif a.op == "walk_to":
        chosen = [_find(below, p) for p in a.to]
        to = {c.printing_id for c in chosen}
        if not chosen or len(to) != len(chosen):
            raise ActionError("Nothing to planeswalk to")
        gone: Gone = []
        if a.away:
            gone = _away(state, pc, a.away_bottom)
            pc.deck = [*chosen, *[c for c in pc.deck if c.printing_id not in to]]
            pc.face_count = len(chosen)
        else:  # "except don't planeswalk away from any plane": turned face up beside the others
            pc.deck = [*pc.deck[:n], *chosen, *[c for c in below if c.printing_id not in to]]
            pc.face_count = n + len(chosen)  # (``walks`` unchanged: the tables' planeswalk motion is the first face-up card changing)
        pc.revealed = [c for c in pc.revealed if c.printing_id not in to]
        log(state, a.actor, a.ts, [*who, text("the table planeswalked to "), *_names(chosen, " and ")], kind="planar")
        if a.away:
            drop_face(state)
        sync(state)
        walker = planar_controller(state)
        _emit_from(state, gone, walker)
        if state.rules is not None:
            ids = all_face_ids(pc)
            for i, c in enumerate(pc.deck[:face_count(pc)]):  # 701.31d: each plane planeswalked to (Spatial Merging: at once, one batch)
                if c.printing_id in to and i < len(ids):
                    emit(state, "planar", counter="encounter" if c.phenomenon else "to", card=ids[i],
                         object_id=state.rules.object_id(ids[i]), printing=c.printing_id, player=walker)
    else:  # shuffle: the cards below the face-up ones
        perm = a.r.perm if a.r is not None else []
        if sorted(perm) != list(range(len(below))):
            raise ActionError("unresolved planar deck order")
        pc.deck = [*pc.deck[:n], *[below[i] for i in perm]]
        pc.revealed = []
        log(state, a.actor, a.ts, [*who, text("shuffled the planar deck")], kind="planar")


# -- planechase automation -- the face-up card as a rules object ---------------------------------------------------------------
FACE_PREFIX = "planar-"


def is_face(card: CardInstance) -> bool:
    """The face-up plane or phenomenon's rules object (``sync``), not a card of anyone's deck."""
    return card.id.startswith(FACE_PREFIX)


def planar_controller(state: GameState) -> str | None:
    """311.5 / 312.4 / 901.6: the active player; if they have left the game, the next player in turn order still in it (who keeps
    the designation until a different player becomes the active player: the next turn makes the active player it again). A target
    dummy never takes a turn and never controls the plane."""
    r = state.rules
    out = set(r.conceded) | set(r.lost) if r is not None else set()
    order = state.turn_order()
    ap = state.turn.active_player
    start = order.index(ap) if ap in order else 0
    for i in range(len(order)):
        p = order[(start + i) % len(order)]
        if p in state.players and not state.players[p].left and p not in out and not state.players[p].dummy:
            return p
    return None


def drop_face(state: GameState) -> None:
    """The face-up cards' objects stop existing (turned face down, or the deck was put away)."""
    pc = state.planechase
    if pc is not None:
        for fid in all_face_ids(pc):
            state.cards.pop(fid, None)
        pc.face_id = None
        pc.face_ids = []


def sync(state: GameState) -> None:
    """Keep the face-up cards' rules objects as the table is: one per face-up card (-- planechase deck (wave D) -- ``deck[:face_count]``,
    matched by position: a card turned face up beside the others comes after them) while a rules engine runs and a planar deck is out,
    controlled by the planar controller. Deterministic (it reads only the table), so replays, undo and saves rebuild it exactly."""
    pc = state.planechase
    if pc is None:
        return
    ctl = planar_controller(state)
    if state.rules is None or not pc.deck or ctl is None:
        drop_face(state)
        return
    ids = all_face_ids(pc) if pc.face_id is not None else []
    kept: list[str] = []
    for i, top in enumerate(pc.deck[:face_count(pc)]):
        face = state.cards.get(ids[i]) if i < len(ids) else None
        if face is not None and face.card_id != top.printing_id:
            state.cards.pop(face.id, None)
            face = None
        if face is None:
            state.rules.next_object += 1  # its own object number: its timestamp, as it is turned face up (613.7d), and a fresh id
            fid = f"{FACE_PREFIX}{state.rules.next_object}"
            face = CardInstance(id=fid, card_id=top.printing_id, name=top.name, owner=ctl, controller=ctl, zone=zone_key(ctl, "command"))
            state.cards[fid] = face
            state.rules.objects[fid] = state.rules.next_object
        elif face.controller != ctl:  # the same object under the new planar controller (no zone change: 311.5)
            face.owner = face.controller = ctl
            face.zone = zone_key(ctl, "command")
        kept.append(face.id)
    for fid in ids[len(kept):]:
        state.cards.pop(fid, None)
    pc.face_id, pc.face_ids = kept[0], kept[1:]


def start(state: GameState, a: A.PlanarStart) -> None:
    if a.r is None or not a.r.cards:
        raise ActionError("unresolved planar deck")
    drop_face(state)
    state.planechase = Planechase(deck=[c.model_copy() for c in a.r.cards])
    sync(state)  # (901.5: the starting plane is turned face up; nothing triggers)
    state.settings.planechase, state.settings.planar_deck_size, state.settings.planar_phenomena = True, len(a.r.cards), a.phenomena
    n = len(a.r.cards)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" dealt a planar deck of {n} cards. The table starts on "),
                               card_part(a.r.cards[0])], kind="planar")


def end(state: GameState, a: A.PlanarEnd) -> None:
    _table(state)
    drop_face(state)
    state.planechase = None
    state.settings.planechase = False
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" put the planar deck away")], kind="planar")


def roll(state: GameState, a: A.PlanarRollAction) -> None:
    pc = _table(state)
    if a.r is None:
        raise ActionError("unresolved planar die")
    if (why := roll_refusal(state, a.actor)) is not None:
        raise ActionError(why)
    cost = roll_cost(state)
    pc.roll_turn, pc.rolls = state.turn.number, cost + 1
    pc.last_roll = PlanarRoll(player=a.actor, face=a.r.face, cost=cost, seq=state.seq)
    paid = f" (cost {{{cost}}})" if cost else ""
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" rolled the planar die{paid}: {a.r.face}")], kind="planar")
    # -- planechase events (wave E2) -- "Whenever you roll the planar die" / "Whenever you roll a blank on the planar die"
    # (app/rules/planar_events.py): a blank that Chaotic Aether makes a chaos roll is no blank roll (its text: it "is a {CHAOS} roll")
    aether = a.r.face == "blank" and state.rules is not None and any(x.get("kind") == "blank_chaos" for x in state.rules.planar_walk_pcw)
    emit(state, "planar", counter="roll", card=pc.face_id, player=a.actor)
    if a.r.face == "blank" and not aether:
        emit(state, "planar", counter="roll_blank", card=pc.face_id, player=a.actor)
    if a.r.face == "blank" and state.rules is not None and any(x.get("kind") == "blank_chaos" for x in state.rules.planar_walk_pcw):
        # -- planechase walk (wave C) -- Chaotic Aether: "each blank roll of the planar die is a {CHAOS} roll" (app/rules/planar_walk.py)
        log(state, a.actor, a.ts, [text("The blank roll is a chaos roll (Chaotic Aether)")], kind="planar")
        emit_chaos(state, a.actor)
    if a.r.face == "chaos":  # 901.9b: chaos ensues (311.7; -- planechase deck (wave D) -- each face-up plane's chaos ability)
        emit_chaos(state, a.actor)
    if a.r.face == "planeswalker":
        if a.by_rules:  # 901.8 / 901.9c: the planeswalking ability triggers (app/rules/planar.py), controlled by the roller
            emit(state, "planar", counter="walk_roll", card=pc.face_id, player=a.actor)
        else:
            _walk(state, a.actor, a.ts)


def planeswalk(state: GameState, a: A.Planeswalk) -> None:
    _walk(state, a.actor, a.ts, a.bottom)
