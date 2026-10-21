"""As-transform emblems are atomic static instructions, not triggered abilities."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / 'fixtures/transform_emblem_cards.json').read_text())
NAME = 'Sephiroth, Fabled SOLDIER // Sephiroth, One-Winged Angel'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='ate', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [c['name'] for c in DATA], ['Stifle', 'Counterspell', 'Waxing Moon', 'Maskwood Nexus'])
    return s, put(s, NAME, 'battlefield')


def emblems(s, pid='p1'):
    from app.rules.designations import emblem_card

    return [c for c in s.state.cards.values() if c.controller == pid and emblem_card(c)]


def finish(s):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    settle(s)
    roundtrip(s)


def kill_token(s):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    wait_priority(s, 'p1')
    act(s, 'p1', type='create_token', player='p1', token={'name': 'Victim', 'type_line': 'Token Creature — Soldier',
                                                       'power': '1', 'toughness': '1', 'colors': []})
    victim = next(c for c in s.state.cards.values() if c.name == 'Victim' and c.zone == 'p1:battlefield')
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[victim.id])


def moon(s, target):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    wait_priority(s, 'p1')
    spell = put(s, 'Waxing Moon', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], target_counts=[1])
    finish(s)


def test_real_oracle_all_faces_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_natural_fourth_death_trigger_transforms_and_grants_one_emblem_without_retroactive_death(cards):
    s, seph = setup(cards)
    for _ in range(4):
        kill_token(s)
        finish(s)
    assert s.state.cards[seph.id].face == 1
    assert len(emblems(s)) == 1
    assert s.state.players['p1'].life == 44
    assert s.state.players['p2'].life == 36
    assert not s.state.rules.stack
    kill_token(s)
    finish(s)
    assert s.state.players['p1'].life == 45
    assert s.state.players['p2'].life == 35


def test_each_real_transform_into_back_grants_emblem_front_does_not(cards):
    from tests.test_rules_designations import put

    s, seph = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    moon(s, seph)
    assert s.state.cards[seph.id].face == 1 and len(emblems(s)) == 1
    moon(s, seph)
    assert s.state.cards[seph.id].face == 0 and len(emblems(s)) == 1
    moon(s, seph)
    assert s.state.cards[seph.id].face == 1 and len(emblems(s)) == 2
    kill_token(s)
    finish(s)
    assert s.state.players['p1'].life == 42
    assert s.state.players['p2'].life == 38


def test_emblem_survives_sephiroth_and_triggers_for_its_own_death(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put

    s, seph = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    moon(s, seph)
    from tests.test_rules_bandmate_references import mana, wait_priority

    wait_priority(s, 'p1')
    murder = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=murder.id, targets=[seph.id])
    finish(s)
    assert len(emblems(s)) == 1
    assert s.state.players['p1'].life == 41 and s.state.players['p2'].life == 39
    kill_token(s)
    finish(s)
    assert s.state.players['p1'].life == 42 and s.state.players['p2'].life == 38


def test_ability_loss_on_resulting_face_suppresses_as_transform_instruction(cards):
    from tests.test_rules_designations import put

    s, seph = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    put(s, 'Dress Down', 'battlefield')
    moon(s, seph)
    assert s.state.cards[seph.id].face == 1 and not emblems(s)


def test_getting_emblem_is_not_an_extra_stack_trigger(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_copy import resolve_top
    from tests.test_rules_designations import put, roundtrip

    s, seph = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    spell = put(s, 'Waxing Moon', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[seph.id], target_counts=[1])
    resolve_top(s)
    assert s.state.cards[seph.id].face == 1 and len(emblems(s)) == 1
    assert not s.state.rules.stack
    roundtrip(s)


def test_copy_token_entering_with_back_face_does_not_get_emblem_then_can_transform(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    s, seph = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    moon(s, seph)
    wait_priority(s, 'p1')
    duplicate = put(s, "Irenicus's Vile Duplication", 'hand')
    mana(s, C=3, U=1)
    act(s, 'p1', type='cast_spell', card_id=duplicate.id, targets=[seph.id])
    finish(s)
    copies = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield' and c.card_id == seph.card_id]
    assert len(copies) == 1
    copy = copies[0]
    assert copy.face == 1 and len(emblems(s)) == 1
    moon(s, copy)
    assert s.state.cards[copy.id].face == 0 and len(emblems(s)) == 1
    from tests.test_rules_wave6c_tokens_pumps import chars

    assert 'Legendary' not in chars(s, copy).supertypes and 'flying' in chars(s, copy).keywords
    moon(s, copy)
    assert s.state.cards[copy.id].face == 1 and len(emblems(s)) == 2
    assert 'Legendary' not in chars(s, copy).supertypes and 'flying' in chars(s, copy).keywords


def test_becoming_permanents_controller_gets_emblem_not_old_trigger_controller(cards):
    from tests.game_helpers import act
    from tests.test_rules_copy import resolve_top

    s, seph = setup(cards)
    for _ in range(3):
        kill_token(s)
        finish(s)
    kill_token(s)
    resolve_top(s)  # Bolt kills the fourth creature; Sephiroth's triggered ability now awaits its target.
    d = s.state.rules.decision
    if d is not None:
        assert 'p2' in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    assert any(entry.source_card == seph.id and entry.controller == 'p1' for entry in s.state.rules.stack.values())
    act(s, 'p1', type='set_controller', card_ids=[seph.id], player='p2')
    finish(s)
    assert s.state.cards[seph.id].face == 1
    assert not emblems(s, 'p1') and len(emblems(s, 'p2')) == 1
    assert s.state.players['p1'].life == 44 and s.state.players['p2'].life == 36


def test_continuing_copy_effect_suppresses_printed_back_face_instruction(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, seph = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Mirrorweave', 'hand')
    mana(s, C=2, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    finish(s)
    assert chars(s, seph).name == 'Grizzly Bears'
    moon(s, seph)
    assert s.state.cards[seph.id].face == 1
    assert chars(s, seph).name == 'Grizzly Bears' and not emblems(s)


def test_single_faced_copy_of_back_face_cannot_transform_or_get_emblem(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, seph = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    moon(s, seph)
    wait_priority(s, 'p1')
    double = put(s, 'Spark Double', 'hand')
    mana(s, C=3, U=1)
    act(s, 'p1', type='cast_spell', card_id=double.id)
    finish(s)
    assert chars(s, double).name == 'Sephiroth, One-Winged Angel'
    moon(s, double)
    assert s.state.cards[double.id].face == 0 and len(emblems(s)) == 1


def test_ordinary_single_faced_token_is_not_transformable(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put

    s, _ = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    act(s, 'p1', type='create_token', player='p1', token={'name': 'Ordinary', 'type_line': 'Token Creature — Soldier',
                                                       'power': '1', 'toughness': '1', 'colors': []})
    token = next(c for c in s.state.cards.values() if c.name == 'Ordinary')
    moon(s, token)
    assert s.state.cards[token.id].face == 0 and not emblems(s)
