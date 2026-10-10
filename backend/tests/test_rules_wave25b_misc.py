"""Wave 25B: smaller reusable pieces (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2d: "create a Food token or a Treasure token" - the choice is made as the instruction is carried out (not a mode, 700.2a).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, mana, to_hand, zone_of

CARDS = [
    ("Tireless Provisioner", "{2}{G}", "Creature — Elf Scout", "3", "2",
     "Landfall — Whenever a land you control enters, create a Food token or a Treasure token. (Food is an artifact with "
     "\"{2}, {T}, Sacrifice this token: You gain 3 life.\" Treasure is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")"),
    ("Ant-Man's Army", "{2}{G}", "Creature — Insect", "3", "2",
     "When this creature enters, create a Food token or a Treasure token. (A Food token is an artifact with \"{2}, {T}, Sacrifice this token: "
     "You gain 3 life.\" A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")"),
]
EXTRA = [card(n, set_code="t25b", number=f"M{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
              colors=["G"], color_identity=["G"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", [c[0] for c in CARDS])
def test_cards_are_full(name):
    assert level(name) == "FULL", name


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.controller == pid and c.zone.endswith(":battlefield")]


@pytest.mark.parametrize("pick,other", [("0", "Treasure"), ("1", "Food")])
def test_food_or_treasure_the_controller_chooses_as_it_resolves(cards, pick, other):
    s = build(cards, ["Tireless Provisioner"], forests=12)
    act(s, "p1", type="move", card_ids=[card_named(s, "Tireless Provisioner").id], to={"player": "p1", "zone": "battlefield"})
    forest = next(c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.label for o in d.options] == ["Create a Food token", "Create a Treasure token"]
    assert len(tokens(s, "Food")) + len(tokens(s, "Treasure")) == 0  # (nothing is made before the choice)
    answer(s, pick)
    made = "Food" if pick == "0" else "Treasure"
    assert len(tokens(s, made)) == 1 and not tokens(s, other)
    check(s)


def test_ant_mans_army_asks_when_it_enters(cards):
    s = build(cards, ["Ant-Man's Army"])
    army = to_hand(s, "Ant-Man's Army")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=army.id)
    answer(s, "1")
    assert zone_of(s, "Ant-Man's Army") == "p1:battlefield" and len(tokens(s, "Treasure")) == 1 and not tokens(s, "Food")
    check(s)
