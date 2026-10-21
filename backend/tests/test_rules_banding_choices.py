"""CR 608.2d / 611.2a: banding among resolution choices."""
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
from tests.test_rules_bandmate_references import keyword, mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import pt
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/banding_choice_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ["Urza's Avenger", "Nature's Blessing"])
def test_choice_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('choice', ['Banding', 'Flying', 'First strike', 'Trample'])
def test_avenger_chooses_on_resolution_and_pump_and_grant_expire(cards, choice):
    s = table(cards, ["Urza's Avenger"], [])
    source = put(s, "Urza's Avenger", 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert not s.state.rules.decision or s.state.rules.decision.kind != 'choose_one'
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_one'
    assert [o.label for o in d.options] == ['Banding', 'Flying', 'First strike', 'Trample']
    assert pt(s, source) == (3, 3)
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == choice)])
    settle(s)
    assert keyword(s, source, choice.lower())
    assert all(not keyword(s, source, other.lower()) for other in ['Banding', 'Flying', 'First strike', 'Trample'] if other != choice)
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert pt(s, source) == (4, 4)
    assert not keyword(s, source, choice.lower())
    roundtrip(s)


@pytest.mark.parametrize('choice', ['+1/+1 counter', 'Banding', 'First strike', 'Trample'])
def test_blessing_targets_on_activation_and_chooses_a_permanent_effect_on_resolution(cards, choice):
    s = table(cards, ["Nature's Blessing", 'Grizzly Bears', 'Sol Ring'], [])
    source = put(s, "Nature's Blessing", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    discard = put(s, 'Sol Ring', 'hand')
    mana(s, G=1, W=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[bear.id],
        cost_choices=[{'component': 1, 'cards': [discard.id]}])
    assert s.state.cards[discard.id].zone == 'p1:graveyard'
    assert not s.state.rules.decision or s.state.rules.decision.kind != 'choose_one'
    roundtrip(s)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_one'
    assert [o.label for o in d.options] == ['+1/+1 counter', 'Banding', 'First strike', 'Trample']
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == choice)])
    settle(s)
    assert pt(s, bear) == ((3, 3) if choice == '+1/+1 counter' else (2, 2))
    if choice != '+1/+1 counter':
        assert keyword(s, bear, choice.lower())
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert pt(s, bear) == ((3, 3) if choice == '+1/+1 counter' else (2, 2))
    if choice != '+1/+1 counter':
        assert keyword(s, bear, choice.lower())
    roundtrip(s)


def test_avenger_ability_resolves_without_asking_when_source_left(cards):
    s = table(cards, ["Urza's Avenger"], [])
    source = put(s, "Urza's Avenger", 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert not s.state.rules.decision or s.state.rules.decision.kind != 'choose_one'
    assert pt(s, source) == (4, 4) and not keyword(s, source, 'banding')
    roundtrip(s)


def test_blessing_fizzles_if_target_left_but_keeps_paid_discard(cards):
    s = table(cards, ["Nature's Blessing", 'Grizzly Bears', 'Sol Ring'], [])
    source = put(s, "Nature's Blessing", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    discard = put(s, 'Sol Ring', 'hand')
    mana(s, G=1, W=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[bear.id],
        cost_choices=[{'component': 1, 'cards': [discard.id]}])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert not s.state.rules.decision or s.state.rules.decision.kind != 'choose_one'
    assert s.state.cards[discard.id].zone == 'p1:graveyard'
    roundtrip(s)


def blessing_choice(s):
    source = put(s, "Nature's Blessing", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    discard = put(s, 'Sol Ring', 'hand')
    mana(s, G=1, W=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[bear.id],
        cost_choices=[{'component': 1, 'cards': [discard.id]}])
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_one'
    return bear, d


def test_blessing_cannot_choose_a_counter_when_counters_are_prohibited(cards):
    from app.game.errors import ActionError

    s = table(cards, ["Nature's Blessing", 'Grizzly Bears', 'Sol Ring', 'Solemnity'], [])
    put(s, 'Solemnity', 'battlefield')
    bear, d = blessing_choice(s)
    assert [o.label for o in d.options] == ['Banding', 'First strike', 'Trample']
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['0'])
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert keyword(s, bear, 'banding') and pt(s, bear) == (2, 2)
    roundtrip(s)


def test_blessing_counter_applies_replacements_and_resumes_the_same_resolution(cards):
    s = table(cards, ["Nature's Blessing", 'Grizzly Bears', 'Sol Ring', 'Hardened Scales', 'Doubling Season'], [])
    put(s, 'Hardened Scales', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    bear, d = blessing_choice(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert d and d.kind == 'confirm' and 'both apply' in d.prompt
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert pt(s, bear) in [(5, 5), (6, 6)]
    assert not s.state.zones['stack']
    roundtrip(s)


def test_blessing_granted_banding_forms_a_band_after_its_enchantment_leaves(cards):
    from tests.test_rules_banding import attacks, block

    s = table(cards, ["Nature's Blessing", 'Grizzly Bears', 'Llanowar Elves', 'Sol Ring'], ['Grizzly Bears'])
    source = put(s, "Nature's Blessing", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    discard = put(s, 'Sol Ring', 'hand')
    mana(s, G=1, W=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[bear.id],
        cost_choices=[{'component': 1, 'cards': [discard.id]}])
    settle(s)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == 'Banding')])
    settle(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    attacks(s, [(bear, 'p2'), (elf, 'p2')], [[bear, elf]])
    assert keyword(s, bear, 'banding')
    assert len(s.state.rules.attacking_bands) == 1
    block(s, [])
    roundtrip(s)
