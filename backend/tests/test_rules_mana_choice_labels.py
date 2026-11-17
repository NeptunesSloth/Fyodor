"""-- mana choice labels -- tapping a permanent with several mana abilities asks which mana; every option names, in short form, the ability it
comes from (no reminder text, no "Activate only if …" that already holds). Tainted Field's {W}/{B} ability is offered only while its
condition holds ("Activate only if you control a Swamp", 602.5b). Real Oracle text (Scryfall); each scenario checks the replay and a save
and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, put

EXTRA = [
    real("Tainted Field", "", 0, "Land", "{T}: Add {C}.\n{T}: Add {W} or {B}. Activate only if you control a Swamp.", None, ""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _swamp(s, pid="p1"):
    """A Swamp onto Alice's battlefield (a token Swamp: the deck has none)."""
    act(s, pid, type="create_token", player=pid, token={"name": "Swamp", "type_line": "Basic Land — Swamp"})
    return next(c for c in s.state.cards.values() if c.is_token and c.name == "Swamp")


def _tap(s, card):
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, tap_for_mana=True)


def test_without_a_swamp_tainted_field_only_taps_for_colorless(cards):
    s = build(cards, ["Tainted Field"])
    field = put(s, "Tainted Field")
    with pytest.raises(ActionError):  # (602.5b: its condition doesn't hold)
        act(s, "p1", type="activate_ability", card_id=field.id, ability=1, mana_choice="W")
    _tap(s, field)
    assert s.state.rules.decision is None and mana_pool(s) == {"C": 1} and s.state.cards[field.id].tapped  # (one ability: nothing to ask)
    check(s)


def test_with_a_swamp_each_option_names_its_ability_in_short(cards):
    s = build(cards, ["Tainted Field"])
    field = put(s, "Tainted Field")
    _swamp(s)
    _tap(s, field)
    d = s.state.rules.decision
    assert d is not None and d.prompt == "Which mana should Tainted Field add?"
    assert [o.label for o in d.options] == ["{C} ({T}: Add {C})", "{W} ({T}: Add {W} or {B})", "{B} ({T}: Add {W} or {B})", "Cancel"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith("{B}"))])
    assert mana_pool(s) == {"B": 1} and s.state.cards[field.id].tapped
    check(s)
