"""A big finite batch is no loop (break-it playtest B4): 200 Kiki-Jiki copies' "sacrifice it at the beginning of the next end step" triggers
paused automatic passing with "This keeps repeating … the game is a draw (104.4b)". A batch that only drains the stack uses up one
action's step budget without repeating anything (104.4b is about a loop of mandatory actions): the pause says how many objects are left,
with no word of a draw; a stack that refills itself still gets the loop wording. Here: Wrath of God on 150 Goblins under Zulaport Cutthroat.
Real Oracle text (Scryfall); replay and a save and a load."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

ZULAPORT = "Zulaport Cutthroat"
EXTRA = [real(ZULAPORT, "{1}{B}", 2, "Creature — Human Rogue Ally", "Whenever this creature or another creature you control dies, each opponent loses 1 "
              "life and you gain 1 life.", ("1", "1"), "B")]


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


def test_a_wipes_death_triggers_resolve_without_a_word_of_a_loop_or_a_draw(cards):
    s = build(cards, [ZULAPORT, "Wrath of God"])
    put(s, ZULAPORT)
    to_phase(s, "main1", turn=3)
    act(s, "p2", type="set_life", player="p2", value=1000)
    goblin = {"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1", "toughness": "1", "colors": ["R"]}
    for n in (100, 50):
        act(s, "p1", type="create_token", player="p1", count=n, stacked=False, token=goblin)
    to_hand(s, "Wrath of God")
    mana(s, W=2, C=2)
    seen = len(s.state.log)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Wrath of God").id)  # (it resolves on automatic passes: 151 triggers follow)
    for _ in range(20):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority", until="stack_empty")
    notes = [_line(e) for e in s.state.log[seen:]]
    assert not any("104.4b" in x or "keeps repeating" in x for x in notes)  # (was: "This keeps repeating: 20 objects resolved in a row")
    assert not s.state.zones.get("stack")
    assert s.state.players["p2"].life == 1000 - 151  # (the 150 Goblins and Zulaport Cutthroat itself)
    check(s)


def test_the_step_budget_pause_of_a_draining_batch_counts_what_is_left(cards):
    """The pause when one action has used up its step budget (engine.loop_pause) on a batch that only drains the stack."""
    from app.rules import engine
    from app.rules.plan import Plan

    s = build(cards, [ZULAPORT])
    to_phase(s, "main1", turn=3)
    plan = Plan(s.state, "p1", s.cards, None)
    plan.max_steps, plan.steps = 100, [{"type": "note"}] * 61
    plan.chain = engine._Chain(200, {})
    plan.chain.n = 159  # (200 end-step sacrifices, all on the stack before the first resolved, none put back)
    plan.state.zones["stack"] = ["x"] * 41
    assert engine.loop_pause(plan, plan.live())
    note = plan.steps[-1]["text"]
    assert note.startswith("Many objects to resolve: 41 left on the stack. Automatic passing stopped here") and "104.4b" not in note
    plan.chain = engine._Chain(1, {})  # a stack that keeps being refilled: the loop wording stays
    plan.chain.n, plan.chain.refills = 30, 29
    plan.steps = [{"type": "note"}] * 61
    assert engine.loop_pause(plan, plan.live())
    assert any("This keeps repeating" in (st.get("text") or "") for st in plan.steps[61:])
