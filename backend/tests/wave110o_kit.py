"""Shared helpers of the wave 110O scenario tests: every card is the real Oracle text, copied from the card database into
tests/fixtures/wave110o_cards.json (the wave's bucket and the helper cards its scenarios use). Every scenario ends with ``check``
(replay and a save and a load: tests/wave9c_kit)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.game.errors import ActionError  # noqa: F401
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of  # noqa: F401

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave110o_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w110o", number=f"O{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def full(name: str) -> bool:
    data = next(c for c in [*EXTRA, *fixture_cards()] if c["name"] == name)
    return coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def cost(name):
    """The card's own mana cost as a pool ({2}{U}{U}: C=2, U=2)."""
    out: dict[str, int] = {}
    for sym in re.findall(r"{([^}]+)}", next(c for c in [*DATA, *fixture_cards()] if c["name"] == name)["mana_cost"] or ""):
        key = "C" if sym.isdigit() else sym.split("/")[0]  # (hybrid: the first colour)
        out[key] = out.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    return {k: v for k, v in out.items() if v}


def settle(s, limit=60, answers=()):
    """Resolve everything on the stack, taking the first option of every decision (``answers``: option ids picked in turn first)."""
    picks = list(answers)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def next_turn(s, limit=300, until=None):
    """Pass priority (no attackers, no blockers) into the next turn (or until ``until(s)`` holds)."""
    turn = s.state.turn.number
    for _ in range(limit):
        if until is not None and until(s):
            return
        if until is None and s.state.turn.number > turn and not s.state.zones.get("stack") and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the next turn")


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached — or passed."""
    from app.game.state import PHASES

    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if turn is not None and (s.state.turn.number, PHASES.index(s.state.turn.phase)) > (turn, PHASES.index(phase)) \
                and not s.state.zones.get("stack") and (d is None or d.kind in ("declare_attackers", "declare_blockers")):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} (at {s.state.turn.phase})")


def cast_on(s, name, target=None, pid="p1", **kw):
    """Cast ``name`` from the hand with its own mana cost paid (a card or a player id as target), then resolve."""
    c = to_hand(s, name, pid)
    if cost(name):
        mana(s, pid, **cost(name))
    targets = {} if target is None else {"targets": [target] if isinstance(target, str) else [target.id]}
    act(s, pid, type="cast_spell", card_id=c.id, **targets, **kw)
    settle(s)
    return s.state.cards[c.id]


def ch(s, c, viewer="p1"):
    return Plan(s.state, viewer, s.cards, None).ch(s.state.cards[c.id])


def now(s, c):
    return s.state.cards[c.id]


def ability(s, c, start):
    """The index of the card's ability whose text starts with ``start``."""
    return next(a.index for a in ch(s, c).abilities if a.text.startswith(start))


def activate(s, c, start, pid="p1", **kw):
    act(s, pid, type="activate_ability", card_id=c.id, ability=ability(s, c, start), **kw)
    settle(s)


def refused(s, match, c, start, pid="p1", **kw):
    """Refused, and nothing at all changed (118.3, 601.2h)."""
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match=match):
        act(s, pid, type="activate_ability", card_id=c.id, ability=ability(s, c, start), **kw)
    assert s.state.model_dump(mode="json") == before


def move(s, c, zone, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"zone": zone} if zone != "battlefield" else {"player": pid, "zone": zone})


def fresh(s, name, pid="p1"):
    """A card named ``name`` (owned by ``pid``) that is still in the library: decks list a name once per copy."""
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":library"))


def put_new(s, name, pid="p1"):
    c = fresh(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def hand_new(s, name, pid="p1"):
    c = fresh(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def grave_new(s, name, pid="p1"):
    c = fresh(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def to_bottom(s, c, pid="p1"):
    """Put the card on the bottom of its owner's library (so that nobody draws it)."""
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "library"}, position="bottom")
