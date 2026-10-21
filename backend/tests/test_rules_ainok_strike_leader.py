"""Ainok aggregate attack trigger and fixed-player attacking token replacements.

CR 508.4: put attacking does not declare an attacker; forced player excludes
planeswalkers/battles. CR 903.3: commander designation is not copiable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave5c_combat import declare, to_attack
from tests.test_rules_wave30m_durations import to_phase

NAME = "Ainok Strike Leader"
PARTNERS = ["Rograkh, Son of Rohgahh", "Kediss, Emberclaw Familiar"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures/ainok_strike_leader_cards.json").read_text())):
        base[c["name"]] = card(
            c["name"], set_code="ain", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, extra=()):
    s = table(cards, [NAME, *PARTNERS, "Grizzly Bears", *extra], ["Jace Beleren"], [])
    source = put(s, NAME, "battlefield")
    partners = [put(s, n, "battlefield") for n in PARTNERS]
    for c in partners:
        act(s, "p1", type="set_commander", card_id=c.id, value=True)
    bear = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", turn=4)
    return s, source, partners, bear


def goblins(s):
    return [
        c for c in s.state.cards.values() if c.token and c.name == "Goblin" and c.zone == "p1:battlefield"
    ]


@pytest.mark.parametrize("attackers", ["self", "partner", "partners", "all", "neither"])
def test_aggregate_self_or_owned_commander_attack_once(cards, attackers):
    s, source, partners, bear = setup(cards)
    selected = {
        "self": [source],
        "partner": partners[:1],
        "partners": partners,
        "all": [source, *partners],
        "neither": [bear],
    }[attackers]
    to_attack(s, 4)
    declare(s, *[(c, "p2") for c in selected])
    settle(s)
    made = goblins(s)
    assert len(made) == (0 if attackers == "neither" else 2)
    assert {c.attacking.id for c in made} == ({"p2", "p3"} if made else set())
    assert all(c.tapped for c in made)
    roundtrip(s)


def test_source_need_not_attack_when_commander_attacks(cards):
    s, source, partners, _ = setup(cards)
    to_attack(s, 4)
    declare(s, (partners[0], "p2"))
    settle(s)
    assert source.attacking is None
    assert len(goblins(s)) == 2
    roundtrip(s)


def test_departed_source_trigger_retains_fixed_opponents(cards):
    s, source, _, _ = setup(cards)
    to_attack(s, 4)
    declare(s, (source, "p2"))
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    settle(s)
    assert {c.attacking.id for c in goblins(s)} == {"p2", "p3"}
    roundtrip(s)




def test_card_is_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('replacement,name,n', [
    ('Parallel Lives', 'Goblin', 4),
    ('Divine Visitation', 'Angel', 2),
    ('Chatterfang, Squirrel General', 'Squirrel', 2),
])
def test_replacements_keep_fixed_player_recipients(cards, replacement, name, n):
    s, source, _, _ = setup(cards, [replacement])
    put(s, replacement, 'battlefield')
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    settle(s)
    made = [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == 'p1:battlefield']
    assert len(made) == n
    assert [c.attacking.id for c in made].count('p2') == n // 2
    assert [c.attacking.id for c in made].count('p3') == n // 2
    assert all(c.tapped for c in made)
    roundtrip(s)


def test_trigger_controller_stays_same_after_source_control_changes(cards):
    s, source, _, _ = setup(cards)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert {c.attacking.id for c in goblins(s)} == {'p2', 'p3'}
    assert not [c for c in s.state.cards.values() if c.is_token and c.controller == 'p2']
    roundtrip(s)


def test_opponent_owned_commander_not_your_commander(cards):
    s = table(cards, [NAME], [PARTNERS[0]], [])
    put(s, NAME, 'battlefield')
    enemy = put(s, PARTNERS[0], 'battlefield', 'p2')
    act(s, 'p2', type='set_commander', card_id=enemy.id, value=True)
    act(s, 'p1', type='set_controller', card_ids=[enemy.id], player='p1')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (enemy, 'p2'))
    settle(s)
    assert not goblins(s)
    roundtrip(s)


def test_fixed_recipient_never_offers_planeswalker_choice(cards):
    s, source, _, _ = setup(cards)
    walker = put(s, 'Jace Beleren', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    to_attack(s, 4)
    declare(s, (source, walker.id))
    settle(s)
    assert {c.attacking.id for c in goblins(s)} == {'p2', 'p3'}
    assert s.state.rules.decision is None
    roundtrip(s)


def test_replacement_order_saved_before_answer_keeps_each_request_recipient(cards):
    from tests.test_rules_wave5c_combat import until

    s, source, _, _ = setup(cards, ['Parallel Lives', 'Peregrin Took'])
    put(s, 'Parallel Lives', 'battlefield')
    put(s, 'Peregrin Took', 'battlefield')
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'replace_order')
    roundtrip(s)
    settle(s)
    made = goblins(s)
    assert len(made) == 4
    assert [c.attacking.id for c in made].count('p2') == 2
    assert [c.attacking.id for c in made].count('p3') == 2
    assert all(c.attacking is None for c in s.state.cards.values() if c.name == 'Food' and c.is_token)
    roundtrip(s)


def test_moonlight_prevents_entering_tokens_without_attacking_ghosts(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source, _, _ = setup(cards, ['Hallowed Moonlight'])
    moonlight = put(s, 'Hallowed Moonlight', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=moonlight.id)
    settle(s)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    settle(s)
    assert not goblins(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.attacking is not None]
    roundtrip(s)


def test_changed_token_creator_cannot_attack_during_another_players_turn(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s = table(cards, [NAME], ['Crafty Cutpurse'], [])
    source = put(s, NAME, 'battlefield')
    to_phase(s, 'main1', turn=4)
    thief = put(s, 'Crafty Cutpurse', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', C=3, U=1)
    act(s, 'p2', type='cast_spell', card_id=thief.id)
    settle(s)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    settle(s)
    made = [c for c in s.state.cards.values() if c.is_token and c.name == 'Goblin']
    assert len(made) == 2
    assert all(c.controller == 'p2' and c.attacking is None and c.tapped for c in made)
    roundtrip(s)


def test_sacrifice_ability_still_grants_indestructible_to_tokens(cards):
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index

    s, source, _, _ = setup(cards)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    settle(s)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id,
        ability=ability_index(s, source, 'indestructible'))
    settle(s)
    assert source.zone == 'p1:graveyard'
    plan = Plan(s.state, 'p1', s.cards, None)
    assert all('indestructible' in plan.ch(c).keywords for c in goblins(s))
    roundtrip(s)


def test_token_entry_choices_keep_recipients_across_json_resume_and_apnap(cards):
    import random

    from app.game.state import GameState
    from app.rules import replace
    from app.rules.plan import Plan

    s, _, _, _ = setup(cards)
    to_attack(s, 4)
    # The shared batch hook also supports tokens whose own actual Oracle text
    # asks an entry choice. Ainok's Goblins themselves have no such choice.
    actual = cards.resolve('Adaptive Automaton')
    spec = {'name': actual['name'], 'type_line': actual['type_line'], 'power': '2', 'toughness': '2',
            'colors': [], 'text': actual['oracle_text']}
    plan = Plan(s.state, 'p1', cards, random.Random(11))
    requests = [('p2', spec, 1, None, True), ('p1', spec, 1, None, True), ('p1', spec, 1, None, True)]
    assert replace.create_token_batch(plan, requests, ctx=None, bind=None, then={'do': 'noop'},
                                      recipient_refs=['p1', 'p2', 'p3']) is None
    order = []
    for _ in range(3):
        plan.state = GameState.model_validate_json(plan.state.model_dump_json())
        d = plan.rules.decision
        assert d is not None and d.resume['step'] == 'replace_order'
        assert d.resume['request']['recipient_refs'] == ['p1', 'p2', 'p3']
        order.append(d.player)
        plan.rules.decision = None
        replace.resume_order(plan, d, [d.options[0].id])
    assert order == ['p1', 'p1', 'p2']
    assert plan.rules.decision is None
    made = [c for c in plan.state.cards.values() if c.is_token and c.name == 'Adaptive Automaton']
    assert len(made) == 3
    assert {c.attacking.id for c in made if c.controller == 'p1'} == {'p2', 'p3'}
    assert all(c.attacking is None for c in made if c.controller == 'p2')


@pytest.mark.parametrize('copied,expected', [(PARTNERS[0], 0), (NAME, 2)])
def test_noncommander_copy_has_only_its_own_attack_identity(cards, copied, expected):
    from tests.test_rules_copy import cast_clone

    s = table(cards, [NAME, 'Clone'], [PARTNERS[0]], [])
    source = put(s, NAME, 'battlefield')
    commander = put(s, PARTNERS[0], 'battlefield', 'p2')
    act(s, 'p2', type='set_commander', card_id=commander.id, value=True)
    to_phase(s, 'main1', turn=1)
    clone = cast_clone(s, pick=source.id if copied == NAME else commander.id)
    settle(s)
    assert s.state.cards[clone.id].commander_key is None
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (clone, 'p2'))
    settle(s)
    assert len(goblins(s)) == expected
    roundtrip(s)


def test_all_opponents_tokens_are_one_simultaneous_creation_batch(cards):
    s, source, _, _ = setup(cards, ['Marneus Calgar'])
    put(s, 'Marneus Calgar', 'battlefield')
    to_attack(s, 4)
    before = len(s.state.zones['p1:hand'])
    declare(s, (source, 'p2'))
    settle(s)
    assert len(goblins(s)) == 2
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def test_nonactive_player_copy_creates_tapped_tokens_without_attacking(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import until

    s = table(cards, [NAME], ['Return the Favor'], [])
    source = put(s, NAME, 'battlefield')
    spell = put(s, 'Return the Favor', 'hand', 'p2')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    until(s, lambda s: any(s.state.cards[cid].ability is not None and s.state.cards[cid].name == NAME
                          for cid in s.state.zones.get('stack', [])))
    trigger = next(cid for cid in s.state.zones['stack']
                   if s.state.cards[cid].ability is not None and s.state.cards[cid].name == NAME)
    wait_priority(s, 'p2')
    mana(s, pid='p2', C=1, R=2)
    act(s, 'p2', type='cast_spell', card_id=spell.id, modes=[0], targets=[trigger])
    settle(s)
    copied = [c for c in s.state.cards.values() if c.is_token and c.name == 'Goblin' and c.controller == 'p2']
    assert len(copied) == 2
    assert all(c.tapped and c.attacking is None for c in copied)
    assert {c.attacking.id for c in goblins(s)} == {'p2', 'p3'}
    roundtrip(s)


def test_departed_opponent_is_not_a_creation_recipient(cards):
    s, source, _, _ = setup(cards)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    act(s, 'p1', type='remove_player', player='p3')
    settle(s)
    assert len(goblins(s)) == 1
    assert goblins(s)[0].attacking.id == 'p2'
    roundtrip(s)
