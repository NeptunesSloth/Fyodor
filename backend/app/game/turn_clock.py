"""-- turn clock (stage 3) -- who the engine is waiting on, and charging them a buffer then a bank on server monotonic time.

A pure model: no hub, save or UI here. ``waiting_on`` reads the table; ``TurnClock`` keeps each player's bank (saved) and the running
waits (in memory only), and only ``sync``/``hold``/``add_time``/``extend_grace``/``give_up``/``mark_acted`` change it.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator

from app.game.autoseat import non_human
from app.game.control import controller_of, decider_of
from app.game.state import GameState

log = logging.getLogger(__name__)

AtZero = Literal["act", "show"]
MAX_BANK = 14400.0
MAX_GRACE_EXTRA = 3600.0
MAX_BANKS = 12


class ClockSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: bool = False
    bank_seconds: int = Field(1500, ge=60, le=7200)
    buffer_seconds: int = Field(30, ge=5, le=300)
    at_zero: AtZero = "act"
    grace_seconds: int = Field(120, ge=30, le=1800)


def waiting_on(state: GameState) -> dict[str, str]:
    """Each charged human seat -> its wait key, in seat order. Nobody while automation is off, paused or the game is over."""
    r = state.rules
    if r is None or state.settings.automation == "off" or r.paused or r.winner is not None or r.draw_reason is not None:
        return {}

    def charged(pid: str) -> bool:
        p = state.players[pid]
        return not (non_human(state, pid) or p.left or pid in r.conceded or pid in r.lost)

    pregame = state.pregame
    if pregame is not None and not pregame.finished:
        out: dict[str, str] = {}
        for pid in state.seat_order:
            seat = pregame.seats.get(pid)
            if seat is not None and seat.status in ("deciding", "bottoming") and charged(pid):
                out[pid] = f"m:{seat.status}:{seat.mulligans}"
        return out
    if r.decision is not None:
        pid = decider_of(state, r.decision)  # 723.5: the controller makes the controlled player's decisions
        return {pid: f"d:{r.decision.id}"} if pid in state.players and charged(pid) else {}
    if r.priority is None:
        return {}
    pid = controller_of(state, r.priority)  # 723.5 again, for the priority decision
    if pid not in state.players or not charged(pid):
        return {}
    stack = state.zones.get("stack", [])
    # 117.3b-d: a new priority (after a resolution, an action taken, a pass) gives a new key; other players' acts and refusals do not
    return {pid: f"p:{state.turn.number}:{state.turn.phase}:{len(stack)}:{stack[-1] if stack else ''}:{len(r.passed)}"}


class _Wait:
    __slots__ = ("key", "last", "buffer", "run")

    def __init__(self, key: str, last: float, buffer: float, run: bool) -> None:
        self.key, self.last, self.buffer, self.run = key, last, buffer, run


class TurnClock(BaseModel):
    settings: ClockSettings = Field(default_factory=lambda: ClockSettings.model_validate({}))
    banks: dict[str, float] = Field(default_factory=dict)

    _waits: dict[str, _Wait] = PrivateAttr(default_factory=dict)
    _held: bool = PrivateAttr(default=False)
    _anyone: bool = PrivateAttr(default=False)  # somebody connected at the last sync
    _away_since: dict[str, float] = PrivateAttr(default_factory=dict)
    _grace_extra: dict[str, float] = PrivateAttr(default_factory=dict)
    _gave_up: set[tuple[str, str]] = PrivateAttr(default_factory=set)
    _acted: dict[str, int] = PrivateAttr(default_factory=dict)

    @field_validator("banks")
    @classmethod
    def _banks_ok(cls, v: dict[str, float]) -> dict[str, float]:
        if len(v) > MAX_BANKS or any(not 0.0 <= b <= MAX_BANK for b in v.values()):
            raise ValueError("bank out of range")
        return v

    # -- reading (never changes anything) --

    def _bank0(self, pid: str) -> float:
        return self.banks.get(pid, float(self.settings.bank_seconds))

    def _exempt(self, pid: str, now: float) -> bool:
        since = self._away_since.get(pid)
        return since is not None and now - since < self.settings.grace_seconds + self._grace_extra.get(pid, 0.0)

    def _project(self, pid: str, w: _Wait, now: float) -> tuple[float, float]:
        """(buffer, bank) of a wait as of ``now``, from its last settle."""
        buf, bank = w.buffer, self._bank0(pid)
        if self.settings.on and w.run and not self._held:
            e = max(0.0, now - w.last)
            used = min(buf, e)
            buf -= used
            bank = max(0.0, bank - (e - used))
        return buf, bank

    def bank(self, pid: str, now: float) -> float:
        w = self._waits.get(pid)
        return self._project(pid, w, now)[1] if w is not None else self._bank0(pid)

    def due(self, now: float) -> list[str]:
        if not self.settings.on or self.settings.at_zero != "act" or self._held or not self._anyone:
            return []
        out = []
        for pid, w in self._waits.items():
            buf, bank = self._project(pid, w, now)
            if buf <= 0.0 and bank <= 0.0 and not self._exempt(pid, now) and (pid, w.key) not in self._gave_up:
                out.append(pid)
        return out

    def next_event(self, now: float) -> float | None:
        if not self.settings.on or self._held:
            return None
        times: list[float] = []
        for pid, w in self._waits.items():
            since = self._away_since.get(pid)
            if since is not None and self._exempt(pid, now):
                times.append(since + self.settings.grace_seconds + self._grace_extra.get(pid, 0.0))
            elif self.settings.at_zero == "act" and w.run and self._anyone and (pid, w.key) not in self._gave_up:
                times.append(w.last + w.buffer + self._bank0(pid))
        return min(times) if times else None

    def public(self, now: float, sent_at: float) -> dict[str, Any]:
        s = self.settings
        out: dict[str, Any] = {"settings": s.model_dump(), "sent_at": sent_at}
        if s.on:
            players: dict[str, Any] = {}
            for pid in sorted(set(self.banks) | set(self._waits)):
                w = self._waits.get(pid)
                buf = round(self._project(pid, w, now)[0], 1) if w is not None else None
                players[pid] = {"bank": round(self.bank(pid, now), 1), "buffer": buf,
                                "running": bool(w and w.run and not self._held), "away": pid in self._away_since}
            out["players"] = players
        return out

    def dump(self, now: float) -> dict[str, Any]:
        return {"settings": self.settings.model_dump(), "banks": {pid: self.bank(pid, now) for pid in self.banks}}

    @classmethod
    def load(cls, data: object) -> TurnClock | None:
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            log.warning("turn clock not loaded: %s", e)
            return None

    def acted_revision(self, pid: str) -> int | None:
        return self._acted.get(pid)

    # -- changing --

    def _settle(self, now: float) -> None:
        for pid, w in self._waits.items():
            if self.settings.on and w.run and not self._held:
                buf, bank = self._project(pid, w, now)
                w.buffer, self.banks[pid] = buf, bank
            w.last = now

    def sync(self, waiting: dict[str, str], connected: set[str], now: float) -> None:
        self._settle(now)
        self._held = False
        if not self.settings.on:
            self._waits.clear()
            self._gave_up.clear()
            return
        self._anyone = bool(connected)
        old, self._waits = self._waits, {}
        for pid, key in waiting.items():
            self.banks.setdefault(pid, float(self.settings.bank_seconds))
            if pid in connected:
                self._away_since.pop(pid, None)
                self._grace_extra.pop(pid, None)
            else:
                self._away_since.setdefault(pid, now)
            w = old.get(pid)
            buf = w.buffer if w is not None and w.key == key else float(self.settings.buffer_seconds)
            self._waits[pid] = _Wait(key, now, buf, self._anyone and not self._exempt(pid, now))
        for pid in [p for p in self._away_since if p not in waiting]:  # (only the waited-on are away)
            del self._away_since[pid]
            self._grace_extra.pop(pid, None)
        self._gave_up = {(p, k) for p, k in self._gave_up if waiting.get(p) == k}

    def hold(self, now: float) -> None:
        self._settle(now)
        self._held = True

    def add_time(self, pid: str, seconds: float, now: float) -> float:
        w = self._waits.get(pid)
        cur = self._project(pid, w, now)[1] if w is not None else self._bank0(pid)
        if w is not None:
            self._settle(now)
        self.banks[pid] = min(MAX_BANK, cur + seconds)
        return self.banks[pid]

    def extend_grace(self, pid: str, seconds: float) -> None:
        self._grace_extra[pid] = min(MAX_GRACE_EXTRA, self._grace_extra.get(pid, 0.0) + seconds)

    def give_up(self, pid: str) -> None:
        w = self._waits.get(pid)
        if w is not None:
            self._gave_up.add((pid, w.key))

    def mark_acted(self, pid: str, revision: int) -> None:
        self._acted[pid] = revision
