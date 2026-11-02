"""Soak: whole Commander games through the rules engine at the Full automation level, with real decks (development tool).

    python -m tools.soak --db ../data/cards.sqlite --games 20 --turns 12 --seed 1 --players 4

Each seat plays like a person at the table: it reads its own view (the JSON the client receives) and picks, with a seeded RNG,
among the moves the engine offers it — the hints (playable lands, castable spells, activatable abilities), the pending decision
and its options (targets, modes, payments, attackers, blockers) — and sends the client's payloads through ``GameSession.perform``.
Mulligans: one free mulligan for a hand of 0-1 or 6-7 lands, else keep. Now and then a seat presses Undo. The seats alternate the two
real decks in ``tests/fixtures/soak_decks``.

Checks: no AutomationError and no unexpected exception; an ActionError for a move the hints offered is a hint/engine mismatch;
every ``CHECK_EVERY`` actions and at the end of each game the history replays to the same table and a save loads back to it (play
then goes on from the loaded table); every seat's view hides the other seats' hands and libraries (the fingerprints of
tests/test_protocol_privacy.py). Some moves the client lets a player put together are checked by the server as a whole (a block
plan, an X, several cards that must share a land type): a refusal of those is expected, counted in the report, and the seat tries
a smaller one. Game ``i`` uses seed ``--seed + i``, so ``--seed <that> --games 1`` replays it exactly (with the same code).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import random
import re
import secrets
import sys
import time
import traceback
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.decks.parser import parse_deck_text
from app.game import resolve as resolve_module
from app.game.control import decider_of
from app.game.errors import ActionError, AutomationError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.mulligan import resolve_policy
from app.game.rules_state import AUTOMATION_PRESETS, start_rules
from app.game.session import GameSession
from app.game.state import GameSettings, GameState
from app.game.visibility import can_see
from app.rules.casting import mana_abilities, pool_covers
from app.rules.mana import parse_cost
from app.storage.saves import load_payload

DECKS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "soak_decks"
DECK_FILES = ("kiora_underdasea.txt", "adrix_nev_super_clons.txt")
CHECK_EVERY = 50  # actions between replay / save-load / privacy checks
UNDO_CHANCE = 0.01  # how often a player takes back the move they just made
MAX_ACTIONS_PER_TURN = 400  # a turn that runs longer is reported as stuck
NAME_OPTION, NUMBER_OPTION = "__name__", "__number__"  # frontend RulesHud: a typed card name / number
KICKER = re.compile(r"^(?:multi)?kicker (?:\{[^}]+\})+$", re.I)  # frontend rulesMenu: a plain kicker line (cast with kicker: 1)


@dataclass
class Problem:
    kind: str
    seed: int
    turn: int
    seq: int
    actor: str
    action: dict[str, Any]
    detail: str

    def signature(self) -> str:
        last = [line for line in self.detail.strip().splitlines() if line.strip()]
        return f"{self.kind}: {re.sub(r'[0-9a-f]{12}', '#', last[-1] if last else '')}"

    def text(self) -> str:
        head = f"[{self.kind}] seed {self.seed}, turn {self.turn}, seq {self.seq}, {self.actor}: {json.dumps(self.action)[:400]}"
        return head + "\n" + "\n".join("    " + line for line in self.detail.rstrip().splitlines())


@dataclass
class Report:
    games: int = 0
    turns: int = 0
    actions: int = 0
    seconds: float = 0.0
    problems: list[Problem] = field(default_factory=list)
    refused: Counter[str] = field(default_factory=Counter)  # moves the client offers but the server checks (illegal block plans)
    outcomes: Counter[str] = field(default_factory=Counter)
    moves: Counter[str] = field(default_factory=Counter)  # accepted moves by kind
    manual: Counter[str] = field(default_factory=Counter)  # "resolve it by hand" prompts (every card of both decks is FULL)
    decks: dict[str, DeckUse] = field(default_factory=dict)  # what each deck actually did: no errors means little if a deck never got going
    digests: list[str] = field(default_factory=list)  # --digest: one line per game (moves made, final table)

    def text(self) -> str:
        lines = [f"games {self.games}, turns {self.turns}, actions {self.actions}, {self.seconds:.0f}s",
                 "outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(self.outcomes.items())),
                 "moves: " + ", ".join(f"{k} {v}" for k, v in self.moves.most_common())]
        if self.manual:
            lines.append("resolve-by-hand prompts: " + "; ".join(f"{k} ×{v}" for k, v in self.manual.most_common(10)))
        if self.refused:
            lines.append("refused client-offered moves (expected): "
                         + "; ".join(f"{k} ×{v}" for k, v in self.refused.most_common(10)))
        if self.decks:
            lines.append("what each deck did:")
            lines += [use.text(name) for name, use in self.decks.items()]
        groups: dict[str, list[Problem]] = {}
        for p in self.problems:
            groups.setdefault(p.signature(), []).append(p)
        lines.append(f"problems: {len(self.problems)} ({len(groups)} distinct)")
        for same in groups.values():
            more = f" (×{len(same)}, seeds {sorted({p.seed for p in same})})" if len(same) > 1 else ""
            lines.append(same[0].text() + more)
        return "\n".join(lines)


@dataclass
class DeckUse:
    """One deck's games: how far it got (its commander cast, the turns its seat took) and the cards it cast and activated."""

    seated: int = 0
    commander_cast: int = 0
    max_lands: int = 0
    cast: Counter[str] = field(default_factory=Counter)
    activated: Counter[str] = field(default_factory=Counter)

    def text(self, name: str) -> str:
        top = ", ".join(f"{n} ×{k}" for n, k in self.cast.most_common(8))
        used = ", ".join(f"{n} ×{k}" for n, k in self.activated.most_common(5))
        return (f"  {name}: {self.seated} games, commander cast {self.commander_cast}×, at most {self.max_lands} lands, "
                f"{sum(self.cast.values())} spells ({len(self.cast)} different), {sum(self.activated.values())} abilities "
                f"({len(self.activated)} different)\n    cast: {top or '-'}\n    activated: {used or '-'}")


