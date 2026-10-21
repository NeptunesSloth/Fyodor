"""Taking control of spells preserves their choices, ownership and distinct Aura targeting."""
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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/spell_control_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAMES = ['Commandeer', 'Aethersnatch', 'Invert Polarity']


def setup(cards):
    return table(cards, [*NAMES, 'Lightning Bolt', 'Counterspell', 'Blaze', 'Leyline of Sanctity', 'Misdirection', 'Holy Strength', 'Gemrazer', 'Ornithopter', 'Grizzly Bears'],
                 ['Lightning Bolt', 'Blaze', 'Holy Strength', 'Gemrazer', 'Ornithopter', 'Sol Ring', 'Perilous Myr', 'Leyline of Sanctity', 'Slippery Bogle', 'Burst Lightning', 'Prodigal Pyromancer', 'Cartouche of Knowledge', 'Revitalize'], ['Act of Treason', 'Zealous Conscripts'])


def cast_steal(s, target, name='Aethersnatch', **extra):
    spell = put(s, name, 'hand')
    wait_priority(s, 'p1')
    costs = {'Commandeer': {'C': 5, 'U': 2}, 'Aethersnatch': {'C': 4, 'U': 2}, 'Invert Polarity': {'U': 2, 'R': 1}}
    if not extra.get('alt_cost'):
        mana(s, **costs[name])
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], **extra)
    return spell, until_asked(s)


@pytest.mark.parametrize('name', NAMES)
def test_spell_control_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Commandeer', 'Aethersnatch'])
@pytest.mark.parametrize('keep', [False, True])
def test_instant_changes_controller_but_not_owner_or_cast_history(cards, name, keep):
    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    oid = s.state.rules.object_id(bolt.id)
    before = list(s.state.zones['stack'])
    _, d = cast_steal(s, bolt, name)
    assert d.player == 'p1' and d.resume['step'] == 'choose_new_targets'
    assert s.state.cards[bolt.id].controller == s.state.rules.stack[bolt.id].controller == 'p1'
    assert s.state.cards[bolt.id].owner == 'p2' and s.state.rules.object_id(bolt.id) == oid
    assert [n.player for n in s.state.rules.turn_log.casts if n.object_id == oid] == ['p2']
    assert before[0] == s.state.zones['stack'][0]
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep' if keep else 'p2'])
    settle(s)
    assert s.state.players['p3' if keep else 'p2'].life == 37
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_targetless_permanent_enters_under_new_controller(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=2)
    ring = put(s, 'Sol Ring', 'hand', 'p2')
    mana(s, 'p2', C=1)
    act(s, 'p2', type='cast_spell', card_id=ring.id)
    assert ring.id not in s.state.rules.stack
    cast_steal(s, ring)
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield' and s.state.cards[ring.id].controller == 'p1'
    assert s.state.cards[ring.id].owner == 'p2'
    roundtrip(s)


def test_aura_target_can_change_without_creating_effect_spell_entry(cards):
    from tests.test_rules_attachments import ch
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    own = put(s, 'Ornithopter', 'battlefield')
    theirs = put(s, 'Ornithopter', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    aura = put(s, 'Holy Strength', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=aura.id, targets=[theirs.id])
    assert aura.id not in s.state.rules.stack
    _, d = cast_steal(s, aura, 'Commandeer')
    assert d.resume['step'] == 'choose_new_targets' and own.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[own.id])
    assert aura.id not in s.state.rules.stack
    settle(s)
    assert s.state.cards[aura.id].zone == 'p1:battlefield' and s.state.cards[aura.id].attached_to == own.id
    assert ch(s, own).pt == (1, 4) and ch(s, theirs).pt == (0, 2)
    roundtrip(s)



