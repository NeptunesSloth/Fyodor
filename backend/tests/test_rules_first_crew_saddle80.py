"""Native first crew/saddle resolution and paid contributor boundaries."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import pick, put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_unblocked_riders32 import unblocked
from tests.test_rules_wave6c_tokens_pumps import chars

DATA = json.loads((Path(__file__).parent / 'fixtures/first_crew_saddle80_cards.json').read_text())
NAMES = ['Mighty Servant of Leuk-o', 'Mindlink Mech', 'Stubborn Burrowfiend']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='crew80', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup80(cards, name):
    names = list(dict.fromkeys([c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Forest', 'Island', 'Sol Ring']))
    s = table(cards, names, [], [])
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    dragon = put(s, 'Shivan Dragon', 'battlefield')
    start(s)
    return s, source, bear, other, dragon


def crew80(s, source, *payers, saddle=False):
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'keywords' and a.text.lower().startswith('saddle' if saddle else 'crew'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[c.id for c in payers])
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_whole80(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_mighty_exact_two_first_resolved_crew_draws(cards):
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    crew80(s, source, bear, other)
    assert any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)
    before = len(s.state.zones.get('p1:hand', []))
    unblocked(s, source)
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == before + 2


def test_mighty_wrong_first_payment_does_not_trigger_on_later_exact_two(cards):
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    crew80(s, source, dragon)
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)
    crew80(s, source, bear, other)
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)


def test_mindlink_native_target_and_copy_exceptions(cards):
    s, source, bear, other, dragon = setup80(cards, 'Mindlink Mech')
    crew80(s, source, bear)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {bear.id}
    pick(s, [bear.id])
    settle(s)
    ch = chars(s, source)
    assert ch.name == 'Grizzly Bears'
    assert ch.pt == (4, 3)
    assert 'Flying' in [a.text for a in ch.abilities]
    assert {'Artifact', 'Creature'} <= ch.types
    assert 'Vehicle' in ch.subtypes


def test_stubborn_mills_before_counting_graveyard_creatures(cards):
    s, source, bear, other, dragon = setup80(cards, 'Stubborn Burrowfiend')
    elf = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Llanowar Elves')
    land = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest')
    for c in [land, elf]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    before = chars(s, source).pt
    crew80(s, source, bear, saddle=True)
    assert s.state.cards[elf.id].zone == 'p1:graveyard'
    assert s.state.cards[land.id].zone == 'p1:graveyard'
    assert chars(s, source).pt == (before[0] + 1, before[1] + 1)
    log_count = len(s.state.zones['p1:graveyard'])
    crew80(s, source, other, saddle=True)
    assert len(s.state.zones['p1:graveyard']) == log_count
    assert chars(s, source).pt == (before[0] + 1, before[1] + 1)


def test_mindlink_animated_noncreature_has_no_copiable_power_toughness(cards):
    from tests.test_rules_bandmate_references import mana
    s, source, bear, other, dragon = setup80(cards, 'Mindlink Mech')
    ring = put(s, 'Sol Ring', 'battlefield')
    ensoul = put(s, 'Ensoul Artifact', 'hand')
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=ensoul.id, targets=[ring.id])
    settle(s)
    assert chars(s, ring).pt == (5, 5)
    crew80(s, source, ring)
    pick(s, [ring.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[ring.id].zone == 'p1:battlefield'


def test_countered_wrong_crew_does_not_consume_first_resolution(cards):
    from tests.test_rules_bandmate_references import mana
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    counter = put(s, 'Stifle', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('crew'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[dragon.id])
    sid = s.state.zones['stack'][-1]
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[sid])
    settle(s)
    assert not chars(s, source).is_creature
    crew80(s, source, bear, other)
    assert any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)


def test_copied_crew_retains_original_cost_objects_for_first_resolution(cards):
    from tests.test_rules_bandmate_references import mana
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    copier = put(s, 'Lithoform Engine', 'battlefield')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('crew'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[bear.id, other.id])
    sid = s.state.zones['stack'][-1]
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=copier.id, ability=0, targets=[sid])
    settle(s)
    # 707.10 retains the objects used for the original costs; only the first
    # resolving crew ability creates the qualifying Vehicle trigger.
    assert sum(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities) == 1


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_pending_native_crew_or_saddle(cards, tmp_path, name):
    import subprocess
    import sys

    import app
    s, source, bear, other, dragon = setup80(cards, name)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    saddle = name == 'Stubborn Burrowfiend'
    index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('saddle' if saddle else 'crew'))
    payers = [bear, other] if name == 'Mighty Servant of Leuk-o' else [bear]
    before_mill = len(s.state.zones.get('p1:graveyard', []))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[c.id for c in payers])
    assert s.state.zones.get('stack')
    saved = tmp_path / 'crew80.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import pick
from tests.test_rules_wave6c_tokens_pumps import chars
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name,source,bear,before=sys.argv[3:]
settle(s)
if name=='Mindlink Mech':
 assert s.state.rules.decision is not None
 pick(s,[bear]);settle(s)
 assert chars(s,s.state.cards[source]).name=='Grizzly Bears'
 assert chars(s,s.state.cards[source]).pt==(4,3)
elif name=='Mighty Servant of Leuk-o':
 assert any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s,s.state.cards[source]).abilities)
else:assert len(s.state.zones['p1:graveyard'])==int(before)+2
assert s.state.rules.decision is None
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, source.id, bear.id, str(before_mill)],
        capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


def test_unknown_legacy_first_history_is_explicit_not_invented(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    old = s.state.model_dump(mode='json')
    assert old['rules']['first_event_history_turn78'] == s.state.turn.number
    old['rules'].pop('crew_saddle_history_turn80')
    s = GameSession(GameState.model_validate(old), cards=cards)
    crew80(s, source, bear, other)
    assert s.state.rules.decision is not None
    assert s.state.rules.decision.kind == 'manual_resolution'
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)
    pick(s, ['done'])
    settle(s)
    crew80(s, source, dragon)
    assert s.state.rules.decision is None
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)


def test_blink_creates_new_source_first_resolution_in_same_turn(cards):
    from tests.test_rules_bandmate_references import mana
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    crew80(s, source, dragon)
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)
    before = s.state.rules.object_id(source.id)
    spell = put(s, 'Cloudshift', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert before != s.state.rules.object_id(source.id)
    crew80(s, source, bear, other)
    assert any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)


def test_first_resolution_is_recorded_while_trigger_ability_is_absent(cards):
    from tests.test_rules_bandmate_references import mana
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    dress = put(s, 'Dress Down', 'hand')
    remove = put(s, "Nature's Claim", 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('crew'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[dragon.id])
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=dress.id)
    settle(s)
    assert not chars(s, source).abilities
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=remove.id, targets=[dress.id])
    settle(s)
    assert chars(s, source).abilities
    crew80(s, source, bear, other)
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)


def test_stubborn_first_resets_next_turn_and_bonus_expires(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, source, bear, other, dragon = setup80(cards, 'Stubborn Burrowfiend')
    before = chars(s, source).pt
    elf = put(s, 'Llanowar Elves', 'graveyard')
    crew80(s, source, bear, saddle=True)
    assert chars(s, source).pt == (before[0] + 1, before[1] + 1)
    gy_before = len(s.state.zones['p1:graveyard'])
    to_phase(s, 'main1', turn=7)
    assert chars(s, source).pt == before
    crew80(s, source, bear, saddle=True)
    assert len(s.state.zones['p1:graveyard']) == gy_before + 2
    assert s.state.cards[elf.id].zone == 'p1:graveyard'
    assert chars(s, source).pt == (before[0] + 1, before[1] + 1)


@pytest.mark.parametrize('name', NAMES)
def test_actual_full_card_cast_then_native_resolution(cards, name):
    from tests.test_rules_bandmate_references import mana
    s, source, bear, other, dragon = setup80(cards, name)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=5, U=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    before = len(s.state.zones.get('p1:graveyard', []))
    crew80(s, source, *([bear, other] if name == 'Mighty Servant of Leuk-o' else [bear]), saddle=name == 'Stubborn Burrowfiend')
    if name == 'Mindlink Mech':
        pick(s, [bear.id])
        settle(s)
        assert chars(s, source).name == 'Grizzly Bears'
        assert chars(s, source).pt == (4, 3)
    elif name == 'Mighty Servant of Leuk-o':
        assert any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)
    else:
        assert len(s.state.zones.get('p1:graveyard', [])) == before + 2


@pytest.mark.parametrize('can_pay', [True, False])
def test_mighty_printed_discard_ward_is_enforced(cards, can_pay):
    from tests.test_rules_bandmate_references import mana
    names = list(dict.fromkeys([c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Forest', 'Island', 'Sol Ring']))
    s = table(cards, names, ['Lightning Bolt', 'Island'], [])
    source = put(s, 'Mighty Servant of Leuk-o', 'battlefield')
    dragon = put(s, 'Shivan Dragon', 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    discard = put(s, 'Island', 'hand', 'p2') if can_pay else None
    start(s)
    # Other players drew during native turn advancement; retain only the
    # explicitly prepared Ward payment card and the spell being cast.
    unwanted = [cid for cid in s.state.zones.get('p2:hand', []) if cid not in {bolt.id, discard.id if discard else None}]
    if unwanted:
        act(s, 'p2', type='move', card_ids=unwanted, to={'player': 'p2', 'zone': 'graveyard'})
    crew80(s, source, dragon)
    mana(s, pid='p2', R=1)
    for _ in range(6):
        if s.state.rules.priority == 'p2':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[source.id])
    settle(s)
    if can_pay:
        d = s.state.rules.decision
        assert d is not None and d.player == 'p2'
        assert 'pay' in {o.id for o in d.options}
        pick(s, ['pay'])
        settle(s)
        d = s.state.rules.decision
        if d:
            assert discard.id in {o.id for o in d.options}
            pick(s, [discard.id])
            settle(s)
        assert s.state.cards[discard.id].zone == 'p2:graveyard'
    else:
        assert s.state.rules.decision is None
    assert s.state.cards[source.id].damage == (3 if can_pay else 0)
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'


def test_old_pending_crew_without_payment_receipt_uses_explicit_notice(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('crew'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[bear.id, other.id])
    old = s.state.model_dump(mode='json')
    for stack in old['rules']['stack'].values():
        for effect in stack.get('effects', []):
            effect.pop('crew_count80', None)
    s = GameSession(GameState.model_validate(old), cards=cards)
    settle(s)
    assert s.state.rules.decision is not None
    assert s.state.rules.decision.kind == 'manual_resolution'
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)
    pick(s, ['done'])
    settle(s)
    assert s.state.rules.decision is None


def test_original_paid_creatures_count_even_after_one_is_blinked(cards):
    from tests.test_rules_bandmate_references import mana
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    spell = put(s, 'Cloudshift', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('crew'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[bear.id, other.id])
    old = s.state.rules.object_id(bear.id)
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert s.state.rules.object_id(bear.id) != old
    assert any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)


def test_unknown_legacy_history_does_not_notice_known_wrong_payment(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    s, source, bear, other, dragon = setup80(cards, 'Mighty Servant of Leuk-o')
    old = s.state.model_dump(mode='json')
    assert old['rules']['first_event_history_turn78'] == s.state.turn.number
    old['rules'].pop('crew_saddle_history_turn80')
    s = GameSession(GameState.model_validate(old), cards=cards)
    crew80(s, source, dragon)
    assert s.state.rules.decision is None
    crew80(s, source, bear, other)
    assert s.state.rules.decision is None
    assert not any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)


def test_trustworthy_fresh_turn_one_records_actual_first_crew(cards):
    from tests.test_rules_wave30m_durations import stops, to_phase
    names = list(dict.fromkeys([c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring']))
    s = table(cards, names, [], [])
    source = put(s, 'Mighty Servant of Leuk-o', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    stops(s, 'main1')
    to_phase(s, 'main1', turn=1)
    assert s.state.turn.number == 1
    assert s.state.rules.crew_saddle_history_turn80 == 1
    crew80(s, source, bear, other)
    assert s.state.rules.decision is None
    assert any(a.text.startswith('Whenever this creature deals combat damage to a player, draw two cards') for a in chars(s, source).abilities)
