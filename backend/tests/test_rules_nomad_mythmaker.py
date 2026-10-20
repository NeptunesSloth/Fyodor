"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/nomad_mythmaker_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Nomad Mythmaker'


def setup(cards, aura='Arrest'):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Grizzly Bears', 'Lightning Greaves', 'Rancor'], [aura, 'Grizzly Bears'])
    source = put(s, NAME, 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    target = put(s, aura, 'graveyard', 'p2')
    to_phase(s, 'main1', turn=4)
    return s, source, own, other, target


def activate(s, source, target, *, resolve=True):
    from tests.test_rules_wave7b_activation import ability_index

    mana(s, W=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Put target Aura'), targets=[target.id])
    if resolve:
        settle(s)


def test_nomad_canonical_promotion(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_other_graveyard_aura_enters_under_your_control_on_your_creature(cards):
    s, source, own, other, aura = setup(cards)
    activate(s, source, aura)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'aura_enters'
    assert {o.id for o in d.options} == {source.id, own.id}
    assert other.id not in {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[own.id])
    settle(s)
    assert s.state.cards[aura.id].zone == 'p1:battlefield'
    assert s.state.cards[aura.id].owner == 'p2' and s.state.cards[aura.id].controller == 'p1'
    assert s.state.cards[aura.id].attached_to == own.id
    roundtrip(s)


def test_player_only_aura_stays_in_graveyard(cards):
    s, source, _, _, aura = setup(cards, 'Curse of Opulence')
    activate(s, source, aura)
    assert s.state.cards[aura.id].zone == 'p2:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_restricted_aura_with_no_legal_host_stays_in_graveyard(cards):
    s, source, _, _, aura = setup(cards, 'Daybreak Coronet')
    activate(s, source, aura)
    assert s.state.cards[aura.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_attachment_does_not_target_shrouded_host(cards):
    s, source, own, _, aura = setup(cards)
    greaves = put(s, 'Lightning Greaves', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[greaves.id], to=own.id)
    activate(s, source, aura)
    d = s.state.rules.decision
    assert d is not None and own.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[own.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == own.id
    roundtrip(s)


def test_restricted_aura_uses_only_legal_creature_host(cards):
    s, source, own, _, aura = setup(cards, 'Daybreak Coronet')
    rancor = put(s, 'Rancor', 'hand')
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=rancor.id, targets=[own.id])
    settle(s)
    activate(s, source, aura)
    assert s.state.rules.decision is None
    assert s.state.cards[aura.id].attached_to == own.id
    assert s.state.cards[aura.id].controller == 'p1' and s.state.cards[aura.id].owner == 'p2'
    roundtrip(s)


def test_graveyard_target_new_incarnation_fizzles(cards):
    s, source, _, _, aura = setup(cards)
    activate(s, source, aura, resolve=False)
    act(s, 'p2', type='move', card_ids=[aura.id], to={'player': 'p2', 'zone': 'exile'})
    act(s, 'p2', type='move', card_ids=[aura.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[aura.id].zone == 'p2:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_no_remaining_creature_you_control_cannot_use_opponents_host(cards):
    s, source, own, other, aura = setup(cards)
    activate(s, source, aura, resolve=False)
    act(s, 'p1', type='move', card_ids=[source.id, own.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[other.id].zone == 'p2:battlefield'
    assert s.state.cards[aura.id].zone == 'p2:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)
