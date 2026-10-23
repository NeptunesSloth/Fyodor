"""Fade Away fixes all original obligations and sacrifices selected permanents together."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.mana_units import visible_pool
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/fade85_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def cast(s, name):
    c = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=[], sources=[])
    settle(s)
    return c



def test_whole_fade(cards):
    assert coverage.of_card_data(cards.resolve('Fade Away')).level == 'FULL'


def test_two_creatures_allow_two_noncreature_sacrifices_and_no_early_commit(cards):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    rock = put(s, 'Sol Ring', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Fade Away')
    choose(s, ['decline'])
    choose(s, ['decline'])
    d = s.state.rules.decision
    assert d.player == 'p1' and d.min_choices == d.max_choices == 2
    assert {o.id for o in d.options} == {a.id, b.id, land.id, rock.id}
    choose(s, [land.id, rock.id])
    assert s.state.cards[land.id].zone == s.state.cards[rock.id].zone == 'p1:battlefield'
    assert s.state.rules.decision.player == 'p2'
    choose(s, [other.id])
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == 'p1:battlefield'
    assert s.state.cards[land.id].zone == s.state.cards[rock.id].zone == 'p1:graveyard'
    moved = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in {land.id, rock.id, other.id}]
    assert len(moved) == 3 and len({e.batch for e in moved}) == 1
    roundtrip(s)


def test_mixed_payment_and_sacrifice_consumes_actual_one_per_paid_obligation(cards):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    cast(s, 'Fade Away')
    choose(s, ['pay'])
    assert visible_pool(s.state, 'p1') == {}
    d = s.state.rules.decision
    assert d.resume['step'] == 'fade_sacrifice85' and d.min_choices == d.max_choices == 1
    choose(s, [a.id])
    assert s.state.cards[a.id].zone == 'p1:graveyard' and s.state.cards[b.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_creature_sacrificed_to_real_mana_ability_still_leaves_initial_two_payment_obligations(cards):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Ornithopter', 'battlefield')
    altar = put(s, "Ashnod's Altar", 'battlefield')
    act(s, 'p1', type='set_prefs', payment='self')
    cast(s, 'Fade Away')
    assert s.state.rules.decision.resume['step'] == 'pay_or_sacrifice'
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0,
        sources=[], cost_choices=[{'component': 0, 'cards': [b.id]}])
    assert s.state.cards[b.id].zone == 'p1:graveyard'
    choose(s, ['pay'])
    assert visible_pool(s.state, 'p1') == {'C': 1}
    assert s.state.rules.decision is not None
    choose(s, ['pay'])
    assert visible_pool(s.state, 'p1') == {}
    assert s.state.rules.decision is None and s.state.cards[a.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_sigarda_prevents_opponent_forced_sacrifices_without_erasing_other_players_obligations(cards):
    s = game(cards)
    sigarda = put(s, 'Sigarda, Host of Herons', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Fade Away')
    choose(s, [bear.id])
    assert s.state.rules.decision is None
    assert s.state.cards[sigarda.id].zone == 'p2:battlefield'
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_true_cold_fade_preserves_earlier_noncreature_sacrifice_and_later_payment(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s = game(cards)
    earlier = put(s, 'Sol Ring', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    later = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
    cast(s, 'Fade Away')
    choose(s, ['decline'])
    choose(s, [earlier.id])
    assert s.state.rules.decision.player == 'p2'
    assert s.state.cards[earlier.id].zone == 'p1:battlefield'
    saved = tmp_path / 'fade.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
earlier,later=sys.argv[3:]
d=s.state.rules.decision
assert d and d.player=='p2'
assert s.state.cards[earlier].zone=='p1:battlefield'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
settle(s)
assert s.state.cards[earlier].zone=='p1:graveyard'
assert s.state.cards[later].zone=='p2:battlefield'
assert not s.state.rules.decision and not s.state.players['p2'].mana
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), earlier.id, later.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
