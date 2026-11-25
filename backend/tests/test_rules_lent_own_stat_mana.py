"""A mana ability sized by its source's own power or toughness, lent to another object (Marvin, Murderous Mimic: "has all activated abilities of
creatures you control â€¦", CR 113.10 / 613.1f). Real Oracle text (tests/fixtures/lent_own_stat_mana_cards.json, from data/cards.sqlite).

* 201.5b: the lender's name in a gained ability is the bearer's name, so "where X is Vivi Ornitier's power" on Marvin is Marvin's power. The lent text
  reads "this permanent's power" (abilities_of._lent), which the mana grammar reads as the source's own stat like "this creature's power".
* 602.5b: "Activate only â€¦ once each turn" applies to the object: Marvin's activation and Vivi's are counted apart.

Each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_effects import replay_matches
from tests.wave9c_kit import build, put

DATA = json.loads((Path(__file__).parent / "fixtures" / "lent_own_stat_mana_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="lsm", number=f"L{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
MARVIN = "Marvin, Murderous Mimic"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump() == s.state.model_dump()


def lent(s, c, start):
    """The index of the ability of ``c`` starting with ``start`` (Marvin's borrowed one)."""
    abilities = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).abilities
    return next(a.index for a in abilities if a.text.startswith(start))


def ready(s, *cs):
    for c in cs:  # (controlled since an earlier turn: {T} abilities, 302.6)
        s.state.rules.controlled_since[c.id].turn = 0


def choose(s, label):
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])


def test_marvin_adds_vivis_mana_by_its_own_power_and_counts_once_each_turn_apart(cards):
    s = build(cards, ["Vivi Ornitier", MARVIN])
    vivi, marvin = put(s, "Vivi Ornitier"), put(s, MARVIN)
    act(s, "p1", type="set_counter", card_id=vivi.id, kind="+1/+1", value=1)  # (Vivi 1/4)
    act(s, "p1", type="set_counter", card_id=marvin.id, kind="+1/+1", value=1)  # (Marvin 3/3)
    borrowed = lent(s, marvin, "{0}: Add X mana")
    act(s, "p1", type="activate_ability", card_id=marvin.id, ability=borrowed)
    assert [o.label for o in s.state.rules.decision.options] == ["{U}{U}{U}", "{U}{U}{R}", "{U}{R}{R}", "{R}{R}{R}"]  # X = Marvin's power
    choose(s, "{U}{R}{R}")
    assert mana_pool(s, "p1") == {"U": 1, "R": 2}
    act(s, "p1", type="activate_ability", card_id=vivi.id, ability=0)  # (Vivi's own: not used up by Marvin's, 602.5b)
    assert [o.label for o in s.state.rules.decision.options] == ["{U}", "{R}"]  # X = Vivi's power
    choose(s, "{U}")
    assert mana_pool(s, "p1") == {"U": 2, "R": 2}
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=marvin.id, ability=borrowed)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=vivi.id, ability=0)
    roundtrip(s)


@pytest.mark.parametrize(("lender", "start", "pool"), [
    ("Marwyn, the Nurturer", "{T}: Add an amount of {G}", {"G": 2}),  # Marvin's power 2, not Marwyn's 1
    ("Vhal, Candlekeep Researcher", "{T}: Add an amount of {C}", {"C": 2}),  # Marvin's toughness 2, not Vhal's 3
])
def test_marvin_adds_an_amount_equal_to_its_own_stat(cards, lender, start, pool):
    s = build(cards, [lender, MARVIN])
    put(s, lender)
    marvin = put(s, MARVIN)
    ready(s, marvin)
    act(s, "p1", type="activate_ability", card_id=marvin.id, ability=lent(s, marvin, start))
    player = s.state.players["p1"]
    added = dict(player.mana)
    for unit in player.mana_units:  # (Vhal's mana carries its spending restriction)
        added[unit.sym] = added.get(unit.sym, 0) + 1
    assert added == pool
    roundtrip(s)


def test_marvin_adds_x_mana_of_one_color_by_its_own_power(cards):
    s = build(cards, ["Kami of Whispered Hopes", MARVIN])
    put(s, "Kami of Whispered Hopes")
    marvin = put(s, MARVIN)
    ready(s, marvin)
    act(s, "p1", type="activate_ability", card_id=marvin.id, ability=lent(s, marvin, "{T}: Add X mana"))
    assert [o.label for o in s.state.rules.decision.options] == ["{W}{W}", "{U}{U}", "{B}{B}", "{R}{R}", "{G}{G}"]
    choose(s, "{B}{B}")
    assert mana_pool(s, "p1") == {"B": 2}  # Marvin's power 2, not the Kami's 1
    roundtrip(s)