@pytest.mark.parametrize('win', [False, True])
def test_invert_polarity_uses_recorded_coin_branch(cards, monkeypatch, win):
    monkeypatch.setattr('app.game.resolve._rng_int', lambda rng, lo, hi: int(win))
    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    _, d = cast_steal(s, bolt, 'Invert Polarity')
    if win:
        assert d.player == 'p1' and s.state.cards[bolt.id].controller == 'p1'
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    else:
        assert d is None
    settle(s)
    assert s.state.players['p2'].life == (37 if win else 40)
    assert s.state.players['p3'].life == 40 and s.state.cards[bolt.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_commandeer_alternative_cost_privately_exiles_exactly_two_other_blue_cards(cards):
    s = setup(cards)
    spell = put(s, 'Commandeer', 'hand')
    a = put(s, 'Counterspell', 'hand')
    b = put(s, 'Misdirection', 'hand')
    put(s, 'Aethersnatch', 'hand')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bolt.id], alt_cost=f'{spell.id}:0')
    d = s.state.rules.decision
    assert d.player == 'p1' and d.min_choices == 0 and d.max_choices == 2
    assert {a.id, b.id} <= {o.id for o in d.options} and spell.id not in {o.id for o in d.options}
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    assert s.state.cards[spell.id].zone == 'p1:hand'
    roundtrip(s)
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[a.id])
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[a.id, b.id])
    d = until_asked(s)
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == 'p1:exile'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert s.state.players['p3'].life == 37 and s.state.cards[bolt.id].owner == 'p2'
    roundtrip(s)


def test_retarget_uses_new_spell_controller_for_player_hexproof(cards):
    s = setup(cards)
    put(s, 'Leyline of Sanctity', 'battlefield')
    put(s, 'Leyline of Sanctity', 'battlefield', 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    _, d = cast_steal(s, bolt)
    assert 'p1' in {o.id for o in d.options} and 'p2' not in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    settle(s)
    assert s.state.players['p1'].life == 37 and s.state.players['p3'].life == 40
    roundtrip(s)


def mutate_cast(s, target):
    from tests.test_rules_wave18d_merged import mutate_key

    gem = put(s, 'Gemrazer', 'hand', 'p2')
    mana(s, 'p2', G=3)
    act(s, 'p2', type='cast_spell', card_id=gem.id, targets=[target.id], alt_cost=mutate_key(s, gem, 'p2'))
    return gem


def test_stolen_mutate_retargets_by_owner_and_merged_host_keeps_its_controller(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    wrong_owner = put(s, 'Grizzly Bears', 'battlefield')
    first = put(s, 'Ornithopter', 'battlefield', 'p2')
    second = put(s, 'Perilous Myr', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    gem = mutate_cast(s, first)
    _, d = cast_steal(s, gem)
    assert second.id in {o.id for o in d.options} and wrong_owner.id not in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[second.id])
    d = until_asked(s)
    assert d.player == 'p1' and d.resume['step'] == 'mutate_choice'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['under'])
    settle(s)
    assert gem.id not in s.state.cards and s.state.cards[second.id].controller == 'p2'
    assert {p.name for p in s.state.cards[second.id].merged} == {'Perilous Myr', 'Gemrazer'}
    roundtrip(s)


@pytest.mark.parametrize('invalid', ['zone', 'hexproof'])
def test_stolen_mutate_with_illegal_target_enters_normally_under_new_controller(cards, invalid):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    target = put(s, 'Slippery Bogle' if invalid == 'hexproof' else 'Ornithopter', 'battlefield', 'p2')
    put(s, 'Perilous Myr', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    gem = mutate_cast(s, target)
    _, d = cast_steal(s, gem)
    if d is not None:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    if invalid == 'zone':
        act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'hand'})
    settle(s)
    assert s.state.cards[gem.id].zone == 'p1:battlefield' and s.state.cards[gem.id].controller == 'p1'
    assert not s.state.cards[gem.id].merged and s.state.cards[gem.id].owner == 'p2'
    roundtrip(s)



@pytest.mark.parametrize('kind', ['x', 'kicker'])
def test_control_preserves_announced_x_and_paid_kicker(cards, kind):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=2)
    spell = put(s, 'Blaze' if kind == 'x' else 'Burst Lightning', 'hand', 'p2')
    mana(s, 'p2', C=4, R=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=['p3'], **({'x_value': 4} if kind == 'x' else {'kicker': 1}))
    oid = s.state.rules.object_id(spell.id)
    _, d = cast_steal(s, spell)
    if kind == 'x':
        assert s.state.rules.stack[spell.id].x == s.state.cards[spell.id].stack_info.x == 4
    else:
        assert s.state.rules.stack[spell.id].kicked == 1
    assert [n.player for n in s.state.rules.turn_log.casts if n.object_id == oid] == ['p2']
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 36 and s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', ['Commandeer', 'Aethersnatch'])
def test_spell_control_does_not_target_activated_abilities(cards, name):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    pyro = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='activate_ability', card_id=pyro.id, ability=0, targets=['p3'])
    ability = s.state.cards[s.state.zones['stack'][-1]]
    spell = put(s, name, 'hand')
    wait_priority(s, 'p1')
    mana(s, C=5, U=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ability.id])
    assert s.state.cards[ability.id].controller == 'p2' and s.state.cards[spell.id].zone == 'p1:hand'
    settle(s)
    roundtrip(s)


