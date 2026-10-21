"""Resume saved payment replacement bodies in a genuinely new Python process."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.payment_rider_injection import inject_mana_draw_rider
from tests.test_rules_abundance import set_library
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings, monkeypatch):
    inject_mana_draw_rider(monkeypatch, {'Payment Test Spring'})
    base = {c['name']: c for c in fixture_cards()}
    for filename in ('abundance_cards.json', 'special_payment_cards.json'):
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='cold', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    base['Payment Test Spring'] = card('Payment Test Spring', set_code='cold', number='spring', type_line='Artifact',
                                      oracle_text='{T}: Add one mana of any color.')
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


COLD_RESUME = r'''
import json
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState

state_path, database, target, kind = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
# No test helper modules or injected rules are imported in this new process.
# The frozen ability/continuation metadata in the save owns pending work.
for _ in range(12):
    d = s.state.rules.decision
    if d is None:
        break
    ids = {o.id for o in d.options}
    if 'decline' in ids:
        chosen = [next(o.id for o in d.options if o.id != 'decline')]
    elif (d.resume or {}).get('step') == 'choose_land_nonland':
        chosen = ['land']
    elif d.kind == 'order':
        chosen = [o.id for o in d.options]
    else:
        raise AssertionError('Unexpected decision: ' + d.prompt)
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': chosen})
expected = 'p1:exile' if kind == 'suspend' else 'p1:graveyard'
assert s.state.cards[target].zone == expected
if kind == 'suspend':
    assert s.state.cards[target].counters.get('time') == 1
    assert s.state.rules.suspended.count(target) == 1
elif kind == 'cycling':
    assert len(s.state.rules.stack) == 1
else:
    assert len(s.state.zones['p1:hand']) == 2
assert not s.state.players['p1'].mana_units
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
loaded = GameState.model_validate_json(s.state.model_dump_json())
assert loaded.model_dump(mode='json') == s.state.model_dump(mode='json')
print(json.dumps({'zone': s.state.cards[target].zone, 'kind': kind}))
repo.close()
'''


@pytest.mark.parametrize('kind,name', [('suspend', 'Rift Bolt'), ('cycling', 'Curator of Mysteries'), ('effect', 'Nihil Spellbomb')])
def test_saved_payment_stage_resumes_after_cold_process_import(cards, tmp_path, kind, name):
    s = table(cards, ['Abundance', name, 'Payment Test Spring', 'Forest', 'Island', 'Lightning Bolt'])
    put(s, 'Abundance', 'battlefield')
    put(s, 'Payment Test Spring', 'battlefield')
    target = put(s, name, 'battlefield' if kind == 'effect' else 'hand')
    set_library(s, ['Forest', 'Island', 'Lightning Bolt'])
    if kind == 'effect':
        act(s, 'p1', type='activate_ability', card_id=target.id, ability=0, targets=['p2'])
        d = until_asked(s)
        assert d.resume['step'] == 'pay_or_sacrifice'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    else:
        ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id])
        index = next(a.index for a in ch.abilities if kind in a.keywords)
        act(s, 'p1', type='activate_ability', card_id=target.id, ability=index)
    assert 'decline' in {o.id for o in s.state.rules.decision.options}
    roundtrip(s)
    saved = tmp_path / 'pending-payment.json'
    saved.write_text(s.state.model_dump_json())
    result = subprocess.run([sys.executable, '-c', COLD_RESUME, str(saved), str(cards.db_path), target.id, kind],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['kind'] == kind
