"""Wave 110A: 610.3 / 610.3c Calix, Destiny's Hand -3: exile until the target enchantment you control leaves the battlefield."""

from __future__ import annotations

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import answer, card_db  # noqa: F401
from tests.wave9c_kit import build, check, put

EXTRA = [
    real("Calix, Destiny's Hand", "{2}{G}{W}", 4, "Legendary Planeswalker — Calix",
         "+1: Look at the top four cards of your library. You may reveal an enchantment card from among them and put that card into your hand. Put the rest on the "
         "bottom of your library in a random order.\n−3: Exile target creature or enchantment you don't control until target enchantment you control leaves the "
         "battlefield.\n−7: Return all enchantment cards from your graveyard to the battlefield.", None, "GW"),
    real("Ench110", "{W}", 1, "Enchantment Creature — Spirit", "", ("1", "1"), "W"),
    real("Bear110", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
_BASE.extend(EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Calix, Destiny's Hand")).level == "FULL"


def _calix(cards):
    s = build(cards, ["Calix, Destiny's Hand", "Ench110"], ["Bear110"])
    calix = put(s, "Calix, Destiny's Hand")
    act(s, "p1", type="counter", card_ids=[calix.id], kind="loyalty", delta=3)
    ench, bear = put(s, "Ench110"), put(s, "Bear110", "p2")
    act(s, "p1", type="activate_ability", card_id=calix.id, ability=1, targets=[bear.id, ench.id], target_counts=[1, 1])
    return s, ench, bear


def test_exiles_then_returns_when_enchantment_leaves(cards):
    s, ench, bear = _calix(cards)
    answer(s)
    assert s.state.cards[bear.id].zone.endswith(":exile")
    check(s)
    act(s, "p1", type="set_damage", card_ids=[ench.id], value=1)  # it dies: state-based action (704.5g), the exile ends (610.3c)
    act(s, "p1", type="pass_priority")
    answer(s)
    assert s.state.cards[ench.id].zone == "p1:graveyard" and s.state.cards[bear.id].zone == "p2:battlefield"
    check(s)


def test_enchantment_gone_before_resolution_exiles_nothing(cards):
    s, ench, bear = _calix(cards)
    act(s, "p1", type="set_damage", card_ids=[ench.id], value=1)
    act(s, "p1", type="pass_priority")
    answer(s)
    assert s.state.cards[bear.id].zone == "p2:battlefield"


