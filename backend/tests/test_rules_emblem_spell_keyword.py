"""Ral's command-zone emblem grants each eligible spell its own storm ability."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAME = 'Ral, Crackling Wit'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/emblem_spell_keyword_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='esk', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def finish(s):
    for _ in range(80):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        options = {o.id for o in d.options}
        answer = 'keep' if 'keep' in options else 'same'
        assert answer in options, (d.prompt, d.options)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
    pytest.fail('copy resolution did not finish')


def setup(cards):
    s = table(cards, [NAME, 'Lightning Bolt', 'Grapeshot', 'Sol Ring', 'Grizzly Bears'], ['Lightning Bolt'])
    source = put(s, NAME, 'battlefield')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=10)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before + 3
    assert len([c for c in s.state.cards.values() if c.zone == 'p1:command' and c.token and c.token.type_line == 'Emblem']) == 1
    roundtrip(s)
    return s


def cast(s, name, mana, targets=(), pid='p1'):
    source = put(s, name, 'hand', pid=pid)
    act(s, pid, type='add_mana', player=pid, mana=mana)
    act(s, pid, type='cast_spell', card_id=source.id, sources=[], targets=list(targets))
    finish(s)
    return source


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_emblem_survives_source_and_grants_storm_only_to_instant_and_sorcery(cards):
    s = setup(cards)
    cast(s, 'Sol Ring', {'C': 1})
    assert len([c for c in s.state.cards.values() if c.name == 'Sol Ring' and c.zone.endswith(':battlefield')]) == 1
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 34
    roundtrip(s)


def test_printed_and_granted_storm_are_independent_instances(cards):
    s = setup(cards)
    cast(s, 'Sol Ring', {'C': 1})
    cast(s, 'Grapeshot', {'C': 1, 'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_creature_is_counted_but_does_not_receive_storm(cards):
    s = setup(cards)
    cast(s, 'Sol Ring', {'C': 1})
    cast(s, 'Grizzly Bears', {'C': 1, 'G': 1})
    assert len([c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.zone.endswith(':battlefield')]) == 1
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 31
    roundtrip(s)


def test_second_emblem_adds_a_separate_storm_ability(cards):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=10)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    settle(s)
    cast(s, 'Sol Ring', {'C': 1})
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 31
    roundtrip(s)


def test_opponents_spell_does_not_receive_storm(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards)
    cast(s, 'Sol Ring', {'C': 1})
    wait_priority(s, 'p2')
    cast(s, 'Lightning Bolt', {'R': 1}, ['p1'], pid='p2')
    assert s.state.players['p1'].life == 37
    roundtrip(s)


def test_saved_command_emblem_grants_storm_in_a_fresh_process(cards, tmp_path):
    s = setup(cards)
    saved = tmp_path / 'ral-emblem.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_emblem_spell_keyword import cast
state_path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
cast(s, 'Sol Ring', {'C': 1})
cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
assert s.state.players['p2'].life == 34
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
