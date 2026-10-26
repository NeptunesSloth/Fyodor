"""Saved native choices retain exact history operands and cost exclusions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_rules_conditional_prevention import cast
from tests.test_rules_damage_history_outcomes import cards as cards
from tests.test_rules_damage_history_outcomes import game
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_wave30m_durations import to_phase


def cold(s, tmp_path, stage, ids):
    saved = tmp_path / "state.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage=sys.argv[3];ids=json.loads(sys.argv[4])
assert s.state.rules.decision is not None
if stage=='reckoning':
    pick(s,['yes']);settle(s)
    assert s.state.cards[ids['old']].zone=='p1:library'
    assert s.state.cards[ids['victim']].damage==2
elif stage=='hunger':
    assert s.state.rules.decision.player=='p2'
    pick(s,['pay']);settle(s)
    d=s.state.rules.decision
    assert d is not None and ids['host'] not in [o.id for o in d.options]
    pick(s,[ids['other']]);settle(s)
    assert s.state.players['p2'].life==40
    assert s.state.cards[ids['host']].zone=='p2:battlefield'
    assert s.state.cards[ids['other']].zone=='p2:graveyard'
elif stage=='sentinel':
    pick(s,['p3']);settle(s)
    assert s.state.players['p3'].life==37
    assert s.state.players['p2'].life==35
elif stage=='builder':
    assert all(s.state.cards[c].zone.endswith(':graveyard') for c in ids['artifacts'])
    assert all(p.life==40 for p in s.state.players.values())
    for _ in range(12):
        d=s.state.rules.decision
        if d is None:break
        choice=next((o.id for o in d.options if 'Furnace' in o.label),d.options[0].id)
        pick(s,[choice]);settle(s)
    assert [s.state.players[p].life for p in ['p1','p2','p3']]==[38,36,36]
assert s.state.rules.decision is None
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path), stage, json.dumps(ids)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("stage", ["reckoning", "hunger", "sentinel", "builder"])
def test_actual_pending_native_choices_resume_in_fresh_engine(cards, tmp_path, stage):
    s = game(cards)
    if stage == "reckoning":
        old = put(s, "Lhurgoyf", "graveyard")
        put(s, "Grizzly Bears", "graveyard", "p2")
        victim = put(s, "Colossal Dreadmaw", "battlefield", "p3")
        cast(s, "Dead Reckoning", [old.id, victim.id], target_counts=[1, 1])
        ids = {"old": old.id, "victim": victim.id}
    elif stage == "hunger":
        host = put(s, "Colossal Dreadmaw", "battlefield", "p2")
        other = put(s, "Grizzly Bears", "battlefield", "p2")
        put(s, "Runeclaw Bear", "battlefield", "p2")
        cast(s, "Unnatural Hunger", [host.id])
        to_phase(s, "upkeep", turn=5)
        settle(s)
        ids = {"host": host.id, "other": other.id}
    elif stage == "sentinel":
        cast(s, "Sentinel Tower")
        cast(s, "Lightning Bolt", ["p2"], resolve=False)
        pick(s, ["p3"])
        settle(s)
        cast(s, "Shock", ["p2"], resolve=False)
        ids = {}
    else:
        cast(s, "Furnace of Rath")
        cast(s, "Torbran, Thane of Red Fell")
        artifacts = [put(s, "Sol Ring", "battlefield", p) for p in ["p1", "p2", "p3"]]
        cast(s, "Builder's Bane", [c.id for c in artifacts], x_value=3, target_counts=[3])
        ids = {"artifacts": [c.id for c in artifacts]}
    assert s.state.rules.decision is not None
    cold(s, tmp_path, stage, ids)


def test_hunger_departed_aura_keeps_original_host_exclusion(cards):
    s = game(cards)
    host = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    other = put(s, "Grizzly Bears", "battlefield", "p2")
    aura = cast(s, "Unnatural Hunger", [host.id])
    to_phase(s, "upkeep", turn=5)
    # A real instant removes the source in response to its captured upkeep trigger.
    cast(s, "Disenchant", [aura.id])
    settle(s)
    pick(s, ["pay"])
    settle(s)
    if s.state.rules.decision:
        assert host.id not in [o.id for o in s.state.rules.decision.options]
        pick(s, [other.id])
        settle(s)
    assert s.state.cards[other.id].zone == "p2:graveyard"
    assert s.state.cards[host.id].zone == "p2:battlefield"
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_hunger_new_host_incarnation_is_eligible_other_creature(cards):
    s = game(cards)
    host = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    original = s.state.rules.object_id(host.id)
    aura = cast(s, "Unnatural Hunger", [host.id])
    to_phase(s, "upkeep", turn=5)
    cast(s, "Cloudshift", [host.id], pid="p2")
    assert s.state.rules.object_id(host.id) != original
    assert s.state.cards[aura.id].zone == "p1:graveyard"
    assert s.state.rules.decision is not None
    pick(s, ["pay"])
    settle(s)
    if s.state.rules.decision:
        pick(s, [host.id])
        settle(s)
    assert s.state.cards[host.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_hunger_cannot_offer_opponent_prohibited_sacrifice_payment(cards):
    s = game(cards)
    host = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    put(s, "Sigarda, Host of Herons", "battlefield", "p2")
    put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, "Unnatural Hunger", [host.id])
    to_phase(s, "upkeep", turn=5)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players["p2"].life == 34
    roundtrip(s)


@pytest.mark.parametrize("kind", ["creature", "enchantment"])
def test_justice_red_creature_and_noncreature_permanent_sources_are_distinct(cards, kind):
    from tests.test_rules_conditional_prevention import activate

    s = game(cards)
    cast(s, "Justice")
    if kind == "creature":
        source = cast(s, "Prodigal Pyromancer")
        activate(s, source, "damage", ["p2"])
    else:
        source = cast(s, "Goblin Bombardment")
        put(s, "Grizzly Bears", "battlefield")
        activate(s, source, "damage", ["p2"])
    assert s.state.players["p2"].life == 39
    assert s.state.players["p1"].life == (39 if kind == "creature" else 40)
    roundtrip(s)


def test_spirit_flare_real_flashback_pays_life_and_exiles_after_second_damage(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority

    s = game(cards)
    own = put(s, "Grizzly Bears", "battlefield")
    second = put(s, "Runeclaw Bear", "battlefield")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    to_phase(s, "declare_attackers", turn=5)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": target.id, "target": "p1"}])
    spell = cast(s, "Spirit Flare", [own.id, target.id], target_counts=[1, 1])
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    mana(s, C=10, W=3)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        targets=[second.id, target.id],
        target_counts=[1, 1],
        sources=[],
    )
    settle(s)
    assert s.state.cards[target.id].damage == 4
    assert s.state.cards[spell.id].zone == "p1:exile"
    assert s.state.players["p1"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("case", ["indestructible", "replacement", "decline"])
def test_tuktuk_destroy_followup_requires_actual_graveyard_death(cards, case):
    s = game(cards)
    if case == "replacement":
        cast(s, "Rest in Peace")
    target = put(s, "Darksteel Relic" if case == "indestructible" else "Sol Ring", "battlefield", "p2")
    cast(s, "Tuktuk Scrapper")
    pick(s, [target.id])
    settle(s)
    pick(s, ["no" if case == "decline" else "yes"])
    settle(s)
    assert s.state.players["p2"].life == 40
    assert s.state.cards[target.id].zone == ("p2:exile" if case == "replacement" else "p2:battlefield")
    roundtrip(s)


def test_dead_reckoning_optional_decline_keeps_card_and_deals_no_damage(cards):
    s = game(cards)
    old = put(s, "Grizzly Bears", "graveyard")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    cast(s, "Dead Reckoning", [old.id, target.id], target_counts=[1, 1])
    pick(s, ["no"])
    settle(s)
    assert s.state.cards[old.id].zone == "p1:graveyard"
    assert s.state.cards[target.id].damage == 0
    roundtrip(s)


def test_catapult_x_less_than_creature_count_deals_zero(cards):
    s = game(cards)
    targets = [
        put(s, n, "battlefield", "p2") for n in ["Grizzly Bears", "Runeclaw Bear", "Colossal Dreadmaw"]
    ]
    cast(s, "Dwarven Catapult", ["p2"], x_value=2)
    assert all(s.state.cards[c.id].damage == 0 for c in targets)
    roundtrip(s)


@pytest.mark.parametrize("gone", ["card", "creature"])
def test_dead_reckoning_with_one_illegal_target_still_does_what_the_other_allows(cards, gone):
    """608.2b: a spell with an illegal target still resolves for the legal one. The card gone: it is not put on top (no damage); the creature gone: the
    card is still put on top and no damage can be dealt."""
    from tests.game_helpers import act

    s = game(cards)
    old = put(s, "Grizzly Bears", "graveyard")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    cast(s, "Dead Reckoning", [old.id, target.id], target_counts=[1, 1], resolve=False)
    moved = old if gone == "card" else target
    act(s, "p1", type="move", card_ids=[moved.id], to={"player": moved.owner, "zone": "exile"})
    settle(s)
    if s.state.rules.decision is not None:
        pick(s, ["yes"])
        settle(s)
    assert s.state.cards[old.id].zone == ("p1:exile" if gone == "card" else "p1:library")
    assert s.state.cards[target.id].damage == 0
    roundtrip(s)
