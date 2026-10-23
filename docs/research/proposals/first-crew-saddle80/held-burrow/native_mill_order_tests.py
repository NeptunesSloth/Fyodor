"""A native Burrowfiend continuation must wait for every mill replacement choice."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import pick, put
from tests.test_rules_first_crew_saddle80 import DATA, crew80
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars

SUPPORTS = json.loads((Path(__file__).parent / 'fixtures/burrow_mill_receipt80_supports.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate([*DATA, *SUPPORTS]):
        base[c['name']] = card(c['name'], set_code='burrow80', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('replacement', ['Rest in Peace', 'Darksteel Colossus'])
def test_burrow_waits_for_actual_mill_replacement_before_downstream_pump(cards, replacement):
    names = [c['name'] for c in [*DATA, *SUPPORTS]] + ['Grizzly Bears', 'Forest']
    s = table(cards, names, [], [])
    source = put(s, 'Stubborn Burrowfiend', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    rip = put(s, 'Rest in Peace', 'hand')
    mana(s, W=2)
    act(s, 'p1', type='cast_spell', card_id=rip.id)
    settle(s)
    top = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Darksteel Colossus')
    forest = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest')
    for c in [forest, top]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    oid = s.state.rules.object_id(source.id)
    before = chars(s, source).pt
    crew80(s, source, bear, saddle=True)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_one'
    assert any('Rest in Peace' in o.label for o in d.options)
    assert any('Darksteel Colossus' in o.label for o in d.options)
    # Even a +0/+0 marker would be a prematurely committed downstream effect.
    assert not [e for e in s.state.rules.effects if e.layer == '7c' and e.source == oid and oid in e.affected]
    option = next(o.id for o in d.options if replacement in o.label)
    pick(s, [option])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.zones.get('p1:graveyard', []) == []
    assert chars(s, source).pt == before
    assert len([e for e in s.state.rules.effects if e.layer == '7c' and e.source == oid and oid in e.affected]) == 1


@pytest.mark.parametrize('replacement', ['Rest in Peace', 'Darksteel Colossus'])
def test_genuine_cold_pending_burrow_replacement_then_pump(cards, tmp_path, replacement):
    import subprocess
    import sys

    import app
    names = [c['name'] for c in [*DATA, *SUPPORTS]] + ['Grizzly Bears', 'Forest']
    s = table(cards, names, [], [])
    source = put(s, 'Stubborn Burrowfiend', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    rip = put(s, 'Rest in Peace', 'hand')
    mana(s, W=2)
    act(s, 'p1', type='cast_spell', card_id=rip.id)
    settle(s)
    top = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Darksteel Colossus')
    forest = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest')
    for c in [forest, top]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    oid = s.state.rules.object_id(source.id)
    crew80(s, source, bear, saddle=True)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_one'
    assert not [e for e in s.state.rules.effects if e.layer == '7c' and e.source == oid and oid in e.affected]
    saved = tmp_path / 'burrow-mill-pending.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,oid,replacement=sys.argv[3:]
d=s.state.rules.decision
assert d is not None and d.kind=='choose_one'
assert not [e for e in s.state.rules.effects if e.layer=='7c' and e.source==oid and oid in e.affected]
pick(s,[next(o.id for o in d.options if replacement in o.label)])
settle(s)
assert s.state.rules.decision is None
assert s.state.zones.get('p1:graveyard',[])==[]
assert chars(s,s.state.cards[source]).pt==(2,2)
assert len([e for e in s.state.rules.effects if e.layer=='7c' and e.source==oid and oid in e.affected])==1
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, oid, replacement],
        capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr
