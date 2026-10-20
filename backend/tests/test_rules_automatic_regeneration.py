"""CR 614.8/616.1: automatic regeneration replaces the current destruction."""
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
from tests.test_rules_designations import build, put, roundtrip, settle

DATA = Path(__file__).parent / 'fixtures/automatic_regeneration_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='arg', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Mossbridge Troll', 'Knight of the Holy Nimbus', 'Clergy of the Holy Nimbus']


def setup(cards, name='Mossbridge Troll', extra=()):
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, [name, 'Murder', 'Day of Judgment', 'Wrath of God', 'Lightning Bolt', 'Dismember', 'Regenerate',
                      'Hyena Umbra', 'Snake Umbra', 'Withstand Death', 'Planar Cleansing', *extra])
    hold(s)
    source = put(s, name, 'battlefield')
    return s, source


def cast(s, name, target=None):
    spell = put(s, name, 'hand')
    mana = {'Murder': {'B': 2, 'C': 1}, 'Day of Judgment': {'W': 2, 'C': 2}, 'Wrath of God': {'W': 2, 'C': 2},
            'Lightning Bolt': {'R': 1}, 'Dismember': {'B': 2, 'C': 1}, 'Regenerate': {'G': 1, 'C': 1},
            'Withstand Death': {'G': 1}, 'Hyena Umbra': {'W': 1}, 'Snake Umbra': {'G': 1, 'C': 2},
            'Planar Cleansing': {'W': 3, 'C': 3}}[name]
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id] if target is not None else [], **({'life_symbols': []} if name == 'Dismember' else {}))
    settle(s)
    return spell


def choose(s, key):
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'regeneration_replacement'
    index = next(str(i) for i, c in enumerate(s.state.rules.destruction_replacements['candidates'][d.resume['card']]) if c['key'] == key)
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[index])
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_real_cards_are_fully_supported(cards, name):
    c = coverage.of_card_data(cards.resolve(name))
    assert c.level == 'FULL', c.manual_parts


@pytest.mark.parametrize('name', NAMES)
def test_automatic_regeneration_replaces_repeated_effect_destruction_without_a_saved_shield(cards, name):
    s, source = setup(cards, name)
    for _ in range(2):
        cast(s, 'Murder', source)
        assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].tapped
        assert not s.state.rules.regen_shields and s.state.rules.destruction_replacements is None
        roundtrip(s)


@pytest.mark.parametrize('name', ['Knight of the Holy Nimbus', 'Clergy of the Holy Nimbus'])
def test_lethal_damage_regenerates_immediately_and_clears_damage_and_combat(cards, name):
    s, source = setup(cards, name)
    act(s, 'p1', type='attack', card_ids=[source.id], target={'kind': 'player', 'id': 'p2'})
    cast(s, 'Lightning Bolt', source)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].tapped
    assert s.state.cards[source.id].damage == 0 and s.state.cards[source.id].attacking is None
    assert not s.state.rules.regen_shields
    roundtrip(s)


def test_cannot_regenerate_destruction_and_zero_toughness_do_not_apply_automatic_replacement(cards):
    for spell in ['Wrath of God', 'Dismember']:
        s, source = setup(cards)
        cast(s, spell, None if spell == 'Wrath of God' else source)
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        assert s.state.rules.destruction_replacements is None
        roundtrip(s)


def test_indestructible_has_no_destruction_event_and_does_not_regenerate(cards):
    s, source = setup(cards)
    cast(s, 'Withstand Death', source)
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and not s.state.cards[source.id].tapped
    assert s.state.rules.destruction_replacements is None
    roundtrip(s)


def test_automatic_regeneration_and_finite_shield_order_is_chosen_again_for_each_event(cards):
    s, source = setup(cards)
    cast(s, 'Regenerate', source)
    oid = s.state.rules.object_id(source.id)
    cast(s, 'Murder', source)
    choose(s, 'automatic')
    assert s.state.rules.regen_shields[oid] == 1
    cast(s, 'Murder', source)
    choose(s, 'shield')
    assert oid not in s.state.rules.regen_shields
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.destruction_replacements is None
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['automatic', 'counter'])
def test_shield_counter_can_be_preserved_or_used_instead_of_regeneration(cards, replacement):
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='shield', delta=1)
    cast(s, 'Murder', source)
    choose(s, replacement)
    assert s.state.cards[source.id].counters.get('shield', 0) == (1 if replacement == 'automatic' else 0)
    assert s.state.cards[source.id].tapped == (replacement == 'automatic')
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['automatic', 'aura'])
def test_umbra_armor_and_automatic_regeneration_are_affected_controllers_choice(cards, replacement):
    s, source = setup(cards)
    aura = cast(s, 'Hyena Umbra', source)
    cast(s, 'Murder', source)
    choose(s, 'automatic' if replacement == 'automatic' else 'aura:' + s.state.rules.object_id(aura.id))
    assert s.state.cards[aura.id].zone == ('p1:battlefield' if replacement == 'automatic' else 'p1:graveyard')
    assert s.state.cards[source.id].tapped == (replacement == 'automatic')
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['automatic', 'aura'])
def test_lethal_sba_replacement_choice_preserves_the_other_protection(cards, replacement):
    s, source = setup(cards, 'Clergy of the Holy Nimbus')
    aura = cast(s, 'Hyena Umbra', source)
    cast(s, 'Lightning Bolt', source)
    choose(s, 'automatic' if replacement == 'automatic' else 'aura:' + s.state.rules.object_id(aura.id))
    assert s.state.cards[source.id].damage == 0
    assert s.state.cards[source.id].tapped == (replacement == 'automatic')
    assert s.state.cards[aura.id].zone == ('p1:battlefield' if replacement == 'automatic' else 'p1:graveyard')