class CachedCards:
    """The card database with each printing read once (CardRepository.get looks for image files on every call)."""

    def __init__(self, repo: CardRepository) -> None:
        self.repo = repo
        self.cache: dict[str, dict[str, Any] | None] = {}

    def get(self, card_id: str) -> dict[str, Any] | None:
        if card_id not in self.cache:
            self.cache[card_id] = self.repo.get(card_id)
        return self.cache[card_id]

    def resolve(self, name: str, set_code: str | None = None, collector_number: str | None = None) -> dict[str, Any] | None:
        return self.repo.resolve(name, set_code, collector_number)

    def close(self) -> None:
        self.repo.close()


def load_deck(cards: CachedCards, path: Path) -> list[DeckCard]:
    out = []
    for e in parse_deck_text(path.read_text("utf-8")).entries:
        found = cards.resolve(e.name, e.set_code, e.collector_number)
        if found is None:
            raise ValueError(f"{path.name}: {e.name} is not in the card database")
        out.append(DeckCard(e.section, e.quantity, found["name"], found["id"]))
    return out


@contextlib.contextmanager
def deterministic(seed: int) -> Iterator[random.Random]:
    """Seed the engine's randomness (shuffles, new ids, random choices) so one seed replays one game exactly. Set iteration
    order also matters: ``main`` re-runs itself with PYTHONHASHSEED=0."""
    engine = random.Random(f"engine:{seed}")
    ids = random.Random(f"ids:{seed}")
    saved = (secrets.SystemRandom, secrets.token_hex, dict(resolve_module.resolve.__kwdefaults__ or {}))

    def token_hex(nbytes: int | None = None) -> str:
        k = 32 if nbytes is None else nbytes
        return ids.getrandbits(8 * k).to_bytes(k, "big").hex()

    secrets.SystemRandom = lambda *_: engine  # type: ignore[assignment,misc]
    secrets.token_hex = token_hex
    resolve_module.resolve.__kwdefaults__ = {**saved[2], "rng": engine}
    try:
        yield engine
    finally:
        secrets.SystemRandom, secrets.token_hex = saved[0], saved[1]  # type: ignore[misc]
        resolve_module.resolve.__kwdefaults__ = saved[2]


def new_session(cards: CachedCards, decks: list[list[DeckCard]], players: int, rng: random.Random,
                engine: random.Random) -> GameSession:
    setups = [PlayerSetup(f"Seat {i + 1}", cards=decks[i % len(decks)]) for i in range(players)]
    settings = GameSettings(starting_life=40, mulligan=resolve_policy("commander_london"), priority_helper="off",
                            automation="full", automation_options=AUTOMATION_PRESETS["full"].model_copy())
    state = new_game(setups, name="Soak", settings=settings, shuffle=True, first_player=rng.randrange(players), rng=engine)
    start_rules(state)
    return GameSession(state, cards=cards)


