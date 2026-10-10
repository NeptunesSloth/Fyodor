"""Review 29A: two tables derived at the same time on two threads (the LAN server's GET /view runs on the threadpool while actions run on the
event loop thread; two games, or two viewers of one game, may be derived at once).

A derivation's re-entrancy state (``layers._depth``, the statics table of the current derivation, the group layers being solved, the objects
whose own layer 4 / characteristic-defining P/T is being read) belonged to the process: one thread's derivation part-way made another
thread's derivation skip the static abilities (anthems, granted keywords) or read the other table's statics. Each thread now has its own."""

from __future__ import annotations

import sys
import threading
import time

import pytest

from app.rules import characteristics as chars
from app.rules import layers
from tests.game_helpers import turn_on
from tests.test_rules_combat import creature, table


def _board(cards, anthem: str):
    s = table(cards)
    creature(s, "p1", "Banner", "0/4", anthem)
    creature(s, "p1", "Knight", "2/2", "Other creatures you control have first strike.")
    creature(s, "p1", "Count", "*/*", "This creature's power and toughness are each equal to the number of creatures you control.")
    creature(s, "p2", "Moor", "0/4", "Each creature is a Zombie in addition to its other creature types.")
    for i in range(12):
        creature(s, "p1", f"A{i}", "2/2")
        creature(s, "p2", f"B{i}", "2/2")
    turn_on(s)
    return s


def _derived(s, cards):
    return {c.id: (c.name, (d := layers.derive(s.state, c, chars.of(c, cards), cards)).pt, tuple(sorted(d.keywords)), tuple(sorted(d.subtypes)))
            for c in s.state.cards.values() if c.zone.endswith(":battlefield")}


def _race(boards, cards, expected, *, churn: bool = False, seconds: float = 3.0) -> list[str]:
    """Derive each board on its own threads (two per board) for ``seconds``; ``churn``: a thread empties the statics cache meanwhile (as a
    changed table does), so threads build the statics table of the same table at the same time. Returns what came out wrong."""
    wrong: list[str] = []
    stop = time.monotonic() + seconds

    def work(i: int) -> None:
        try:
            while time.monotonic() < stop and not wrong:
                got = _derived(boards[i], cards)
                if got != expected[i]:
                    wrong.append(f"table {i}: " + ", ".join(f"{v[0]} {v[1:]} != {expected[i][k][1:]}" for k, v in got.items() if v != expected[i][k])[:300])
        except Exception as exc:  # noqa: BLE001 - a crash (another table's statics) is a failure too
            wrong.append(f"table {i}: {exc!r}")

    def empty() -> None:
        while time.monotonic() < stop and not wrong:
            layers._STATIC_CACHE.clear()
            time.sleep(0.0005)

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # (switch threads as often as possible: the window is one derivation)
    try:
        threads = [threading.Thread(target=work, args=(i,)) for i in [*range(len(boards))] * 2]
        threads += [threading.Thread(target=empty)] if churn else []
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    return wrong


def test_two_tables_derived_at_once_on_two_threads_each_get_their_own_answers(cards):
    boards = [_board(cards, "Creatures you control get +1/+1."), _board(cards, "Creatures you control get +2/+0.")]
    expected = [_derived(s, cards) for s in boards]
    a0 = next(v for v in expected[0].values() if v[0] == "A0")
    assert a0[1:3] == ((3, 3), ("first strike",)) and "Zombie" in a0[3]  # (the anthem, the Knight, the Moor: statics apply)
    wrong = _race(boards, cards, expected)
    assert not wrong, wrong[0]


def _parse(text: str):
    from app.rules import scripts
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import parse_abilities

    ch = Characteristics(name="Test", types=frozenset({"Creature"}), oracle_text=text, abilities=tuple(parse_abilities(text, spell=False)))
    return scripts.definitions(ch)


def _forget_parses() -> None:
    import functools
    import gc

    for obj in gc.get_objects():
        if isinstance(obj, functools._lru_cache_wrapper) and str(getattr(obj, "__module__", "")).startswith("app."):
            obj.cache_clear()


FIEND = ("When this creature enters, exile another target creature.\nWhen this creature leaves the battlefield, return the exiled card to the "
         "battlefield under its owner's control.")  # (607.2a: "the exiled card" is what the linked ability exiled)
VOYAGER = ("{2}, Sacrifice this creature: Exile target creature. Return the exiled card to the battlefield under its owner's control at the "
           "beginning of the next end step.")  # (608.2c: what this ability exiled: read again without the linked templates)
SHIELD = ("{T}: The next time a source of your choice would deal damage to you this turn, prevent that damage. If damage is prevented this way, "
          "this creature deals that much damage to that source's controller.")


@pytest.mark.parametrize(("parked", "nested", "text"), [(VOYAGER, "define", FIEND), (SHIELD, "parse_effects", SHIELD)], ids=["linked_exile", "rider"])
def test_a_card_read_while_another_thread_is_part_way_through_a_reading_is_read_as_alone(cards, monkeypatch, parked, nested, text):
    """The card-text grammar's re-readings (an ability read again without the linked-exile templates; a prevention rider read as a sentence
    of its own) marked the whole process while they ran: a card another thread read meanwhile was read differently (Fiend Hunter's return
    lost its link; the shield lost its ability), and the parse cache kept that reading for every later game."""
    from app.rules import scripts

    _forget_parses()
    alone = _parse(text)
    assert alone
    _forget_parses()
    inside, release = threading.Event(), threading.Event()
    real = getattr(scripts, nested)
    depth = threading.local()

    def parked_call(*a, **k):  # the helper thread's nested reading waits part-way until the card has been read
        depth.n = getattr(depth, "n", 0) + 1
        try:
            if threading.current_thread().name == "parked" and depth.n > 1:  # (nested: inside the re-reading)
                inside.set()
                release.wait(10)
            return real(*a, **k)
        finally:
            depth.n -= 1

    monkeypatch.setattr(scripts, nested, parked_call)
    helper = threading.Thread(target=_parse, args=(parked,), name="parked")
    helper.start()
    try:
        assert inside.wait(10)
        got = _parse(text)
    finally:
        release.set()
        helper.join()
    _forget_parses()
    assert got == alone


def test_one_table_whose_statics_two_threads_read_at_once_grants_each_static_once(cards):
    """Two viewers of one game: both find the statics table missing and build it at once. The statics that other statics grant (613.7a: the
    Leader's "Creature tokens you control get +2/+2." on each creature) were appended to the list the cache shares: built twice, twice."""
    s = table(cards)
    creature(s, "p1", "Leader", "2/2", 'Creatures you control have "Creature tokens you control get +2/+2."')
    creature(s, "p1", "Tok", "1/1")
    for i in range(10):
        creature(s, "p2", f"B{i}", "2/2")
    turn_on(s)
    expected = [_derived(s, cards)]
    assert next(v for v in expected[0].values() if v[0] == "Tok")[1] == (5, 5)  # (the Leader's copy and the Tok's own: test_rules_statics)
    wrong = _race([s], cards, expected, churn=True)
    assert not wrong, wrong[0]
