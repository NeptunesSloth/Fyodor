"""Low-level injected draw riders must finish before an attack declaration commits.

The synthetic source has legal printed mana text. Injection exercises the generic
continuation boundary; CR 605.1a forbids direct library movement in mana abilities.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.payment_rider_injection import inject_mana_draw_rider
from tests.test_rules_abundance import set_library
from tests.test_rules_designations import roundtrip
from tests.test_rules_wave5c_combat import EXTRA, attacking, build, old, put, to_attack


@pytest.fixture()
def cards(settings, monkeypatch):
    base = {c['name']: c for c in fixture_cards() + EXTRA}
    data = json.loads((Path(__file__).parent / 'fixtures/abundance_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='apc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    base['Drawing mana source'] = card('Drawing mana source', set_code='apc', number='mana',
        mana_cost='{2}', cmc=2.0, type_line='Artifact',
        oracle_text='{T}: Add {C}{C}. You gain 1 life.', colors=[], color_identity=[])
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    inject_mana_draw_rider(monkeypatch, {'Drawing mana source'})
    yield repo
    repo.close()


@pytest.mark.parametrize('replace_draw', [False, True])
def test_attack_payment_waits_for_mana_rider_draw_replacement(cards, replace_draw):
    s = build(cards, 'Abundance', 'Drawing mana source', 'Lightning Bolt', bob=['Propaganda'])
    put(s, 'Abundance')
    sphere = put(s, 'Drawing mana source')
    put(s, 'Propaganda', 'p2')
    attacker = old(s, 'p1', 'Attacker')
    to_attack(s)
    top = set_library(s, ['Lightning Bolt', 'Forest'])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p2'}], sources=[sphere.id])
    d = s.state.rules.decision
    assert d is not None and 'decline' in {o.id for o in d.options}
    assert attacking(s, attacker) is None
    assert s.state.players['p1'].life == 40
    assert s.state.cards[sphere.id].tapped
    roundtrip(s)
    option = next(o.id for o in d.options if o.id != 'decline') if replace_draw else 'decline'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[option])
    if replace_draw:
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {'land', 'nonland'}
        assert attacking(s, attacker) is None
        assert s.state.players['p1'].life == 40
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['land'])
    assert attacking(s, attacker) == 'p2'
    assert s.state.players['p1'].life == 41
    assert s.state.cards[top[1 if replace_draw else 0]].zone == 'p1:hand'
    assert s.state.rules.turn_log.drew.get('p1', 0) == (0 if replace_draw else 1)
    roundtrip(s)
