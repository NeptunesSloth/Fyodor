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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/linked_attachment_return_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Gift of Immortality'


def setup(cards, *, host_owner='p1', aura_owner='p1'):
    s = table(cards, [NAME, 'Grizzly Bears', 'Murder', 'Ephemerate', 'Containment Priest', 'Disenchant', 'Swords to Plowshares', 'Gods Willing', 'Wrath of God', "Teferi's Protection"],
              [NAME, 'Grizzly Bears'])
    host = put(s, 'Grizzly Bears', 'battlefield', host_owner)
    aura = put(s, NAME, 'hand', aura_owner)
    if aura_owner != 'p1':
        act(s, aura_owner, type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=2, W=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[host.id])
    settle(s)
    return s, aura, host


def kill(s, host, *, resolve=True):
    spell = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[host.id])
    if resolve:
        settle(s)


def end(s):
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'end')
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_returns_host_then_aura_attached_next_end_step(cards):
    s, aura, host = setup(cards)
    kill(s, host)
    assert s.state.cards[host.id].zone == 'p1:battlefield'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert len(s.state.rules.delayed) == 1
    roundtrip(s)
    end(s)
    assert s.state.cards[aura.id].zone == 'p1:battlefield'
    assert s.state.cards[aura.id].attached_to == host.id
    roundtrip(s)


@pytest.mark.parametrize('which', ['host', 'aura'])
def test_old_incarnation_cannot_return_or_receive_aura(cards, which):
    s, aura, host = setup(cards)
    kill(s, host)
    if which == 'host':
        blink = put(s, 'Ephemerate', 'hand')
        mana(s, W=1)
        act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[host.id])
        settle(s)
    else:
        act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'exile'})
        act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'graveyard'})
    end(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_returned_creature_dying_again_leaves_aura_in_graveyard(cards):
    s, aura, host = setup(cards)
    kill(s, host)
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'graveyard'})
    end(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('host_owner,aura_owner', [('p2', 'p1'), ('p1', 'p2')])
def test_creature_and_aura_return_under_their_owners_control(cards, host_owner, aura_owner):
    s, aura, host = setup(cards, host_owner=host_owner, aura_owner=aura_owner)
    kill(s, host)
    assert s.state.cards[host.id].zone == f'{host_owner}:battlefield'
    end(s)
    assert s.state.cards[aura.id].zone == f'{aura_owner}:battlefield'
    assert s.state.cards[aura.id].attached_to == host.id
    roundtrip(s)


def test_priest_replaces_immediate_return_so_aura_cannot_return(cards):
    s, aura, host = setup(cards)
    put(s, 'Containment Priest', 'battlefield')
    kill(s, host)
    assert s.state.cards[host.id].zone == 'p1:exile'
    end(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_aura_removed_before_host_death_has_no_trigger(cards):
    s, aura, host = setup(cards)
    spell = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[aura.id])
    settle(s)
    kill(s, host)
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    assert not s.state.rules.delayed
    roundtrip(s)


def test_token_host_returns_neither_token_nor_aura(cards):
    s = table(cards, [NAME, 'Raise the Alarm', 'Murder'])
    spell = put(s, 'Raise the Alarm', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    host = next(c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier')
    aura = put(s, NAME, 'hand')
    mana(s, C=2, W=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[host.id])
    settle(s)
    kill(s, host)
    assert host.id not in s.state.cards and not s.state.rules.delayed
    end(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_merged_host_returns_all_components_and_owner_chooses_attachment(cards):
    s = table(cards, [NAME, 'Grizzly Bears', 'Migratory Greathorn', 'Murder'])
    host = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, NAME, 'hand')
    mana(s, C=2, W=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[host.id])
    settle(s)
    from tests.test_rules_wave18d_merged import mutate as mutate_card

    mutate = mutate_card(s, 'Migratory Greathorn', host, over='under', C=2, G=1)
    kill(s, host)
    assert s.state.cards[host.id].zone == 'p1:battlefield'
    assert s.state.cards[mutate.id].zone == 'p1:battlefield'
    end(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'linked_attachment_host'
    assert {o.id for o in d.options} == {host.id, mutate.id}
    assert s.view(d.player)['rules']['decision'].get('options')
    assert not s.view('p2')['rules']['decision'].get('options')
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[mutate.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == mutate.id
    roundtrip(s)


def test_protection_from_white_makes_delayed_attachment_illegal(cards):
    from tests.test_rules_wave5e_protection import resolve_with

    s, aura, host = setup(cards)
    kill(s, host)
    spell = put(s, 'Gods Willing', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[host.id])
    resolve_with(s, 'White')
    settle(s)
    end(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_phased_out_host_is_not_available_to_delayed_attachment(cards):
    s, aura, host = setup(cards)
    kill(s, host)
    spell = put(s, "Teferi's Protection", 'hand')
    mana(s, C=2, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[host.id].zone.endswith(':phased')
    end(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_simultaneous_deaths_preserve_source_graveyard_link(cards):
    s, aura, host = setup(cards)
    spell = put(s, 'Wrath of God', 'hand')
    mana(s, C=2, W=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[host.id].zone == 'p1:battlefield'
    end(s)
    assert s.state.cards[aura.id].attached_to == host.id
    roundtrip(s)


def test_death_during_end_step_waits_for_following_end_step(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, aura, host = setup(cards)
    end(s)
    kill(s, host)
    assert s.state.cards[host.id].zone == 'p1:battlefield'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)
    to_phase(s, 'end', turn=2)
    settle(s)
    assert s.state.cards[aura.id].attached_to == host.id
    roundtrip(s)
