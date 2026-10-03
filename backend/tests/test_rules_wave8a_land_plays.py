"""Wave 8A: one-shot extra land plays (305.2, 611.2a; app/rules/land_plays.py).

"You may play an additional land this turn." (Explore, Urban Evolution, Beanstalk Wurm's Plant Beans) and "You may play
up to three additional lands this turn." (Summer Bloom): a continuous effect of the resolving spell that lasts this turn;
several add up; the next turn is back to one land. The static "on each of your turns" wordings are wave 4J's.
Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, cast, to_hand, until
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Explore', set_code="tst", number="W00", mana_cost='{1}{G}', cmc=2.0, type_line='Sorcery', oracle_text='You may play an additional land this turn.\nDraw a card.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Urban Evolution', set_code="tst", number="W01", mana_cost='{3}{G}{U}', cmc=5.0, type_line='Sorcery', oracle_text='Draw three cards. You may play an additional land this turn.', colors=['G', 'U'], color_identity=['G', 'U']),  # noqa: E501
    card('Summer Bloom', set_code="tst", number="W02", mana_cost='{1}{G}', cmc=2.0, type_line='Sorcery', oracle_text='You may play up to three additional lands this turn.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Rites of Flourishing', set_code="tst", number="W03", mana_cost='{2}{G}', cmc=3.0, type_line='Enchantment', oracle_text="At the beginning of each player's draw step, that player draws an additional card.\nEach player may play an additional land on each of their turns.", colors=['G'], color_identity=['G']),  # noqa: E501
]
FULL = ["Explore", "Urban Evolution", "Summer Bloom"]


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


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_rites_of_flourishing_stays_manual(cards):
    assert coverage.of_card_data(cards.resolve("Rites of Flourishing")).level != "FULL"


def test_the_wordings():
    assert scripts.parse_effects("You may play an additional land this turn.") == ([{"do": "extra_land", "n": 1}], None, False)
    assert scripts.parse_effects("You may play up to three additional lands this turn.") == ([{"do": "extra_land", "n": 3}], None, False)
    for text in ("You may play an additional land on each of your turns.", "Each player may play an additional land this turn.",
                 "You may play four additional lands this turn.", "Target player may play an additional land this turn."):
        assert scripts.parse_effects(text) is None, text


def lands_in_hand(s, n):
    ids = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:n]
    act(s, "p1", type="move", card_ids=ids, to={"zone": "hand"})
    return ids


def play(s, cid):
    act(s, "p1", type="play_land", card_id=cid)


def test_explore_allows_a_second_land_and_no_third(cards):
    s = build(cards, "Explore")
    first, second, third = lands_in_hand(s, 3)
    explore = to_hand(s, "Explore")
    play(s, first)
    with pytest.raises(ActionError, match="already played"):
        play(s, second)  # one land a turn (305.2) - before Explore
    mana(s, G=2)
    cast(s, explore)
    play(s, second)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="already played"):
        play(s, third)
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_the_extra_land_play_lasts_this_turn_only(cards):
    s = build(cards, "Explore")
    first, second, third = lands_in_hand(s, 3)
    explore = to_hand(s, "Explore")
    mana(s, G=2)
    cast(s, explore)  # the permission is used for nothing this turn
    play(s, first)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # Alice's next turn
    play(s, second)
    with pytest.raises(ActionError, match="already played"):
        play(s, third)
    roundtrip(s)


def test_summer_bloom_and_explore_add_up(cards):
    s = build(cards, "Explore", "Summer Bloom")
    lands = lands_in_hand(s, 6)
    mana(s, G=4)
    cast(s, to_hand(s, "Summer Bloom"))
    cast(s, to_hand(s, "Explore"))
    for cid in lands[:5]:  # 1 + 3 + 1
        play(s, cid)
    with pytest.raises(ActionError, match="already played"):
        play(s, lands[5])
    assert len([c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]) == 5
    roundtrip(s)


def test_the_permission_survives_a_save_taken_in_between(cards):
    s = build(cards, "Explore")
    first, second = lands_in_hand(s, 2)
    mana(s, G=2)
    cast(s, to_hand(s, "Explore"))
    play(s, first)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    act(loaded, "p1", type="play_land", card_id=second)
    assert loaded.state.cards[second].zone == "p1:battlefield"
    roundtrip(s)