@pytest.mark.parametrize('replacement', ['automatic', 'aura'])
def test_simultaneous_destruction_snapshots_armor_before_its_own_destruction(cards, replacement):
    s, source = setup(cards, extra=['Grizzly Bears', 'Hill Giant'])
    bears = put(s, 'Grizzly Bears', 'battlefield')
    giant = put(s, 'Hill Giant', 'battlefield')
    aura = cast(s, 'Hyena Umbra', source)
    cast(s, 'Planar Cleansing')
    choose(s, 'automatic' if replacement == 'automatic' else 'aura:' + s.state.rules.object_id(aura.id))
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].tapped == (replacement == 'automatic')
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in [bears, giant, aura])
    assert s.state.rules.destruction_replacements is None
    roundtrip(s)


def test_cannot_regenerate_still_allows_umbra_armor(cards):
    s, source = setup(cards)
    aura = cast(s, 'Hyena Umbra', source)
    cast(s, 'Wrath of God')
    assert s.state.cards[source.id].zone == 'p1:battlefield' and not s.state.cards[source.id].tapped
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('spell,name', [('Murder', 'Mossbridge Troll'), ('Lightning Bolt', 'Clergy of the Holy Nimbus')])
def test_destruction_replacement_resumes_in_a_fresh_process(cards, tmp_path, spell, name):
    import subprocess
    import sys

    s, source = setup(cards, name)
    aura = cast(s, 'Hyena Umbra', source)
    cast(s, spell, source)
    assert s.state.rules.decision.resume['step'] == 'regeneration_replacement'
    roundtrip(s)
    saved = tmp_path / 'regeneration.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, source, aura = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
assert d.resume['step'] == 'regeneration_replacement'
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['0']})
assert s.state.cards[source].zone == 'p1:battlefield'
assert s.state.cards[source].tapped and s.state.cards[source].damage == 0
assert s.state.cards[aura].zone == 'p1:battlefield'
assert s.state.rules.destruction_replacements is None
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, aura.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_simultaneous_sba_choices_follow_active_player_order_instead_of_card_order(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, first = setup(cards, 'Clergy of the Holy Nimbus', extra=['Knight of the Holy Nimbus'])
    second = put(s, 'Knight of the Holy Nimbus', 'battlefield')
    for source, name in [(first, 'Hyena Umbra'), (second, 'Snake Umbra')]:
        aura = put(s, name, 'battlefield')
        act(s, 'p1', type='attach', card_ids=[aura.id], to=source.id)
    act(s, 'p1', type='set_controller', card_ids=[second.id], player='p2')
    to_phase(s, 'main1', turn=2)
    for source in [first, second]:
        act(s, 'p1', type='set_damage', card_ids=[source.id], value=5)
    act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.decision.player == 'p2'
    choose(s, 'automatic')
    assert s.state.rules.decision.player == 'p1'
    choose(s, 'automatic')
    assert all(s.state.cards[c.id].zone.endswith(':battlefield') and s.state.cards[c.id].damage == 0 for c in [first, second])
    roundtrip(s)


@pytest.mark.parametrize('name', ['Knight of the Holy Nimbus', 'Clergy of the Holy Nimbus'])
def test_opponents_real_activation_disables_automatic_regeneration_for_the_turn(cards, name):
    s, source = setup(cards, name)
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2})
    act(s, 'p1', type='pass_priority')
    from app.rules.plan import Plan

    index = next(a.index for a in Plan(s.state, 'p1', s.cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    assert s.state.rules.object_id(source.id) in s.state.rules.no_regen
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.rules.destruction_replacements is None
    roundtrip(s)
