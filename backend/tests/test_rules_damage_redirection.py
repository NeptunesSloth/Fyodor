"""Canonical scoped prevention follows exact objects, dynamic classes and native budgets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/damage_redirection_cards.json").read_text())
NAMES = [c["name"] for c in DATA[:15]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="red", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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


def activate(s, source, text, targets=(), pid="p1", resolve=True, **kwargs):
    mana(s, pid=pid, C=10, W=3, U=3, B=3, R=3, G=3)
    wait_priority(s, pid)
    ab = next(a.index for a in chars(s, source).abilities if text in a.text)
    act(
        s,
        pid,
        type="activate_ability",
        card_id=source.id,
        ability=ab,
        targets=list(targets),
        sources=[],
        **kwargs,
    )
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
def test_canonical_ordinary_cards_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result.manual_parts


def choose_source(s, source):
    if d := s.state.rules.decision:
        choose(s, [next(o.id for o in d.options if o.card_id == source.id)])


def test_mirror_strike_actual_unblocked_attacker_damages_its_controller(cards):
    s = game(cards)
    attacker = put(s, "Centaur Courser", "battlefield", "p2")
    attack(s, [attacker], pid="p2", target="p1", turn=2)
    to_phase(s, "declare_blockers")
    if (d := s.state.rules.decision) and d.kind == "declare_blockers":
        act(s, d.player, type="declare_blockers", blocks=[])
    settle(s)
    cast(s, "Mirror Strike", [attacker.id])
    damage(s)
    assert s.state.players["p1"].life == 40
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_turn_tables_redirects_all_attackers_to_named_attacking_creature(cards):
    s = game(cards)
    big = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    small = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [big, small], pid="p2", target="p1", turn=2)
    cast(s, "Turn the Tables", [big.id])
    damage(s)
    assert s.state.players["p1"].life == 40
    assert s.state.cards[big.id].zone.endswith(":graveyard")
    roundtrip(s)


@pytest.mark.parametrize("name", ["Kor Dirge", "Kor Chant"])
def test_kor_pair_targets_and_later_nontarget_source_choice(cards, name):
    s = game(cards)
    protected = put(s, "Grizzly Bears", "battlefield")
    other = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    to_phase(s, "main1", turn=2)
    cast(s, name, [protected.id, other.id], target_counts=[1, 1])
    assert s.state.rules.decision
    choose_source(s, pyro)
    for _ in range(2):
        if s.state.cards[pyro.id].tapped:
            act(s, "p2", type="tap", card_ids=[pyro.id], tapped=False)
        activate(s, pyro, "deals 1 damage", [protected.id], pid="p2")
    assert s.state.cards[protected.id].damage == 0
    assert s.state.cards[other.id].damage == 2
    roundtrip(s)


def test_attendants_protect_target_from_chosen_source_repeatedly(cards):
    s = game(cards)
    guard = put(s, "Oracle's Attendants", "battlefield")
    protected = put(s, "Grizzly Bears", "battlefield")
    pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
    to_phase(s, "main1", turn=4)
    activate(s, guard, "All damage", [protected.id])
    choose_source(s, pyro)
    for _ in range(2):
        if s.state.cards[pyro.id].tapped:
            act(s, "p2", type="tap", card_ids=[pyro.id], tapped=False)
        activate(s, pyro, "deals 1 damage", [protected.id], pid="p2")
    assert s.state.cards[protected.id].damage == 0
    assert s.state.cards[guard.id].damage == 2
    roundtrip(s)


def test_reverberation_whole_sorcery_batch_sums_to_spell_controller(cards):
    s = game(cards)
    to_phase(s, "main1", turn=2)
    source = cast(s, "Flame Rift", pid="p2", resolve=False)
    cast(s, "Reverberation", [source.id])
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [40, 28, 40]
    roundtrip(s)


def test_kjeldoran_guard_takes_unblocked_attacker_combat_damage(cards):
    s = game(cards)
    guard = put(s, "Kjeldoran Royal Guard", "battlefield")
    attacker = put(s, "Centaur Courser", "battlefield", "p2")
    attack(s, [attacker], pid="p2", target="p1", turn=5)
    activate(s, guard, "All combat damage")
    damage(s)
    assert s.state.players["p1"].life == 40
    assert s.state.cards[guard.id].damage == 3
    roundtrip(s)


def test_stalker_targets_attacking_source_and_takes_its_damage(cards):
    s = game(cards)
    guard = put(s, "Shimian Night Stalker", "battlefield")
    attacker = put(s, "Centaur Courser", "battlefield", "p2")
    attack(s, [attacker], pid="p2", target="p1", turn=5)
    activate(s, guard, "All damage", [attacker.id])
    damage(s)
    assert s.state.players["p1"].life == 40
    assert s.state.cards[guard.id].damage == 3
    roundtrip(s)


def test_incarnation_owner_can_activate_under_opponents_control(cards):
    s = game(cards)
    source = put(s, "Personal Incarnation", "battlefield")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    with pytest.raises(ActionError):
        activate(s, source, "The next 1", pid="p2")
    activate(s, source, "The next 1")
    cast(s, "Lightning Bolt", [source.id], pid="p3")
    assert s.state.cards[source.id].damage == 2
    assert s.state.players["p1"].life == 39
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_martyrdom_only_original_caster_activates_after_control_change(cards):
    s = game(cards)
    source = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Martyrdom", [source.id])
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    with pytest.raises(ActionError):
        activate(s, source, "The next 1", ["p3"], pid="p2")
    activate(s, source, "The next 1", ["p3"])
    cast(s, "Shock", ["p3"], pid="p3")
    assert s.state.players["p3"].life == 39
    assert s.state.cards[source.id].damage == 1
    roundtrip(s)


@pytest.mark.parametrize("redirect", [False, True])
def test_flaming_gambit_target_controller_chooses_own_creature_or_declines(cards, redirect):
    s = game(cards)
    own = put(s, "Grizzly Bears", "battlefield")
    other = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    cast(s, "Flaming Gambit", ["p2"], x_value=3)
    d = s.state.rules.decision
    assert d and d.player == "p2"
    assert other.id in {o.card_id for o in d.options} and own.id not in {o.card_id for o in d.options}
    choose(s, [other.id] if redirect else [])
    assert s.state.cards[other.id].damage == (3 if redirect else 0)
    assert s.state.players["p2"].life == (40 if redirect else 37)
    roundtrip(s)


def test_ascent_nontarget_creature_choice_redirects_until_casters_next_turn(cards):
    s = game(cards)
    chosen = put(s, "Colossal Dreadmaw", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Ascent of the Worthy")
    choose_source(s, chosen)
    cast(s, "Lightning Bolt", [bear.id], pid="p2")
    assert s.state.cards[bear.id].damage == 0
    assert s.state.cards[chosen.id].damage == 3
    to_phase(s, "main1", turn=2)
    cast(s, "Shock", [bear.id], pid="p2")
    assert s.state.cards[bear.id].damage == 0
    assert s.state.cards[chosen.id].damage == 2
    roundtrip(s)


def prototype_game(cards, *, furnace=False, recipient_name="Black Knight"):
    """An explicit low-level native descriptor prototype, not card grammar admission."""
    from app.game.session import GameSession
    from app.rules import context, effects, replace
    from app.rules.plan import Plan

    s = game(cards)
    first = put(s, "Healer's Hawk", "battlefield", "p2")
    second = put(s, "Grizzly Bears", "battlefield", "p3")
    recipient = put(s, recipient_name, "battlefield")
    if furnace:
        put(s, "Furnace of Rath", "battlefield")
    plan = Plan(s.state.model_copy(deep=True), "p1", cards, None)
    replace.add_record(
        plan,
        event="damage",
        match={"to": {"pids": ["p1"]}},
        op={"do": "redirect", "to": "oid", "oid": plan.oid(recipient.id), "limit": 3, "allocate": True},
        controller="p3",
        source=None,
        source_card=None,
        label="Finite redirection prototype",
    )
    ctx = {
        "controller": "p1",
        "source_card": recipient.id,
        "source_object": plan.oid(recipient.id),
        "stack_id": "",
        "name": "Prototype native damage batch",
        "next": 0,
        "effects": [
            {"do": "damage", "who": "player:p1", "src": "ref:prototype_a", "n": 4, "with_next": True},
            {"do": "damage", "who": "player:p1", "src": "ref:prototype_b", "n": 4},
        ],
    }
    context.bind_objects(plan, ctx, "prototype_a", [first.id])
    context.bind_objects(plan, ctx, "prototype_b", [second.id])
    effects.continue_effects(plan, ctx)
    return GameSession(plan.state, cards=cards), recipient


def number(s, n):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name=str(n))
    settle(s)


def test_native_single_recipient_prototype_allows_one_plus_two_arbitrary_split(cards):
    s, recipient = prototype_game(cards)
    d = s.state.rules.decision
    assert d and d.player == "p1" and d.resume["step"] == "redirect_amount"
    assert s.state.players["p1"].life == 40  # no damage or lifelink committed before allocation
    number(s, 1)
    assert s.state.players["p1"].life == 35
    assert s.state.players["p2"].life == 43  # white source's redirected1 prevented by protection
    assert s.state.cards[recipient.id].zone.endswith(":graveyard")  # green source's redirected2
    roundtrip(s)


def test_native_single_recipient_allocation_reasks_replacement_order_before_commit(cards):
    s, recipient = prototype_game(cards, furnace=True)
    allocations = 0
    for _ in range(16):
        d = s.state.rules.decision
        if d is None:
            break
        assert s.state.players["p1"].life == 40
        if d.resume["step"] == "redirect_amount":
            allocations += 1
            number(s, 1)
        else:
            choose(s, [next(o.id for o in d.options if "Furnace" in o.label)])
    assert allocations >= 1 and s.state.rules.decision is None
    assert s.state.players["p1"].life == 27  # 16 damage, three redirected
    assert s.state.players["p2"].life == 47  # seven actual white-source damage, one prevented
    assert s.state.cards[recipient.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_native_single_recipient_allocation_cold_save_real_choice(cards, tmp_path):
    import subprocess
    import sys

    s, recipient = prototype_game(cards)
    saved = tmp_path / "allocation.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_damage_redirection import number
from tests.test_rules_designations import roundtrip
save,db,recipient=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
assert s.state.rules.decision.player=='p1' and s.state.rules.decision.resume['step']=='redirect_amount'
number(s,1)
assert s.state.players['p1'].life==35 and s.state.players['p2'].life==43
assert s.state.cards[recipient].zone.endswith(':graveyard')
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), recipient.id],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_ascent_actual_all_chapters_return_angel_warrior_with_entry_flying_counter(cards):
    s = game(cards)
    chosen = put(s, "Colossal Dreadmaw", "battlefield")
    returned = put(s, "Runeclaw Bear", "graveyard")
    saga = cast(s, "Ascent of the Worthy")
    choose_source(s, chosen)
    to_phase(s, "main1", turn=4)
    settle(s)
    choose_source(s, chosen)
    to_phase(s, "main1", turn=7)
    settle(s)
    choose_source(s, returned)
    assert s.state.cards[returned.id].zone.endswith(":battlefield")
    assert s.state.cards[returned.id].counters.get("flying") == 1
    assert {"Angel", "Warrior", "Bear"} <= chars(s, returned).subtypes
    assert s.state.cards[saga.id].zone.endswith(":graveyard")
    roundtrip(s)


@pytest.mark.parametrize("life", [9, -3])
def test_incarnation_dies_costs_original_owner_half_life_even_under_opponent_control(cards, life):
    s = game(cards)
    cast(s, "Platinum Angel")
    source = put(s, "Personal Incarnation", "battlefield")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    act(s, "p1", type="set_life", player="p1", value=life)
    cast(s, "Murder", [source.id], pid="p3")
    assert s.state.players["p1"].life == (4 if life == 9 else -3)
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_martyrdom_may_target_same_creature_without_changing_actual_damage(cards):
    s = game(cards)
    source = put(s, "Colossal Dreadmaw", "battlefield")
    cast(s, "Martyrdom", [source.id])
    activate(s, source, "The next 1", [source.id])
    cast(s, "Shock", [source.id], pid="p2")
    assert s.state.cards[source.id].damage == 2
    assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_flaming_gambit_native_flashback_pays_x_and_exiles_after_damage(cards):
    s = game(cards)
    spell = cast(s, "Flaming Gambit", ["p2"], x_value=1)
    assert s.state.players["p2"].life == 39
    mana(s, C=3, R=3)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], x_value=2, sources=[])
    settle(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[spell.id].zone.endswith(":exile")
    roundtrip(s)


def captain_pending(cards):
    s = game(cards)
    hawk = put(s, "Healer's Hawk", "battlefield", "p2")
    baloth = put(s, "Rumbling Baloth", "battlefield", "p2")
    recipient = put(s, "White Knight", "battlefield")
    attack(s, [hawk, baloth], pid="p2", target="p1", turn=2)
    cast(s, "Giant Growth", [hawk.id], pid="p2")
    cast(s, "Touch of Darkness", [hawk.id], pid="p2", target_counts=[1])
    cast(s, "Captain's Maneuver", ["p1", recipient.id], target_counts=[1, 1], x_value=3)
    damage(s)
    return s, hawk, recipient


def test_real_captain_maneuver_combat_allows_one_plus_two_not_source_order(cards):
    s, hawk, recipient = captain_pending(cards)
    d = s.state.rules.decision
    assert d and d.player == "p1" and d.resume["step"] == "redirect_amount"
    frame = d.resume["frame"]
    row = frame["request"]["rows"][frame["i"]]
    number(s, 1 if row["source_card"] == hawk.id else 2)
    assert s.state.players["p1"].life == 35
    assert s.state.players["p2"].life == 43
    assert s.state.cards[recipient.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_real_razia_total_three_survives_its_source_leaving_and_multiple_hits(cards):
    s = game(cards)
    source = put(s, "Razia, Boros Archangel", "battlefield")
    protected = put(s, "Grizzly Bears", "battlefield")
    destination = put(s, "Colossal Dreadmaw", "battlefield")
    activate(s, source, "The next 3", [protected.id, destination.id], target_counts=[1, 1])
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Shock", [protected.id], pid="p2")
    assert s.state.cards[protected.id].damage == 0
    assert s.state.cards[destination.id].damage == 2
    cast(s, "Shock", [protected.id], pid="p2")
    assert s.state.cards[protected.id].damage == 1
    assert s.state.cards[destination.id].damage == 3
    roundtrip(s)


def test_real_hazduhr_actual_x_mana_tap_cost_and_remaining_pool(cards):
    s = game(cards)
    source = put(s, "Hazduhr the Abbot", "battlefield")
    protected = put(s, "Healer's Hawk", "battlefield")
    to_phase(s, "main1", turn=4)
    activate(s, source, "The next X", [protected.id], x_value=3)
    assert s.state.cards[source.id].tapped
    cast(s, "Shock", [protected.id], pid="p2")
    assert s.state.cards[source.id].damage == 2
    cast(s, "Shock", [protected.id], pid="p2")
    assert s.state.cards[source.id].damage == 3
    assert s.state.cards[protected.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_cross_recipient_finite_pool_is_explicitly_outside_native_prototype(cards):
    from app.rules import context, effects, replace
    from app.rules.plan import Plan

    s = game(cards)
    source = put(s, "Colossal Dreadmaw", "battlefield")
    destination = put(s, "Rumbling Baloth", "battlefield")
    plan = Plan(s.state.model_copy(deep=True), "p1", cards, None)
    replace.add_record(
        plan,
        event="damage",
        match={"to": {"pids": ["p1", "p3"]}},
        op={"do": "redirect", "to": "oid", "oid": plan.oid(destination.id), "limit": 3, "allocate": True},
        controller="p1",
        source=None,
        source_card=None,
        label="Unsupported cross-recipient prototype",
    )
    ctx = {
        "controller": "p1",
        "source_card": source.id,
        "source_object": plan.oid(source.id),
        "stack_id": "",
        "name": "Cross-recipient native prototype",
        "next": 0,
        "effects": [
            {"do": "damage", "who": "player:p1", "src": "ref:cross_source", "n": 4, "with_next": True},
            {"do": "damage", "who": "player:p3", "src": "ref:cross_source", "n": 4},
        ],
    }
    context.bind_objects(plan, ctx, "cross_source", [source.id])
    with pytest.raises(ValueError, match="cannot allocate across recipients"):
        effects.continue_effects(plan, ctx)
    assert all(plan.state.players[p].life == 40 for p in ("p1", "p2", "p3"))


@pytest.mark.parametrize(
    "stage", ["kor_source", "martyrdom_actor", "captain_combat", "ascent_control", "razia_remaining"]
)
def test_real_redirection_states_cold_resume_registered_callbacks(cards, tmp_path, stage):
    import json
    import subprocess
    import sys

    s = game(cards)
    ids = {}
    if stage == "kor_source":
        protected = put(s, "Grizzly Bears", "battlefield")
        destination = put(s, "Colossal Dreadmaw", "battlefield", "p2")
        pyro = put(s, "Prodigal Pyromancer", "battlefield", "p2")
        to_phase(s, "main1", turn=2)
        cast(s, "Kor Dirge", [protected.id, destination.id], target_counts=[1, 1])
        assert s.state.rules.decision
        ids = {"protected": protected.id, "destination": destination.id, "pyro": pyro.id}
    elif stage == "martyrdom_actor":
        source = put(s, "Grizzly Bears", "battlefield")
        cast(s, "Martyrdom", [source.id])
        act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
        ids = {"source": source.id}
    elif stage == "captain_combat":
        s, hawk, recipient = captain_pending(cards)
        assert s.state.rules.decision.resume["step"] == "redirect_amount"
        ids = {"hawk": hawk.id, "recipient": recipient.id}
    elif stage == "ascent_control":
        destination = put(s, "Colossal Dreadmaw", "battlefield")
        protected = put(s, "Grizzly Bears", "battlefield")
        saga = cast(s, "Ascent of the Worthy")
        choose_source(s, destination)
        act(s, "p1", type="set_controller", card_ids=[destination.id], player="p2")
        act(s, "p1", type="move", card_ids=[saga.id], to={"player": "p1", "zone": "graveyard"})
        ids = {"protected": protected.id, "destination": destination.id}
    else:
        source = put(s, "Razia, Boros Archangel", "battlefield")
        protected = put(s, "Grizzly Bears", "battlefield")
        destination = put(s, "Colossal Dreadmaw", "battlefield")
        activate(s, source, "The next 3", [protected.id, destination.id], target_counts=[1, 1])
        cast(s, "Shock", [protected.id], pid="p2")
        assert s.state.cards[destination.id].damage == 2
        ids = {"protected": protected.id, "destination": destination.id}
    saved = tmp_path / f"{stage}.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_damage_redirection import cast,activate,choose_source,number
from tests.test_rules_designations import roundtrip
from tests.test_rules_wave30m_durations import to_phase
save,db,stage,raw=sys.argv[1:];ids=json.loads(raw)
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if stage=='kor_source':
 pyro=s.state.cards[ids['pyro']]
 choose_source(s,pyro)
 activate(s,pyro,'deals 1 damage',[ids['protected']],pid='p2')
 assert s.state.cards[ids['protected']].damage==0 and s.state.cards[ids['destination']].damage==1
elif stage=='martyrdom_actor':
 activate(s,s.state.cards[ids['source']],'The next 1',['p3'])
 cast(s,'Shock',['p3'],pid='p3')
 assert s.state.players['p3'].life==39 and s.state.cards[ids['source']].damage==1
elif stage=='captain_combat':
 d=s.state.rules.decision;frame=d.resume['frame'];row=frame['request']['rows'][frame['i']]
 number(s,1 if row['source_card']==ids['hawk'] else 2)
 assert s.state.players['p1'].life==35 and s.state.players['p2'].life==43
 assert s.state.cards[ids['recipient']].zone.endswith(':graveyard')
elif stage=='ascent_control':
 to_phase(s,'main1',turn=2)
 cast(s,'Shock',[ids['protected']],pid='p2')
 assert s.state.cards[ids['protected']].damage==0 and s.state.cards[ids['destination']].damage==2
 to_phase(s,'main1',turn=4)
 cast(s,'Shock',[ids['protected']])
 assert s.state.cards[ids['protected']].zone.endswith(':graveyard')
else:
 cast(s,'Shock',[ids['protected']],pid='p2')
 assert s.state.cards[ids['protected']].damage==1 and s.state.cards[ids['destination']].damage==3
roundtrip(s);repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage, json.dumps(ids)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_exhausted_finite_pool_does_not_reopen_on_later_simultaneous_damage(cards):
    from app.game.session import GameSession
    from app.rules import context, effects
    from app.rules.plan import Plan

    s, recipient = prototype_game(cards, recipient_name="Rumbling Baloth")
    number(s, 1)
    assert s.state.cards[recipient.id].damage == 3 and s.state.players["p1"].life == 35
    first = next(
        c
        for c in s.state.cards.values()
        if c.name == "Healer's Hawk" and c.zone.endswith(":battlefield") and c.controller == "p2"
    )
    second = next(
        c
        for c in s.state.cards.values()
        if c.name == "Grizzly Bears" and c.zone.endswith(":battlefield") and c.controller == "p3"
    )
    plan = Plan(s.state.model_copy(deep=True), "p1", cards, None)
    ctx = {
        "controller": "p1",
        "source_card": recipient.id,
        "source_object": plan.oid(recipient.id),
        "stack_id": "",
        "name": "Second native damage batch",
        "next": 0,
        "effects": [
            {"do": "damage", "who": "player:p1", "src": "ref:again_a", "n": 4, "with_next": True},
            {"do": "damage", "who": "player:p1", "src": "ref:again_b", "n": 4},
        ],
    }
    context.bind_objects(plan, ctx, "again_a", [first.id])
    context.bind_objects(plan, ctx, "again_b", [second.id])
    effects.continue_effects(plan, ctx)
    assert plan.rules.decision is None
    assert plan.state.players["p1"].life == 27
    assert plan.state.cards[recipient.id].damage == 3
    roundtrip(GameSession(plan.state, cards=cards))


def test_captain_x_zero_creates_no_redirect_pool_or_future_choice(cards):
    s = game(cards)
    cast(s, "Captain's Maneuver", ["p1", "p2"], target_counts=[1, 1], x_value=0)
    cast(s, "Lightning Bolt", ["p1"], pid="p2")
    assert s.state.players["p1"].life == 37 and s.state.rules.decision is None
    roundtrip(s)


def test_martyrdom_external_actor_restriction_is_not_borrowed_as_ability_text(cards):
    s = game(cards)
    original = put(s, "Grizzly Bears", "battlefield")
    borrower = put(s, "Experiment Kraj", "battlefield", "p2")
    act(s, "p1", type="set_counter", card_id=original.id, kind="+1/+1", value=1)
    cast(s, "Martyrdom", [original.id])
    # Kraj receives the activated ability text, not the external restriction
    # that Martyrdom's resolution placed on the original granted instance.
    activate(s, borrower, "The next 1", ["p3"], pid="p2")
    cast(s, "Shock", ["p3"], pid="p3")
    assert s.state.players["p3"].life == 39
    assert s.state.cards[borrower.id].damage == 1
    roundtrip(s)
