"""CR 603.4 / 701.21: a death that was not a sacrifice."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/nonsacrificed_departures_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_miter_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Urza's Miter")).level == 'FULL'


@pytest.mark.parametrize('payment', ['pay', 'decline', 'unavailable'])
@pytest.mark.parametrize('recipient', ['self', 'own', 'opponent'])
def test_miter_only_triggers_for_nonsacrificed_artifacts_you_control(cards, payment, recipient):
    s = table(cards, ["Urza's Miter", 'Sol Ring', 'Shatter'], ['Sol Ring'])
    miter = put(s, "Urza's Miter", 'battlefield')
    own = put(s, 'Sol Ring', 'battlefield')
    opposing = put(s, 'Sol Ring', 'battlefield', 'p2')
    target = {'self': miter, 'own': own, 'opponent': opposing}[recipient]
    spell = put(s, 'Shatter', 'hand')
    mana(s, C=4 if payment != 'unavailable' else 1, R=1)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    if recipient != 'opponent' and payment != 'unavailable':
        assert d and d.player == 'p1' and {o.id for o in d.options} == {'pay', 'decline'}
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[payment])
        settle(s)
    else:
        assert not d or not s.state.zones['stack']
    assert len(s.state.zones['p1:hand']) == before - 1 + (recipient != 'opponent' and payment == 'pay')
    roundtrip(s)


@pytest.mark.parametrize('recipient', ['self', 'own'])
def test_miter_does_not_trigger_for_a_sacrifice_paid_as_an_activation_cost(cards, recipient):
    s = table(cards, ["Urza's Miter", 'Sol Ring', 'Claws of Gix'], [])
    miter = put(s, "Urza's Miter", 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    claws = put(s, 'Claws of Gix', 'battlefield')
    victim = miter if recipient == 'self' else ring
    mana(s, C=4)
    act(s, 'p1', type='activate_ability', card_id=claws.id, ability=0,
        cost_choices=[{'component': 1, 'cards': [victim.id]}])
    roundtrip(s)
    settle(s)
    assert not s.state.zones['stack']
    assert s.state.players['p1'].life == 41
    roundtrip(s)


def test_miter_does_not_trigger_for_a_sacrifice_in_a_resolving_effect(cards):
    s = table(cards, ["Urza's Miter", 'Ornithopter', 'Grizzly Bears', 'Innocent Blood'], ['Grizzly Bears'])
    put(s, "Urza's Miter", 'battlefield')
    thopter = put(s, 'Ornithopter', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell = put(s, 'Innocent Blood', 'hand')
    mana(s, B=1, C=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[thopter.id])
    settle(s)
    d = s.state.rules.decision
    if d:
        assert d.player == 'p2'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    assert not s.state.zones['stack']
    assert s.state.cards[thopter.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_miter_sees_each_simultaneously_destroyed_artifact_including_itself(cards):
    s = table(cards, ["Urza's Miter", 'Sol Ring', 'Ornithopter', 'Shatterstorm'], [])
    for name in ["Urza's Miter", 'Sol Ring', 'Ornithopter']:
        put(s, name, 'battlefield')
    spell = put(s, 'Shatterstorm', 'hand')
    mana(s, C=11, R=2)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    for _ in range(3):
        settle(s)
        d = s.state.rules.decision
        assert d and d.player == 'p1' and {o.id for o in d.options} == {'pay', 'decline'}
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert not s.state.zones['stack']
    assert len(s.state.zones['p1:hand']) == before - 1 + 3
    roundtrip(s)


def test_a_previously_sacrificed_artifact_can_die_as_a_different_object_and_trigger_miter(cards):
    s = table(cards, ["Urza's Miter", 'Sol Ring', 'Claws of Gix', 'Shatter'], [])
    put(s, "Urza's Miter", 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    claws = put(s, 'Claws of Gix', 'battlefield')
    mana(s, C=5, R=1)
    act(s, 'p1', type='activate_ability', card_id=claws.id, ability=0,
        cost_choices=[{'component': 1, 'cards': [ring.id]}])
    settle(s)
    assert not s.state.zones['stack']
    act(s, 'p1', type='move', card_ids=[ring.id], to={'player': 'p1', 'zone': 'battlefield'})
    spell = put(s, 'Shatter', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('text', [
    "When this creature enters, if it wasn't sacrificed, draw a card.",
    "Whenever one or more creatures die, if it wasn't sacrificed, draw a card.",
])
def test_nonsacrifice_condition_needs_a_single_departure_event(text):
    from app.rules import scripts
    from tests.test_rules_scripts import ch

    value = ch('Unbound', 'Creature — Human', text)
    assert not scripts.definitions(value)


def test_miter_does_not_trigger_when_a_graveyard_replacement_exiles_the_artifact(cards):
    s = table(cards, ["Urza's Miter", 'Sol Ring', 'Shatter', 'Rest in Peace'], [])
    put(s, "Urza's Miter", 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    put(s, 'Rest in Peace', 'battlefield')
    spell = put(s, 'Shatter', 'hand')
    mana(s, C=4, R=1)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id])
    settle(s)
    assert not s.state.zones['stack']
    assert s.state.cards[ring.id].zone == 'p1:exile'
    assert len(s.state.zones['p1:hand']) == before - 1
    roundtrip(s)
