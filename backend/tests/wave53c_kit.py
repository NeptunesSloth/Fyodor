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
from tests.test_rules_conditionals import creature, on_field, sandbox, settle, token_of, until  # noqa: E402,F401
from tests.wave9c_kit import card_named, check  # noqa: E402,F401


def combat_step(s):
    """Rules on, to Alice's declare attackers step; both players stop at the declare blockers step (to act once the blocks are known)."""
    _combat_step(s)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=["declare_attackers", "declare_blockers"], others=["declare_attackers", "declare_blockers"], smart_pass=False)


def attach(s, equipment, host, pid="p1"):
    act(s, pid, type="attach", card_ids=[equipment.id], to=host.id)


def swing(s, attackers, blocks=(), pid="p1", opp="p2", target=None, before=None):
    """Alice (p1) attacks Bob with ``attackers``; ``blocks`` = [(blocker, attacker), …]; plays on until the blockers are declared and answered
    (the trigger stack settled), then returns with the table in the declare blockers step."""
    act(s, pid, type="declare_attackers", attackers=[{"card_id": c.id, "target": target or opp} for c in attackers])
    if before is not None:  # (the declare attackers step, attackers declared, before blockers: cast a spell, …)
        priority_to(s, pid)
        before()
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


def cast_now(s, name, targets=(), pid="p1", counts=None, **m):
    """Move ``name`` from the library to the hand, add ``m`` to the pool, cast it at ``targets`` and let the stack resolve."""
    c = in_play(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    pool(s, pid, **m)
    priority_to(s, pid)
    extra = {} if counts is None else {"target_counts": counts}
    act(s, pid, type="cast_spell", card_id=c.id, targets=[t if isinstance(t, str) else t.id for t in targets], **extra)
    settle(s)
    return c


def main_step(s):
    """Rules on, Alice's first main phase."""
    from tests.game_helpers import turn_on

    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    return s


def priority_to(s, pid):
    """The active player has priority first in a step: they pass until ``pid`` has it."""
    for _ in range(3):
        if s.state.rules.priority == pid:
            return
        act(s, s.state.rules.priority, type="pass_priority")


def drive(s, prefer=(), limit=40):
    """Resolve the stack, answering each decision with the first of ``prefer`` it offers (a confirmation: yes), else its first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            pick = next((p for p in prefer if p in ids), "yes" if "yes" in ids else ids[0])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def discard_for_real(s, name):
    """Discard ``name`` from Alice's hand with Faithless Looting (draw two, then discard two: the named card first)."""
    for n in ("Faithless Looting", name):
        c = in_play(s, n)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    pool(s, R=1)
    act(s, "p1", type="cast_spell", card_id=in_play(s, "Faithless Looting").id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            want = [o.id for o in d.options if o.card_id == in_play(s, name).id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=(want + [o.id for o in d.options if o.id not in want])[: d.max_choices])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
