"""CR 609.4 / 702.11: target as though hexproof were absent."""
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
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/hexproof_targeting_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Detection Tower', 'Nowhere to Run', 'Glaring Spotlight', 'Kaya, Bane of the Dead'])
def test_hexproof_targeting_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def field_permission(s, name):
    source = put(s, name, 'battlefield')
    if name == 'Kaya, Bane of the Dead':
        act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=7)
    return source


@pytest.mark.parametrize('name', ['Nowhere to Run', 'Glaring Spotlight', 'Kaya, Bane of the Dead'])
@pytest.mark.parametrize('source_leaves', [False, True])
def test_static_permission_allows_target_but_departure_restores_hexproof_on_resolution(cards, name, source_leaves):
    from tests.test_rules_bandmate_references import keyword

    s = table(cards, [name, 'Lightning Bolt'], ['Gladecover Scout'])
    source = field_permission(s, name)
    scout = put(s, 'Gladecover Scout', 'battlefield', 'p2')
    assert keyword(s, scout, 'hexproof')
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[scout.id])
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[scout.id].zone == ('p2:battlefield' if source_leaves else 'p2:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Nowhere to Run', 'Glaring Spotlight', 'Kaya, Bane of the Dead'])
@pytest.mark.parametrize('victim', ['Nimble Mongoose', 'Black Knight'])
def test_hexproof_permission_does_not_override_shroud_or_protection(cards, name, victim):
    from app.game.errors import ActionError

    s = table(cards, [name, 'Path to Exile'], [victim])
    field_permission(s, name)
    target = put(s, victim, 'battlefield', 'p2')
    spell = put(s, 'Path to Exile', 'hand')
    mana(s, W=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    roundtrip(s)


@pytest.mark.parametrize('name,third_allowed', [('Nowhere to Run', True), ('Glaring Spotlight', False), ('Kaya, Bane of the Dead', False)])
def test_static_permission_limits_which_players_spells_it_applies_to(cards, name, third_allowed):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority

    s = table(cards, [name], ['Gladecover Scout'], ['Lightning Bolt'])
    field_permission(s, name)
    scout = put(s, 'Gladecover Scout', 'battlefield', 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p3')
    wait_priority(s, 'p3')
    mana(s, 'p3', R=1)
    if third_allowed:
        act(s, 'p3', type='cast_spell', card_id=bolt.id, targets=[scout.id])
        settle(s)
        assert s.state.cards[scout.id].zone == 'p2:graveyard'
    else:
        with pytest.raises(ActionError):
            act(s, 'p3', type='cast_spell', card_id=bolt.id, targets=[scout.id])
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_detection_tower_tracks_later_creatures_and_its_permission_expires_at_end_of_turn(cards, source_leaves):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import keyword

    s = table(cards, ['Detection Tower', 'Lightning Bolt'], ['Gladecover Scout'])
    tower = put(s, 'Detection Tower', 'battlefield')
    to_phase(s, 'main1', turn=4)
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=tower.id, ability=1)
    settle(s)
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[tower.id], to={'player': 'p1', 'zone': 'graveyard'})
    scout = put(s, 'Gladecover Scout', 'battlefield', 'p2')
    assert keyword(s, scout, 'hexproof')
    # A target query must see the later entrant without removing its keyword.
    from app.rules.plan import Plan
    from app.rules.targets import legal_targets

    p = Plan(s.state, 'p1', s.cards, None)
    assert scout.id in legal_targets(p, 'creature', 'p1')
    act(s, 'p1', type='set_counter', card_id=scout.id, kind='+1/+1', value=3)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[scout.id])
    settle(s)
    assert s.state.cards[scout.id].damage == 3 and keyword(s, scout, 'hexproof')
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p1')
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[scout.id])
    roundtrip(s)


@pytest.mark.parametrize('name,allowed', [('Kaya, Bane of the Dead', True), ('Glaring Spotlight', False), ('Nowhere to Run', False)])
@pytest.mark.parametrize('shield', ['Leyline of Sanctity', 'Ivory Mask'])
def test_player_hexproof_scope_and_shroud(cards, name, allowed, shield):
    from app.game.errors import ActionError

    s = table(cards, [name, 'Lightning Bolt'], [shield])
    field_permission(s, name)
    put(s, shield, 'battlefield', 'p2')
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    if allowed and shield == 'Leyline of Sanctity':
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
        settle(s)
        assert s.state.players['p2'].life == 37
    else:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    roundtrip(s)


@pytest.mark.parametrize('present', [False, True])
def test_nowhere_suppresses_ward_at_the_target_event_and_leaving_does_not_retroactively_trigger_it(cards, present):
    s = table(cards, ['Nowhere to Run', 'Lightning Bolt'], ['Tolarian Terror'])
    nowhere = field_permission(s, 'Nowhere to Run') if present else None
    terror = put(s, 'Tolarian Terror', 'battlefield', 'p2')
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[terror.id])
    assert len(s.state.zones['stack']) == (1 if present else 2)
    if nowhere:
        act(s, 'p1', type='move', card_ids=[nowhere.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[terror.id].damage == (3 if present else 0)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Nowhere to Run', 'Glaring Spotlight', 'Kaya, Bane of the Dead'])
def test_permission_also_ignores_hexproof_from_a_quality(cards, name):
    from tests.test_rules_bandmate_references import keyword

    s = table(cards, [name, 'Swords to Plowshares'], ['Knight of Malice'])
    field_permission(s, name)
    knight = put(s, 'Knight of Malice', 'battlefield', 'p2')
    assert keyword(s, knight, 'hexproof from')
    spell = put(s, 'Swords to Plowshares', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[knight.id])
    settle(s)
    assert s.state.cards[knight.id].zone == 'p2:exile'
    roundtrip(s)


@pytest.mark.parametrize('name,allowed', [('Kaya, Bane of the Dead', True), ('Nowhere to Run', False), ('Glaring Spotlight', False)])
def test_kaya_also_applies_to_noncreature_permanents(cards, name, allowed):
    from app.game.errors import ActionError

    s = table(cards, [name, 'Stone Rain'], ['Lotus Field'])
    field_permission(s, name)
    land = put(s, 'Lotus Field', 'battlefield', 'p2')
    spell = put(s, 'Stone Rain', 'hand')
    mana(s, C=2, R=1)
    if allowed:
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[land.id])
        settle(s)
        assert s.state.cards[land.id].zone == 'p2:graveyard'
    else:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[land.id])
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_nowheres_own_entry_trigger_can_target_hexproof_but_rechecks_on_resolution(cards, source_leaves):
    s = table(cards, ['Nowhere to Run'], ['Gladecover Scout'])
    scout = put(s, 'Gladecover Scout', 'battlefield', 'p2')
    nowhere = put(s, 'Nowhere to Run', 'hand')
    mana(s, C=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=nowhere.id)
    settle(s)
    d = s.state.rules.decision
    assert d and scout.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[scout.id])
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[nowhere.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[scout.id].zone == ('p2:battlefield' if source_leaves else 'p2:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Vhati il-Dal', 'Turn to Frog', 'Abbot of Keral Keep', 'Celestial Colonnade'])
def test_targeting_template_does_not_intercept_other_until_end_of_turn_effects(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
