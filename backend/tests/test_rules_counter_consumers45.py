"""Canonical native counter-payment consumers and saved receipt proofs."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import counter_consumers45 as leaf
from app.rules import graveyard_payments45 as graves
from app.rules import urge_payment45 as urge
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

HYDE = 'Mister Hyde, Monster Within'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_consumers45_cards.json').read_text())):
        base[row['name']] = card(row['name'], set_code='ccf', number=str(i), **{
            ('card_faces' if k == 'faces' else k): v for k, v in row.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [HYDE, 'Grizzly Bears', 'Jace Beleren', 'Fear of Sleep Paralysis', 'Abundance', 'Doubling Season', 'Vorinclex, Monstrous Raider']
    s = table(cards, names, names, names)
    return s, put(s, HYDE, 'battlefield'), put(s, 'Grizzly Bears', 'battlefield')


def upkeep(s, mode):
    to_phase(s, 'upkeep', turn=4)
    d = s.state.rules.decision
    if d is None:
        settle(s)
        d = s.state.rules.decision
    assert d is not None
    option = next(o for o in d.options if ('Remove' if mode else 'Put') in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)


@pytest.mark.parametrize('kind', ['+1/+1', 'charge', 'stun'])
def test_hyde_actual_upkeep_mandatory_any_kind_payment_draws_one(cards, kind):
    s, source, bear = setup(cards)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind=kind, value=2)
    upkeep(s, 1)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == leaf.STEP
    assert d.min_choices == d.max_choices == 1
    assert all(o.id != 'decline' for o in d.options)
    before = len(s.state.zones['p1:hand'])
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert s.state.cards[bear.id].counters.get(kind) == 1
    assert len(s.state.zones['p1:hand']) == before + 1
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_hyde_no_counter_does_not_draw_or_offer_decline(cards):
    s, _, _ = setup(cards)
    upkeep(s, 1)
    assert s.state.rules.decision is None


@pytest.mark.parametrize('modifier,expected', [(None, 1), ('Doubling Season', 2), ('Vorinclex, Monstrous Raider', 0)])
def test_hyde_actual_upkeep_first_mode_native_put_replacements(cards, modifier, expected):
    s, source, _ = setup(cards)
    if modifier:
        put(s, modifier, 'battlefield', pid='p2' if modifier.startswith('Vorinclex') else 'p1')
    upkeep(s, 0)
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == expected


def test_hyde_counter_selection_excludes_foreign_and_planeswalker_only(cards):
    s, _, _ = setup(cards)
    foreign = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    walker = put(s, 'Jace Beleren', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=foreign.id, kind='charge', value=2)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    upkeep(s, 1)
    assert s.state.rules.decision is None
    assert s.state.cards[foreign.id].counters['charge'] == 2
    assert s.state.cards[walker.id].counters['loyalty'] == 3


def test_hyde_actual_cast_printed_cost_and_characteristics(cards):
    from app.rules.plan import Plan
    from tests.test_rules_linked_aggregates import cast

    s, source, _ = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
    cast(s, source)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.pt == (2, 2) and {'Human', 'Villain'} <= set(ch.subtypes)


def test_hyde_prohibited_stun_kind_excluded_but_other_kind_still_pays(cards):
    s, _, bear = setup(cards)
    fear = put(s, 'Fear of Sleep Paralysis', 'battlefield', pid='p2')
    assert fear is not None
    for kind in ['stun', 'charge']:
        act(s, 'p1', type='set_counter', card_id=bear.id, kind=kind, value=2)
    upkeep(s, 1)
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 1 and 'charge' in d.options[0].label
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.cards[bear.id].counters == {'stun': 2, 'charge': 1}


def test_hyde_can_pay_from_own_source(cards):
    s, source, _ = setup(cards)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='charge', value=1)
    upkeep(s, 1)
    d = s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options} == {source.id}
    before = len(s.state.zones['p1:hand'])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    assert not s.state.cards[source.id].counters
    assert len(s.state.zones['p1:hand']) == before + 1


@pytest.mark.parametrize('stage', ['mode', 'counter', 'draw'])
def test_hyde_actual_true_cold_continuation(cards, tmp_path, stage):
    import subprocess
    import sys

    s, source, bear = setup(cards)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=2)
    if stage == 'draw':
        put(s, 'Abundance', 'battlefield')
    if stage == 'mode':
        to_phase(s, 'upkeep', turn=4)
        if s.state.rules.decision is None:
            settle(s)
    else:
        upkeep(s, 1)
        if stage == 'draw':
            d = s.state.rules.decision
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.rules.decision is not None
    before = len(s.state.zones['p1:hand'])
    saved = tmp_path / 'hyde45.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state, db, bear, before = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state).read_text()), cards=repo)
for _ in range(50):
 d = s.state.rules.decision
 if d:
  if d.resume.get('step') == 'mandatory_counter_consumer45': pick=d.options[0].id
  elif any('Remove' in o.label for o in d.options): pick=next(o.id for o in d.options if 'Remove' in o.label)
  else: pick=next((o.id for o in d.options if o.id in ('no','decline')),d.options[0].id)
  s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[pick]})
 elif s.state.rules.stack: s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else: break
assert s.state.rules.decision is None
assert s.state.cards[bear].counters['charge']==1
assert len(s.state.zones['p1:hand'])==int(before)+1
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), bear.id, str(before)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('change', ['sourcegone', 'sourcecontrol', 'sourceblink'])
def test_hyde_old_trigger_can_pay_other_creature_after_source_changes(cards, change):
    s, source, bear = setup(cards)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=1)
    to_phase(s, 'upkeep', turn=4)
    assert s.state.rules.decision is not None
    if change == 'sourcecontrol':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
        if change == 'sourceblink':
            act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    d = s.state.rules.decision
    option = next(o for o in d.options if 'Remove' in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    before = len(s.state.zones['p1:hand'])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    assert not s.state.cards[bear.id].counters
    assert len(s.state.zones['p1:hand']) == before + 1


@pytest.mark.parametrize('change', ['depart', 'blink', 'control'])
def test_hyde_revalidates_selected_exact_counter_object(cards, change):
    s, _, bear = setup(cards)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=1)
    upkeep(s, 1)
    d = s.state.rules.decision
    old = s.state.rules.object_id(bear.id)
    if change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p2')
    else:
        act(s, 'p1', type='move', card_ids=[bear.id], to={'zone': 'hand'})
        if change == 'blink':
            act(s, 'p1', type='move', card_ids=[bear.id], to={'zone': 'battlefield'})
            act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=4)
            assert s.state.rules.object_id(bear.id) != old
    before = len(s.state.zones['p1:hand'])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    assert len(s.state.zones['p1:hand']) == before
    if change == 'blink':
        assert s.state.cards[bear.id].counters['charge'] == 4


@pytest.mark.parametrize('control_changed', [False, True])
def test_hyde_first_mode_affects_original_source_even_with_changed_control(cards, control_changed):
    s, source, _ = setup(cards)
    to_phase(s, 'upkeep', turn=4)
    d = s.state.rules.decision
    assert d is not None
    if control_changed:
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    act(s, d.player, type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if 'Put' in o.label)])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == int(control_changed)


@pytest.mark.parametrize('name', ['Charnel Troll', 'Entrails Feaster'])
@pytest.mark.parametrize('owner', ['p1', 'p2'])
def test_staged_graveyard_upkeep_payment_uses_printed_zone_scope(cards, name, owner):
    names = [name, 'Grizzly Bears', 'Llanowar Elves']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'graveyard', pid=owner)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    if name == 'Charnel Troll' and owner == 'p2':
        assert d is None and s.state.cards[source.id].zone == 'p1:graveyard'
        assert s.state.cards[corpse.id].zone == 'p2:graveyard'
        return
    assert d is not None and d.resume['step'] == graves.STEP
    assert d.min_choices == int(name == 'Charnel Troll')
    assert {o.card_id for o in d.options} == {corpse.id}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert s.state.cards[corpse.id].zone == f'{owner}:exile'
    assert s.state.cards[source.id].counters.get('+1/+1') == 1
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('has_card', [False, True])
def test_feaster_declined_or_unpayable_taps_original(cards, has_card):
    names = ['Entrails Feaster', 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, 'Entrails Feaster', 'battlefield')
    if has_card:
        put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    if has_card:
        d = s.state.rules.decision
        assert d is not None
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[source.id].tapped
    assert not s.state.cards[source.id].counters


@pytest.mark.parametrize('pay', [False, True])
def test_urge_native_self_target_zero_toughness_vampire_survives_only_accepted_tap(cards, pay):
    from tests.test_rules_linked_aggregates import cast

    names = ['Urge to Feed', 'Vampire Nighthawk', 'Grizzly Bears']
    s = table(cards, names, names, names)
    spell = put(s, 'Urge to Feed', 'hand')
    vampire = put(s, 'Vampire Nighthawk', 'battlefield')
    cast(s, spell, targets=[vampire.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == urge.STEP
    assert s.state.cards[vampire.id].zone == 'p1:battlefield'
    assert d.min_choices == 0 and d.max_choices == 1
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[vampire.id] if pay else [])
    settle(s)
    assert s.state.cards[vampire.id].zone == ('p1:battlefield' if pay else 'p1:graveyard')
    if pay:
        from app.rules.plan import Plan
        assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[vampire.id]).pt == (0, 1)
        assert s.state.cards[vampire.id].tapped and s.state.cards[vampire.id].counters == {'+1/+1': 1}


def test_urge_actual_any_number_excludes_tapped_foreign_nonvampire_but_not_sickness(cards):
    from tests.test_rules_linked_aggregates import cast

    names = ['Urge to Feed', 'Vampire Nighthawk', 'Vampire Hexmage', 'Grizzly Bears', 'Vampire Nighthawk']
    s = table(cards, names, names, names)
    spell = put(s, 'Urge to Feed', 'hand')
    vampire = put(s, 'Vampire Nighthawk', 'battlefield')
    sick = put(s, 'Vampire Hexmage', 'battlefield')
    tapped = next(c for c in s.state.cards.values() if c.name == 'Vampire Nighthawk' and c.owner == 'p1' and c.id != vampire.id)
    act(s, 'p1', type='move', card_ids=[tapped.id], to={'zone': 'battlefield'})
    act(s, 'p1', type='tap', card_ids=[tapped.id], tapped=True)
    foreign = put(s, 'Vampire Nighthawk', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p3')
    cast(s, spell, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options} == {vampire.id, sick.id}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[vampire.id, sick.id])
    settle(s)
    for obj in [vampire, sick]:
        assert s.state.cards[obj.id].tapped and s.state.cards[obj.id].counters == {'+1/+1': 1}
    assert s.state.cards[tapped.id].tapped and not s.state.cards[tapped.id].counters
    assert not s.state.cards[bear.id].tapped and not s.state.cards[foreign.id].tapped
    assert s.state.cards[target.id].zone == 'p3:graveyard'


def test_magistrate_actual_cast_enters_five_and_death_payment_returns_exact_card(cards):
    from tests.test_rules_linked_aggregates import cast

    names = ['Magnanimous Magistrate', 'Grizzly Bears', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, 'Magnanimous Magistrate', 'hand')
    cast(s, source)
    settle(s)
    assert s.state.cards[source.id].counters == {'reprieve': 5}
    bear = put(s, 'Grizzly Bears', 'battlefield')
    old = s.state.rules.object_id(bear.id)
    bolt = put(s, 'Lightning Bolt', 'hand')
    cast(s, bolt, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume.get('opt', {}).get('cost') == 'Remove 2 reprieve counters from ~'
    new = s.state.rules.object_id(bear.id)
    assert new != old and s.state.cards[bear.id].zone == 'p1:graveyard'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.cards[source.id].counters == {'reprieve': 3}
    assert s.state.cards[bear.id].zone == 'p1:battlefield' and s.state.rules.object_id(bear.id) != new
    roundtrip(s)


@pytest.mark.parametrize('modifier,expected', [('Solemnity', 0), ('Doubling Season', 2), ('Vorinclex, Monstrous Raider', 0)])
@pytest.mark.parametrize('name', ['Charnel Troll', 'Entrails Feaster'])
def test_exile_payment_remains_accepted_with_modified_counter_put(cards, modifier, expected, name):
    names = [name, 'Grizzly Bears', modifier]
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'graveyard')
    put(s, modifier, 'battlefield', pid='p2' if modifier.startswith('Vorinclex') else 'p1')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert s.state.cards[corpse.id].zone == 'p1:exile'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.cards[source.id].tapped
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == expected


def test_charnel_printed_activation_discards_creature_and_feeds_upkeep(cards):
    from tests.test_rules_linked_aggregates import activate

    names = ['Charnel Troll', 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, 'Charnel Troll', 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'hand')
    to_phase(s, 'upkeep', turn=4)
    assert s.state.rules.stack and s.state.rules.decision is None
    from app.rules.plan import Plan

    ability = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).abilities if a.kind == 'activated')
    activate(s, source, ability=ability, cost_choices=[{'component': 1, 'cards': [corpse.id]}])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == graves.STEP
    assert s.state.cards[source.id].counters.get('+1/+1') == 1
    assert s.state.cards[corpse.id].zone == 'p1:graveyard'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert s.state.cards[source.id].counters == {'+1/+1': 2}
    assert s.state.cards[corpse.id].zone == 'p1:exile'


def cold_finish(s, tmp_path, target, source, expected_counter, expected_zone, choose_card=None, first='Vorinclex'):
    import subprocess
    import sys

    saved = tmp_path / 'consumer45.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state,db,target,source,amount,zone,pick,first=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(state).read_text()),cards=repo)
for _ in range(60):
 d=s.state.rules.decision
 if d:
  if d.resume.get('step') in ('graveyard_payment45','urge_payment45'): ids=[pick]
  elif any(o.id=='pay' for o in d.options): ids=['pay']
  else: ids=[next((o.id for name in first.split('|') for o in d.options if name in o.label),d.options[0].id)]
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
 elif s.state.rules.stack: s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else: break
assert s.state.rules.decision is None
assert s.state.cards[target].zone==zone
assert s.state.cards[source].counters.get('+1/+1',0)==int(amount)
assert not s.state.cards[source].tapped or source==target
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(s.cards.db_path), target.id, source.id,
                             str(expected_counter), expected_zone, choose_card or '', first],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name', ['Charnel Troll', 'Entrails Feaster'])
@pytest.mark.parametrize('stage', ['choice', 'put'])
def test_upkeep_exile_payment_actual_true_cold_choice_and_put_completion(cards, tmp_path, name, stage):
    names = [name, 'Grizzly Bears', 'Doubling Season', 'Vorinclex, Monstrous Raider']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'graveyard', pid='p2' if name == 'Entrails Feaster' else 'p1')
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == graves.STEP
    if stage == 'put':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
        d = s.state.rules.decision
        assert d is not None
        assert s.state.cards[corpse.id].zone.endswith(':exile')

        def find_receipt(raw):
            if isinstance(raw, dict):
                value = raw.get(graves.BIND)
                if isinstance(value, dict) and 'accepted' in value:
                    return graves.ExilePayment.model_validate(value)
                for child in raw.values():
                    found = find_receipt(child)
                    if found is not None:
                        return found
            elif isinstance(raw, list):
                for child in raw:
                    found = find_receipt(child)
                    if found is not None:
                        return found
            return None

        receipt = find_receipt(d.resume)
        assert receipt is not None and receipt.accepted and receipt.completed
        assert receipt.original.zone.endswith(':graveyard')
        assert len(receipt.result) == 1 and receipt.result[0].zone.endswith(':exile')
        assert receipt.result[0].object_id == s.state.rules.object_id(corpse.id)
        assert receipt.result[0].object_id != receipt.original.object_id
    cold_finish(s, tmp_path, corpse, source, 0, f'{corpse.owner}:exile', corpse.id)


@pytest.mark.parametrize('stage', ['choice', 'put'])
def test_urge_actual_zero_toughness_self_save_cold_at_choice_and_native_put(cards, tmp_path, stage):
    from tests.test_rules_linked_aggregates import cast

    names = ['Urge to Feed', 'Vampire Nighthawk', 'Doubling Season', 'Vorinclex, Monstrous Raider']
    s = table(cards, names, names, names)
    source = put(s, 'Vampire Nighthawk', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    spell = put(s, 'Urge to Feed', 'hand')
    cast(s, spell, targets=[source.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == urge.STEP
    if stage == 'put':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[source.id])
        d = s.state.rules.decision
        assert d is not None and s.state.cards[source.id].tapped
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    cold_finish(s, tmp_path, source, source, 1, 'p1:battlefield', source.id, 'Doubling Season')


@pytest.mark.parametrize('scenario', ['decline', 'insufficient', 'gravegone', 'graveblink', 'sourcegone', 'sourcecontrol', 'stolenowner'])
def test_magistrate_actual_payment_negatives_and_owner_return(cards, scenario):
    from tests.test_rules_linked_aggregates import cast

    names = ['Magnanimous Magistrate', 'Grizzly Bears', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, 'Magnanimous Magistrate', 'hand')
    cast(s, source)
    settle(s)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2' if scenario == 'stolenowner' else 'p1')
    if scenario == 'stolenowner':
        act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p1')
    if scenario == 'insufficient':
        act(s, 'p1', type='set_counter', card_id=source.id, kind='reprieve', value=1)
    bolt = put(s, 'Lightning Bolt', 'hand')
    cast(s, bolt, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    if scenario == 'insufficient':
        assert d is None and s.state.cards[source.id].counters == {'reprieve': 1}
        assert s.state.cards[bear.id].zone == 'p1:graveyard'
        return
    assert d is not None and d.resume['opt']['cost'] == 'Remove 2 reprieve counters from ~'
    if scenario in ('gravegone', 'graveblink'):
        old = s.state.rules.object_id(bear.id)
        act(s, 'p1', type='move', card_ids=[bear.id], to={'zone': 'exile'})
        if scenario == 'graveblink':
            act(s, 'p1', type='move', card_ids=[bear.id], to={'zone': 'graveyard'})
            assert s.state.rules.object_id(bear.id) != old
    if scenario == 'sourcegone':
        act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
    if scenario == 'sourcecontrol':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline' if scenario == 'decline' else 'pay'])
    settle(s)
    if scenario == 'sourcegone':
        assert s.state.cards[bear.id].zone == 'p1:graveyard'
    elif scenario == 'decline':
        assert s.state.cards[source.id].counters == {'reprieve': 5}
        assert s.state.cards[bear.id].zone == 'p1:graveyard'
    else:
        assert s.state.cards[source.id].counters == {'reprieve': 3}
        assert s.state.cards[bear.id].zone == ('p1:exile' if scenario == 'gravegone' else 'p1:graveyard' if scenario == 'graveblink'
                                             else 'p2:battlefield' if scenario == 'stolenowner' else 'p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('stage', ['payment', 'entry'])
def test_magistrate_true_cold_original_cost_and_native_entry_counter_receipts(cards, tmp_path, stage):
    from tests.test_rules_linked_aggregates import cast

    names = ['Magnanimous Magistrate', 'Fertilid', 'Lightning Bolt', 'Doubling Season', 'Vorinclex, Monstrous Raider', 'Hardened Scales']
    s = table(cards, names, names, names)
    source = put(s, 'Magnanimous Magistrate', 'hand')
    cast(s, source)
    settle(s)
    corpse = put(s, 'Fertilid', 'hand')
    cast(s, corpse)
    settle(s)
    assert s.state.cards[corpse.id].counters == {'+1/+1': 2}
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    put(s, 'Hardened Scales', 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand')
    cast(s, bolt, targets=[corpse.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['opt']['cost'] == 'Remove 3 reprieve counters from ~'
    if stage == 'entry':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
        assert s.state.rules.decision is not None and s.state.cards[source.id].counters == {'reprieve': 2}
    cold_finish(s, tmp_path, corpse, corpse, 4, 'p1:battlefield', first='Vorinclex|Hardened Scales|Doubling Season')


def test_urge_illegal_sole_target_suppresses_the_entire_payment(cards):
    from tests.test_rules_linked_aggregates import cast

    names = ['Urge to Feed', 'Vampire Nighthawk', 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, 'Urge to Feed', 'hand')
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    vampire = put(s, 'Vampire Nighthawk', 'battlefield')
    cast(s, source, targets=[target.id])
    act(s, 'p1', type='move', card_ids=[target.id], to={'zone': 'hand'})
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[vampire.id].tapped and not s.state.cards[vampire.id].counters
    assert s.state.cards[source.id].zone == 'p1:graveyard'


@pytest.mark.parametrize('name', ['Charnel Troll', 'Entrails Feaster'])
@pytest.mark.parametrize('change', ['sourcegone', 'sourceblink', 'sourcecontrol', 'corpseblink'])
def test_upkeep_exile_payment_preserves_original_source_and_corpse_refs(cards, name, change):
    names = [name, 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'graveyard')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    if change == 'sourcecontrol':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    elif change.startswith('source'):
        act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
        if change == 'sourceblink':
            act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    else:
        act(s, 'p1', type='move', card_ids=[corpse.id], to={'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[corpse.id], to={'zone': 'graveyard'})
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    if change == 'corpseblink':
        assert s.state.cards[corpse.id].zone == 'p1:graveyard'
        assert s.state.cards[source.id].zone == ('p1:graveyard' if name == 'Charnel Troll' else 'p1:battlefield')
        if name == 'Entrails Feaster':
            assert s.state.cards[source.id].tapped
    else:
        assert s.state.cards[corpse.id].zone == 'p1:exile'
        assert s.state.cards[source.id].counters.get('+1/+1', 0) == int(change == 'sourcecontrol')
        assert not s.state.cards[source.id].tapped


def test_feaster_graveyard_shroud_does_not_block_nontarget_payment(cards):
    names = ['Entrails Feaster', 'Grizzly Bears', 'Ground Seal']
    s = table(cards, names, names, names)
    source = put(s, 'Entrails Feaster', 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    put(s, 'Ground Seal', 'battlefield', pid='p2')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options} == {corpse.id}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert s.state.cards[corpse.id].zone == 'p2:exile'
    assert s.state.cards[source.id].counters == {'+1/+1': 1}


@pytest.mark.parametrize('name', ['Charnel Troll', 'Entrails Feaster'])
def test_graveyard_payment_noncreature_cards_are_not_resources(cards, name):
    names = [name, 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    other = put(s, 'Lightning Bolt', 'graveyard')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[other.id].zone == 'p1:graveyard'
    if name == 'Charnel Troll':
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    else:
        assert s.state.cards[source.id].tapped


def test_feaster_commander_payment_finishes_counter_before_903_9a_choice(cards):
    from tests.test_rules_linked_aggregates import cast

    names = ['Entrails Feaster', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, 'Entrails Feaster', 'battlefield')
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand')
    cast(s, bolt, targets=[commander.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert s.state.cards[commander.id].zone == 'p1:graveyard'
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == graves.STEP
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[commander.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and s.state.cards[commander.id].zone == 'p1:exile'
    assert s.state.cards[source.id].counters == {'+1/+1': 1}
    assert not s.state.cards[source.id].tapped
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    assert s.state.cards[commander.id].zone == 'p1:command'
    assert s.state.cards[source.id].counters == {'+1/+1': 1}


def test_magistrate_actual_simultaneous_deaths_cannot_overpay_frozen_costs(cards):
    from tests.test_rules_linked_aggregates import cast

    names = ['Magnanimous Magistrate', 'Grizzly Bears', 'Llanowar Elves', 'Pyroclasm']
    s = table(cards, names, names, names)
    source = put(s, 'Magnanimous Magistrate', 'hand')
    cast(s, source)
    settle(s)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='reprieve', value=2)
    spell = put(s, 'Pyroclasm', 'hand')
    cast(s, spell)
    spent = 0
    for _ in range(15):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        if 'opt' in d.resume:
            cost = d.resume['opt']['cost']
            assert cost in ['Remove 1 reprieve counters from ~', 'Remove 2 reprieve counters from ~']
            amount = int(cost.split()[1])
            assert spent + amount <= 2
            spent += amount
            ids = ['pay']
        else:
            ids = [o.id for o in d.options]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    assert s.state.rules.decision is None
    assert spent in (1, 2)
    assert s.state.cards[source.id].counters.get('reprieve', 0) == 2 - spent
    assert sum(s.state.cards[o.id].zone == 'p1:battlefield' for o in [bear, elf]) == 1
    roundtrip(s)


def test_magistrate_animated_vehicle_death_uses_creature_lki_but_returns_artifact(cards):
    from app.rules.plan import Plan
    from tests.test_rules_linked_aggregates import activate, cast

    names = ['Magnanimous Magistrate', "Smuggler's Copter", 'Grizzly Bears', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, 'Magnanimous Magistrate', 'hand')
    cast(s, source)
    settle(s)
    vehicle = put(s, "Smuggler's Copter", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    ability = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[vehicle.id]).abilities if a.text.startswith('Crew'))
    activate(s, vehicle, ability=ability)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[vehicle.id]).is_creature
    bolt = put(s, 'Lightning Bolt', 'hand')
    cast(s, bolt, targets=[vehicle.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['opt']['cost'] == 'Remove 2 reprieve counters from ~'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.cards[vehicle.id].zone == 'p1:battlefield'
    assert not Plan(s.state, 'p1', cards, None).ch(s.state.cards[vehicle.id]).is_creature
    assert s.state.cards[source.id].counters == {'reprieve': 3}


@pytest.mark.parametrize('victim', ['foreign', 'zero', 'self'])
def test_magistrate_printed_death_trigger_exclusions(cards, victim):
    from tests.test_rules_linked_aggregates import cast

    names = ['Magnanimous Magistrate', 'Grizzly Bears', 'Memnite', 'Lightning Bolt', 'Murder']
    s = table(cards, names, names, names)
    source = put(s, 'Magnanimous Magistrate', 'hand')
    cast(s, source)
    settle(s)
    target = source if victim == 'self' else put(s, 'Grizzly Bears' if victim == 'foreign' else 'Memnite',
                                                'battlefield', pid='p2' if victim == 'foreign' else 'p1')
    spell = put(s, 'Murder' if victim == 'self' else 'Lightning Bolt', 'hand')
    cast(s, spell, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone.endswith(':graveyard')
    assert s.state.rules.decision is None
    if victim != 'self':
        assert s.state.cards[source.id].counters == {'reprieve': 5}


def test_magistrate_nontoken_filter_excludes_native_copy_with_positive_mana_value(cards):
    from app.rules.plan import Plan
    from tests.test_rules_linked_aggregates import cast

    names = ['Magnanimous Magistrate', 'Grizzly Bears', 'Rite of Replication', 'Pyroclasm']
    s = table(cards, names, names, names)
    source = put(s, 'Magnanimous Magistrate', 'hand')
    cast(s, source)
    settle(s)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    copy = put(s, 'Rite of Replication', 'hand')
    cast(s, copy, targets=[bear.id])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.controller == 'p1' and c.zone.endswith(':battlefield')]
    assert len(tokens) == 1 and Plan(s.state, 'p1', cards, None).ch(tokens[0]).mana_value == 2
    spell = put(s, 'Pyroclasm', 'hand')
    cast(s, spell)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['opt']['cost'] == 'Remove 2 reprieve counters from ~'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters == {'reprieve': 3}
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert not any(c.is_token and c.zone.endswith(':battlefield') for c in s.state.cards.values())


@pytest.mark.parametrize('name', ['Charnel Troll', 'Entrails Feaster'])
def test_upkeep_consumers_actual_printed_cast_and_characteristics(cards, name):
    from app.rules.plan import Plan
    from tests.test_rules_linked_aggregates import cast

    s = table(cards, [name], [name], [name])
    source = put(s, name, 'hand')
    cast(s, source)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.pt == ((4, 4) if name == 'Charnel Troll' else (1, 1))
    if name == 'Charnel Troll':
        assert 'trample' in {k.lower() for k in ch.keywords}


@pytest.mark.parametrize('modifier,expected', [('Solemnity', 0), ('Doubling Season', 2), ('Vorinclex, Monstrous Raider', 0)])
def test_urge_native_tap_acceptance_is_independent_of_counter_put_result(cards, modifier, expected):
    from tests.test_rules_linked_aggregates import cast

    names = ['Urge to Feed', 'Vampire Nighthawk', 'Grizzly Bears', modifier]
    s = table(cards, names, names, names)
    source = put(s, 'Urge to Feed', 'hand')
    vampire = put(s, 'Vampire Nighthawk', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    put(s, modifier, 'battlefield', pid='p2' if modifier.startswith('Vorinclex') else 'p1')
    cast(s, source, targets=[victim.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[vampire.id])
    settle(s)
    assert s.state.cards[vampire.id].tapped
    assert s.state.cards[vampire.id].counters.get('+1/+1', 0) == expected
    assert s.state.cards[victim.id].zone == 'p2:graveyard'


def test_feaster_already_tapped_original_source_can_still_pay_exile(cards):
    names = ['Entrails Feaster', 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, 'Entrails Feaster', 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'graveyard')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert s.state.cards[source.id].counters == {'+1/+1': 1}
    assert s.state.cards[source.id].tapped
    assert s.state.cards[corpse.id].zone == 'p1:exile'


def test_troll_failed_exact_exile_cost_cannot_sacrifice_now_foreign_source(cards):
    names = ['Charnel Troll', 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, 'Charnel Troll', 'battlefield')
    corpse = put(s, 'Grizzly Bears', 'graveyard')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, 'p1', type='move', card_ids=[corpse.id], to={'zone': 'hand'})
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p2:battlefield' and not s.state.cards[source.id].counters


@pytest.mark.parametrize('problem', ['missing_green', 'noncreature'])
def test_charnel_native_activation_requires_full_mana_and_creature_discard_atomically(cards, problem):
    from app.game.errors import ActionError
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import mana, wait_priority

    names = ['Charnel Troll', 'Grizzly Bears', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, 'Charnel Troll', 'battlefield')
    payment = put(s, 'Grizzly Bears' if problem == 'missing_green' else 'Lightning Bolt', 'hand')
    mana(s, B=1, G=0 if problem == 'missing_green' else 1)
    wait_priority(s, 'p1')
    ability = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).abilities if a.kind == 'activated')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability,
            cost_choices=[{'component': 1, 'cards': [payment.id]}])
    assert s.state.model_dump(mode='json') == before
