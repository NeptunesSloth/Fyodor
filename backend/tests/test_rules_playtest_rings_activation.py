"""Rings of Brighthearth: "Whenever you activate an ability, if it isn't a mana ability, you may pay {2}. If you do, copy that ability."
603.4 (the intervening if): a mana ability (605.1a) never triggers it. 707.10: a copy of an ability is put on the stack, not activated,
so the copy Rings makes can't trigger Rings (or any "whenever you activate") again. Break-it playtest B1 (Basalt Monolith).
Real Oracle text (Scryfall); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, check, put

RINGS = "Rings of Brighthearth"
MONOLITH = "Basalt Monolith"
EXTRA = [
    real(RINGS, "{3}", 3, "Artifact", "Whenever you activate an ability, if it isn't a mana ability, you may pay {2}. If you do, copy that "
         "ability. You may choose new targets for the copy."),
    real(MONOLITH, "{3}", 3, "Artifact", "This artifact doesn't untap during your untap step.\n{T}: Add {C}{C}{C}.\n{3}: Untap this artifact."),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _rings_items(s):
    return [x for x in s.state.zones.get("stack", []) if RINGS in (s.state.cards[x].name or "")]


def _table(cards):
    s = build(cards, [RINGS, MONOLITH])
    put(s, RINGS)
    monolith = put(s, MONOLITH)
    to_phase(s, "main1", turn=3)
    return s, monolith


def test_mana_ability_does_not_trigger_rings(cards):
    s, monolith = _table(cards)
    act(s, "p1", type="activate_ability", card_id=monolith.id, ability=1)  # {T}: Add {C}{C}{C} (a mana ability, 605.1a)
    assert s.state.cards[monolith.id].tapped
    assert len(s.state.players["p1"].mana_units) == 3  # ({C}{C}{C} in the pool)
    assert _rings_items(s) == [] and s.state.rules.decision is None
    check(s)


def test_the_copy_rings_makes_does_not_trigger_rings_again(cards):
    s, monolith = _table(cards)
    act(s, "p1", type="activate_ability", card_id=monolith.id, ability=1)  # {C}{C}{C} pays for the untap
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=monolith.id, ability=2)  # {3}: Untap — a nonmana ability: Rings triggers once
    assert len(_rings_items(s)) == 1
    seen_rings = 1
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            yes = next((o.id for o in d.options if o.id in ("yes", "pay") or (o.label or "").lower().startswith(("yes", "pay"))), d.options[0].id)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[yes])
        elif s.state.zones.get("stack"):
            seen_rings = max(seen_rings, len(_rings_items(s)))
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert seen_rings == 1  # (707.10: the copy isn't activated, so no second or third Rings trigger)
    assert not s.state.cards[monolith.id].tapped
    assert all(s.state.cards[f.id].tapped for f in forests)  # (Rings' {2} paid with two mana abilities: neither triggered Rings)
    assert sum("Resolved" in "".join(p.t or p.name or "" for p in e.parts) and "Basalt Monolith" in "".join(p.name or "" for p in e.parts)
               for e in s.state.log) == 2  # (the untap ability and its copy, 707.10)
    check(s)

