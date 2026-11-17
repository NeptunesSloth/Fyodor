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
STOPS_MINE = ("main1", "main2", "declare_blockers")  # (where it takes priority: :func:`_stops`)
STOPS_THEIRS = ("declare_blockers", "end")
_DAMAGE = re.compile(r"deals? (\d+) damage")
_HARM = ("destroy", "exile target", "damage", "gets -", "-1/-1", "return target", "tap target", "can't block", "fights", "counter target spell",
         "sacrifice")
_HELP = ("gets +", "+1/+1 counter", "gains ", "untap target", "hexproof", "indestructible")
_DRAW_RAMP = ("draw", "search your library", "add {", "put a land", "lands you control")
_PUMP = re.compile(r"gets \+(\d+)/\+(\d+)")
_BAD_COST = ("sacrifice", "discard", "pay ", "life", "exile", "return", "remove", "put ", "untapped", "reveal")
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
            self.cards[cid] = Seen(cid, c.get("name") or "", zone, holder, c.get("controller") or "", ch, bool(c.get("tapped")),
                                   power, tough, frozenset(k.lower() for k in kws), bool(c.get("commander_key")),
                                   (ch.oracle_text if ch else "").lower(),
                                   {"creature": st.get("creature"), "attacking": c.get("attacking"), "blocking": c.get("blocking"),
                                    "blocking_more": list(c.get("blocking_more") or ()), "attached_to": c.get("attached_to"),
                                    "counters": dict(c.get("counters") or {})})

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
    return [*_plays(b, memory), {"type": "pass_priority"}]


