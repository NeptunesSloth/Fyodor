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

DATA = json.loads((Path(__file__).parent / "fixtures/conditional_prevention_cards.json").read_text())
NAMES = [c["name"] for c in DATA[:15]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="cps", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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


def test_avatar_count_is_equipment_controller_current_creatures(cards):
    s = game(cards)
    bear = put(s, "Centaur Courser", "battlefield", "p2")
    equipment = cast(s, "Shield of the Avatar")
    act(s, "p1", type="attach", card_ids=[equipment.id], to=bear.id)
    put(s, "Grizzly Bears", "battlefield")
    cast(s, "Lightning Bolt", [bear.id], pid="p2")
    assert s.state.cards[bear.id].damage == 2
    put(s, "Runeclaw Bear", "battlefield")
    cast(s, "Shock", [bear.id], pid="p2")
    assert s.state.cards[bear.id].damage == 2
    roundtrip(s)


def test_pegasus_applies_each_spell_recipient_but_not_ability(cards):
    s = game(cards)
    cast(s, "Plated Pegasus")
    cast(s, "Flame Rift")
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [37, 37, 37]
    source = put(s, "Thrashing Wumpus", "battlefield", "p2")
    activate(s, source, "each creature", pid="p2")
    assert s.state.players["p1"].life == 36
    roundtrip(s)


def test_well_laid_plans_creature_shared_color_not_spell(cards):
    s = game(cards)
    cast(s, "Well-Laid Plans")
    source = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    victim = put(s, "Prodigal Pyromancer", "battlefield")
    to_phase(s, "main1", turn=2)
    activate(s, source, "deals 1 damage", [victim.id], pid="p2")
    assert s.state.cards[victim.id].damage == 0
    green = put(s, "Centaur Courser", "battlefield")
    act(s, "p2", type="tap", card_ids=[source.id], tapped=False)
    activate(s, source, "deals 1 damage", [green.id], pid="p2")
    assert s.state.cards[green.id].damage == 1
    cast(s, "Shock", [green.id], pid="p2")
    assert s.state.cards[green.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_bronze_horse_only_targeting_spell_and_another_creature(cards):
    s = game(cards)
    horse = cast(s, "Bronze Horse")
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Lightning Bolt", [horse.id], pid="p2")
    assert s.state.cards[horse.id].damage == 0
    source = put(s, "Thrashing Wumpus", "battlefield", "p2")
    activate(s, source, "each creature", pid="p2")
    assert s.state.cards[horse.id].damage == 1
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Shock", [horse.id], pid="p2")
    assert s.state.cards[horse.id].damage == 3
    roundtrip(s)


def test_callous_giant_threshold_is_whole_damage_event(cards):
    s = game(cards)
    giant = cast(s, "Callous Giant")
    cast(s, "Lightning Bolt", [giant.id], pid="p2")
    assert s.state.cards[giant.id].damage == 0
    cast(s, "Furnace of Rath")
    cast(s, "Shock", [giant.id], pid="p2")
    if s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, [next(o.id for o in d.options if "Furnace" in o.label)])
    assert s.state.cards[giant.id].zone.endswith(":graveyard")
    roundtrip(s)


@pytest.mark.parametrize("kicked,n", [(False, 2), (True, 4)])
def test_orim_normal_and_actual_kicker_receipt(cards, kicked, n):
    s = game(cards)
    cast(s, "Orim's Touch", ["p1"], kicker=int(kicked))
    cast(s, "Lightning Bolt", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 40 - max(0, 3 - n)
    cast(s, "Shock", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 40 - max(0, 5 - n)
    roundtrip(s)


def test_elvish_healer_resolution_green_creature_bonus(cards):
    s = game(cards)
    healer = put(s, "Elvish Healer", "battlefield")
    victim = put(s, "Centaur Courser", "battlefield")
    to_phase(s, "main1", turn=4)
    activate(s, healer, "Prevent the next", [victim.id])
    cast(s, "Lightning Bolt", [victim.id], pid="p2")
    assert s.state.cards[victim.id].damage == 1
    roundtrip(s)


def test_hydra_spends_real_counter_before_creating_prevention(cards):
    s = game(cards)
    hydra = cast(s, "Balduvian Hydra", x_value=3)
    cast(s, "Giant Growth", [hydra.id])
    assert s.state.cards[hydra.id].counters.get("+1/+0") == 3
    activate(s, hydra, "Remove a +1/+0")
    assert s.state.cards[hydra.id].counters.get("+1/+0") == 2
    cast(s, "Shock", [hydra.id], pid="p2")
    assert s.state.cards[hydra.id].damage == 1
    roundtrip(s)


def source_choice(s, source):
    d = s.state.rules.decision
    if d is not None:
        choose(s, [next(o.id for o in d.options if o.card_id == source.id)])


def test_ajani_actual_ultimate_command_emblem_survives_source(cards):
    s = game(cards)
    ajani = cast(s, "Ajani Steadfast")
    act(s, "p1", type="set_counter", card_id=ajani.id, kind="loyalty", value=7)
    activate(s, ajani, "You get an emblem")
    assert s.state.cards[ajani.id].zone.endswith(":graveyard")
    cast(s, "Lightning Bolt", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 39
    walker = cast(s, "Ajani, the Greathearted")
    before = s.state.cards[walker.id].counters["loyalty"]
    cast(s, "Lightning Bolt", [walker.id], pid="p2")
    assert s.state.cards[walker.id].counters["loyalty"] == before - 1
    roundtrip(s)


def test_guard_dogs_colors_compared_only_when_ability_resolves(cards):
    s = game(cards)
    dogs = put(s, "Guard Dogs", "battlefield")
    attacker = put(s, "Centaur Courser", "battlefield", "p2")
    chosen = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", turn=5)
    activate(s, dogs, "Choose a permanent", [attacker.id])
    source_choice(s, chosen)
    # The chosen matching permanent can leave; the created source shield persists.
    act(s, "p1", type="move", card_ids=[chosen.id], to={"player": "p1", "zone": "graveyard"})
    attack(s, [attacker], pid="p2", target="p1", turn=5)
    damage(s)
    assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_shadow_circle_chooses_nontarget_shadow_source_and_only_next_damage(cards):
    s = game(cards)
    circle = cast(s, "Circle of Protection: Shadow")
    source = put(s, "Dauthi Marauder", "battlefield", "p2")
    to_phase(s, "main1", turn=2)
    activate(s, circle, "The next time")
    source_choice(s, source)
    attack(s, [source], pid="p2", target="p1", turn=2)
    damage(s)
    assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_spore_cloud_actual_blockers_tapped_both_sides_skip_next_untap(cards):
    s = game(cards)
    a = put(s, "Centaur Courser", "battlefield")
    b = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [a])
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id}])
    cast(s, "Spore Cloud")
    assert s.state.cards[b.id].tapped
    damage(s)
    assert s.state.cards[a.id].damage == s.state.cards[b.id].damage == 0
    to_phase(s, "upkeep", turn=5)
    assert s.state.cards[b.id].tapped
    to_phase(s, "upkeep", turn=7)
    assert s.state.cards[a.id].tapped
    to_phase(s, "upkeep", turn=8)
    assert not s.state.cards[b.id].tapped
    roundtrip(s)


