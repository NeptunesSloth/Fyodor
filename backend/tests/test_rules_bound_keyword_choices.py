"""CR 608.2d: a choice grant binds its object before presenting alternatives."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_banding import declare_only
from tests.test_rules_bandmate_references import keyword, mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import pt
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/bound_keyword_choices_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Hungering Puppetbeast', "Hunter's Axe"])
def test_bound_keyword_choice_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('choice', ['Trample', 'Hexproof', 'Haste'])
@pytest.mark.parametrize('counters_forbidden', [False, True])
def test_puppetbeast_grants_its_choice_even_when_the_counter_cannot_be_put(cards, choice, counters_forbidden):
    s = table(cards, ['Hungering Puppetbeast', 'Sol Ring', 'Solemnity'], [])
    beast = put(s, 'Hungering Puppetbeast', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    if counters_forbidden:
        put(s, 'Solemnity', 'battlefield')
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=beast.id, ability=1,
        cost_choices=[{'component': 1, 'cards': [ring.id]}])
    settle(s)
    d = s.state.rules.decision
    assert d and [o.label for o in d.options] == ['Trample', 'Hexproof', 'Haste']
    assert pt(s, beast) == ((5, 5) if counters_forbidden else (6, 6))
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == choice)])
    settle(s)
    assert keyword(s, beast, choice.lower())
    assert not keyword(s, ring, choice.lower())
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert not keyword(s, beast, choice.lower())
    assert pt(s, beast) == ((5, 5) if counters_forbidden else (6, 6))
    roundtrip(s)


@pytest.mark.parametrize('choice', ['Trample', 'Deathtouch'])
@pytest.mark.parametrize('equipment_left', [False, True])
def test_axe_granted_attack_trigger_gives_the_attacker_the_choice(cards, choice, equipment_left):
    s = table(cards, ["Hunter's Axe", 'Grizzly Bears'], ['Grizzly Bears'])
    axe = put(s, "Hunter's Axe", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='attach', card_ids=[axe.id], to=bear.id)
    declare_only(s, [bear], [])
    if equipment_left:
        act(s, 'p1', type='move', card_ids=[axe.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    assert d and [o.label for o in d.options] == ['Trample', 'Deathtouch']
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == choice)])
    settle(s)
    assert keyword(s, bear, choice.lower()) and not keyword(s, axe, choice.lower())
    roundtrip(s)


def test_keyword_choice_pronoun_without_an_antecedent_is_manual():
    from app.rules import scripts

    assert scripts._parse_effects('It gains your choice of trample or haste until end of turn.', None) is None


def test_puppetbeast_does_not_grant_a_choice_to_a_new_incarnation(cards):
    s = table(cards, ['Hungering Puppetbeast', 'Sol Ring'], [])
    beast = put(s, 'Hungering Puppetbeast', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=beast.id, ability=1,
        cost_choices=[{'component': 1, 'cards': [ring.id]}])
    act(s, 'p1', type='move', card_ids=[beast.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[beast.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert not s.state.rules.decision or s.state.rules.decision.kind != 'choose_one'
    assert pt(s, beast) == (5, 5)
    assert not keyword(s, beast, 'haste')
    roundtrip(s)
