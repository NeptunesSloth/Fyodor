"""Wave 24C: a reflexive "When you do" after counters (CR 603.12, 122.6, 614.17) — "Whenever Auron attacks, put a +1/+1 counter on it. When you
do, exile target creature defending player controls with power less than Auron's power until Auron leaves the battlefield." (Auron, Venerated
Guardian).

The reflexive ability triggers only if the counter was really put: Solemnity ("Counters can't be put on artifacts, creatures, enchantments,
or lands", 614.17) stops it, so nothing is exiled. Every scenario uses real Oracle text (tests/fixtures/wave24c_reflexive_cards.json, from
data/cards.sqlite) and checks that replaying the recorded history reproduces the table and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_wave5j_token_copies import game, put, roundtrip, token
from tests.test_rules_wave23c_values import attack, unready

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24c_reflexive_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24r", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def counters(s, c):
    return {k: v for k, v in s.state.cards[c.id].counters.items() if v}


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def run_attack(s, auron, bear):
    """Attack with Auron, let the bear stay out of combat, answer the reflexive ability's target with it, stop when the damage is done."""
    from tests.game_helpers import act

    unready(s, auron)
    attack(s, auron)
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id] if bear.id in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        elif s.state.players["p2"].life < 40:
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("the attack never finished")


def test_auron_exiles_a_smaller_creature_once_the_counter_is_put(cards):
    s = game(cards, ["Auron, Venerated Guardian"])
    auron = put(s, "Auron, Venerated Guardian")
    bear = token(s, "p2", "Bob Bear", "2/2")
    run_attack(s, auron, bear)
    assert counters(s, auron) == {"+1/+1": 1}
    assert bear.id not in s.state.cards or s.state.cards[bear.id].zone != "p2:battlefield"  # exiled (a token ceases to exist there): its power 2 is less than Auron's
    roundtrip(s)


def test_the_reflexive_ability_waits_for_the_counter(cards):
    s = game(cards, ["Auron, Venerated Guardian", "Solemnity"])
    put(s, "Solemnity")
    auron = put(s, "Auron, Venerated Guardian")
    bear = token(s, "p2", "Bob Bear", "2/2")
    run_attack(s, auron, bear)
    assert counters(s, auron) == {}  # 614.17: no counter was put
    assert s.state.cards[bear.id].zone == "p2:battlefield"  # so "when you do" never happened
    roundtrip(s)
