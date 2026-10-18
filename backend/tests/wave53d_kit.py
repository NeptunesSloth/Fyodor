"""Shared helpers of the wave 53D scenario tests: the real-Oracle fixture cards (tests/fixtures/wave53d_cards.json, from data/cards.sqlite) in a test card database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave53d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w53d", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


# -- tables and answers -------------------------------------------------------------------------------------------------
import json as _json  # noqa: E402

from app.game.factory import PlayerSetup, new_game  # noqa: E402
from app.game.session import GameSession  # noqa: E402
from tests.game_helpers import act, deck, enable  # noqa: E402
from tests.test_rules_wave34b_activated import settle  # noqa: E402, F401
from tests.wave9c_kit import card_named, check, put, to_hand  # noqa: E402, F401


def table(cards, mine=(), bobs=(), carols=(), forests=9, players=3, bob_cmd="Atraxa, Praetors' Voice"):
    """Alice (p1, in her main phase), Bob (p2) and, with ``players`` 3, Carol (p3): the turn order is p1, p2, p3. The hands are empty."""
    def deck_of(commander, spells, lands):
        return deck(cards, commander, [*((1, n) for n in spells), *lands])

    setups = [PlayerSetup("Alice", cards=deck_of("Krenko, Mob Boss", mine, [(forests, "Forest")])),
              PlayerSetup("Bob", cards=deck_of(bob_cmd, bobs, [(12, "Island")]))]
    if players == 3:
        setups.append(PlayerSetup("Carol", cards=deck_of("Atraxa, Praetors' Voice", carols, [(12, "Island")])))
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def answer(s, pid, label=None, *, name=None, expect=True):
    """The pending decision is ``pid``'s: pick the option labelled ``label`` (or the first), or type ``name`` (a card name, a number)."""
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d.player if d else None, pid)
    if name is not None:
        act(s, pid, type="choose", decision_id=d.id, option_ids=[], name=name)
    else:
        pick = next(o for o in d.options if label is None or o.label == label)
        act(s, pid, type="choose", decision_id=d.id, option_ids=[pick.id])


def log(s, viewer="p2"):
    return _json.dumps(s.view(viewer)["log"])


def seen_by_others(s, pid):
    """Everything the other players and a spectator are shown (their views, serialized)."""
    from app.game.visibility import SPECTATOR

    return [(v, _json.dumps(s.view(v))) for v in [p for p in s.state.players if p != pid] + [SPECTATOR]]


def resolve(s, limit=20):
    """Pass priority until the stack is empty or a decision comes up (nothing is answered for the players)."""
    for _ in range(limit):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("the stack never emptied")
