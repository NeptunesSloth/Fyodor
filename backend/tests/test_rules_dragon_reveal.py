"""Optional reveal costs and immutable Dragon presence while casting."""
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

NAMES = ["Silumgar's Scorn", 'Orator of Ojutai', 'Draconic Roar', "Dragonlord's Prerogative", 'Foul-Tongue Invocation', 'Scaleguard Sentinels']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/dragon_reveal_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name, *, dragon_name='Shivan Dragon'):
    s = table(cards, [name, dragon_name, 'Grizzly Bears', 'Unsummon', 'Dress Down'], ['Grizzly Bears', 'Lightning Bolt', 'Counterspell'])
    spell = put(s, name, 'hand')
    dragon = put(s, dragon_name, 'hand')
    return s, spell, dragon


def cast(s, spell, *, reveal=False, targets=()):
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=list(targets), optional_costs=[f'{spell.id}:reveal'] if reveal else [])
    d = s.state.rules.decision
    if d and d.resume.get('step') == 'ability_cost':
        assert all(o.label == 'Shivan Dragon' for o in d.options)
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[d.options[0].id])


@pytest.mark.parametrize('mode', ['none', 'reveal', 'control'])
def test_orator_draw_uses_original_cast_snapshot_and_keeps_revealed_card(cards, mode):
    s, spell, dragon = setup(cards, 'Orator of Ojutai')
    if mode == 'control':
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, W=2)
    before = len(s.state.zones['p1:hand'])
    cast(s, spell, reveal=mode == 'reveal')
    if mode == 'control':
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert len(s.state.zones['p1:hand']) == before - 1 + int(mode != 'none')
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    if mode == 'reveal':
        assert s.state.cards[dragon.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['none', 'reveal', 'control'])
def test_roar_damage_and_target_controller_link(cards, mode):
    s, spell, dragon = setup(cards, 'Draconic Roar')
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    if mode == 'control':
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'battlefield'})
    mana(s, R=1, C=1)
    cast(s, spell, reveal=mode == 'reveal', targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 40 - (3 if mode != 'none' else 0)
    roundtrip(s)


@pytest.mark.parametrize('reveal', [False, True])
def test_scaleguard_entry_counters(cards, reveal):
    s, spell, _ = setup(cards, 'Scaleguard Sentinels')
    mana(s, G=2)
    cast(s, spell, reveal=reveal)
    settle(s)
    assert s.state.cards[spell.id].counters.get('+1/+1', 0) == int(reveal)
    roundtrip(s)


@pytest.mark.parametrize('reveal', [False, True])
def test_invocation_life_rider_after_opponent_sacrifice(cards, reveal):
    s, spell, _ = setup(cards, 'Foul-Tongue Invocation')
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    mana(s, B=1, C=2)
    cast(s, spell, reveal=reveal, targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    if d:
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[victim.id])
        settle(s)
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 40 + 4 * int(reveal)
    roundtrip(s)


@pytest.mark.parametrize('mode', ['none', 'reveal', 'control'])
def test_scorn_is_soft_or_hard_counter_from_cast_facts(cards, mode):
    s, spell, dragon = setup(cards, "Silumgar's Scorn")
    if mode == 'control':
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'battlefield'})
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', R=1, C=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p1'])
    wait_priority(s, 'p1')
    mana(s, U=2)
    cast(s, spell, reveal=mode == 'reveal', targets=[bolt.id])
    settle(s)
    if mode == 'none':
        d = s.state.rules.decision
        assert d and d.player == 'p2'
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
        settle(s)
    assert s.state.players['p1'].life == 40 - (3 if mode == 'none' else 0)
    roundtrip(s)


@pytest.mark.parametrize('mode', ['none', 'reveal', 'control'])
def test_prerogative_uncounterability_and_four_cards(cards, mode):
    s, spell, dragon = setup(cards, "Dragonlord's Prerogative")
    if mode == 'control':
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='set_prefs', hold_priority=True)
    before = len(s.state.zones['p1:hand'])
    mana(s, U=2, C=4)
    cast(s, spell, reveal=mode == 'reveal')
    # The frozen presence remains true after this permanent goes away.
    if mode == 'control':
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'graveyard'})
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[spell.id])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before - 1 + (4 if mode != 'none' else 0)
    roundtrip(s)


def test_optional_reveal_cannot_select_wrong_card_and_cast_does_not_require_reveal(cards):
    s, spell, dragon = setup(cards, 'Orator of Ojutai')
    act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'graveyard'})
    mana(s, W=2)
    with pytest.raises(ActionError):
        cast(s, spell, reveal=True)
    cast(s, spell)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('reveal', [False, True])
def test_changeling_qualifies_from_battlefield_and_hand(cards, reveal):
    s, spell, dragon = setup(cards, 'Orator of Ojutai', dragon_name='Changeling Outcast')
    if not reveal:
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'battlefield'})
    before = len(s.state.zones['p1:hand'])
    mana(s, W=2)
    cast(s, spell, reveal=reveal)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_acquiring_a_dragon_after_casting_does_not_create_cast_fact(cards):
    s, spell, dragon = setup(cards, 'Orator of Ojutai')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    before = len(s.state.zones['p1:hand'])
    mana(s, W=2)
    cast(s, spell)
    act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert len(s.state.zones['p1:hand']) == before - 2
    roundtrip(s)


def test_two_eligible_cards_private_saved_choice_reveals_only_selected(cards):
    s = table(cards, ['Orator of Ojutai', 'Shivan Dragon', 'Changeling Outcast'], ['Forest'])
    spell = put(s, 'Orator of Ojutai', 'hand')
    dragon = put(s, 'Shivan Dragon', 'hand')
    changeling = put(s, 'Changeling Outcast', 'hand')
    mana(s, W=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[], optional_costs=[f'{spell.id}:reveal'])
    d = s.state.rules.decision
    assert d and d.player == 'p1' and {o.card_id for o in d.options} == {dragon.id, changeling.id}
    assert not s.state.cards[dragon.id].revealed_to and not s.state.cards[changeling.id].revealed_to
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[dragon.id])
    settle(s)
    # Public reveal events disclose the selected cost card, never the other option.
    record = s.state.rules.payments.get(s.state.rules.object_id(spell.id))
    assert record and record.revealed == [dragon.id]
    assert not s.state.cards[changeling.id].revealed_to
    roundtrip(s)
