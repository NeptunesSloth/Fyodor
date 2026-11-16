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


def _walk(state: GameState, actor: str | None, ts: float) -> None:
    """Planeswalk (701.31b): the face-up card goes to the bottom of the planar deck and the next card is turned face up."""
    pc = _table(state)
    gone = state.cards.get(pc.face_id or "")
    gone_oid = state.rules.object_id(gone.id) if gone is not None and state.rules is not None else None
    left = pc.deck.pop(0)
    pc.deck.append(left)
    pc.visited = [*pc.visited, left][-VISITED_KEPT:]
    pc.walks += 1
    now = pc.deck[0]
    parts = [text("The table planeswalked to "), card_part(now)]
    if now.phenomenon:
        parts.append(text(" (a phenomenon: resolve it, then planeswalk)"))
    log(state, actor, ts, parts, kind="planar")
    # -- planechase automation -- 901.7a: the card turned face down is gone as an object, the one turned face up is a new one
    drop_face(state)
    sync(state)
    walker = planar_controller(state)
    if gone is not None:  # 701.31d: the plane (or phenomenon) planeswalked away from
        emit(state, "planar", counter="from", card=gone.id, object_id=gone_oid, printing=left.printing_id, player=walker)
    face = state.cards.get(pc.face_id or "")
    if face is not None and state.rules is not None:  # 701.31d the plane planeswalked to; 312.5 a phenomenon encountered
        emit(state, "planar", counter="encounter" if now.phenomenon else "to", card=face.id, object_id=state.rules.object_id(face.id),
             printing=now.printing_id, player=walker)


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
    """The face-up card's object stops existing (it was turned face down, or the deck was put away)."""
    pc = state.planechase
    if pc is not None and pc.face_id is not None:
        state.cards.pop(pc.face_id, None)
        pc.face_id = None


def sync(state: GameState) -> None:
    """Keep the face-up card's rules object as the table is: one while a rules engine runs and a planar deck is out, controlled by
    the planar controller. Deterministic (it reads only the table), so replays, undo and saves rebuild it exactly."""
    pc = state.planechase
    if pc is None:
        return
    ctl = planar_controller(state)
    if state.rules is None or not pc.deck or ctl is None:
        drop_face(state)
        return
    top = pc.deck[0]
    face = state.cards.get(pc.face_id or "")
    if face is not None and face.card_id != top.printing_id:
        drop_face(state)
        face = None
    if face is None:
        state.rules.next_object += 1  # its own object number: its timestamp, as it is turned face up (613.7d), and a fresh id
        fid = f"{FACE_PREFIX}{state.rules.next_object}"
        face = CardInstance(id=fid, card_id=top.printing_id, name=top.name, owner=ctl, controller=ctl, zone=zone_key(ctl, "command"))
        state.cards[fid] = face
        pc.face_id = fid
        state.rules.objects[fid] = state.rules.next_object
    elif face.controller != ctl:  # the same object under the new planar controller (no zone change: 311.5)
        face.owner = face.controller = ctl
        face.zone = zone_key(ctl, "command")


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
    if a.r.face == "chaos":  # 901.9b: chaos ensues (311.7)
        emit(state, "planar", counter="chaos", card=pc.face_id, player=a.actor)
    if a.r.face == "planeswalker":
        if a.by_rules:  # 901.8 / 901.9c: the planeswalking ability triggers (app/rules/planar.py), controlled by the roller
            emit(state, "planar", counter="walk_roll", card=pc.face_id, player=a.actor)
        else:
            _walk(state, a.actor, a.ts)


def planeswalk(state: GameState, a: A.Planeswalk) -> None:
    _walk(state, a.actor, a.ts)
