"""Canonical nonmana fees are chosen, locked, and paid as native cost events."""

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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAMES = [
    "Leviathan",
    "Exalted Dragon",
    "Floodtide Serpent",
    "Flooded Woodlands",
    "Reclamation",
    "Hollow Warrior",
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/nonmana_declaration_costs_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="ndc", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/nonmana_declaration_costs_cards.json").read_text()
        )
    ]
    return table(cards, names, names, ["Grizzly Bears", "Memnite"])


def lands(s, n, pid="p2"):
    ids = [
        c.id
        for c in s.state.cards.values()
        if c.name == "Island" and c.owner == pid and c.zone == f"{pid}:library"
    ][:n]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "battlefield"})
    return ids


def declare(s, host, chosen, target="p1", **extra):
    act(
        s,
        "p2",
        type="declare_attackers",
        attackers=[{"card_id": host.id, "target": target}],
        cost_choices=[{"component": 0, "cards": chosen}],
        **extra,
    )


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(("name", "count"), [("Leviathan", 2), ("Exalted Dragon", 1)])
def test_actual_sacrifice_attack_cost(cards, name, count):
    s = setup(cards)
    host = put(s, name, "battlefield", pid="p2")
    initial = lands(s, count + 2 if name == "Leviathan" else count)
    to_phase(s, "declare_attackers", turn=2)
    ids = [cid for cid in initial if s.state.cards[cid].zone == "p2:battlefield"][:count]
    assert len(ids) == count
    declare(s, host, ids)
    assert all(s.state.cards[cid].zone == "p2:graveyard" for cid in ids)
    assert s.state.cards[host.id].attacking is not None
    assert s.state.rules.declaration_cost_reserved is None
    roundtrip(s)


