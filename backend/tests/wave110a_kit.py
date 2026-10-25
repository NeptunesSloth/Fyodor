"""Shared helpers of the wave 110A scenario tests: real Oracle text cards on the wave 9C table (Alice p1, Bob p2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

__all__ = ["real", "build", "card_named", "check", "life", "mana", "pt", "put", "to_hand", "zone_of", "until", "act", "answer", "cast", "gy",
           "to_graveyard", "ch", "open_repo", "full_test", "STEPS", "fund", "goto", "pytest", "stops", "to_phase", "next_turn"]

STEPS = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]


DATA = json.loads((Path(__file__).parent / "fixtures" / "wave110a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w110a", number=f"A{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings):
    """The fixture cards (real Oracle text from data/cards.sqlite, tests/fixtures/wave110a_cards.json) in a test card database."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def full_test(names):
    @pytest.mark.parametrize("name", names)
    def test_full(cards, name):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
    return test_full


def answer(s, *picks, limit=80):
    """Resolve everything; decisions are answered from ``picks`` in turn (an option id, label or card id; a list: several), else with their first options."""
    picks = list(picks)

    def find(d, token):
        return next((o.id for o in d.options if token in (o.id, o.label, o.card_id)), token)

    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [find(d, t) for t in pick] if isinstance(pick, list) else [find(d, pick)] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", extra="", pay=True, **kw):
    """Cast ``name`` from the hand (put there), its printed mana cost (and ``extra``, "{R}") first put in the pool."""
    c = to_hand(s, name, pid)
    if pay:
        fund(s, (s.cards.resolve(name).get("mana_cost") or "").replace(" // ", "") + extra, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def to_graveyard(s, n, name="Forest", pid="p1"):
    """``n`` more of the player's cards named ``name`` (from the library) into their graveyard."""
    cards = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    assert len(cards) == n
    act(s, pid, type="move", card_ids=[c.id for c in cards], to={"player": pid, "zone": "graveyard"})


def gy(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:graveyard", []))


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def goto(s, phase, who="p1"):
    """Stops everywhere, then pass until it is ``who``'s priority in ``phase``."""
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.turn.phase == phase and s.state.rules.priority == who)


def next_turn(s):
    """To Alice's next main phase: what was put onto the table before has been there since the turn began (no summoning sickness)."""
    to_phase(s, "main1", turn=s.state.turn.number + (2 if s.state.turn.active_player == "p1" else 1))


def fund(s, cost, pid="p1"):
    """Put exactly the mana of ``cost`` ("{3}{W}", generic as colorless) in the player's pool."""
    import re

    pool = {}
    for sym in re.findall(r"\{([^}]+)\}", cost):
        key = "C" if sym.isdigit() else sym
        pool[key] = pool.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    mana(s, pid, **pool)