def test_commandeer_cannot_target_a_creature_spell(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=2)
    creature = put(s, 'Ornithopter', 'hand', 'p2')
    act(s, 'p2', type='cast_spell', card_id=creature.id)
    spell = put(s, 'Commandeer', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=5, U=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creature.id])
    assert s.state.cards[creature.id].controller == 'p2' and s.state.cards[spell.id].zone == 'p1:hand'
    settle(s)
    roundtrip(s)



def test_untargeted_spell_instructions_use_new_controller(cards):
    s = setup(cards)
    original = put(s, 'Revitalize', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', W=1, C=1)
    act(s, 'p2', type='cast_spell', card_id=original.id)
    _, d = cast_steal(s, original)
    assert d is None
    settle(s)
    assert s.state.players['p1'].life == 43 and s.state.players['p2'].life == 40
    assert s.state.cards[original.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('keep', [False, True])
def test_controlled_aura_enchant_restriction_uses_new_controller(cards, keep):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    own = put(s, 'Ornithopter', 'battlefield')
    theirs = put(s, 'Ornithopter', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    aura = put(s, 'Cartouche of Knowledge', 'hand', 'p2')
    mana(s, 'p2', C=1, U=1)
    act(s, 'p2', type='cast_spell', card_id=aura.id, targets=[theirs.id])
    _, d = cast_steal(s, aura)
    assert own.id in {o.id for o in d.options} and theirs.id not in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep' if keep else own.id])
    settle(s)
    if keep:
        assert s.state.cards[aura.id].zone == 'p2:graveyard'
    else:
        assert s.state.cards[aura.id].zone == 'p1:battlefield' and s.state.cards[aura.id].attached_to == own.id
    roundtrip(s)


def test_temporary_control_returns_to_stolen_spells_entry_controller(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=2)
    original = put(s, 'Ornithopter', 'hand', 'p2')
    act(s, 'p2', type='cast_spell', card_id=original.id)
    _, d = cast_steal(s, original)
    if d is not None:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert s.state.cards[original.id].controller == 'p1'
    to_phase(s, 'main1', turn=3)
    threaten = put(s, 'Act of Treason', 'hand', 'p3')
    mana(s, 'p3', C=2, R=1)
    act(s, 'p3', type='cast_spell', card_id=threaten.id, targets=[original.id])
    settle(s)
    assert s.state.cards[original.id].controller == 'p3'
    assert s.state.rules.control_baselines[s.state.rules.object_id(original.id)] == 'p1'
    roundtrip(s)
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[original.id].controller == 'p1' and s.state.cards[original.id].owner == 'p2'
    assert not s.state.rules.control_baselines
    roundtrip(s)



def test_temporary_permanent_control_returns_stolen_aura_to_entry_controller(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    host = put(s, 'Ornithopter', 'battlefield')
    to_phase(s, 'main1', turn=2)
    aura = put(s, 'Holy Strength', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=aura.id, targets=[host.id])
    _, d = cast_steal(s, aura)
    if d is not None:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    to_phase(s, 'main1', turn=3)
    conscripts = put(s, 'Zealous Conscripts', 'hand', 'p3')
    mana(s, 'p3', C=4, R=1)
    act(s, 'p3', type='cast_spell', card_id=conscripts.id)
    d = until_asked(s)
    act(s, 'p3', type='choose', decision_id=d.id, option_ids=[aura.id])
    settle(s)
    assert s.state.cards[aura.id].controller == 'p3'
    assert s.state.cards[aura.id].attached_to == host.id
    roundtrip(s)
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[aura.id].controller == 'p1' and s.state.cards[aura.id].owner == 'p2'
    assert s.state.cards[aura.id].attached_to == host.id
    roundtrip(s)
