"""CR 608.2d: return one card matching either qualified card kind."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/disjunctive_reanimation_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Overlord of the Balemurk'


def test_overlord_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_overlord(cards, *, impending=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave43d_cast_keywords import alt_key

    s = table(cards, [NAME, 'Grizzly Bears', 'Serra Avatar', 'Gideon Jura', 'Sol Ring'], ['Grizzly Bears', 'Gideon Jura'])
    source = put(s, NAME, 'hand')
    available = {n: put(s, n, 'graveyard') for n in ['Grizzly Bears', 'Serra Avatar', 'Gideon Jura', 'Sol Ring']}
    other = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    # Prevent an incidental matching card from the starting library; four lands are milled.
    top = s.state.zones['p1:library'][:4]
    assert len(top) == 4 and all(s.state.cards[c].name == 'Forest' for c in top)
    mana(s, B=5)
    extra = {'alt_cost': alt_key(s, NAME, 'impending')} if impending else {}
    act(s, 'p1', type='cast_spell', card_id=source.id, **extra)
    return s, source, available, other, top


@pytest.mark.parametrize('impending', [False, True])
@pytest.mark.parametrize('pick', ['Grizzly Bears', 'Gideon Jura', None])
def test_enters_mills_then_optional_choice_keeps_each_branch_qualifier(cards, impending, pick):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, available, other, top = setup_overlord(cards, impending=impending)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    offered = {o.card_id for o in d.options if o.card_id}
    assert offered == {available['Grizzly Bears'].id, available['Gideon Jura'].id}
    assert other.id not in offered
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in top)
    if impending:
        assert not chars(s, source).is_creature and s.state.cards[source.id].counters['time'] == 5
    roundtrip(s)
    chosen = [] if pick is None else [next(o.id for o in d.options if o.card_id == available[pick].id)]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=chosen)
    settle(s)
    for name, c in available.items():
        assert s.state.cards[c.id].zone == ('p1:hand' if name == pick else 'p1:graveyard')
    roundtrip(s)


def test_attack_also_mills_then_returns_an_eligible_card(cards):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_designations import roundtrip, settle

    s, source, available, _, _ = setup_overlord(cards)
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    before = len(s.state.zones['p1:graveyard'])
    declare_only(s, [source], {})
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    assert len(s.state.zones['p1:graveyard']) == before + 4
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.card_id == available['Gideon Jura'].id)])
    settle(s)
    assert s.state.cards[available['Gideon Jura'].id].zone == 'p1:hand'
    roundtrip(s)


def test_can_return_the_creature_just_milled(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, available, _, _ = setup_overlord(cards)
    bear = available['Grizzly Bears']
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    settle(s)
    d = s.state.rules.decision
    assert d and s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == bear.id)])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:hand'
    roundtrip(s)
