"""Blocking declarations survive a new process during either payment stage."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests import test_rules_archangel_tithes as archangel
from tests.game_helpers import act
from tests.test_rules_archangel_tithes import declare, setup
from tests.test_rules_designations import put, roundtrip


@pytest.fixture()
def cards(settings):
    yield from archangel.cards.__wrapped__(settings)


RESUME = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path, database, blocker, attacker, stage = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
d = s.state.rules.decision
assert d is not None
s.perform(d.player, {'type': 'choose', 'decision_id': d.id,
                     'option_ids': ['pay' if stage == 'manual' else 'decline']})
assert s.state.cards[blocker].blocking == attacker
assert not s.state.players['p2'].mana and not s.state.players['p2'].mana_units
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''


@pytest.mark.parametrize('stage', ['manual', 'rider'])
def test_block_tax_payment_resumes_in_fresh_process(cards, tmp_path, monkeypatch, stage):
    if stage == 'rider':
        from tests.payment_rider_injection import inject_mana_draw_rider

        inject_mana_draw_rider(monkeypatch, {'Island'})
    s, source, _, blockers = setup(cards, defenders=('Wall of Air', 'Abundance'))
    land = put(s, 'Island', 'battlefield', 'p2')
    if stage == 'manual':
        act(s, 'p2', type='set_prefs', payment='self')
        declare(s, [(blockers[0], source)])
        assert s.state.rules.decision.resume['step'] == 'pay_mana'
        act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    else:
        declare(s, [(blockers[0], source)], sources=[land.id])
        assert 'decline' in {o.id for o in s.state.rules.decision.options}
    assert s.state.cards[blockers[0].id].blocking is None
    roundtrip(s)
    saved = tmp_path / 'pending-block-tax.json'
    saved.write_text(s.state.model_dump_json())
    result = subprocess.run([sys.executable, '-c', RESUME, str(saved), str(cards.db_path),
                             blockers[0].id, source.id, stage], capture_output=True,
                            text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
