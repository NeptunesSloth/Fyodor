"""Native stun replacement in costs and kind-specific removal restrictions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import activate
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_restrictions43_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='crs', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = ['Pili-Pala', 'Halo Fountain', 'Grizzly Bears', 'Fear of Sleep Paralysis']
    return table(cards, names, names, names)


def stun(s, c):
    act(s, 'p1', type='tap', card_ids=[c.id], tapped=True)
    act(s, 'p1', type='counter', card_ids=[c.id], kind='stun', delta=2)


def test_actual_halo_fountain_stun_replaces_untap_cost_and_still_pays(cards):
    s = setup(cards)
    fountain = put(s, 'Halo Fountain', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    stun(s, bear)
    activate(s, fountain)
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
    assert s.state.cards[bear.id].tapped
    assert s.state.cards[bear.id].counters['stun'] == 1
    assert s.state.cards[fountain.id].tapped
    assert any(c.is_token and c.name == 'Citizen' for c in s.state.cards.values())
    roundtrip(s)



def test_native_removal_kind_controller_and_move_preflight(cards):
    from app.rules import counter_moves, counter_removal_results
    from app.rules.plan import Plan

    s = setup(cards)
    fear = put(s, 'Fear of Sleep Paralysis', 'battlefield', pid='p2')
    decline_eerie(s)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    dest = put(s, 'Pili-Pala', 'battlefield')
    stun(s, bear)
    p = Plan(s.state, 'p1', cards, None)
    assert counter_removal_results.remove(p, bear.id, 'stun', 1, by='p1') == 0
    ctx = {'controller': 'p1', 'source_card': bear.id, 'source_object': p.oid(bear.id)}
    assert counter_moves._do(p, ctx, {}, [bear.id], dest.id, {'stun': 1})
    assert p.state.cards[bear.id].counters['stun'] == 2
    assert not p.state.cards[dest.id].counters
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
    p = Plan(s.state, 'p1', cards, None)
    assert counter_removal_results.remove(p, bear.id, '+1/+1', 1, by='p1') == 1
    # It protects opponents of the current source controller, not its owner.
    p.state.cards[fear.id].controller = 'p1'
    assert counter_removal_results.remove(p, bear.id, 'stun', 1, by='p1') == 1


def test_actual_halo_fountain_prohibited_stun_cost_rolls_back(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority

    s = setup(cards)
    fountain = put(s, 'Halo Fountain', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Fear of Sleep Paralysis', 'battlefield', pid='p2')
    decline_eerie(s)
    stun(s, bear)
    mana(s, W=1)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=fountain.id, ability=0)
    assert s.state.model_dump(mode='json') == before
    assert not s.state.cards[fountain.id].tapped
    assert s.state.cards[bear.id].counters['stun'] == 2


def test_actual_pili_pala_q_cost_uses_stun_replacement(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Pili-Pala', 'battlefield')
    to_phase(s, 'main1', turn=4)
    stun(s, source)
    activate(s, source, ability=1)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert s.state.cards[source.id].tapped
    assert s.state.cards[source.id].counters['stun'] == 1
    roundtrip(s)


def test_actual_pili_pala_prohibited_q_cost_has_no_partial_payment(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Pili-Pala', 'battlefield')
    to_phase(s, 'main1', turn=4)
    put(s, 'Fear of Sleep Paralysis', 'battlefield', pid='p2')
    decline_eerie(s)
    stun(s, source)
    mana(s, C=2)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.model_dump(mode='json') == before


def test_actual_halo_fountain_untap_cost_true_cold(cards, tmp_path):
    from tests.test_rules_counter_outcomes42 import cold_finish

    s = setup(cards)
    fountain = put(s, 'Halo Fountain', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Pili-Pala', 'battlefield')
    stun(s, bear)
    act(s, 'p1', type='tap', card_ids=[other.id], tapped=True)
    activate(s, fountain)
    d = s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options} == {bear.id, other.id}
    cold_finish(s, cards, tmp_path, [[bear.id]],
                f"assert s.state.cards[{bear.id!r}].tapped; "
                f"assert s.state.cards[{bear.id!r}].counters['stun'] == 1; "
                f"assert s.state.cards[{other.id!r}].tapped; "
                "assert any(c.is_token and c.name == 'Citizen' for c in s.state.cards.values())")


def decline_eerie(s):
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.min_choices == 0
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
