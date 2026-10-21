"""Resolution payments wait for mana-source replacements, then resume exactly once."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.payment_rider_injection import inject_mana_draw_rider
from tests.test_rules_abundance import set_library
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def injected_draw_rider(monkeypatch):
    inject_mana_draw_rider(monkeypatch, {'Payment Test Spring'})


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    raw = json.loads((Path(__file__).parent / 'fixtures/abundance_cards.json').read_text())
    for i, c in enumerate(raw):
        base[c['name']] = card(c['name'], set_code='opc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    # Print a legal mana ability; the explicit test fixture injects its structured
    # draw rider below classification (CR 605.1a excludes native library-moving abilities).
    base['Payment Test Spring'] = card('Payment Test Spring', set_code='opc', number='spring', type_line='Artifact',
                                      oracle_text='{T}: Add {B}.')
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('paused', [False, True])
def test_spellbomb_payment_finishes_only_after_mana_sources_replacement_and_then_draws_once(cards, paused, injected_draw_rider):
    s = table(cards, ['Abundance', 'Nihil Spellbomb', 'Payment Test Spring', 'Forest', 'Island', 'Lightning Bolt'])
    spring = put(s, 'Payment Test Spring', 'battlefield')
    bomb = put(s, 'Nihil Spellbomb', 'battlefield')
    if paused:
        put(s, 'Abundance', 'battlefield')
    top = set_library(s, ['Forest', 'Island', 'Lightning Bolt'])
    before = len(s.state.zones['p1:hand'])
    drawn = s.state.rules.turn_log.drew.get('p1', 0)
    act(s, 'p1', type='activate_ability', card_id=bomb.id, ability=0, targets=['p2'])
    d = until_asked(s)
    assert d.resume['step'] == 'pay_or_sacrifice' and d.resume['opt']['cost'] == '{B}'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    if paused:
        for i in range(2):
            d = s.state.rules.decision
            assert d is not None and 'decline' in {o.id for o in d.options}
            # The original trigger's draw must wait for the mana source's draw replacement.
            assert len(s.state.zones['p1:hand']) == before + i
            assert s.state.cards[spring.id].zone == 'p1:battlefield' and s.state.cards[spring.id].tapped
            roundtrip(s)
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id != 'decline')])
            d = s.state.rules.decision
            assert d.resume['step'] == 'choose_land_nonland'
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=['land'])
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:hand' for c in top[:2])
    assert len(s.state.zones['p1:hand']) == before + 2
    assert s.state.cards[bomb.id].zone == 'p1:graveyard'
    assert s.state.cards[spring.id].zone == 'p1:battlefield' and s.state.cards[spring.id].tapped
    assert mana_pool(s) == {}
    assert s.state.rules.turn_log.drew.get('p1', 0) == drawn + (0 if paused else 2)
    roundtrip(s)



@pytest.mark.parametrize('paused', [False, True])
def test_actual_ward_waits_for_mana_rider_before_original_spell_resolves(cards, paused, injected_draw_rider):
    s = table(cards, ['Abundance', 'Payment Test Spring', 'Lightning Bolt', 'Forest', 'Island'], ['Tolarian Terror'])
    spring = put(s, 'Payment Test Spring', 'battlefield')
    target = put(s, 'Tolarian Terror', 'battlefield', 'p2')
    if paused:
        put(s, 'Abundance', 'battlefield')
    top = set_library(s, ['Forest', 'Island'])
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    d = until_asked(s)
    assert d.resume.get('counter') == spell.id
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    if paused:
        d = s.state.rules.decision
        assert d is not None and 'decline' in {o.id for o in d.options}
        assert s.state.cards[spell.id].zone == 'stack' and s.state.cards[target.id].damage == 0
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id != 'decline')])
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['land'])
    settle(s)
    assert s.state.cards[target.id].damage == 3
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.cards[top[0]].zone == 'p1:hand'
    assert s.state.cards[spring.id].tapped and mana_pool(s) == {}
    roundtrip(s)
