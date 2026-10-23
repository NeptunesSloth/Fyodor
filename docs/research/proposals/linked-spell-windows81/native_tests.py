"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/linked_spell_windows81_cards.json').read_text())
RIOTER, AZULA = 'Boiling Rock Rioter', 'Azula, Cunning Usurper'
ENVOY = 'Expedition Envoy'
NAMES = [RIOTER, AZULA]
BIRGI = 'Birgi, God of Storytelling // Harnfel, Horn of Bounty'
DOG = 'Isamaru, Hound of Konda'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='lc76', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc76', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest', ENVOY, 'Akoum Battlesinger',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')




@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical81(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'



def azula_pool(cards):
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[own.id], player='p2')
    other = put(s, ENVOY, 'battlefield', pid='p2')
    act(s, 'p2', type='create_token', player='p2', token={'name': 'Decoy', 'type_line': 'Token Creature — Goblin',
                                                       'power': '2', 'toughness': '2'})
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == 'Decoy')
    bolt = put(s, 'Lightning Bolt', 'graveyard', pid='p2')
    alternative = put(s, 'Divination', 'graveyard', pid='p2')
    land = put(s, 'Forest', 'graveyard', pid='p2')
    source = cast(s, AZULA)
    answer(s, ['p2'])
    d = s.state.rules.decision
    assert d and d.player == 'p2' and {own.id, other.id} <= {o.id for o in d.options}
    assert token.id not in {o.id for o in d.options}
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[own.id])
    assert s.state.model_dump(mode='json') == before
    answer(s, [own.id])
    d = s.state.rules.decision
    assert d and d.player == 'p2' and {bolt.id, alternative.id} <= {o.id for o in d.options}
    assert land.id not in {o.id for o in d.options}
    answer(s, [bolt.id])
    assert s.state.cards[own.id].zone == 'p1:exile' and s.state.cards[bolt.id].zone == 'p2:exile'
    assert s.state.cards[other.id].zone == s.state.cards[token.id].zone == 'p2:battlefield'
    linked = s.state.rules.exiled_with[s.state.rules.object_id(source.id)]
    assert {s.state.rules.object_id(own.id), s.state.rules.object_id(bolt.id)} <= set(linked)
    return s, source.id, own.id, bolt.id


def test_actual_azula_paid_any_type_unlimited81(cards):
    s, source, own, bolt = azula_pool(cards)
    act(s, 'p1', type='clear_mana')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=own)
    settle(s)
    assert s.state.cards[own].zone == 'p1:battlefield'
    life = s.state.players['p2'].life
    act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    settle(s)
    assert s.state.cards[bolt].zone == 'p2:graveyard' and s.state.players['p2'].life == life - 3
    assert not s.state.players['p1'].mana
    roundtrip(s)


def rioter_choice(cards, *, payable=True):
    s = setup(cards)
    source = cast(s, RIOTER)
    helper = put(s, ENVOY, 'battlefield')
    target = next(c for c in s.state.cards.values() if c.name == ENVOY and c.owner == 'p1' and c.id != helper.id)
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Tap an untapped Ally'),
        targets=[target.id], cost_choices=[{'component': 0, 'cards': [helper.id]}])
    settle(s)
    assert helper.tapped and not source.tapped and s.state.cards[target.id].zone == 'p1:exile'
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='clear_mana')
    mana(s, **({'W': 1} if payable else {'C': 1}))
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    return s, source.id, target.id


def test_actual_rioter_paid_choice81(cards):
    s, source, target = rioter_choice(cards)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and target in {o.id for o in d.options}
    answer(s, [target])
    settle(s)
    assert s.state.cards[target].zone == 'p1:battlefield'
    record = s.state.rules.payments[s.state.rules.object_id(target)]
    assert record.mana_spent == {'W': 1} and record.alternative is None
    roundtrip(s)


def test_rioter_does_not_waive_cost81(cards):
    s, source, target = rioter_choice(cards, payable=False)
    d = s.state.rules.decision
    assert d and target in {o.id for o in d.options}
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target])
    assert s.state.model_dump(mode='json') == before
    answer(s, [])
    settle(s)
    mana(s, W=1)
    assert not casting.castable(s.state, 'p1', s.state.cards[target], cards)
    roundtrip(s)