def test_return_enchantment_attack_cost(cards):
    s = setup(cards)
    host = put(s, "Floodtide Serpent", "battlefield", pid="p2")
    enchant = put(s, "Propaganda", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    declare(s, host, [enchant.id])
    assert s.state.cards[enchant.id].zone == "p2:hand"
    assert s.state.cards[host.id].attacking is not None
    roundtrip(s)


@pytest.mark.parametrize("mode", ["attack", "block"])
def test_hollow_taps_a_creature_outside_declaration(cards, mode):
    s = setup(cards)
    host = put(s, "Hollow Warrior", "battlefield", pid="p2")
    helper = put(s, "Grizzly Bears", "battlefield", pid="p2")
    attacker = put(s, "Memnite", "battlefield")
    if mode == "attack":
        to_phase(s, "declare_attackers", turn=2)
        declare(s, host, [helper.id])
        assert s.state.cards[host.id].attacking is not None
    else:
        to_phase(s, "declare_attackers", turn=4)
        attack(s, (attacker, "p2"))
        to_phase(s, "declare_blockers", turn=4)
        act(
            s,
            "p2",
            type="declare_blockers",
            blocks=[{"blocker_id": host.id, "attacker_id": attacker.id}],
            cost_choices=[{"component": 0, "cards": [helper.id]}],
        )
        assert s.state.cards[host.id].blocking
    assert s.state.cards[helper.id].tapped
    roundtrip(s)


@pytest.mark.parametrize(
    ("name", "creature"),
    [("Flooded Woodlands", "Grizzly Bears"), ("Reclamation", "Kalitas, Traitor of Ghet")],
)
def test_global_color_fee_charges_only_declared_color(cards, name, creature):
    s = setup(cards)
    put(s, name, "battlefield")
    host = put(s, creature, "battlefield", pid="p2")
    free = put(s, "Memnite", "battlefield", pid="p2")
    island = lands(s, 1)[0]
    to_phase(s, "declare_attackers", turn=2)
    act(
        s,
        "p2",
        type="declare_attackers",
        attackers=[{"card_id": host.id, "target": "p3"}, {"card_id": free.id, "target": "p1"}],
        cost_choices=[{"component": 0, "cards": [island]}],
    )
    assert s.state.cards[island].zone == "p2:graveyard"
    assert s.state.cards[host.id].attacking and s.state.cards[free.id].attacking
    roundtrip(s)


def test_same_dryad_can_be_tapped_then_sacrificed_for_distinct_costs(cards):
    s = setup(cards)
    dragon = put(s, "Exalted Dragon", "battlefield", pid="p2")
    warrior = put(s, "Hollow Warrior", "battlefield", pid="p2")
    dryad = put(s, "Dryad Arbor", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    payload = {
        "type": "declare_attackers",
        "attackers": [{"card_id": dragon.id, "target": "p1"}, {"card_id": warrior.id, "target": "p3"}],
        "cost_choices": [{"component": 0, "cards": [dryad.id]}, {"component": 1, "cards": [dryad.id]}],
    }
    with pytest.raises(ActionError):
        act(s, "p2", **payload, cost_order=[0, 1])
    assert s.state.cards[dryad.id].zone == "p2:battlefield" and not s.state.cards[dryad.id].tapped
    act(s, "p2", **payload, cost_order=[1, 0])
    assert s.state.cards[dryad.id].zone == "p2:graveyard"
    assert s.state.cards[dragon.id].attacking and s.state.cards[warrior.id].attacking
    roundtrip(s)


def test_hollow_cannot_tap_another_declared_attacker(cards):
    s = setup(cards)
    host = put(s, "Hollow Warrior", "battlefield", pid="p2")
    helper = put(s, "Grizzly Bears", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        act(
            s,
            "p2",
            type="declare_attackers",
            attackers=[{"card_id": host.id, "target": "p1"}, {"card_id": helper.id, "target": "p3"}],
            cost_choices=[{"component": 0, "cards": [helper.id]}],
        )
    assert not s.state.cards[helper.id].tapped
    roundtrip(s)


def test_commander_return_choice_precedes_cost_move_and_attack(cards):
    s = setup(cards)
    host = put(s, "Floodtide Serpent", "battlefield", pid="p2")
    commander = put(s, "Karametra, God of Harvests", "battlefield", pid="p2")
    act(s, "p2", type="set_commander", card_id=commander.id)
    to_phase(s, "declare_attackers", turn=2)
    declare(s, host, [commander.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "cost_moves"
    assert s.state.cards[commander.id].zone == "p2:battlefield" and s.state.cards[host.id].attacking is None
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.cards[commander.id].zone == "p2:command"
    assert s.state.cards[host.id].attacking
    roundtrip(s)


def test_chosen_order_preserves_required_island_type(cards):
    s = setup(cards)
    serpent = put(s, "Floodtide Serpent", "battlefield", pid="p2")
    leviathan = put(s, "Leviathan", "battlefield", pid="p2")
    # Let native Leviathan upkeep happen before setting up the two Island resources.
    to_phase(s, "main1", turn=2)
    island = lands(s, 1)[0]
    plains = put(s, "Plains", "battlefield", pid="p2")
    seas = put(s, "Spreading Seas", "hand", pid="p2")
    mana(s, pid="p2", U=1, C=1)
    act(s, "p2", type="cast_spell", card_id=seas.id, targets=[plains.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    # Source insertion order is Leviathan before Serpent in the canonical deck.
    payload = {
        "type": "declare_attackers",
        "attackers": [{"card_id": leviathan.id, "target": "p1"}, {"card_id": serpent.id, "target": "p3"}],
        "cost_choices": [
            {"component": 0, "cards": [island, plains.id]},
            {"component": 1, "cards": [seas.id]},
        ],
    }
    with pytest.raises(ActionError):
        act(s, "p2", **payload, cost_order=[1, 0])
    assert (
        s.state.cards[seas.id].zone == "p2:battlefield" and s.state.cards[plains.id].zone == "p2:battlefield"
    )
    act(s, "p2", **payload, cost_order=[0, 1])
    assert s.state.cards[island].zone == "p2:graveyard" and s.state.cards[plains.id].zone == "p2:graveyard"
    assert s.state.cards[seas.id].zone == "p2:hand"
    roundtrip(s)


@pytest.mark.parametrize("outcome", ["exile", "library:shuffle"])
def test_native_graveyard_replacement_choices_precede_cost_commit(cards, outcome):
    s = setup(cards)
    host = put(s, "Exalted Dragon", "battlefield", pid="p2")
    put(s, "Ashaya, Soul of the Wild", "battlefield", pid="p2")
    island = put(s, "Progenitus", "battlefield", pid="p2").id
    put(s, "Rest in Peace", "battlefield")
    to_phase(s, "declare_attackers", turn=2)
    declare(s, host, [island])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "cost_moves"
    assert s.state.cards[island].zone == "p2:battlefield" and s.state.cards[host.id].attacking is None
    selected = next(o.id for o in d.options if o.id == outcome)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[selected])
    if outcome == "exile":
        assert s.state.cards[island].zone == "p2:exile"
    else:
        assert any(c.name == "Progenitus" and c.zone == "p2:library" for c in s.state.cards.values())
    assert s.state.cards[host.id].attacking
    roundtrip(s)


def test_replacement_token_rider_finishes_before_attack_commit(cards):
    s = setup(cards)
    host = put(s, "Exalted Dragon", "battlefield", pid="p2")
    dryad = put(s, "Dryad Arbor", "battlefield", pid="p2")
    for name in ["Kalitas, Traitor of Ghet", "Divine Visitation", "Chatterfang, Squirrel General"]:
        put(s, name, "battlefield")
    to_phase(s, "declare_attackers", turn=2)
    declare(s, host, [dryad.id])
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] != "declare_blockers"
    assert s.state.cards[dryad.id].zone == "p2:exile" and s.state.cards[host.id].attacking is None
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.cards[host.id].attacking
    assert len([c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]) == 2
    roundtrip(s)


def reserved_payment_setup(cards):
    s = setup(cards)
    host = put(s, "Exalted Dragon", "battlefield", pid="p2")
    land = put(s, "Dwarven Ruins", "battlefield", pid="p2")
    aura = put(s, "Brainwash", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[host.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    return s, host, land


def test_auto_mana_keeps_sacrifice_resource_but_can_tap_it_first(cards):
    from tests.game_helpers import mana_pool

    s, host, land = reserved_payment_setup(cards)
    mana(s, pid="p2", C=1)
    with pytest.raises(ActionError):
        declare(s, host, [land.id])
    assert s.state.cards[land.id].zone == "p2:battlefield" and not s.state.cards[land.id].tapped
    assert s.state.rules.declaration_cost_reserved is None
    mana(s, pid="p2", C=1)
    declare(s, host, [land.id])
    assert s.state.cards[land.id].zone == "p2:graveyard" and s.state.cards[host.id].attacking
    assert mana_pool(s, "p2") == {} and s.state.rules.declaration_cost_reserved is None
    roundtrip(s)


@pytest.mark.parametrize("cancel", [False, True])
def test_manual_payment_reservations_clear_on_pay_or_cancel(cards, cancel):
    from app.rules import casting
    from tests.game_helpers import mana_pool

    s, host, land = reserved_payment_setup(cards)
    act(s, "p2", type="set_prefs", payment="self")
    mana(s, pid="p2", C=2)
    declare(s, host, [land.id])
    assert s.state.rules.declaration_cost_reserved.objects[land.id] == s.state.rules.object_id(land.id)
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=land.id, ability=2)
    if cancel:
        d = s.state.rules.decision
        act(s, "p2", type="choose", decision_id=d.id, option_ids=["cancel"])
        assert s.state.cards[land.id].zone == "p2:battlefield" and not s.state.cards[land.id].tapped
        assert s.state.cards[host.id].attacking is None and mana_pool(s, "p2") == {"C": 2}
        assert 2 in [i for i, _ in casting.mana_abilities(s.state, s.state.cards[land.id], s.cards)]
    else:
        act(s, "p2", type="activate_ability", card_id=land.id, ability=1)
        assert s.state.cards[land.id].zone == "p2:graveyard" and s.state.cards[host.id].attacking
        assert mana_pool(s, "p2") == {}
    assert s.state.rules.declaration_cost_reserved is None
    roundtrip(s)


@pytest.mark.parametrize("stage", ["objects", "commander", "replacement", "rider", "mana"])
def test_cost_payment_resumes_in_fresh_process(cards, tmp_path, stage):
    import subprocess
    import sys

    if stage == "mana":
        s, host, resource = reserved_payment_setup(cards)
        act(s, "p2", type="set_prefs", payment="self")
        mana(s, pid="p2", C=2)
        declare(s, host, [resource.id])
    else:
        s = setup(cards)
        host = put(
            s, "Floodtide Serpent" if stage == "commander" else "Exalted Dragon", "battlefield", pid="p2"
        )
        if stage == "commander":
            resource = put(s, "Karametra, God of Harvests", "battlefield", pid="p2")
            act(s, "p2", type="set_commander", card_id=resource.id)
        elif stage == "rider":
            resource = put(s, "Dryad Arbor", "battlefield", pid="p2")
            for name in ["Kalitas, Traitor of Ghet", "Divine Visitation", "Chatterfang, Squirrel General"]:
                put(s, name, "battlefield")
        else:
            selected = lands(s, 2 if stage == "objects" else 1)[0]
            resource = s.state.cards[selected]
            if stage == "replacement":
                put(s, "Rest in Peace", "battlefield")
                put(s, "Ashaya, Soul of the Wild", "battlefield", pid="p2")
                resource = put(s, "Progenitus", "battlefield", pid="p2")
        to_phase(s, "declare_attackers", turn=2)
        if stage == "objects":
            attack(s, (host, "p1"), pid="p2")
        else:
            declare(s, host, [resource.id])
    assert s.state.rules.decision and s.state.cards[host.id].attacking is None
    roundtrip(s)
    saved = tmp_path / "nonmana-cost.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import mana_pool
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage,host,resource=sys.argv[3:]
if stage=='mana':
    assert s.state.rules.declaration_cost_reserved.objects[resource]==s.state.rules.object_id(resource)
    try:s.perform('p2',{'type':'activate_ability','card_id':resource,'ability':2})
    except ActionError:pass
    else:raise AssertionError('reserved permanent sacrificed for mana')
    s.perform('p2',{'type':'activate_ability','card_id':resource,'ability':1})
else:
    for _ in range(20):
        if s.state.cards[host].attacking is not None:break
        d=s.state.rules.decision
        assert d is not None
        if stage=='objects' and d.resume['step']=='ability_cost':choice=[resource]
        elif stage=='commander':choice=['yes']
        elif stage=='replacement':choice=['exile']
        elif d.kind=='order':choice=[o.id for o in d.options]
        else:choice=[d.options[0].id]
        s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':choice})
assert s.state.cards[host].attacking is not None
assert s.state.cards[resource].zone==('p2:command' if stage=='commander' else 'p2:exile' if stage in ('rider','replacement') else 'p2:graveyard')
assert s.state.rules.declaration_cost_reserved is None
if stage=='mana':assert mana_pool(s,'p2')=={}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage, host.id, resource.id],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_global_fee_counts_every_colored_attacker_before_committing(cards):
    s = setup(cards)
    put(s, "Flooded Woodlands", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    dryad = put(s, "Dryad Arbor", "battlefield", pid="p2")
    ids = lands(s, 2)
    to_phase(s, "declare_attackers", turn=2)
    payload = dict(type="declare_attackers", attackers=[
        {"card_id": bears.id, "target": "p1"}, {"card_id": dryad.id, "target": "p3"}])
    with pytest.raises(ActionError):
        act(s, "p2", **payload, cost_choices=[{"component": 0, "cards": ids[:1]}])
    assert all(s.state.cards[cid].zone == "p2:battlefield" for cid in ids)
    act(s, "p2", **payload, cost_choices=[{"component": 0, "cards": ids}])
    assert all(s.state.cards[cid].zone == "p2:graveyard" for cid in ids)
    assert s.state.cards[bears.id].attacking and s.state.cards[dryad.id].attacking
    roundtrip(s)


def test_distinct_global_sources_require_distinct_sacrifices(cards):
    s = setup(cards)
    put(s, "Flooded Woodlands", "battlefield")
    put(s, "Flooded Woodlands", "battlefield", pid="p2")
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    ids = lands(s, 2)
    to_phase(s, "declare_attackers", turn=2)
    payload = dict(type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}], cost_order=[0, 1])
    with pytest.raises(ActionError):
        act(s, "p2", **payload, cost_choices=[{"component": 0, "cards": ids[:1]}, {"component": 1, "cards": ids[:1]}])
    assert all(s.state.cards[cid].zone == "p2:battlefield" for cid in ids)
    act(s, "p2", **payload, cost_choices=[{"component": i, "cards": [cid]} for i, cid in enumerate(ids)])
    assert all(s.state.cards[cid].zone == "p2:graveyard" for cid in ids)
    assert s.state.cards[bears.id].attacking
    roundtrip(s)


def test_native_order_question_preserves_selected_shared_resource(cards):
    s = setup(cards)
    dragon = put(s, "Exalted Dragon", "battlefield", pid="p2")
    warrior = put(s, "Hollow Warrior", "battlefield", pid="p2")
    dryad = put(s, "Dryad Arbor", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[
        {"card_id": dragon.id, "target": "p1"}, {"card_id": warrior.id, "target": "p3"}],
        cost_choices=[{"component": 0, "cards": [dryad.id]}, {"component": 1, "cards": [dryad.id]}])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "declaration_cost_order"
    assert s.state.cards[dryad.id].zone == "p2:battlefield" and not s.state.cards[dryad.id].tapped
    roundtrip(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["1", "0"])
    assert s.state.cards[dryad.id].zone == "p2:graveyard"
    assert s.state.cards[dragon.id].attacking and s.state.cards[warrior.id].attacking
    roundtrip(s)


def test_cost_object_selection_can_cancel_without_paying(cards):
    s = setup(cards)
    host = put(s, "Exalted Dragon", "battlefield", pid="p2")
    ids = lands(s, 2)
    to_phase(s, "declare_attackers", turn=2)
    previous = s.state.rules.decision
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": host.id, "target": "p1"}])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "ability_cost"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[])
    assert s.state.rules.decision == previous
    assert s.state.cards[host.id].attacking is None
    assert all(s.state.cards[cid].zone == "p2:battlefield" and not s.state.cards[cid].tapped for cid in ids)
    assert s.state.rules.declaration_cost_reserved is None
    roundtrip(s)


def test_angel_spell_ability_sacrifice_ban_does_not_ban_declaration_cost(cards):
    s = setup(cards)
    host = put(s, "Exalted Dragon", "battlefield", pid="p2")
    dryad = put(s, "Dryad Arbor", "battlefield", pid="p2")
    put(s, "Angel of Jubilation", "battlefield")
    to_phase(s, "declare_attackers", turn=2)
    declare(s, host, [dryad.id])
    assert s.state.cards[dryad.id].zone == "p2:graveyard"
    assert s.state.cards[host.id].attacking
    roundtrip(s)
