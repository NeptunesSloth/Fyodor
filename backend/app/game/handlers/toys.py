"""-- table toys (docs/3D_DIRECTION.md §7 "Tabletop toys") -- the dice cannon and the hidden draw bag.

Toys of the table, like its dice: never the rules engine's (a volley isn't "rolling a die" for a card), allowed to a player who
is out of the game (``app.game.out_of_game``) and open to everyone under the table's card permissions. Every outcome is decided
on the server (``app.game.resolve``, the game's own random source) and recorded on the action, so replays, saves and undo
keep it; how the cannon rolls in and the dice fly, or a chit comes out of the bag, is cosmetic on each table.

**The dice cannon** fires a volley of dice across the table: ``count`` d``sides`` landing in front of the player who fired it,
or "Who goes first": one d20 at each player still in the game (each landing in front of that player, in their seat colour);
the highest goes first, and players tied for the highest are fired at again, only them, until one is highest. One log line
says it ("Bob goes first (19)") with every die it took.

**The draw bag** holds named chits (numbers, player names, words: teams, a random seat, a house draw). Like a library, no
view holds what is in it or its order, only how many (``app.game.views.bag_view``): its chits stay on the server, and a draw takes one at
random. The drawn chit is shown to everyone, or only to the player who drew it (who may show it later); every draw is
logged, the chit in the log only for those who may see it (``app.game.views.render_log``). Undoing a draw takes back a random
outcome, so it asks the table like a roll does (``app.game.undo_requests``).
"""

from __future__ import annotations

from collections.abc import Callable

from app.game import actions as A
from app.game import eliminations
from app.game.errors import ActionError
from app.game.ops import log, pname, text
from app.game.state import BagLog, CannonLog, DiceRollLog, DrawnChit, GameState, LogPart

BAG_MAX = 200  # chits in the bag at most
REFIRES = 50  # a tie re-fired this often is the server's bad luck (1 in 20^50): it stops and says so


# ---------------------------------------------------------------------------- the dice cannon


def in_game(state: GameState) -> list[str]:
    """The players still in the game, in seat order (who goes first is theirs to roll for)."""
    out = eliminations.out_now(state)
    return [pid for pid in state.seat_order if pid not in out]


def first_volleys(players: list[str], d20: Callable[[], int]) -> A.CannonData:
    """One d20 at each player; while the highest is tied, the tied players alone are fired at again."""
    results: list[int] = []
    who: list[str] = []
    rounds: list[int] = []
    group, n = list(players), 0
    while True:
        rolls = [d20() for _ in group]
        results += rolls
        who += group
        rounds += [n] * len(group)
        top = max(rolls)
        tied = [pid for pid, v in zip(group, rolls, strict=True) if v == top]
        if len(tied) == 1:
            return A.CannonData(results=results, players=who, rounds=rounds)
        group, n = tied, n + 1
        if n > REFIRES:
            raise ActionError("The dice cannon jammed on a tie: fire it again")


def resolve_cannon(state: GameState, a: A.Cannon, actor: str, randint: Callable[[int, int], int]) -> A.CannonData:
    """The server's numbers for a volley (``randint``: the game's random source)."""
    if a.mode == "first":
        players = in_game(state)
        if len(players) < 2:
            raise ActionError("Who goes first needs two players in the game")
        a.sides, a.count = 20, len(players)
        return first_volleys(players, lambda: randint(1, 20))
    return A.CannonData(results=[randint(1, a.sides) for _ in range(a.count)], players=[actor] * a.count, rounds=[0] * a.count)


def winner(r: A.CannonData) -> tuple[str, int]:
    """Who goes first, and their deciding roll: the highest of the last volley."""
    last = max(r.rounds)
    return max(((pid, v) for pid, v, n in zip(r.players, r.results, r.rounds, strict=True) if n == last), key=lambda x: x[1])


