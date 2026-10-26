"""Wave 110H: Tahngarth, First Mate (CR 506.3b, 508.4, 613.1b / 611.2, real Oracle text).

* Tahngarth: when an opponent attacks and it is tapped, its controller may give that opponent control of it until end of combat, then chooses a player or
  planeswalker that opponent is attacking; it is attacking it (never declared, so no attack trigger) and returns when combat ends.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import check

TAH = ("Tahngarth can't be blocked by more than one creature.\nWhenever an opponent attacks with one or more creatures, if Tahngarth is tapped, you may have that "
       "opponent gain control of Tahngarth until end of combat. If you do, choose a player or planeswalker that opponent is attacking. Tahngarth is attacking that "
       "player or planeswalker.")
EXTRA = [real("Tahngarth, First Mate", "{2}{R}{G}", 4, "Legendary Creature — Minotaur Warrior", TAH, ("4", "5"), "RG"),
         real("Balduvian Bears", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
         real("Test Walker", "{2}{U}", 3, "Legendary Planeswalker \u2014 Jace", "+1: Draw a card.", None, "U")]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Tahngarth, First Mate")).level == "FULL"


def _go(cards, tapped=True, may="yes", who="p2"):
    names = ["Tahngarth, First Mate", "Test Walker", "Grizzly Bears", "Balduvian Bears"]
    s = table(cards, names, names, names)
    to_phase(s, "main1", 4)
    bears = [put(s, "Grizzly Bears", "battlefield"), put(s, "Balduvian Bears", "battlefield")]
    tah = put(s, "Tahngarth, First Mate", "battlefield", "p2")
    jace = put(s, "Test Walker", "battlefield", "p3")
    act(s, "p3", type="set_counter", card_id=jace.id, kind="loyalty", value=3)
    to_phase(s, "main1", 7)
    if tapped:
        act(s, "p2", type="tap", card_ids=[tah.id], tapped=True)
    to_phase(s, "declare_attackers", 7)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears[0].id, "target": "p2"}, {"card_id": bears[1].id, "target": jace.id}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        pick = may if may in ids else (who if who in ids else jace.id if who == "walker" else ids[0])
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    return s, tah, jace


@pytest.mark.parametrize(("who", "target"), [("walker", "jace"), ("p2", "p2")])
def test_attacks_chosen_then_returns(cards, who, target):
    s, tah, jace = _go(cards, who=who)
    t = s.state.cards[tah.id]
    assert t.controller == "p1" and t.is_attacking
    assert t.attacking.id == (jace.id if target == "jace" else target)
    check(s)
    to_phase(s, "main2", 7)
    assert s.state.cards[tah.id].controller == "p2" and not s.state.cards[tah.id].is_attacking


def test_declined(cards):
    s, tah, _ = _go(cards, may="no")
    t = s.state.cards[tah.id]
    assert t.controller == "p2" and not t.is_attacking


def test_untapped_no_trigger(cards):
    s, tah, _ = _go(cards, tapped=False)
    t = s.state.cards[tah.id]
    assert t.controller == "p2" and not t.is_attacking
