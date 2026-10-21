"""CR 608.2c, 701.23b/d: conditional tutor branches resolve once and search privately."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/conditional_tutor_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='ctu', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_counsel_full(cards):
    assert coverage.of_card_data(cards.resolve('Demonic Counsel')).level == 'FULL'


@pytest.mark.parametrize('delirium', [False, True])
def test_conditional_search_uses_current_graveyard_types(cards, delirium):
    s = table(cards, ['Demonic Counsel', 'Demon of Catastrophes', 'Perilous Myr', 'Lightning Bolt'])
    source = put(s, 'Demonic Counsel', 'hand')
    # Artifact + creature on one card count separately; basic is a supertype, not another type.
    put(s, 'Perilous Myr', 'graveyard')
    put(s, 'Forest', 'graveyard')
    if delirium:
        put(s, 'Lightning Bolt', 'graveyard')
    mana(s, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    d = until_asked(s)
    assert d is not None and d.resume['step'] == 'search'
    assert d.min_choices == (1 if delirium else 0) and d.max_choices == 1
    options = {s.state.cards[o.id].name: o.id for o in d.options}
    assert 'Demon of Catastrophes' in options
    assert ('Forest' in options) == delirium
    for pid in ('p2', 'p3'):
        public = json.dumps(s.view(pid))
        assert all(o.id not in public for o in d.options)
        assert 'Demon of Catastrophes' not in public
    roundtrip(s)
    if delirium:
        with pytest.raises(ActionError):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    chosen = options['Forest' if delirium else 'Demon of Catastrophes']
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert s.state.cards[chosen].zone == 'p1:hand'
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_delirium_is_checked_on_resolution(cards):
    s = table(cards, ['Demonic Counsel', 'Demon of Catastrophes', 'Perilous Myr', 'Lightning Bolt'])
    source = put(s, 'Demonic Counsel', 'hand')
    put(s, 'Perilous Myr', 'graveyard')
    put(s, 'Forest', 'graveyard')
    bolt = put(s, 'Lightning Bolt', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, B=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p3'])
    d = until_asked(s)
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert d is not None and d.resume['step'] == 'search' and d.min_choices == 1
    chosen = next(o.id for o in d.options if s.state.cards[o.id].name == 'Forest')
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert s.state.cards[chosen].zone == 'p1:hand'
    roundtrip(s)


def test_qualified_search_can_fail_to_find(cards):
    s = table(cards, ['Demonic Counsel', 'Demon of Catastrophes'])
    source = put(s, 'Demonic Counsel', 'hand')
    mana(s, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    d = until_asked(s)
    assert d is not None and d.min_choices == 0
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert not any(c.name == 'Demon of Catastrophes' and c.zone == 'p1:hand' for c in s.state.cards.values())
    roundtrip(s)
