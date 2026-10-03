"""Wave 13E: "Players can't untap more than N <kind> during their untap steps" (Smoke, Stoic Angel, Winter Orb, Static Orb,
Imi Statue, Winter Moon), researched against CR 2026-09-25.

* 502.3: the active player determines which permanents untap; effects can keep some from untapping. The limit is on what
  the active player untaps in their own untap step, and they choose which (a decision in the untap step: no priority, 502.4).
* Winter Orb limits only while it is untapped (the condition is read as the untap step begins).
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, on_field, to_turn
from tests.test_rules_wave4h_activation_costs import build, roundtrip

EXTRA = [
    card('Smoke', set_code="tst", number="N04", mana_cost='{2}{R}{R}', cmc=4.0, type_line='Enchantment', oracle_text="Players can't untap more than one creature during their untap steps.", colors=['R'], color_identity=['R']),  # noqa: E501
    card('Winter Orb', set_code="tst", number="N05", mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text="As long as this artifact is untapped, players can't untap more than one land during their untap steps."),  # noqa: E501
    card('Static Orb', set_code="tst", number="N06", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text="As long as this artifact is untapped, players can't untap more than two permanents during their untap steps."),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def tapped(s, c):
    return s.state.cards[c.id].tapped


def tap(s, pid, *cs, value=True):
    act(s, pid, type="tap", card_ids=[c.id for c in cs], tapped=value)


def to_question(s, number):
    for _ in range(200):
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif (d.resume or {}).get("step") == "untap_limit":
            assert s.state.turn.number == number and s.state.turn.phase == "untap" and s.state.rules.priority is None
            return d
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("no question")


def test_smoke_lets_the_active_player_choose_one_creature_to_untap(cards):
    s = build(cards, p1=("Smoke",), p2=("Island",))
    on_field(s, "Smoke")
    a, b = creature(s, "p2", "Ox"), creature(s, "p2", "Yak")
    isle = on_field(s, "Island", pid="p2")
    tap(s, "p2", a, b, isle)
    d = to_question(s, 2)
    assert d.player == "p2" and d.min_choices == d.max_choices == 1 and sorted(o.card_id for o in d.options) == sorted([a.id, b.id])
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)  # the question survives a save
    assert loaded.state.rules.decision.id == d.id
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == b.id)])
    assert tapped(s, a) and not tapped(s, b) and not tapped(s, isle)  # (the land isn't a creature: Smoke doesn't limit it)
    roundtrip(s)
    to_turn(s, 3)  # Alice has nothing tapped: no question


def test_winter_orb_limits_only_while_it_is_untapped(cards):
    s = build(cards, p1=("Winter Orb",), p2=("Island",))
    orb = on_field(s, "Winter Orb")
    i1 = on_field(s, "Island", pid="p2")
    i2 = creature(s, "p2", "Mire", type_line="Token Land — Test")
    tap(s, "p2", i1, i2)
    tap(s, "p1", orb)  # a tapped Orb limits nothing
    to_turn(s, 2)
    assert not tapped(s, i1) and not tapped(s, i2)
    tap(s, "p1", orb, value=False)
    tap(s, "p2", i1, i2)
    d = to_question(s, 4)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert sum(tapped(s, c) for c in (i1, i2)) == 1
    roundtrip(s)


def test_two_kinds_are_asked_in_turn_and_the_lowest_limit_rules(cards):
    s = build(cards, p1=("Smoke", "Static Orb"), p2=())
    on_field(s, "Smoke")
    on_field(s, "Static Orb")
    xs = [creature(s, "p2", f"Ox{i}") for i in range(3)]
    tap(s, "p2", *xs)
    d = to_question(s, 2)  # Smoke: one creature (Static Orb's two permanents come second, over what is still allowed)
    assert d.min_choices == 1
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert sum(tapped(s, c) for c in xs) == 2
    roundtrip(s)