def game_over(state: GameState) -> str | None:
    r = state.rules
    if r is None:
        return "automation off"
    if r.winner:
        return "won"
    if r.draw_reason:
        return "draw"
    alive = [p for p in state.seat_order if p not in r.lost and p not in r.conceded]
    return "everyone lost" if not alive else None


# ---------------------------------------------------------------------------------------------- the bot
class Bot:
    """Chooses one move for whoever must act, from that seat's own view."""

    def __init__(self, session: GameSession, cards: CachedCards, rng: random.Random) -> None:
        self.session, self.cards, self.rng = session, cards, rng
        self.names = sorted({c.name for c in session.state.cards.values() if c.name})
        self.oracle: dict[str, str] = {}
        self.fewer_blocks = False  # the last block plan was refused: try a smaller one
        self.fewer_picks = False  # the last multi-pick answer was refused: pick as few as allowed
        self.on_manual: Any = None
        self.last_decision: dict[str, Any] = {}
        self.paying: dict[str, bool] = {}  # decision id -> whether this seat decided to pay that optional cost

    def next_move(self, *, fallback: bool = False) -> tuple[str, dict[str, Any], str]:
        """(actor, payload, how): how is "hint" (offered by the engine), "decision" or "client" (offered by the client UI only).
        ``fallback``: the last move was refused, so with priority just pass (a decision is answered again at random)."""
        state = self.session.state
        pre = state.pregame
        if pre is not None and not pre.finished:
            for pid in state.seat_order:
                seat = pre.seats.get(pid)
                if seat is not None and seat.status == "deciding":  # one (free) mulligan for a hand of 0-1 or 6-7 lands
                    lands = sum("Land" in ((self.cards.get(state.cards[c].card_id or "") or {}).get("type_line") or "")
                                for c in state.zones[f"{pid}:hand"])
                    take = seat.mulligans == 0 and not 2 <= lands <= 5
                    return pid, {"type": "mulligan_take" if take else "mulligan_keep"}, "client"
                if seat is not None and seat.status == "bottoming":
                    hand = state.zones[f"{pid}:hand"]
                    return pid, {"type": "mulligan_bottom", "card_ids": hand[: seat.to_bottom]}, "client"
        r = state.rules
        assert r is not None
        if r.decision is not None:
            who = decider_of(state, r.decision)
            d = self.last_decision = self.session.view(who)["rules"]["decision"]
            if d["kind"] == "manual_resolution" and self.on_manual is not None:
                self.on_manual(d["prompt"])
            return who, self.answer(who, d), "decision"
        if r.priority is None:
            raise RuntimeError("nobody has priority and nothing is being decided")
        pid = r.priority
        if fallback:
            return pid, {"type": "pass_priority"}, "client"
        return (pid, *self.priority_move(pid, self.session.view(pid)))

    # -- priority -------------------------------------------------------------------------------------------
    def priority_move(self, pid: str, view: dict[str, Any]) -> tuple[dict[str, Any], str]:
        h = view["rules"]["hints"]
        rng = self.rng
        if h.get("playable_lands") and rng.random() < 0.9:
            return {"type": "play_land", "card_id": rng.choice(h["playable_lands"])}, "hint"
        spells: list[dict[str, Any]] = []
        for cid in h.get("castable", []):
            cast: dict[str, Any] = {"type": "cast_spell", "card_id": cid}
            if cid in h.get("x_cast", []):
                cast["x_value"] = rng.randint(0, 6)
            if any(KICKER.match(line) for line in self.lines(view, cid)) and rng.random() < 0.4:
                cast["kicker"] = 1
                if cid in h.get("x_kicker", []):
                    cast["x_value"] = rng.randint(0, 4)
            spells.append(cast)
        spells += [{"type": "cast_spell", "card_id": cid, "free": True} for cid in h.get("free_castable", [])]
        spells += [{"type": "cast_spell", "card_id": cid, "alt_cost": alt["id"]}
                   for cid, alts in h.get("alt_castable", {}).items() for alt in alts]
        spells += [{"type": "cast_spell", "card_id": cid, "optional_costs": [opt["id"]]}
                   for cid, opts in h.get("optional_costs", {}).items() for opt in opts]
        abilities = [{"type": "activate_ability", "card_id": a["card_id"], "ability": a["ability"],
                      **({"x_value": rng.randint(0, 5)} if a.get("x") else {})} for a in h.get("activatable", [])]
        mine = self.session.state.turn.active_player == pid
        # (an X the seat picks is the client's number prompt, not part of the hint: "x" moves the server may refuse, e.g. Doppelgang's
        # "X target permanents" with fewer permanents)
        if spells and rng.random() < (0.8 if mine else 0.3):
            move = rng.choice(spells)
            return move, "x" if "x_value" in move else "hint"
        if abilities and rng.random() < (0.5 if mine else 0.2):
            move = rng.choice(abilities)
            return move, "x" if "x_value" in move else "hint"
        stack = self.session.state.zones.get("stack")
        if rng.random() < (0.04 if stack else 0.015):  # the HUD's other pass buttons: Resolve one / Resolve all with a stack, End turn without
            return {"type": "pass_priority", "until": rng.choice(["stack_changes", "stack_empty"] if stack else ["next_turn"])}, "client"
        return {"type": "pass_priority"}, "client"

    def lines(self, view: dict[str, Any], cid: str) -> list[str]:
        """The card's ability lines, the way the client reads them (frontend abilityLines)."""
        printing = (view["cards"].get(cid) or {}).get("card_id")
        if not printing:
            return []
        if printing not in self.oracle:
            data = self.cards.get(printing) or {}
            self.oracle[printing] = data.get("oracle_text") or (data.get("faces") or [{}])[0].get("oracle_text") or ""
        return [re.sub(r"\s*\([^()]*\)", "", line).strip() for line in self.oracle[printing].split("\n") if line.strip()]

    # -- decisions ------------------------------------------------------------------------------------------
    def answer(self, who: str, d: dict[str, Any]) -> dict[str, Any]:
        rng = self.rng
        options = d.get("options") or []
        ids = [o["id"] for o in options]
        choose: dict[str, Any] = {"type": "choose", "decision_id": d["id"]}
        display = d.get("display") or {}
        kind = d["kind"]
        if kind == "declare_attackers":
            targets = [i[2:] for i in ids if i.startswith("t:")]
            attackers = [i[2:] for i in ids if i.startswith("a:")]
            go = rng.random() < 0.6
            return {"type": "declare_attackers", "attackers": [
                {"card_id": a, "target": rng.choice(targets)} for a in attackers if go and rng.random() < 0.6]}
        if kind == "declare_blockers":
            blockers = [i[2:] for i in ids if i.startswith("b:")]
            attackers = [i[2:] for i in ids if i.startswith("a:")]
            p, self.fewer_blocks = (0.15 if self.fewer_blocks else 0.4), False
            return {"type": "declare_blockers", "blocks": [
                {"blocker_id": b, "attacker_id": rng.choice(attackers)} for b in blockers if rng.random() < p]}
        if display.get("kind") == "tap_mana":
            return self.tap_mana(who, d, display)
        if "pay" in ids and kind == "choose_one":  # "Pay {1}?", ward's "pay {2} or … is countered": tap mana first, then Pay
            label = next(o["label"] for o in options if o["id"] == "pay")
            return self.optional_cost(who, d, str(display.get("cost") or re.sub(r"^Pay ", "", label)))
        if d.get("cancelable") and rng.random() < 0.03:
            return {**choose, "option_ids": ["cancel"]}
        if ids and ids[0] == NAME_OPTION:
            return {**choose, "option_ids": [], "name": rng.choice(self.names)}
        if ids and ids[0] == NUMBER_OPTION:
            return {**choose, "option_ids": [], "name": str(rng.randint(0, 5))}
        if kind == "divide":
            return {**choose, "option_ids": [], "amounts": self.divide(options, display)}
        if kind == "order":
            return {**choose, "option_ids": rng.sample(ids, len(ids))}
        if kind == "reconcile":
            groups: dict[str, list[str]] = {}
            for o in options:
                groups.setdefault(o.get("group") or o["id"], []).append(o["id"])
            return {**choose, "option_ids": [rng.choice(g) for g in groups.values()]}
        picks = [o["id"] for o in options if o.get("group") != "seen"]
        if kind == "choose_one" and "tap your mana first" in str(d.get("prompt") or "") and any(i.startswith("x:") for i in picks):
            # "pay any amount of mana" (Minds Aglow's join forces): an amount needs that mana in the pool first; the bot pays nothing
            picks = [i for i in picks if not i.startswith("x:") or i == "x:0"] or picks
        if kind in ("choose_one", "confirm", "manual_resolution"):
            return {**choose, "option_ids": [rng.choice(picks)] if picks else []}
        lo, hi = d.get("min_choices", 1), min(d.get("max_choices", 1), len(picks))
        if self.fewer_picks:
            hi, self.fewer_picks = max(min(lo, hi), min(hi, 1)), False
        chosen = rng.sample(picks, rng.randint(min(lo, hi), hi))
        weights = {o["id"]: o["label"].split(" — ")[0].count("{P}") for o in options}
        if picks and all(weights.get(i) for i in picks):  # the Seasons: "up to five {P} worth of modes", each mode's {P} on its label (700.2d)
            budget = d.get("max_choices", 1) * min(weights.values())
            while sum(weights[i] for i in chosen) > budget:
                chosen.pop(rng.randrange(len(chosen)))
        return {**choose, "option_ids": chosen}

    def divide(self, options: list[dict[str, Any]], display: dict[str, Any]) -> list[int]:
        """601.2d / 510.1: at least ``least`` each (a trampler's blockers: lethal damage first, 702.19b), the rest at random."""
        total, least = int(display.get("total", 0)), int(display.get("least", 1))
        lethal = list(display.get("lethal") or [])
        amounts = [lethal[i] if i < len(lethal) else least for i in range(len(options))]
        if sum(amounts) > total:  # (not enough for every blocker: the client's prefill, in order)
            amounts, left = [], total
            for i in range(len(options)):
                amounts.append(min(left, lethal[i] if i < len(lethal) else least))
                left -= amounts[-1]
        for _ in range(max(0, total - sum(amounts))):
            amounts[self.rng.randrange(len(options))] += 1
        return amounts

    def mana_sources(self, who: str) -> list[str]:
        state = self.session.state
        return [cid for cid in state.zones.get(f"{who}:battlefield", []) if not state.cards[cid].tapped
                and state.cards[cid].controller == who and mana_abilities(state, state.cards[cid], self.session.cards)]  # type: ignore[arg-type]

    def optional_cost(self, who: str, d: dict[str, Any], cost_text: str) -> dict[str, Any]:
        """"Pay {1}? (tap your mana first)": decide once; to pay, tap mana sources (any of yours, as the client lets you click
        them) until the pool covers the cost, then Pay; with nothing left to tap, don't."""
        choose = {"type": "choose", "decision_id": d["id"]}
        decline = next(o["id"] for o in d["options"] if o["id"] != "pay")
        if self.paying.setdefault(d["id"], self.rng.random() < 0.6) is False:
            return {**choose, "option_ids": [decline]}
        state = self.session.state
        try:
            cost = parse_cost(cost_text)
        except Exception:  # noqa: BLE001 - not a plain mana cost: just answer
            return {**choose, "option_ids": ["pay"]}
        if pool_covers(state, who, cost, None, self.session.cards):
            return {**choose, "option_ids": ["pay"]}
        sources = self.mana_sources(who)
        if not sources:
            return {**choose, "option_ids": [decline]}
        cid = self.rng.choice(sources)
        found = mana_abilities(state, state.cards[cid], self.session.cards)  # type: ignore[arg-type]
        return {"type": "activate_ability", "card_id": cid, "ability": found[0][0]}

    def tap_mana(self, who: str, d: dict[str, Any], display: dict[str, Any]) -> dict[str, Any]:
        """Tap one of the offered mana sources (the client's tapForMana: the permanent's first mana ability); cancel when
        there is nothing left to tap. The engine goes on by itself once the pool covers the cost."""
        state = self.session.state
        untapped = [cid for cid in display.get("sources", []) if cid in state.cards and not state.cards[cid].tapped]
        if untapped and self.rng.random() < 0.98:
            cid = self.rng.choice(untapped)
            found = mana_abilities(state, state.cards[cid], self.session.cards)  # type: ignore[arg-type]
            if found:
                return {"type": "activate_ability", "card_id": cid, "ability": found[0][0]}
        if "remaining" in display and not display["remaining"]:
            return {"type": "choose", "decision_id": d["id"], "option_ids": ["pay"]}
        return {"type": "choose", "decision_id": d["id"], "option_ids": ["cancel"]}


