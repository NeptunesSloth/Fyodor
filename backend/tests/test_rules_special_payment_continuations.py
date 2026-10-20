"""Special actions and hand activations resume exactly once after mana-source draw replacements."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.payment_rider_injection import inject_mana_draw_rider
from tests.test_rules_abundance import set_library
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave38d_companion import build38


@pytest.fixture()
def injected_draw_rider(monkeypatch):
    inject_mana_draw_rider(monkeypatch, {'Payment Test Spring'})


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/special_payment_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    base['Payment Test Spring'] = card('Payment Test Spring', set_code='spp', number='spring', type_line='Artifact',
                                      oracle_text='{T}: Add one mana of any color.')
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Abundance', 'Dimir Machinations', 'Curator of Mysteries', 'Rift Bolt', 'Slickshot Show-Off', 'Ravenform',
         'Scornful Egotist', 'Forest', 'Island', 'Payment Test Spring']
CASES = [('transmute', 'Dimir Machinations', {'C': 1, 'B': 1}), ('cycling', 'Curator of Mysteries', {}),
         ('suspend', 'Rift Bolt', {}), ('plot', 'Slickshot Show-Off', {'C': 1}),
         ('foretell', 'Ravenform', {'C': 1}), ('face_up', 'Scornful Egotist', {}),
         ('companion', 'Lutri, the Spellchaser', {'C': 2})]


@pytest.mark.parametrize('paused', [False, True])
@pytest.mark.parametrize('kind,name,pool', CASES)
def test_special_action_terminal_waits_for_mana_source_draw(cards, paused, kind, name, pool, injected_draw_rider):
    if kind == 'companion':
        s = build38(cards, companion=name, commander='Krenko, Mob Boss', spells=[*((1, n) for n in NAMES), (15, 'Forest')])
        for pid in ['p1', 'p2']:
            act(s, pid, type='set_prefs', response='on')
        target = next(c for c in s.state.cards.values() if c.name == name and c.owner == 'p1')
    else:
        s = table(cards, NAMES)
        target = put(s, name, 'hand')
    if paused:
        put(s, 'Abundance', 'battlefield')
    spring = put(s, 'Payment Test Spring', 'battlefield')
    top = set_library(s, ['Forest', 'Island'])
    if kind == 'face_up':
        act(s, 'p1', type='move', card_ids=[target.id], to={'zone': 'battlefield', 'player': 'p1'},
            face_down=True, face_down_kind='morph')
    if pool:
        mana(s, **pool)
    if kind == 'face_up':
        act(s, 'p1', type='turn_face_up', card_id=target.id, method='morph')
    else:
        ch = Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[target.id])
        ability = next(ab.index for ab in ch.abilities if ('cycling' if kind == 'cycling' else kind) in ab.keywords)
        act(s, 'p1', type='activate_ability', card_id=target.id, ability=ability)
    if paused:
        d = s.state.rules.decision
        assert d is not None and 'decline' in {o.id for o in d.options}
        assert s.state.cards[target.id].zone == ('p1:companion' if kind == 'companion' else 'p1:battlefield' if kind == 'face_up' else 'p1:hand')
        if kind == 'face_up':
            assert s.state.cards[target.id].face_down
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id != 'decline')])
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['land'])
    assert s.state.cards[spring.id].tapped and mana_pool(s) == {}
    expected = 'p1:graveyard' if kind in ('transmute', 'cycling') else 'p1:foretell' if kind == 'foretell' else 'p1:hand' if kind == 'companion' else 'p1:battlefield' if kind == 'face_up' else 'p1:exile'
    assert s.state.cards[target.id].zone == expected
    assert s.state.cards[top[0]].zone == 'p1:hand'
    if kind == 'suspend':
        assert s.state.cards[target.id].counters.get('time') == 1
        assert s.state.rules.suspended.count(target.id) == 1
    if kind == 'plot':
        assert len([p for p in s.state.rules.permissions if p.card == target.id]) == 1
    if kind == 'face_up':
        assert not s.state.cards[target.id].face_down
    if kind == 'cycling' and paused:
        d = until_asked(s)
        assert 'decline' in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    roundtrip(s)
