"""Panharmonicon doubling Pestermite's enters trigger (603.2d: it triggers an additional time): the two are the same ability of the same
object on the same event, so there is no order to choose (603.3b) — each still gets its own target as it is put on the stack (603.3d).
Second playtest pass S3: a trigger-order prompt with a single row, "Done (0/1)". Different abilities still ask for an order.
Real Oracle text (Scryfall); replay and a save and a load."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Panharmonicon", "{4}", 4, "Artifact", "If an artifact or creature entering causes a triggered ability of a permanent you control to "
         "trigger, that ability triggers an additional time."),
    real("Pestermite", "{2}{U}", 3, "Creature — Faerie Rogue", "Flash\nFlying\nWhen this creature enters, you may tap or untap target permanent.",
         ("2", "1"), "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_panharmonicons_doubled_trigger_asks_no_order_but_two_targets(cards):
    s = build(cards, ["Panharmonicon", "Pestermite", "Grizzly Bears"], ["Llanowar Elves"])
    put(s, "Panharmonicon")
    bear = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves", "p2")
    to_phase(s, "main1", turn=3)
    to_hand(s, "Pestermite")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Pestermite").id)
    kinds, targets = [], [elves.id, bear.id]
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            kinds.append(d.kind)
            ids = [o.id for o in d.options]
            if d.prompt.endswith("choose a target"):
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[targets.pop(0)])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["tap"] if "tap" in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert "order" not in kinds
    assert not targets  # (two triggers: two targets chosen)
    assert s.state.cards[elves.id].tapped and s.state.cards[bear.id].tapped
    check(s)
