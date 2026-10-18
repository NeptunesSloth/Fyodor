"""Shared helpers of the wave 53A scenario tests: the real-Oracle fixture cards (tests/fixtures/wave53a_cards.json, from data/cards.sqlite) in a test card database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave53a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w53a", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards: Any, *decks: Any, lands: int = 10) -> Any:
    """A table of ``len(decks)`` players (Alice, Bob, Carol, Dave; ids p1..p4), each with the named cards of her list (``(copies, name)`` allowed) and
    ``lands`` basic lands (Forests for Alice, Islands for the rest); Alice is on her first main phase."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import act, deck, enable

    def entries(names: Any) -> list[tuple[int, str]]:
        return [n if isinstance(n, tuple) else (1, n) for n in names]

    players = [PlayerSetup(name, cards=deck(cards, "Krenko, Mob Boss" if i == 0 else "Atraxa, Praetors' Voice",
                                              [*entries(names), (lands, "Forest" if i == 0 else "Island")]))
               for i, (name, names) in enumerate(zip(("Alice", "Bob", "Carol", "Dave"), decks, strict=False))]
    s = GameSession(enable(new_game(players, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def alice_next(s: Any) -> None:
    """To the first main phase of Alice's next turn (what was put onto the table before has been there since it began: no summoning sickness)."""
    from tests.test_rules_wave34b_activated import to_phase

    to_phase(s, "main1", turn=s.state.turn.number + len(s.state.players))


def card_view(s: Any, viewer: str, c: Any) -> str:
    import json

    return json.dumps(s.view(viewer)["cards"].get(c.id, {}))


def unseen_by(s: Any, c: Any, *viewers: str) -> bool:
    """Nothing in the viewers' views of the table names this card (its name, its printing)."""
    return all(c.name not in card_view(s, v, c) and c.card_id not in card_view(s, v, c) for v in viewers)


def until_asked(s: Any, limit: int = 30) -> Any:
    """Pass priority until a decision is open (returned)."""
    from tests.game_helpers import act

    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")
