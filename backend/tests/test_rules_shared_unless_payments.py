"""CR 118.12a / 605.3a: shared optional payments in APNAP order."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/shared_unless_payments_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Soul Strings', 'Icy Prison', 'Nakaya Shade', 'Wild Might', 'Rhystic Shield', 'Rhystic Tutor'])
def test_shared_unless_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def fund(s, pid, **mana):
    act(s, pid, type='add_mana', player=pid, mana=mana)


def shared_answers(s, accepted, expected=('p1', 'p2', 'p3')):
    for pid in expected:
        d = s.state.rules.decision
        assert d is not None and d.player == pid, (pid, d)
        assert {o.id for o in d.options} == {'pay', 'decline'}
        roundtrip(s)
        act(s, pid, type='choose', decision_id=d.id, option_ids=['pay' if pid in accepted else 'decline'])
        settle(s)
    roundtrip(s)


def pt(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id]).pt


@pytest.mark.parametrize('accepted', [[], ['p1'], ['p2'], ['p1', 'p2', 'p3']])
def test_nakaya_shade_every_player_may_pay_and_only_no_payments_pumps(cards, accepted):
    s = table(cards, ['Nakaya Shade'])
    source = put(s, 'Nakaya Shade', 'battlefield')
    for pid in ['p1', 'p2', 'p3']:
        fund(s, pid, C=2)
    fund(s, 'p1', B=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    shared_answers(s, accepted)
    assert pt(s, source) == ((1, 1) if accepted else (2, 2))
    for pid in ['p1', 'p2', 'p3']:
        assert sum(s.state.players[pid].mana.values()) == (0 if pid in accepted else 2)
    roundtrip(s)


def test_shared_payment_player_can_activate_mana_abilities_but_others_cannot(cards):
    s = table(cards, ['Nakaya Shade'], ['Sol Ring'], ['Sol Ring'])
    source = put(s, 'Nakaya Shade', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    other = put(s, 'Sol Ring', 'battlefield', 'p3')
    fund(s, 'p1', B=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    assert s.state.rules.decision.player == 'p2'  # p1 has no resources; automatic decline.
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p3', type='activate_ability', card_id=other.id, ability=0)
    assert s.state.model_dump(mode='json') == before
    act(s, 'p2', type='activate_ability', card_id=ring.id, ability=0)
    d = s.state.rules.decision
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    d = s.state.rules.decision
    assert d.player == 'p3'
    act(s, 'p3', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert pt(s, source) == (1, 1)
    assert s.state.cards[ring.id].tapped and not s.state.cards[other.id].tapped
    assert sum(s.state.players['p2'].mana.values()) == 0
    roundtrip(s)


@pytest.mark.parametrize('accepted', [[], ['p2']])
def test_wild_might_keeps_its_first_pump_even_when_the_second_is_denied(cards, accepted):
    s = table(cards, ['Wild Might', 'Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Wild Might', 'hand')
    for pid in ['p1', 'p2', 'p3']:
        fund(s, pid, C=2)
    fund(s, 'p1', C=3, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert pt(s, bear) == (3, 3)
    shared_answers(s, accepted)
    assert pt(s, bear) == ((3, 3) if accepted else (7, 7))
    roundtrip(s)


@pytest.mark.parametrize('accepted', [[], ['p2']])
def test_rhystic_shield_applies_both_instructions_to_the_original_creatures(cards, accepted):
    s = table(cards, ['Rhystic Shield', 'Grizzly Bears', 'Llanowar Elves'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell = put(s, 'Rhystic Shield', 'hand')
    for pid in ['p1', 'p2', 'p3']:
        fund(s, pid, C=2)
    fund(s, 'p1', C=3, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[])
    settle(s)
    assert pt(s, bear) == (2, 3) and pt(s, elf) == (1, 2)
    shared_answers(s, accepted)
    assert pt(s, bear) == (2, 3 if accepted else 5)
    assert pt(s, elf) == (1, 2 if accepted else 4)
    assert pt(s, other) == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('x,accepted', [(0, []), (0, ['p3']), (2, []), (2, ['p2']), (2, ['p1', 'p2', 'p3'])])
def test_soul_strings_uses_cast_x_for_all_payments_and_keeps_both_targets(cards, x, accepted):
    s = table(cards, ['Soul Strings', 'Grizzly Bears', 'Llanowar Elves'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    elf = put(s, 'Llanowar Elves', 'graveyard')
    spell = put(s, 'Soul Strings', 'hand')
    fund(s, 'p1', C=x + 2, B=1)
    for pid in ['p2', 'p3']:
        fund(s, pid, C=x)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id, elf.id], target_counts=[2], x_value=x)
    settle(s)
    shared_answers(s, accepted)
    for c in [bear, elf]:
        assert c.id in s.state.zones['p1:graveyard' if accepted else 'p1:hand']
    for pid in accepted:
        assert sum(s.state.players[pid].mana.values()) == 0
    roundtrip(s)


@pytest.mark.parametrize('accepted', [[], ['p2']])
def test_icy_prison_upkeep_is_prevented_by_any_players_payment(cards, accepted):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Icy Prison'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    prison = put(s, 'Icy Prison', 'hand')
    fund(s, 'p1', U=2)
    act(s, 'p1', type='cast_spell', card_id=prison.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and bear.id in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert bear.id in s.state.zones['p2:exile']
    roundtrip(s)
    to_phase(s, 'upkeep', turn=4)
    for pid in ['p1', 'p2', 'p3']:
        fund(s, pid, C=3)
    settle(s)
    shared_answers(s, accepted)
    assert prison.id in s.state.zones['p1:battlefield' if accepted else 'p1:graveyard']
    assert bear.id in s.state.zones['p2:exile' if accepted else 'p2:battlefield']
    roundtrip(s)


@pytest.mark.parametrize('accepted', [[], ['p2']])
def test_leading_unless_gates_the_entire_tutor_and_shuffle(cards, accepted):
    s = table(cards, ['Rhystic Tutor', 'Grizzly Bears'])
    spell = put(s, 'Rhystic Tutor', 'hand')
    for pid in ['p1', 'p2', 'p3']:
        fund(s, pid, C=2)
    fund(s, 'p1', C=4, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[])
    settle(s)
    shared_answers(s, accepted)
    if accepted:
        assert s.state.rules.decision is None
    else:
        d = s.state.rules.decision
        assert d is not None and d.player == 'p1'
        bear = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1')
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
        assert bear.id in s.state.zones['p1:hand']
    roundtrip(s)


@pytest.mark.parametrize('removed', [1, 2])
def test_soul_strings_rechecks_targets_before_offering_shared_payments(cards, removed):
    s = table(cards, ['Soul Strings', 'Grizzly Bears', 'Llanowar Elves'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    elf = put(s, 'Llanowar Elves', 'graveyard')
    spell = put(s, 'Soul Strings', 'hand')
    fund(s, 'p1', B=1, C=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id, elf.id], target_counts=[2], x_value=0)
    for c in [bear, elf][:removed]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    if removed == 2:
        assert s.state.rules.decision is None
        assert spell.id in s.state.zones['p1:graveyard']
    else:
        shared_answers(s, [])
        assert elf.id in s.state.zones['p1:hand']
    roundtrip(s)


def test_shade_returning_before_resolution_is_a_new_object(cards):
    s = table(cards, ['Nakaya Shade'])
    shade = put(s, 'Nakaya Shade', 'battlefield')
    fund(s, 'p1', B=1)
    act(s, 'p1', type='activate_ability', card_id=shade.id, ability=0)
    act(s, 'p1', type='move', card_ids=[shade.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[shade.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)  # All players lack mana: no payable choice, and the new Shade gets no bonus.
    assert s.state.rules.decision is None
    assert pt(s, shade) == (1, 1)
    roundtrip(s)