def _stops(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Its own stops (a player's preference, set once through the same intent a player sends): besides its main phases, the declare
    blockers step (a trick once the blocks are known; the step only happens when creatures attack) and the end of another player's
    turn (instant-speed abilities and flash). Otherwise the engine passes for it there and it never gets the chance."""
    prefs = (view.get("rules") or {}).get("prefs") or {}
    if not prefs:
        return []
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
        if seat.get("mulligans", 0) == 0 and not 2 <= len(lands) <= 5:
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
    castable = [cid for cid in b.hints.get("castable") or [] if cid in b.cards and cid not in tried]
    stack_empty = not b.view.get("stack")
    if b.phase == "declare_blockers" and stack_empty:  # (blocks are known: a trick that wins or saves a fight, either player's turn)
        return _tricks(b, [b.cards[c] for c in castable], memory)[:MAX_TRIES]
    if not b.my_turn:  # instant speed: a creature with flash and its instant-speed abilities, at the end of another player's turn
        if b.phase == "end" and stack_empty:
            flash = [b.cards[c] for c in castable if b.cards[c].creature and b.cards[c].has("flash")]
            return [*[_cast(b, c, memory) for c in sorted(flash, key=lambda c: -c.mv)][:2], *_activations(b, memory, "end")][:MAX_TRIES]
        return []
    if b.phase not in MAIN or not stack_empty:
        return []
    out: list[dict[str, Any]] = []
    lands = [b.cards[c] for c in b.hints.get("playable_lands") or [] if c in b.cards and c not in tried]
    if lands:
        best = max(lands, key=lambda land: _land_score(b, land))
        out.append({"type": "play_land", "card_id": best.id})
    cards = [b.cards[c] for c in castable]
    commanders = [c for c in cards if c.commander and c.zone == "command"]
    permanents = sorted((c for c in cards if c not in commanders and c.ch is not None and c.ch.is_permanent_card and not c.land),
                        key=lambda c: (-c.mv, not c.creature))
    spells = sorted((c for c in cards if c.ch is not None and c.ch.is_instant_or_sorcery and _worth_casting(b, c)), key=lambda c: -c.mv)
    lethal = [c for c in spells if _lethal(b, c)]  # (burn that wins the game: first)
    for c in [*lethal, *commanders, *permanents, *(c for c in spells if c not in lethal)]:
        if c.ch is not None and "Aura" in c.ch.subtypes and not _target_for(b, c, b.creatures(b.me) + b.foes_creatures()):
            continue
        out.append(_cast(b, c, memory))
    # (then its abilities: after the spells, so the mana goes to the spells first; the list stays short enough that the pass is tried)
    return [*out[: MAX_TRIES], *_activations(b, memory, b.phase)[:3]]


def _cast(b: Board, c: Seen, memory: dict[str, Any]) -> dict[str, Any]:
    memory["casting"] = c.id
    return {"type": "cast_spell", "card_id": c.id}


def _worth_casting(b: Board, c: Seen) -> bool:
    """An instant or sorcery worth casting in its main phase: card draw and ramp, removal with an opposing creature to hit, burn that
    kills something (or the player). Pump and tricks wait (it doesn't cast them)."""
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


def _lethal(b: Board, c: Seen) -> bool:
    dmg = _damage(c)
    return _kind(c) == "harm" and dmg is not None and "target" in c.text and b.foe is not None and b.life(b.foe) <= dmg


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
    creatures = "any target" in eff or "target creature" in eff or "creature or" in eff
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
        if "tap target" in eff or dmg is None and ("damage" in eff or "target creature" not in eff):
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
        if card is None or h.get("x") or card.zone != "battlefield" or card.controller != b.me or not _fresh(memory, card.id, h.get("ability")):
            continue
        ab = _ability(card, h.get("ability"))
        if ab is None:
            continue
        cost = (ab.cost or "").lower()
        eff = _effect(ab)
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
            out.append((found[0], 100 + i, _payload(card, ab, found[1])))
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
        return [*_blocks(b, d), {"type": "declare_blockers"}]
    options: list[dict[str, Any]] = d.get("options") or []
    display = d.get("display") or {}
    choose = lambda ids, **more: {"type": "choose", "decision_id": d["id"], "option_ids": ids, **more}  # noqa: E731
    ids = [o["id"] for o in options if o.get("group") != "seen"]
    if display.get("kind") in ("payment", "tap_mana") and "pay" in ids:
        return [choose(["pay"]), *_fallback(d, info)]
    if kind == "divide":
        return [*_divide(b, d), *_fallback(d, info)]
    targetish = [o for o in options if o.get("group") != "seen" and (o.get("card_id") in b.cards or o["id"] in b.players)]
    if targetish and len(targetish) == len(ids) and kind in ("choose_cards", "choose_one"):
        source = _activating(b, d, memory) or b.cards.get(d.get("source_id") or "") or b.cards.get(memory.get("casting") or "")
        among: list[Any] = [b.cards[o["card_id"]] if o.get("card_id") in b.cards else o["id"] for o in targetish]
        best = _target_for(b, source, among)
        need = max(1, int(d.get("min_choices") or 0))
        out = []
        if len(best) >= need:
            out.append(choose(best[:need]))
            out += [choose([x]) for x in best[1:3] if need == 1]
        return [*out, *_fallback(d, info)]
    return _fallback(d, info)


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
    """601.2d: as evenly as it may (at least one each), the rest on the first."""
    total = _num((d.get("display") or {}).get("total"))
    n = len(d.get("options") or [])
    if not n or total < n:
        return []
    amounts = [total // n] * n
    amounts[0] += total - sum(amounts)
    return [{"type": "choose", "decision_id": d["id"], "option_ids": [], "amounts": amounts}]


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


def _attacks(b: Board, d: dict[str, Any]) -> list[dict[str, Any]]:
    options = d.get("options") or []
    attackers = [b.cards[o["id"][2:]] for o in options if o["id"].startswith("a:") and o["id"][2:] in b.cards]
    targets = [o["id"][2:] for o in options if o["id"].startswith("t:")]
    if not attackers or not targets:
        return []
    order = b.opponents
    target = next((p for p in order if p in targets), targets[0])
    defender = target if target in b.players else (b.cards[target].controller if target in b.cards else target)
    blockers = [c for c in b.creatures(defender) if not c.tapped]
    chosen: list[Seen] = []
    for a in attackers:
        able = [x for x in blockers if _can_block(x, a)]
        if not able or not any(_kills(x, a) for x in able):
            chosen.append(a)
    every = sorted(attackers, key=lambda c: -c.power)
    unblocked = sum(c.power * (2 if c.has("double strike") else 1) for c in every[len(blockers):])
    if target in b.players and unblocked >= b.life(target) > 0:
        chosen = every  # (lethal even if the biggest are blocked: everything)

    def declare(group: list[Seen]) -> dict[str, Any]:
        return {"type": "declare_attackers", "attackers": [{"card_id": c.id, "target": target} for c in group]}

    tries = [declare(chosen)] if chosen else []
    evasive = [c for c in chosen if not any(_can_block(x, c) for x in blockers)]
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