def cannon(state: GameState, a: A.Cannon) -> None:
    r = a.r
    if r is None or not r.results or not len(r.results) == len(r.players) == len(r.rounds):
        raise ActionError("unresolved dice cannon")
    sides = 20 if a.mode == "first" else a.sides
    if any(not 1 <= v <= sides for v in r.results) or any(pid not in state.players for pid in r.players):
        raise ActionError("unresolved dice cannon")
    if a.mode == "first":
        first, top = winner(r)

        def volley(n: int) -> str:
            return ", ".join(f"{state.players[pid].name} {v}" for pid, v, k in zip(r.players, r.results, r.rounds, strict=True) if k == n)

        fired = volley(0) + "".join(f"; the tie re-fired: {volley(n)}" for n in range(1, max(r.rounds) + 1))
        parts: list[LogPart] = [pname(state, first), text(f" goes first ({top}) — "), pname(state, a.actor),
                                text(f" fired the dice cannon, a d20 at each player: {fired}")]
        cannon_log = CannonLog(mode="first", players=list(r.players), rounds=list(r.rounds), winner=first)
    else:
        shown = f"{r.results[0]}" if len(r.results) == 1 else f"{', '.join(map(str, r.results))} (total {sum(r.results)})"
        what = f"a d{sides}" if len(r.results) == 1 else f"{len(r.results)}d{sides}"
        parts = [pname(state, a.actor), text(f" fired {what} from the dice cannon: {shown}")]
        cannon_log = CannonLog(mode="volley", players=list(r.players), rounds=list(r.rounds))
    log(state, a.actor, a.ts, parts, kind="dice", roll=DiceRollLog(sides=sides, results=list(r.results), cannon=cannon_log))


# ---------------------------------------------------------------------------- the draw bag


def _chits(n: int) -> str:
    return "1 chit" if n == 1 else f"{n} chits"


def bag_fill(state: GameState, a: A.BagFill) -> None:
    bag = state.bag
    if a.replace:
        bag.chits, bag.drawn = list(a.chits), []
        msg = f" filled the draw bag with {_chits(len(a.chits))}"
    else:
        if len(bag.chits) + len(a.chits) > BAG_MAX:
            raise ActionError(f"The draw bag holds {BAG_MAX} chits at most")
        bag.chits += a.chits
        msg = f" put {_chits(len(a.chits))} in the draw bag ({len(bag.chits)} inside)"
    if len(bag.chits) > BAG_MAX:
        raise ActionError(f"The draw bag holds {BAG_MAX} chits at most")
    log(state, a.actor, a.ts, [pname(state, a.actor), text(msg)], kind="toy")


def bag_draw(state: GameState, a: A.BagDraw) -> None:
    bag = state.bag
    if a.r is None:
        raise ActionError("unresolved draw")
    if not bag.chits:
        raise ActionError("The draw bag is empty")
    if a.r.index >= len(bag.chits):
        raise ActionError("unresolved draw")
    chit = bag.chits.pop(a.r.index)
    bag.drawn.append(DrawnChit(player=a.actor, chit=chit, shown=a.reveal, seq=state.seq))
    left = f"({len(bag.chits)} left)"
    if a.reveal:
        msg = f" drew “{chit}” from the draw bag {left}"
    else:  # the chit itself only in the drawer's own log line (views.render_log)
        msg = f" drew a chit from the draw bag and kept it hidden {left}"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(msg)], kind="toy")
    state.log[-1].bag = BagLog(player=a.actor, chit=chit, hidden=not a.reveal, left=len(bag.chits))


def bag_show(state: GameState, a: A.BagShow) -> None:
    hidden = [d for d in state.bag.drawn if d.player == a.actor and not d.shown]
    if not hidden:
        raise ActionError("You have no hidden chit to show")
    for d in hidden:
        d.shown = True
    names = ", ".join(f"“{d.chit}”" for d in hidden)
    msg = f" showed the chit they drew: {names}" if len(hidden) == 1 else f" showed the chits they drew: {names}"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(msg)], kind="toy")


def bag_return(state: GameState, a: A.BagReturn) -> None:
    bag = state.bag
    if not bag.drawn:
        raise ActionError("No chits have been drawn from the draw bag")
    n = len(bag.drawn)
    bag.chits += [d.chit for d in bag.drawn]
    bag.drawn = []
    msg = f" put the drawn {'chit' if n == 1 else f'{n} chits'} back in the draw bag ({len(bag.chits)} inside)"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(msg)], kind="toy")


def bag_empty(state: GameState, a: A.BagEmpty) -> None:
    bag = state.bag
    if not bag.chits and not bag.drawn:
        raise ActionError("The draw bag is already empty")
    bag.chits, bag.drawn = [], []
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" emptied the draw bag")], kind="toy")

