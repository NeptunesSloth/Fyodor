"""Shared helpers of the wave 110C scenario tests (real Oracle text; every scenario ends with ``check``: replay and a save/load round trip)."""

from __future__ import annotations

from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real  # noqa: F401  (re-exported)
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand  # noqa: F401  (re-exported)

STEPS = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]


def make_db(settings, extra):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def answer(s, *picks, limit=80):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def to_graveyard(s, n, name="Forest", pid="p1"):
    """``n`` more of the player's cards named ``name`` (from the library) into their graveyard."""
    cards = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    assert len(cards) == n
    act(s, pid, type="move", card_ids=[c.id for c in cards], to={"player": pid, "zone": "graveyard"})


def gy(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:graveyard", []))


def zone(s, c):
    return s.state.cards[c.id].zone


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