# ---------------------------------------------------------------------------------------------- checks
CLOCK_KEYS = frozenset({"ts", "created_at", "updated_at", "at"})  # wall-clock times: not part of a game's outcome


def table_digest(state: GameState) -> str:
    """--digest: a short hash of the whole table (rules state, log and all) with the wall-clock times left out, to compare two runs of
    the same seeds (e.g. before and after a speed-up)."""
    def strip(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if k not in CLOCK_KEYS}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v
    return hashlib.sha256(json.dumps(strip(state.model_dump(mode="json")), sort_keys=True).encode()).hexdigest()[:16]


def replay_and_reload(session: GameSession) -> GameSession:
    """The history replays to the table, and a save (state + history, as SaveRepository writes it) loads back to it."""
    now = session.state.model_dump(mode="json")
    if session.history.rebuild().model_dump(mode="json") != now:
        raise AssertionError("the history doesn't replay to the table")
    payload = json.loads(json.dumps({"state": now, "history": session.history.to_dict()}))
    state, history = load_payload(payload)
    if history is None:
        raise AssertionError("the saved history doesn't replay to the saved table (the load dropped it)")
    if state.model_dump(mode="json") != now:
        raise AssertionError("the loaded table differs from the saved one")
    return GameSession(state, cards=session.cards, history=history)


