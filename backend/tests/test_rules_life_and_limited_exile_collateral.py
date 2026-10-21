"""Canonical collateral promotions: unlimited life-paid exile plays and a dead Witness's one shared play."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/life_and_limited_exile_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Inside Information', 'Unlucky Witness'])
def test_collateral_exile_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def top_cards(s, pid, names):
    ids = []
    for name in names:
        c = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name and c.id not in ids)
        ids.append(c.id)
    for cid in reversed(ids):
        act(s, pid, type='move', card_ids=[cid], to={'player': pid, 'zone': 'library'}, position='top')
    return ids


def information(s, x=3, target='p2'):
    spell = put(s, 'Inside Information', 'hand')
    mana(s, B=2, C=x)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, targets=[target])
    settle(s)
    return spell


def test_inside_information_all_exiled_cards_can_be_played_and_only_spells_cost_life(cards):
    s = table(cards, ['Inside Information'], ['Forest', 'Lightning Bolt', 'Grizzly Bears'])
    top = top_cards(s, 'p2', ['Forest', 'Lightning Bolt', 'Grizzly Bears'])
    spell = information(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    grants = [p for p in s.state.rules.permissions if p.card in top]
    assert len(grants) == 3 and all(p.life_mv and not p.group for p in grants)
    assert all(s.view('p3')['cards'][cid].get('name') for cid in top)
    life = s.state.players['p1'].life
    act(s, 'p1', type='play_land', card_id=top[0])
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p3'])
    settle(s)
    act(s, 'p1', type='cast_spell', card_id=top[2], free=True)
    settle(s)
    assert s.state.players['p1'].life == life - 3
    assert s.state.cards[top[0]].zone == s.state.cards[top[2]].zone == 'p1:battlefield'
    assert s.state.cards[top[1]].zone == 'p2:graveyard'
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)


def test_inside_information_zero_x_does_not_exile_or_grant_any_card(cards):
    s = table(cards, ['Inside Information'], ['Grizzly Bears'])
    before = list(s.state.zones['p2:library'])
    information(s, x=0)
    assert s.state.zones['p2:library'] == before and not s.state.rules.permissions
    roundtrip(s)


def test_inside_information_rejects_own_library_and_expiry_preserves_unplayed_exile(cards):
    s = table(cards, ['Inside Information'], ['Lightning Bolt'])
    top = top_cards(s, 'p2', ['Lightning Bolt'])
    spell = put(s, 'Inside Information', 'hand')
    mana(s, B=2, C=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1, targets=['p1'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1, targets=['p2'])
    settle(s)
    assert top[0] in view.hints(s.state, 'p1', cards)['free_castable']
    to_phase(s, 'main1', turn=2)
    assert s.state.cards[top[0]].zone == 'p2:exile'
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)


def dead_witness(cards, *, phase='main1', turn=1, extra_beginning=False):
    s = table(cards, ['Unlucky Witness', 'Shock', 'Forest', 'Lightning Bolt', 'Sphinx of the Second Sun'])
    witness = put(s, 'Unlucky Witness', 'battlefield')
    if extra_beginning:
        put(s, 'Sphinx of the Second Sun', 'battlefield')
    to_phase(s, phase, turn=turn)
    top = top_cards(s, 'p1', ['Forest', 'Lightning Bolt'])
    shock = put(s, 'Shock', 'hand')
    oid = s.state.rules.object_id(witness.id)
    wait_priority(s, 'p1')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=shock.id, targets=[witness.id])
    for _ in range(30):
        if s.state.cards[witness.id].zone == 'p1:graveyard':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('Witness never died from Shock')
    assert any(e.kind == 'trigger' and e.source_card == witness.id and e.source_object == oid for e in s.state.rules.stack.values())
    roundtrip(s)
    settle(s)
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in top)
    grants = [p for p in s.state.rules.permissions if p.card in top]
    assert len(grants) == 2 and len({p.group for p in grants}) == 1
    assert all(p.left == 1 and not p.life_mv and not p.free for p in grants)
    assert s.state.cards[witness.id].zone == 'p1:graveyard'
    return s, top


@pytest.mark.parametrize('land_first', [False, True])
def test_dead_witness_grants_only_one_shared_land_or_normal_mana_spell_play(cards, land_first):
    s, top = dead_witness(cards)
    life = s.state.players['p1'].life
    mana(s, R=1)
    if land_first:
        act(s, 'p1', type='play_land', card_id=top[0])
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=top[1], targets=['p2'])
        assert mana_pool(s).get('R') == 1
    else:
        act(s, 'p1', type='cast_spell', card_id=top[1], targets=['p2'])
        settle(s)
        with pytest.raises(ActionError):
            act(s, 'p1', type='play_land', card_id=top[0])
        assert mana_pool(s) == {}
    assert s.state.players['p1'].life == life
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)


def test_witness_main_phase_grant_expires_at_start_of_that_turns_own_end_step(cards):
    s, top = dead_witness(cards)
    to_phase(s, 'end', turn=1)
    assert not [p for p in s.state.rules.permissions if p.card in top]
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in top)
    roundtrip(s)


def test_witness_dying_during_own_end_step_survives_until_next_own_end_step(cards):
    s, top = dead_witness(cards, phase='end', turn=1)
    assert len([p for p in s.state.rules.permissions if p.card in top]) == 2
    to_phase(s, 'main1', turn=4)
    assert len([p for p in s.state.rules.permissions if p.card in top]) == 2
    to_phase(s, 'end', turn=4)
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)


def test_witness_dying_on_opponent_turn_ignores_intervening_other_players_end_steps(cards):
    s, top = dead_witness(cards, turn=2)
    to_phase(s, 'end', turn=2)
    assert len([p for p in s.state.rules.permissions if p.card in top]) == 2
    to_phase(s, 'end', turn=3)
    assert len([p for p in s.state.rules.permissions if p.card in top]) == 2
    to_phase(s, 'end', turn=4)
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)


def test_witness_grant_during_additional_beginning_phase_expires_at_following_restored_end_step(cards):
    s, top = dead_witness(cards, phase='upkeep', turn=1, extra_beginning=True)
    assert s.state.rules.extra_phases == ['end']
    to_phase(s, 'end', turn=1)
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)
