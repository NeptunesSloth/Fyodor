"""Coax's exile alternative remains available under Commander rule 903.11."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_ordered_tutor_continuations import cast


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json', 'coax_outside65_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='co65', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards):
    return gameplay.setup(cards, 'Coax from the Blind Eternities', "Ulamog's Crusher", 'All Is Dust', "Kozilek's Return")


def test_coax_whole_canonical(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve('Coax from the Blind Eternities')).level == 'FULL'


@pytest.mark.parametrize('name', ["Ulamog's Crusher", 'All Is Dust'])
def test_faceup_owned_eldrazi_creature_or_kindred_card_can_be_chosen(cards, name):
    s = setup(cards)
    target = put(s, name, 'exile')
    cast(s, 'Coax from the Blind Eternities')
    d = s.state.rules.decision
    assert d and d.player == 'p1' and d.min_choices == 0 and d.max_choices == 1
    assert target.id in [o.id for o in d.options]
    answer(s, [target.id])
    assert s.state.cards[target.id].zone == 'p1:hand'
    assert not s.state.rules.decision
    roundtrip(s)


def test_face_down_foreign_and_devoid_noneldrazi_not_offered(cards):
    s = setup(cards)
    hidden = put(s, "Ulamog's Crusher", 'exile')
    act(s, 'p1', type='move', card_ids=[hidden.id], to={'player': 'p1', 'zone': 'exile'}, face_down=True)
    foreign = put(s, "Ulamog's Crusher", 'exile', 'p2')
    other = put(s, "Kozilek's Return", 'exile')
    legal = put(s, 'All Is Dust', 'exile')
    cast(s, 'Coax from the Blind Eternities')
    d = s.state.rules.decision
    assert d and [o.id for o in d.options] == [legal.id]
    assert all(c.id not in [o.id for o in d.options] for c in [hidden, foreign, other])
    answer(s, [])
    assert s.state.cards[legal.id].zone == 'p1:exile'
    roundtrip(s)


def test_empty_exile_still_resolves_without_import_or_choice(cards):
    s = setup(cards)
    source = cast(s, 'Coax from the Blind Eternities')
    assert source.zone == 'p1:graveyard'
    assert not s.state.rules.decision
    assert not any(c.zone.endswith(':exile') for c in s.state.cards.values())
    roundtrip(s)


def test_genuine_cold_pending_public_exile_choice_uses_native_return_receipt(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    target = put(s, 'All Is Dust', 'exile')
    cast(s, 'Coax from the Blind Eternities')
    saved = tmp_path / 'coax65.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
assert d is not None and d.player=='p1'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
assert s.state.cards[sys.argv[3]].zone=='p1:hand'
assert s.state.rules.decision is None
roundtrip(s)
'''
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), target.id],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
