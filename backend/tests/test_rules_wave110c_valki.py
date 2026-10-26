"""Wave 110C: Valki, God of Lies // Tibalt, Cosmic Impostor. 701.20a (reveal), 610.3 (exile until it leaves: back to the hand), 607.2a (cards exiled with),
707.2 (becomes a copy), 614.12 (as it enters), 400.7 (a new Tibalt object has no cards of the old one)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_designations import put as move
from tests.test_rules_wave30m_durations import three
from tests.wave110c_kit import answer, check, make_db, mana, real

VALKI = ("When Valki enters, each opponent reveals their hand. For each opponent, exile a creature card they revealed this way until Valki leaves the battlefield.\n"
         "{X}: Choose a creature card exiled with Valki with mana value X. Valki becomes a copy of that card.")
TIBALT = ('As Tibalt enters, you get an emblem with "You may play cards exiled with Tibalt, Cosmic Impostor, and you may spend mana as though it were mana of any '
          'color to cast those spells."\n+2: Exile the top card of each player\'s library.\n−3: Exile target artifact or creature.\n'
          "−8: Exile all graveyards. Add {R}{R}{R}.")
FACES = [{"object": "card_face", "name": "Valki, God of Lies", "mana_cost": "{1}{B}", "type_line": "Legendary Creature — God", "oracle_text": VALKI,
          "power": "2", "toughness": "1", "colors": ["B"]},
         {"object": "card_face", "name": "Tibalt, Cosmic Impostor", "mana_cost": "{5}{B}{R}", "type_line": "Legendary Planeswalker — Tibalt",
          "oracle_text": TIBALT, "loyalty": "5", "colors": ["B", "R"]}]
EXTRA = [card("Valki, God of Lies // Tibalt, Cosmic Impostor", set_code="tst", number="V1", layout="modal_dfc", mana_cost=None, cmc=2.0,
              type_line="Legendary Creature — God // Legendary Planeswalker — Tibalt", colors=["B"], color_identity=["B", "R"], image_uris=None, card_faces=FACES),
         real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"), real("Test Wurm", "{3}{G}", 4, "Creature — Wurm", "", ("4", "4"), "G"),
         real("Test Rite", "{1}{W}", 2, "Enchantment", "", None, "W")]
NAME = "Valki, God of Lies // Tibalt, Cosmic Impostor"


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def table(cards):
    s = three(cards, [NAME, "Lightning Bolt"], ["Test Bear", "Test Rite"], ["Test Wurm", "Test Bear"])
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", response="on")
    return s


def valki(cards):
    s = table(cards)
    for pid, names in (("p2", ["Test Bear", "Test Rite"]), ("p3", ["Test Wurm"])):
        for n in names:
            move(s, n, "hand", pid)
    v = move(s, NAME, "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=v.id, face=0)
    answer(s)
    return s, v


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def test_etb_exiles_one_creature_card_of_each_opponent_and_they_come_back(cards):
    s, v = valki(cards)
    ex = lambda pid: [c.name for c in s.state.cards.values() if c.owner == pid and c.zone == f"{pid}:exile"]  # noqa: E731
    assert ex("p2") == ["Test Bear"] and ex("p3") == ["Test Wurm"]
    assert [s.state.cards[c].name for c in s.state.zones["p2:hand"]].count("Test Rite") == 1  # (only a creature card)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=move(s, "Lightning Bolt", "hand").id, targets=[v.id])  # (Valki dies: 603.10a)
    answer(s)
    assert ex("p2") == [] and ex("p3") == []  # (610.3: back where they were)
    assert "Test Bear" in [s.state.cards[c].name for c in s.state.zones["p2:hand"]]
    check(s)


@pytest.mark.parametrize(("x", "name"), [(2, "Test Bear"), (4, "Test Wurm"), (3, None)])
def test_x_picks_the_exiled_card_with_that_mana_value(cards, x, name):
    from tests.wave110d_kit import ability

    s, v = valki(cards)
    mana(s, C=x)
    act(s, "p1", type="activate_ability", card_id=v.id, ability=ability(s, v, "{X}"), x_value=x, sources=[])
    answer(s)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[v.id]).name == (name or "Valki, God of Lies")
    check(s)


def test_tibalt_emblem_plays_cards_exiled_with_him_with_any_color(cards):
    from tests.wave110d_kit import ability

    s = table(cards)
    bear = next(c for c in s.state.cards.values() if c.name == "Test Bear" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[bear.id], to={"player": "p2", "zone": "library"}, position="top")
    t = move(s, NAME, "hand")
    mana(s, B=1, R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=t.id, face=1)
    answer(s)
    assert "Tibalt, Cosmic Impostor Emblem" in [c.name for c in s.state.cards.values() if c.zone == "p1:command"]
    act(s, "p1", type="activate_ability", card_id=t.id, ability=ability(s, t, "+2"), sources=[])
    answer(s)
    assert s.state.cards[bear.id].zone == "p2:exile"
    mana(s, B=2)  # (609.4b: black pays {1}{G})
    act(s, "p1", type="cast_spell", card_id=bear.id)
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    check(s)
