"""Secure the Wastes for X = 250 under Doubling Season and Anointed Procession (break-it playtest B5): 250 Warriors, doubled twice (616.1:
each replacement applies once, in the order the affected player picks; both double, so 1,000 either way) — one engine token stack ×1,000
(docs/TOKEN_STACKS.md). The cast was refused: the stack audit read "Create X … tokens" as an amount it couldn't vouch for, though X is the
one number announced for the spell (107.3, 601.2b), the same for every member. Real Oracle text (Scryfall); replay and a save and a load."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Secure the Wastes", "{X}{W}", 1, "Instant", "Create X 1/1 white Warrior creature tokens.", None, "W"),
    real("Doubling Season", "{4}{G}", 5, "Enchantment", "If an effect would create one or more tokens under your control, it creates twice that many of "
         "those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on "
         "that permanent instead.", None, "G"),
    real("Anointed Procession", "{3}{W}", 4, "Enchantment", "If an effect would create one or more tokens under your control, it creates twice that many "
         "of those tokens instead.", None, "W"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _secure(cards, x, doublers=("Doubling Season", "Anointed Procession")):
    s = build(cards, ["Secure the Wastes", *doublers])
    for name in doublers:
        put(s, name)
    to_phase(s, "main1", turn=3)
    to_hand(s, "Secure the Wastes")
    for _ in range((x + 1) // 50):
        mana(s, W=50)
    if (x + 1) % 50:
        mana(s, W=(x + 1) % 50)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Secure the Wastes").id, x_value=x)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s


def _warriors(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Warrior" and c.zone == "p1:battlefield"]


@pytest.mark.parametrize("x, want", [(250, 1000), (30, 120)])
def test_two_doublers_make_one_stack(cards, x, want):
    s = _secure(cards, x)
    warriors = _warriors(s)
    assert len(warriors) == 1 and warriors[0].quantity == want
    assert card_named(s, "Secure the Wastes").zone == "p1:graveyard"
    check(s)


def test_a_small_x_still_makes_separate_tokens(cards):
    s = _secure(cards, 24)
    warriors = _warriors(s)
    assert len(warriors) == 96 and all(c.quantity == 1 for c in warriors)
    check(s)
