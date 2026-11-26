"""Seven of Nine, Tertiary Adjunct: "That Is Irrelevant — {T}: Draw a card, then discard a card. When you discard a nonland card this way, put two
charge counters on up to one target artifact." (207.2c: an ability word; 603.12: the reflexive trigger only when the discarded card is nonland.)
Real Oracle text (Scryfall); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, put, to_hand

EXTRA = [
    real("Seven of Nine, Tertiary Adjunct", "{2}{U}", 3, "Legendary Artifact Creature — Borg", "That Is Irrelevant — {T}: Draw a card, then discard a "
         "card. When you discard a nonland card this way, put two charge counters on up to one target artifact.", ("1", "4"), "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    extra = [*EXTRA, *(c for c in [real("Sol Ring", "{1}", 1, "Artifact", "{T}: Add {C}{C}.", None, ""),
                                    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R")]
                       if c["name"] not in have)]
    build_database([*fixture_cards(), *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Seven of Nine, Tertiary Adjunct")).level == "FULL"


def _settle(s, discard_id, artifact_id):
    """Resolve the stack: discard ``discard_id`` when asked, target ``artifact_id`` with the reflexive trigger."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            by_card = {getattr(o, "card_id", None) or o.id: o.id for o in d.options}
            pick = by_card.get(discard_id) or by_card.get(artifact_id) or d.options[0].id
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize("nonland", [True, False])
def test_loot_puts_charge_counters_only_for_a_nonland_discard(cards, nonland):
    s = build(cards, ["Seven of Nine, Tertiary Adjunct", "Sol Ring", "Lightning Bolt"])
    seven = put(s, "Seven of Nine, Tertiary Adjunct")
    ring = put(s, "Sol Ring")
    to_phase(s, "main1", turn=3)  # (no longer summoning sick, 302.6)
    bolt = to_hand(s, "Lightning Bolt")
    forest = to_hand(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=seven.id, ability=0)
    _settle(s, bolt.id if nonland else forest.id, ring.id)
    discarded = bolt if nonland else forest
    assert card_named(s, discarded.name, "p1").zone == "p1:graveyard" or discarded.id in s.state.zones.get("p1:graveyard", [])
    assert s.state.cards[ring.id].counters.get("charge", 0) == (2 if nonland else 0)
    check(s)
