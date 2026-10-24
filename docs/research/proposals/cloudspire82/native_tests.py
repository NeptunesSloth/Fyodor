"""Cloudspire uses native entry snapshots and Pilot crew/saddle power."""
from pathlib import Path

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_crew_saddle_readers81 import cards as cards
from tests.test_rules_crew_saddle_readers81 import crew81, setup81
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars


def test_cloudspire_whole82(cards):
    assert coverage.of_card_data(cards.resolve('Cloudspire Coordinator')).level == 'FULL'


def test_native_cloudspire_counts_entered_mounts_and_vehicles_only(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, source, bear = setup81(cards, 'Cloudspire Coordinator')
    put(s, 'Subterranean Schooner', 'battlefield')
    to_phase(s, 'main1', turn=7)
    vehicle = put(s, 'Ghost Ark', 'battlefield')
    mount = put(s, "Archmage's Newt", 'battlefield')
    put(s, 'Memnite', 'battlefield')
    # The old Vehicle and non-Mount/non-Vehicle entrants are excluded.
    index = next(a.index for a in chars(s, source).abilities if a.text.startswith('{T}: Create'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    pilots = [c for c in s.state.cards.values() if c.name == 'Pilot' and c.zone == 'p1:battlefield']
    assert len(pilots) == 2
    assert all(chars(s, c).pt == (1, 1) for c in pilots)
    assert all('saddles Mounts and crews Vehicles' in chars(s, c).abilities[0].text for c in pilots)
    crew81(s, vehicle, pilots[0])
    assert 'Creature' in chars(s, vehicle).types
    crew81(s, mount, pilots[1], saddle=True)
    assert any(f.kind == 'saddled' and f.object_id == s.state.rules.object_id(mount.id) for f in s.state.rules.turn_log.facts)


def test_cloudspire_counts_departed_entries_and_repeated_new_objects(cards):
    from tests.test_rules_bandmate_references import mana
    s, source, bear = setup81(cards, 'Cloudspire Coordinator')
    vehicle = put(s, 'Ghost Ark', 'battlefield')
    mount = put(s, "Archmage's Newt", 'battlefield')
    destroy = put(s, 'Disenchant', 'hand')
    blink = put(s, 'Cloudshift', 'hand')
    mana(s, W=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=destroy.id, targets=[vehicle.id])
    settle(s)
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[mount.id])
    settle(s)
    index = next(a.index for a in chars(s, source).abilities if a.text.startswith('{T}: Create'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == 'Pilot' and c.zone == 'p1:battlefield']) == 3


def test_cloudspire_genuine_cold_pending_activation(cards, tmp_path):
    import subprocess
    import sys

    import app
    s, source, bear = setup81(cards, 'Cloudspire Coordinator')
    put(s, 'Ghost Ark', 'battlefield')
    put(s, "Archmage's Newt", 'battlefield')
    index = next(a.index for a in chars(s, source).abilities if a.text.startswith('{T}: Create'))
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.zones.get('stack')
    saved = tmp_path / 'cloudspire82.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
pilots=[c for c in s.state.cards.values() if c.name=='Pilot' and c.zone=='p1:battlefield']
assert len(pilots)==2
assert all(chars(s,c).pt==(1,1) for c in pilots)
assert all('saddles Mounts and crews Vehicles' in chars(s,c).abilities[0].text for c in pilots)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
        capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


def test_cloudspire_actual_printed_cast(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_crew_saddle_readers81 import DATA
    from tests.test_rules_declaration_requirements33 import start
    from tests.test_rules_designations import pick
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [c['name'] for c in DATA], ['Forest'], [])
    source = put(s, 'Cloudspire Coordinator', 'hand')
    start(s)
    mana(s, R=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.decision is not None
    assert 'scry' in s.state.rules.decision.prompt.lower()
    pick(s, [])
    settle(s)
    if s.state.rules.decision is not None:
        pick(s, [o.id for o in s.state.rules.decision.options])
        settle(s)
    assert s.state.rules.decision is None
