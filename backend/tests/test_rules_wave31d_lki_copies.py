"""Wave 31D follow-up: a copy of a spell that has left the stack (CR 707.10, 608.2h), real Oracle text (tests/fixtures/wave31d_cards.json).

The rulings: "Copies are created even if the spell that caused Thousand-Year Storm's ability to trigger has been countered" (2018-10-05),
"Each Storm … can copy the Storm spell even if that spell is countered before that ability resolves" (2018-07-13), Krark: "If you win the
flip, but the spell … isn't on the stack anymore … the copy is still created" and on a lost flip nothing is returned (2020-11-10), Fire Lord
Azula: "They resolve even if the spell is countered before the copy is created" (2025-10-02). The copy is made from how the spell last existed on
the stack — its targets, X, modes, kicker — kept when it leaves (``RulesState.stack_lki``), and the copy is not cast.

Every scenario checks that replaying the recorded history reproduces the table and that a save and a load keep it.
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.rules_state import RulesState
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave31d_spell_copies import EXTRA, hand, hold, resolve_one, settle
from tests.wave9c_kit import build, check, life, mana, put, reloaded, to_hand


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def counter_in_response(s, spell):
    """Alice has put a spell and its trigger on the stack and passes; Bob counters the spell; the Counterspell resolves, the trigger doesn't yet."""
    counterspell = to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=2)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counterspell.id, targets=[spell.id])
    top = s.state.zones["stack"][-1]
    for _ in range(4):
        if top not in s.state.zones.get("stack", []):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    assert [e.kind for e in s.state.rules.stack.values()] == ["trigger"]  # only the copy trigger is left


def storm_scene(cards):
    """Thousand-Year Storm; a first Bolt cast and resolved (Bob at 37); the second one on the stack with the Storm's trigger above it."""
    s = build(cards, ["Thousand-Year Storm", "Lightning Bolt", "Lightning Bolt"], ["Counterspell"])
    put(s, "Thousand-Year Storm")
    first, second = hand(s, "Lightning Bolt", 2)
    hold(s)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 37
    act(s, "p1", type="cast_spell", card_id=second.id, targets=["p2"])
    return s, second


# -- Thousand-Year Storm ---------------------------------------------------------------------------------------------------------------------
def test_thousand_year_storm_still_copies_a_spell_that_was_countered_before_its_trigger_resolved(cards):
    s, second = storm_scene(cards)
    counter_in_response(s, second)
    remembered = [m for m in s.state.rules.stack_lki.values() if m.card == second.id and m.entry is not None]
    assert len(remembered) == 1 and remembered[0].entry is not None and remembered[0].entry.targets[0].id == "p2"  # how this spell was there
    resolve_one(s)  # the trigger: one spell was cast before the second Bolt — one copy, made from the countered Bolt (608.2h, 707.10)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith("Copy of Lightning Bolt")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["keep"])
    [copy] = [c for c in s.state.zones["stack"] if s.state.cards[c].is_token]
    assert [t.id for t in s.state.rules.stack[copy].targets] == ["p2"] and s.state.rules.stack[copy].copy_of is not None
    assert s.state.rules.spells_this_turn("p1", s.state.turn.number) == 2  # the copy isn't cast
    settle(s)
    assert life(s, "p2") == 34 and s.state.cards[second.id].zone == "p1:graveyard"  # the countered Bolt did nothing; its copy hit Bob for 3
    assert copy not in s.state.cards  # 707.10a: it ceased to exist as it left the stack
    check(s)


