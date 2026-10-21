"""Welcome the Dead: actual graveyard arrivals and native saved continuations."""

import pytest

from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def zombies(s):
    return [
        c
        for c in s.state.cards.values()
        if c.token is not None and c.zone == "p1:battlefield" and "Zombie" in c.token.type_line
    ]


def discard(s):
    d = s.state.rules.decision
    assert d and d.kind == "choose_cards", d
    choose(s, [d.options[0].id])


def test_basic_actual_draw_discard_life_and_tapped_token(cards):
    s = game(cards, ["Welcome the Dead"])
    before = len(s.state.zones["p1:library"])
    source = cast(s, "Welcome the Dead")
    discard(s)
    assert len(s.state.zones["p1:library"]) == before - 3
    assert s.state.players["p1"].life == 38
    assert source.zone == "p1:graveyard"
    assert len(zombies(s)) == 1 and all(c.tapped for c in zombies(s))
    roundtrip(s)


def test_prior_hand_arrivals_even_when_card_no_longer_in_graveyard(cards):
    s = game(cards, ["Welcome the Dead"])
    c = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "exile"})
    cast(s, "Welcome the Dead")
    discard(s)
    assert len(zombies(s)) == 3
    roundtrip(s)


def test_battlefield_arrival_does_not_count(cards):
    s = game(cards, ["Welcome the Dead"])
    c = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Welcome the Dead")
    discard(s)
    assert len(zombies(s)) == 1


def test_legacy_unknown_pauses_only_final_creation(cards):
    s = game(cards, ["Welcome the Dead"])
    s.state.rules.graveyard_history_from_turn = None
    cast(s, "Welcome the Dead")
    discard(s)
    d = s.state.rules.decision
    assert d and d.kind == "manual_resolution"
    assert s.state.players["p1"].life == 38 and not zombies(s)
    choose(s, ["done"])
    assert not s.state.rules.decision and s.state.players["p1"].life == 38
    roundtrip(s)


def test_actual_thought_scour_mill_and_discard(cards):
    s = game(cards, ["Welcome the Dead", "Thought Scour"])
    cast(s, "Thought Scour", ["p1"])
    cast(s, "Welcome the Dead")
    discard(s)
    assert len(zombies(s)) == 3
    roundtrip(s)


@pytest.mark.parametrize("earlier", [False, True])
def test_rest_in_peace_counts_actual_arrivals_not_current_graveyard(cards, earlier):
    s = game(cards, ["Welcome the Dead", "Thought Scour", "Rest in Peace"])
    if earlier:
        cast(s, "Rest in Peace")
    cast(s, "Thought Scour", ["p1"])
    if not earlier:
        cast(s, "Rest in Peace")
    cast(s, "Welcome the Dead")
    discard(s)
    assert len(zombies(s)) == (0 if earlier else 2)
    assert not s.state.zones["p1:graveyard"]
    roundtrip(s)


def test_draw_replacement_does_not_increase_discard_or_token_count(cards):
    s = game(cards, ["Welcome the Dead", "Alhammarret's Archive"])
    cast(s, "Alhammarret's Archive")
    put(s, "Welcome the Dead", "hand")
    before = len(s.state.zones["p1:library"])
    cast(s, "Welcome the Dead")
    discard(s)
    assert len(s.state.zones["p1:library"]) == before - 4
    assert len(zombies(s)) == 1 and s.state.players["p1"].life == 38


def test_native_flashback_cast_exiles_after_resolution(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    s = game(cards, ["Welcome the Dead"])
    source = put(s, "Welcome the Dead", "graveyard")
    mana(s, C=5, B=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[], sources=[])
    settle(s)
    discard(s)
    # Setup itself moved this physical card from library to graveyard this turn.
    assert source.zone == "p1:exile" and len(zombies(s)) == 2
    roundtrip(s)


@pytest.mark.parametrize("legacy", [False, True])
def test_actual_cold_discard_or_unknown_final_creation(cards, tmp_path, legacy):
    import subprocess
    import sys

    s = game(cards, ["Welcome the Dead"])
    if legacy:
        s.state.rules.graveyard_history_from_turn = None
    cast(s, "Welcome the Dead")
    discard_option = s.state.rules.decision.options[0].id
    if legacy:
        discard(s)
        assert s.state.rules.decision.kind == "manual_resolution"
    saved = tmp_path / "welcome.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
legacy=sys.argv[4]=='True'
choose(s,['done'] if legacy else [sys.argv[3]])
assert not s.state.rules.decision
assert s.state.players['p1'].life==38
z=[c for c in s.state.cards.values() if c.token is not None and c.zone=='p1:battlefield' and 'Zombie' in c.token.type_line]
assert len(z)==(0 if legacy else 1)
assert any(c.name=='Welcome the Dead' and c.zone=='p1:graveyard' for c in s.state.cards.values())
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), discard_option, str(legacy)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_discard_return_and_repeat_discard_count_occurrences(cards):
    s = game(cards, ["Welcome the Dead", "Faithless Looting", "Regrowth", "Mind Rot"])
    bear = put(s, "Grizzly Bears", "hand")
    elf = put(s, "Llanowar Elves", "hand")
    cast(s, "Faithless Looting")
    choose(s, [bear.id, elf.id])
    cast(s, "Regrowth", [bear.id])
    ring = put(s, "Sol Ring", "hand")
    cast(s, "Mind Rot", ["p1"])
    choose(s, [bear.id, ring.id])
    cast(s, "Welcome the Dead")
    discard(s)
    assert len(zombies(s)) == 5
    roundtrip(s)


def test_previous_turn_arrivals_do_not_count(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards, ["Welcome the Dead", "Thought Scour"])
    cast(s, "Thought Scour", ["p1"])
    to_phase(s, "main1", turn=7)
    cast(s, "Welcome the Dead")
    discard(s)
    assert len(zombies(s)) == 1
    roundtrip(s)


def test_legacy_missing_origin_does_not_guess(cards):
    s = game(cards, ["Welcome the Dead", "Thought Scour"])
    cast(s, "Thought Scour", ["p1"])
    assert s.state.rules.turn_log.entered_graveyard
    s.state.rules.turn_log.entered_graveyard[0].from_zone = None
    cast(s, "Welcome the Dead")
    discard(s)
    assert s.state.rules.decision.kind == "manual_resolution"
    assert not zombies(s)
    choose(s, ["done"])
    roundtrip(s)


def test_legacy_history_becomes_trustworthy_on_later_observed_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards, ["Welcome the Dead"])
    s.state.rules.graveyard_history_from_turn = None
    source = cast(s, "Welcome the Dead")
    discard(s)
    choose(s, ["done"])
    to_phase(s, "main1", turn=7)
    # The same actual physical card returns to hand; no prior-turn arrival counts.
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    cast(s, "Welcome the Dead")
    discard(s)
    assert not s.state.rules.decision and len(zombies(s)) == 1
    assert s.state.players["p1"].life == 36
    roundtrip(s)


def test_actual_whole_printed_card_full(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve("Welcome the Dead"))
    assert result.level == "FULL", result.manual_parts
