"""CR702.16k: player-specific protection follows each object's actual provenance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/player_protection_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='ppf', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())]
    s = three(cards, names, names, names)
    hold(s)
    return s


def cast(s, name, player='p1', *, targets=(), settle_after=True):
    source = put(s, name, 'hand', player)
    mana = {'True-Name Nemesis': {'U': 2, 'C': 1}, 'Lightning Bolt': {'R': 1}, 'Krenko, Mob Boss': {'R': 2, 'C': 2},
            'Pacifism': {'W': 1, 'C': 1}, 'Clever Impersonator': {'U': 2, 'C': 2},
            'Mind Rot': {'B': 1, 'C': 2}, 'Goblin Chainwhirler': {'R': 3}}[name]
    act(s, player, type='add_mana', player=player, mana=mana)
    act(s, player, type='cast_spell', card_id=source.id, targets=list(targets))
    if settle_after:
        settle(s)
    return s.state.cards[source.id]


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def nemesis(s, player='p1', protected='p2'):
    source = cast(s, 'True-Name Nemesis', player)
    d = s.state.rules.decision
    assert d is not None and protected in {o.id for o in d.options}, d
    answer(s, [protected])
    return s.state.cards[source.id]


def heritage(s, accepted=('p2',)):
    background = put(s, 'Noble Heritage', 'battlefield')
    creatures = {p: put(s, 'Grizzly Bears', 'battlefield', p) for p in ['p2', 'p3']}
    commander = cast(s, 'Krenko, Mob Boss')
    creatures['p1'] = commander
    for player in ['p1', 'p2', 'p3']:
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'counter_offer' and d.player == player, d
        answer(s, [creatures[player].id] if player in accepted else [])
    return background, commander, creatures


def priority(s, player):
    for _ in range(8):
        if s.state.rules.priority == player:
            return
        if s.state.rules.decision is not None and s.state.rules.decision.resume['step'] == 'commander_zone':
            answer(s, ['no'])
            continue
        assert not s.state.rules.decision
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('priority did not reach player')


@pytest.mark.parametrize('name', ['True-Name Nemesis', 'Noble Heritage'])
def test_canonical_cards_are_fully_supported(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_nemesis_chooses_player_and_prevents_only_that_players_targeting(cards):
    s = setup(cards)
    source = nemesis(s)
    assert 'protection' in Plan(s.state, 'p1', s.cards, None).ch(source).keywords
    priority(s, 'p2')
    with pytest.raises(ActionError, match='target|Target|legal'):
        cast(s, 'Lightning Bolt', 'p2', targets=[source.id])
    priority(s, 'p3')
    cast(s, 'Lightning Bolt', 'p3', targets=[source.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_heritage_protects_player_from_accepting_opponent_and_not_their_creatures(cards):
    s = setup(cards)
    _, commander, creatures = heritage(s)
    assert s.state.cards[creatures['p2'].id].counters['+1/+1'] == 2
    assert not s.state.cards[creatures['p3'].id].counters
    priority(s, 'p2')
    with pytest.raises(ActionError, match='target|Target|legal'):
        cast(s, 'Lightning Bolt', 'p2', targets=['p1'])
    cast(s, 'Lightning Bolt', 'p2', targets=[commander.id])
    assert s.state.cards[commander.id].zone == 'p1:graveyard'
    priority(s, 'p3')
    cast(s, 'Lightning Bolt', 'p3', targets=['p1'])
    assert s.state.players['p1'].life == 37
    roundtrip(s)


def test_current_damage_source_controller_differs_from_activated_ability_controller(cards):
    s = setup(cards)
    source = nemesis(s)
    pinger = put(s, 'Prodigal Pyromancer', 'battlefield')
    ability = next(a.index for a in Plan(s.state, 'p1', s.cards, None).ch(pinger).abilities if a.kind == 'activated')
    # Stage a permanent that has been controlled since before this turn.
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=pinger.id, ability=ability, targets=[source.id])
    act(s, 'p1', type='set_controller', card_ids=[pinger.id], player='p2')
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].damage == 0
    assert any('Protection prevents' in str(entry) for entry in s.state.log)
    roundtrip(s)


def test_nemesis_choice_is_an_id_even_when_two_players_have_the_same_name(cards):
    s = setup(cards)
    act(s, 'p1', type='rename_player', player='p2', name='Opponent')
    act(s, 'p1', type='rename_player', player='p3', name='Opponent')
    source = nemesis(s, protected='p2')
    ch = Plan(s.state, 'p1', s.cards, None).ch(source)
    assert any('player p2' in a.text for a in ch.abilities)
    priority(s, 'p3')
    cast(s, 'Lightning Bolt', 'p3', targets=[source.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_nemesis_loses_protection_with_abilities_and_regains_original_choice(cards):
    s = setup(cards)
    source = nemesis(s)
    humility = put(s, 'Humility', 'battlefield')
    assert 'protection' not in Plan(s.state, 'p1', s.cards, None).ch(source).keywords
    act(s, 'p1', type='move', card_ids=[humility.id], to={'zone': 'graveyard'})
    ch = Plan(s.state, 'p1', s.cards, None).ch(source)
    assert 'protection' in ch.keywords and any('player p2' in a.text for a in ch.abilities)
    roundtrip(s)


def test_copy_enters_with_a_new_player_choice_instead_of_donors_choice(cards):
    s = setup(cards)
    original = nemesis(s)
    copied = cast(s, 'Clever Impersonator')
    d = s.state.rules.decision
    assert original.id in {o.id for o in d.options}, d
    answer(s, [original.id])
    d = s.state.rules.decision
    assert d is not None and 'p3' in {o.id for o in d.options}, d
    answer(s, ['p3'])
    ch = Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[copied.id])
    assert any('player p3' in a.text for a in ch.abilities)
    assert ch.object_controller == 'p1' and ch.object_owner == 'p1'
    priority(s, 'p2')
    cast(s, 'Lightning Bolt', 'p2', targets=[copied.id])
    assert s.state.cards[copied.id].zone == 'p1:graveyard'
    assert s.state.cards[original.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_protection_stops_chosen_players_blockers_but_not_other_blockers(cards):
    from app.rules import combat

    s = setup(cards)
    source = nemesis(s)
    blockers = [put(s, 'Grizzly Bears', 'battlefield', p) for p in ['p2', 'p3']]
    view = Plan(s.state, 'p1', s.cards, None)
    assert 'protection' in combat.block_problem(s.state, blockers[0], view.ch(blockers[0]), source, view.ch(source), s.cards).lower()
    assert combat.block_problem(s.state, blockers[1], view.ch(blockers[1]), source, view.ch(source), s.cards) is None
    roundtrip(s)


def test_equipment_control_change_makes_protected_attachment_illegal(cards):
    s = setup(cards)
    source = nemesis(s)
    equipment = put(s, 'Bonesplitter', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[equipment.id], to=source.id)
    assert s.state.cards[equipment.id].attached_to == source.id
    act(s, 'p1', type='set_controller', card_ids=[equipment.id], player='p2')
    act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[equipment.id].attached_to is None
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_aura_control_change_makes_protected_attachment_go_to_graveyard(cards):
    s = setup(cards)
    source = nemesis(s)
    aura = cast(s, 'Pacifism', targets=[source.id])
    assert s.state.cards[aura.id].attached_to == source.id
    act(s, 'p1', type='set_controller', card_ids=[aura.id], player='p2')
    act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_noble_acceptance_with_replacement_to_zero_still_grants_protection(cards):
    s = setup(cards)
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p1')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p3')
    _, _, creatures = heritage(s)
    assert not s.state.cards[creatures['p2'].id].counters
    assert any(x['player'] == 'p1' and x['quality'] == 'player:p2' for x in s.state.rules.player_shields)
    roundtrip(s)


def test_noble_cannot_offer_a_prohibited_counter_payment(cards):
    s = setup(cards)
    put(s, 'Noble Heritage', 'battlefield')
    put(s, 'Solemnity', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Krenko, Mob Boss')
    assert s.state.rules.decision is None and not s.state.rules.player_shields
    roundtrip(s)


def test_self_acceptance_gives_counters_without_protection_from_self(cards):
    s = setup(cards)
    _, commander, _ = heritage(s, accepted=['p1'])
    assert s.state.cards[commander.id].counters['+1/+1'] == 2
    assert not s.state.rules.player_shields
    roundtrip(s)


def test_aura_entry_preview_uses_intended_controller_instead_of_graveyard_owner(cards):
    from app.rules import attachments

    s = setup(cards)
    source = nemesis(s)
    aura = put(s, 'Pacifism', 'graveyard', 'p3')
    view = Plan(s.state, 'p1', s.cards, None)
    assert attachments.host_problem(view, aura, source.id, controller='p2') is not None
    assert attachments.host_problem(view, aura, source.id, controller='p1') is None
    roundtrip(s)


def test_blinking_nemesis_creates_a_fresh_choice(cards):
    s = setup(cards)
    source = nemesis(s)
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
    source = nemesis(s, protected='p3')
    assert s.state.rules.object_id(source.id) != old
    priority(s, 'p2')
    cast(s, 'Lightning Bolt', 'p2', targets=[source.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_player_protection_does_not_prevent_loss_of_life(cards):
    s = setup(cards)
    heritage(s)
    purge = put(s, 'Psychic Purge', 'hand', 'p2')
    land = s.state.zones['p2:library'][0]
    act(s, 'p2', type='move', card_ids=[land], to={'zone': 'hand'})
    cast(s, 'Mind Rot', targets=['p2'])
    assert s.state.rules.decision is None
    assert s.state.cards[purge.id].zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 35
    roundtrip(s)


def test_departed_stolen_damage_source_uses_last_known_controller_not_graveyard_owner(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = nemesis(s, protected='p3')
    to_phase(s, 'main1', turn=2)
    goblin = cast(s, 'Goblin Chainwhirler', 'p2', settle_after=False)
    for _ in range(8):
        if s.state.cards[goblin.id].zone.endswith(':battlefield'):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.zones.get('stack')  # The real enter trigger is pending.
    act(s, 'p2', type='set_controller', card_ids=[goblin.id], player='p3')
    act(s, 'p3', type='move', card_ids=[goblin.id], to={'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].damage == 0
    assert s.state.cards[goblin.id].zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 39
    assert any('Protection prevents' in str(entry) for entry in s.state.log)
    roundtrip(s)


def test_noble_background_can_leave_without_ending_existing_protection(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    background, _, _ = heritage(s)
    act(s, 'p1', type='move', card_ids=[background.id], to={'zone': 'graveyard'})
    to_phase(s, 'main1', turn=2)
    assert s.state.rules.player_shields
    to_phase(s, 'main1', turn=4)
    assert not s.state.rules.player_shields
    roundtrip(s)


def test_owned_stolen_commander_grants_to_its_controller_and_keeps_that_beneficiary_after_departure(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[commander.id], player='p2')
    background = put(s, 'Noble Heritage', 'battlefield')
    creatures = {p: put(s, 'Grizzly Bears', 'battlefield', p) for p in ['p1', 'p3']}
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    act(s, 'p1', type='move', card_ids=[background.id], to={'zone': 'exile'})
    act(s, 'p2', type='move', card_ids=[commander.id], to={'zone': 'exile'})
    answer(s, [])
    assert s.state.rules.decision.player == 'p3'
    answer(s, [])
    assert s.state.rules.decision.player == 'p1'
    answer(s, [creatures['p1'].id])
    assert any(x['player'] == 'p2' and x['controller'] == 'p2' and x['quality'] == 'player:p1'
               for x in s.state.rules.player_shields)
    to_phase(s, 'main1', turn=4)
    assert s.state.rules.player_shields
    to_phase(s, 'main1', turn=5)
    assert not s.state.rules.player_shields
    roundtrip(s)


def test_copied_discard_damage_ability_uses_uncontrolled_card_owner_for_prevention(cards):
    s = setup(cards)
    heritage(s)
    tactics = put(s, 'Guerrilla Tactics', 'hand', 'p2')
    land = s.state.zones['p2:library'][0]
    act(s, 'p2', type='move', card_ids=[land], to={'zone': 'hand'})
    cast(s, 'Mind Rot', targets=['p2'])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and 'p3' in {o.id for o in d.options}, d
    assert 'p1' not in {o.id for o in d.options}
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['p3'])
    target = s.state.zones['stack'][-1]
    priority(s, 'p3')
    favor = put(s, 'Return the Favor', 'hand', 'p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'R': 2, 'C': 1})
    act(s, 'p3', type='cast_spell', card_id=favor.id, modes=[0], targets=[target])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p3' and 'p1' in {o.id for o in d.options}, d
    answer(s, ['p1'])
    assert s.state.cards[tactics.id].zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 40 and s.state.players['p3'].life == 36
    assert any('Protection prevents' in str(entry) for entry in s.state.log)
    roundtrip(s)


def test_player_protection_removes_aura_when_attachment_changes_to_protected_controller(cards):
    s = setup(cards)
    heritage(s)
    aura = put(s, 'Curse of Opulence', 'battlefield', 'p3')
    act(s, 'p3', type='attach', card_ids=[aura.id], to='p1')
    assert s.state.cards[aura.id].attached_player == 'p1'
    act(s, 'p3', type='set_controller', card_ids=[aura.id], player='p2')
    act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[aura.id].zone == 'p3:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('stage', ['nemesis', 'offer', 'replacement'])
def test_player_specific_protection_resumes_in_a_fresh_process(cards, tmp_path, stage):
    import subprocess
    import sys

    s = setup(cards)
    if stage == 'nemesis':
        source = cast(s, 'True-Name Nemesis')
    else:
        put(s, 'Noble Heritage', 'battlefield')
        source = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        put(s, 'Grizzly Bears', 'battlefield', 'p3')
        if stage == 'replacement':
            put(s, 'Doubling Season', 'battlefield', 'p2')
            put(s, 'Hardened Scales', 'battlefield', 'p2')
        cast(s, 'Krenko, Mob Boss')
        answer(s, [])
        answer(s, [source.id])
        if stage == 'replacement':
            answer(s, [])
            assert s.state.rules.decision.resume['step'] != 'counter_offer'
    roundtrip(s)
    saved = tmp_path / 'player-protection.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, source, stage = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
for _ in range(20):
    d = s.state.rules.decision
    if d is not None:
        ids = ['p2'] if stage == 'nemesis' else ([] if d.resume['step'] == 'counter_offer' else [d.options[0].id])
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ids})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
from app.rules.plan import Plan
from app.rules import targets, player_shields
plan = Plan(s.state, 'p1', repo, None)
if stage == 'nemesis':
    assert source not in targets.legal_targets(plan, 'creature', 'p2', None)
    assert source in targets.legal_targets(plan, 'creature', 'p3', None)
else:
    assert not player_shields.can_target(plan, 'p2', 'p1', None)
    assert player_shields.can_target(plan, 'p3', 'p1', None)
    n = s.state.cards[source].counters['+1/+1']
    assert n in (5, 6) if stage == 'replacement' else n == 2
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, stage],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('unpreventable', [False, True])
def test_combat_damage_obeys_player_protection_and_cannot_be_prevented(cards, unpreventable):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = nemesis(s)
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if unpreventable:
        put(s, 'Questing Beast', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p1'}])
    to_phase(s, 'declare_blockers', turn=2)
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': source.id, 'attacker_id': attacker.id}])
    to_phase(s, 'main2', turn=2)
    assert s.state.cards[attacker.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].zone == ('p1:graveyard' if unpreventable else 'p1:battlefield')
    roundtrip(s)
