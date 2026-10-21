"""Exact exile-batch permissions and delayed remaining-card damage."""
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
from tests.test_rules_abundance import set_library
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Powerbalance'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/powerbalance_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()






def setup(cards, top_name='Divination', spell_name='Divination', x=0, defer=False):
    names = ['Powerbalance', 'Lightning Bolt', 'Grizzly Bears', 'Divination', 'Counterspell', 'Fireball',
             'Bonecrusher Giant // Stomp', 'Valki, God of Lies // Tibalt, Cosmic Impostor',
             'Turntimber Symbiosis // Turntimber, Serpentine Wood', 'Ancestral Vision', 'Trinisphere', 'Fling', 'Forest', 'Island', 'Stonecoil Serpent', 'Future Sight']
    s = table(cards, names, ['Divination', 'Fireball', 'Grizzly Bears', 'Lightning Bolt', 'Ornithopter'])
    source = put(s, NAME, 'hand')
    mana(s, R=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    to_phase(s, 'main1', turn=2)
    settle(s)
    top = set_library(s, [top_name, 'Forest' if top_name != 'Forest' else 'Island', 'Island' if top_name != 'Forest' else 'Grizzly Bears'])
    spell = put(s, spell_name, 'hand', 'p2')
    mana(s, C=20, R=5, U=5, G=5, pid='p2')
    args = {'x_value': x, 'targets': ['p1']} if spell_name == 'Fireball' else {'targets': ['p1']} if spell_name == 'Lightning Bolt' else {}
    act(s, 'p2', type='cast_spell', card_id=spell.id, **args)
    if defer:
        return s, source, spell, top, None
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'confirm' and d.player == 'p1'
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    assert not s.view('p2')['cards'].get(top[0], {}).get('name')
    roundtrip(s)
    return s, source, spell, top, d


def reveal(s, d):
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    return s.state.rules.decision


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_optional_reveal_decline_does_not_expose_or_cast_top(cards):
    s, source, spell, top, d = setup(cards)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert not s.view('p2')['cards'].get(top[0], {}).get('name')
    assert s.state.cards[top[0]].zone == 'p1:library'
    roundtrip(s)


def test_reveal_and_decline_cast_hides_original_top_without_moving_it(cards):
    s, source, spell, top, d = setup(cards)
    d = reveal(s, d)
    assert d is not None and top[0] in {o.id for o in d.options}
    assert s.view('p2')['cards'][top[0]]['name'] == 'Divination'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.zones['p1:library'] == top
    assert not s.view('p2')['cards'].get(top[0], {}).get('name')
    roundtrip(s)


@pytest.mark.parametrize('top_name', ['Lightning Bolt', 'Forest'])
def test_mismatch_and_land_are_revealed_but_not_cast_or_played(cards, top_name):
    s, source, spell, top, d = setup(cards, top_name=top_name)
    d = reveal(s, d)
    if d is not None:
        assert d.options == []
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[top[0]].zone == 'p1:library' and not s.state.cards[top[0]].revealed_to
    roundtrip(s)


def test_actual_cast_uses_resolution_permission_without_mana(cards):
    s, source, spell, top, d = setup(cards)
    d = reveal(s, d)
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) >= 2
    assert not s.state.rules.permissions
    roundtrip(s)


@pytest.mark.parametrize('top_name,opponent_x,eligible_face', [
    ('Bonecrusher Giant // Stomp', 1, 1),
    ('Bonecrusher Giant // Stomp', 2, 0),
    ('Valki, God of Lies // Tibalt, Cosmic Impostor', 1, 0),
    ('Valki, God of Lies // Tibalt, Cosmic Impostor', 6, 1),
])
def test_actual_cast_spell_face_mana_value_filters_adventure_and_modal_faces(cards, top_name, opponent_x, eligible_face):
    s, source, spell, top, d = setup(cards, top_name=top_name, spell_name='Fireball', x=opponent_x)
    d = reveal(s, d)
    assert d is not None and len(d.options) == 1
    option = d.options[0].id
    assert option == top[0] + f'@{eligible_face}'
    roundtrip(s)
    if top_name.startswith('Valki') or eligible_face == 0:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[option])
        settle(s)
        assert s.state.cards[top[0]].zone == 'p1:battlefield'
        assert s.state.cards[top[0]].face == eligible_face
    else:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[option])
        settle(s)
        target = s.state.rules.decision
        assert target is not None and 'p2' in {o.id for o in target.options}
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=target.id, option_ids=['p2'])
        settle(s)
        assert s.state.cards[top[0]].zone == 'p1:exile'
        assert s.state.players['p2'].life == 38
    roundtrip(s)



def test_countered_opponent_spell_keeps_announced_x_for_lki_comparison(cards):
    s, source, spell, top, _ = setup(cards, top_name='Bonecrusher Giant // Stomp', spell_name='Fireball', x=2, defer=True)
    counter = put(s, 'Counterspell', 'hand')
    mana(s, U=2)
    for _ in range(3):
        if s.state.rules.priority in (None, 'p1'):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    d = s.state.rules.decision
    assert d is not None and d.kind == 'confirm'
    d = reveal(s, d)
    assert d is not None and {o.id for o in d.options} == {top[0] + '@0'}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0] + '@0'])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:battlefield'
    roundtrip(s)


