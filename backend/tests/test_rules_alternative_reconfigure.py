"""CR 702.151a, 602.2b: alternative reconfigure costs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/alternative_reconfigure_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Razorfield Ripper'


def test_ripper_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, energy=0, tax=False, training=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Grizzly Bears', 'Suppression Field', 'Training Grounds'], ['Stifle'])
    source = put(s, NAME, 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    if energy:
        act(s, 'p1', type='resource', player='p1', key='energy', delta=energy)
    if tax:
        put(s, 'Suppression Field', 'battlefield')
    if training:
        put(s, 'Training Grounds', 'battlefield')
    return s, source, host


def activate(s, source, host, *, unattach=False, side=None):
    from tests.game_helpers import act

    kwargs = {} if side is None else {'cost_choices': [{'component': 20, 'cards': [f'either:{side}']}]}
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=3 if unattach else 2,
        targets=[] if unattach else [host.id], **kwargs)


@pytest.mark.parametrize('side', [0, 1])
def test_either_payment_attach_and_unattach(cards, side):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, host = setup(cards, energy=6)
    mana(s, C=4)
    for unattach in [False, True]:
        wait_priority(s, 'p1')
        energy = s.state.players['p1'].resources['energy']
        pool = s.state.players['p1'].mana.get('C', 0)
        activate(s, source, host, unattach=unattach)
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {'either:0', 'either:1'}
        assert s.state.players['p1'].resources['energy'] == energy
        assert s.state.players['p1'].mana.get('C', 0) == pool
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[f'either:{side}'])
        assert s.state.players['p1'].resources['energy'] == energy - (3 if side else 0)
        assert s.state.players['p1'].mana.get('C', 0) == pool - (0 if side else 2)
        settle(s)
        assert s.state.cards[source.id].attached_to == (None if unattach else host.id)
        assert chars(s, source).is_creature == unattach
        roundtrip(s)


@pytest.mark.parametrize('side', [0, 1])
def test_activation_tax_applies_to_each_cost(cards, side):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, host = setup(cards, energy=3, tax=True)
    mana(s, C=4 if side == 0 else 2)
    activate(s, source, host, side=side)
    settle(s)
    assert s.state.cards[source.id].attached_to == host.id
    assert not any(s.state.players['p1'].mana.values())
    assert s.state.players['p1'].resources['energy'] == (3 if side == 0 else 0)
    roundtrip(s)


@pytest.mark.parametrize('energy,pool,side', [(0, 2, 0), (3, 0, 1)])
def test_only_payable_side_is_used_without_prompt(cards, energy, pool, side):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, host = setup(cards, energy=energy)
    if pool:
        mana(s, C=pool)
    activate(s, source, host)
    assert s.state.rules.decision is None
    settle(s)
    assert s.state.cards[source.id].attached_to == host.id
    assert not s.state.players['p1'].resources.get('energy', 0)
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_cost_prompt_can_be_cancelled_without_payment(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, source, host = setup(cards, energy=3)
    mana(s, C=2)
    activate(s, source, host)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    assert not s.state.zones.get('stack') and s.state.rules.decision is None
    assert s.state.players['p1'].resources['energy'] == 3
    assert s.state.players['p1'].mana['C'] == 2
    roundtrip(s)


@pytest.mark.parametrize('energy,pool,tax', [(2, 1, False), (3, 0, True)])
def test_unpayable_cost_is_atomic_and_not_an_available_action(cards, energy, pool, tax):
    from app.game.errors import ActionError
    from app.rules.casting import activatable
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, source, host = setup(cards, energy=energy, tax=tax)
    if pool:
        mana(s, C=pool)
    assert {'card_id': source.id, 'ability': 2} not in activatable(s.state, 'p1', s.cards, check_priority=False)
    with pytest.raises(ActionError):
        activate(s, source, host)
    assert s.state.players['p1'].resources['energy'] == energy
    assert s.state.players['p1'].mana.get('C', 0) == pool
    assert s.state.cards[source.id].attached_to is None
    roundtrip(s)


def test_self_target_and_unattached_detach_are_illegal(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, source, host = setup(cards, energy=3)
    mana(s, C=2)
    with pytest.raises(ActionError):
        activate(s, source, source, side=1)
    with pytest.raises(ActionError):
        activate(s, source, host, unattach=True, side=1)
    assert s.state.players['p1'].resources['energy'] == 3 and s.state.players['p1'].mana['C'] == 2
    roundtrip(s)


def test_reconfigure_requires_sorcery_timing(cards):
    from app.game.errors import ActionError
    from app.rules.casting import activatable
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, source, host = setup(cards, energy=3)
    to_phase(s, 'begin_combat', turn=1)
    assert {'card_id': source.id, 'ability': 2} not in activatable(s.state, 'p1', s.cards, check_priority=False)
    with pytest.raises(ActionError):
        activate(s, source, host, side=1)
    assert s.state.players['p1'].resources['energy'] == 3
    roundtrip(s)


def test_cost_reduction_tracks_creature_status_after_attachment(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, host = setup(cards, training=True)
    mana(s, C=1)
    activate(s, source, host, side=0)
    settle(s)
    assert s.state.cards[source.id].attached_to == host.id
    wait_priority(s, 'p1')
    mana(s, C=2)
    activate(s, source, host, unattach=True, side=0)
    settle(s)
    # Training Grounds' minimum one applies to the creature's attach cost;
    # after attachment it is not a creature, so unattach costs the full two.
    assert not any(s.state.players['p1'].mana.values())
    assert s.state.cards[source.id].attached_to is None
    roundtrip(s)


def test_stifle_retains_energy_payment_without_attaching(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, source, host = setup(cards, energy=3)
    activate(s, source, host, side=1)
    wait_priority(s, 'p2')
    spell = put(s, 'Stifle', 'hand', pid='p2')
    mana(s, pid='p2', U=1)
    ability = s.state.zones['stack'][-1]
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[ability])
    settle(s)
    assert s.state.cards[source.id].attached_to is None
    assert s.state.players['p1'].resources['energy'] == 0
    roundtrip(s)


@pytest.mark.parametrize('attached', [False, True])
def test_attacking_source_or_host_gets_energy_then_uses_new_total(cards, attached):
    from tests.test_rules_banding import declare_only
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, host = setup(cards, energy=2)
    if attached:
        mana(s, C=2)
        activate(s, source, host, side=0)
        settle(s)
    attacker = host if attached else source
    declare_only(s, [attacker], [])
    settle(s)
    assert s.state.players['p1'].resources['energy'] == 3
    assert chars(s, attacker).pt == ((5, 5) if attached else (6, 6))
    roundtrip(s)
