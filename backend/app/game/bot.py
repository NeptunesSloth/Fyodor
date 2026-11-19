"""-- test opponent -- the server plays for a Sandbox opponent that has a deck ("Add an opponent", app/game/handlers/bot_seat.py): a
"goldfish+" opponent, simple and fast, so a deck can be tested against something that plays back.

**What it sees.** Each decision starts from :func:`observe`: the table exactly as the opponent's own seat is shown it (``build_view`` and
the rules HUD's ``rules_view`` for that seat: its own hand, public information, the engine's hint lists of what it may play now). The
policy (:func:`decide`) reads nothing else; the printed text of a card it can see is looked up in the card database by its printing (public
knowledge). So it never reads a hidden zone of another player (400.2): another player's hand reaches it as anonymous placeholders.

**How it acts.** Through the same intents a player sends, one at a time (``GameSession.perform_bot``): each is validated and recorded
like any player's action, so history replays it (undo, redo, a reload, a save). The engine stays the judge: the policy offers a few tries,
best first, and the first one the engine accepts is the one; every list ends with the safe answer (pass, attack with nothing, block with
nothing, then the target dummy's smallest answer: app/game/dummy.py), so it never holds the game up. Mana is paid by the engine's own
payer (``casting.payment_mode``: its seat always pays automatically).

**The policy ("Simple").**

* Opening hand: keep seven with 2-5 lands; otherwise mulligan once, then keep (cards to the bottom: extra lands while it has more than four,
  else its most expensive spells).
* Its main phases, with the stack empty: play a land (one that enters untapped first, then the colours its hand needs); cast its
  commander when it can; cast the most expensive permanent it can, then other spells: card draw and ramp, removal when an opponent has a
  creature, burn when it kills a creature or the player. Only what the engine's hints list as castable or playable now.
* Targets: removal and burn at the opponent's biggest threat (a commander, then the most power), burn at the player when it is lethal;
  pump and other help on its own best creature.
* Attacks: each creature that no untapped blocker could kill (its power below the attacker's toughness, no deathtouch), or that can't be
  blocked (flying with no flyer or reach across the table), at the human player; everything when that is lethal even if the biggest are
  blocked.
* Blocks: a block that kills the attacker and survives, or trades up; chump blocks only when the damage coming is lethal.
* Abilities (only what the engine's hints list as activatable now; mana abilities are the payer's): after its spells, equip onto its best
  creature (an Equipment not already on one of its creatures), a planeswalker's best ability it can read (removal, cards, tokens; else a
  plus one), and activated abilities whose text it reads: damage and removal at the opponents' things (the same targeting as its spells),
  card draw, tokens, a land search, counters, life, scry. A creature's {T} ability waits for its second main phase (it may attack first);
  at the end of another player's turn it uses its instant-speed ones. Never an ability that untaps something, nor one with a cost it
  doesn't judge (a sacrifice, a discard, life …); each ability at most ``ABILITY_CAP`` times a turn, ``TURN_CAP`` in all (the stack
  resolving opens a new window, so the window cap alone wouldn't stop a free repeatable ability).
* Combat tricks: once blockers are declared (either player's turn), a "target creature gets +N/+N" (or indestructible) instant or ability
  on its creature in a fight it changes (the creature survives, or kills and survives), or on an unblocked attacker when the extra damage
  is lethal.
* Stops: it sets its own (``set_prefs``, as a player sets theirs, once) at its declare blockers step and at another player's declare
  blockers and end steps, besides its main phases; otherwise the engine would pass for it there.
* Otherwise it passes; at instant speed it also casts a creature with flash at the end of another player's turn.

**Beyond Simple** (-- bot smarts --; Simple keeps the reading above, except that every level answers a division of any size):

* The stack (Intermediate on): another player's spell or ability that would take its creature (destroy, exile, bounce, lethal damage or
  -N/-N, from the target arrows; or a board wipe) gets an instant-speed answer it holds: a protection / hexproof / indestructible / pump
  instant on the creature ("creatures you control …" against a wipe), a blink of the target, a regeneration ability, or the doomed
  creature's own "Sacrifice this creature: …". Advanced also counters the removal of a key creature (its commander, a big one, two or
  more to a wipe) and kills the creature another player pumps in a fight. Each spell or ability is answered once (``memory["answered"]``).
* Combat maths (Intermediate on, :func:`_clash`): first strike and double strike, deathtouch, trample, indestructible, flying / reach,
  menace (two blockers) and an attacker's damage divided lethal-first among its blockers. Attacks: each creature no legal block kills;
  everything when what gets through the best blocks is lethal. Blocks: one that wins, trades up or walls for free; two on a menace
  attacker; chumps only while the damage coming (trample counted) is lethal. Advanced also double-blocks a big attacker when the pair
  kills it for less than it is worth. Divisions (every level, :func:`_divide`): lethal damage to each creature it can kill, the most
  valuable first, the rest trampling over (or at a player among the targets); the even split after it in case the engine refuses.
* X, modes, several targets (Intermediate on): X spells and "{X}, …:" abilities with X from its mana (burn just big enough to kill what
  it aims at, all of it at a player when lethal); a modal spell when one mode is clearly good, its modes by :func:`_mode_score`; as many
  worthwhile targets as a spell may have.

Each decision is cheap: one view of the table and a few comparisons. ``MAX_PER_WINDOW`` caps what it does in one priority window (then it
only passes) and the driver caps how long it plays without the player acting (app/multiplayer/bots.py).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.game.autoseat import bots_of
from app.game.control import decider_of
from app.game.errors import ActionError
from app.game.rules_state import Decision, DecisionOption
from app.game.state import CardInstance, GameState, TokenDef

if TYPE_CHECKING:
    from app.game.session import GameSession
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.oracle import AbilityText

log = logging.getLogger(__name__)

MAX_PER_WINDOW = 24  # actions in one priority window (a turn's step, as the stack stands) before it only passes
MAX_TRIES = 6
ABILITY_CAP = 2  # activations of one ability in a turn (a repeatable ability never loops: the stack resolving opens a new window)
TURN_CAP = 10  # activations in a turn, all its abilities together
MAIN = ("main1", "main2")
LEVEL = {"simple": 0, "intermediate": 1, "advanced": 2}  # -- bot levels -- (state.PlayerState.bot_level; a seat without one: Intermediate)
SIMPLE, INTERMEDIATE, ADVANCED = 0, 1, 2
STOPS_MINE = ("main1", "main2", "declare_blockers")  # (where it takes priority: :func:`_stops`)
STOPS_THEIRS = ("declare_blockers", "end")
_DAMAGE = re.compile(r"deals? (\d+) damage")
_HARM = ("destroy", "exile target", "damage", "gets -", "-1/-1", "return target", "tap target", "can't block", "fights", "counter target spell",
         "sacrifice")
_HELP = ("gets +", "+1/+1 counter", "gains ", "untap target", "hexproof", "indestructible")
_DRAW_RAMP = ("draw", "search your library", "add {", "put a land", "lands you control")
_TARGET_CREATURE = re.compile(r"target (?:[\w-]+ )?creature")
_PUMP = re.compile(r"gets \+(\d+)/\+(\d+)")
_BAD_COST = ("sacrifice", "discard", "pay ", "life", "exile", "return", "remove", "put ", "untapped", "reveal")
_COUNTER = "counter target"
_WIPE = ("destroy all creatures", "exile all creatures", "to each creature", "all creatures get -", "destroy all nonland", "each creature you don't control")
_EQUIP_TEXT = "target creature you control gets +"  # (an equip ability's choice reads as help for its own creature)
_BASIC_COLOR = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}


# -- who acts --------------------------------------------------------------------------------------------------------------------


def pending(state: GameState) -> str | None:
    """The opponent the game is waiting for now, or None (cheap: who decides, who has priority, who has an opening hand to settle).
    Nothing while rules automation isn't Full, is paused, or the game is over."""
    for pid in bots_of(state):
        if state.players[pid].left:
            continue
        pregame = state.pregame
        if pregame is not None and not pregame.finished:
            seat = pregame.seats.get(pid)
            if seat is not None and seat.status in ("deciding", "bottoming"):
                return pid
            continue
        r = state.rules
        if r is None or state.settings.automation != "full" or r.paused or r.winner is not None or r.draw_reason is not None:
            return None
        if pid in r.lost or pid in r.conceded:
            continue
        if r.decision is not None:
            if decider_of(state, r.decision) == pid:
                return pid
            continue
        if r.priority == pid:
            return pid
    return None


def observe(state: GameState, pid: str, info: CardInfo) -> dict[str, Any]:
    """The table as ``pid``'s own seat is shown it: everything :func:`decide` may read."""
    from app.game.views import build_view
    from app.rules.view import rules_view

    view = build_view(state, pid, log_limit=1)
    view["rules"] = rules_view(state, pid, info)
    return view


def step(session: GameSession) -> str | None:
    """Play one action for the opponent the game waits for; its type, or None when nothing was played (nobody waits for one, or no try
    was accepted: the table goes on by hand)."""
    state = session.state
    pid = pending(state)
    if pid is None:
        return None
    from app.game.resolve import NoCardInfo

    info: Any = session.cards if session.cards is not None else NoCardInfo()
    memory = session.bot_memory.setdefault(pid, {})
    view = observe(state, pid, info)
    for payload in _stops(view):  # (its stops first, as a player sets theirs: then the move itself)
        try:
            session.perform_bot(pid, payload)
        except (ActionError, ValidationError):
            continue
        except Exception:  # noqa: BLE001 - never breaks the table: it plays on without them
            log.exception("The test opponent couldn't set its stops")
            continue
        if pending(session.state) != pid:
            return str(payload["type"])
        state = session.state
        view = observe(state, pid, info)
    try:
        tries = decide(view, info, memory)
    except Exception:  # noqa: BLE001 - the policy must never break the table: it passes / answers the smallest way instead
        log.exception("The test opponent couldn't work out its move")
        tries = _safe(observe(state, pid, info), info)
    for payload in tries[: MAX_TRIES + 4]:
        try:
            session.perform_bot(pid, payload)
        except (ActionError, ValidationError):
            continue
        except Exception:  # noqa: BLE001 - an engine failure on one try: the next one
            log.exception("The test opponent's %s failed", payload.get("type"))
            continue
        _remember(memory, session.state, payload)
        return str(payload.get("type"))
    return None


def run(session: GameSession, limit: int = 200) -> int:
    """Play for the opponents until none is waited for (at most ``limit`` actions): the tests' driver (the server paces them)."""
    n = 0
    while n < limit and step(session) is not None:
        n += 1
    return n


# -- reading the view ------------------------------------------------------------------------------------------------------------


@dataclass
class Seen:
    """A card the opponent can see, as it reads it."""

    id: str
    name: str
    zone: str  # the zone's name ("battlefield", "hand" …), "stack"
    holder: str  # whose zone
    controller: str
    ch: Characteristics | None
    tapped: bool = False
    power: int = 0
    toughness: int = 0
    keywords: frozenset[str] = frozenset()
    commander: bool = False
    text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def creature(self) -> bool:
        return self.ch is not None and self.ch.is_creature or bool(self.extra.get("creature"))

    @property
    def land(self) -> bool:
        return self.ch is not None and self.ch.is_land

    @property
    def mv(self) -> float:
        return self.ch.mana_value if self.ch is not None else 0

    def has(self, kw: str) -> bool:
        return kw in self.keywords