def test_revealed_old_incarnation_is_not_cast_after_library_departure_and_return(cards):
    s, source, spell, top, d = setup(cards)
    d = reveal(s, d)
    assert d is not None
    act(s, 'p1', type='move', card_ids=[top[0]], to={'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[top[0]], to={'zone': 'library'}, position='top')
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:library'
    assert not s.state.rules.free_casts and not s.state.rules.permissions
    roundtrip(s)


@pytest.mark.parametrize('change', ['leave', 'controller'])
def test_trigger_retains_original_controller_when_source_changes(cards, change):
    s, source, spell, top, _ = setup(cards, defer=True)
    if change == 'leave':
        act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    else:
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    d = reveal(s, d)
    assert d is not None and top[0] in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    if change == 'controller' and (new := s.state.rules.decision) is not None:
        assert new.player == 'p3' and new.kind == 'confirm'
        act(s, 'p3', type='choose', decision_id=new.id, option_ids=['no'])
        settle(s)
    assert s.state.cards[top[0]].zone == 'p1:graveyard'
    roundtrip(s)


def test_top_at_resolution_is_used_instead_of_top_at_trigger_time(cards):
    s, source, spell, top, _ = setup(cards, defer=True)
    act(s, 'p1', type='move', card_ids=[top[0]], to={'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    d = reveal(s, d)
    if d is not None:
        assert not d.options
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[top[1]].zone == 'p1:library' and not s.state.cards[top[1]].revealed_to
    roundtrip(s)


def test_empty_library_reveals_nothing_and_does_not_cast(cards):
    s, source, spell, top, _ = setup(cards, defer=True)
    act(s, 'p1', type='move', card_ids=top, to={'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    reveal(s, d)
    assert s.state.rules.decision is None and not s.state.rules.free_casts
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_trinisphere_mandatory_cost_can_be_paid_or_cancelled(cards, pay):
    s, source, spell, top, _ = setup(cards, top_name='Grizzly Bears', spell_name='Fireball', x=1, defer=True)
    put(s, 'Trinisphere', 'battlefield')
    settle(s)
    d = reveal(s, s.state.rules.decision)
    assert d is not None
    if pay:
        mana(s, C=3)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
        settle(s)
        from tests.game_helpers import mana_pool

        assert s.state.cards[top[0]].zone == 'p1:battlefield' and not mana_pool(s)
    else:
        from app.game.errors import ActionError

        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
        assert s.state.model_dump(mode='json') == before
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
        assert s.state.cards[top[0]].zone == 'p1:library' and not s.state.cards[top[0]].revealed_to
    assert not s.state.rules.permissions and not s.state.rules.free_casts
    roundtrip(s)


def test_exact_reference_is_revalidated_during_target_announcement(cards):
    from app.game.errors import ActionError

    s, source, spell, top, d = setup(cards, top_name='Lightning Bolt', spell_name='Fireball', x=0)
    d = reveal(s, d)
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and 'p2' in {o.id for o in d.options}
    act(s, 'p1', type='move', card_ids=[top[0]], to={'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[top[0]], to={'zone': 'library'}, position='top')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:library' and not s.state.rules.free_casts
    roundtrip(s)



def test_free_x_spell_uses_x_zero_for_actual_cast_and_state_actions(cards):
    s, source, spell, top, d = setup(cards, top_name='Stonecoil Serpent', spell_name='Ornithopter')
    d = reveal(s, d)
    assert d is not None and {o.id for o in d.options} == {top[0]}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:graveyard'
    records = [p for p in s.state.rules.payments.values() if p.card == top[0]]
    assert records and (records[-1].x or 0) == 0
    assert s.state.rules.decision is None
    roundtrip(s)


def test_no_mana_cost_spell_can_be_cast_for_free_at_mana_value_zero(cards):
    s, source, spell, top, d = setup(cards, top_name='Ancestral Vision', spell_name='Ornithopter')
    spare = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1')
    act(s, 'p1', type='move', card_ids=[spare.id], to={'zone': 'library'}, position='bottom')
    d = reveal(s, d)
    assert d is not None and {o.id for o in d.options} == {top[0]}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    target = s.state.rules.decision
    assert target is not None and 'p1' in {o.id for o in target.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=target.id, option_ids=['p1'])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:graveyard'
    assert s.state.rules.decision is None and not s.state.players['p1'].left
    assert all(s.state.cards[c].zone == 'p1:hand' for c in [*top[1:], spare.id])
    roundtrip(s)


def test_cleanup_preserves_independent_continuous_top_reveal(cards):
    s, source, spell, top, d = setup(cards)
    put(s, 'Future Sight', 'battlefield')
    d = reveal(s, d)
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert not s.state.cards[top[0]].revealed_to
    assert s.view('p2')['cards'][top[0]]['name'] == 'Divination'
    roundtrip(s)
