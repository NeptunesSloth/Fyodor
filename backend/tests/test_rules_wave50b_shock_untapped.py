"""Wave 50B: a shock land under "Lands you control enter untapped" still asks for its life (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json and
tests/fixtures/wave50b_fetch_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 616.1, Spelunking's rulings (2023-11-10; Horizon Explorer 2025-07-25): "If a land has an ability that says it enters tapped, you choose the order in which that
  ability's effect and Spelunking's effect apply. This means you can choose to have the land enter tapped or untapped." A shock land ("As this land enters, you may pay
  2 life. If you don't, it enters tapped.") was never asked: untapped, no life. The controller is asked now (the payoff for life paid is theirs to want); not paying
  applies the shock land's effect first and Spelunking's after: untapped. The order that leaves it tapped is not offered (ponytail: nothing wants it).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, life, put, reloaded, to_hand
from tests.wave45a_kit import EXTRA as EXTRA45

FETCH = json.loads((Path(__file__).parent / "fixtures" / "wave50b_fetch_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50u", number=f"F{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(FETCH) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA45, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def pending(s):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    return d


def pick(s, option):
    d = pending(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def vents(s):
    return s.state.cards[card_named(s, "Steam Vents").id]


@pytest.mark.parametrize("enabler", ["Spelunking", "Horizon Explorer"])
@pytest.mark.parametrize(("answer", "left"), [("pay", 38), ("tapped", 40)])
def test_a_shock_land_asks_for_its_life_and_enters_untapped_either_way(cards, enabler, answer, left):
    s = build(cards, [enabler, "Steam Vents"], [])
    put(s, enabler)
    land = to_hand(s, "Steam Vents")
    act(s, "p1", type="play_land", card_id=land.id)
    d = pending(s)
    assert d.player == "p1" and [o.id for o in d.options] == ["pay", "tapped"] and "untapped either way" in d.prompt
    assert [o.label for o in d.options] == ["Pay 2 life", "Don't pay (still untapped)"]
    assert vents(s).zone == "p1:hand" and life(s) == 40  # nothing moved while asked
    check(s)
    s = reloaded(s)
    pick(s, answer)
    assert vents(s).zone == "p1:battlefield" and not vents(s).tapped and life(s) == left  # 616.1: the shock land first (tapped), then the enabler (untapped)
    check(s)


def test_a_shock_land_that_cannot_pay_enters_untapped_without_a_question(cards):
    s = build(cards, ["Spelunking", "Steam Vents"], [])
    put(s, "Spelunking")
    act(s, "p1", type="set_life", player="p1", value=1)  # 119.4: 2 life can't be paid from 1
    act(s, "p1", type="play_land", card_id=to_hand(s, "Steam Vents").id)
    assert s.state.rules.decision is None and vents(s).zone == "p1:battlefield" and not vents(s).tapped and life(s) == 1
    check(s)


def test_without_the_enabler_a_shock_land_asks_as_before(cards):
    s = build(cards, ["Steam Vents"], [])
    act(s, "p1", type="play_land", card_id=to_hand(s, "Steam Vents").id)
    d = pending(s)
    assert "or it enters tapped?" in d.prompt and [o.label for o in d.options] == ["Pay 2 life (untapped)", "Enters tapped"]
    pick(s, "tapped")
    assert vents(s).tapped and life(s) == 40
    check(s)


def test_a_shock_land_a_fetch_land_finds_asks_too(cards):
    s = build(cards, ["Spelunking", "Steam Vents", "Scalding Tarn"], [])
    put(s, "Spelunking")
    tarn = put(s, "Scalding Tarn")
    act(s, "p1", type="activate_ability", card_id=tarn.id, ability=0)
    for _ in range(6):  # the search (a private choice), then the shock land's life
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        if "untapped either way" in d.prompt:
            break
        pick(s, d.options[0].id)
    d = pending(s)
    assert "Steam Vents" in d.prompt and "untapped either way" in d.prompt
    check(s)
    pick(s, "pay")
    settle(s)
    assert vents(s).zone == "p1:battlefield" and not vents(s).tapped and life(s) == 40 - 1 - 2  # Scalding Tarn's 1 life, the shock land's 2
    check(s)
