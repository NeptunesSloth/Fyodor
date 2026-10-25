"""Original revealed objects, category matching and native queued hidden-zone choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_library_packets101 import advance, cast, cold, top
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/reveal_categories104_cards.json').read_text())
NAMES = [c['name'] for c in DATA[:5]]


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        extra = {k: v for k, v in c.items() if k not in {'name', 'set_code', 'number', 'id'}}
        base[c['name']] = card(c['name'], set_code='r104', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, phase='main1', commander='Krenko, Mob Boss'):
    ds = [deck(cards, commander, [(2, c['name']) for c in DATA] + [(40, 'Forest'), (10, 'Island')]),
          deck(cards, "Atraxa, Praetors' Voice", [(30, 'Island')])]
    s = GameSession(enable(new_game([PlayerSetup('Alice', cards=ds[0]), PlayerSetup('Bob', cards=ds[1])], shuffle=False)), cards=cards)
    for pid in ['p1', 'p2']:
        act(s, pid, type='set_stops', own=['upkeep', 'main1', 'end'], others=['upkeep', 'main1', 'end'], smart_pass=False)
    to_phase(s, phase, 1)
    act(s, 'p1', type='add_mana', player='p1', mana={c: 50 for c in ['C', 'W', 'U', 'B', 'R', 'G']})
    return s


def pick(s, ids):
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'pick_looked'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


@pytest.mark.parametrize('name', NAMES)
def test_canonical104(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def niv(s):
    ids = top(s, ['Coiling Oracle', 'Maraleaf Pixie', 'Baleful Strix', 'Knight of Autumn', 'Birds of Paradise',
                  'Ornithopter', 'Forest', 'Island', 'Grizzly Bears', 'Sol Ring'])
    cast(s, 'Niv-Mizzet Reborn')
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    return ids


def test_niv_exact_pairs_required_and_native_duplicate_category_rejection104(cards):
    s = setup(cards)
    ids = niv(s)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == d.max_choices == 3
    assert set(o.id for o in d.options) == set(ids[:4])
    with pytest.raises(ActionError, match='one card of each kind'):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=ids[:3])
    pick(s, [ids[0], ids[2], ids[3]])
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:hand' for c in [ids[0], ids[2], ids[3]])
    assert not any(c.name == 'Birds of Paradise' and c.zone == 'p1:hand' for c in s.state.cards.values())
    from tests.test_rules_effects import replay_matches
    replay_matches(s)


def test_niv_cold_category_selection104(cards, tmp_path):
    s = setup(cards)
    ids = niv(s)
    cold(s, tmp_path, {'ids': [ids[0], ids[2], ids[3]]}, '''
d=s.state.rules.decision
assert d.resume['step'] == 'pick_looked'
act(s,d.player,type='choose',decision_id=d.id,option_ids=extra['ids'])
advance(s)
assert all(s.state.cards[c].zone == 'p1:hand' for c in extra['ids'])
''')


def portent(s, names=None):
    ids = top(s, names or ['Sol Ring', 'Grizzly Bears', 'Doubling Season', 'Cultivate'])
    cast(s, 'Portent of Calamity', x_value=len(ids))
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    return ids


def test_portent_four_actual_exiles_one_native_free_cast_rest_hand104(cards):
    s = setup(cards)
    ids = portent(s)
    pick(s, ids)
    advance(s, stop=lambda d: d.resume.get('step') == 'free_cast_pick')
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'free_cast_pick'
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[1]])
    advance(s)
    assert s.state.cards[ids[1]].zone == 'p1:battlefield'
    assert all(s.state.cards[c].zone == 'p1:hand' for c in [ids[0], ids[2], ids[3]])
    assert len([c for c in s.state.rules.turn_log.casts if c.player == 'p1']) == 2


def test_portent_three_categories_no_free_cast_and_rest_graveyard104(cards):
    s = setup(cards)
    ids = portent(s, ['Sol Ring', 'Arcane Signet', 'Grizzly Bears', 'Cultivate'])
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 3
    pick(s, [ids[0], ids[2], ids[3]])
    advance(s)
    assert s.state.cards[ids[1]].zone == 'p1:graveyard'
    assert all(s.state.cards[c].zone == 'p1:hand' for c in [ids[0], ids[2], ids[3]])
    assert len(s.state.rules.turn_log.casts) == 1


def test_portent_cold_at_native_free_cast104(cards, tmp_path):
    s = setup(cards)
    ids = portent(s)
    pick(s, ids)
    advance(s, stop=lambda d: d.resume.get('step') == 'free_cast_pick')
    cold(s, tmp_path, {'ids': ids}, '''
d=s.state.rules.decision
assert d.resume['step'] == 'free_cast_pick'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[extra['ids'][1]])
advance(s)
assert s.state.cards[extra['ids'][1]].zone == 'p1:battlefield'
assert all(s.state.cards[c].zone == 'p1:hand' for c in [extra['ids'][0],extra['ids'][2],extra['ids'][3]])
''')


def selective(s):
    ids = top(s, ['Ornithopter', 'Vampire Nighthawk', 'Silver Knight', 'Baleful Strix', 'Inkwell Leviathan', 'Grizzly Bears', 'Forest'])
    cast(s, 'Selective Adaptation')
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    return ids


def test_selective_maximum_distinct_keyword_assignment_and_native_split104(cards):
    s = setup(cards)
    ids = selective(s)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == d.max_choices == 5
    pick(s, ids[:5])
    advance(s, stop=lambda d: d.resume.get('step') == 'return_choice')
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'return_choice'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[1]])
    advance(s)
    assert s.state.cards[ids[1]].zone == 'p1:battlefield'
    assert all(s.state.cards[c].zone == 'p1:hand' for c in [ids[0], ids[2], ids[3], ids[4]])
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in ids[5:])


def test_selective_cold_before_native_battlefield_selection104(cards, tmp_path):
    s = setup(cards)
    ids = selective(s)
    pick(s, ids[:5])
    advance(s, stop=lambda d: d.resume.get('step') == 'return_choice')
    cold(s, tmp_path, {'ids': ids}, '''
d=s.state.rules.decision
assert d.resume['step'] == 'return_choice'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[extra['ids'][1]])
advance(s)
assert s.state.cards[extra['ids'][1]].zone == 'p1:battlefield'
assert all(s.state.cards[c].zone == 'p1:hand' for c in [extra['ids'][0],extra['ids'][2],extra['ids'][3],extra['ids'][4]])
''')


def test_sanar_frozen_five_colors_nonland_stop_and_paid_cast104(cards):
    s = setup(cards, phase='upkeep')
    put(s, 'Transguild Courier', 'battlefield')
    put(s, 'Sanar, Innovative First-Year', 'battlefield')
    ids = top(s, ['Forest', 'Silver Knight', 'Counterspell', 'Vampire Nighthawk', 'Lightning Bolt', 'Grizzly Bears', 'Hill Giant'])
    to_phase(s, 'main1', 1)
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 5
    assert set(o.id for o in d.options) == set(ids[1:6])
    pick(s, ids[1:6])
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids[1:6])
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=ids[5], sources=[])
    advance(s)
    assert s.state.cards[ids[5]].zone == 'p1:battlefield'
    assert len(s.state.rules.turn_log.casts) == 1


def test_hurkyl_actual_noncreature_cast_history_categories104(cards):
    s = setup(cards)
    put(s, 'Hurkyl, Master Wizard', 'battlefield')
    cast(s, 'Sol Ring')
    advance(s)
    cast(s, 'Lightning Bolt', targets=['p2'])
    advance(s)
    cast(s, 'Cultivate')
    advance(s)
    cast(s, 'Ornithopter')
    advance(s)
    ids = top(s, ['Sol Ring', 'Lightning Bolt', 'Cultivate', 'Grizzly Bears', 'Doubling Season'])
    to_phase(s, 'end', 1)
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 3 and set(o.id for o in d.options) == set(ids[:3])
    pick(s, ids[:3])
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:hand' for c in ids[:3])


@pytest.mark.parametrize('command', [True, False])
def test_niv_original_tucked_commander_native_hand_choice104(cards, tmp_path, command):
    s = setup(cards, commander='Kinnan, Bonder Prodigy')
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.zone == 'p1:command')
    rest = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=rest, to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    cast(s, 'Niv-Mizzet Reborn')
    pick(s, [commander.id])
    advance(s, stop=lambda d: 'commander' in d.resume.get('step', ''))
    d = s.state.rules.decision
    assert d is not None and 'commander' in d.resume.get('step', '')
    cold(s, tmp_path, {'card': commander.id, 'command': command}, '''
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes' if extra['command'] else 'no'])
advance(s)
assert s.state.cards[extra['card']].zone == ('p1:command' if extra['command'] else 'p1:hand')
''')


def test_portent_zero_x_reveals_nothing104(cards):
    s = setup(cards)
    ids = top(s, ['Sol Ring', 'Grizzly Bears'])
    cast(s, 'Portent of Calamity', x_value=0)
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:library' for c in ids)
    assert not s.state.zones.get('p1:exile') and not s.state.zones.get('p1:graveyard', [])[:-1]
    assert len(s.state.rules.turn_log.casts) == 1


def test_portent_rest_replacement_exile_does_not_count_toward_four104(cards):
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield')
    ids = portent(s, ['Sol Ring', 'Arcane Signet', 'Grizzly Bears', 'Cultivate'])
    pick(s, [ids[0], ids[2], ids[3]])
    advance(s)
    assert s.state.cards[ids[1]].zone == 'p1:exile'
    assert all(s.state.cards[c].zone == 'p1:hand' for c in [ids[0], ids[2], ids[3]])
    assert len(s.state.rules.turn_log.casts) == 1


def test_selective_no_matching_keyword_cards104(cards):
    s = setup(cards)
    ids = top(s, ['Grizzly Bears', 'Hill Giant', 'Forest', 'Island', 'Sol Ring', 'Arcane Signet', 'Cultivate'])
    cast(s, 'Selective Adaptation')
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in ids)


def test_sanar_source_left_zero_current_colors_still_shuffles104(cards):
    s = setup(cards, phase='upkeep')
    source = put(s, 'Sanar, Innovative First-Year', 'battlefield')
    top(s, ['Silver Knight', 'Counterspell', 'Grizzly Bears'])
    to_phase(s, 'main1', 1)
    assert s.state.zones.get('stack')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    old = set(s.state.zones['p1:library'])
    advance(s)
    assert not s.state.zones.get('p1:exile') and not s.state.rules.permissions
    assert len(s.state.zones['p1:library']) == len(old)
    assert not old.intersection(s.state.zones['p1:library'])


def test_hurkyl_creature_artifact_cast_is_not_noncreature_history104(cards):
    s = setup(cards)
    put(s, 'Hurkyl, Master Wizard', 'battlefield')
    cast(s, 'Ornithopter')
    advance(s)
    ids = top(s, ['Sol Ring', 'Lightning Bolt', 'Cultivate'])
    to_phase(s, 'end', 1)
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:library' for c in ids)


def test_selective_hexproof_from_is_hexproof_702_11d104(cards):
    s = setup(cards)
    ids = top(s, ['Knight of Grace', 'Silver Knight', 'Ornithopter', 'Grizzly Bears', 'Forest', 'Sol Ring', 'Cultivate'])
    cast(s, 'Selective Adaptation')
    advance(s, stop=lambda d: d.resume.get('step') == 'pick_looked')
    d = s.state.rules.decision
    assert d is not None and d.min_choices == d.max_choices == 3
    pick(s, ids[:3])
    advance(s, stop=lambda d: d.resume.get('step') == 'return_choice')
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[2]])
    advance(s)
    assert s.state.cards[ids[2]].zone == 'p1:battlefield'
    assert all(s.state.cards[c].zone == 'p1:hand' for c in ids[:2])
