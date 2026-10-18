"""Shared helpers of the wave 52C scenario tests: the real-Oracle fixture cards (tests/fixtures/wave52c_cards.json, from data/cards.sqlite) in a test card database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave52c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w52c", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


# -- shared scenario helpers (wave 52C) --
from tests.game_helpers import act  # noqa: E402
from tests.wave9c_kit import card_named  # noqa: E402


def move(s, name, zone, pid="p1", position=None):
    c = card_named(s, name, pid)
    payload = {"type": "move", "card_ids": [c.id], "to": {"player": pid, "zone": zone}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)
    return s.state.cards[c.id]


def first(d):
    return [o.id for o in d.options][: max(1, d.min_choices)]


def drive(s, pick=first, limit=60):
    """Pass priority and answer every question (``pick(decision)`` -> option ids) until the stack and the questions are done."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and not s.state.rules.pending_triggers:
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d))
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def castable(s, c, pid="p1"):
    from app.rules.view import hints  # noqa: PLC0415

    return c.id in hints(s.state, pid, s.cards).get("castable", [])


def zones(s, pid="p1"):
    return lambda z: [s.state.cards[i].name for i in s.state.zones[f"{pid}:{z}"]]



def to_phase(s, phase, turn=None, limit=200):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


def next_turn(s):
    """To the main phase of Alice's next turn: what was put onto the table before has been there since the turn began (no summoning sickness)."""
    to_phase(s, "main1", turn=s.state.turn.number + 2)
