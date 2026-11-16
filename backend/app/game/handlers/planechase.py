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
"""

from __future__ import annotations

from typing import Any, Literal

from app.game import actions as A
from app.game.errors import ActionError
from app.game.ops import log, pname, text
from app.game.state import ALL, GameState, LogPart, PlanarCard, PlanarRoll, Planechase

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
    """Planeswalk: the face-up card goes to the bottom of the planar deck and the next card is turned face up."""
    pc = _table(state)
    left = pc.deck.pop(0)
    pc.deck.append(left)
    pc.visited = [*pc.visited, left][-VISITED_KEPT:]
    pc.walks += 1
    now = pc.deck[0]
    parts = [text("The table planeswalked to "), card_part(now)]
    if now.phenomenon:
        parts.append(text(" (a phenomenon: resolve it, then planeswalk)"))
    log(state, actor, ts, parts, kind="planar")


def start(state: GameState, a: A.PlanarStart) -> None:
    if a.r is None or not a.r.cards:
        raise ActionError("unresolved planar deck")
    state.planechase = Planechase(deck=[c.model_copy() for c in a.r.cards])
    state.settings.planechase, state.settings.planar_deck_size, state.settings.planar_phenomena = True, len(a.r.cards), a.phenomena
    n = len(a.r.cards)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" dealt a planar deck of {n} cards. The table starts on "),
                               card_part(a.r.cards[0])], kind="planar")


def end(state: GameState, a: A.PlanarEnd) -> None:
    _table(state)
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
    if a.r.face == "planeswalker":
        _walk(state, a.actor, a.ts)


def planeswalk(state: GameState, a: A.Planeswalk) -> None:
    _walk(state, a.actor, a.ts)
