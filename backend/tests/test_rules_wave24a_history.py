"""Wave 24A: this-turn counts read during a resolution include what the resolution just did (CR 608.2h).

The turn's log notes tokens, discards, sacrifices, damage and counters when triggers are collected, so a later sentence of the same
resolution ("Draw two cards, then discard a card. You gain life equal to the number of cards you've discarded this turn.") must read
the events not yet noted too — once (history.log_for adds them in a scratch copy, never counting an event twice).

Real Oracle text (tests/fixtures/wave24a_cards.json, from data/cards.sqlite); each scenario replays and round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.rules_state import Event
from app.rules import history
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import cast, drive, game, mana, put, roundtrip

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24a_cards.json").read_text("utf-8"))
NAMES = ("Deadly Embrace", "Dihada's Ploy", "Flesh Allergy", "Fists of Flame", "Swift Demise")
EXTRA = [card(c["name"], set_code="t24a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")})
         for i, c in enumerate(DATA) if c["name"] in NAMES]
FODDER = [card("Probe Bear", set_code="t24a", number="A90", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Bear", oracle_text="",
               power="2", toughness="2", colors=["G"], color_identity=["G"])]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FODDER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def life(s, pid="p1"):
    return s.state.players[pid].life


def test_dihadas_ploy_gains_life_for_the_discard_it_just_made(cards):
    s = game(cards, ["Dihada's Ploy", "Probe Bear"])
    put(s, "Probe Bear", "hand")
    before = life(s)
    cast(s, "Dihada's Ploy", U=1, B=1, C=1)
    drive(s)
    assert life(s) == before + 1  # 608.2h: the one card it discarded earlier in this resolution
    roundtrip(s)


def test_the_discard_is_counted_once_after_the_triggers_have_looked_at_it(cards):
    s = game(cards, ["Dihada's Ploy", "Probe Bear"])
    put(s, "Probe Bear", "hand")
    cast(s, "Dihada's Ploy", U=1, B=1, C=1)
    drive(s)
    plan = Plan(s.state, "p1", s.cards, None)
    assert history.amount(plan, {"controller": "p1"}, {"turn_history": "discarded"}) == 1


def test_deadly_embrace_draws_for_the_creature_it_destroyed_and_one_that_died_before(cards):
    s = game(cards, ["Deadly Embrace", "Probe Bear"], ["Probe Bear"])
    mine = put(s, "Probe Bear")
    victim = put(s, "Probe Bear", pid="p2")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "graveyard"})  # one died earlier this turn
    n = hand(s)
    cast(s, "Deadly Embrace", targets=[victim.id], B=2, C=3)
    drive(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard" and hand(s) == n + 2  # (the cast spell was put in hand first: net +2)
    roundtrip(s)


def test_flesh_allergy_counts_the_creature_its_cost_sacrificed(cards):
    s = game(cards, ["Flesh Allergy", "Probe Bear"], ["Probe Bear"])
    fodder = put(s, "Probe Bear")
    victim = put(s, "Probe Bear", pid="p2")
    before = life(s, "p2")
    c = put(s, "Flesh Allergy", "hand")
    mana(s, "p1", B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[victim.id])
    drive(s, choose=lambda d: [fodder.id] if fodder.id in {o.id for o in d.options} else None)
    assert s.state.cards[victim.id].zone == "p2:graveyard" and life(s, "p2") == before - 2  # the sacrificed one and the destroyed one
    roundtrip(s)


def test_events_not_yet_noted_are_read_once_and_in_every_count(cards):
    s = game(cards)
    r = s.state.rules
    n = s.state.turn.number
    r.events.append(Event(batch=r.batch + 1, kind="damage", turn=n, player="p2", amount=3))
    plan = Plan(s.state, "p1", s.cards, None)
    assert history.amount(plan, {"controller": "p1"}, {"turn_history": "opp_damage"}) == 3
    assert history.holds(plan, {"controller": "p1"}, {"history": "damage", "who": "opponent", "n": 3})
    # the collector notes it for good, and it then counts once
    pr = plan.rules  # (the plan works on its own copy of the table)
    pr.trigger_batch = pr.batch + 1
    history.note_events(plan, [e for e in pr.events if e.batch == pr.trigger_batch])
    assert history.amount(plan, {"controller": "p1"}, {"turn_history": "opp_damage"}) == 3


def test_last_turns_log_never_reads_pending_events(cards):
    s = game(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    assert history.log_for(plan, True).facts == []