class Privacy:
    """Every seat's view hides the other seats' hands and libraries: no fingerprint of a hidden card (its id, name, printing,
    Oracle text… — tests/test_protocol_privacy.py) appears outside the log, unless a card the viewer may see shares it or has it in
    its own text (a copy of Council of Reeds says "At the beginning of combat on your turn,", as Helm of the Host does)."""

    def __init__(self, cards: CachedCards) -> None:
        helpers = importlib.import_module("tests.test_protocol_privacy")
        self.fingerprints, self.hidden_keys = helpers.fingerprints, helpers.HIDDEN_KEYS
        self.cards = cards

    def check(self, session: GameSession, viewer: str, view: dict[str, Any] | None = None) -> None:
        state = session.state
        view = view if view is not None else session.view(viewer)
        body = {k: v for k, v in view.items() if k != "log"}
        text = json.dumps(body)
        seen: set[str] = set()
        public: list[str] = []  # the texts of the cards the viewer may see
        hidden = []
        for c in state.cards.values():
            if can_see(state, c, viewer):
                seen.update(self.fingerprints(c, self.cards))
                data = self.cards.get(c.card_id) if c.card_id else None
                public += [(data or {}).get("oracle_text") or "", *((f.get("oracle_text") or "") for f in (data or {}).get("faces", [])),
                           c.token.text if c.token is not None else ""]
            elif c.owner != viewer and c.zone.split(":")[-1] in ("hand", "library"):
                hidden.append(c)
                if c.commander_key:  # 903.3: who the commander is is public (the commander list shows it, not which hidden card it is)
                    seen.update(t for t in self.fingerprints(c, self.cards) if t != c.id)
        shown = "\n".join(public)
        # a hidden card's name inside a longer visible one ("Badgermole" in "Badgermole Cub") isn't a leak: take the visible texts out first
        scrubbed = text
        for known in sorted((t for t in seen if len(t) > 3), key=len, reverse=True):
            scrubbed = scrubbed.replace(known, "")
        for c in hidden:
            keywords = {k.lower() for k in ((self.cards.get(c.card_id) or {}).get("keywords") or [])} if c.card_id else set()
            for token in self.fingerprints(c, self.cards):
                if keywords and all(part.strip().lower() in keywords for part in token.split(",")):
                    continue  # (a first line that is only keywords, "Indestructible": any public marker or reminder may say the word)
                if token not in seen and token not in shown and token in scrubbed:
                    raise AssertionError(f"{viewer} sees {token!r} of {c.name} in {c.zone}")
        for card_view in body.get("cards", {}).values():
            if card_view.get("hidden") and card_view["zone"].split(":")[1] in ("hand", "sideboard", "foretell") \
                    and set(card_view) != self.hidden_keys:
                raise AssertionError(f"{viewer}'s view of a hidden card has {sorted(card_view)}")
        d = (body.get("rules") or {}).get("decision")
        if d and state.rules and state.rules.decision and decider_of(state, state.rules.decision) != viewer and "options" in d:
            raise AssertionError(f"{viewer} sees the options of another player's decision")


