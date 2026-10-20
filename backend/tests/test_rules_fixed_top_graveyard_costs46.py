"""Native exact fixed-top graveyard costs, ordering and payment continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_damage_redirection import cast
from tests.test_rules_designations import put, settle
from tests.test_rules_ordered_zone_costs46 import DATA
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave40c_graveyard_order import run


@pytest.fixture()
def cards(settings):
    extra = json.loads((Path(__file__).parent / 'fixtures/automatic_regeneration_cards.json').read_text())
    petal = next(r for r in json.loads((Path(__file__).parent / 'fixtures/activated_copy_family_cards.json').read_text()) if r['name'] == 'Lotus Petal')
    sphere = next(r for r in json.loads((Path(__file__).parent / 'fixtures/prevention_outcomes_cards.json').read_text()) if r['name'] == 'Chromatic Sphere')
    imp = next(r for r in json.loads((Path(__file__).parent / 'fixtures/name_search_family_cards.json').read_text()) if r['name'] == 'Stinkweed Imp')
    plains = next(r for r in json.loads((Path(__file__).parent / 'fixtures/attached_kindred_look_cards.json').read_text()) if r['name'] == 'Plains')
    coating = next(r for r in json.loads((Path(__file__).parent / 'fixtures/goblin_welder_cards.json').read_text()) if r['name'] == 'Liquimetal Coating')
    rows = [*DATA, petal, sphere, imp, plains, coating, *(r for r in extra if r['name'] in ('Wrath of God', 'Planar Cleansing'))]
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(rows):
        base[row['name']] = card(row['name'], set_code='g46', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('reader', ['Alms', "Nature's Kiss"])
@pytest.mark.parametrize('spell', ['Wrath of God', 'Planar Cleansing'])
def test_actual_destroy_batch_then_later_aura_and_resolving_spell_arrivals(cards, reader, spell):
    names = [reader, spell, 'Grizzly Bears', 'Black Knight']
    s = table(cards, names, names, names)
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Black Knight', 'battlefield')
    source = cast(s, reader, [first.id]) if reader == "Nature's Kiss" else put(s, reader, 'battlefield')
    wipe = cast(s, spell, resolve=False)
    d = run(s)
    assert d is not None and d.kind == 'order' and d.player == 'p1'
    expected = {first.id, second.id}
    if spell == 'Planar Cleansing':
        expected.add(source.id)
    assert {o.id for o in d.options} == expected
    # Destruction occurs during resolution. The spell enters afterward, above that batch.
    if reader == "Nature's Kiss" and spell == 'Wrath of God':
        # Its host died in resolution; the unattached Aura follows in a later SBA batch.
        assert s.state.zones['p1:graveyard'][-2:] == [wipe.id, source.id]
    else:
        assert s.state.zones['p1:graveyard'][-1] == wipe.id
    ordered = [first.id, *sorted(expected - {first.id})]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=ordered)
    settle(s)
    pile = s.state.zones['p1:graveyard']
    assert [c for c in pile if c in expected] == list(reversed(ordered))
    if reader == "Nature's Kiss" and spell == 'Wrath of God':
        assert pile[-1] == source.id
    else:
        assert pile[-1] == wipe.id


@pytest.mark.parametrize('name', ['Alms', "Nature's Kiss"])
def test_production_fixed_top_cost_exiles_exact_latest_card_with_native_payment_facts(cards, name):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    names = [name, 'Grizzly Bears', 'Forest', 'Island']
    s = table(cards, names, names, names)
    target = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, name, [target.id]) if name == "Nature's Kiss" else put(s, name, 'battlefield')
    earlier = put(s, 'Forest', 'graveyard')
    latest = put(s, 'Island', 'graveyard')
    old_oid = s.state.rules.object_id(latest.id)
    mana(s, C=1)
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index,
        targets=[target.id] if name == 'Alms' else [], sources=[])
    assert s.state.cards[latest.id].zone == 'p1:exile'
    assert s.state.cards[earlier.id].zone == 'p1:graveyard'
    entry = next(reversed(s.state.rules.stack))
    receipt = s.state.rules.payments[s.state.rules.object_id(entry)]
    assert receipt.exiled == [latest.id] and receipt.exiled_was == [old_oid]
    settle(s)
    if name == "Nature's Kiss":
        from tests.test_rules_wave6c_tokens_pumps import pt
        assert pt(s, target) == (3, 3)
    else:
        assert s.state.rules.prevention.get(s.state.rules.object_id(target.id)) == 1


@pytest.mark.parametrize('initial_card', [False, True])
def test_production_fixed_top_binds_after_actual_mana_source_sacrifice(cards, initial_card):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    names = ['Alms', 'Grizzly Bears', 'Forest', 'Lotus Petal']
    s = table(cards, names, names, names)
    source = put(s, 'Alms', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    petal = put(s, 'Lotus Petal', 'battlefield')
    earlier = put(s, 'Forest', 'graveyard') if initial_card else None
    assert not any(s.state.players['p1'].mana.values())
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index,
        targets=[target.id], sources=[petal.id])
    assert s.state.cards[petal.id].zone == 'p1:exile'
    if earlier is not None:
        assert s.state.zones['p1:graveyard'] == [earlier.id]
    else:
        assert s.state.zones.get('p1:graveyard', []) == []
    entry = next(reversed(s.state.rules.stack))
    receipt = s.state.rules.payments[s.state.rules.object_id(entry)]
    assert receipt.exiled == [petal.id] and sum(receipt.mana_spent.values()) == 1
    settle(s)
    assert s.state.rules.prevention.get(s.state.rules.object_id(target.id)) == 1


def test_native_chromatic_sphere_instant_only_restriction_rejects_during_fixed_top_payment(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    names = ['Alms', 'Grizzly Bears', 'Forest', 'Chromatic Sphere', 'Stinkweed Imp', 'Suppression Field']
    s = table(cards, names, names, names)
    source = put(s, 'Alms', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Suppression Field', 'battlefield')
    sphere = put(s, 'Chromatic Sphere', 'battlefield')
    put(s, 'Stinkweed Imp', 'graveyard')
    land = put(s, 'Forest', 'battlefield')
    act(s, 'p1', type='set_prefs', payment='self', hold_priority=True)
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match='While paying you can only tap for mana|only.*instant'):
        act(s, 'p1', type='activate_ability', card_id=sphere.id, ability=0, mana_choice='W')
    assert s.state.model_dump_json() == before


def open_empty_top_window(cards, *, with_petal=False):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    names = ['Alms', 'Grizzly Bears', 'Lotus Petal', 'Forest', 'Island']
    s = table(cards, names, names, names)
    if with_petal:
        put(s, 'Lotus Petal', 'battlefield')
    source = put(s, 'Alms', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=1)
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    d = s.state.rules.decision
    assert d is not None and d.resume.get('fixed_top_cost_window46')
    return s, d


@pytest.mark.parametrize('choice', ['pay', 'cancel'])
def test_production_empty_gy_no_route_final_rejection_and_cancel_are_atomic(cards, choice):
    from app.game.errors import ActionError

    s, d = open_empty_top_window(cards)
    assert s.state.zones.get('p1:graveyard', []) == []
    before = s.state.model_dump_json()
    if choice == 'pay':
        with pytest.raises(ActionError, match='no top card'):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
        assert s.state.model_dump_json() == before
        assert s.state.rules.decision.id == d.id
    else:
        pool = dict(s.state.players['p1'].mana)
        zones = {z: list(ids) for z, ids in s.state.zones.items()}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
        assert s.state.rules.decision is None
        assert s.state.players['p1'].mana == pool and s.state.zones == zones
        assert not s.state.rules.stack


def test_production_surplus_mana_preserves_explicit_window_to_make_actual_top(cards):
    s, d = open_empty_top_window(cards, with_petal=True)
    petal = next(c for c in s.state.cards.values() if c.name == 'Lotus Petal' and c.zone == 'p1:battlefield')
    act(s, 'p1', type='activate_ability', card_id=petal.id, ability=0, mana_choice='W')
    d = s.state.rules.decision
    assert d is not None and d.resume.get('fixed_top_cost_window46')
    assert s.state.cards[petal.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].mana['C'] == 1
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.cards[petal.id].zone == 'p1:exile'
    entry = next(reversed(s.state.rules.stack))
    receipt = s.state.rules.payments[s.state.rules.object_id(entry)]
    assert receipt.exiled == [petal.id] and sum(receipt.mana_spent.values()) == 1
    settle(s)


def test_production_fixed_top_original_alms_can_leave_battlefield_and_itself_pay_actual_top_cost(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    names = ['Alms', 'Grizzly Bears', 'Forest', 'Krark-Clan Ironworks', 'Liquimetal Coating']
    s = table(cards, names, names, names)
    source = put(s, 'Alms', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    ironworks = put(s, 'Krark-Clan Ironworks', 'battlefield')
    coating = put(s, 'Liquimetal Coating', 'battlefield')
    put(s, 'Forest', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=coating.id, ability=0, targets=[source.id], sources=[])
    settle(s)
    assert 'Artifact' in chars(s, source).types
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    original = s.state.rules.object_id(source.id)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    assert s.state.rules.decision.resume['fixed_top_cost_window46']
    act(s, 'p1', type='activate_ability', card_id=ironworks.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [source.id]}])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    graveyard_oid = s.state.rules.object_id(source.id)
    assert graveyard_oid != original
    d = s.state.rules.decision
    assert d is not None and d.resume['fixed_top_cost_window46']
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.cards[source.id].zone == 'p1:exile'
    entry = next(reversed(s.state.rules.stack))
    receipt = s.state.rules.payments[s.state.rules.object_id(entry)]
    assert receipt.exiled == [source.id] and receipt.exiled_was == [graveyard_oid]
    assert s.state.rules.stack[entry].source_object == original
    settle(s)
    assert s.state.rules.prevention.get(s.state.rules.object_id(target.id)) == 1


def test_production_low_level_zero_total_mana_cost_keeps_explicit_native_mana_window(cards, monkeypatch):
    """Prerequisite only: inject a locked {0} total; no printed reducer/source admission."""
    from dataclasses import replace

    from app.rules import casting
    native_cost = casting.ability_cost

    def zero(ch, ability, **kwargs):
        cost = native_cost(ch, ability, **kwargs)
        return replace(cost, mana='{0}') if ch.name == 'Alms' else cost

    monkeypatch.setattr(casting, 'ability_cost', zero)
    s, d = open_empty_top_window(cards, with_petal=True)
    assert d.resume['cost'] == '{0}'
    petal = next(c for c in s.state.cards.values() if c.name == 'Lotus Petal' and c.zone == 'p1:battlefield')
    act(s, 'p1', type='activate_ability', card_id=petal.id, ability=0, mana_choice='W')
    d = s.state.rules.decision
    assert d is not None and d.resume['fixed_top_cost_window46']
    before_pool = dict(s.state.players['p1'].mana)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.cards[petal.id].zone == 'p1:exile'
    assert s.state.players['p1'].mana == before_pool
    entry = next(reversed(s.state.rules.stack))
    receipt = s.state.rules.payments[s.state.rules.object_id(entry)]
    assert receipt.exiled == [petal.id] and not receipt.mana_spent


@pytest.mark.parametrize('stage', ['mana', 'graveyard_order'])
def test_native_fresh_process_fixed_top_payment_continuations_without_adapters(cards, tmp_path, stage):
    import subprocess
    import sys

    s, d = open_empty_top_window(cards, with_petal=stage == 'mana')
    wanted = next(c for c in s.state.cards.values() if c.name == ('Lotus Petal' if stage == 'mana' else 'Island') and c.owner == 'p1')
    other = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1')
    if stage == 'graveyard_order':
        # Native Plan batch is a prerequisite input, not a claimed printed mana producer.
        from app.game.session import GameSession
        from app.rules.plan import Plan
        plan = Plan(s.state, 'p1', cards, None)
        plan.do({'type': 'move', 'card_ids': [other.id, wanted.id], 'to': {'player': 'p1', 'zone': 'graveyard'}})
        s = GameSession(plan.state, cards=cards)
        assert s.state.rules.pending_gy_order
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'fixed_top_cost_order46'
        assert not s.state.rules.stack
        assert s.state.cards[wanted.id].zone == 'p1:graveyard'
    save = tmp_path / f'fixed-top-{stage}.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
stage,save,db,wanted,other=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if stage=='mana':
 assert s.state.rules.decision.resume['fixed_top_cost_window46']
 act(s,'p1',type='activate_ability',card_id=wanted,ability=0,mana_choice='W')
 d=s.state.rules.decision
 assert d is not None and d.resume['fixed_top_cost_window46']
 assert s.state.cards[wanted].zone=='p1:graveyard'
 act(s,'p1',type='choose',decision_id=d.id,option_ids=['pay'])
else:
 d=s.state.rules.decision
 assert d.resume['step']=='fixed_top_cost_order46'
 assert d.resume['fixed_top_then']['stage']=='activation_announced'
 act(s,'p1',type='choose',decision_id=d.id,option_ids=[wanted,other])
 assert s.state.cards[other].zone=='p1:graveyard'
assert s.state.cards[wanted].zone=='p1:exile'
entry=next(reversed(s.state.rules.stack))
receipt=s.state.rules.payments[s.state.rules.object_id(entry)]
assert receipt.exiled==[wanted] and sum(receipt.mana_spent.values())==1
assert not s.state.rules.pending_gy_order
settle(s)
old=s.state.rules.object_id(wanted)
roundtrip(s)
settle(s)
assert s.state.rules.object_id(wanted)==old
assert s.state.cards[wanted].zone=='p1:exile'
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, stage, str(save), str(cards.db_path), wanted.id, other.id],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def announce_with_fixed_top(s, source, targets=(), pid='p1'):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    wait_priority(s, pid)
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, pid, type='activate_ability', card_id=source.id, ability=index, targets=list(targets), sources=[])


def test_alms_actual_one_damage_budget_then_native_spell_damage_exhausts_it(cards):
    from tests.test_rules_bandmate_references import mana

    names = ['Alms', 'Leashling', 'Forest', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, 'Alms', 'battlefield')
    target = put(s, 'Leashling', 'battlefield')
    cost = put(s, 'Forest', 'graveyard')
    mana(s, C=1)
    announce_with_fixed_top(s, source, [target.id])
    settle(s)
    cast(s, 'Lightning Bolt', [target.id], pid='p2')
    assert s.state.cards[target.id].zone == 'p1:battlefield' and s.state.cards[target.id].damage == 2
    assert s.state.cards[cost.id].zone == 'p1:exile'
    cast(s, 'Lightning Bolt', [target.id])
    assert s.state.cards[target.id].zone == 'p1:graveyard'


@pytest.mark.parametrize('change', ['gone', 'reattached'])
def test_natures_kiss_native_ability_uses_source_lki_or_current_attachment(cards, change):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave6c_tokens_pumps import pt

    names = ["Nature's Kiss", 'Grizzly Bears', 'Black Knight', 'Forest']
    s = table(cards, names, names, names)
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Black Knight', 'battlefield')
    source = cast(s, "Nature's Kiss", [first.id])
    cost = put(s, 'Forest', 'graveyard')
    mana(s, C=1)
    announce_with_fixed_top(s, source)
    if change == 'gone':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    else:
        act(s, 'p1', type='attach', card_ids=[source.id], to=second.id)
    settle(s)
    assert s.state.cards[cost.id].zone == 'p1:exile'
    assert pt(s, first) == ((3, 3) if change == 'gone' else (2, 2))
    assert pt(s, second) == ((3, 3) if change == 'reattached' else (2, 2))


@pytest.mark.parametrize('name', ['Alms', "Nature's Kiss"])
def test_fixed_top_source_control_uses_activators_own_graveyard(cards, name):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave6c_tokens_pumps import pt

    names = [name, 'Grizzly Bears', 'Forest', 'Island']
    s = table(cards, names, names, names)
    target = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, name, [target.id]) if name == "Nature's Kiss" else put(s, name, 'battlefield')
    own = put(s, 'Forest', 'graveyard')
    payer = put(s, 'Island', 'graveyard', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    mana(s, pid='p2', C=1)
    announce_with_fixed_top(s, source, [target.id] if name == 'Alms' else [], pid='p2')
    settle(s)
    assert s.state.cards[payer.id].zone == 'p2:exile' and s.state.cards[own.id].zone == 'p1:graveyard'
    if name == "Nature's Kiss":
        assert pt(s, target) == (3, 3)
    else:
        assert s.state.rules.prevention.get(s.state.rules.object_id(target.id)) == 1


@pytest.mark.parametrize('name', ['Alms', "Nature's Kiss"])
def test_native_countered_fixed_top_ability_keeps_actual_exile_cost_paid(cards, name):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave6c_tokens_pumps import pt

    names = [name, 'Grizzly Bears', 'Forest', 'Stifle']
    s = table(cards, names, names, names)
    target = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, name, [target.id]) if name == "Nature's Kiss" else put(s, name, 'battlefield')
    paid = put(s, 'Forest', 'graveyard')
    mana(s, C=1)
    announce_with_fixed_top(s, source, [target.id] if name == 'Alms' else [])
    entry = next(reversed(s.state.rules.stack))
    cast(s, 'Stifle', [entry], pid='p2')
    assert s.state.cards[paid.id].zone == 'p1:exile'
    assert pt(s, target) == (2, 2)
    assert not s.state.rules.prevention.get(s.state.rules.object_id(target.id))


def test_alms_noncreature_target_is_rejected_before_cost_or_mana_window(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    names = ['Alms', 'Forest']
    s = table(cards, names, names, names)
    source = put(s, 'Alms', 'battlefield')
    paid = put(s, 'Forest', 'graveyard')
    mana(s, C=1)
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=['p2'])
    assert s.state.model_dump_json() == before and s.state.cards[paid.id].zone == 'p1:graveyard'


def test_natures_kiss_pump_ends_at_cleanup_and_enchanted_creature_ability_loss_does_not_remove_aura_ability(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave6c_tokens_pumps import pt
    from tests.test_rules_wave30m_durations import to_phase

    names = ["Nature's Kiss", 'Grizzly Bears', 'Forest', 'Island', 'Turn to Frog']
    s = table(cards, names, names, names)
    target = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, "Nature's Kiss", [target.id])
    cast(s, 'Turn to Frog', [target.id])
    paid = put(s, 'Forest', 'graveyard')
    mana(s, C=1)
    announce_with_fixed_top(s, source)
    settle(s)
    assert pt(s, target) == (2, 2) and s.state.cards[paid.id].zone == 'p1:exile'
    second_cost = put(s, 'Island', 'graveyard')
    announce_with_fixed_top(s, source)
    settle(s)
    assert pt(s, target) == (3, 3) and s.state.cards[second_cost.id].zone == 'p1:exile'
    to_phase(s, 'main1', turn=2)
    assert pt(s, target) == (2, 2)


@pytest.mark.parametrize('name', ['Alms', "Nature's Kiss"])
def test_whole_original_card_definition_coverage_for_fixed_top_collateral(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
