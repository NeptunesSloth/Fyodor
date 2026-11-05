"""CR 701.50b-c, 702.51: actual convokers connive with saved object identity and chosen order."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/convoke_connive_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Lethal Scheme'


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, leader=False):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [NAME, 'Grizzly Bears', 'Ornithopter', 'Sol Ring', 'Murder', 'Cloudshift', 'Leader, Super-Genius', 'Leader, Super-Genius', 'Reverberate', 'Glorious Purpose', 'Slip Out the Back', 'Llanowar Elves', 'Mirror Gallery', 'Hardened Scales', 'Branching Evolution'], ['Llanowar Elves', 'Murder'])
    source = put(s, NAME, 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    thopter = put(s, 'Ornithopter', 'battlefield')
    target = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    if int(leader) > 1:
        put(s, 'Mirror Gallery', 'battlefield')
    if leader:
        from tests.game_helpers import act

        leaders = [c for c in s.state.cards.values() if c.name == 'Leader, Super-Genius' and c.owner == 'p1']
        for c in leaders[:int(leader)]:
            act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    for name in ['Sol Ring', 'Murder']:
        put(s, name, 'hand')
    return s, source, bear, thopter, target


def cast_scheme(s, source, target, helpers):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    mana(s, B=4 - len(helpers))
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id],
        contributions=[{'card': c.id, 'kind': 'convoke'} for c in helpers])


def choose_conniver(s, creature):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt == 'Choose which creature connives next'
    option = next(o for o in d.options if o.card_id == creature.id)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])


def discard(s, name):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    settle(s)
    d = s.state.rules.decision
    while d is not None and d.resume.get('step') == 'replace_order':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
        d = s.state.rules.decision
    assert d is not None and d.prompt.startswith('Connive: discard')
    option = next(o for o in d.options if s.state.cards[o.id].name == name)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])


def test_controller_chooses_each_conniver_and_both_draw_then_discard(cards):
    from tests.test_rules_designations import roundtrip, settle
    s, source, bear, thopter, target = setup(cards)
    cast_scheme(s, source, target, [bear, thopter])
    choose_conniver(s, thopter)
    discard(s, 'Murder')
    discard(s, 'Sol Ring')
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_destroyed_convoker_still_draws_and_discards_without_counter(cards):
    from tests.test_rules_designations import roundtrip, settle
    s, source, bear, thopter, _ = setup(cards)
    cast_scheme(s, source, bear, [bear, thopter])
    choose_conniver(s, bear)
    discard(s, 'Murder')
    discard(s, 'Sol Ring')
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert not s.state.cards[bear.id].counters
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_leader_replacement_applies_separately_to_each_conniver(cards):
    from tests.test_rules_designations import roundtrip, settle
    s, source, bear, thopter, target = setup(cards, leader=True)
    before = len(s.state.zones['p1:library'])
    cast_scheme(s, source, target, [bear, thopter])
    choose_conniver(s, thopter)
    discard(s, 'Murder')
    discard(s, 'Sol Ring')
    settle(s)
    assert len(s.state.zones['p1:library']) == before - 4
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_no_convokers_does_not_connive(cards):
    from tests.test_rules_designations import roundtrip, settle
    s, source, bear, thopter, target = setup(cards)
    before = len(s.state.zones['p1:library'])
    cast_scheme(s, source, target, [])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert len(s.state.zones['p1:library']) == before
    assert not s.state.cards[bear.id].counters and not s.state.cards[thopter.id].counters
    roundtrip(s)


def test_illegal_only_target_prevents_all_conniving(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    s, source, bear, thopter, target = setup(cards)
    before = len(s.state.zones['p1:library'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast_scheme(s, source, target, [bear, thopter])
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:library']) == before
    assert not s.state.cards[bear.id].counters and not s.state.cards[thopter.id].counters
    roundtrip(s)


def test_each_current_controller_connives_in_apnap_order(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, bear, thopter, target = setup(cards)
    put(s, 'Murder', 'hand', 'p2')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast_scheme(s, source, target, [bear, thopter])
    act(s, 'p1', type='set_controller', card_ids=[thopter.id], player='p2')
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    discard(s, 'Murder')
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    discard(s, 'Murder')
    settle(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_copy_refers_to_original_actual_convokers(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, bear, thopter, target = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast_scheme(s, source, target, [bear, thopter])
    copy = put(s, 'Reverberate', 'hand')
    mana(s, R=2)
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[source.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith('Copy of Lethal Scheme')
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    choose_conniver(s, thopter)
    discard(s, 'Murder')
    discard(s, 'Sol Ring')
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_connive_trigger_occurs_after_discard_and_counter_process(cards):
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, bear, _, target = setup(cards)
    purpose = put(s, 'Glorious Purpose', 'battlefield')
    cast_scheme(s, source, target, [bear])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith('Connive: discard')
    assert not any(t.source_card == purpose.id for t in s.state.rules.pending_triggers)
    assert not any(e.kind == 'designation' and e.counter == 'connive' for e in s.state.rules.events)
    discard(s, 'Murder')
    settle(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == 2
    assert s.state.cards[purpose.id].counters['plan'] == 1
    roundtrip(s)


def test_returned_convoker_is_new_object_and_gets_no_old_connive_counter(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, bear, thopter, target = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast_scheme(s, source, target, [bear, thopter])
    blink = put(s, 'Cloudshift', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[bear.id])
    choose_conniver(s, bear)
    discard(s, 'Murder')
    discard(s, 'Sol Ring')
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert not s.state.cards[bear.id].counters
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_phased_out_convoker_does_not_exist_for_conniving(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, bear, thopter, target = setup(cards)
    before = len(s.state.zones['p1:library'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast_scheme(s, source, target, [bear, thopter])
    phase = put(s, 'Slip Out the Back', 'hand')
    before = len(s.state.zones['p1:library'])
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=phase.id, targets=[bear.id])
    discard(s, 'Murder')
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:phased'
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    assert len(s.state.zones['p1:library']) == before - 1
    roundtrip(s)


def test_creature_tapped_for_mana_is_not_a_convoker(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase
    s, source, bear, thopter, target = setup(cards)
    elf = put(s, 'Llanowar Elves', 'battlefield')
    to_phase(s, 'main1', turn=4)
    mana(s, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id], sources=[elf.id],
        contributions=[{'card': bear.id, 'kind': 'convoke'}])
    discard(s, 'Murder')
    settle(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    assert s.state.cards[elf.id].tapped and not s.state.cards[elf.id].counters
    assert not s.state.cards[thopter.id].counters
    roundtrip(s)


def test_multiple_connive_replacements_resume_remaining_convokers(cards):
    from tests.test_rules_designations import roundtrip, settle
    s, source, bear, thopter, target = setup(cards, leader=2)
    before = len(s.state.zones['p1:library'])
    cast_scheme(s, source, target, [bear, thopter])
    choose_conniver(s, thopter)
    # (the two Leaders are copies of one effect: their order can't matter, so it isn't asked (616.1))
    assert s.state.rules.decision.resume.get('step') != 'replace_order'
    discard(s, 'Murder')
    assert s.state.rules.decision.resume.get('step') != 'replace_order'
    discard(s, 'Sol Ring')
    settle(s)
    assert len(s.state.zones['p1:library']) == before - 6
    assert s.state.cards[bear.id].counters['+1/+1'] == 1
    assert s.state.cards[thopter.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_connive_finishes_after_counter_replacement_choice_then_triggers(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s, source, bear, _, target = setup(cards)
    purpose = put(s, 'Glorious Purpose', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    put(s, 'Branching Evolution', 'battlefield')
    cast_scheme(s, source, target, [bear])
    discard(s, 'Murder')
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'replace_order'
    assert not any(t.source_card == purpose.id for t in s.state.rules.pending_triggers)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.resume.get('step') == 'replace_order':
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
        if s.state.rules.decision is None and not s.state.zones.get('stack'):
            break
    assert s.state.cards[purpose.id].counters['plan'] == 1
    assert s.state.cards[bear.id].counters['+1/+1'] in (6, 7, 8)
    roundtrip(s)
