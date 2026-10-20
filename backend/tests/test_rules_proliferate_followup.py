"""CR 701.34: actual counter recipients qualify for a proliferate followup."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/proliferate_followup_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_ripples_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Ripples of Potential')).level == 'FULL'


def answer(s, ids):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    d = s.state.rules.decision
    assert d
    assert set(ids) <= {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


def setup(cards, extra=None):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    extras = [extra] if isinstance(extra, str) else list(extra or [])
    s = table(cards, ['Ripples of Potential', 'Grizzly Bears', 'Sol Ring', 'Simic Sky Swallower', *extras], ['Grizzly Bears'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    sky = put(s, 'Simic Sky Swallower', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    for c, kind in [(bear, '+1/+1'), (ring, 'charge'), (sky, 'shield'), (other, '+1/+1')]:
        act(s, 'p1', type='counter', card_ids=[c.id], kind=kind, delta=1)
    act(s, 'p1', type='resource', player='p3', key='poison', delta=1)
    for name in extras:
        put(s, name, 'battlefield')
    return s, bear, ring, sky, other


def cast(s):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle

    spell = put(s, 'Ripples of Potential', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)


def test_followup_only_offers_own_permanents_that_actually_received_counters(cards):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase

    s, bear, ring, sky, other = setup(cards)
    cast(s)
    answer(s, [bear.id, other.id, 'p3'])
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {bear.id}
    answer(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:phased'
    assert s.state.cards[ring.id].zone == s.state.cards[sky.id].zone == 'p1:battlefield'
    assert s.state.cards[other.id].zone == 'p2:battlefield'
    assert s.state.players['p3'].resources['poison'] == 2
    assert s.state.cards[bear.id].counters['+1/+1'] == 2
    roundtrip(s)
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].counters['+1/+1'] == 2
    roundtrip(s)


def test_followup_is_untargeted_and_supports_noncreatures_and_any_counter_kind(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, bear, ring, sky, _ = setup(cards)
    cast(s)
    answer(s, [ring.id, sky.id])
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {ring.id, sky.id}
    answer(s, [ring.id, sky.id])
    settle(s)
    assert s.state.cards[ring.id].zone == s.state.cards[sky.id].zone == 'p1:phased'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('decline_first', [True, False])
def test_can_choose_no_proliferate_recipients_or_no_phasing(cards, decline_first):
    from tests.test_rules_designations import roundtrip, settle

    s, bear, _, _, _ = setup(cards)
    cast(s)
    answer(s, [] if decline_first else [bear.id])
    if not decline_first:
        answer(s, [])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].counters['+1/+1'] == (1 if decline_first else 2)
    roundtrip(s)


def test_prohibited_counter_puts_do_not_qualify_for_phasing(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, bear, _, _, _ = setup(cards, 'Solemnity')
    cast(s)
    answer(s, [bear.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_repeated_proliferation_replacement_keeps_followup_scope_across_both_actions(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, bear, ring, _, _ = setup(cards, 'Tekuthal, Inquiry Dominus')
    cast(s)
    answer(s, [bear.id])
    d = s.state.rules.decision
    assert d and d.prompt.startswith('Proliferate:')
    answer(s, [ring.id])
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {bear.id, ring.id}
    answer(s, [bear.id, ring.id])
    settle(s)
    assert s.state.cards[bear.id].zone == s.state.cards[ring.id].zone == 'p1:phased'
    assert s.state.cards[bear.id].counters['+1/+1'] == 2
    assert s.state.cards[ring.id].counters['charge'] == 2
    roundtrip(s)


def test_counter_ordering_pause_preserves_actual_recipient_scope(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, bear, ring, _, _ = setup(cards, ('Hardened Scales', 'Doubling Season'))
    cast(s)
    answer(s, [bear.id])
    for _ in range(3):
        d = s.state.rules.decision
        assert d
        if '616.1' not in d.prompt:
            break
        answer(s, [d.options[0].id])
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {bear.id}
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[ring.id])
    answer(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:phased'
    assert s.state.cards[bear.id].counters['+1/+1'] in (4, 5)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)
