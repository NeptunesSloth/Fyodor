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
* Otherwise it passes; at instant speed it only casts a creature with flash at the end of another player's turn.

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

log = logging.getLogger(__name__)

MAX_PER_WINDOW = 24  # actions in one priority window (a turn's step, as the stack stands) before it only passes
MAX_TRIES = 6
MAIN = ("main1", "main2")
_DAMAGE = re.compile(r"deals? (\d+) damage")
_HARM = ("destroy", "exile target", "damage", "gets -", "-1/-1", "return target", "tap target", "can't block", "fights", "counter target spell",
         "sacrifice")
_HELP = ("gets +", "+1/+1 counter", "gains ", "untap target", "hexproof", "indestructible")
_DRAW_RAMP = ("draw", "search your library", "add {", "put a land", "lands you control")
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
    try:
        tries = decide(observe(state, pid, info), info, memory)
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
                                   (ch.oracle_text if ch else "").lower(), {"creature": st.get("creature")})

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
    t = c.text
    if any(w in t for w in _HARM):
        return "harm"
    if any(w in t for w in _HELP):
        return "help"
    return ""


def _damage(c: Seen | None) -> int | None:
    m = _DAMAGE.search(c.text) if c is not None else None
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
    if memory["count"] >= MAX_PER_WINDOW or not b.hints.get("has_priority"):
        return [{"type": "pass_priority"}]
    return [*_plays(b, memory), {"type": "pass_priority"}]


def _remember(memory: dict[str, Any], state: GameState, payload: dict[str, Any]) -> None:
    memory["count"] = memory.get("count", 0) + 1
    if payload.get("card_id"):
        memory.setdefault("tried", []).append(payload["card_id"])


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
    if not b.my_turn:  # instant speed: only a creature with flash, at the end of another player's turn
        if b.phase == "end" and stack_empty:
            flash = [b.cards[c] for c in castable if b.cards[c].creature and b.cards[c].has("flash")]
            return [_cast(b, c, memory) for c in sorted(flash, key=lambda c: -c.mv)][:2]
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
    return out[: MAX_TRIES]


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
        source = b.cards.get(d.get("source_id") or "") or b.cards.get(memory.get("casting") or "")
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
