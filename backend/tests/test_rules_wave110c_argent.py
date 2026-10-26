"""Wave 110C: The Argent Etchings (Elesh Norn's back face): I incubates five times (701.53) and transforms every Incubator (701.28); III destroys every other permanent but
artifacts, lands and Phyrexians, and Elesh Norn comes back front face up as a new object (400.7)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.wave36a_kit import next_own_turn, resolve_stack
from tests.wave110c_kit import build, check, make_db, put, real

NORN_FRONT = ("Vigilance\nWhenever a source an opponent controls deals damage to you or a permanent you control, that source's controller loses 2 life unless they pay {1}.\n"
              "{2}{W}, Sacrifice three other creatures: Exile Elesh Norn, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.")
ETCHINGS = ("(As this Saga enters and after your draw step, add a lore counter.)\nI — Incubate 2 five times, then transform all Incubator tokens you control.\n"
            "II — Creatures you control get +1/+1 and gain double strike until end of turn.\n"
            "III — Destroy all other permanents except for artifacts, lands, and Phyrexians. Exile this Saga, then return it to the battlefield (front face up).")
NORN = card("Elesh Norn // The Argent Etchings", set_code="tst", number="E1", layout="transform", mana_cost=None, cmc=4.0,
            type_line="Legendary Creature — Phyrexian Praetor // Enchantment — Saga", colors=["W"], color_identity=["W"], image_uris=None,
            card_faces=[{"object": "card_face", "name": "Elesh Norn", "mana_cost": "{2}{W}{W}", "type_line": "Legendary Creature — Phyrexian Praetor", "oracle_text": NORN_FRONT,
                         "power": "3", "toughness": "5", "colors": ["W"]},
                        {"object": "card_face", "name": "The Argent Etchings", "mana_cost": "", "type_line": "Enchantment — Saga", "oracle_text": ETCHINGS, "colors": ["W"]}])
EXTRA = [NORN, real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"), real("Test Praetor", "{2}{B}", 3, "Creature — Phyrexian Horror", "", ("3", "3"), "B"),
         real("Test Relic", "{2}", 2, "Artifact", "", None, ""), real("Test Rite", "{1}{W}", 2, "Enchantment", "", None, "W")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Elesh Norn // The Argent Etchings")).level == "FULL"


def _own_turn(s):
    next_own_turn(s)
    resolve_stack(s)


def test_chapters_one_and_three(cards):
    s = build(cards, ["Elesh Norn // The Argent Etchings", "Test Bear", "Test Praetor", "Test Relic", "Test Rite"], ["Test Bear"], forests=30, islands=30)
    norn = put(s, "Elesh Norn // The Argent Etchings")
    s.state.cards[norn.id].face = 1  # the back face: The Argent Etchings
    mine = [put(s, n) for n in ("Test Bear", "Test Praetor", "Test Relic", "Test Rite")]
    theirs = put(s, "Test Bear", "p2")
    _own_turn(s)  # I: five Incubator tokens with two +1/+1 counters, all transformed
    toks = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield" and c.owner == "p1" and c.counters.get("+1/+1") == 2]
    assert len(toks) == 5 and all(c.face == 1 for c in toks)
    _own_turn(s)  # II: nothing to check besides it resolving
    assert s.state.cards[norn.id].counters.get("lore") == 2
    _own_turn(s)  # III
    z = {c.name: s.state.cards[c.id].zone for c in mine}
    assert z["Test Bear"] == "p1:graveyard" and z["Test Rite"] == "p1:graveyard"  # a creature and an enchantment destroyed
    assert z["Test Praetor"] == "p1:battlefield" and z["Test Relic"] == "p1:battlefield"  # a Phyrexian and an artifact stay
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    assert all(s.state.cards[c.id].zone == "p1:battlefield" for c in toks)  # the Phyrexian Tokens are artifact creatures and Phyrexians
    n = s.state.cards[norn.id]
    assert n.zone == "p1:battlefield" and n.face == 0 and not n.counters.get("lore")  # Elesh Norn, front face up
    check(s)
