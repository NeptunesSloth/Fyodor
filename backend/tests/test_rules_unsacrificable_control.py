"""CR 101.2, 701.21, 608.2c: unsacrificable permanents and upkeep control transfers."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/unsacrificable_control_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Alexios, Deimos of Kosmos'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Grizzly Bears', 'Fling', "Ashnod's Altar", 'Dress Down', 'Vorinclex, Monstrous Raider', 'Assault Suit', 'Wild Cantor', 'Sakura-Tribe Elder', 'Jace Beleren', 'Ornithopter', 'Goblin Welder', 'Sol Ring', "Urza's Saga", 'Nissa, Worldwaker', 'Avalanche Riders', 'Elder Deep-Fiend', 'Patron of the Akki'],
              ['Diabolic Edict', 'All Is Dust', 'Vorinclex, Monstrous Raider', 'Jace Beleren'], [])
    alexios = put(s, NAME, 'battlefield')
    return s, alexios


def test_alexios_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_each_upkeep_transfers_untaps_grows_and_grants_haste(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s, alexios = setup(cards)
    for turn, pid in [(2, 'p2'), (3, 'p3'), (4, 'p1')]:
        act(s, 'p1', type='tap', card_ids=[alexios.id], tapped=True)
        to_phase(s, 'main1', turn=turn)
        c = s.state.cards[alexios.id]
        assert c.owner == 'p1' and c.controller == pid and not c.tapped
        assert c.counters['+1/+1'] == turn - 1
        assert 'haste' in chars(s, c).keywords
        roundtrip(s)


@pytest.mark.parametrize('vorinclex_player,expected', [('p1', 0), ('p2', 2)])
def test_upkeep_counter_is_put_by_the_named_player_not_ability_controller(cards, vorinclex_player, expected):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, alexios = setup(cards)
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', vorinclex_player)
    to_phase(s, 'main1', turn=2)
    assert s.state.cards[alexios.id].controller == 'p2'
    assert s.state.cards[alexios.id].counters.get('+1/+1', 0) == expected
    roundtrip(s)


@pytest.mark.parametrize('other', [False, True])
def test_edict_cannot_choose_alexios_and_sacrifices_another_creature_if_possible(cards, other):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, alexios = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield') if other else None
    edict = put(s, 'Diabolic Edict', 'hand', 'p2')
    mana(s, 'p2', C=1, B=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=edict.id, targets=['p1'])
    settle(s)
    assert s.state.cards[alexios.id].zone == 'p1:battlefield'
    if bear:
        assert s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_sacrifice_all_effect_leaves_alexios_but_sacrifices_other_colored_creatures(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, alexios = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'All Is Dust', 'hand', 'p2')
    # Sorcery is cast on its controller's turn; Alexios is now controlled by p2.
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=2)
    mana(s, 'p2', C=7)
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[alexios.id].zone == 'p2:battlefield'
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_cannot_sacrifice_alexios_for_an_additional_cost(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, alexios = setup(cards)
    fling = put(s, 'Fling', 'hand')
    mana(s, C=1, R=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=fling.id, targets=['p2'], cost_choices=[{'component': 0, 'cards': [alexios.id]}])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_mana_sacrifice_cannot_choose_alexios_but_can_choose_another_creature(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, alexios = setup(cards)
    altar = put(s, "Ashnod's Altar", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0, cost_choices=[{'component': 0, 'cards': [alexios.id]}])
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0, cost_choices=[{'component': 0, 'cards': [bear.id]}])
    settle(s)
    assert s.state.cards[alexios.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert sum(u.sym == 'C' for u in s.state.players['p1'].mana_units) + s.state.players['p1'].mana.get('C', 0) == 2
    roundtrip(s)


def test_owner_cannot_be_attacked_but_owners_planeswalker_can(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, alexios = setup(cards)
    pw = put(s, 'Jace Beleren', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=pw.id, kind='loyalty', value=3)
    to_phase(s, 'main1', turn=2)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': alexios.id, 'target': 'p1'}])
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[])
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': alexios.id, 'target': pw.id}])
    assert s.state.cards[alexios.id].attacking.id == pw.id
    roundtrip(s)


@pytest.mark.parametrize('name', ['Wild Cantor', 'Sakura-Tribe Elder'])
def test_equipment_prohibition_stops_self_sacrifice_costs_including_mana(cards, name):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip

    s, _ = setup(cards)
    source = put(s, name, 'battlefield')
    suit = put(s, 'Assault Suit', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[suit.id], to=source.id)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert s.state.model_dump_json() == before
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_ability_loss_removes_alexios_own_sacrifice_prohibition(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, alexios = setup(cards)
    dress = put(s, 'Dress Down', 'hand')
    mana(s, C=2, U=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=dress.id)
    settle(s)
    fling = put(s, 'Fling', 'hand')
    act(s, 'p1', type='cast_spell', card_id=fling.id, targets=['p2'], cost_choices=[{'component': 0, 'cards': [alexios.id]}])
    settle(s)
    assert s.state.cards[alexios.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 36
    roundtrip(s)


def test_welder_returns_legal_incoming_even_when_outgoing_cannot_be_sacrificed(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, alexios = setup(cards)
    act(s, 'p1', type='move', card_ids=[alexios.id], to={'player': 'p1', 'zone': 'exile'})
    welder = put(s, 'Goblin Welder', 'battlefield')
    host = put(s, 'Ornithopter', 'battlefield')
    suit = put(s, 'Assault Suit', 'battlefield')
    incoming = put(s, 'Sol Ring', 'graveyard')
    act(s, 'p1', type='attach', card_ids=[suit.id], to=host.id)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=welder.id, ability=0, targets=[host.id, incoming.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[host.id].zone == 'p1:battlefield'
    assert s.state.cards[incoming.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_animated_saga_cannot_be_sacrificed_until_equipment_prohibition_ends(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave7b_activation import ability_index

    s, alexios = setup(cards)
    act(s, 'p1', type='move', card_ids=[alexios.id], to={'player': 'p1', 'zone': 'exile'})
    saga = put(s, "Urza's Saga", 'battlefield')
    nissa = put(s, 'Nissa, Worldwaker', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=nissa.id, kind='loyalty', value=3)
    index = ability_index(s, nissa, 'becomes a 4/4')
    act(s, 'p1', type='activate_ability', card_id=nissa.id, ability=index, targets=[saga.id])
    settle(s)
    suit = put(s, 'Assault Suit', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[suit.id], to=saga.id)
    act(s, 'p1', type='set_counter', card_id=saga.id, kind='lore', value=3)
    act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    assert s.state.cards[saga.id].zone == 'p1:battlefield'
    act(s, 'p1', type='detach', card_ids=[suit.id])
    act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    assert s.state.cards[saga.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_declining_echo_payment_cannot_sacrifice_equipped_creature(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip

    s, alexios = setup(cards)
    act(s, 'p1', type='move', card_ids=[alexios.id], to={'player': 'p1', 'zone': 'exile'})
    rider = put(s, 'Avalanche Riders', 'battlefield')
    suit = put(s, 'Assault Suit', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[suit.id], to=rider.id)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == 'upkeep'
          and bool(s.state.zones.get('stack')) and s.state.rules.decision is None)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    until(s, lambda s: s.state.rules.decision is not None
          and s.state.rules.decision.resume.get('step') == 'pay_or_sacrifice')
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['sacrifice'])
    settle(s)
    assert s.state.cards[rider.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_emerge_cannot_sacrifice_alexios(cards):
    from app.game.errors import ActionError
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, alexios = setup(cards)
    spell = put(s, 'Elder Deep-Fiend', 'hand')
    ch = Plan(s.state, 'p1', s.cards, None).ch(spell)
    index = next(a.index for a in ch.abilities if 'emerge' in a.keywords)
    mana(s, C=5, U=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:{index}',
            cost_choices=[{'component': 0, 'cards': [alexios.id]}])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_offering_cannot_sacrifice_equipped_goblin(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, _ = setup(cards)
    goblin = put(s, 'Goblin Welder', 'battlefield')
    suit = put(s, 'Assault Suit', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[suit.id], to=goblin.id)
    patron = put(s, 'Patron of the Akki', 'hand')
    mana(s, C=5, R=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=patron.id, optional_costs=[f'{patron.id}:offering'])
    assert s.state.model_dump_json() == before
    roundtrip(s)