# ---------------------------------------------------------------------------------------------- one game
class Game:
    """One seeded game: the bot plays it move by move, every failure is recorded (the engine changed nothing: play goes on with
    another move), and the table is checked every CHECK_EVERY actions and at the end."""

    def __init__(self, cards: CachedCards, decks: list[list[DeckCard]], seed: int, players: int, report: Report,
                 privacy: Privacy, *, log: bool = False, names: list[str] | None = None) -> None:
        self.cards, self.seed, self.report, self.privacy, self.log = cards, seed, report, privacy, log
        self.rng = random.Random(f"bot:{seed}")
        self.engine = random.Random(f"engine:{seed}")
        self.decks, self.players = decks, players
        self.names = names or [f"deck {i + 1}" for i in range(len(decks))]
        self.actor, self.payload = "", dict[str, Any]()
        self.failed = False
        self.trace = hashlib.sha256()  # --digest: every accepted move (and undo), in order

    def problem(self, kind: str, detail: str) -> None:
        self.failed = True
        s = self.session.state
        self.report.problems.append(Problem(kind, self.seed, s.turn.number, s.seq, self.actor, self.payload, detail))
        if self.log:
            print(self.report.problems[-1].text(), file=sys.stderr)

    def play(self, turns: int) -> None:
        with deterministic(self.seed) as engine:
            self.session = new_session(self.cards, self.decks, self.players, self.rng, engine)
            self.bot = Bot(self.session, self.cards, self.rng)
            self.bot.on_manual = lambda prompt: self.report.manual.update([re.sub(r"[0-9a-f]{12}", "#", prompt)[:120]])
            for pid in self.session.state.seat_order:  # each player's own preferences (players always tap their own mana)
                self.session.perform(pid, {"type": "set_prefs", "response": self.rng.choice(["auto", "auto", "on"]),
                                           "auto_resolve_own_triggers": self.rng.choice(["safe", "safe", "off", "on"]),
                                           "auto_target": self.rng.random() < 0.7, "hold_priority": self.rng.random() < 0.2})
            for pid in self.session.state.seat_order:
                self.use(pid).seated += 1
            outcome = self.loop(turns)
            if outcome not in ("crashed", "stuck") and not self.check():
                outcome = "crashed"
        self.report.games += 1
        self.report.turns += min(self.session.state.turn.number, turns)
        self.report.outcomes[outcome] += 1
        self.report.digests.append(f"seed {self.seed}: {outcome}, turn {self.session.state.turn.number}, seq {self.session.state.seq}, "
                                   f"moves {self.trace.hexdigest()[:16]}, table {table_digest(self.session.state)}")

    def loop(self, turns: int) -> str:
        since_check, turn_actions, last_turn = 0, 0, 0
        while True:
            state = self.session.state
            over = game_over(state)
            if over or state.turn.number > turns:
                return over or "turn limit"
            if state.turn.number != last_turn:
                last_turn, turn_actions = state.turn.number, 0
            if turn_actions > MAX_ACTIONS_PER_TURN:
                self.problem("stuck", f"more than {MAX_ACTIONS_PER_TURN} actions in one turn")
                return "stuck"
            if not self.step():
                return "stuck"
            self.report.actions += 1
            turn_actions += 1
            since_check += 1
            if since_check >= CHECK_EVERY:
                since_check = 0
                if not self.check():
                    return "crashed"

    def step(self) -> bool:
        """One accepted move. A refused or failed move is recorded and the seat tries another (False: none was accepted)."""
        for attempt in range(6):
            try:
                self.actor, self.payload, how = self.bot.next_move(fallback=attempt > 0)
            except Exception:  # noqa: BLE001 - a view or a hint that fails is an engine bug
                self.problem("exception (view or bot)", traceback.format_exc())
                return False
            try:
                card = self.session.state.cards.get(str(self.payload.get("card_id") or ""))
                self.session.perform(self.actor, self.payload)
                self.trace.update(json.dumps([self.actor, self.payload], sort_keys=True).encode())
                self.report.moves[self.move_kind(how)] += 1
                self.note_use(how, card)
                if self.rng.random() < UNDO_CHANCE:  # the table's Undo button: take the move back (and play on from there)
                    self.session.undo(self.actor)
                    self.trace.update(b"undo")
                    self.report.moves["undo"] += 1
                return True
            except AutomationError as exc:
                self.problem("AutomationError", "".join(traceback.format_exception(exc.__cause__ or exc)))
            except ActionError as exc:
                if self.payload.get("type") == "declare_blockers" and self.payload.get("blocks"):
                    # the client lets a player put any blocker on any attacker; the server checks the plan (509.1b, 509.1c)
                    self.report.refused[f"declare_blockers: {str(exc)[:80]}"] += 1
                    self.bot.fewer_blocks = True
                    continue
                if how == "decision" and self.payload.get("type") == "choose" and len(self.payload.get("option_ids") or ()) > max(
                        1, self.bot.last_decision.get("min_choices", 1)):
                    # several picks the server checks together ("two basic land cards that share a land type"): pick fewer
                    self.report.refused[f"choose {len(self.payload['option_ids'])}: {str(exc)[:80]}"] += 1
                    self.bot.fewer_picks = True
                    continue
                if how == "x":
                    self.report.refused[f"X {self.payload['x_value']}: {re.sub(r'[0-9a-f]{12}', '#', str(exc))[:80]}"] += 1
                    continue
                self.problem("hint mismatch" if how in ("hint", "decision") else "refused", str(exc))
            except Exception:  # noqa: BLE001
                self.problem("exception", traceback.format_exc())
        return False

    def use(self, pid: str) -> DeckUse:
        name = self.names[self.session.state.seat_order.index(pid) % len(self.names)]
        return self.report.decks.setdefault(name, DeckUse())

    def note_use(self, how: str, card: Any) -> None:
        """What the move did for its deck: a spell cast (its commander?), a non-mana ability activated, the lands it has."""
        kind = self.payload.get("type")
        if card is None or kind not in ("cast_spell", "activate_ability", "play_land"):
            return
        use = self.use(self.actor)
        if kind == "cast_spell":
            use.cast[card.name] += 1
            use.commander_cast += bool(card.commander_key)
        elif kind == "activate_ability" and how != "decision":  # (a decision's activation is tapping for mana)
            use.activated[card.name] += 1
        state = self.session.state
        lands = sum(1 for c in state.zones.get(f"{self.actor}:battlefield", [])
                    if "Land" in ((self.cards.get(state.cards[c].card_id or "") or {}).get("type_line") or ""))
        use.max_lands = max(use.max_lands, lands)

    def move_kind(self, how: str) -> str:
        kind = str(self.payload["type"])
        if how == "decision" and kind == "activate_ability":
            return "tap for mana"
        if how == "decision" and kind == "choose":
            d = self.bot.last_decision
            return f"answer {d.get('display', {}).get('kind') or d.get('kind')}" if d else "answer"
        return kind

    def check(self) -> bool:
        session = self.session
        try:
            for pid in session.state.seat_order:
                self.privacy.check(session, pid)
        except AssertionError as exc:
            self.problem("privacy", str(exc))
            return False
        try:
            self.session = self.bot.session = replay_and_reload(session)
        except Exception:  # noqa: BLE001
            self.problem("replay / save-load", traceback.format_exc())
            return False
        return True


