"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/attached_destruction82_cards.json').read_text())
NAMES = [c['name'] for c in DATA[:4]]
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
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest', 'Bonesplitter', 'Bonesplitter', 'Short Sword', 'Wind Drake',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')




@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical82(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'



def equipped(s, creature='Wind Drake', equipment='Bonesplitter'):
    host = put(s, creature, 'battlefield')
    gear = put(s, equipment, 'battlefield')
    mana(s, C=10)
    act(s, 'p1', type='activate_ability', card_id=gear.id, ability=ability(s, gear, 'Equip {'), targets=[host.id])
    settle(s)
    assert s.state.cards[gear.id].attached_to == host.id
    return host.id, gear.id


def test_eaten_destroys_host_and_all_current_equipment_simultaneously82(cards):
    s = setup(cards)
    host, gear = equipped(s)
    second = put(s, 'Short Sword', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[second.id], to=host)
    spare = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Bonesplitter' and c.id != gear)
    act(s, 'p1', type='move', card_ids=[spare.id], to={'player': 'p1', 'zone': 'battlefield'})
    cast(s, 'Eaten by Spiders', targets=[host])
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in [host, gear, second.id])
    assert s.state.cards[spare.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_soul_nova_exiles_actual_attacker_and_current_equipment82(cards):
    s = setup(cards)
    host, gear = equipped(s)
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': host, 'target': 'p2'}])
    settle(s)
    cast(s, 'Soul Nova', targets=[host])
    assert s.state.cards[host].zone == s.state.cards[gear].zone == 'p1:exile'
    roundtrip(s)


def test_unforge_uses_current_host_at_destruction82(cards):
    s = setup(cards)
    old, gear = equipped(s, creature='Grizzly Bears')
    current = put(s, 'Wind Drake', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[gear], to=current.id)
    cast(s, 'Unforge', targets=[gear])
    assert s.state.cards[gear].zone == 'p1:graveyard'
    assert s.state.cards[current.id].zone == 'p1:graveyard'
    assert s.state.cards[old].zone == 'p1:battlefield' and s.state.cards[old].damage == 0
    roundtrip(s)


def test_light_equipment_choice_is_optional_during_resolution_not_an_extra_target82(cards):
    from tests.test_rules_controller_tutors import answer

    s = setup(cards)
    host, gear = equipped(s)
    cast(s, 'Light of Judgment', targets=[host])
    d = s.state.rules.decision
    assert d and d.kind == 'choose_one' and d.player == 'p1'
    option = next(o.id for o in d.options if o.label == 'Destroy Bonesplitter')
    answer(s, [option])
    settle(s)
    assert s.state.cards[gear].zone == s.state.cards[host].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Eaten by Spiders', 'Light of Judgment'])
def test_illegal_creature_target_never_destroys_its_leftover_equipment82(cards, name):
    s = setup(cards)
    host, gear = equipped(s)
    source = put(s, name, 'hand')
    mana(s, C=10, R=5, G=5)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[host])
    cast(s, 'Disperse', targets=[host])
    assert s.state.cards[host].zone == 'p1:hand'
    assert s.state.cards[gear].zone == 'p1:battlefield' and s.state.cards[gear].attached_to is None
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('decline', [False, True])
def test_light_accepts_no_equipment_or_declines_optional_destruction82(cards, decline):
    from tests.test_rules_controller_tutors import answer

    s = setup(cards)
    if decline:
        host, gear = equipped(s)
    else:
        host = put(s, 'Wind Drake', 'battlefield').id
        gear = None
    cast(s, 'Light of Judgment', targets=[host])
    if decline:
        d = s.state.rules.decision
        assert d and d.kind == 'choose_one'
        answer(s, [next(o.id for o in d.options if o.label == 'Destroy no Equipment')])
        settle(s)
        assert s.state.cards[gear].zone == 'p1:battlefield'
    assert s.state.cards[host].zone == 'p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


def test_unforge_indestructible_equipment_still_uses_bound_host_for_damage82(cards):
    s = setup(cards)
    host, gear = equipped(s, equipment='Darksteel Plate')
    cast(s, 'Unforge', targets=[gear])
    assert s.state.cards[gear].zone == s.state.cards[host].zone == 'p1:battlefield'
    assert s.state.cards[host].damage == 2
    roundtrip(s)


@pytest.mark.parametrize('mode', ['unforge', 'light_choice'])
def test_genuine_fresh_process_restores_current_attached_objects82(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    s = setup(cards)
    host, gear = equipped(s)
    if mode == 'light_choice':
        cast(s, 'Light of Judgment', targets=[host])
        assert s.state.rules.decision and s.state.rules.decision.kind == 'choose_one'
    else:
        source = put(s, 'Unforge', 'hand')
        mana(s, C=2, R=1)
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[gear])
    saved = tmp_path / 'attachment82.json'
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
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
host,gear,mode=sys.argv[3:]
if mode=='light_choice':
 d=s.state.rules.decision
 assert d and d.player=='p1'
 answer(s,[next(o.id for o in d.options if o.label=='Destroy Bonesplitter')])
settle(s)
assert s.state.cards[host].zone==s.state.cards[gear].zone=='p1:graveyard'
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), host, gear, mode],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
