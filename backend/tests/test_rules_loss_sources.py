"""-- loss sources -- the rules record which card made a player lose (``RulesState.lost_source``, shown to every viewer as
``rules.lost_source``): the spell or ability that said "you lose the game" (Final Fortune), the last public source that took the life to 0
(Lightning Bolt's damage, Sign in Blood's life loss) or made the player draw from an empty library. Public facts only; nothing when the
last change had no known source. Real Oracle text (Scryfall); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, to_hand

EXTRA = [
    real("Final Fortune", "{R}{R}", 2, "Instant",
         "Take an extra turn after this one. At the beginning of that turn's end step, you lose the game.", None, "R"),
    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),
    real("Sign in Blood", "{B}{B}", 2, "Sorcery", "Target player draws two cards and loses 2 life.", None, "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _seen(s, loser):
    """What every viewer is shown of the loss's source."""
    shown = [s.view(v)["rules"]["lost_source"].get(loser) for v in ("p1", "p2")]
    assert shown[0] == shown[1]
    return shown[0]


def _cast(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id, **kw)
    settle(s)


def test_final_fortune_is_named_as_the_card_that_lost_the_game(cards):
    s = build(cards, ["Final Fortune"])
    mana(s, R=2)
    _cast(s, "Final Fortune")
    turn = s.state.turn.number
    to_phase(s, "end", turn=turn + 1)  # (the extra turn: Alice's again)
    settle(s)
    r = s.state.rules
    assert r.lost.get("p1") == "an effect" and r.winner == "p2"
    printing = card_named(s, "Final Fortune").card_id
    assert _seen(s, "p1") == {"name": "Final Fortune", "card_id": printing}
    check(s)
    again = GameState.model_validate_json(s.state.model_dump_json())
    assert again.rules.lost_source["p1"].name == "Final Fortune"


def test_lightning_bolts_damage_to_zero_life_names_it(cards):
    s = build(cards, ["Lightning Bolt"])
    act(s, "p2", type="set_life", player="p2", value=3)
    mana(s, R=1)
    _cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.rules.lost.get("p2") == "0 or less life"
    assert _seen(s, "p2") == {"name": "Lightning Bolt", "card_id": card_named(s, "Lightning Bolt").card_id}
    check(s)


def test_sign_in_bloods_life_loss_names_it(cards):
    s = build(cards, ["Sign in Blood"])
    act(s, "p2", type="set_life", player="p2", value=2)
    mana(s, B=2)
    _cast(s, "Sign in Blood", targets=["p2"])
    assert s.state.rules.lost.get("p2") == "0 or less life"
    assert _seen(s, "p2")["name"] == "Sign in Blood"
    check(s)


def test_a_draw_from_an_empty_library_names_the_spell_that_made_it(cards):
    s = build(cards, ["Sign in Blood"])
    library = list(s.state.zones["p2:library"])
    act(s, "p2", type="move", card_ids=library, to={"zone": "exile"})
    mana(s, B=2)
    _cast(s, "Sign in Blood", targets=["p2"])
    assert s.state.rules.lost.get("p2") == "drew from an empty library"
    assert _seen(s, "p2")["name"] == "Sign in Blood"
    check(s)


def test_a_life_change_by_hand_after_the_damage_leaves_no_source(cards):
    s = build(cards, ["Lightning Bolt"])
    mana(s, R=1)
    _cast(s, "Lightning Bolt", targets=["p2"])
    act(s, "p2", type="life", player="p2", delta=-37)  # (by hand: no card did it)
    act(s, "p1", type="pass_priority")  # (704.3: checked as a player would receive priority)
    settle(s)
    assert s.state.rules.lost.get("p2") == "0 or less life"
    assert _seen(s, "p2") is None and "p2" not in s.state.rules.lost_source
    check(s)
