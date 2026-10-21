"""Cumulative exile thresholds reset per opponent; Dream's free casts retain normal timing."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

AMULET = 'Unstable Amulet'
RISE = 'Furious Rise'
FOES = 'Superior Foes of Spider-Man'
NAMES = [AMULET, RISE, FOES]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/next_linked_exile_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='emt', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def setup(cards, name=AMULET, extra=()):
    s = table(cards, [name, 'Grizzly Bears', 'Lightning Bolt', 'Questing Beast', *extra], ['Lightning Bolt', 'Opt'], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, name, 'battlefield')
    act(s, 'p1', type='resource', player='p1', key='energy', delta=20)
    settle(s)
    return s, source


def top(s, name, pid='p1'):
    obj = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name)
    act(s, pid, type='move', card_ids=[obj.id], to={'player': pid, 'zone': 'library'}, position='top')
    return obj.id


def activate(s, source, pid='p1'):
    from tests.test_rules_wave7b_activation import ability_index

    if s.state.cards[source.id].tapped:
        act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, pid)
    act(s, pid, type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'Exile the top'))
    settle(s)


def refused(s, cid, pid='p1'):
    wait_priority(s, pid)
    with pytest.raises(ActionError):
        act(s, pid, type='cast_spell', card_id=cid)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_amulet_actual_second_exile_ends_old_permission_and_cast_rider(cards):
    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    assert s.state.cards[bear].zone == 'p1:exile'
    bolt = top(s, 'Lightning Bolt')
    activate(s, source)
    assert {p.card for p in s.state.rules.permissions} == {bolt}
    refused(s, bear)
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 36 and s.state.players['p3'].life == 39
    roundtrip(s)


def test_old_permission_survives_cleanup_source_departure_and_blink(cards):
    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    bolt = top(s, 'Lightning Bolt')
    activate(s, source)
    assert {p.card for p in s.state.rules.permissions} == {bear, bolt}
    to_phase(s, 'main1', turn=4)
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=bear)
    settle(s)
    assert s.state.cards[bear].zone == 'p1:battlefield'
    roundtrip(s)


def test_empty_library_activation_does_not_end_previous_permission(cards):
    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    rest = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=rest, to={'player': 'p1', 'zone': 'graveyard'})
    activate(s, source)
    assert {p.card for p in s.state.rules.permissions} == {bear}
    roundtrip(s)


def test_furious_rise_real_intervening_if_and_second_turn_revoke(cards):
    s, source = setup(cards, RISE)
    beast = put(s, 'Questing Beast', 'battlefield')
    bear = top(s, 'Grizzly Bears')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert {p.card for p in s.state.rules.permissions} == {bear}
    to_phase(s, 'main1', turn=4)
    bolt = top(s, 'Lightning Bolt')
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='move', card_ids=[beast.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[bolt].zone == 'p1:library'
    assert {p.card for p in s.state.rules.permissions} == {bear}
    act(s, 'p1', type='move', card_ids=[beast.id], to={'player': 'p1', 'zone': 'battlefield'})
    to_phase(s, 'end', turn=7)
    settle(s)
    assert s.state.cards[bear].zone == 'p1:exile'
    assert bear not in {p.card for p in s.state.rules.permissions}
    roundtrip(s)


def test_amulet_permission_plays_land_with_normal_land_limit(cards):
    s, source = setup(cards)
    forest = top(s, 'Forest')
    activate(s, source)
    act(s, 'p1', type='play_land', card_id=forest)
    second = top(s, 'Forest')
    activate(s, source)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=second)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='play_land', card_id=second)
    assert s.state.cards[second].zone == 'p1:battlefield'
    roundtrip(s)


def test_amulet_cast_permission_requires_full_mana_and_ordinary_timing(cards):
    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    refused(s, bear)
    to_phase(s, 'end', turn=1)
    mana(s, C=1, G=1)
    refused(s, bear)
    roundtrip(s)


def test_amulet_controller_change_new_players_exile_does_not_end_old_duration(cards):
    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, 'p2', type='resource', player='p2', key='energy', delta=5)
    bolt = top(s, 'Lightning Bolt', 'p2')
    activate(s, source, 'p2')
    assert {(p.player, p.card) for p in s.state.rules.permissions} == {('p1', bear), ('p2', bolt)}
    mana(s, C=1, G=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bear)
    settle(s)
    assert s.state.cards[bear].zone == 'p1:battlefield'
    roundtrip(s)


def test_queued_old_controller_activation_expires_only_old_players_permission(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    bolt = top(s, 'Lightning Bolt')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'Exile the top'))
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert {(p.player, p.card) for p in s.state.rules.permissions} == {('p1', bolt)}
    refused(s, bear)
    roundtrip(s)


def test_source_leaves_with_second_activation_pending_still_expires_old_duration(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    bolt = top(s, 'Lightning Bolt')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'Exile the top'))
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert {p.card for p in s.state.rules.permissions} == {bolt}
    refused(s, bear)
    roundtrip(s)


def test_native_skill_borrower_distinct_acquired_link_scopes_do_not_revoke_each_other(cards):
    s, _ = setup(cards, 'Skill Borrower', extra=(AMULET, AMULET))
    borrower = next(c for c in s.state.cards.values() if c.name == 'Skill Borrower')
    to_phase(s, 'main1', turn=4)
    amulets = [c.id for c in s.state.cards.values() if c.name == AMULET]
    for cid in amulets:
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'library'}, position='top')
        activate(s, borrower)
    perms = s.state.rules.permissions
    assert {p.card for p in perms} == set(amulets)
    assert len({p.stop_on_linked_exile for p in perms}) == 2
    assert all('|borrowed:' in p.stop_on_linked_exile for p in perms)
    roundtrip(s)


def test_superior_foes_optional_exile_decline_preserves_previous_permission(cards):
    from tests.test_rules_conditionals import until

    s, source = setup(cards, FOES, extra=('Questing Beast',))
    bear = top(s, 'Grizzly Bears')
    beast = put(s, 'Questing Beast', 'hand')
    mana(s, C=4, G=4)
    act(s, 'p1', type='cast_spell', card_id=beast.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'may'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    assert {p.card for p in s.state.rules.permissions} == {bear}
    act(s, 'p1', type='move', card_ids=[beast.id], to={'player': 'p1', 'zone': 'hand'})
    bolt = top(s, 'Lightning Bolt')
    wait_priority(s, 'p1')
    mana(s, C=2, G=2)
    act(s, 'p1', type='cast_spell', card_id=beast.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert s.state.cards[bolt].zone == 'p1:library'
    assert {p.card for p in s.state.rules.permissions} == {bear}
    roundtrip(s)


def test_original_object_exile_leave_return_cannot_use_stale_permission(cards):
    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    act(s, 'p1', type='move', card_ids=[bear], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[bear], to={'player': 'p1', 'zone': 'exile'})
    mana(s, C=1, G=1)
    refused(s, bear)
    roundtrip(s)


def test_countered_second_activation_does_not_exile_or_end_permission(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source = setup(cards, extra=('Stifle',))
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    bolt = top(s, 'Lightning Bolt')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'Exile the top'))
    pending = s.state.zones['stack'][-1]
    stifle = put(s, 'Stifle', 'hand')
    mana(s, U=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=stifle.id, targets=[pending])
    settle(s)
    assert s.state.cards[bolt].zone == 'p1:library'
    assert {p.card for p in s.state.rules.permissions} == {bear}
    roundtrip(s)


def test_two_queued_activations_expire_in_resolution_order(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    bolt = top(s, 'Lightning Bolt')
    for _ in range(2):
        act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, s.state.cards[source.id], 'Exile the top'))
    beast = top(s, 'Questing Beast')
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in [bear, bolt, beast])
    assert {p.card for p in s.state.rules.permissions} == {bolt}
    roundtrip(s)


def test_cold_saved_permission_then_second_activation_expires_original(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_wave7b_activation import ability_index

    s, source = setup(cards)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    bolt = top(s, 'Lightning Bolt')
    ability = ability_index(s, s.state.cards[source.id], 'Exile the top')
    saved = tmp_path / 'next-exile.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, source, ability, old, new = sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.perform('p1',{'type':'tap','card_ids':[source],'tapped':False})
s.perform('p1',{'type':'activate_ability','card_id':source,'ability':int(ability)})
for _ in range(60):
    if not s.state.zones.get('stack'):break
    s.perform(s.state.rules.priority,{'type':'pass_priority'})
else:raise AssertionError('did not settle')
assert {p.card for p in s.state.rules.permissions}=={new}
assert s.state.cards[old].zone=='p1:exile'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), source.id, str(ability), bear, bolt],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def borrowed_exile(s, source):
    from app.rules import abilities_of
    from app.rules.plan import Plan

    return next(a for a in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[source.id]).abilities
                if a.index >= abilities_of.BORROWED and 'Exile the top' in a.text)


def legacy_scope(ab):
    import re

    from app.rules import abilities_of

    return abilities_of._scope_hash([re.sub(r'[a-zA-Z0-9_-]+\.(\d+)', r'object.\1', x) for x in ab.borrowed_origin[:-1]])


def test_unambiguous_public_legacy_saved_link_is_reused_before_announcement(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from app.rules import abilities_of, scripts

    s, source = setup(cards, 'Drana and Linvala', extra=('March of the Machines', AMULET))
    amulet = next(c for c in s.state.cards.values() if c.name == AMULET)
    act(s, 'p1', type='move', card_ids=[amulet.id], to={'player': 'p2', 'zone': 'battlefield'})
    put(s, 'March of the Machines', 'battlefield')
    settle(s)
    to_phase(s, 'main1', turn=4)
    ab = borrowed_exile(s, source)
    old = legacy_scope(ab)
    modern = abilities_of.link_scope(ab)
    assert old != modern and all('.0' not in x for x in ab.borrowed_origin)
    bear = top(s, 'Grizzly Bears')
    activate(s, source)
    key = next(iter(s.state.rules.exiled_with))
    data = s.state.model_dump(mode='json')
    legacy_key = key.split('|borrowed:')[0] + '|borrowed:' + old
    data['rules']['exiled_with'][legacy_key] = data['rules']['exiled_with'].pop(key)
    data['rules']['permissions'][0]['stop_on_linked_exile'] = legacy_key
    s = GameSession(GameState.model_validate(data), cards=cards)
    ab = borrowed_exile(s, source)
    assert abilities_of.link_scope(ab) == old
    from app.rules.plan import Plan
    definition = scripts.define(ab, Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]))
    assert definition['effects'][0]['scope'] == old
    bolt = top(s, 'Lightning Bolt')
    activate(s, source)
    assert {p.card for p in s.state.rules.permissions} == {bolt}
    assert s.state.cards[bear].zone == 'p1:exile'
    roundtrip(s)


def test_ambiguous_zero_legacy_scope_never_absorbs_new_hidden_donor(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from app.rules import abilities_of

    s, source = setup(cards, 'Skill Borrower', extra=(AMULET, AMULET))
    to_phase(s, 'main1', turn=4)
    donors = [c.id for c in s.state.cards.values() if c.name == AMULET]
    act(s, 'p1', type='move', card_ids=[donors[0]], to={'player': 'p1', 'zone': 'library'}, position='top')
    old = legacy_scope(borrowed_exile(s, source))
    activate(s, source)
    data = s.state.model_dump(mode='json')
    key = next(iter(data['rules']['exiled_with']))
    legacy_key = key.split('|borrowed:')[0] + '|borrowed:' + old
    data['rules']['exiled_with'][legacy_key] = data['rules']['exiled_with'].pop(key)
    data['rules']['permissions'][0]['stop_on_linked_exile'] = legacy_key
    s = GameSession(GameState.model_validate(data), cards=cards)
    act(s, 'p1', type='move', card_ids=[donors[1]], to={'player': 'p1', 'zone': 'library'}, position='top')
    assert abilities_of.link_scope(borrowed_exile(s, source)) != old
    activate(s, source)
    assert {p.card for p in s.state.rules.permissions} == set(donors)
    roundtrip(s)


def test_real_private_renumber_preserves_modern_scope_hints_and_saved_links(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from app.rules import abilities_of

    s, source = setup(cards, 'Drana and Linvala', extra=('March of the Machines', AMULET))
    donor = next(c for c in s.state.cards.values() if c.name == AMULET)
    act(s, 'p1', type='move', card_ids=[donor.id], to={'player': 'p2', 'zone': 'battlefield'})
    put(s, 'March of the Machines', 'battlefield')
    settle(s)
    to_phase(s, 'main1', turn=4)
    bear = top(s, 'Grizzly Bears')
    ab = borrowed_exile(s, source)
    old_scope = abilities_of.link_scope(ab)
    activate(s, source)
    old_source, old_donor = source.id, donor.id
    s.perform('p1', {'type': 'renumber', 'card_ids': [old_source, old_donor]}, trusted=True)
    assert old_source not in s.state.cards and old_donor not in s.state.cards
    source = next(c for c in s.state.cards.values() if c.name == 'Drana and Linvala')
    donor = next(c for c in s.state.cards.values() if c.name == AMULET)
    assert source.borrow_identity == old_source and donor.borrow_identity == old_donor
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    ab_after = borrowed_exile(s, source)
    assert ab.index == ab_after.index and abilities_of.link_scope(ab_after) == old_scope
    before = s.state.model_dump(mode='json')
    view = s.view('p1')
    assert s.state.model_dump(mode='json') == before
    assert {'card_id': source.id, 'ability': ab.index} in view['rules']['hints']['activatable']
    public = json.dumps(view)
    assert 'borrow_identity' not in public and old_source not in public and old_donor not in public
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    assert abilities_of.link_scope(borrowed_exile(s, source)) == old_scope
    bolt = top(s, 'Lightning Bolt')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ab.index)
    settle(s)
    assert s.state.cards[bear].zone == 'p1:exile' and {p.card for p in s.state.rules.permissions} == {bolt}
    roundtrip(s)


def test_initial_zero_incarnation_donor_scope_survives_real_renumber(cards):
    from app.rules import abilities_of

    s, source = setup(cards, 'Skill Borrower', extra=(AMULET,))
    to_phase(s, 'main1', turn=4)
    donor = top(s, AMULET)
    ab = borrowed_exile(s, source)
    before = abilities_of.link_scope(ab)
    s.perform('p1', {'type': 'renumber', 'card_ids': [donor]}, trusted=True)
    new = next(c.id for c in s.state.cards.values() if c.name == AMULET)
    assert new != donor and s.state.cards[new].borrow_identity == donor
    assert abilities_of.link_scope(borrowed_exile(s, source)) == before
    assert {'card_id': source.id, 'ability': ab.index} in s.view('p1')['rules']['hints']['activatable']
    activate(s, source)
    assert {p.card for p in s.state.rules.permissions} == {new}
    roundtrip(s)


def test_new_physical_token_split_resets_private_borrow_identity(cards):
    s, source = setup(cards, 'Skill Borrower')
    act(s, 'p1', type='copy_card', card_id=source.id)
    token = next(c for c in s.state.cards.values() if c.name == 'Skill Borrower' and c.is_token)
    act(s, 'p1', type='stack_adjust', card_id=token.id, delta=1)
    old = token.id
    s.perform('p1', {'type': 'renumber', 'card_ids': [old]}, trusted=True)
    token = next(c for c in s.state.cards.values() if c.name == 'Skill Borrower' and c.is_token)
    assert token.borrow_identity == old
    act(s, 'p1', type='split_stack', card_id=token.id, count=1)
    clone = next(c for c in s.state.cards.values() if c.is_token and c.name == 'Skill Borrower' and c.id != token.id)
    assert clone.borrow_identity is None and clone.id != old
    roundtrip(s)
