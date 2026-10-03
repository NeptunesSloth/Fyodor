"""Wave 8A: extra turns (500.7; app/rules/extra_turns.py).

"Take an extra turn after this one." (Temporal Manipulation, Capture of Jingzhou, Mu Yanling), "Target player takes an
extra turn after this one." (Time Warp, Beacon of Tomorrows, Karn's Temporal Sundering), "Target player takes two extra
turns after this one." (Time Stretch). The extra turns come directly after the turn they were added to, the latest first;
the turn order then goes on from the player whose regular turn it was. The "you lose the game" wordings stay manual.
Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import creature, settle, to_hand, until
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Time Warp', set_code="tst", number="W00", mana_cost='{3}{U}{U}', cmc=5.0, type_line='Sorcery', oracle_text='Target player takes an extra turn after this one.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Time Stretch', set_code="tst", number="W01", mana_cost='{8}{U}{U}', cmc=10.0, type_line='Sorcery', oracle_text='Target player takes two extra turns after this one.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Temporal Manipulation', set_code="tst", number="W02", mana_cost='{3}{U}{U}', cmc=5.0, type_line='Sorcery', oracle_text='Take an extra turn after this one.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Capture of Jingzhou', set_code="tst", number="W03", mana_cost='{3}{U}{U}', cmc=5.0, type_line='Sorcery', oracle_text='Take an extra turn after this one.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Beacon of Tomorrows', set_code="tst", number="W04", mana_cost='{6}{U}{U}', cmc=8.0, type_line='Sorcery', oracle_text="Target player takes an extra turn after this one. Shuffle Beacon of Tomorrows into its owner's library.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Temporal Trespass', set_code="tst", number="W05", mana_cost='{8}{U}{U}{U}', cmc=11.0, type_line='Sorcery', oracle_text='Delve (Each card you exile from your graveyard while casting this spell pays for {1}.)\nTake an extra turn after this one. Exile Temporal Trespass.', colors=['U'], color_identity=['U'], keywords=['Delve']),  # noqa: E501
    card('Final Fortune', set_code="tst", number="W06", mana_cost='{R}{R}', cmc=2.0, type_line='Instant', oracle_text="Take an extra turn after this one. At the beginning of that turn's end step, you lose the game.", colors=['R'], color_identity=['R']),  # noqa: E501
    card('Savor the Moment', set_code="tst", number="W07", mana_cost='{1}{U}{U}', cmc=3.0, type_line='Sorcery', oracle_text='Take an extra turn after this one. Skip the untap step of that turn.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Mu Yanling', set_code="tst", number="W08", mana_cost='{4}{U}{U}', cmc=6.0, type_line='Legendary Planeswalker — Yanling', oracle_text="+2: Target creature can't be blocked this turn.\n−3: Draw two cards.\n−10: Tap all creatures your opponents control. You take an extra turn after this one.", loyalty='5', colors=['U'], color_identity=['U']),  # noqa: E501
    card("Karn's Temporal Sundering", set_code="tst", number="W09", mana_cost='{4}{U}{U}', cmc=6.0, type_line='Legendary Sorcery', oracle_text="(You may cast a legendary sorcery only if you control a legendary creature or planeswalker.)\nTarget player takes an extra turn after this one. Return up to one target nonland permanent to its owner's hand. Exile Karn's Temporal Sundering.", colors=['U'], color_identity=['U']),  # noqa: E501
]
FULL = ["Time Warp", "Time Stretch", "Temporal Manipulation", "Capture of Jingzhou", "Beacon of Tomorrows", "Temporal Trespass",
        "Mu Yanling", "Karn's Temporal Sundering"]
MANUAL = ["Final Fortune", "Savor the Moment"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")
    return loaded


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", MANUAL)
def test_the_lose_the_game_and_skip_wordings_stay_manual(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level != "FULL"


def test_the_wordings():
    assert scripts.parse_effects("Take an extra turn after this one.") == ([{"do": "extra_turn", "who": "you", "n": 1}], None, False)
    assert scripts.parse_effects("Target player takes two extra turns after this one.") == (
        [{"do": "extra_turn", "who": "target", "n": 2}], "player", False)
    for text in ("Take an extra turn after this one. At the beginning of that turn's end step, you lose the game.",
                 "Take an extra turn after this one. Skip the untap step of that turn.",
                 "Target opponent takes an extra turn after this one.",
                 "Take four extra turns after this one."):
        assert scripts.parse_effects(text) is None, text


def table(cards, players=2):
    names = ["Time Warp", "Time Stretch", "Temporal Manipulation", "Beacon of Tomorrows", "Karn's Temporal Sundering"]
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Island")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]))]
    if players == 3:
        setups.append(PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Island")])))
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def cast_sorcery(s, name, *targets):
    c = to_hand(s, name)
    mana(s, U=2, C=10)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=list(targets))
    settle(s)
    return c


def turns(s, upto):
    """(turn number, active player) for each turn from the current one up to turn ``upto``."""
    out = [(s.state.turn.number, s.state.turn.active_player)]
    for n in range(s.state.turn.number + 1, upto + 1):
        until(s, lambda s, n=n: s.state.turn.number == n and s.state.turn.phase == "main1")
        out.append((n, s.state.turn.active_player))
    return out


def test_time_warp_on_an_opponent_then_the_regular_order_goes_on(cards):
    s = table(cards)
    cast_sorcery(s, "Time Warp", "p2")
    assert turns(s, 5) == [(1, "p1"), (2, "p2"), (3, "p2"), (4, "p1"), (5, "p2")]  # Bob's extra turn, then his own (500.7)
    roundtrip(s)


def test_an_extra_turn_for_yourself(cards):
    s = table(cards)
    cast_sorcery(s, "Temporal Manipulation")
    assert turns(s, 4) == [(1, "p1"), (2, "p1"), (3, "p2"), (4, "p1")]
    roundtrip(s)


def test_two_extra_turns_are_both_taken(cards):
    s = table(cards)
    cast_sorcery(s, "Time Stretch", "p1")
    assert turns(s, 5) == [(1, "p1"), (2, "p1"), (3, "p1"), (4, "p2"), (5, "p1")]
    roundtrip(s)


def test_in_a_three_player_game_the_turn_order_resumes_after_the_turn_it_was_added_to(cards):
    s = table(cards, players=3)
    cast_sorcery(s, "Time Warp", "p3")
    # Alice's turn, Carol's extra turn, then Bob (who follows Alice) and Carol's own, Alice again
    assert turns(s, 6) == [(1, "p1"), (2, "p3"), (3, "p2"), (4, "p3"), (5, "p1"), (6, "p2")]
    roundtrip(s)


def test_the_latest_extra_turn_is_taken_first(cards):
    s = table(cards)
    cast_sorcery(s, "Temporal Manipulation")  # turn 2: Alice again
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    cast_sorcery(s, "Time Warp", "p2")  # added to Alice's extra turn: Bob's turn comes directly after it
    assert turns(s, 5) == [(2, "p1"), (3, "p2"), (4, "p2"), (5, "p1")]  # (the regular turn after Alice's is Bob's)
    roundtrip(s)


def test_a_pending_extra_turn_is_taken_before_one_added_earlier(cards):
    s = table(cards)
    cast_sorcery(s, "Temporal Manipulation")  # pending: Alice
    cast_sorcery(s, "Time Warp", "p2")  # pending: Alice, Bob - Bob's was created last, so it is taken first
    assert turns(s, 5) == [(1, "p1"), (2, "p2"), (3, "p1"), (4, "p2"), (5, "p1")]
    roundtrip(s)


def test_the_extra_turn_survives_a_save_taken_before_it_begins(cards):
    s = table(cards)
    cast_sorcery(s, "Time Warp", "p2")
    assert s.state.rules.extra_turns == [{"player": "p2", "label": "Time Warp"}]
    loaded = roundtrip(s)
    assert turns(loaded, 3) == [(1, "p1"), (2, "p2"), (3, "p2")]


def test_beacon_of_tomorrows_shuffles_itself_into_the_library(cards):
    s = table(cards)
    c = cast_sorcery(s, "Beacon of Tomorrows", "p2")
    assert s.state.cards[c.id].zone == "p1:library" or any(
        s.state.cards[x].name == "Beacon of Tomorrows" for x in s.state.zones["p1:library"])
    assert turns(s, 2) == [(1, "p1"), (2, "p2")]
    roundtrip(s)


def test_karn_sundering_gives_the_turn_bounces_and_exiles_itself(cards):
    s = table(cards)
    karn = to_hand(s, "Karn's Temporal Sundering")
    legend = creature(s, "p1", "Karn Fan", type_line="Legendary Creature — Test")
    ox = creature(s, "p2", "Ox")
    mana(s, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=karn.id, targets=["p2", ox.id], target_counts=[1, 1])
    settle(s)
    assert ox.id not in s.state.zones["p2:battlefield"] and legend.id in s.state.zones["p1:battlefield"]
    assert [s.state.cards[c].name for c in s.state.zones["p1:exile"]] == ["Karn's Temporal Sundering"]
    assert turns(s, 3) == [(1, "p1"), (2, "p2"), (3, "p2")]
    roundtrip(s)