def run(db: Path, *, games: int, turns: int, seed: int, players: int, log: bool = False, deck_files: tuple[str, ...] = DECK_FILES) -> Report:
    cards = CachedCards(CardRepository(db, ImageStore(db.parent / "images")))
    try:
        decks = [load_deck(cards, DECKS / name) for name in deck_files]
        report, privacy = Report(), Privacy(cards)
        start = time.perf_counter()
        for i in range(games):
            turn = (i * players) % len(decks)  # each game seats the next decks in the list, so every deck plays
            names = [Path(n).stem for n in deck_files]
            Game(cards, decks[turn:] + decks[:turn], seed + i, players, report, privacy, log=log,
                 names=names[turn:] + names[:turn]).play(turns)
            if log:
                print(f"game {i + 1}/{games} (seed {seed + i}): {report.actions} actions so far", file=sys.stderr)
        report.seconds = time.perf_counter() - start
        return report
    finally:
        cards.close()


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("PYTHONHASHSEED") != "0":  # set iteration order is part of a game: run again with a fixed hash seed
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, "-m", "tools.soak", *(sys.argv[1:] if argv is None else argv)])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "cards.sqlite")
    ap.add_argument("--games", type=int, default=5)
    ap.add_argument("--turns", type=int, default=12, help="stop each game after this turn number")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--players", type=int, choices=(2, 4), default=2)
    ap.add_argument("--log", action="store_true", help="print each problem as it happens")
    ap.add_argument("--digest", action="store_true", help="print a hash of each game's moves and final table (to compare two runs)")
    ap.add_argument("--decks", nargs="+", default=list(DECK_FILES), metavar="FILE",
                    help="deck files in tests/fixtures/soak_decks, seated in turn (default: the two original decks)")
    args = ap.parse_args(argv)
    report = run(args.db, games=args.games, turns=args.turns, seed=args.seed, players=args.players, log=args.log, deck_files=tuple(args.decks))
    print(report.text())
    if args.digest:
        print("\n".join(report.digests))
    return 1 if report.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
