"""Break-it playtest B4 (perf): Kiki-Jiki, Mirror Breaker and Pestermite repeated into a board of hasty copies, each with its own "Sacrifice
it at the beginning of the next end step" (a delayed trigger per copy, 603.7). From "No attack" to the end step's sacrifices, the playtest
waited about 50 s with 200 copies. A generous timing bound (a loaded machine runs this too), and the wording: no loop, no draw.
The board is built with the REPEAT tool exactly as the playtest did; FYODOR_PERF_COPIES sets how many copies (default 40: building 200 by
repeat takes minutes on its own). Real Oracle text (Scryfall); replay and a save and a load."""

from __future__ import annotations

import os
import time

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, check, put

KIKI, PEST = "Kiki-Jiki, Mirror Breaker", "Pestermite"
EXTRA = [
    real(KIKI, "{2}{R}{R}{R}", 5, "Legendary Creature — Goblin Shaman", "Haste\n{T}: Create a token that's a copy of target nonlegendary creature you "
         "control, except it has haste. Sacrifice it at the beginning of the next end step.", ("2", "2"), "R"),
    real(PEST, "{2}{U}", 3, "Creature — Faerie Rogue", "Flash\nFlying\nWhen this creature enters, you may tap or untap target permanent.", ("2", "1"), "U"),
]
COPIES = int(os.environ.get("FYODOR_PERF_COPIES", "40"))
BOUND = 2.0 + 0.6 * COPIES  # seconds for the whole end step (generous: about 0.25 s a copy was the 200-copy playtest's pace)


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _line(entry) -> str:
    return "".join(p.t or p.name or "" for p in entry.parts)


def test_the_end_step_sacrifices_of_many_kiki_copies_are_quick_and_no_loop(cards):
    s = build(cards, [KIKI, PEST])
    kiki, pest = put(s, KIKI), put(s, PEST)
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=kiki.id, ability=1, targets=[pest.id])
    for _ in range(10):  # the copy's Pestermite trigger: target Kiki-Jiki, untap it
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[kiki.id if kiki.id in ids else "untap" if "untap" in ids else ids[0]])
    act(s, "p1", type="repeat_sequence", count=len(s.state.rules.recent["p1"]), times=COPIES - 1)
    copies = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(copies) == COPIES
    seen = len(s.state.log)
    started = time.perf_counter()
    for _ in range(40):
        d = s.state.rules.decision
        if s.state.turn.number > 3:
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[])  # "No attack"
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority", until="next_turn")
    elapsed = time.perf_counter() - started
    assert not any(c.zone == "p1:battlefield" for c in (s.state.cards.get(x.id) for x in copies) if c is not None)
    notes = [_line(e) for e in s.state.log[seen:]]
    assert not any("104.4b" in x or "keeps repeating" in x for x in notes)
    assert elapsed < BOUND, f"{COPIES} copies: the end step took {elapsed:.1f} s"
    check(s)
