"""Shared helpers of the wave 110B scenario tests: the real-Oracle fixture cards (tests/fixtures/wave110b_cards.json, from data/cards.sqlite) and a table with
Alice and Bob (tests/wave9c_kit.py)."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until  # noqa: F401
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of  # noqa: F401

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave110b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w110b", number=f"B{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
NAMES = [c["name"] for c in DATA if c["name"] not in KNOWN]


def repository(settings):
    """The card repository of a test (each test module wraps it in its own ``cards`` fixture)."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def pool(s, pid="p1"):
    return dict(s.state.players[pid].mana)


def cast(s, name, targets=(), pid="p1", **kw):
    """``pid`` casts the card from their hand (put there first) and everything resolves."""
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, targets=list(targets), **kw)
    settle(s)


def ch(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def attack(s, *creatures, target="p2"):
    """From Alice's first main phase: on to declare attackers and attack ``target`` with the creatures (no summoning sickness for them)."""
    for c in creatures:
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="pass_priority")
    assert s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": target} for c in creatures])


def through_combat(s, blocks=None):
    """Play on to the second main phase; Bob declares ``blocks`` ((blocker, attacker) pairs) if given, the rest of what is asked the first option."""
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in (blocks or [])])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def top(s, name, pid="p1"):
    """The player's card named ``name`` goes on top of their library (drawn first)."""
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "library"}, position="top")


def drive(s, answer=None, limit=80):
    """Resolve everything: a decision is answered by ``answer(decision)`` (option ids, or None for the first options), else priority passes."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = answer(d) if answer else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")
