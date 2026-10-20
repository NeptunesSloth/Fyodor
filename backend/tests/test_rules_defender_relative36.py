"""Canonical exact-target delayed watches, event batching and source/controller identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sba import power
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/defender_relative36_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="bd35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads((Path(__file__).parent / "fixtures/defender_relative36_cards.json").read_text())
    ]
    return table(cards, names, names, names)


NAMES = [
    "Graven Abomination",
    "Rakshasa Debaser",
    "Chorale of the Void",
    "Hive of the Eye Tyrant",
    "Xantid Swarm",
    "Shrouded Serpent",
    "Mtenda Lion",
    "Sibilant Spirit",
    "Harbor Guardian",
    "Unquenchable Fury",
    "The Long Reach of Night // Animus of Night's Reach",
    "Shakedown Heavy",
]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def attack(s, source, who="p2", turn=4):
    from tests.test_rules_wave30p_combat import attack as declare

    to_phase(s, "declare_attackers", turn=turn)
    declare(s, (source, who))
    settle(s)


@pytest.mark.parametrize(
    "name,dest", [("Graven Abomination", "p2:exile"), ("Rakshasa Debaser", "p1:battlefield")]
)
def test_attack_uses_only_correct_defending_graveyard(cards, name, dest):
    s = setup(cards)
    source = put(s, name, "battlefield")
    right = put(s, "Grizzly Bears", "graveyard", pid="p2")
    wrong = put(s, "Runeclaw Bear", "graveyard", pid="p3")
    start(s)
    attack(s, source)
    d = s.state.rules.decision
    assert d and right.id in [o.card_id for o in d.options] and wrong.id not in [o.card_id for o in d.options]
    pick(s, [right.id])
    settle(s)
    assert s.state.cards[right.id].zone == dest
    assert s.state.cards[wrong.id].zone == "p3:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Sibilant Spirit", "Harbor Guardian"])
@pytest.mark.parametrize("answer", ["yes", "no"])
def test_defender_optional_draw_not_attacker_or_other_player(cards, name, answer):
    s = setup(cards)
    source = put(s, name, "battlefield")
    start(s)
    before = {p: len(s.state.zones[p + ":hand"]) for p in ["p1", "p2", "p3"]}
    attack(s, source)
    assert s.state.rules.decision.player == "p2"
    pick(s, [answer])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == before["p2"] + (answer == "yes")
    assert len(s.state.zones["p1:hand"]) == before["p1"]
    assert len(s.state.zones["p3:hand"]) == before["p3"]
    roundtrip(s)


@pytest.mark.parametrize("name,cost", [("Shrouded Serpent", {"C": 4}), ("Mtenda Lion", {"U": 1})])
@pytest.mark.parametrize("pay", [True, False])
def test_defender_optional_payment_real_combat_result(cards, name, cost, pay):
    s = setup(cards)
    source = put(s, name, "battlefield")
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    for color, n in cost.items():
        mana(s, pid="p2", **{color: n})
    from tests.test_rules_wave30p_combat import attack as declare

    declare(s, (source, "p2"))
    settle(s)
    assert s.state.rules.decision.player == "p2"
    pick(s, ["pay" if pay else "decline"])
    settle(s)
    if name == "Shrouded Serpent":
        imposed = Plan(s.state, "p1", cards, None).ch(s.state.cards[source.id]).imposed
        assert ("cant_be_blocked" in imposed) == (not pay)
    else:
        to_phase(s, "combat_damage", turn=4)
        settle(s)
        assert s.state.players["p2"].life == (40 if pay else 38)
    roundtrip(s)


def test_xantid_only_defender_after_trigger_resolution_and_expires(cards):
    s = setup(cards)
    source = put(s, "Xantid Swarm", "battlefield")
    start(s)
    attack(s, source)
    for _ in range(8):
        if s.state.rules.priority == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    card = put(s, "Shock", "hand", pid="p2")
    mana(s, pid="p2", R=1)
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p2", type="cast_spell", card_id=card.id, targets=["p1"], target_counts=[1])
    cast(s, "Shock", ["p1"], pid="p3", target_counts=[1])
    assert s.state.players["p1"].life == 38
    to_phase(s, "main1", turn=5)
    cast(s, "Shock", ["p1"], pid="p2", target_counts=[1])
    assert s.state.players["p1"].life == 36
    roundtrip(s)


def test_shakedown_defender_accept_draw_untaps_and_removes_old_source(cards):
    s = setup(cards)
    source = put(s, "Shakedown Heavy", "battlefield")
    start(s)
    before = len(s.state.zones["p1:hand"])
    attack(s, source)
    assert s.state.rules.decision.player == "p2"
    pick(s, ["yes"])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + 1
    assert not s.state.cards[source.id].tapped
    assert not s.state.cards[source.id].is_attacking
    roundtrip(s)


def test_fury_granted_host_uses_actual_defender_hand_count(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    cast(s, "Unquenchable Fury", [bear.id], target_counts=[1])
    before = len(s.state.zones["p3:hand"])
    attack(s, bear, "p3")
    assert s.state.players["p3"].life == 40 - before
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_hive_actual_animation_grants_defender_graveyard_trigger(cards):
    s = setup(cards)
    hive = put(s, "Hive of the Eye Tyrant", "battlefield")
    victim = put(s, "Grizzly Bears", "graveyard", pid="p2")
    start(s)
    mana(s, B=1, C=3)
    act(s, "p1", type="activate_ability", card_id=hive.id, ability=2)
    settle(s)
    attack(s, hive)
    pick(s, [victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:exile"
    to_phase(s, "main1", turn=5)
    assert not Plan(s.state, "p1", cards, None).ch(s.state.cards[hive.id]).is_creature
    roundtrip(s)


def test_chorale_enters_tapped_attacking_any_legal_recipient(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    victim = put(s, "Runeclaw Bear", "graveyard", pid="p2")
    start(s)
    cast(s, "Chorale of the Void", [bear.id], target_counts=[1])
    attack(s, bear)
    pick(s, [victim.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "token_attack"
    assert "p3" in [o.id for o in d.options]
    pick(s, ["p3"])
    settle(s)
    current = s.state.cards[victim.id]
    assert current.zone == "p1:battlefield" and current.tapped
    assert current.attacking.id == "p3"
    roundtrip(s)


def test_animus_real_saga_transforms_then_counts_only_defending_graveyard(cards):
    s = setup(cards)
    put(s, "Grizzly Bears", "graveyard", pid="p2")
    put(s, "Memnite", "graveyard", pid="p2")
    put(s, "Shock", "graveyard", pid="p2")
    put(s, "Runeclaw Bear", "graveyard", pid="p3")
    start(s)
    saga = cast(s, "The Long Reach of Night // Animus of Night's Reach")
    # Its normal chapters progress through actual turn-based Saga actions.
    to_phase(s, "main1", turn=7)
    settle(s)
    to_phase(s, "main1", turn=10)
    settle(s)
    assert s.state.cards[saga.id].face == 1
    to_phase(s, "declare_attackers", turn=13)
    plan = Plan(s.state, "p1", cards, None)
    expected = sum("Creature" in plan.ch(c).types for c in s.state.cards.values() if c.zone == "p2:graveyard")
    assert expected >= 2
    attack(s, s.state.cards[saga.id], turn=13)
    assert (
        power(s.state.cards[saga.id], Plan(s.state, "p1", cards, None).ch(s.state.cards[saga.id])) == expected
    )
    roundtrip(s)


def test_saved_defender_payment_resumes_cold_with_original_payer(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, "Shrouded Serpent", "battlefield")
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    mana(s, pid="p2", C=4)
    from tests.test_rules_wave30p_combat import attack as declare

    declare(s, (source, "p2"))
    settle(s)
    assert s.state.rules.decision.player == "p2"
    saved = tmp_path / "defender-pay.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.rules.decision.player=='p2'
pick(s,['pay'])
settle(s)
assert 'cant_be_blocked' not in Plan(s.state,'p1',repo,None).ch(s.state.cards[sys.argv[3]]).imposed
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_fury_counts_defender_hand_at_resolution_after_response(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    cast(s, "Unquenchable Fury", [bear.id], target_counts=[1])
    from tests.test_rules_wave30p_combat import attack as declare

    to_phase(s, "declare_attackers", turn=4)
    declare(s, (bear, "p2"))
    before = len(s.state.zones["p2:hand"])
    # The defender consumes one real hand card before the granted damage trigger resolves.
    card = put(s, "Shock", "hand", pid="p2")
    before = len(s.state.zones["p2:hand"])
    mana(s, pid="p2", R=1)
    for _ in range(8):
        if s.state.rules.priority == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=card.id, targets=["p1"], target_counts=[1])
    settle(s)
    assert s.state.players["p2"].life == 40 - (before - 1)
    assert s.state.players["p1"].life == 38
    roundtrip(s)


def test_xantid_defender_can_respond_before_trigger_resolves(cards):
    s = setup(cards)
    source = put(s, "Xantid Swarm", "battlefield")
    start(s)
    from tests.test_rules_wave30p_combat import attack as declare

    to_phase(s, "declare_attackers", turn=4)
    declare(s, (source, "p2"))
    cast(s, "Shock", ["p1"], pid="p2", target_counts=[1])
    assert s.state.players["p1"].life == 38
    assert any(x.get("player") == "p2" for x in s.state.rules.cast_limits)
    roundtrip(s)