def test_sphere_colored_actual_payment_selects_source_and_pays_life(cards):
    s = game(cards)
    sphere = cast(s, "Protective Sphere")
    source = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    to_phase(s, "main1", turn=2)
    # Clear all colors so the generic activation is paid with the single red mana.
    act(s, "p1", type="clear_mana")
    mana(s, R=1)
    wait_priority(s, "p1")
    ab = next(a.index for a in chars(s, sphere).abilities if "activation cost" in a.text)
    act(s, "p1", type="activate_ability", card_id=sphere.id, ability=ab, sources=[])
    settle(s)
    source_choice(s, source)
    assert s.state.players["p1"].life == 39
    activate(s, source, "deals 1 damage", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 39
    roundtrip(s)


def test_mourners_real_imprint_and_dynamic_link_existence(cards):
    s = game(cards)
    imprinted = put(s, "Lightning Bolt", "graveyard")
    source = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    shield = cast(s, "Mourner's Shield")
    # ETB target selection and optional exile use native queued choices.
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        option = next((o.id for o in d.options if o.card_id == imprinted.id), None)
        choose(s, [option or d.options[0].id])
    assert s.state.cards[imprinted.id].zone.endswith(":exile")
    to_phase(s, "main1", turn=2)
    activate(s, shield, "Prevent all damage")
    source_choice(s, source)
    activate(s, source, "deals 1 damage", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 40
    act(s, "p1", type="move", card_ids=[imprinted.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="tap", card_ids=[source.id], tapped=False)
    activate(s, source, "deals 1 damage", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 39
    roundtrip(s)


@pytest.mark.parametrize("kicked,division", [(False, [1, 2]), (True, [2, 4])])
def test_pollen_actual_divided_prevention_and_kicker_sacrifice(cards, kicked, division):
    s = game(cards)
    land = put(s, "Forest", "battlefield")
    cast(
        s,
        "Pollen Remedy",
        ["p1", "p2"],
        kicker=int(kicked),
        target_counts=[0, 2] if kicked else [2, 0],
        division=division,
    )
    if s.state.rules.decision:
        source_choice(s, land)
    assert s.state.cards[land.id].zone.endswith(":graveyard") == kicked
    cast(s, "Flame Rift")
    assert s.state.players["p1"].life == 36 + division[0]
    assert s.state.players["p2"].life == 36 + min(4, division[1])
    assert s.state.players["p3"].life == 36
    roundtrip(s)


@pytest.mark.parametrize("kicked", [False, True])
def test_pollen_any_number_explicit_zero_targets(cards, kicked):
    s = game(cards)
    land = put(s, "Forest", "battlefield")
    spell = cast(s, "Pollen Remedy", kicker=int(kicked), target_counts=[0, 0])
    if s.state.rules.decision:
        source_choice(s, land)
    assert s.state.cards[spell.id].zone.endswith(":graveyard")
    cast(s, "Lightning Bolt", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("stage", ["emblem", "sphere_choice", "linked_card", "pollen_budget"])
def test_conditional_prevention_saved_state_resumes_in_new_process(cards, tmp_path, stage):
    import subprocess
    import sys

    s = game(cards)
    ids = {}
    if stage == "emblem":
        source = cast(s, "Ajani Steadfast")
        act(s, "p1", type="set_counter", card_id=source.id, kind="loyalty", value=7)
        activate(s, source, "You get an emblem")
    elif stage == "sphere_choice":
        sphere = cast(s, "Protective Sphere")
        pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
        to_phase(s, "main1", turn=2)
        act(s, "p1", type="clear_mana")
        mana(s, R=1)
        wait_priority(s, "p1")
        ab = next(a.index for a in chars(s, sphere).abilities if "activation cost" in a.text)
        act(s, "p1", type="activate_ability", card_id=sphere.id, ability=ab, sources=[])
        settle(s)
        assert s.state.rules.decision
        ids = {"pyro": pyro.id}
    elif stage == "linked_card":
        linked = put(s, "Lightning Bolt", "graveyard")
        pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
        source = cast(s, "Mourner's Shield")
        for _ in range(4):
            d = s.state.rules.decision
            if d is None:
                break
            option = next((o.id for o in d.options if o.card_id == linked.id), None)
            choose(s, [option or d.options[0].id])
        assert s.state.cards[linked.id].zone.endswith(":exile")
        to_phase(s, "main1", turn=2)
        activate(s, source, "Prevent all damage")
        source_choice(s, pyro)
        ids = {"pyro": pyro.id, "linked": linked.id}
    else:
        cast(s, "Pollen Remedy", ["p1", "p2"], target_counts=[2, 0], division=[1, 2])
        cast(s, "Shock", ["p2"], pid="p2")
        assert s.state.players["p2"].life == 40
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
from tests.test_rules_conditional_prevention import cast,activate,source_choice
from tests.test_rules_designations import roundtrip
save,db,stage,raw=sys.argv[1:]
ids=json.loads(raw)
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if stage=='emblem':
 cast(s,'Lightning Bolt',['p1'],pid='p2')
 assert s.state.players['p1'].life==39
elif stage=='pollen_budget':
 cast(s,'Flame Rift')
 assert [s.state.players[p].life for p in ('p1','p2','p3')]==[37,36,36]
else:
 pyro=s.state.cards[ids['pyro']]
 if stage=='sphere_choice': source_choice(s,pyro)
 activate(s,pyro,'deals 1 damage',['p1'],pid='p2')
 assert s.state.players['p1'].life==(39 if stage=='sphere_choice' else 40)
 if stage=='linked_card':
  act(s,'p1',type='move',card_ids=[ids['linked']],to={'player':'p1','zone':'hand'})
  act(s,'p2',type='tap',card_ids=[pyro.id],tapped=False)
  activate(s,pyro,'deals 1 damage',['p1'],pid='p2')
  assert s.state.players['p1'].life==39
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


def test_sphere_colorless_payment_creates_no_color_wildcard(cards):
    s = game(cards)
    sphere = cast(s, "Protective Sphere")
    act(s, "p1", type="clear_mana")
    mana(s, C=1)
    wait_priority(s, "p1")
    ab = next(a.index for a in chars(s, sphere).abilities if "activation cost" in a.text)
    act(s, "p1", type="activate_ability", card_id=sphere.id, ability=ab, sources=[])
    settle(s)
    assert s.state.rules.decision is None
    cast(s, "Lightning Bolt", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 36  # pay1life, then3damage
    roundtrip(s)


def test_healer_bonus_is_resolution_snapshot_not_damage_time_color(cards):
    s = game(cards)
    healer = put(s, "Elvish Healer", "battlefield")
    victim = put(s, "Centaur Courser", "battlefield")
    to_phase(s, "main1", turn=4)
    activate(s, healer, "Prevent the next", [victim.id])
    cast(s, "Turn to Frog", [victim.id], pid="p2")
    assert "G" not in chars(s, victim).colors
    cast(s, "Shock", [victim.id], pid="p2")
    assert s.state.cards[victim.id].zone.endswith(":battlefield")
    assert s.state.cards[victim.id].damage == 0
    roundtrip(s)


def test_shadow_source_qualifier_rechecks_current_keywords(cards):
    s = game(cards)
    circle = cast(s, "Circle of Protection: Shadow")
    source = put(s, "Dauthi Marauder", "battlefield", "p2")
    to_phase(s, "main1", turn=2)
    activate(s, circle, "The next time")
    source_choice(s, source)
    cast(s, "Turn to Frog", [source.id])
    attack(s, [source], pid="p2", target="p1", turn=2)
    damage(s)
    assert s.state.players["p1"].life == 39
    roundtrip(s)


def test_pollen_illegal_target_does_not_redistribute_its_share(cards):
    s = game(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Pollen Remedy", [bear.id, "p1"], target_counts=[2, 0], division=[1, 2], resolve=False)
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "hand"})
    settle(s)
    cast(s, "Shock", ["p1"], pid="p2")
    cast(s, "Lightning Bolt", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 37
    roundtrip(s)


def test_orim_copy_keeps_kicked_amount_without_repaying_kicker(cards):
    s = game(cards)
    source = cast(s, "Orim's Touch", ["p1"], kicker=1, resolve=False)
    cast(s, "Reverberate", [source.id], pid="p2")
    while s.state.rules.decision:
        d = s.state.rules.decision
        # Keep the copied spell's original target.
        choice = next((o.id for o in d.options if "keep" in o.label.lower()), None)
        choose(s, [choice] if choice else [])
    settle(s)
    for _ in range(3):
        cast(s, "Lightning Bolt", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 39
    roundtrip(s)


def test_mourners_old_shield_record_keeps_its_original_link_after_new_incarnation(cards):
    s = game(cards)
    red = put(s, "Lightning Bolt", "graveyard")
    green = put(s, "Grizzly Bears", "graveyard")
    pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    shield = cast(s, "Mourner's Shield")
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        selected = next((o.id for o in d.options if o.card_id == red.id), None)
        choose(s, [selected or d.options[0].id])
    assert s.state.cards[red.id].zone.endswith(":exile")
    to_phase(s, "main1", turn=4)
    activate(s, shield, "Prevent all damage")
    source_choice(s, pyro)
    act(s, "p1", type="move", card_ids=[shield.id], to={"player": "p1", "zone": "graveyard"})
    shield = cast(s, "Mourner's Shield")
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        selected = next((o.id for o in d.options if o.card_id == green.id), None)
        choose(s, [selected or d.options[0].id])
    assert s.state.cards[green.id].zone.endswith(":exile")
    activate(s, pyro, "deals 1 damage", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 40
    roundtrip(s)