def test_azula_own_turn_only_and_native_flash81(cards):
    s, source, own, bolt = azula_pool(cards)
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    mana(s, C=3)
    assert not casting.castable(s.state, 'p1', s.state.cards[bolt], cards)
    assert not casting.castable(s.state, 'p1', s.state.cards[own], cards)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    mana(s, C=2)
    assert s.state.turn.phase == 'upkeep'
    assert casting.castable(s.state, 'p1', s.state.cards[own], cards)
    act(s, 'p1', type='cast_spell', card_id=own)
    settle(s)
    assert s.state.cards[own].zone == 'p1:battlefield'
    roundtrip(s)


def test_azula_current_controller81(cards):
    s, source, own, bolt = azula_pool(cards)
    act(s, 'p1', type='set_controller', card_ids=[source], player='p2')
    mana(s, C=3)
    assert not casting.castable(s.state, 'p1', s.state.cards[own], cards)
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    mana(s, pid='p2', C=2)
    assert casting.castable(s.state, 'p2', s.state.cards[own], cards)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=own)
    settle(s)
    assert s.state.cards[own].controller == 'p2' and s.state.cards[own].owner == 'p1'
    roundtrip(s)


def test_azula_source_departure81(cards):
    s, source, own, bolt = azula_pool(cards)
    mana(s, C=3, U=1)
    bounce = put(s, 'Disperse', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[source])
    settle(s)
    mana(s, C=4)
    assert s.state.cards[source].zone == 'p1:hand'
    assert not casting.castable(s.state, 'p1', s.state.cards[own], cards)
    assert not casting.castable(s.state, 'p1', s.state.cards[bolt], cards)
    roundtrip(s)


@pytest.mark.parametrize('mode', ['azula', 'rioter'])
def test_genuine_fresh_process_linked_authorities81(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    if mode == 'azula':
        s, source, target, bolt = azula_pool(cards)
        act(s, 'p1', type='clear_mana')
        mana(s, C=2)
    else:
        s, source, target = rioter_choice(cards)
    saved = tmp_path / 'linked81.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_library_look import settle
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
cid,mode=sys.argv[3:]
if mode=='azula':
 act(s,'p1',type='cast_spell',card_id=cid)
else:
 d=s.state.rules.decision
 assert d and cid in {o.id for o in d.options}
 answer(s,[cid])
settle(s)
assert s.state.cards[cid].zone=='p1:battlefield'
p=s.state.rules.payments[s.state.rules.object_id(cid)]
assert p.alternative is None
assert p.mana_spent==({'C':2} if mode=='azula' else {'W':1})
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target, mode],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def test_rioter_attack_filters_owner_type_and_original_link81(cards):
    s = setup(cards)
    source = cast(s, RIOTER)
    helpers = [put(s, ENVOY, 'battlefield'), put(s, 'Akoum Battlesinger', 'battlefield')]
    targets = [next(c for c in s.state.cards.values() if c.name == ENVOY and c.owner == 'p1' and c.id != helpers[0].id),
               put(s, ENVOY, 'graveyard', pid='p2'), put(s, 'Grizzly Bears', 'graveyard')]
    act(s, 'p1', type='move', card_ids=[targets[0].id], to={'player': 'p1', 'zone': 'graveyard'})
    for target, helper in zip(targets, [*helpers, source], strict=True):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Tap an untapped Ally'),
            targets=[target.id], cost_choices=[{'component': 0, 'cards': [helper.id]}])
        settle(s)
    unlinked = next(c for c in s.state.cards.values() if c.name == 'Akoum Battlesinger' and c.id != helpers[1].id)
    act(s, 'p1', type='move', card_ids=[unlinked.id], to={'player': 'p1', 'zone': 'exile'})
    to_phase(s, 'declare_attackers', turn=4)
    mana(s, W=5, C=5, G=5)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {targets[0].id}
    answer(s, [])
    settle(s)
    roundtrip(s)
