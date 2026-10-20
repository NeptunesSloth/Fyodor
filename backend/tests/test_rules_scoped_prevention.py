"""Canonical scoped prevention follows exact objects, dynamic classes and native budgets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/scoped_prevention_cards.json").read_text())
NAMES = [c["name"] for c in DATA[:18]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="sps", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = [c["name"] for c in DATA]
    return table(cards, names, names, names)


def choose(s, values):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=values)
    settle(s)


def cast(s, name, targets=(), pid="p1", resolve=True, **kwargs):
    source = put(s, name, "hand", pid)
    mana(s, pid=pid, C=30, W=8, U=8, B=8, R=8, G=8)
    wait_priority(s, pid)
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), sources=[], **kwargs)
    if resolve:
        settle(s)
    return source


def activate(s, source, text, targets=(), pid="p1", resolve=True):
    mana(s, pid=pid, C=10, W=3, U=3, B=3, R=3, G=3)
    wait_priority(s, pid)
    ab = next(a.index for a in chars(s, source).abilities if text in a.text)
    act(s, pid, type="activate_ability", card_id=source.id, ability=ab, targets=list(targets), sources=[])
    if resolve:
        settle(s)


def attack(s, attackers, *, pid="p1", target="p2", turn=4):
    to_phase(s, "declare_attackers", turn=turn)
    act(s, pid, type="declare_attackers", attackers=[{"card_id": a.id, "target": target} for a in attackers])
    settle(s)


def damage(s):
    to_phase(s, "combat_damage")
    settle(s)


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result.manual_parts


@pytest.mark.parametrize("name", ["Kiora, the Crashing Wave", "Dovin, Hand of Control"])
def test_real_loyalty_protects_both_sides_through_opponent_turn(cards, name):
    s = game(cards)
    source = cast(s, name)
    target = put(s, "Thrashing Wumpus", "battlefield", "p2")
    activate(s, source, "Until your next turn", [target.id])
    activate(s, target, "each creature", pid="p2")
    assert s.state.cards[target.id].damage == 0
    assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 40
    # Source leaving cannot end an already-created next-turn shield.
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "upkeep", turn=2)
    cast(s, "Lightning Bolt", [target.id], pid="p2")
    assert s.state.cards[target.id].damage == 0
    roundtrip(s)


def test_energy_arc_untaps_and_protects_both_sides_of_actual_combat(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    attack(s, [a])
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id}])
    cast(s, "Energy Arc", [a.id], target_counts=[1])
    assert not s.state.cards[a.id].tapped
    damage(s)
    assert s.state.cards[a.id].damage == 0 and s.state.cards[b.id].damage == 0
    roundtrip(s)


def test_terrifying_presence_leaves_only_target_combat_damage(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Centaur Courser", "battlefield")
    attack(s, [a, b])
    cast(s, "Terrifying Presence", [a.id])
    damage(s)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_moonmist_transforms_actual_human_and_checks_creature_types_when_damage_happens(cards):
    s = game(cards)
    human = put(s, "Delver of Secrets // Insectile Aberration", "battlefield")
    cast(s, "Moonmist")
    assert s.state.cards[human.id].face == 1
    to_phase(s, "main1", turn=4)
    cast(s, "Moonmist")
    # These creatures enter after resolution; the dynamic class still applies.
    later = put(s, "Centaur Courser", "battlefield")
    wolf = put(s, "Young Wolf", "battlefield")
    put(s, "Fervor", "battlefield")
    attack(s, [later, wolf])
    damage(s)
    assert s.state.players["p2"].life == 39
    roundtrip(s)


def test_inspire_awe_dynamic_enchanted_and_enchantment_exceptions(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Centaur Courser", "battlefield")
    enchantment = put(s, "Courser of Kruphix", "battlefield")
    aura = cast(s, "Rancor", [a.id])
    attack(s, [a, b, enchantment])
    cast(s, "Inspire Awe")
    # Finish native scry privately, before the prevention can matter.
    if s.state.rules.decision:
        choose(s, [])
    act(s, "p1", type="attach", card_ids=[aura.id], to=b.id)
    damage(s)
    assert s.state.players["p2"].life == 33  # enchanted Bear4 + enchantment Courser2
    roundtrip(s)


def test_wellgabber_real_activation_protects_original_tapped_tribal_target_after_untap(cards):
    s = game(cards)
    source = put(s, "Wellgabber Apothecary", "battlefield")
    target = put(s, "Merfolk Looter", "battlefield")
    act(s, "p1", type="tap", card_ids=[target.id], tapped=True)
    activate(s, source, "Prevent all damage", [target.id])
    act(s, "p1", type="tap", card_ids=[target.id], tapped=False)
    cast(s, "Lightning Bolt", [target.id])
    assert s.state.cards[target.id].zone == "p1:battlefield" and s.state.cards[target.id].damage == 0
    roundtrip(s)


def test_blinding_powder_real_granted_unattach_cost_protects_host(cards):
    s = game(cards)
    powder = put(s, "Blinding Powder", "battlefield")
    host = put(s, "Grizzly Bears", "battlefield")
    blocker = put(s, "Centaur Courser", "battlefield", "p2")
    act(s, "p1", type="attach", card_ids=[powder.id], to=host.id)
    attack(s, [host])
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": host.id}])
    activate(s, host, "Unattach")
    assert s.state.cards[powder.id].attached_to is None
    damage(s)
    assert s.state.cards[host.id].zone == "p1:battlefield" and s.state.cards[host.id].damage == 0
    assert s.state.cards[blocker.id].damage == 2
    roundtrip(s)


def test_cautery_sliver_real_granted_sacrifice_cost_protects_player(cards):
    s = game(cards)
    source = put(s, "Cautery Sliver", "battlefield")
    other = put(s, "Muscle Sliver", "battlefield")
    activate(s, other, "Prevent the next", ["p1"])
    assert s.state.cards[other.id].zone == "p1:graveyard"
    cast(s, "Lightning Bolt", ["p1"])
    assert s.state.players["p1"].life == 38
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_griffin_scoped_budget_ignores_noncombat_then_prevents_only_one_combat_damage(cards):
    s = game(cards)
    source = put(s, "Decorated Griffin", "battlefield")
    a = put(s, "Centaur Courser", "battlefield", "p2")
    attack(s, [a], pid="p2", target="p1", turn=2)
    activate(s, source, "Prevent the next")
    cast(s, "Shock", ["p1"])
    assert s.state.players["p1"].life == 38
    damage(s)
    assert s.state.players["p1"].life == 36
    roundtrip(s)


def test_barbed_wire_budget_is_consumed_by_original_source_only(cards):
    s = game(cards)
    source = put(s, "Barbed Wire", "battlefield")
    to_phase(s, "upkeep", turn=2)
    activate(s, source, "Prevent the next")
    assert s.state.players["p2"].life == 40
    cast(s, "Shock", ["p2"])
    assert s.state.players["p2"].life == 38
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert s.state.players["p3"].life == 39
    roundtrip(s)


def test_healing_grace_source_choice_and_immediate_life_then_shared_remaining_budget(cards):
    s = game(cards)
    pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    to_phase(s, "main1", turn=2)
    cast(s, "Healing Grace", ["p1"])
    d = s.state.rules.decision
    choice = next(o.id for o in d.options if o.card_id == pyro.id)
    choose(s, [choice])
    assert s.state.players["p1"].life == 43
    for _ in range(4):
        if s.state.cards[pyro.id].tapped:
            act(s, "p2", type="tap", card_ids=[pyro.id], tapped=False)
        activate(s, pyro, "deals 1 damage", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 42
    roundtrip(s)


def test_dazzling_reflection_immediate_life_and_one_shot_source_prevention(cards):
    s = game(cards)
    source = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    to_phase(s, "main1", turn=2)
    cast(s, "Dazzling Reflection", [source.id])
    assert s.state.players["p1"].life == 41
    activate(s, source, "deals 1 damage", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 41
    act(s, "p2", type="tap", card_ids=[source.id], tapped=False)
    activate(s, source, "deals 1 damage", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_ajani_aid_sacrifices_then_nontarget_choice_of_combat_source(cards):
    s = game(cards)
    source = put(s, "Ajani's Aid", "battlefield")
    a = put(s, "Centaur Courser", "battlefield")
    b = put(s, "Grizzly Bears", "battlefield")
    attack(s, [a, b])
    activate(s, source, "Sacrifice")
    assert s.state.cards[source.id].zone == "p1:graveyard"
    choose(s, [a.id])
    damage(s)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_shieldmage_real_tap_wizards_cost_prevents_target_spell_damage(cards):
    s = game(cards)
    source = put(s, "Shieldmage Elder", "battlefield", "p2")
    w1 = put(s, "Prodigal Sorcerer", "battlefield", "p2")
    w2 = put(s, "Merfolk Looter", "battlefield", "p2")
    bolt = cast(s, "Lightning Bolt", ["p2"], resolve=False)
    activate(s, source, "target spell", [bolt.id], pid="p2")
    assert s.state.cards[w1.id].tapped and s.state.cards[source.id].tapped
    assert not s.state.cards[w2.id].tapped
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_forcefield_real_unblocked_choice_leaves_one_damage_and_other_attacker_unaffected(cards):
    s = game(cards)
    source = put(s, "Forcefield", "battlefield")
    a = put(s, "Siege Mastodon", "battlefield", "p2")
    b = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [a, b], pid="p2", target="p1", turn=2)
    to_phase(s, "declare_blockers")
    if s.state.rules.decision and s.state.rules.decision.kind == "declare_blockers":
        act(s, "p1", type="declare_blockers", blocks=[])
    activate(s, source, "The next time")
    choose(s, [a.id])
    damage(s)
    assert s.state.players["p1"].life == 37
    roundtrip(s)


def test_feint_taps_actual_blockers_and_prevents_both_sources_combat_damage(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    attack(s, [a])
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id}])
    cast(s, "Feint", [a.id])
    assert s.state.cards[b.id].tapped
    damage(s)
    assert s.state.cards[a.id].damage == 0 and s.state.cards[b.id].damage == 0
    roundtrip(s)


def test_sewers_actual_blocking_creature_and_its_attacker_are_shielded_until_endcombat(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    attack(s, [a])
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id}])
    cast(s, "Sewers of Estark", [b.id])
    damage(s)
    assert s.state.cards[a.id].damage == 0 and s.state.cards[b.id].damage == 0
    to_phase(s, "main2")
    assert not any(rec.get("until") == "end_of_combat" for rec in s.state.rules.replacements)
    roundtrip(s)


def test_griffin_simultaneous_sources_native_which_damage_choice_controls_lifelink(cards):
    s = game(cards)
    source = put(s, "Decorated Griffin", "battlefield")
    hawk = put(s, "Healer's Hawk", "battlefield", "p2")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [hawk, bear], pid="p2", target="p1", turn=2)
    activate(s, source, "Prevent the next")
    damage(s)
    d = s.state.rules.decision
    assert d and d.player == "p1" and "615.7" in d.prompt
    choose(s, [next(o.id for o in d.options if o.card_id == hawk.id)])
    assert s.state.players["p1"].life == 38
    assert s.state.players["p2"].life == 40  # Hawk dealt zero, so no lifelink
    roundtrip(s)


def test_unpreventable_damage_does_not_consume_scoped_budget(cards):
    s = game(cards)
    source = put(s, "Decorated Griffin", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [bear], pid="p2", target="p1", turn=2)
    activate(s, source, "Prevent the next")
    cast(s, "Skullcrack", ["p1"], pid="p2")
    damage(s)
    assert s.state.players["p1"].life == 35
    assert any(key.startswith("scoped:") and n == 1 for key, n in s.state.rules.prevention.items())
    roundtrip(s)


def test_shieldmage_targeted_permanent_spell_covers_the_actual_entered_damage_source(cards):
    s = game(cards)
    source = put(s, "Shieldmage Elder", "battlefield", "p2")
    put(s, "Prodigal Sorcerer", "battlefield", "p2")
    bear = put(s, "Siege Mastodon", "battlefield", "p2")
    spell = cast(s, "Flametongue Kavu", resolve=False)
    activate(s, source, "target spell", [spell.id], pid="p2")
    d = s.state.rules.decision
    assert d and bear.id in {o.id for o in d.options}
    choose(s, [bear.id])
    assert s.state.cards[spell.id].zone == "p1:battlefield"
    assert s.state.cards[bear.id].damage == 0
    roundtrip(s)


def test_sewers_attacking_branch_native_unblockable_and_noncombat_source_not_prevented(cards):
    s = game(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    attack(s, [bear])
    cast(s, "Sewers of Estark", [bear.id])
    assert "unblockable" in chars(s, bear).imposed
    damage(s)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_loyalty_shield_does_not_follow_a_new_target_incarnation(cards):
    s = game(cards)
    source = cast(s, "Kiora, the Crashing Wave")
    target = put(s, "Thrashing Wumpus", "battlefield", "p2")
    activate(s, source, "Until your next turn", [target.id])
    act(s, "p2", type="move", card_ids=[target.id], to={"player": "p2", "zone": "exile"})
    act(s, "p2", type="move", card_ids=[target.id], to={"player": "p2", "zone": "battlefield"})
    cast(s, "Lightning Bolt", [target.id])
    assert s.state.cards[target.id].zone == "p2:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("stage", ["source_choice", "remaining_budget", "source_order", "next_turn"])
def test_native_prevention_states_resume_in_fresh_process(cards, tmp_path, stage):
    import subprocess
    import sys

    s = game(cards)
    ids = {}
    if stage in ("source_choice", "remaining_budget"):
        pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
        to_phase(s, "main1", turn=2)
        cast(s, "Healing Grace", ["p1"])
        ids = {"pyro": pyro.id}
        if stage == "remaining_budget":
            d = s.state.rules.decision
            choose(s, [next(o.id for o in d.options if o.card_id == pyro.id)])
            activate(s, pyro, "deals 1 damage", ["p1"], pid="p2")
            assert s.state.players["p1"].life == 43
            assert any(
                key.startswith("scoped:") and value == 2 for key, value in s.state.rules.prevention.items()
            )
    elif stage == "source_order":
        source = put(s, "Decorated Griffin", "battlefield")
        hawk = put(s, "Healer's Hawk", "battlefield", "p2")
        bear = put(s, "Grizzly Bears", "battlefield", "p2")
        attack(s, [hawk, bear], pid="p2", target="p1", turn=2)
        activate(s, source, "Prevent the next")
        damage(s)
        assert s.state.rules.decision and "615.7" in s.state.rules.decision.prompt
        ids = {"hawk": hawk.id}
    else:
        source = cast(s, "Kiora, the Crashing Wave")
        target = put(s, "Thrashing Wumpus", "battlefield", "p2")
        activate(s, source, "Until your next turn", [target.id])
        act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
        ids = {"target": target.id}
    saved = tmp_path / f"{stage}.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_scoped_prevention import choose,activate,cast
from tests.test_rules_designations import roundtrip
from tests.test_rules_wave30m_durations import to_phase
save,db,stage,raw=sys.argv[1:]
ids=json.loads(raw)
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if stage in ('source_choice','remaining_budget'):
 pyro=s.state.cards[ids['pyro']]
 if stage=='source_choice':
  d=s.state.rules.decision
  choose(s,[next(o.id for o in d.options if o.card_id==pyro.id)])
  assert s.state.players['p1'].life==43
 for _ in range(4 if stage=='source_choice' else 3):
  if s.state.cards[pyro.id].tapped:act(s,'p2',type='tap',card_ids=[pyro.id],tapped=False)
  activate(s,pyro,'deals 1 damage',['p1'],pid='p2')
 assert s.state.players['p1'].life==42
elif stage=='source_order':
 d=s.state.rules.decision
 choose(s,[next(o.id for o in d.options if o.card_id==ids['hawk'])])
 assert s.state.players['p1'].life==38 and s.state.players['p2'].life==40
else:
 to_phase(s,'main1',turn=2)
 cast(s,'Shock',[ids['target']],pid='p2')
 assert s.state.cards[ids['target']].damage==0
 to_phase(s,'main1',turn=4)
 cast(s,'Shock',[ids['target']])
 assert s.state.cards[ids['target']].damage==2
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage, json.dumps(ids)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_terrifying_presence_illegal_target_prevents_nothing(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Centaur Courser", "battlefield")
    attack(s, [a, b])
    cast(s, "Terrifying Presence", [a.id], resolve=False)
    act(s, "p1", type="move", card_ids=[a.id], to={"player": "p1", "zone": "hand"})
    settle(s)
    damage(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_energy_arc_zero_targets_is_a_legal_spell_and_makes_no_global_shield(cards):
    s = game(cards)
    a = put(s, "Centaur Courser", "battlefield")
    attack(s, [a])
    cast(s, "Energy Arc", [], target_counts=[0])
    damage(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_dazzling_two_one_shot_shields_leave_the_second_for_the_next_damage_event(cards):
    s = game(cards)
    source = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    to_phase(s, "main1", turn=2)
    cast(s, "Dazzling Reflection", [source.id])
    cast(s, "Dazzling Reflection", [source.id])
    assert s.state.players["p1"].life == 42
    for n in range(3):
        if s.state.cards[source.id].tapped:
            act(s, "p2", type="tap", card_ids=[source.id], tapped=False)
        activate(s, source, "deals 1 damage", ["p1"], pid="p2")
        if s.state.rules.decision:
            choose(s, [s.state.rules.decision.options[0].id])
        assert s.state.players["p1"].life == (42 if n < 2 else 41)
    roundtrip(s)


def test_wellgabber_nontribal_or_untapped_target_is_illegal(cards):
    from app.game.errors import ActionError

    s = game(cards)
    source = put(s, "Wellgabber Apothecary", "battlefield")
    wrong = put(s, "Grizzly Bears", "battlefield")
    merfolk = put(s, "Merfolk Looter", "battlefield")
    for target in (wrong, merfolk):
        with pytest.raises(ActionError):
            activate(s, source, "Prevent all damage", [target.id])


def test_forcefield_excludes_blocked_trampler_and_never_targets_the_chosen_creature(cards):
    s = game(cards)
    source = put(s, "Forcefield", "battlefield", "p2")
    attacker = put(s, "Centaur Courser", "battlefield")
    blocker = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, "Rancor", [attacker.id])
    attack(s, [attacker])
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    activate(s, source, "The next time", pid="p2")
    assert s.state.rules.decision is None  # no unblocked creature to choose
    damage(s)
    if s.state.rules.decision:
        d = s.state.rules.decision
        assert d.kind == "divide"
        act(
            s,
            d.player,
            type="choose",
            decision_id=d.id,
            amounts=[2 if o.card_id == blocker.id else 3 for o in d.options],
        )
        settle(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_source_only_budget_is_shared_across_native_simultaneous_recipient_events(cards):
    # Barbed Wire's printed upkeep hits one recipient. This native planner unit
    # also verifies the generic source-only budget never multiplies per recipient.
    from app.rules import replace
    from app.rules.plan import Plan

    s = game(cards)
    source = put(s, "Barbed Wire", "battlefield")
    activate(s, source, "Prevent the next")
    plan = Plan(s.state.model_copy(deep=True), "p1", s.cards, None)
    oid = plan.oid(source.id)
    info = replace.source_info(plan, source.id, oid, plan.ch(plan.state.cards[source.id]), "p1")
    events = [
        {
            "source_card": source.id,
            "source_oid": oid,
            "src": info,
            "target": pid,
            "amount": 1,
            "combat": False,
        }
        for pid in ("p3", "p2", "p1")
    ]
    result = replace.plan_damage(plan, events, answers={}, order=None, ask=True)
    assert isinstance(result, replace.DamagePlan)
    assert len(result.events) == 3 and sum(e["amount"] for e in result.events) == 2
    assert next(e for e in result.events if e["target"] == "p1")["amount"] == 0
    assert sum(value for key, value in result.shields.items() if key.startswith("scoped:")) == 0
