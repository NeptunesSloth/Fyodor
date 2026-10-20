"""CR 608.2d, 701.13, 202.3: opponent choices and milled-card mana values."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/mill_pair_repeat_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def setup(cards, names, *, source='Grindstone', owner='p2', bruvac=False, rip=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    extras = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/mill_pair_repeat_cards.json').read_text())]
    s = table(cards, [*extras, *names] if owner == 'p1' else extras, names if owner == 'p2' else [], [])
    permanent = put(s, source, 'battlefield')
    if bruvac:
        put(s, 'Bruvac the Grandiloquent', 'battlefield')
    if rip:
        put(s, 'Rest in Peace', 'battlefield')
    selected = []
    for name in names:
        selected.append(next(c.id for c in s.state.cards.values() if c.name == name and c.owner == owner and c.id not in selected))
    library = list(s.state.zones.get(owner+':library', []))
    if library:
        act(s, owner, type='move', card_ids=library, to={'player': owner, 'zone': 'exile'})
    if selected:
        act(s, owner, type='move', card_ids=selected, to={'player': owner, 'zone': 'library'}, index=0)
    return s, permanent, selected


def grind(s, source, pid='p2'):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    mana(s, C=3)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[pid])
    for _ in range(40):
        r = s.state.rules
        if r.draw_reason or r.decision or not s.state.zones.get('stack'):
            break
        act(s, r.priority, type='pass_priority')
    roundtrip(s)


@pytest.mark.parametrize('names,milled', [
    (['Lightning Bolt', 'Shock', 'Counterspell', 'Sol Ring', 'Opt', 'Shock'], 4),
    (['Lightning Bolt', 'Counterspell', 'Shock', 'Opt'], 2),
    (['Sol Ring', 'Ornithopter', 'Lightning Bolt', 'Shock'], 2),
    (['Manamorphose', 'Shock', 'Sol Ring', 'Ornithopter'], 4),
    (['Manamorphose', 'Counterspell', 'Shock', 'Opt'], 2),
    (['Dryad Arbor', 'Llanowar Elves', 'Sol Ring', 'Ornithopter'], 4),
    (['Lightning Bolt'], 1), ([], 0)])
def test_grindstone_uses_only_the_latest_batch_and_a_shared_nonempty_color(cards, names, milled):
    s, source, selected = setup(cards, names)
    grind(s, source)
    assert len(s.state.zones.get('p2:graveyard', [])) == milled
    assert len(s.state.zones.get('p2:library', [])) == len(selected)-milled
    assert 'p2' not in s.state.rules.lost


def test_bruvac_checks_for_any_qualifying_pair_in_the_expanded_batch(cards):
    names = ['Lightning Bolt', 'Counterspell', 'Shock', 'Sol Ring', 'Forest', 'Island', 'Ornithopter', 'Opt']
    s, source, _ = setup(cards, names, bruvac=True)
    grind(s, source)
    # First four contain a red pair despite the first two not sharing a color.
    # The second batch stops: Opt is the only colored card in it.
    assert len(s.state.zones.get('p2:graveyard', [])) == 8
    assert not s.state.zones.get('p2:library')
    assert 'p2' not in s.state.rules.lost


def test_public_exile_replacement_preserves_latest_pair_information(cards):
    s, source, selected = setup(cards, ['Lightning Bolt', 'Shock', 'Sol Ring', 'Ornithopter'], rip=True)
    grind(s, source)
    assert all(s.state.cards[c].zone == 'p2:exile' for c in selected)
    assert not s.state.zones.get('p2:library') and not s.state.zones.get('p2:graveyard')


@pytest.mark.parametrize('names,milled', [
    (['Lightning Bolt', 'Shock', 'Sol Ring', 'Ornithopter'], 4),
    (['Dryad Arbor', 'Llanowar Elves', 'Lightning Bolt', 'Shock'], 2)])
def test_tutelage_requires_two_nonland_cards_in_the_shared_color_pair(cards, names, milled):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, _, selected = setup(cards, names, source="Sphinx's Tutelage")
    spell = put(s, 'Opt', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'look'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    d = s.state.rules.decision
    assert d and 'p2' in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert len(s.state.zones.get('p2:graveyard', [])) == milled
    assert len(s.state.zones.get('p2:library', [])) == len(selected)-milled
    roundtrip(s)


def test_tamiyo_chapter_draws_between_matching_card_type_batches(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    names = ['Sol Ring', 'Ornithopter', 'Forest', 'Lightning Bolt', 'Shock', 'Island', 'Counterspell', 'Sol Ring']
    s, source, selected = setup(cards, names, source='The Tale of Tamiyo', owner='p1')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:hand' for c in [selected[2], selected[5]])
    assert all(s.state.cards[c].zone == 'p1:graveyard' for i, c in enumerate(selected) if i not in (2, 5))
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


def painter(s):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle

    source = put(s, "Painter's Servant", 'hand')
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d and 'Red' in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['Red'])
    settle(s)


def test_mandatory_whole_library_self_shuffle_is_a_draw_and_roundtrips(cards):
    from app.game.errors import ActionError
    from app.rules.view import _rules_view
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source, _ = setup(cards, ['Darksteel Colossus', 'Blightsteel Colossus'])
    painter(s)
    grind(s, source)
    r = s.state.rules
    assert r.draw_reason and not r.winner and not r.lost and not r.conceded
    assert r.priority is None and r.decision is None
    assert len(s.state.zones['p2:library']) == 2
    view = _rules_view(s.state, 'p1', s.cards)
    assert view['draw_reason'] == r.draw_reason and view['hints'] == {}
    with pytest.raises(ActionError, match='over: draw'):
        act(s, 'p1', type='pass_priority')
    with pytest.raises(ActionError, match='over: draw'):
        act(s, 'p1', type='concede')
    roundtrip(s)
    s.undo('p1')
    assert s.state.rules.draw_reason is None
    s.redo('p1')
    assert s.state.rules.draw_reason == r.draw_reason
    roundtrip(s)


def test_two_colorless_self_shufflers_do_not_falsely_draw(cards):
    s, source, _ = setup(cards, ['Darksteel Colossus', 'Blightsteel Colossus'])
    grind(s, source)
    assert len(s.state.zones['p2:library']) == 2
    assert s.state.rules.draw_reason is None and s.state.rules.decision is None


def test_single_colored_self_shuffler_stops_short_library_without_draw(cards):
    s, source, _ = setup(cards, ['Progenitus'])
    grind(s, source)
    assert len(s.state.zones['p2:library']) == 1
    assert s.state.rules.draw_reason is None


def test_competing_replacement_choices_finish_before_either_shuffle_and_can_end_loop(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, source, _ = setup(cards, ['Progenitus', 'Progenitus'], rip=True)
    grind(s, source)
    for i in range(2):
        d = s.state.rules.decision
        assert d and d.resume['step'] == 'mill_pair_replace' and d.player == 'p2'
        assert len(s.state.zones['p2:library']) == 2  # all outcomes prepared before committing
        assert not s.state.rules.draw_reason
        roundtrip(s)
        # One mandatory shuffle and one public exile: a subsequent one-card mill ends.
        pick = next(o.id for o in d.options if ('library:shuffle' if i == 0 else 'exile') in o.label)
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[pick])
        settle(s)
    # The remaining Progenitus has another genuine 616 choice in the next batch.
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'mill_pair_replace'
    act(s, 'p2', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if 'exile' in o.label)])
    settle(s)
    assert not s.state.zones.get('p2:library')
    assert s.state.rules.draw_reason is None and s.state.rules.decision is None
    roundtrip(s)


def test_long_finite_process_checkpoints_without_priority_or_secret_information(cards, monkeypatch):
    from app.game.errors import ActionError
    from app.rules import mill_pair_repeat
    from app.rules.view import _rules_view
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    monkeypatch.setattr(mill_pair_repeat, 'BUDGET', 2)
    s, source, selected = setup(cards, ['Shock'] * 8 + ['Sol Ring', 'Ornithopter'])
    grind(s, source)
    for expected in [4, 8]:
        d = s.state.rules.decision
        assert d and d.resume['step'] == 'mill_pair_continue'
        assert len(d.resume['ctx']['effects']) == 3  # no unrolled context growth
        assert len(s.state.zones['p2:graveyard']) == expected
        assert [o.id for o in d.options] == ['continue']
        assert not s.state.rules.draw_reason
        view = _rules_view(s.state, 'p3', s.cards)
        assert 'request' not in view['decision'] and 'resume' not in view['decision']
        roundtrip(s)
        with pytest.raises(ActionError):
            act(s, 'p2', type='pass_priority')
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['continue'])
        settle(s)
    assert len(s.state.zones['p2:graveyard']) == len(selected)
    assert not s.state.rules.decision and not s.state.rules.draw_reason
    roundtrip(s)


def test_old_rules_state_has_no_draw_outcome():
    from app.game.rules_state import RulesState

    assert RulesState.model_validate({}).draw_reason is None


def test_three_self_shufflers_prove_every_possible_pair_without_disclosing_hidden_cards(cards):
    s, source, _ = setup(cards, ['Progenitus'] * 3)
    grind(s, source)
    assert s.state.rules.draw_reason
    assert len(s.state.zones['p2:library']) == 3
    assert 'Progenitus' not in s.state.rules.draw_reason


def test_repeated_random_outcome_with_a_possible_nonmatching_pair_is_not_a_draw(cards, monkeypatch):
    from app.game import resolve
    from app.game.actions import ShuffleData
    from app.rules import mill_pair_repeat
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    monkeypatch.setattr(mill_pair_repeat, 'BUDGET', 2)
    original = resolve.shuffle_data

    def keep_top(size, rng=None):
        data = original(size)
        return ShuffleData(perm=list(range(size)), new_ids=data.new_ids)

    monkeypatch.setattr(resolve, 'shuffle_data', keep_top)
    s, source, _ = setup(cards, ['Progenitus', 'Progenitus', 'Darksteel Colossus'])
    grind(s, source)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'mill_pair_continue'
    assert not s.state.rules.draw_reason
    roundtrip(s)
    # A future shuffle may expose the colorless card, so this identical observed
    # result is not proof of an unbreakable loop.
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['continue'])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'mill_pair_continue'
    assert not s.state.rules.draw_reason
    roundtrip(s)


def test_tamiyo_matching_type_loop_with_draws_prohibited_is_a_draw(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, source, _ = setup(cards, ['Darksteel Colossus', 'Blightsteel Colossus'], source='The Tale of Tamiyo', owner='p1')
    put(s, 'Maralen of the Mornsong', 'battlefield')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    for _ in range(30):
        r = s.state.rules
        if r.draw_reason or r.decision or not s.state.zones.get('stack'):
            break
        act(s, r.priority, type='pass_priority')
    assert s.state.rules.draw_reason and not s.state.rules.winner
    assert len(s.state.zones['p1:library']) == 2
    roundtrip(s)


def test_gaea_blessing_trigger_waits_until_the_entire_repeat_finishes(cards):
    s, source, _ = setup(cards, ["Gaea's Blessing", 'Llanowar Elves', 'Shock', 'Counterspell'])
    grind(s, source)
    assert len(s.state.zones['p2:library']) == 4
    assert not s.state.zones.get('p2:graveyard')
    mills = [step for a in s.history.actions for step in (getattr(a, 'r', None) if isinstance(getattr(a, 'r', None), list) else []) if step['type'] == 'mill']
    assert len(mills) == 2 and all(step['count'] == 2 for step in mills)


def test_normal_cards_in_a_replaced_batch_still_emit_mill_events(cards):
    from tests.test_rules_designations import put

    s, source, _ = setup(cards, ['Darksteel Colossus', 'Shock'])
    put(s, 'The Wise Mothman', 'battlefield')
    grind(s, source)
    assert len(s.state.zones['p2:graveyard']) == 1
    d = s.state.rules.decision
    # One nonland card was actually milled, despite the other move's replacement.
    assert d is not None and d.player == 'p1'


@pytest.mark.parametrize('name', ['Grindstone', "Sphinx's Tutelage"])
def test_complete_repeat_cards_are_fully_automated(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_expanded_mandatory_loop_uses_pigeonhole_proof_not_all_pairs_match(cards):
    # Any four of these five contain a colored pair, although a Colossus and a
    # Nexus do not share a color. One Bruvac increases each batch from two to four.
    s, source, _ = setup(cards, ['Progenitus', 'Nexus of Fate', 'Nexus of Fate',
                                'Darksteel Colossus', 'Blightsteel Colossus'], bruvac=True)
    grind(s, source)
    assert s.state.rules.draw_reason
    assert len(s.state.zones['p2:library']) == 5


def test_default_processing_budget_resumes_a_large_finite_library_exactly(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, source, selected = setup(cards, ['Shock'] * 80 + ['Sol Ring', 'Ornithopter'])
    grind(s, source)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'mill_pair_continue'
    assert len(s.state.zones['p2:graveyard']) == 64
    assert len(s.state.zones['p2:library']) == 18
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['continue'])
    settle(s)
    assert len(s.state.zones['p2:graveyard']) == len(selected)
    assert not s.state.zones.get('p2:library')
    assert not s.state.rules.decision and not s.state.rules.draw_reason
    roundtrip(s)


def test_source_departure_does_not_end_the_resolving_ability(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, selected = setup(cards, ['Shock', 'Shock', 'Sol Ring', 'Ornithopter'])
    mana(s, C=3)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert all(s.state.cards[c].zone == 'p2:graveyard' for c in selected)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_voidwalker_marks_exiled_cards_once_despite_permanent_counter_multipliers(cards):
    from tests.test_rules_designations import put

    s, source, selected = setup(cards, ['Shock', 'Shock', 'Sol Ring', 'Ornithopter'])
    put(s, 'Dauthi Voidwalker', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield')
    grind(s, source)
    assert all(s.state.cards[c].zone == 'p2:exile' and s.state.cards[c].counters.get('void') == 1 for c in selected)


def test_prepared_exile_counter_helper_rejects_a_battlefield_recipient(cards):
    from app.rules.plan import Plan
    from app.rules.replacements import mark_exiled_counters

    s, source, _ = setup(cards, [])
    plan = Plan(s.state, 'p1', cards, None)
    with pytest.raises(ValueError, match='current exiled cards'):
        mark_exiled_counters(plan, [source.id], 'void', actor='p1')
    assert not plan.steps
