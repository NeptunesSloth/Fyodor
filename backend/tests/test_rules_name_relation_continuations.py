"""Canonical name relations bind exact public history and linked incarnations."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

NAME = "Twinning Glass"
DATA = Path(__file__).parent / 'fixtures/name_relation_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='csc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Grizzly Bears', 'Lightning Bolt', 'Forest', 'Lightning Bolt', 'Giant Growth', 'Yenna, Redtooth Regent', 'Kami of Ancient Law', 'Pacifism', 'Hint of Insanity', 'Hint of Insanity']
    s = three(cards, names, names, names)
    hold(s)
    return s




def activate(s, source, needle=None):
    from tests.test_rules_player_protection import priority
    from tests.test_rules_wave7b_activation import ability_index
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id,
        ability=ability_index(s, source, needle) if needle else 0)
    settle(s)


def choose(s, ids=(), **kw):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=list(ids), **kw)
    settle(s)


def test_twinning_glass_canonical_full(cards):
    result = coverage.of_card_data(cards.resolve('Twinning Glass'))
    assert result.level == 'FULL', result.manual_parts


def test_twinning_uses_another_players_cast_name_after_spell_left_stack(cards):
    s = setup(cards)
    source = put(s, 'Twinning Glass', 'battlefield')
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2')
    assert s.state.rules.turn_log.casts[-1].names == ['Lightning Bolt']
    selected = put(s, 'Lightning Bolt', 'hand')
    activate(s, source)
    d = s.state.rules.decision
    assert d is not None and any(o.id == selected.id for o in d.options)
    choose(s, [selected.id])
    if s.state.rules.decision is not None:
        choose(s, ['p3'])
    assert s.state.players['p3'].life == 34
    assert s.state.cards[selected.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_twinning_with_no_cast_names_allows_only_decline(cards):
    s = setup(cards)
    source = put(s, 'Twinning Glass', 'battlefield')
    put(s, 'Lightning Bolt', 'hand')
    activate(s, source)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and not d.options
    choose(s)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_twinning_explicitly_restores_public_name_missing_from_an_older_save(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    source = put(s, 'Twinning Glass', 'battlefield')
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2')
    data = s.state.model_dump(mode='json')
    for receipt in data['rules']['turn_log']['casts']:
        receipt.pop('names')
    s = GameSession(GameState.model_validate(data), cards=cards)
    selected = put(s, 'Lightning Bolt', 'hand')
    activate(s, s.state.cards[source.id])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and 'Restore public history' in d.prompt
    choose(s, name='Lightning Bolt')
    assert s.state.rules.turn_log.casts[-1].names == ['Lightning Bolt']
    d = s.state.rules.decision
    assert d is not None and any(o.id == selected.id for o in d.options)
    choose(s)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Retraced Image', 'Mitotic Manipulation', 'Hint of Insanity', 'Key to the Side-Door', 'Mindreaver'])
def test_additional_native_relations_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_retraced_image_reveals_only_selected_card_and_puts_matching_permanent(cards):
    from app.game.visibility import can_see
    s = setup(cards)
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    selected = put(s, 'Grizzly Bears', 'hand')
    private = put(s, 'Forest', 'hand')
    spell(s, 'Retraced Image', {'U': 1})
    choose(s, [selected.id])
    assert s.state.cards[selected.id].zone == 'p1:battlefield'
    assert not can_see(s.state, s.state.cards[private.id], 'p2')
    roundtrip(s)


def test_mitotic_manipulation_puts_matching_looked_card_onto_battlefield(cards):
    s = setup(cards)
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    selected = put(s, 'Grizzly Bears', 'library')
    act(s, 'p1', type='move', card_ids=[selected.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    spell(s, 'Mitotic Manipulation', {'U': 2, 'C': 1})
    choose(s, [selected.id])
    assert s.state.cards[selected.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_hint_of_insanity_discards_duplicate_nonland_hand_cards_only(cards):
    s = setup(cards)
    duplicates = [c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Lightning Bolt']
    act(s, 'p2', type='move', card_ids=[c.id for c in duplicates], to={'player': 'p2', 'zone': 'hand'})
    single = put(s, 'Grizzly Bears', 'hand', 'p2')
    spell(s, 'Hint of Insanity', {'B': 1, 'C': 2}, ['p2'])
    assert all(s.state.cards[c.id].zone == 'p2:graveyard' for c in duplicates)
    assert s.state.cards[single.id].zone == 'p2:hand'
    roundtrip(s)


def test_side_door_native_cost_discards_matching_legend_and_draws_two(cards):
    s = setup(cards)
    source = put(s, 'Key to the Side-Door', 'battlefield')
    legend = put(s, 'Yenna, Redtooth Regent', 'battlefield')
    selected = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == legend.name and c.id != legend.id)
    act(s, 'p1', type='move', card_ids=[selected.id], to={'player': 'p1', 'zone': 'hand'})
    drew = s.state.rules.turn_log.drew.get('p1', 0)
    activate(s, source, 'Discard a legendary card')
    assert s.state.cards[selected.id].zone == 'p1:graveyard'
    assert s.state.rules.turn_log.drew.get('p1', 0) == drew + 2
    roundtrip(s)


def test_mindreaver_sacrifice_retains_exact_linked_source_for_target_legality(cards):
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    source = put(s, 'Mindreaver', 'battlefield')
    linked = put(s, 'Lightning Bolt', 'library', 'p2')
    act(s, 'p2', type='move', card_ids=[linked.id], to={'player': 'p2', 'zone': 'library'}, position='top')
    spell(s, 'Giant Growth', {'G': 1}, [source.id])
    choose(s, ['p2'])
    assert s.state.cards[linked.id].zone == 'p2:exile'
    bolt = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Lightning Bolt' and c.id != linked.id)
    act(s, 'p2', type='move', card_ids=[bolt.id], to={'player': 'p2', 'zone': 'hand'})
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[bolt.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bolt.id].zone == 'p2:graveyard' and s.state.players['p3'].life == 40
    roundtrip(s)


def test_harness_the_storm_canonical_full(cards):
    result = coverage.of_card_data(cards.resolve('Harness the Storm'))
    assert result.level == 'FULL', result.manual_parts


def test_harness_the_storm_pays_to_cast_exact_matching_graveyard_card(cards):
    s = setup(cards)
    put(s, 'Harness the Storm', 'battlefield')
    copies = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Lightning Bolt']
    act(s, 'p1', type='move', card_ids=[copies[1].id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'])
    choose(s, [copies[1].id])
    choose(s, [copies[1].id])
    if s.state.rules.decision is not None:
        choose(s, ['p3'])
    assert s.state.players['p3'].life == 34
    assert s.state.cards[copies[1].id].zone == 'p1:graveyard'
    assert len([n for n in s.state.rules.turn_log.casts if n.player == 'p1']) == 2
    roundtrip(s)


def test_scalpelexis_canonical_full(cards):
    result = coverage.of_card_data(cards.resolve('Scalpelexis'))
    assert result.level == 'FULL', result.manual_parts


def attack(s, source):
    from tests.test_rules_wave30m_durations import stops, to_phase
    put(s, 'Fervor', 'battlefield')
    stops(s, 'declare_attackers', 'main2')
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    to_phase(s, 'main2')
    settle(s)


def test_scalpelexis_repeats_only_latest_matching_four_card_batch(cards):
    s = setup(cards)
    source = put(s, 'Scalpelexis', 'battlefield')
    bolts = [c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Lightning Bolt']
    chosen = [*bolts, *(put(s, name, 'library', 'p2') for name in
                         ('Grizzly Bears', 'Ornithopter', 'Fervor', 'Key to the Side-Door', 'Harness the Storm', 'Mitotic Manipulation'))]
    for c in reversed(chosen):
        act(s, 'p2', type='move', card_ids=[c.id], to={'player': 'p2', 'zone': 'library'}, position='top')
    before = list(s.state.zones['p2:library'])
    assert before[:8] == [c.id for c in chosen]
    attack(s, source)
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in chosen)
    assert s.state.zones['p2:library'] == before[8:]
    roundtrip(s)


@pytest.mark.parametrize('name', ['Yenna, Redtooth Regent', 'Pirated Copy', 'Dual Nature', "Jester's Scepter"])
def test_copy_link_relations_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_yenna_creates_nonlegendary_copy_of_qualified_enchantment(cards):
    from app.rules.plan import Plan
    s = setup(cards)
    source = put(s, 'Yenna, Redtooth Regent', 'battlefield')
    target = put(s, 'Fervor', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[target.id])
    settle(s)
    copies = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert len(copies) == 1 and Plan(s.state, 'p1', s.cards, None).ch(copies[0]).name == 'Fervor'
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_pirated_copy_retains_pirate_and_draws_for_actual_combat_damage(cards):
    from app.rules.plan import Plan
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = spell(s, 'Pirated Copy', {'U': 1, 'C': 4})
    choose(s, [bear.id])
    ch = Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[source.id])
    assert ch.name == 'Grizzly Bears' and 'Pirate' in ch.subtypes
    drew = s.state.rules.turn_log.drew.get('p1', 0)
    attack(s, source)
    assert s.state.rules.turn_log.drew.get('p1', 0) == drew + 1
    roundtrip(s)


def test_dual_nature_departure_exiles_all_matching_tokens(cards):
    s = setup(cards)
    put(s, 'Dual Nature', 'battlefield')
    original = spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    token = next(c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield')
    spell(s, 'Lightning Bolt', {'R': 1}, [original.id])
    assert token.id not in s.state.cards or not s.state.cards[token.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_dual_nature_source_cleanup_preserves_unrelated_copy_tokens(cards):
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    source = put(s, 'Dual Nature', 'battlefield')
    original = spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    made = next(c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield')
    spell(s, 'Cackling Counterpart', {'U': 2, 'C': 1}, [original.id])
    unrelated = next(c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield' and c.id != made.id)
    kami = put(s, 'Kami of Ancient Law', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=kami.id, ability=0, targets=[source.id])
    settle(s)
    assert made.id not in s.state.cards or not s.state.cards[made.id].zone.endswith(':battlefield')
    assert s.state.cards[unrelated.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_jesters_scepter_pays_linked_face_down_card_and_counters_matching_spell(cards):
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    top = put(s, 'Lightning Bolt', 'library', 'p2')
    printing = top.card_id
    act(s, 'p2', type='move', card_ids=[top.id], to={'player': 'p2', 'zone': 'library'}, position='top')
    source = spell(s, "Jester's Scepter", {'C': 3})
    choose(s, ['p2'])
    linked = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.card_id == printing and c.zone == 'p2:exile')
    assert linked.face_down
    bolt = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.card_id == printing and c.id != linked.id)
    act(s, 'p2', type='move', card_ids=[bolt.id], to={'player': 'p2', 'zone': 'hand'})
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[bolt.id],
        cost_choices=[{'component': 2, 'cards': [linked.id]}])
    settle(s)
    assert s.state.cards[linked.id].zone == s.state.cards[bolt.id].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', ['Kotose, the Silent Spider', 'Spellweaver Helix'])
def test_final_core_relations_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_kotose_one_shared_play_permission_includes_original_and_search_finds(cards):
    from app.game.errors import ActionError
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    original = put(s, 'Lightning Bolt', 'graveyard', 'p2')
    other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == original.name and c.id != original.id)
    act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'library'})
    source = spell(s, 'Kotose, the Silent Spider', {'U': 1, 'B': 1, 'C': 3})
    choose(s, [original.id])
    choose(s, [other.id])
    grants = [p for p in s.state.rules.permissions if p.card in (original.id, other.id)]
    assert len(grants) == 2 and len({p.group for p in grants}) == 1
    assert all(p.player == 'p1' and p.play and p.spend == 'color' for p in grants)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='cast_spell', card_id=other.id, targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life == 37 and s.state.cards[source.id].zone == 'p1:battlefield'
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=original.id, targets=['p3'])
    roundtrip(s)


def test_spellweaver_helix_same_name_imprints_cast_exactly_one_copy_without_recursion(cards):
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    originals = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Hint of Insanity']
    assert len(originals) == 3
    act(s, 'p1', type='move', card_ids=[c.id for c in originals[:2]], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[originals[2].id], to={'player': 'p1', 'zone': 'hand'})
    source = spell(s, 'Spellweaver Helix', {'C': 3})
    choose(s, [c.id for c in originals[:2]])
    if s.state.rules.decision is not None:
        choose(s, ['yes'])
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in originals[:2])
    victims = [c for c in s.state.cards.values() if c.owner == 'p3' and c.name == 'Lightning Bolt']
    act(s, 'p3', type='move', card_ids=[c.id for c in victims], to={'player': 'p3', 'zone': 'hand'})
    before = len(s.state.rules.turn_log.casts)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=originals[2].id, targets=['p2'])
    settle(s)
    choose(s, [originals[0].id])
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 1
    copy_id = d.options[0].card_id
    choose(s, [d.options[0].id])
    if s.state.rules.decision is not None:
        choose(s, ['p3'])
    assert all(s.state.cards[c.id].zone == 'p3:graveyard' for c in victims)
    assert len(s.state.rules.turn_log.casts) == before + 2
    assert copy_id not in s.state.cards or s.state.cards[copy_id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('kind', ['history', 'repeat'])
def test_name_relation_callbacks_resume_in_a_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    if kind == 'history':
        from app.game.session import GameSession
        from app.game.state import GameState
        s = setup(cards)
        source = put(s, 'Twinning Glass', 'battlefield')
        spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2')
        data = s.state.model_dump(mode='json')
        for receipt in data['rules']['turn_log']['casts']:
            receipt.pop('names')
        s = GameSession(GameState.model_validate(data), cards=cards)
        put(s, 'Lightning Bolt', 'hand')
        activate(s, s.state.cards[source.id])
    else:
        s = three(cards, ['Scalpelexis', 'Fervor', *(['Forest'] * 150)], ['Forest'] * 150, ['Forest'] * 150)
        hold(s)
        source = put(s, 'Scalpelexis', 'battlefield')
        from tests.test_rules_wave30m_durations import stops, to_phase
        put(s, 'Fervor', 'battlefield')
        stops(s, 'declare_attackers', 'main2')
        to_phase(s, 'declare_attackers')
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
        for _ in range(80):
            d = s.state.rules.decision
            if d is not None and d.kind == 'declare_blockers':
                act(s, d.player, type='declare_blockers', blocks=[])
            elif d is not None:
                break
            else:
                act(s, s.state.rules.priority, type='pass_priority')
        assert 'mandatory repeated exile' in s.state.rules.decision.prompt
        assert len(s.state.zones['p2:library']) > 0
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, kind = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
def settle():
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == 'order':
            s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [o.id for o in d.options]})
        elif d is None and s.state.zones.get('stack'):
            s.perform(s.state.rules.priority, {'type': 'pass_priority'})
        else:
            return
    raise AssertionError('did not settle')
d = s.state.rules.decision
if kind == 'history':
    assert d.player == 'p2'
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [], 'name': 'Lightning Bolt'})
    settle()
    assert s.state.rules.turn_log.casts[-1].names == ['Lightning Bolt']
    d = s.state.rules.decision
    assert d is not None and d.options
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': []})
    settle()
else:
    assert [o.id for o in d.options] == ['continue']
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['continue']})
    settle()
    assert not s.state.zones['p2:library']
    assert len(s.state.zones['p2:exile']) >= 140
assert s.state.rules.decision is None
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