def test_the_copy_is_made_after_a_save_and_a_load_with_the_snapshot_pending(cards):
    s, second = storm_scene(cards)
    counter_in_response(s, second)
    saved = RulesState.model_validate(s.state.rules.model_dump(mode="json"))  # a save of the table's rules state keeps the snapshot …
    assert saved.stack_lki == s.state.rules.stack_lki
    s2 = reloaded(s)  # … and so does rebuilding the table from its history
    assert set(s2.state.rules.stack_lki) == set(s.state.rules.stack_lki) and s2.state.rules.stack_lki
    for table in (s, s2):
        resolve_one(table)
        d = table.state.rules.decision
        assert d is not None and d.prompt.startswith("Copy of Lightning Bolt")
        act(table, "p1", type="choose", decision_id=d.id, option_ids=["keep"])
        settle(table)
        assert life(table, "p2") == 34
    check(s)
    check(s2)


def test_a_spell_moved_to_a_hand_by_hand_is_copied_too_without_showing_the_hand(cards):
    s, second = storm_scene(cards)
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})  # (the table move: it leaves the stack for its owner's hand)
    assert s.state.cards[second.id].zone == "p1:hand" and s.state.rules.stack_lki
    resolve_one(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith("Copy of Lightning Bolt")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["keep"])
    settle(s)
    assert life(s, "p2") == 34 and s.state.cards[second.id].zone == "p1:hand"
    assert not s.view("p2")["cards"].get(second.id, {}).get("name")  # the Bolt in Alice's hand is still hidden from Bob (the copy on the stack was public)
    check(s)


def test_without_a_snapshot_the_copy_is_asked_for_by_hand_never_silently_skipped(cards):
    s, second = storm_scene(cards)
    counter_in_response(s, second)
    s.state.rules.stack_lki.clear()  # (a table saved before the snapshots existed)
    resolve_one(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == "manual_resolution" and "by hand" in d.prompt and "left the stack" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["done"])
    settle(s)
    assert life(s, "p2") == 37  # nothing was copied by the engine


def test_a_copy_card_action_needs_real_last_known_information(cards):
    s, second = storm_scene(cards)
    counter_in_response(s, second)
    with pytest.raises(ActionError, match="last known information"):
        act(s, "p1", type="copy_card", card_id=second.id, last_known="nowhere.1")  # (not a way to read a hidden card's name)
    other = to_hand(s, "Counterspell", "p2")
    with pytest.raises(ActionError):
        act(s, "p1", type="copy_card", card_id=other.id, last_known=next(iter(s.state.rules.stack_lki)))  # (another card's snapshot)


# -- Krark, the Thumbless ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("heads", [True, False])
def test_krark_copies_a_countered_spell_on_a_won_flip_and_returns_nothing_on_a_lost_one(cards, monkeypatch, heads):
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: 1 if heads else 0)
    s = build(cards, ["Krark, the Thumbless", "Lightning Bolt"], ["Counterspell"])
    put(s, "Krark, the Thumbless")
    bolt = to_hand(s, "Lightning Bolt")
    hold(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    counter_in_response(s, bolt)
    settle(s)
    if heads:  # the copy is created although the Bolt is gone, and resolves
        assert life(s, "p2") == 37
    else:  # "nothing is returned to your hand. The card stays in its current zone"
        assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


# -- storm (702.40) ---------------------------------------------------------------------------------------------------------------------------
def test_storm_copies_a_countered_grapeshot(cards):
    s = build(cards, ["Grapeshot", "Lightning Bolt"], ["Counterspell"])
    bolt, grapeshot = to_hand(s, "Lightning Bolt"), to_hand(s, "Grapeshot")
    hold(s)
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=grapeshot.id, targets=["p2"])
    act(s, "p1", type="pass_priority")
    counterspell = to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=counterspell.id, targets=[grapeshot.id])
    # the Counterspell resolves; the storm trigger (cast before it was countered) is still on the stack
    for _ in range(6):
        if s.state.cards[grapeshot.id].zone == "p1:graveyard":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[grapeshot.id].zone == "p1:graveyard" and s.state.rules.stack_lki
    check(s)  # (a save and a load with the snapshot pending)
    settle(s)
    assert life(s, "p2") == 40 - 3 - 1  # the Bolt, and one copy of the countered Grapeshot (one spell was cast before it)
    check(s)
