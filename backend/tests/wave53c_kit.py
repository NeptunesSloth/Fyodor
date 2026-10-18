"""Shared helpers of the wave 53C scenario tests: the real-Oracle fixture cards (tests/fixtures/wave53c_cards.json, from data/cards.sqlite) in a test card database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave53c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w53c", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


# -- scenario helpers: a table in sandbox mode, rules on for combat --
from app.game.errors import ActionError  # noqa: E402,F401
from tests.game_helpers import act  # noqa: E402
from tests.test_rules_conditionals import combat_step as _combat_step  # noqa: E402
from tests.test_rules_conditionals import creature, on_field, sandbox, settle, until  # noqa: E402,F401
from tests.wave9c_kit import card_named, check  # noqa: E402,F401


def combat_step(s):
    """Rules on, to Alice's declare attackers step; both players stop at the declare blockers step (to act once the blocks are known)."""
    _combat_step(s)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=["declare_blockers"], others=["declare_blockers"], smart_pass=False)


def attach(s, equipment, host, pid="p1"):
    act(s, pid, type="attach", card_ids=[equipment.id], to=host.id)


def swing(s, attackers, blocks=(), pid="p1", opp="p2", target=None):
    """Alice (p1) attacks Bob with ``attackers``; ``blocks`` = [(blocker, attacker), …]; plays on until the blockers are declared and answered
    (the trigger stack settled), then returns with the table in the declare blockers step."""
    act(s, pid, type="declare_attackers", attackers=[{"card_id": c.id, "target": target or opp} for c in attackers])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in blocks])
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers were asked for")


def to_postcombat(s):
    until(s, lambda s: s.state.turn.phase == "main2", limit=60)


def alive(s, c):
    return c.id in s.state.cards and s.state.cards[c.id].zone.endswith(":battlefield")


def in_play(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def zone_of(s, c):
    return s.state.cards[c.id].zone if c.id in s.state.cards else None


def pool(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def bob_swings(s, attackers, blocks=(), target="p1"):
    """Play on to Bob's declare attackers step (turn 2), Bob attacks Alice with ``attackers``; Alice blocks with ``blocks`` = [(blocker, attacker), …]."""
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "declare_attackers", limit=200)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": target} for c in attackers])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in blocks])
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers were asked for")