def _num(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class Board:
    """What :func:`decide` works from: ``view`` and the printed characteristics of the cards it shows."""

    def __init__(self, view: dict[str, Any], info: CardInfo) -> None:
        from app.rules import characteristics as chars

        self.view = view
        self.me: str = view["viewer"]
        self.rules: dict[str, Any] = view.get("rules") or {}
        self.hints: dict[str, Any] = self.rules.get("hints") or {}
        self.players = {p["id"]: p for p in view["players"]}
        level = self.players.get(self.me, {}).get("bot_level")
        self.level: int = LEVEL.get(level or "", LEVEL["intermediate"])  # -- bot levels -- 0 Simple, 1 Intermediate, 2 Advanced
        stats = self.rules.get("stats") or {}
        lost = set(self.rules.get("lost") or {}) | set(self.rules.get("conceded") or [])
        self.live = [pid for pid in view["seat_order"] if not self.players[pid].get("left") and pid not in lost]
        self.cards: dict[str, Seen] = {}
        for cid, c in view["cards"].items():
            if c.get("hidden"):
                continue  # (another player's hidden card: an anonymous placeholder, never read)
            zone_key = c.get("zone") or ""
            holder, _, zone = zone_key.rpartition(":") if ":" in zone_key else ("", "", zone_key)
            stub = CardInstance(id=cid, card_id=c.get("card_id"), name=c.get("name") or "", owner=c.get("owner") or "",
                                controller=c.get("controller") or "", zone=zone_key, face=c.get("face") or 0,
                                face_down=bool(c.get("face_down")), is_token=bool(c.get("is_token")),
                                token=TokenDef.model_validate(c["token"]) if c.get("token") else None)
            try:
                ch = chars.of(stub, info) if not stub.face_down else None
            except Exception:  # noqa: BLE001 - a card it can't read is left alone
                ch = None
            st = stats.get(cid) or {}
            pt = st.get("pt")
            power = _num(pt[0]) if pt else _num(ch.power if ch else None)
            tough = _num(pt[1]) if pt else _num(ch.toughness if ch else None)
            kws = (ch.keywords if ch else frozenset()) | frozenset(st.get("gained") or ()) - frozenset(st.get("lost") or ())
            ability = c.get("ability") or {}
            text = (ch.oracle_text if ch else "") if not ability else str(ability.get("text") or "")  # (an ability on the stack: its text)
            self.cards[cid] = Seen(cid, c.get("name") or "", zone, holder, c.get("controller") or "", ch, bool(c.get("tapped")),
                                   power, tough, frozenset(k.lower() for k in kws), bool(c.get("commander_key")),
                                   text.lower(),
                                   {"creature": st.get("creature"), "attacking": c.get("attacking"), "blocking": c.get("blocking"),
                                    "blocking_more": list(c.get("blocking_more") or ()), "attached_to": c.get("attached_to"),
                                    "counters": dict(c.get("counters") or {}), "damage": _num(c.get("damage")),
                                    "ability": bool(ability), "x": (c.get("stack_info") or {}).get("x")})
        # what each spell or ability on the stack targets (the engine's target arrows, public: 601.2c)
        self.targets: dict[str, list[str]] = {}
        for ar in view.get("arrows") or ():
            if ar.get("kind") == "target":
                self.targets.setdefault(ar.get("source") or "", []).extend(ar.get("targets") or ())

    # (zones)
    def zone(self, pid: str, name: str) -> list[Seen]:
        ids = self.view["zones"].get(f"{pid}:{name}") or []
        if isinstance(ids, dict):  # a library: only the cards it may see
            ids = [cid for _, cid in ids.get("known", [])]
        return [self.cards[cid] for cid in ids if cid in self.cards]

    def creatures(self, pid: str) -> list[Seen]:
        return [c for c in self.zone(pid, "battlefield") if c.creature and c.controller == pid] + \
            [c for p in self.live if p != pid for c in self.zone(p, "battlefield") if c.creature and c.controller == pid]

    def foes_creatures(self) -> list[Seen]:
        return [c for p in self.opponents for c in self.creatures(p)]

    @property
    def opponents(self) -> list[str]:
        """The players it plays against, the human ones first (a target dummy or another opponent after them)."""
        others = [pid for pid in self.live if pid != self.me]
        return sorted(others, key=lambda pid: (bool(self.players[pid].get("dummy")) or self.players[pid].get("bot") is not None,
                                               self.live.index(pid)))

    @property
    def foe(self) -> str | None:
        return next(iter(self.opponents), None)

    def life(self, pid: str) -> int:
        return _num(self.players[pid].get("life"))

    @property
    def my_turn(self) -> bool:
        return self.view["turn"].get("active_player") == self.me

    @property
    def phase(self) -> str:
        return str(self.view["turn"].get("phase") or "")


def _threat(c: Seen) -> tuple[int, int, float]:
    return (1 if c.commander else 0, c.power, c.mv)


def _kind(c: Seen | None) -> str:
    """What a spell or ability does to its targets, from its text: "harm", "help" or "" (neither, or nothing it can tell)."""
    if c is None:
        return ""
    return _kind_of(c.text)


def _kind_of(t: str) -> str:
    if any(w in t for w in _HARM):
        return "harm"
    if any(w in t for w in _HELP):
        return "help"
    return ""


def _damage(c: Seen | None) -> int | None:
    return _damage_text(c.text) if c is not None else None


def _damage_text(t: str) -> int | None:
    m = _DAMAGE.search(t)
    return int(m.group(1)) if m else None


# -- the policy -------------------------------------------------------------------------------------------------------------------


def decide(view: dict[str, Any], info: CardInfo, memory: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The intents to try, best first (the first the engine accepts is played), from ``view`` alone (see :func:`observe`)."""
    memory = memory if memory is not None else {}
    b = Board(view, info)
    pregame = view.get("pregame")
    if pregame and (seat := (pregame.get("seats") or {}).get(b.me)) is not None:
        return _opening_hand(b, seat)
    d = b.rules.get("decision")
    if d is not None and d.get("options") is not None:
        return _answer(b, d, info, memory)
    window = (view["turn"].get("number"), b.phase, view["turn"].get("active_player"), len(view.get("stack") or []))
    if memory.get("window") != window:
        memory["window"], memory["count"], memory["tried"] = window, 0, []
    turn = [view["turn"].get("number"), view["turn"].get("active_player")]
    if (memory.get("acts") or {}).get("turn") != turn:  # (the activation ledger: a turn long, whatever the stack does)
        memory["acts"] = {"turn": turn, "n": {}, "total": 0}
    if memory["count"] >= MAX_PER_WINDOW or not b.hints.get("has_priority"):
        return [{"type": "pass_priority"}]
    return [*_plays(b, memory)[:MAX_TRIES + 3], {"type": "pass_priority"}]  # (short enough that :func:`step` always reaches the pass)


def _stops(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Its own stops (a player's preference, set once through the same intent a player sends): besides its main phases, the declare
    blockers step (a trick once the blocks are known; the step only happens when creatures attack) and the end of another player's
    turn (instant-speed abilities and flash). Otherwise the engine passes for it there and it never gets the chance."""
    prefs = (view.get("rules") or {}).get("prefs") or {}
    me = next((p for p in view.get("players") or [] if p.get("id") == view.get("viewer")), {})
    if not prefs or LEVEL.get(me.get("bot_level") or "", INTERMEDIATE) == SIMPLE:
        return []  # (Simple plays in its main phases only, as it always did)
    mine, theirs = list(prefs.get("stops_my_turn") or []), list(prefs.get("stops_their_turn") or [])
    want_mine = list(dict.fromkeys([*mine, *STOPS_MINE]))
    want_theirs = list(dict.fromkeys([*theirs, *STOPS_THEIRS]))
    if want_mine == mine and want_theirs == theirs:
        return []
    return [{"type": "set_prefs", "stops_my_turn": want_mine, "stops_their_turn": want_theirs}]


def _remember(memory: dict[str, Any], state: GameState, payload: dict[str, Any]) -> None:
    memory["count"] = memory.get("count", 0) + 1
    if payload.get("card_id"):
        memory.setdefault("tried", []).append(payload["card_id"])
    if payload.get("type") == "cast_spell":
        memory["casting"] = payload["card_id"]
        memory.pop("activating", None)
    elif payload.get("type") == "activate_ability":  # (what its choices are for, and the per-turn count that keeps it from looping)
        memory["activating"] = {"card": payload["card_id"], "ability": payload["ability"]}
        acts = memory.setdefault("acts", {"turn": None, "n": {}, "total": 0})
        key = f"{payload['card_id']}:{payload['ability']}"
        acts["n"][key] = acts["n"].get(key, 0) + 1
        acts["total"] = acts.get("total", 0) + 1


def _safe(view: dict[str, Any], info: CardInfo) -> list[dict[str, Any]]:
    d = (view.get("rules") or {}).get("decision")
    if d is not None and d.get("options") is not None:
        return _fallback(d, info)
    if view.get("pregame"):
        return [{"type": "mulligan_keep"}]
    return [{"type": "pass_priority"}]


# (opening hand)


def _opening_hand(b: Board, seat: dict[str, Any]) -> list[dict[str, Any]]:
    hand = b.zone(b.me, "hand")
    lands = [c for c in hand if c.land]
    if seat.get("status") == "deciding":
        early = [c for c in hand if not c.land and c.mv <= 3]
        if seat.get("mulligans", 0) == 0 and (not 2 <= len(lands) <= 5 or b.level >= ADVANCED and not early):  # (Advanced: and a play early)
            return [{"type": "mulligan_take"}, {"type": "mulligan_keep"}]
        return [{"type": "mulligan_keep"}]
    if seat.get("status") == "bottoming":
        n = int(seat.get("to_bottom") or 0)
        keep_lands, spells = list(lands), sorted((c for c in hand if not c.land), key=lambda c: -c.mv)
        out: list[str] = []
        while len(out) < n and (keep_lands or spells):
            if len(keep_lands) > 4 or not spells:
                out.append(keep_lands.pop().id)
            else:
                out.append(spells.pop(0).id)
        return [{"type": "mulligan_bottom", "card_ids": out}] if out else []
    return []


# (priority)


def _plays(b: Board, memory: dict[str, Any]) -> list[dict[str, Any]]:
    tried = set(memory.get("tried") or ())
    x_cast = set(b.hints.get("x_cast") or ())
    castable = [cid for cid in b.hints.get("castable") or [] if cid in b.cards and cid not in tried]
    x_cards = [b.cards[c] for c in castable if c in x_cast]  # (X is announced as it is cast: :func:`_x_casts`, Intermediate on)
    cards = [b.cards[c] for c in castable if c not in x_cast]
    stack_empty = not b.view.get("stack")
    if not stack_empty:  # (something on the stack: Intermediate saves its creatures from removal; Advanced also counters threats)
        if b.level < INTERMEDIATE:
            return []
        return _on_the_stack(b, cards, memory)[:MAX_TRIES]
    if b.phase == "declare_blockers":  # (blocks are known: a trick that wins or saves a fight, either player's turn; removal at an attacker)
        if b.level < INTERMEDIATE:
            return []
        return [*_tricks(b, cards, memory), *(_kill_attacker(b, cards) if not b.my_turn and b.level >= ADVANCED else [])][:MAX_TRIES]
    if not b.my_turn:  # instant speed at the end of another player's turn: flash creatures, instants worth it, instant-speed abilities
        if b.phase == "end":
            flash = [c for c in cards if c.creature and c.has("flash")]
            instants = [c for c in cards if b.level >= INTERMEDIATE and _instant(c) and not c.ch.is_permanent_card  # type: ignore[union-attr]
                        and _COUNTER not in c.text and _worth_casting(b, c)]
            x_instants = _x_casts(b, [c for c in x_cards if _instant(c)], memory) if b.level >= INTERMEDIATE else []
            return [*[_cast(b, c, memory) for c in sorted([*flash, *instants], key=lambda c: (-c.mv, c.id))][:3], *x_instants[:2],
                    *(_activations(b, memory, "end") if b.level >= INTERMEDIATE else [])][:MAX_TRIES]
        return []
    if b.phase not in MAIN:
        return []
    out: list[dict[str, Any]] = []
    lands = [b.cards[c] for c in b.hints.get("playable_lands") or [] if c in b.cards and c not in tried]
    if lands:
        best = max(lands, key=lambda land: _land_score(b, land))
        out.append({"type": "play_land", "card_id": best.id})
    commanders = [c for c in cards if c.commander and c.zone == "command"]
    permanents = [c for c in cards if c not in commanders and c.ch is not None and c.ch.is_permanent_card and not c.land]
    spells = [c for c in cards if c.ch is not None and c.ch.is_instant_or_sorcery and _worth_casting(b, c)]
    lethal = [c for c in spells if _lethal(b, c)]  # (burn that wins the game: first, whatever it costs)
    wanted = [c for c in [*commanders, *permanents, *spells] if c not in lethal and not (
        c.ch is not None and "Aura" in c.ch.subtypes and not _target_for(b, c, b.creatures(b.me) + b.foes_creatures()))]
    if b.level >= ADVANCED:  # (the set of spells that uses its mana best, mana kept for a counterspell, the commander's tax counted)
        reserve = _reserve(b)
        planned = _spend(b, wanted, max(0, _mana(b) - reserve))
        order = [*lethal, *planned]
        if not reserve:  # (what its mana count may have missed: the rest, most expensive first, as the engine allows)
            order += sorted((c for c in wanted if c not in planned), key=lambda c: (-_cost(b, c), not c.creature, c.id))
    else:  # (its commander, then the most expensive permanent it can cast, then other spells)
        order = [*lethal, *[c for c in commanders if c in wanted],
                 *sorted((c for c in wanted if c in permanents), key=lambda c: (-c.mv, not c.creature, c.id)),
                 *sorted((c for c in wanted if c in spells), key=lambda c: (-c.mv, c.id))]
    out += [_cast(b, c, memory) for c in order]
    out = out[:MAX_TRIES]
    if b.level >= INTERMEDIATE and x_cards:  # (X spells with the mana left once the others are cast; a lethal one first)
        xs = _x_casts(b, x_cards, memory)
        lethal_x = [p for p in xs if p.pop("lethal", False)]
        out = [*out[:1 if lands else 0], *lethal_x, *out[1 if lands else 0:]][:MAX_TRIES] + [p for p in xs if p not in lethal_x][:2]
    # (then its abilities: after the spells, so the mana goes to the spells first; the list stays short enough that the pass is tried)
    return [*out, *(_activations(b, memory, b.phase)[:3] if b.level >= INTERMEDIATE else [])]


def _cast(b: Board, c: Seen, memory: dict[str, Any]) -> dict[str, Any]:
    memory["casting"] = c.id
    return {"type": "cast_spell", "card_id": c.id}


def _instant(c: Seen) -> bool:
    return c.ch is not None and ("Instant" in c.ch.types or c.has("flash"))


def _worth_casting(b: Board, c: Seen) -> bool:
    """An instant or sorcery worth casting in its main phase: card draw and ramp, removal with an opposing creature to hit, burn that
    kills something (or the player), a board wipe only when it is behind on the board. Pump and tricks wait (after blockers),
    counterspells wait for a spell to counter."""
    if b.level >= INTERMEDIATE and (modal := _modal_worth(b, c)) is not None:
        return modal  # (a modal spell: by its best mode now)
    if _COUNTER in c.text:
        return False
    if _wipe(c) and b.level >= ADVANCED:
        return _wipe_worth(b, c)
    kind = _kind(c)
    if kind == "harm":
        dmg = _damage(c)
        foes = b.foes_creatures()
        if dmg is not None:
            return any(x.toughness <= dmg for x in foes) or _lethal(b, c)
        return bool(foes)
    if kind == "help":
        return False
    return any(w in c.text for w in _DRAW_RAMP) or not c.text


# (sequencing and mana)


def _cost_mv(cost: str) -> int:
    """A mana cost's total ("{4}{R}{R}" → 6; X counts 0)."""
    return sum(int(s) if s.isdigit() else 0 if s in ("X", "Y", "Z") else 1 for s in re.findall(r"\{([^}]+)\}", cost))


def _cost(b: Board, c: Seen) -> int:
    """What casting ``c`` costs now (the engine's current cost when it differs: commander tax, cost changers), as a mana total."""
    now = (b.hints.get("cost_now") or {}).get(c.id)
    if now:
        return _cost_mv(now)
    return _cost_mv(c.ch.mana_cost) if c.ch is not None and c.ch.mana_cost else int(c.mv)


def _mana(b: Board) -> int:
    """About how much mana it can make now: its untapped lands, and its untapped mana rocks and dorks that can tap (public facts)."""
    sick = set(b.hints.get("summoning_sick") or ())
    n = 0
    for c in b.zone(b.me, "battlefield"):
        if c.controller != b.me or c.tapped:
            continue
        if c.land:
            n += 1
        elif "{t}: add" in c.text and not (c.creature and c.id in sick):
            n += 2 if "add {c}{c}" in c.text else 1
    return n


def _ramp(c: Seen) -> bool:
    t = c.text
    return not c.land and ("search your library for" in t and "land" in t or "put a land" in t or "{t}: add" in t)


def _value(b: Board, c: Seen) -> float:
    """What a spell is worth to cast this turn: its mana value, more for ramp while it has few lands, its commander, a creature."""
    lands = sum(1 for x in b.zone(b.me, "battlefield") if x.land and x.controller == b.me)
    return _cost(b, c) + (3 if _ramp(c) and lands < 5 else 0) + (2 if c.commander else 0) + (0.5 if c.creature else 0) + 0.1


def _spend(b: Board, cards: list[Seen], budget: int) -> list[Seen]:
    """The set of spells that uses its mana best this turn (most value within ``budget``; at most twelve looked at), ramp first, then the
    most expensive: e.g. two 2-drops rather than one 3-drop with four mana."""
    pool = sorted(cards, key=lambda c: (-_value(b, c), c.id))[:12]
    costs = [_cost(b, c) for c in pool]
    values = [_value(b, c) for c in pool]
    best: tuple[float, int] = (0.0, 0)
    for mask in range(1, 1 << len(pool)):
        total = sum(costs[i] for i in range(len(pool)) if mask >> i & 1)
        if total > budget:
            continue
        v = sum(values[i] for i in range(len(pool)) if mask >> i & 1)
        if v > best[0] + 1e-9:
            best = (v, mask)
    chosen = [pool[i] for i in range(len(pool)) if best[1] >> i & 1]
    return sorted(chosen, key=lambda c: (not _ramp(c), -_cost(b, c), c.id))


def _reserve(b: Board) -> int:
    """Mana to keep open on its own turn for a counterspell it holds, once it has a creature on the table (not before: it develops
    first). 0 when it holds none."""
    held = [c for c in b.zone(b.me, "hand") if _COUNTER in c.text and _instant(c)]
    if not held or not b.creatures(b.me):
        return 0
    return min(_cost(b, c) for c in held)


# (interaction)


def _wipe(c: Seen) -> bool:
    return any(w in c.text for w in _WIPE)


def _wipe_worth(b: Board, c: Seen) -> bool:
    """A board wipe only when it is behind: what it kills of the opponents' is worth clearly more than what it loses (two creatures
    or more of theirs)."""
    dmg = _damage(c)

    def dies(x: Seen) -> bool:
        return not x.has("indestructible") and (dmg is None or x.toughness <= dmg)

    def worth(cs: list[Seen]) -> int:
        return sum(max(0, x.power) + max(0, x.toughness) + (6 if x.commander else 0) for x in cs if dies(x))

    theirs = [x for x in b.foes_creatures() if dies(x)]
    return len(theirs) >= 2 and worth(theirs) >= worth(b.creatures(b.me)) + 4


def _menace(b: Board, c: Seen) -> bool:
    """Another player's spell worth a counterspell: a commander, a board wipe, a big creature, anything of mana value 4 or more, burn
    that would kill it."""
    dmg = _damage(c)
    return c.commander or _wipe(c) or c.mv >= 4 or c.creature and c.power >= 4 or dmg is not None and dmg >= b.life(b.me)


def _responses(b: Board, cards: list[Seen], *, key: bool = False) -> list[dict[str, Any]]:
    """With a spell of another player's on top of the stack: counter it when it is a threat (:func:`_menace`) or it would take a key
    creature of its (``key``: its commander, a big creature, two or more to a board wipe), with a counterspell whose restriction it meets
    ("creature spell", "noncreature spell")."""
    stack = b.view.get("stack") or []
    top = b.cards.get(stack[-1]) if stack else None
    if top is None or top.controller == b.me or top.ch is None or top.extra.get("ability") or not (key or _menace(b, top)):
        return []
    out: list[dict[str, Any]] = []
    for c in sorted(cards, key=lambda c: (_cost(b, c), c.id)):
        t = c.text
        if _COUNTER not in t or not _instant(c):
            continue
        if "noncreature spell" in t and top.creature or "creature spell" in t and "noncreature" not in t and not top.creature:
            continue
        out += [{"type": "cast_spell", "card_id": c.id, "targets": [top.id]}, {"type": "cast_spell", "card_id": c.id}]
    return out[:4]


def _kill_attacker(b: Board, cards: list[Seen], among: list[Seen] | None = None) -> list[dict[str, Any]]:
    """On another player's turn, after blockers: instant removal at the most dangerous attacker it kills (it hits it or its creature);
    ``among``: those creatures instead."""
    if among is None:
        mine = b.creatures(b.me)
        attackers = [a for a in b.foes_creatures() if a.extra.get("attacking") and (  # (not one its blocks already kill)
            not (fought := [m for m in mine if m.extra.get("blocking") == a.id or a.id in (m.extra.get("blocking_more") or ())])
            or not _clash(a, fought)[0])]
    else:
        attackers = among
    if not attackers:
        return []
    out: list[dict[str, Any]] = []
    for c in sorted(cards, key=lambda c: (_cost(b, c), c.id)):
        if not _instant(c) or c.ch is None or c.ch.is_permanent_card or _kind(c) != "harm" or _wipe(c) or _COUNTER in c.text:
            continue
        if "target" not in c.text or _TARGET_CREATURE.search(c.text) is None and "any target" not in c.text:
            continue
        dmg = _damage(c)
        hit = [a for a in attackers if a.power >= 2 and (dmg is None and not a.has("indestructible") or dmg is not None and a.toughness <= dmg)]
        if hit:
            best = max(hit, key=lambda a: (_threat(a), a.id))
            out.append({"type": "cast_spell", "card_id": c.id, "targets": [best.id]})
    return out[:2]


def _lethal(b: Board, c: Seen) -> bool:
    dmg = _damage(c)
    return _kind(c) == "harm" and dmg is not None and "target" in c.text and b.foe is not None and b.life(b.foe) <= dmg


# -- X spells (Intermediate and Advanced) -- 107.3a: X announced as it is cast, from the mana it has left


_X = re.compile(r"\bx\b")


def _with_x(text: str, x: int) -> str:
    """``text`` with X read as ``x`` ("deals X damage" → "deals 5 damage"), so the rest of the policy reads it like any spell."""
    return _X.sub(str(x), text)


def _x_most(b: Board, cost: str, budget: int | None = None) -> int:
    """The largest X it can pay for a cost with {X} (or {X}{X}) from the mana it has (at most 1000, CastSpell.x_value's bound)."""
    xs = max(1, cost.count("{X}"))
    have = _mana(b) if budget is None else budget
    return max(0, min(1000, (have - _cost_mv(cost)) // xs))


def _x_casts(b: Board, cards: list[Seen], memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Its X spells worth casting now, X chosen from its mana: burn just big enough to kill the creature it aims at (all of it at a
    player when that is lethal: such a try is marked ``lethal``), card draw, tokens and creatures as big as it can; never X below 1 (or
    below 2 for a permanent). Each with X one smaller after it (its mana count is only an estimate: the engine judges the cost)."""
    out: list[dict[str, Any]] = []
    reserve = _reserve(b) if b.level >= ADVANCED and b.my_turn else 0
    for c in sorted(cards, key=lambda c: (-c.mv, c.id)):
        if c.ch is None or "{X}" not in (c.ch.mana_cost or ""):
            continue
        most = _x_most(b, c.ch.mana_cost, max(0, _mana(b) - reserve))
        floor = 2 if c.ch.is_permanent_card else 1
        if most < floor:
            continue
        x, lethal, aim = most, False, []
        proxy = Seen(c.id, c.name, c.zone, c.holder, c.controller, c.ch, text=_with_x(c.text, most))
        if not c.ch.is_permanent_card:
            if _COUNTER in c.text or not _worth_casting(b, proxy):
                continue
            if _kind(proxy) == "harm" and _damage(proxy) is not None and c.text.count("target") == 1:
                lethal = _lethal(b, proxy)
                if lethal and b.foe is not None:
                    aim = [b.foe]
                else:  # (burn at a creature: the smallest X that kills the one it would aim at)
                    target = next(iter(_target_for(b, proxy, b.foes_creatures())), None)
                    victim = b.cards.get(target or "")
                    if victim is None:
                        continue
                    x = max(floor, min(most, victim.toughness - _num(victim.extra.get("damage"))))
                    aim = [victim.id]
        memory["casting"] = c.id
        out.append({"type": "cast_spell", "card_id": c.id, "x_value": x, **({"targets": aim} if aim else {}),
                    **({"lethal": True} if lethal else {})})
        if x - 1 >= floor and not aim:
            out.append({"type": "cast_spell", "card_id": c.id, "x_value": x - 1})
    return out


# -- modes (Intermediate and Advanced) -- 700.2: the modes of a modal spell or ability, each read on its own


_MODE_OPTION = re.compile(r"^\d+:\d+$")
_TARGET_TYPE = re.compile(r"target (?:[\w-]+ )?(artifact|enchantment|creature|planeswalker|land|permanent|spell)")


def _modes_text(t: str) -> list[str]:
    """The modes printed on a modal card ("• …" lines), lower case."""
    return [m.strip() for m in t.split("•")[1:]] if "•" in t else []


def _mode_score(b: Board, t: str) -> float:
    """How good one mode is now (higher is better; below 0: it hurts it or does nothing)."""
    t = t.lower()
    kind = _kind_of(t)
    if _COUNTER in t:
        stack = b.view.get("stack") or []
        top = b.cards.get(stack[-1]) if stack else None
        return 3 if top is not None and top.controller != b.me else -1
    if kind == "harm" and "target" in t:
        m = _TARGET_TYPE.search(t)
        what = m.group(1) if m else "creature"
        theirs = [c for p in b.opponents for c in b.zone(p, "battlefield") if c.controller == p]
        if what == "creature" or "any target" in t:
            dmg = _damage_text(t)
            foes = b.foes_creatures()
            if dmg is not None:
                kills = [c for c in foes if c.toughness <= dmg]
                return 3 + max((_worth(c) for c in kills), default=0) / 10 if kills else (1 if "any target" in t or "player" in t else -1)
            return 3 + max((_worth(c) for c in foes), default=0) / 10 if foes else -1
        if what == "spell":
            return -1
        hit = [c for c in theirs if what == "permanent" or c.ch is not None and what.capitalize() in c.ch.types]
        return 3 if hit else -1
    if kind == "harm" and "each opponent" in t:
        return 1.5
    if "draw" in t:
        return 2
    if "create" in t:
        return 2
    if "search your library" in t or "add {" in t:
        return 1.5
    if kind == "help":
        return 1 if b.creatures(b.me) else -1
    if "gain" in t and "life" in t:
        return 1
    if "sacrifice" in t or "discard" in t:
        return -0.5
    return 0.5


def _modal_worth(b: Board, c: Seen) -> bool | None:
    """A modal spell is worth casting in its main phase when one of its modes is clearly good now (None: not a modal card it reads)."""
    modes = _modes_text(c.text)
    if not modes or not re.search(r"choose (?:one|two|three|any number|one or more|up to)", c.text):
        return None
    return max(_mode_score(b, m) for m in modes) >= 1.5


def _modes_answer(b: Board, d: dict[str, Any]) -> list[dict[str, Any]] | None:
    """A "Choose N modes" decision (option ids "i:k", labels the modes' text): the best modes by :func:`_mode_score`, as many as are
    good (at least the least it must choose, at most the most). None: not a modes decision."""
    options = [o for o in d.get("options") or [] if o.get("group") != "seen"]
    if d.get("kind") != "choose_cards" or not options or "mode" not in str(d.get("prompt") or "") \
            or not all(_MODE_OPTION.match(str(o["id"])) for o in options):
        return None
    lo, hi = int(d.get("min_choices") or 0), int(d.get("max_choices") or 1)
    scored = sorted(options, key=lambda o: (-_mode_score(b, str(o.get("label") or "")), o["id"]))
    good = [o["id"] for o in scored if _mode_score(b, str(o.get("label") or "")) > 0]
    picks = good[:hi] if len(good) >= lo else [o["id"] for o in scored[:lo]]
    out = [{"type": "choose", "decision_id": d["id"], "option_ids": picks}] if picks or lo == 0 else []
    if lo <= 1 <= hi:
        out += [{"type": "choose", "decision_id": d["id"], "option_ids": [o["id"]]} for o in scored[:3] if [o["id"]] != picks]
    return out


# -- answering the stack (Intermediate and Advanced) -- a spell or ability of another player's that would kill its creature (or a board
# wipe): an instant-speed answer it holds, once per spell or ability (never a loop)


_SHIELD = ("hexproof", "shroud", "protection from", "phase out", "phases out")
_MINUS = re.compile(r"gets? -(\d+)/-(\d+)")


def _removal_kind(t: str) -> str | None:
    """How a harmful spell or ability removes a creature: "exile", "bounce", "minus" (-N/-N), "destroy", "damage" (None: it doesn't)."""
    if "exile" in t:
        return "exile"
    if "return target" in t and "hand" in t or "return all" in t:
        return "bounce"
    if _MINUS.search(t):
        return "minus"
    if "destroy" in t:
        return "destroy"
    if "damage" in t:
        return "damage"
    if "sacrifice" in t:
        return "sacrifice"
    return None


def _doomed(b: Board, top: Seen) -> tuple[str, list[Seen], bool] | None:
    """What ``top`` (another player's spell or ability) would take from it: (how, its creatures that would die or leave, a board wipe)."""
    text = _with_x(top.text, _num(top.extra.get("x"))) if top.extra.get("x") is not None else top.text
    wipe = any(w in text for w in _WIPE) or "all creatures" in text and _removal_kind(text) is not None
    how = _removal_kind(text)
    if how is None or how == "sacrifice":
        return None
    if wipe:
        hit = b.creatures(b.me)
    else:
        hit = [b.cards[x] for x in b.targets.get(top.id, []) if x in b.cards and b.cards[x].controller == b.me
               and b.cards[x].zone == "battlefield" and b.cards[x].creature]
    dmg = _damage_text(text)
    minus = _MINUS.search(text)

    def dies(c: Seen) -> bool:
        if how == "damage":
            return dmg is not None and not c.has("indestructible") and dmg >= c.toughness - _num(c.extra.get("damage"))
        if how == "minus":
            return minus is not None and int(minus.group(2)) >= c.toughness
        if how == "destroy":
            return not c.has("indestructible")
        return True

    doomed = sorted((c for c in hit if dies(c)), key=lambda c: (-_worth(c), c.id))
    return (how, doomed, wipe) if doomed else None


def _saved_by(how: str, wipe: bool, eff: str, c: Seen, top: Seen) -> bool:
    """Would an effect ``eff`` on ``c`` save it from ``top`` (removal of kind ``how``)?"""
    no_regen = "can't be regenerated" in top.text
    if "phase out" in eff or "phases out" in eff:
        return True
    if not wipe and any(s in eff for s in _SHIELD):
        return True  # (hexproof, shroud, protection: the target is illegal as it resolves, 608.2b)
    if "indestructible" in eff and how in ("destroy", "damage"):
        return True
    if "regenerate" in eff and how in ("destroy", "damage") and not no_regen:
        return True
    pump = _pump_of(eff)
    if pump is not None and (pump[0] or pump[1]):
        dmg = _damage_text(_with_x(top.text, _num(top.extra.get("x"))))
        minus = _MINUS.search(top.text)
        if how == "damage" and dmg is not None:
            return c.toughness + pump[1] - _num(c.extra.get("damage")) > dmg
        if how == "minus" and minus is not None:
            return c.toughness + pump[1] > int(minus.group(2))
    return False


def _on_the_stack(b: Board, cards: list[Seen], memory: dict[str, Any]) -> list[dict[str, Any]]:
    """With another player's spell or ability on top of the stack: save its creatures from it (Intermediate on: :func:`_protect`), counter
    a threat (Advanced: its key creature's removal too), or kill the creature another player pumps in a fight (Advanced). Each spell or
    ability on the stack is answered once (the per-turn ledger ``memory["answered"]``: after its answer resolves the same spell is on top
    again, and it lets it be)."""
    stack = b.view.get("stack") or []
    top = b.cards.get(stack[-1]) if stack else None
    if top is None or top.controller == b.me:
        return []
    turn = [b.view["turn"].get("number"), b.view["turn"].get("active_player")]
    answered = memory.get("answered") or {}
    if answered.get("turn") != turn:
        answered = memory["answered"] = {"turn": turn, "ids": []}
    if top.id in answered["ids"]:
        return []
    doomed = _doomed(b, top)
    key = doomed is not None and (doomed[1][0].commander or _worth(doomed[1][0]) >= 6 or doomed[2] and len(doomed[1]) >= 2)
    out: list[dict[str, Any]] = []
    if b.level >= ADVANCED:
        out += _responses(b, cards, key=key)
    if doomed is not None:
        out += _protect(b, cards, memory, top, *doomed)
    if b.level >= ADVANCED:
        out += _answer_pump(b, cards, top)
    if out:
        answered["ids"].append(top.id)
    return out


def _protect(b: Board, cards: list[Seen], memory: dict[str, Any], top: Seen, how: str, doomed: list[Seen],
             wipe: bool) -> list[dict[str, Any]]:
    """Instant-speed answers that save its most valuable doomed creature (or, from a board wipe, all of them): a protection, hexproof,
    indestructible or pump instant ("target creature you control …", "creatures you control …"), a blink of the target ("exile target
    creature you control, then return it": the removal loses its target), a regeneration ability, or a sacrifice of the doomed creature
    for value (its own "Sacrifice this creature: …")."""
    best = doomed[0]
    out: list[dict[str, Any]] = []
    for c in sorted(cards, key=lambda c: (_cost(b, c), c.id)):
        if not _instant(c) or c.ch is None or c.ch.is_permanent_card or _COUNTER in c.text:
            continue
        t = c.text
        mass = "creatures you control" in t or "permanents you control" in t
        aimed = "target creature you control" in t or "target permanent you control" in t or "target creature" in t and _kind_of(t) == "help"
        blink = "exile target" in t and "you control" in t and "return" in t and not wipe
        if blink:
            out.append({"type": "cast_spell", "card_id": c.id, "targets": [best.id]})
        elif mass and all(_saved_by(how, wipe, t, x, top) for x in doomed[:1]):
            out.append({"type": "cast_spell", "card_id": c.id})
        elif aimed and _saved_by(how, wipe, t, best, top):
            out.append({"type": "cast_spell", "card_id": c.id, "targets": [best.id]})
    ids = {c.id for c in doomed}
    for h in b.hints.get("activatable") or []:
        card = b.cards.get(h.get("card_id") or "")
        if card is None or h.get("x") or card.controller != b.me or card.zone != "battlefield" or not _fresh(memory, card.id, h.get("ability")):
            continue
        ab = _ability(card, h.get("ability"))
        if ab is None or ab.kind != "activated":
            continue
        cost, eff = (ab.cost or "").lower(), _effect(ab)
        own = "this creature" in cost or card.name.lower() in cost or "~" in cost
        if card.id in ids and "sacrifice" in cost and own and "untap" not in eff and (
                "draw" in eff or "create" in eff or "damage" in eff or "search your library" in eff or "gain" in eff or "add {" in eff):
            targets = _want(b, card, eff)
            out.append(_payload(card, ab, targets[1] if targets else []))
            continue
        if any(w in cost for w in _BAD_COST):
            continue
        if "target creature" in eff and _saved_by(how, wipe, eff, best, top):
            out.append(_payload(card, ab, [best.id]))
        elif "target" not in eff and card.id in ids and _saved_by(how, wipe, eff, card, top):
            out.append(_payload(card, ab, []))  # ("{1}{G}: Regenerate this creature.")
    return out


def _answer_pump(b: Board, cards: list[Seen], top: Seen) -> list[dict[str, Any]]:
    """Advanced: another player pumps their creature in a fight with its own: instant removal at that creature in response (the pump
    then has no target)."""
    if _kind(top) != "help" or _pump_of(top.text) is None:
        return []
    pumped = [b.cards[x] for x in b.targets.get(top.id, []) if x in b.cards and b.cards[x].controller != b.me
              and (b.cards[x].extra.get("attacking") or b.cards[x].extra.get("blocking"))]
    if not pumped:
        return []
    return _kill_attacker(b, cards, among=pumped)


def _land_score(b: Board, land: Seen) -> tuple[int, int]:
    t = land.text
    tapped = "enters tapped" in t or "enters the battlefield tapped" in t
    makes = {_BASIC_COLOR[s] for s in (land.ch.subtypes if land.ch else ()) if s in _BASIC_COLOR}
    makes |= set(re.findall(r"\{([WUBRG])\}", t)) if "add" in t else set()
    if "any color" in t:
        makes |= set("WUBRG")
    have = set()
    for mine in b.zone(b.me, "battlefield"):
        if mine.land and mine.ch is not None:
            have |= {_BASIC_COLOR[s] for s in mine.ch.subtypes if s in _BASIC_COLOR}
            have |= set(re.findall(r"\{([WUBRG])\}", mine.text))
    need: dict[str, int] = {}
    for c in b.zone(b.me, "hand") + b.zone(b.me, "command"):
        if c.ch is not None and not c.land:
            for sym in re.findall(r"\{([WUBRG])\}", c.ch.mana_cost):
                need[sym] = need.get(sym, 0) + (30 if _lethal(b, c) else 1)  # (the colour of burn that would win: first)
    useful = sum(n * (3 if s not in have else 1) for s, n in need.items() if s in makes)
    return (0 if tapped else 1, useful)


# (abilities)


def _ability(card: Seen, index: Any) -> AbilityText | None:
    """The printed ability ``index`` of ``card`` (an ability a card was granted isn't read: it is left alone)."""
    if card.ch is None:
        return None
    return next((a for a in card.ch.abilities if a.index == index), None)


def _effect(ab: AbilityText) -> str:
    """What an activated or loyalty ability does: its text after the cost, lower case."""
    t = ab.text
    if ab.cost is not None and ":" in t:
        t = t.split(":", 1)[1]
    return t.strip().lower()


def _proxy(card: Seen, text: str) -> Seen:
    """``card`` as one of its abilities reads (so a choice for the ability is scored by what the ability does, not the whole card)."""
    return Seen(card.id, card.name, card.zone, card.holder, card.controller, None, text=text)


def _activating(b: Board, d: dict[str, Any], memory: dict[str, Any]) -> Seen | None:
    """The ability it just activated, as the source of a choice the engine asks for it (a target, a mode)."""
    act = memory.get("activating")
    if not act:
        return None
    src = d.get("source_id")
    card = b.cards.get(act.get("card") or "")
    if card is None or (src and src != card.id):
        return None
    ab = _ability(card, act.get("ability"))
    if ab is None:
        return None
    return _proxy(card, _EQUIP_TEXT if "equip" in ab.keywords else _effect(ab))


def _payload(card: Seen, ab: AbilityText, targets: list[str]) -> dict[str, Any]:
    return {"type": "activate_ability", "card_id": card.id, "ability": ab.index, **({"targets": targets} if targets else {})}


def _fresh(memory: dict[str, Any], cid: str, index: Any) -> bool:
    """May it still activate this ability this turn? (the per-turn ledger: no ability over and over, whatever the stack does)"""
    acts = memory.get("acts") or {}
    return acts.get("total", 0) < TURN_CAP and (acts.get("n") or {}).get(f"{cid}:{index}", 0) < ABILITY_CAP


def _harm_targets(b: Board, source: Seen, eff: str) -> list[str]:
    """The opponents' things (and the opponents, when it may target a player) a harmful ability is worth aiming at, best first."""
    players = any(w in eff for w in ("any target", "target player", "target opponent", "player or planeswalker"))
    creatures = "any target" in eff or _TARGET_CREATURE.search(eff) is not None or "creature or" in eff
    among: list[Any] = []
    if creatures:
        among += [c for c in b.foes_creatures()
                  if "attacking or blocking" not in eff or c.extra.get("attacking") or c.extra.get("blocking")]
    if players:
        among += b.opponents
    return _target_for(b, source, among)


def _want(b: Board, card: Seen, eff: str) -> tuple[int, list[str]] | None:
    """How much it wants an ability that does ``eff`` (3 removal, 2 good, 1 fine), and its targets; None to leave it. Only effects it
    can read: damage and removal at the opponents' things, card draw, tokens, a land search, counters, life, scry (never untapping:
    combos)."""
    if "untap" in eff or "gets +" in eff or "gains " in eff and "life" not in eff:
        return None  # (pumps wait for a fight: :func:`_tricks`)
    source = _proxy(card, eff)
    if _kind_of(eff) == "harm":
        dmg = _damage_text(eff)
        if "target" not in eff:
            return (2, []) if "each opponent" in eff else None
        if "tap target" in eff or dmg is None and ("damage" in eff or _TARGET_CREATURE.search(eff) is None):
            return None
        best = _harm_targets(b, source, eff)
        return (3, best[:1]) if best else None
    if "target" in eff:
        if "target player" in eff and ("draw" in eff or "gain" in eff or "scry" in eff):
            return (2, [b.me])
        if "+1/+1 counter" in eff and "target creature" in eff:
            best = _target_for(b, source, b.creatures(b.me))
            return (1, best[:1]) if best else None
        return None
    if "search your library" in eff and "land" in eff or "draw" in eff or "create" in eff:
        return (2, [])
    if "+1/+1 counter" in eff or "scry" in eff or "surveil" in eff or "gain" in eff and "life" in eff:
        return (1, [])
    return None


def _activations(b: Board, memory: dict[str, Any], when: str) -> list[dict[str, Any]]:
    """Its abilities worth activating now (best first): equip its best creature and planeswalker abilities in its main phases; the
    rest of what :func:`_want` reads in its main phases (a creature's {T} ability after combat) and at instant speed at the end of
    another player's turn. Only what the engine's hints list as activatable now (mana abilities aren't: the payer uses those)."""
    if (memory.get("acts") or {}).get("total", 0) >= TURN_CAP:
        return []
    out: list[tuple[int, int, dict[str, Any]]] = []
    if when in MAIN:
        out += [(4, i, p) for i, p in enumerate(_equips(b, memory))]
    for i, h in enumerate(b.hints.get("activatable") or []):
        card = b.cards.get(h.get("card_id") or "")
        if card is None or card.zone != "battlefield" or card.controller != b.me or not _fresh(memory, card.id, h.get("ability")):
            continue
        ab = _ability(card, h.get("ability"))
        if ab is None:
            continue
        cost = (ab.cost or "").lower()
        eff = _effect(ab)
        x: int | None = None
        if h.get("x"):  # ("{X}, {T}: …": X from the mana it has, at least 1; only a mana X: "Sacrifice X", "-X" are left alone)
            x = _x_most(b, (ab.cost or "").upper().replace("{T}", "")) if ab.kind == "activated" and "{x}" in cost else 0
            if x < 1:
                continue
            eff = _with_x(eff, x)
        found: tuple[int, list[str]] | None
        if ab.kind == "loyalty":
            if when not in MAIN:
                continue
            found = _loyalty(b, card, cost, eff)
        elif ab.kind == "activated":
            if when == "main1" and "{t}" in cost and card.creature:
                continue  # (a creature taps for its ability after combat: it may attack first)
            if any(w in cost for w in _BAD_COST) and not ("search your library" in eff and "land" in eff):
                continue  # (a cost it won't judge: a sacrifice, a discard, life, cards from somewhere)
            found = _want(b, card, eff)
        else:
            continue
        if found is not None:
            out.append((found[0], 100 + i, {**_payload(card, ab, found[1]), **({"x_value": x} if x else {})}))
    out.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, _, p in out]


def _loyalty(b: Board, card: Seen, cost: str, eff: str) -> tuple[int, list[str]] | None:
    """A planeswalker's ability: the best one it reads (removal, cards, tokens), else a plus ability that targets nothing."""
    cost = cost.replace("−", "-").strip()
    have = _num((card.extra.get("counters") or {}).get("loyalty"))
    found = _want(b, card, eff)
    if cost.startswith("-"):
        if _num(cost[1:]) >= have or found is None or found[0] < 2:
            return None  # (never the one that would put it in the graveyard)
        return found
    if found is not None:
        return (found[0] + 1, found[1])
    if cost.startswith("+") and "target opponent" in eff and b.foe is not None and eff.count("target") == 1:
        return (1, [b.foe])
    return (1, []) if cost.startswith("+") and "target" not in eff else None


def _equips(b: Board, memory: dict[str, Any]) -> list[dict[str, Any]]:
    """702.6a: each Equipment of its that isn't on one of its creatures, onto its best creature (one that can attack this turn first).
    Never one already on its creature (so it doesn't move them back and forth)."""
    mine = b.creatures(b.me)
    if not mine:
        return []
    sick = set(b.hints.get("summoning_sick") or ())
    order = sorted(mine, key=lambda c: (c.id in sick, -(c.power * 10 + c.toughness + (50 if c.commander else 0)), c.id))
    out: list[dict[str, Any]] = []
    for eq in b.zone(b.me, "battlefield"):
        if eq.controller != b.me or eq.ch is None or "Equipment" not in eq.ch.subtypes or eq.creature:
            continue
        on = b.cards.get(eq.extra.get("attached_to") or "")
        if on is not None and on.controller == b.me and on.creature:
            continue
        ab = next((a for a in eq.ch.abilities if a.kind == "keywords" and "equip" in a.keywords), None)
        if ab is None or not _fresh(memory, eq.id, ab.index):
            continue
        out += [_payload(eq, ab, [c.id]) for c in order if c.id != eq.id][:2]
    return out


# (combat tricks)


def _fights(b: Board) -> list[tuple[Seen, list[Seen]]]:
    """Its creatures in combat, each with the opposing creatures it fights (an attacker's blockers; a blocker's attackers), the most
    valuable first; an unblocked attacker with none."""
    foes = {c.id: c for c in b.foes_creatures()}
    out: list[tuple[Seen, list[Seen]]] = []
    for m in b.creatures(b.me):
        if m.extra.get("attacking"):
            out.append((m, [f for f in foes.values() if f.extra.get("blocking") == m.id or m.id in (f.extra.get("blocking_more") or ())]))
        elif m.extra.get("blocking"):
            fought = [foes[i] for i in [m.extra["blocking"], *(m.extra.get("blocking_more") or ())] if i in foes]
            if fought:
                out.append((m, fought))
    out.sort(key=lambda f: (-(f[0].power + f[0].toughness + (50 if f[0].commander else 0)), f[0].id))
    return out


def _outcome(m: Seen, foes: list[Seen], n: int = 0, k: int = 0, ind: bool = False) -> tuple[bool, bool]:
    """(does ``m`` die, does it kill one of them) with +n/+k (and indestructible): all their damage on it, all its on one."""
    incoming = sum(max(0, f.power) * (2 if f.has("double strike") else 1) for f in foes)
    dies = not (ind or m.has("indestructible")) and (any(f.has("deathtouch") and f.power > 0 for f in foes) or incoming >= m.toughness + k)
    power = m.power + n
    kills = power > 0 and any(not f.has("indestructible") and (m.has("deathtouch") or power >= f.toughness) for f in foes)
    return dies, kills


def _pump_of(eff: str) -> tuple[int, int, bool] | None:
    """+N/+N and indestructible from a pump's text (a -N anywhere in it: not a pump it reads)."""
    m = _PUMP.search(eff)
    ind = "indestructible" in eff
    if m is None and not ind or "/-" in eff:
        return None
    return (int(m.group(1)), int(m.group(2)), ind) if m else (0, 0, ind)


def _tricks(b: Board, castable: list[Seen], memory: dict[str, Any]) -> list[dict[str, Any]]:
    """After blockers (either player's turn): a pump spell or ability on its creature where it changes the fight (it survives, or it
    kills and survives), or on an unblocked attacker when the extra damage is lethal. Only "target creature" pumps of +N/+N or
    indestructible (or an ability that pumps its own creature), aimed at the creature it picks; nothing otherwise (it passes)."""
    fights = _fights(b)
    if not fights:
        return []
    options: list[tuple[Any, int, int, bool, str | None]] = []  # (the spell or (card, ability), +n, +k, indestructible, only this one)
    for c in sorted(castable, key=lambda c: (c.mv, c.id)):
        instant = c.ch is not None and ("Instant" in c.ch.types or c.has("flash")) and not c.ch.is_permanent_card
        if instant and "target creature" in c.text and "sacrifice" not in c.text and (pump := _pump_of(c.text)) is not None:
            options.append((c, *pump, None))
    for h in b.hints.get("activatable") or []:
        card = b.cards.get(h.get("card_id") or "")
        if card is None or h.get("x") or card.zone != "battlefield" or card.controller != b.me or not _fresh(memory, card.id, h.get("ability")):
            continue
        ab = _ability(card, h.get("ability"))
        if ab is None or ab.kind != "activated" or any(w in (ab.cost or "").lower() for w in _BAD_COST):
            continue
        eff = _effect(ab)
        if "untap" in eff or (pump := _pump_of(eff)) is None:
            continue
        if "target creature" in eff:
            options.append(((card, ab), *pump, None))
        elif "target" not in eff and not (card.creature and "{t}" in (ab.cost or "").lower()):
            options.append(((card, ab), *pump, card.id))  # (it pumps itself: only for its own fight)
    life = {p: b.life(p) for p in b.opponents}
    unblocked = [m for m, foes in fights if not foes and m.extra.get("attacking")]
    out: list[dict[str, Any]] = []
    for what, n, k, ind, only in options:
        for m, foes in fights:
            if only is not None and m.id != only:
                continue
            if foes:
                before, after = _outcome(m, foes), _outcome(m, foes, n, k, ind)
                worth = before[0] and not after[0] or not before[1] and after[1] and not after[0]
            elif m.extra.get("attacking"):
                at = (m.extra.get("attacking") or {}).get("id")
                hits = sum(u.power * (2 if u.has("double strike") else 1) for u in unblocked if (u.extra.get("attacking") or {}).get("id") == at)
                worth = n > 0 and at in life and hits < life[at] <= hits + n * (2 if m.has("double strike") else 1)
            else:
                worth = False
            if not worth:
                continue
            if isinstance(what, Seen):
                out.append({"type": "cast_spell", "card_id": what.id, "targets": [m.id]})
            else:
                card, ab = what
                out.append(_payload(card, ab, [] if only is not None else [m.id]))
            break
    return out


# (targets)


def _target_for(b: Board, source: Seen | None, among: list[Seen] | list[str]) -> list[str]:
    """``among`` (cards or player ids) best first for ``source``'s targets: harmful at the opponents' biggest threats (burn at the player
    when lethal, else at the biggest creature it kills), helpful at its own best creature."""
    kind = _kind(source)
    dmg = _damage(source)
    scored: list[tuple[float, str]] = []
    score: float
    for x in among:
        if isinstance(x, str):  # a player
            mine = x == b.me
            if kind == "help":
                score = 5 if mine else -50
            elif mine:
                score = -100
            else:
                human = not b.players[x].get("dummy") and b.players[x].get("bot") is None
                lethal = dmg is not None and b.life(x) <= dmg
                score = (1000 if lethal else 40 if dmg is not None else 1) + (10 if human else 0)
            scored.append((score, x))
            continue
        mine = x.controller == b.me
        if kind == "help":
            score = (x.power * 10 + x.toughness + (50 if x.commander else 0)) if mine and x.creature else -100
        elif mine:
            score = -100 - x.power
        else:
            c, p, mv = _threat(x)
            score = c * 500 + p * 10 + mv + (5 if x.creature else 0)
            if b.level >= INTERMEDIATE:  # (threat: an engine, a planeswalker)
                score += (15 if "whenever" in x.text or "{t}:" in x.text.replace("{t}: add", "") else 0) + (30 if x.ch is not None and "Planeswalker" in x.ch.types else 0)
            if dmg is not None and x.creature:
                score = score + 200 if x.toughness <= dmg else score - 300
        scored.append((score, x.id))
    scored.sort(key=lambda s: -s[0])
    return [x for s, x in scored if s > -100]


def _answer(b: Board, d: dict[str, Any], info: CardInfo, memory: dict[str, Any]) -> list[dict[str, Any]]:
    kind = d.get("kind")
    if kind == "declare_attackers":
        return [*_attacks(b, d), {"type": "declare_attackers"}]
    if kind == "declare_blockers":
        return [*(_blocks(b, d) if b.level < INTERMEDIATE else _blocks_smart(b, d)), {"type": "declare_blockers"}]
    options: list[dict[str, Any]] = d.get("options") or []
    display = d.get("display") or {}
    choose = lambda ids, **more: {"type": "choose", "decision_id": d["id"], "option_ids": ids, **more}  # noqa: E731
    ids = [o["id"] for o in options if o.get("group") != "seen"]
    if display.get("kind") in ("payment", "tap_mana") and "pay" in ids:
        return [choose(["pay"]), *_fallback(d, info)]
    if kind == "divide":
        return [*_divide(b, d), *_fallback(d, info)]
    if kind == "choose_one" and "keep" in ids and str(d.get("prompt") or "").startswith("Copy of "):  # 707.10c: a copy's target, kept or changed
        return [choose([_copy_target(b, d, options)]), *_fallback(d, info)]
    if b.level >= INTERMEDIATE and (modes := _modes_answer(b, d)) is not None:
        return [*modes, *_fallback(d, info)]
    targetish = [o for o in options if o.get("group") != "seen" and (o.get("card_id") in b.cards or o["id"] in b.players)]
    if targetish and len(targetish) == len(ids) and kind in ("choose_cards", "choose_one"):
        source = _activating(b, d, memory) or b.cards.get(d.get("source_id") or "") or b.cards.get(memory.get("casting") or "")
        among: list[Any] = [b.cards[o["card_id"]] if o.get("card_id") in b.cards else o["id"] for o in targetish]
        best = _target_for(b, source, among)
        need = max(1, int(d.get("min_choices") or 0))
        most = int(d.get("max_choices") or need)
        if source is not None and "divided" in source.text:  # (at least 1 each, 601.2d: never more targets than it has damage to divide)
            split = _damage(source) if "x damage" not in source.text else None
            most = min(most, split) if split is not None else need
        prompt = str(d.get("prompt") or "")
        out = []
        if b.level >= INTERMEDIATE and most > need and len(best) > need and "target" in prompt and _kind(source) in ("harm", "help"):
            out.append(choose(best[:most]))  # (several targets: as many as are worth it, up to the most it may choose)
        if len(best) >= need:
            out.append(choose(best[:need]))
            out += [choose([x]) for x in best[1:3] if need == 1]
        return [*out, *_fallback(d, info)]
    return _fallback(d, info)


def _copy_target(b: Board, d: dict[str, Any], options: list[dict[str, Any]]) -> str:
    """-- playtest (nov 17) -- a copy's new target (707.10c: "Copy of Giant Growth: keep its target or choose a new one"): it keeps the
    target unless another is clearly better. A pump moves only to its own creature in a fight the pump changes (it put Riku's copy of
    Giant Growth on Riku, out of combat, for Riku's commander bonus); a harmful copy moves to a target it scores above the one it has."""
    prompt = str(d.get("prompt") or "")
    name = prompt[len("Copy of "):].split(":", 1)[0] if prompt.startswith("Copy of ") else ""
    spell = next((c for c in b.cards.values() if c.zone == "stack" and c.name == name), None)
    keep = next((o for o in options if o["id"] == "keep"), {})
    current = keep.get("card_id")
    others = [o for o in options if o["id"] != "keep" and o.get("group") != "seen"]
    kind = _kind(spell)
    if kind == "help":
        pump = _pump_of(spell.text) if spell is not None else None
        if pump is None:
            return "keep"
        offered = {o.get("card_id") or o["id"] for o in others}
        for m, foes in _fights(b):
            if m.id == current or m.id not in offered:
                continue
            if foes:
                before, after = _outcome(m, foes), _outcome(m, foes, *pump)
                if before[0] and not after[0] or not before[1] and after[1] and not after[0]:
                    return m.id
        return "keep"
    if kind == "harm" and current is not None:  # (a player it targets: kept, it can't weigh them against each other here)
        among: list[Any] = [b.cards.get(x, x) for x in [current, *(o.get("card_id") or o["id"] for o in others)]
                            if x in b.cards or x in b.players]
        best = _target_for(b, spell, among)
        if best and best[0] != current and any((o.get("card_id") or o["id"]) == best[0] for o in others):
            return next(o["id"] for o in others if (o.get("card_id") or o["id"]) == best[0])
    return "keep"


def _fallback(d: dict[str, Any], info: CardInfo) -> list[dict[str, Any]]:
    """The target dummy's answers (its smallest, app/game/dummy.py), read from the decision as this seat is shown it."""
    from app.game import dummy

    try:
        dec = Decision(id=d["id"], player=d.get("player") or "", kind=d["kind"], prompt=str(d.get("prompt") or "")[:300],
                       options=[DecisionOption(**{k: o.get(k) for k in ("id", "label", "card_id", "group")}) for o in d.get("options") or []],
                       min_choices=int(d.get("min_choices") or 0), max_choices=int(d.get("max_choices") or 0),
                       source_id=d.get("source_id"), display=d.get("display"))
    except (ValidationError, KeyError):
        return []
    if dec.kind == "divide":
        return []
    return dummy.answers(dec, info=info)


def _divide(b: Board, d: dict[str, Any]) -> list[dict[str, Any]]:
    """601.2d / 510.1c-d: a division, from what the decision shows (any amount: a power may reach 2^31-1). Damage: lethal damage to each
    creature it can kill, the most valuable first (a blocker's lethal damage as the prompt counts it, 1 with deathtouch), then the rest
    to what a trampler attacks once every blocker has lethal damage (702.19b), else to a player among the targets, else to the first it
    kills. Counters: as evenly as it may. Then, in case the engine refuses that, the even split (at least the least share each). Every
    level: a division is never left unanswered."""
    disp = d.get("display") or {}
    options = d.get("options") or []
    total, n = _num(disp.get("total")), len(options)
    least = _num(disp.get("least", 1)) if disp.get("least") is not None else 1
    if not n or total < least * n:
        return []
    free = disp.get("free") if isinstance(disp.get("free"), int) and 0 <= disp["free"] < n else None
    need_shown = [_num(x) for x in disp.get("need") or []]
    ids = [o.get("card_id") or o["id"] for o in options]
    rows = [i for i in range(n) if i != free]

    def even() -> list[int]:
        amounts = [least] * n
        spare = total - least * n
        each, extra = divmod(spare, len(rows)) if rows else (0, spare)
        for i in rows:
            amounts[i] += each
        amounts[rows[0] if rows else 0] += extra
        return amounts

    plans: list[list[int]] = []
    if disp.get("what") != "counters":
        amounts = [least] * n
        left = total - least * n

        def need(i: int) -> int | None:
            if i < len(need_shown):
                return need_shown[i]
            c = b.cards.get(ids[i])
            if c is None or not c.creature and not (c.ch is not None and "Planeswalker" in c.ch.types):
                return None  # (a player: what is left over)
            if not c.creature:
                return max(1, _num((c.extra.get("counters") or {}).get("loyalty")))
            return max(1, c.toughness - _num(c.extra.get("damage")))

        kill = sorted((i for i in rows if need(i) is not None and (b.cards.get(ids[i]) is None or b.cards[ids[i]].controller != b.me)),
                      key=lambda i: (-_worth(b.cards[ids[i]]) if ids[i] in b.cards else 0, i))
        for i in kill:
            want = max(0, (need(i) or 0) - amounts[i])
            if want <= left:
                amounts[i] += want
                left -= want
        if left:
            lethal_all = all(amounts[i] >= (need(i) or 0) for i in rows if i < len(need_shown))
            players = [i for i in rows if need(i) is None]
            spot = free if free is not None and lethal_all else players[0] if players else (kill or rows or [0])[0]
            amounts[spot] += left
        plans.append(amounts)
    plans.append(even())
    out: list[dict[str, Any]] = []
    for p in plans:
        if sum(p) == total and all(x >= least for x in p) and not any(o["amounts"] == p for o in out):
            out.append({"type": "choose", "decision_id": d["id"], "option_ids": [], "amounts": p})
    return out


# (combat)


def _flies(c: Seen) -> bool:
    return c.has("flying")


def _can_block(blocker: Seen, attacker: Seen) -> bool:
    if "can't be blocked" in attacker.text or attacker.has("menace") or attacker.has("shadow"):
        return False
    return not (_flies(attacker) and not (_flies(blocker) or blocker.has("reach")))


def _kills(source: Seen, victim: Seen) -> bool:
    if victim.has("indestructible"):
        return False
    return source.power > 0 and (source.has("deathtouch") or source.power >= victim.toughness)


# -- combat maths (Intermediate and Advanced) -- first strike and double strike (510.4), deathtouch (702.2c), trample (702.19b), menace
# (702.111b), flying and reach (702.9b, 702.17b), indestructible (702.12b) and an attacker's damage divided among its blockers, lethal
# damage to each in turn (510.1c). Simple keeps its old reading (above).


def _legal_block(x: Seen, a: Seen) -> bool:
    """May ``x`` block ``a`` as far as it can tell (509.1b; menace is a matter of how many block it: :func:`_unblockable`)."""
    if "can't be blocked" in a.text and "except" not in a.text or "this creature can't block" in x.text:
        return False
    if a.has("shadow") != x.has("shadow"):
        return False
    return not (_flies(a) and not (_flies(x) or x.has("reach")))


def _unblockable(a: Seen, blockers: list[Seen]) -> bool:
    able = [x for x in blockers if _legal_block(x, a)]
    return not able or a.has("menace") and len(able) < 2


def _hits(c: Seen, plus: int = 0) -> int:
    return max(0, c.power + plus) * (2 if c.has("double strike") else 1)


def _strikes(c: Seen, step: str) -> bool:
    """Does ``c`` deal combat damage in this step (510.4: first strike and double strike in the first, the rest and double strike after)."""
    first = c.has("first strike") or c.has("double strike")
    return first if step == "first" else (not c.has("first strike") or c.has("double strike"))


def _worth(c: Seen) -> float:
    """What a creature is worth on the table, to weigh a trade or a chump."""
    kw = sum(1 for k in ("flying", "deathtouch", "lifelink", "first strike", "double strike", "trample", "indestructible", "hexproof")
             if c.has(k))
    return max(0, c.power) + max(0, c.toughness) + c.mv / 2 + kw + (8 if c.commander else 0)


def _clash(a: Seen, blockers: list[Seen], plus: tuple[int, int, bool] = (0, 0, False),
           guard: tuple[str, int, int, bool] | None = None) -> tuple[bool, list[Seen], int]:
    """510: ``a`` attacks, blocked by ``blockers`` (none: unblocked), with +n/+k (and indestructible) on it from ``plus`` and on the blocker
    ``guard`` names. (does ``a`` die, which blockers die, the damage through to what it attacks). Each step deals its damage at once; the
    attacker assigns lethal damage to its blockers in the order given (1 with deathtouch), then a trampler the rest to what it attacks;
    a creature blocked by creatures that all died assigns none (510.1a) unless it tramples."""
    n, k, ind = plus
    power = max(0, a.power + n)
    a_ind = ind or a.has("indestructible")
    a_tough = a.toughness + k
    a_marked = _num(a.extra.get("damage"))
    tough = [x.toughness + (guard[2] if guard and guard[0] == x.id else 0) for x in blockers]
    bpow = [max(0, x.power + (guard[1] if guard and guard[0] == x.id else 0)) for x in blockers]
    b_ind = [x.has("indestructible") or bool(guard and guard[0] == x.id and guard[3]) for x in blockers]
    marked = [_num(x.extra.get("damage")) for x in blockers]
    alive = [True] * len(blockers)
    a_alive, through = True, 0
    for step in ("first", "regular"):
        hit_a, touched = 0, False
        for i, x in enumerate(blockers):
            if alive[i] and _strikes(x, step) and bpow[i] > 0:
                hit_a += bpow[i]
                touched = touched or x.has("deathtouch")
        dealt = [0] * len(blockers)
        if a_alive and _strikes(a, step) and power > 0:
            if not blockers:
                through += power
            else:
                live = [i for i in range(len(blockers)) if alive[i]]
                left = power
                for i in live:
                    give = min(left, 1 if a.has("deathtouch") else max(0, tough[i] - marked[i]))
                    dealt[i] += give
                    left -= give
                if left and a.has("trample"):
                    through += left
                elif left and live:
                    dealt[live[0]] += left  # (else 510.1a: blocked, its blockers gone, no trample: no damage)
        for i in range(len(blockers)):
            marked[i] += dealt[i]
            if alive[i] and not b_ind[i] and (marked[i] >= tough[i] or dealt[i] and a.has("deathtouch")):
                alive[i] = False
        a_marked += hit_a
        if a_alive and not a_ind and (a_marked >= a_tough or hit_a and touched):
            a_alive = False
    return not a_alive, [x for i, x in enumerate(blockers) if not alive[i]], through


def _attack_plan_smart(b: Board, attackers: list[Seen], target: str, blockers: list[Seen]) -> tuple[bool, float, list[Seen]]:
    """Intermediate and Advanced: each creature no legal block kills (one blocker; a menace attacker two), and everything when what gets
    through the defender's best blocks (each blocker on the biggest attacker it can block, a trampler's excess over it) is lethal."""
    def safe(a: Seen) -> bool:
        able = [x for x in blockers if _legal_block(x, a)]
        if _unblockable(a, blockers):
            return True
        if a.has("menace"):
            top = sorted(able, key=lambda x: (-x.power, x.id))[:5]
            return not any(_clash(a, [x, y])[0] for i, x in enumerate(top) for y in top[i + 1:])
        return not any(_clash(a, [x])[0] for x in able)

    chosen = [a for a in attackers if safe(a)]
    every = sorted(attackers, key=lambda c: (-_hits(c), c.id))
    free, through = list(blockers), 0
    for a in every:
        if _unblockable(a, free):
            through += _hits(a)
            continue
        able = sorted((x for x in free if _legal_block(x, a)), key=lambda x: (-x.toughness, x.id))
        take = able[:2 if a.has("menace") else 1]
        for x in take:
            free.remove(x)
        if a.has("trample"):
            through += _clash(a, take)[2]
    lethal = target in b.players and through >= b.life(target) > 0
    if lethal:
        chosen = every
    expect = sum(_hits(c) * (1 if _unblockable(c, blockers) else 0.5) for c in chosen)
    return lethal, expect, chosen


def _blocks_smart(b: Board, d: dict[str, Any]) -> list[dict[str, Any]]:
    """Intermediate and Advanced blocks, from the combat maths: a block that kills the attacker and survives, a trade up, a wall that
    takes no loss; two blockers on an attacker none kills alone when the pair kills it for less than it is worth (Advanced; a menace
    attacker needs two at any level); then chump blocks only while the damage coming (a trampler's excess counted) is lethal."""
    from itertools import combinations

    options = d.get("options") or []
    blockers = [b.cards[o["id"][2:]] for o in options if o["id"].startswith("b:") and o["id"][2:] in b.cards]
    attackers = [b.cards[o["id"][2:]] for o in options if o["id"].startswith("a:") and o["id"][2:] in b.cards]
    if not blockers or not attackers:
        return []
    life = b.life(b.me)
    free = list(blockers)
    plan: dict[str, list[Seen]] = {}
    order = sorted(attackers, key=lambda c: (-_worth(c), c.id))
    for a in order:  # (one blocker that wins, trades up, or walls it for free)
        if a.has("menace"):
            continue
        able = [x for x in free if _legal_block(x, a)]
        good, trade, wall = [], [], []
        for x in able:
            dies, dead, _ = _clash(a, [x])
            if dies and not dead:
                good.append(x)
            elif dies and _worth(x) < _worth(a):
                trade.append(x)
            elif not dead and not dies and _hits(a) > 0:
                wall.append(x)
        pick = min(good or trade or wall, key=lambda x: (_worth(x), x.id)) if good or trade or wall else None
        if pick is not None:
            plan[a.id] = [pick]
            free.remove(pick)
    for a in order:  # (two on one)
        if a.id in plan or not (b.level >= ADVANCED or a.has("menace")):
            continue
        able = sorted((x for x in free if _legal_block(x, a)), key=lambda x: (_worth(x), x.id))[:6]
        best: tuple[float, list[Seen]] | None = None
        for x, y in combinations(able, 2):
            pair = sorted([x, y], key=lambda c: (-_worth(c), c.id))  # (it kills the more valuable first)
            dies, dead, _ = _clash(a, pair)
            loss = sum(_worth(c) for c in dead)
            if dies and loss < _worth(a) and (best is None or loss < best[0]):
                best = (loss, pair)
        if best is not None:
            plan[a.id] = best[1]
            for x in best[1]:
                free.remove(x)
    good_blocks = {a: list(xs) for a, xs in plan.items()}

    def coming() -> int:
        return sum(_clash(a, plan[a.id])[2] if a.id in plan else _hits(a) for a in attackers)

    while coming() >= life:  # chump only while the damage coming is lethal: where a chump saves the most
        best_chump: tuple[int, str, list[Seen]] | None = None
        for a in attackers:
            if a.id in plan:
                continue
            able = sorted((x for x in free if _legal_block(x, a)), key=lambda x: (_worth(x), x.id))
            need = 2 if a.has("menace") else 1
            if len(able) < need:
                continue
            chumps = able[:need]
            saved = _hits(a) - _clash(a, chumps)[2]
            if saved > 0 and (best_chump is None or saved > best_chump[0]):
                best_chump = (saved, a.id, chumps)
        if best_chump is None:
            break
        plan[best_chump[1]] = best_chump[2]
        for x in best_chump[2]:
            free.remove(x)

    def declare(p: dict[str, list[Seen]]) -> dict[str, Any]:
        return {"type": "declare_blockers", "blocks": [{"blocker_id": x.id, "attacker_id": a} for a, xs in p.items() for x in xs]}

    tries = [declare(plan)] if plan else []
    if good_blocks and good_blocks != plan:
        tries.append(declare(good_blocks))
    singles = {a: xs for a, xs in plan.items() if len(xs) == 1}
    if singles and singles != plan:
        tries.append(declare(singles))
    tries += [declare({a: xs}) for a, xs in list(plan.items())[:3] if len(plan) > 1]
    return tries


def _attack_plan(b: Board, attackers: list[Seen], target: str) -> tuple[bool, float, list[Seen]]:
    """Its attack at ``target``: (lethal, the damage it expects through, the attackers). Each creature that no untapped blocker could
    kill (or that can't be blocked), everything when that is lethal even if the biggest are blocked."""
    defender = target if target in b.players else (b.cards[target].controller if target in b.cards else target)
    blockers = [c for c in b.creatures(defender) if not c.tapped]
    if b.level >= INTERMEDIATE:
        return _attack_plan_smart(b, attackers, target, blockers)
    chosen = [a for a in attackers if not any(_kills(x, a) for x in blockers if _can_block(x, a))]
    every = sorted(attackers, key=lambda c: (-c.power, c.id))
    unblocked = sum(c.power * (2 if c.has("double strike") else 1) for c in every[len(blockers):])
    lethal = target in b.players and unblocked >= b.life(target) > 0
    if lethal:
        chosen = every
    through = sum(c.power * (1 if not any(_can_block(x, c) for x in blockers) else 0.5) for c in chosen)
    return lethal, through, chosen


def _hold_back(b: Board, chosen: list[Seen]) -> list[Seen]:
    """-- crack-back -- keep home what it needs so the opponents' creatures can't kill it on their turn (each creature it keeps home
    stops one of theirs, the biggest first; its attackers stay tapped through their turn, vigilance aside)."""
    chosen = list(chosen)
    life = b.life(b.me)
    powers = sorted((max(0, c.power) * (2 if c.has("double strike") else 1) for c in b.foes_creatures()), reverse=True)
    home = [c for c in b.creatures(b.me) if not c.tapped and (c not in chosen or c.has("vigilance"))]
    while chosen and sum(powers[len(home):]) >= life:
        keep = [c for c in chosen if not c.has("vigilance")]
        if not keep:
            break
        stay = max(keep, key=lambda c: (c.toughness, c.power, c.id))
        chosen.remove(stay)
        home.append(stay)
    return chosen


def _attacks(b: Board, d: dict[str, Any]) -> list[dict[str, Any]]:
    options = d.get("options") or []
    attackers = [b.cards[o["id"][2:]] for o in options if o["id"].startswith("a:") and o["id"][2:] in b.cards]
    targets = [o["id"][2:] for o in options if o["id"].startswith("t:")]
    if not attackers or not targets:
        return []
    players = [p for p in b.opponents if p in targets]
    if b.level >= INTERMEDIATE and players:
        # the opponent it does the most to (Advanced: one it kills first), the one with less life, the human first on a tie
        plans = {p: _attack_plan(b, attackers, p) for p in players}
        target = max(players, key=lambda p: (b.level >= ADVANCED and plans[p][0], plans[p][1], -b.life(p), -players.index(p)))
        lethal, _, chosen = plans[target]
        if not lethal:
            chosen = _hold_back(b, chosen)
    else:
        target = next(iter(players), targets[0])
        lethal, _, chosen = _attack_plan(b, attackers, target)
    defender = target if target in b.players else (b.cards[target].controller if target in b.cards else target)
    blockers = [c for c in b.creatures(defender) if not c.tapped]

    def declare(group: list[Seen]) -> dict[str, Any]:
        return {"type": "declare_attackers", "attackers": [{"card_id": c.id, "target": target} for c in group]}

    tries = [declare(chosen)] if chosen else []
    evasive = [c for c in chosen if not any(_can_block(x, c) for x in blockers)] if b.level < INTERMEDIATE else \
        [c for c in chosen if _unblockable(c, blockers)]
    if evasive and len(evasive) < len(chosen):
        tries.append(declare(evasive))
    return tries


def _blocks(b: Board, d: dict[str, Any]) -> list[dict[str, Any]]:
    options = d.get("options") or []
    blockers = [b.cards[o["id"][2:]] for o in options if o["id"].startswith("b:") and o["id"][2:] in b.cards]
    attackers = [b.cards[o["id"][2:]] for o in options if o["id"].startswith("a:") and o["id"][2:] in b.cards]
    if not blockers or not attackers:
        return []
    life = b.life(b.me)
    free = list(blockers)
    plan: dict[str, Seen] = {}  # attacker id -> blocker
    for a in sorted(attackers, key=lambda c: -c.power):
        able = [x for x in free if _can_block(x, a)]
        good = [x for x in able if _kills(x, a) and not _kills(a, x)]
        trade = [x for x in able if _kills(x, a) and _kills(a, x) and (x.mv < a.mv or (x.power + x.toughness < a.power + a.toughness))]
        pick = min(good, key=lambda x: (x.mv, x.power)) if good else min(trade, key=lambda x: (x.mv, x.power)) if trade else None
        if pick is not None:
            plan[a.id] = pick
            free.remove(pick)

    def coming() -> int:
        return sum(a.power * (2 if a.has("double strike") else 1) for a in attackers
                   if a.id not in plan or a.has("trample"))

    good_blocks = dict(plan)
    for a in sorted(attackers, key=lambda c: -c.power):  # chump only when the damage coming is lethal
        if coming() < life:
            break
        if a.id in plan:
            continue
        able = [x for x in free if _can_block(x, a)]
        if able:
            pick = min(able, key=lambda x: (x.power + x.toughness, x.mv))
            plan[a.id] = pick
            free.remove(pick)

    def declare(p: dict[str, Seen]) -> dict[str, Any]:
        return {"type": "declare_blockers", "blocks": [{"blocker_id": x.id, "attacker_id": a} for a, x in p.items()]}

    tries = [declare(plan)] if plan else []
    if good_blocks and good_blocks != plan:
        tries.append(declare(good_blocks))
    tries += [declare({a: x}) for a, x in list(plan.items())[:3] if len(plan) > 1]
    return tries
