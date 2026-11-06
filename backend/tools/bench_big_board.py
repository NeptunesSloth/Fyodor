"""-- big boards round 3 -- A reproducible big-board benchmark (no card database download needed).

Adrix and Nev, ``n`` Scute Swarms and six Forests on the battlefield, a seventh Forest played: ``n`` landfall triggers, each making a
copy of a Scute Swarm, doubled by Adrix and Nev. Times the land drop and resolving everything left on the stack, and prints a digest of
the final table, the log and the replay so a speed-up can be checked to change nothing:

    PYTHONPATH=$PWD python -m tools.bench_big_board 20 40 80 [--repeat 3] [--profile out.prof]
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import importlib
import itertools
import secrets
import statistics
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession

# The test kit's fixtures and helpers (untyped test code: loaded by name so the type checker doesn't follow them into tests/)
_fixtures: Any = importlib.import_module("tests.fixtures.cards")
_helpers: Any = importlib.import_module("tests.game_helpers")
card, fixture_cards = _fixtures.card, _fixtures.fixture_cards
act, deck, enable = _helpers.act, _helpers.deck, _helpers.enable


@contextmanager
def deterministic() -> Iterator[None]:
    """Ids, salts and clock readings from counters while it lasts, so two runs (before and after a change) give the same digest."""
    ids, clock = itertools.count(1), itertools.count(1)
    saved = secrets.token_hex, secrets.token_urlsafe, uuid.uuid4, time.time
    secrets.token_hex = lambda nbytes=16: format(next(ids), "x").rjust(2 * (nbytes or 16), "0")
    secrets.token_urlsafe = lambda nbytes=16: format(next(ids), "x").rjust(nbytes or 16, "0")
    uuid.uuid4 = lambda: uuid.UUID(int=next(ids))
    time.time = lambda: 1_700_000_000.0 + next(clock)
    try:
        yield
    finally:
        secrets.token_hex, secrets.token_urlsafe, uuid.uuid4, time.time = saved


def _real(name: str, cost: str, cmc: int, types: str, text: str, pt: tuple[str, str] | None, colors: str) -> dict[str, Any]:
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"BB-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=[], **extra)


EXTRA = [
    _real('Adrix and Nev, Twincasters', '{2}{G}{U}', 4, 'Legendary Creature — Merfolk Wizard',
          'Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player '
          'pays {2}.)\nIf one or more tokens would be created under your control, twice that many of those tokens are created instead.',
          ("2", "2"), 'GU'),
    _real('Scute Swarm', '{2}{G}', 3, 'Creature — Insect',
          "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, "
          "create a token that's a copy of this creature instead.", ("1", "1"), 'G'),
]


def repository(root: Path) -> CardRepository:
    db = root / "cards.sqlite"
    build_database([*fixture_cards(), *EXTRA], db, meta={"bulk_type": "test"})
    return CardRepository(db, ImageStore(root / "images"))


def table(cards: CardRepository, n: int) -> tuple[GameSession, str]:
    alice = deck(cards, "Adrix and Nev, Twincasters", [(n, "Scute Swarm"), (8, "Forest")])
    bob = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    mine = lambda name: [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == name]  # noqa: E731
    act(s, "p1", type="move", card_ids=mine("Adrix and Nev, Twincasters") + mine("Scute Swarm") + mine("Forest")[:6],
        to={"player": "p1", "zone": "battlefield"})
    forest = mine("Forest")[6]
    act(s, "p1", type="move", card_ids=[forest], to={"player": "p1", "zone": "hand"})
    return s, forest


def resolve_all(s: GameSession) -> None:
    """Resolve everything on the stack (the first option of each question)."""
    while s.state.zones.get("stack"):
        r = s.state.rules
        assert r is not None
        if r.decision is not None:
            act(s, r.decision.player, type="choose", decision_id=r.decision.id, option_ids=[r.decision.options[0].id])
        else:
            assert r.priority is not None
            act(s, r.priority, type="pass_priority")


def digest(s: GameSession) -> str:
    """The final table, its log and its replay, hashed: equal digests before and after a speed-up mean nothing it saves changed."""
    h = hashlib.sha256()
    h.update(s.state.model_dump_json().encode())
    for a in s.history.actions:
        h.update(a.model_dump_json().encode())
    return h.hexdigest()[:16]


def run(cards: CardRepository, n: int, prof: cProfile.Profile | None = None) -> tuple[float, float, str, int]:
    """The land drop and resolving the rest: (seconds, seconds, digest, permanents Alice has at the end)."""
    with deterministic():
        s, forest = table(cards, n)
        if prof:
            prof.enable()
        t0 = time.perf_counter()
        act(s, "p1", type="play_land", card_id=forest)
        t1 = time.perf_counter()
        resolve_all(s)
        t2 = time.perf_counter()
        if prof:
            prof.disable()
        return t1 - t0, t2 - t1, digest(s), len(s.state.zones["p1:battlefield"])


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sizes", nargs="*", type=int, default=[20, 40, 80])
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--profile", help="write a cProfile of the last run of the last size here")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        cards = repository(Path(tmp))
        try:
            for n in args.sizes:
                lands, resolves, digests = [], [], set()
                for i in range(args.repeat):
                    prof = cProfile.Profile() if args.profile and n == args.sizes[-1] and i == args.repeat - 1 else None
                    land, res, dig, board = run(cards, n, prof)
                    lands.append(land)
                    resolves.append(res)
                    digests.add(dig)
                    if prof:
                        prof.dump_stats(args.profile)
                print(f"n={n:3d} board={board:4d} land drop {statistics.median(lands):6.2f} s  resolve {statistics.median(resolves):6.2f} s"
                      f"  (runs: {', '.join(f'{a:.2f}+{b:.2f}' for a, b in zip(lands, resolves, strict=True))})  digest {sorted(digests)}",
                      flush=True)
        finally:
            cards.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
