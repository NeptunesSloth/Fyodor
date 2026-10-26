"""Wave 110B session 13: single cards on real Oracle text; each scenario checks replay and save/load.

* Curator of Sun's Creation: 701.57 "Whenever you discover" is an event with the value N; the second discover reuses N; once each turn (603.2).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle as look_settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave12a_counters_keywords import real

MOTHER = "Hit the Mother Lode"
EXTRA = [
    real("Curator of Sun's Creation", "{3}{R}", 4, "Creature — Human Wizard",
         "Whenever you discover, discover again for the same value. This ability triggers only once each turn.", ("3", "3"), "R"),
    real("Big Rock", "{8}{G}", 9, "Sorcery", "You gain 1 life.", None, "G"),
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures/discover_followup_cards.json").read_text())):
        base[c["name"]] = card(c["name"], set_code="sdc", number=str(i), **{k: v for k, v in c.items() if k != "name"})
    for c in EXTRA:
        base[c["name"]] = c
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Curator of Sun's Creation")).level == "FULL"


def zones(s, name):
    return sorted(c.zone for c in s.state.cards.values() if c.name == name and c.owner == "p1")


def run(cards, lodes):
    """Library top to bottom: Bears, Big Rock, Bears, Bears; ``lodes`` Hit the Mother Lode casts in one turn."""
    s = table(cards, [MOTHER] * lodes + ["Curator of Sun's Creation", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Big Rock"], ["Forest"])
    put(s, "Curator of Sun's Creation", "battlefield")
    for name in ("Bears", "Bears", "Big Rock", "Bears"):
        act(s, "p1", type="move", card_ids=[put(s, "Big Rock" if name == "Big Rock" else "Grizzly Bears", "hand").id], to={"player": "p1", "zone": "library"}, index=0)
    for _ in range(lodes):
        mana(s, C=4, R=3)
        act(s, "p1", type="cast_spell", card_id=put(s, MOTHER, "hand").id)
        settle(s)
    roundtrip(s)
    return s


def test_discovers_again_for_the_same_value(cards):
    """Discover 10 hits Grizzly Bears (mana value 2); the new discover is 10 as well, not 2: Big Rock (9) is found next."""
    s = run(cards, 1)
    assert zones(s, "Big Rock") == ["p1:graveyard"]  # discovered and cast (a sorcery resolves)
    assert zones(s, "Grizzly Bears").count("p1:library") == 2


def test_triggers_only_once_each_turn(cards):
    """A second Mother Lode the same turn discovers once only (603.2: the ability triggers once each turn)."""
    s = run(cards, 2)
    assert zones(s, "Grizzly Bears").count("p1:library") == 1


# -- Hylda of the Icy Crown: 701.26a "Whenever you tap an untapped creature an opponent controls" (one event per creature), then "you may pay {1}. When you do, choose one" --
HYLDA = real("Hylda of the Icy Crown", "{2}{W}{U}", 4, "Legendary Creature — Giant Wizard",
             "Whenever you tap an untapped creature an opponent controls, you may pay {1}. When you do, choose one —\n"
             "• Create a 4/4 white and blue Elemental creature token.\n• Put a +1/+1 counter on each creature you control.\n• Scry 2, then draw a card.", ("3", "3"), "WU")


@pytest.fixture()
def tapcards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures/trigger_tap_actors62_cards.json").read_text())):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    base[HYLDA["name"]] = HYLDA
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_hylda_full(tapcards):
    assert coverage.of_card_data(tapcards.resolve("Hylda of the Icy Crown")).level == "FULL"


def hylda_run(cards, pay, mode, target="p2"):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_declaration_requirements33 import start

    deck = ["Hylda of the Icy Crown", "Grizzly Bears", "Frost Lynx"]
    s = table(cards, deck, deck, deck)
    put(s, "Hylda of the Icy Crown", "battlefield")
    own = put(s, "Grizzly Bears", "battlefield")
    start(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    victim = put(s, "Grizzly Bears", "battlefield", target)
    wait_priority(s, "p1")
    mana(s, C=3, U=1)  # Frost Lynx {2}{U} plus the {1} for Hylda
    act(s, "p1", type="cast_spell", card_id=put(s, "Frost Lynx", "hand").id, targets=[victim.id])
    for _ in range(15):
        look_settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = {o.id: o.label for o in d.options}
        if "pay" in ids or "decline" in ids:
            pick = "pay" if pay else next(i for i in ids if i != "pay")
        elif any("Elemental" in lbl or "counter" in lbl or "Scry" in lbl for lbl in ids.values()):
            pick = next(i for i, lbl in ids.items() if mode in lbl)
        else:
            pick = victim.id if victim.id in ids else next(iter(ids))
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    roundtrip(s)
    return s, own, victim


@pytest.mark.parametrize("mode", ["Elemental", "counter", "Scry"])
def test_hylda_paid_mode(tapcards, mode):
    s, own, victim = hylda_run(tapcards, True, mode)
    assert victim.tapped
    mine = [c for c in s.state.cards.values() if c.controller == "p1" and c.zone == "p1:battlefield"]
    if mode == "Elemental":
        assert any(c.name == "Elemental" for c in mine)
    elif mode == "counter":
        assert s.state.cards[own.id].counters.get("+1/+1", 0) == 1
    else:
        assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) >= 1


def test_hylda_unpaid_does_nothing(tapcards):
    s, own, victim = hylda_run(tapcards, False, "counter")
    assert s.state.cards[victim.id].tapped and s.state.cards[own.id].counters.get("+1/+1", 0) == 0
    assert not any(c.name == "Elemental" for c in s.state.cards.values())
