"""Conditional attachment and Army animation use native continuous effects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Bark of Doran", "Solid Footing", "The Kingpin of Crime"]
DATA = json.loads((Path(__file__).parent / "fixtures/conditional_toughness96_cards.json").read_text())
ALL = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, "main1", 1)
    return s


def cast(s, name, pid="p1", targets=(), **kwargs):
    candidates = [
        c
        for c in s.state.cards.values()
        if c.name == name
        and c.owner == pid
        and c.zone not in (f"{pid}:battlefield", "stack")
        and c.ability is None
    ]
    source = next((c for c in candidates if c.zone == f"{pid}:hand"), candidates[0])
    if source.zone != f"{pid}:hand":
        act(s, pid, type="move", card_ids=[source.id], to={"player": pid, "zone": "hand"})
    mana(s, pid, C=20, W=10, U=10, B=10, R=10, G=10)
    wait_priority(s, pid)
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), sources=[], **kwargs)
    settle(s)
    return source


def ch(s, source):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[source.id])


def empty_hands(s, *players):
    for pid in players:
        hand = list(s.state.zones.get(f"{pid}:hand", []))
        if hand:
            act(s, pid, type="move", card_ids=hand, to={"player": pid, "zone": "library"})


@pytest.mark.parametrize("name", NAMES)
def test_canonical_whole_cast(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
    s = game(cards)
    if name == "Solid Footing":
        bear = cast(s, "Grizzly Bears")
        source = cast(s, name, targets=[bear.id])
        assert ch(s, bear).pt == (3, 3)
    else:
        source = cast(s, name)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def assigned(s, source):
    from app.rules import combat

    return combat._assigns(s.state.cards[source.id], ch(s, source))


def choose(s, answer):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer])
    settle(s)


def equip(s, equipment, target):
    mana(s, "p1", C=5)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=equipment.id, ability=2, targets=[target.id], sources=[])
    settle(s)


def attack(s, *creatures, turn=4):
    to_phase(s, "declare_attackers", turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in creatures])
    settle(s)


def test_actual_bark_equip_and_combat_current_stats(cards):
    s = game(cards)
    bear = cast(s, "Grizzly Bears")
    bark = cast(s, "Bark of Doran")
    equip(s, bark, bear)
    assert ch(s, bear).pt == (2, 3) and "assign_toughness" in ch(s, bear).imposed
    attack(s, bear)
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_actual_solid_vigilance_and_combat(cards):
    s = game(cards)
    guard = cast(s, "Maritime Guard")
    cast(s, "Solid Footing", targets=[guard.id])
    assert ch(s, guard).pt == (2, 4) and "assign_toughness" not in ch(s, guard).imposed
    cast(s, "Vigilance", targets=[guard.id])
    assert ch(s, guard).pt == (2, 4) and "assign_toughness" in ch(s, guard).imposed
    attack(s, guard)
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 36
    roundtrip(s)


def test_actual_kingpin_pay_life_and_combat(cards):
    s = game(cards)
    guard = cast(s, "Maritime Guard")
    bear = cast(s, "Grizzly Bears")
    kingpin = cast(s, "The Kingpin of Crime")
    attack(s, kingpin, guard, bear)
    choose(s, "pay")
    assert s.state.players["p1"].life == 38
    assert ch(s, kingpin).pt == (1, 5) and assigned(s, kingpin) == 5
    assert ch(s, guard).pt == (1, 3) and assigned(s, guard) == 3
    assert ch(s, bear).pt == (2, 2) and assigned(s, bear) == 2
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 30
    roundtrip(s)


def test_bark_current_power_crossing_during_actual_combat(cards):
    s = game(cards)
    bear = cast(s, "Grizzly Bears")
    bark = cast(s, "Bark of Doran")
    equip(s, bark, bear)
    attack(s, bear)
    cast(s, "Trumpet Blast")
    assert ch(s, bear).pt == (4, 3) and "assign_toughness" not in ch(s, bear).imposed
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 36
    to_phase(s, "main1", 5)
    assert ch(s, bear).pt == (2, 3) and "assign_toughness" in ch(s, bear).imposed
    roundtrip(s)


def test_bark_actual_fight_uses_power_and_current_host_after_reequip(cards):
    s = game(cards)
    bear = cast(s, "Grizzly Bears")
    guard = cast(s, "Maritime Guard")
    bark = cast(s, "Bark of Doran")
    equip(s, bark, bear)
    opponent = put(s, "Maritime Guard", "battlefield", "p2")
    cast(s, "Prey Upon", targets=[bear.id, opponent.id], target_counts=[1, 1])
    assert s.state.cards[opponent.id].zone == "p2:battlefield" and s.state.cards[opponent.id].damage == 2
    equip(s, bark, guard)
    assert ch(s, bear).pt == (2, 2) and assigned(s, bear) == 2
    assert ch(s, guard).pt == (1, 4) and "assign_toughness" in ch(s, guard).imposed
    roundtrip(s)


def test_solid_current_granted_vigilance_removed_during_combat(cards):
    s = game(cards)
    guard = cast(s, "Maritime Guard")
    cast(s, "Solid Footing", targets=[guard.id])
    vigilance = cast(s, "Vigilance", targets=[guard.id])
    attack(s, guard)
    cast(s, "Disenchant", targets=[vigilance.id])
    assert ch(s, guard).pt == (2, 4) and "vigilance" not in ch(s, guard).keywords
    assert "assign_toughness" not in ch(s, guard).imposed
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_solid_printed_vigilance_removed_by_actual_spoiling(cards):
    s = game(cards)
    troops = cast(s, "Standing Troops")
    cast(s, "Solid Footing", targets=[troops.id])
    assert ch(s, troops).pt == (2, 5) and "assign_toughness" in ch(s, troops).imposed
    attack(s, troops)
    cast(s, "Sudden Spoiling", pid="p2", targets=["p1"])
    assert ch(s, troops).pt == (1, 3) and "vigilance" not in ch(s, troops).keywords
    assert "assign_toughness" not in ch(s, troops).imposed
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 39
    roundtrip(s)


def test_solid_actual_fight_still_uses_power(cards):
    s = game(cards)
    guard = cast(s, "Maritime Guard")
    cast(s, "Solid Footing", targets=[guard.id])
    cast(s, "Vigilance", targets=[guard.id])
    giant = put(s, "Hill Giant", "battlefield", "p2")
    cast(s, "Prey Upon", targets=[guard.id, giant.id], target_counts=[1, 1])
    assert ch(s, guard).pt == (2, 4) and "assign_toughness" in ch(s, guard).imposed
    assert s.state.cards[giant.id].zone == "p2:battlefield" and s.state.cards[giant.id].damage == 2
    assert s.state.cards[guard.id].zone == "p1:battlefield" and s.state.cards[guard.id].damage == 3
    roundtrip(s)


def test_kingpin_decline_leaves_actual_power_damage(cards):
    s = game(cards)
    guard = cast(s, "Maritime Guard")
    kingpin = cast(s, "The Kingpin of Crime")
    attack(s, kingpin, guard)
    choose(s, "decline")
    assert s.state.players["p1"].life == 40 and assigned(s, guard) == 1
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_kingpin_cannot_pay_two_life(cards):
    s = game(cards)
    guard = cast(s, "Maritime Guard")
    kingpin = cast(s, "The Kingpin of Crime")
    act(s, "p1", type="life", player="p1", delta=-39)
    attack(s, kingpin, guard)
    assert s.state.rules.decision is None and s.state.players["p1"].life == 1
    assert assigned(s, guard) == 1
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_kingpin_current_stats_during_combat_and_real_expiry(cards):
    s = game(cards)
    guard = cast(s, "Maritime Guard")
    kingpin = cast(s, "The Kingpin of Crime")
    attack(s, kingpin, guard)
    choose(s, "pay")
    cast(s, "Giant Growth", targets=[guard.id])
    choose(s, "decline")
    assert ch(s, guard).pt == (4, 6) and assigned(s, guard) == 6
    cast(s, "Unleash Fury", targets=[guard.id])
    choose(s, "decline")
    assert ch(s, guard).pt == (8, 6) and assigned(s, guard) == 8
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 27
    to_phase(s, "main1", 5)
    assert ch(s, guard).pt == (1, 3) and assigned(s, guard) == 1
    assert assigned(s, kingpin) == 1
    roundtrip(s)


def test_kingpin_late_flash_entrant_control_and_source_departure(cards):
    s = game(cards)
    kingpin = cast(s, "The Kingpin of Crime")
    attack(s, kingpin)
    choose(s, "pay")
    ringer = cast(s, "Village Bell-Ringer")
    choose(s, "decline")
    assert ch(s, ringer).pt == (1, 4) and assigned(s, ringer) == 4
    act(s, "p1", type="set_controller", card_ids=[ringer.id], player="p2")
    assert assigned(s, ringer) == 1
    act(s, "p2", type="set_controller", card_ids=[ringer.id], player="p1")
    assert assigned(s, ringer) == 4
    cast(s, "Murder", targets=[kingpin.id])
    choose(s, "decline")
    assert s.state.cards[kingpin.id].zone == "p1:graveyard"
    assert assigned(s, ringer) == 4
    to_phase(s, "main1", 5)
    assert assigned(s, ringer) == 1
    roundtrip(s)


def test_kingpin_canonical_extort_is_real_multiplayer_drain(cards):
    s = game(cards)
    cast(s, "The Kingpin of Crime")
    bear = cast(s, "Grizzly Bears")
    choose(s, "pay")
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert [s.state.players[p].life for p in ["p1", "p2", "p3"]] == [42, 39, 39]
    roundtrip(s)


def cold(s, tmp_path, mode, meta):
    import os
    import subprocess
    import sys

    import app

    saved = tmp_path / f"toughness96-{mode}.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_toughness96 import cast,ch,choose,attack,assigned
from tests.test_rules_designations import roundtrip
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mode=sys.argv[3];m=json.loads(sys.argv[4]);source=s.state.cards[m['source']]
if mode=='bark':
 assert ch(s,source).pt==(2,3) and 'assign_toughness' in ch(s,source).imposed
 attack(s,source);cast(s,'Trumpet Blast')
 assert ch(s,source).pt==(4,3) and 'assign_toughness' not in ch(s,source).imposed
 to_phase(s,'main2',4);assert s.state.players['p2'].life==36
elif mode=='solid':
 assert ch(s,source).pt==(2,4) and 'assign_toughness' in ch(s,source).imposed
 attack(s,source);cast(s,'Disenchant',targets=[m['vigilance']])
 assert 'assign_toughness' not in ch(s,source).imposed
 to_phase(s,'main2',4);assert s.state.players['p2'].life==38
elif mode=='pending':
 assert s.state.rules.decision is not None
 choose(s,'pay');assert s.state.players['p1'].life==38
 assert assigned(s,source)==5
 to_phase(s,'main2',4);assert s.state.players['p2'].life==32
elif mode in ('gain','lose'):
 creature=s.state.cards[m['creature']]
 if mode=='gain':
  assert ch(s,creature).pt==(3,3) and assigned(s,creature)==3
  cast(s,'Tower Defense');choose(s,'decline')
  assert ch(s,creature).pt==(3,8) and assigned(s,creature)==8
  to_phase(s,'main2',4);assert s.state.players['p2'].life==22
 else:
  assert ch(s,creature).pt==(1,3) and assigned(s,creature)==3
  cast(s,'Giant Growth',targets=[creature.id]);choose(s,'decline')
  cast(s,'Unleash Fury',targets=[creature.id]);choose(s,'decline')
  assert ch(s,creature).pt==(8,6) and assigned(s,creature)==8
  to_phase(s,'main2',4);assert s.state.players['p2'].life==27
else:
 assert assigned(s,source)==5
 ringer=cast(s,'Village Bell-Ringer');choose(s,'decline')
 assert assigned(s,ringer)==4
 cast(s,'Murder',targets=[source.id]);choose(s,'decline')
 assert s.state.cards[source.id].zone=='p1:graveyard' and assigned(s,ringer)==4
 to_phase(s,'main1',5);assert assigned(s,ringer)==1
roundtrip(s);repo.close()
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path), mode, json.dumps(meta)],
        cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["bark", "solid", "pending", "dynamic", "gain", "lose"])
def test_true_cold_current_recipient_and_payment_continuations(cards, tmp_path, mode):
    s = game(cards)
    if mode == "bark":
        source = cast(s, "Grizzly Bears")
        bark = cast(s, "Bark of Doran")
        equip(s, bark, source)
        meta = {"source": source.id}
    elif mode == "solid":
        source = cast(s, "Maritime Guard")
        cast(s, "Solid Footing", targets=[source.id])
        vigilance = cast(s, "Vigilance", targets=[source.id])
        meta = {"source": source.id, "vigilance": vigilance.id}
    elif mode == "pending":
        guard = cast(s, "Maritime Guard")
        source = cast(s, "The Kingpin of Crime")
        attack(s, source, guard)
        meta = {"source": source.id}
    elif mode in ("gain", "lose"):
        creature = cast(s, "Hill Giant" if mode == "gain" else "Maritime Guard")
        source = cast(s, "The Kingpin of Crime")
        attack(s, source, creature)
        choose(s, "pay")
        meta = {"source": source.id, "creature": creature.id}
    else:
        source = cast(s, "The Kingpin of Crime")
        attack(s, source)
        choose(s, "pay")
        meta = {"source": source.id}
    cold(s, tmp_path, mode, meta)


def test_kingpin_gains_eligibility_after_rule_begins_actual_combat(cards):
    s = game(cards)
    giant = cast(s, "Hill Giant")
    kingpin = cast(s, "The Kingpin of Crime")
    attack(s, kingpin, giant)
    choose(s, "pay")
    assert ch(s, giant).pt == (3, 3)
    cast(s, "Tower Defense")
    choose(s, "decline")
    assert ch(s, giant).pt == (3, 8) and ch(s, kingpin).pt == (1, 10)
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 22
    roundtrip(s)
