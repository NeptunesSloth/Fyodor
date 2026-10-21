"""Native grouped-token replacement foundations; admission hooks land separately."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.rules_state import ObjectRef
from app.rules import token_creation_replacements as grouped
from app.rules.plan import Plan
from app.rules.replace import Candidate
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put
from tests.test_rules_linked_aggregates import cast
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/token_creation_replacements_cards.json').read_text())
NAMES = [c['name'] for c in DATA[:5]]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='tor', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return table(cards, [c['name'] for c in DATA], [c['name'] for c in DATA], [c['name'] for c in DATA])


def candidate(plan, source, definition):
    return Candidate(id='s:' + plan.oid(source) + ':0', event='tokens', match=definition['match'], op=definition['op'],
                     controller=source.controller, source_card=source.id, source_oid=plan.oid(source), seq=(1, 0, 0), label=source.name)


def parts():
    return [{'kind': 'tokens', 'player': 'p1', 'count': 1,
             'token': {'name': 'Soldier', 'power': '1', 'toughness': '1', 'colors': ['W'], 'type_line': 'Token Creature — Soldier', 'text': ''},
             'effect_tapped': True, 'recipient_ref': 'p2'},
            {'kind': 'tokens', 'player': 'p1', 'count': 2,
             'token': {'name': 'Treasure', 'type_line': 'Token Artifact — Treasure', 'text': '{T}, Sacrifice this token: Add one mana of any color.'},
             'effect_tapped': False, 'recipient_ref': 'p3'}]


def test_foundation_one_jinnie_choice_transforms_all_kinds_and_preserves_ancestry(cards):
    s = setup(cards)
    source = put(s, NAMES[0], 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    d = grouped.definition(cards.resolve(NAMES[0])['oracle_text'])
    assert d is not None
    c = candidate(plan, source, d)
    group = grouped.TokenCreationGroup(player='p1', parts=parts())
    receipt = grouped.snapshot(plan, c, group, 'dog')
    result = grouped.apply(plan, c, group, receipt)
    assert [p['count'] for p in result.parts] == [1, 2]
    assert all(p['token']['name'] == 'Dog' and p['token']['text'] == 'Vigilance' for p in result.parts)
    assert [p['effect_tapped'] for p in result.parts] == [True, False]
    assert [p['recipient_ref'] for p in result.parts] == ['p2', 'p3']
    assert grouped.TokenCreationGroup.model_validate_json(result.model_dump_json()) == result


def test_foundation_decline_spends_opportunity_for_modified_event(cards):
    s = setup(cards)
    source = put(s, NAMES[0], 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    d = grouped.definition(cards.resolve(NAMES[0])['oracle_text'])
    assert d is not None
    c = candidate(plan, source, d)
    group = grouped.TokenCreationGroup(player='p1', parts=parts())
    multiplier = Candidate(id='double', event='tokens', match={'who': 'you'}, op={'do': 'mul', 'n': 2}, controller='p1',
                           source_card=None, source_oid=None, seq=(2,), label='Double')
    after_multiplier = grouped.apply(plan, multiplier, group)
    assert c in grouped.applicable(plan, [c], after_multiplier, frozenset())
    after_decline = grouped.apply(plan, multiplier, grouped.decline(group, c))
    assert not grouped.applicable(plan, [c], after_decline, frozenset())


def test_foundation_first_creation_before_source_arrives_is_still_recorded(cards):
    s = setup(cards)
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    settle(s)
    source = put(s, 'Esix, Fractal Bloom', 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    d = grouped.definition('The first time you would create one or more tokens during each of your turns, you may instead choose a creature other than ~ and create that many tokens that are copies of that creature.')
    assert d is not None
    c = candidate(plan, source, d)
    prior = grouped.prior_creators(plan)
    assert 'p1' in prior
    assert not grouped.eligible(plan, c, grouped.TokenCreationGroup(player='p1', parts=parts()), prior)


def test_foundation_copy_receipt_is_copiable_recipe_and_exact_refs(cards):
    s = setup(cards)
    source = put(s, 'Esix, Fractal Bloom', 'battlefield')
    original = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[original.id], kind='+1/+1', delta=2)
    plan = Plan(s.state, 'p1', cards, None)
    d = grouped.definition('The first time you would create one or more tokens during each of your turns, you may instead choose a creature other than ~ and create that many tokens that are copies of that creature.')
    assert d is not None
    c = candidate(plan, source, d)
    receipt = grouped.snapshot(plan, c, grouped.TokenCreationGroup(player='p1', parts=parts()), 'apply', original.id)
    assert receipt.original == ObjectRef(card=original.id, object_id=plan.oid(original), zone=original.zone)
    restored = grouped.TokenReplacementChoice.model_validate_json(receipt.model_dump_json())
    from app.rules import copying
    assert restored.recipe is not None
    ch = copying.characteristics(restored.recipe, plan.info)
    assert (ch.power, ch.toughness) == ('2', '2')


@pytest.mark.parametrize('replacement_first', [False, True])
def test_foundation_genuine_order_changes_whether_added_food_is_replaced(cards, replacement_first):
    s = setup(cards)
    source = put(s, NAMES[0], 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    d = grouped.definition(cards.resolve(NAMES[0])['oracle_text'])
    assert d is not None
    jinnie = candidate(plan, source, d)
    food = Candidate(id='food', event='tokens', match={'who': 'you'},
                     op={'do': 'extra', 'n': 1, 'token': {'name': 'Food', 'type_line': 'Token Artifact — Food', 'text': ''}},
                     controller='p1', source_card=None, source_oid=None, seq=(2,), label='Peregrin Took')
    group = grouped.TokenCreationGroup(player='p1', parts=parts())
    answers = {}
    receipts = []
    for _ in range(4):
        try:
            result = grouped.plan_group(plan, 'one', [jinnie, food], group, frozenset(), answers, receipts)
            break
        except grouped.GroupQuestion as q:
            wanted = jinnie.id + '|dog' if replacement_first or len(answers) else 'food|apply'
            assert wanted in q.commands.values()
            answers[q.fingerprint] = wanted
    else:
        raise AssertionError('The grouped choice did not finish')
    assert sum(p['count'] for p in result.parts) == 4
    assert sum(p['count'] for p in result.parts if p['token']['name'] == 'Food') == int(replacement_first)
    assert sum(p['count'] for p in result.parts if p['token']['name'] == 'Dog') == (3 if replacement_first else 4)


def test_foundation_explicit_decline_is_not_offered_again_after_multiplier(cards):
    s = setup(cards)
    source = put(s, NAMES[0], 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    d = grouped.definition(cards.resolve(NAMES[0])['oracle_text'])
    assert d is not None
    jinnie = candidate(plan, source, d)
    multiplier = Candidate(id='double', event='tokens', match={'who': 'you'}, op={'do': 'mul', 'n': 2}, controller='p1',
                           source_card=None, source_oid=None, seq=(2,), label='Double')
    group = grouped.TokenCreationGroup(player='p1', parts=parts())
    with pytest.raises(grouped.GroupQuestion) as raised:
        grouped.plan_group(plan, 'one', [jinnie, multiplier], group, frozenset(), {}, [])
    q = raised.value
    result = grouped.plan_group(plan, 'one', [jinnie, multiplier], group, frozenset(), {q.fingerprint: jinnie.id + '|decline'}, [])
    assert sum(p['count'] for p in result.parts) == 6
    assert {p['token']['name'] for p in result.parts} == {'Soldier', 'Treasure'}


def test_foundation_commuting_multipliers_need_no_order_question(cards):
    s = setup(cards)
    plan = Plan(s.state, 'p1', cards, None)
    candidates = [Candidate(id=str(n), event='tokens', match={'who': 'you'}, op={'do': 'mul', 'n': n}, controller='p1',
                            source_card=None, source_oid=None, seq=(n,), label=str(n)) for n in (2, 3)]
    result = grouped.plan_group(plan, 'one', candidates, grouped.TokenCreationGroup(player='p1', parts=parts()), frozenset(), {}, [])
    assert sum(p['count'] for p in result.parts) == 18


def tokens(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]


def choose_label(s, word):
    from tests.test_rules_conditionals import until

    until(s, lambda x: x.state.rules.decision is not None, limit=30)
    d = s.state.rules.decision
    option = next((o for o in d.options if word.lower() in o.label.lower()), None)
    assert option is not None, (d.prompt, [(o.id, o.label) for o in d.options])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])


@pytest.mark.parametrize('mode,name,pt,keyword', [('Cats', 'Cat', (2, 2), 'Haste'), ('Dogs', 'Dog', (3, 1), 'Vigilance'), ('Decline', 'Soldier', (1, 1), None)])
def test_actual_jinnie_native_spell_all_branches(cards, mode, name, pt, keyword):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    spell = put(s, 'Raise the Alarm', 'hand')
    cast(s, spell)
    choose_label(s, mode)
    settle(s)
    made = tokens(s)
    assert len(made) == 2 and all(ch(s, c).name == name and ch(s, c).pt == pt for c in made)
    if keyword:
        assert all(keyword.lower() in ch(s, c).keywords for c in made)
    roundtrip(s)


def test_actual_esix_native_non_target_original_and_copy_recipe(cards):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    source = put(s, NAMES[1], 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p2', type='counter', card_ids=[bear.id], kind='+1/+1', delta=3)
    assert 'flying' in ch(s, source).keywords
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    choose_label(s, 'Apply')
    until(s, lambda x: x.state.rules.decision is not None, limit=30)
    d = s.state.rules.decision
    assert source.id not in {o.id for o in d.options} and bear.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).name == 'Grizzly Bears' and ch(s, c).pt == (2, 2) for c in tokens(s))
    roundtrip(s)


def test_explicit_creation_atoms_preserve_fixed_addition_defenders(cards):
    """Foreach actions remain simultaneous, with one replacement per action."""
    s = setup(cards)
    plan = Plan(s.state, 'p1', cards, None)
    original = parts()
    original[0]['creation_atom'] = 'opponent:p2'
    original[1]['creation_atom'] = 'opponent:p3'
    groups = grouped.initial_groups(plan, original)
    assert len(groups) == 2
    extra = Candidate(id='frog', event='tokens', match={'who': 'you'},
                      op={'do': 'extra', 'n': 1, 'token': {'name': 'Frog', 'type_line': 'Token Creature — Frog', 'text': ''}},
                      controller='p1', source_card=None, source_oid=None, seq=(1,), label='Quina')
    results = [grouped.apply(plan, extra, group) for group in groups]
    assert [group.parts[-1]['recipient_ref'] for group in results] == ['p2', 'p3']
    assert all('creation_ancestry' not in group.parts[-1] for group in results)
    # Metadata alone must never split a heterogeneous instruction.
    for part in original:
        part.pop('creation_atom')
    assert len(grouped.initial_groups(plan, original)) == 1


def test_creator_change_does_not_merge_explicit_creation_atoms(cards):
    s = setup(cards)
    plan = Plan(s.state, 'p1', cards, None)
    original = parts()
    original[0]['creation_atom'] = 'one'
    original[1]['creation_atom'] = 'two'
    original[1]['player'] = 'p2'
    change = Candidate(id='creator', event='tokens', match={}, op={'do': 'set_creator'},
                       controller='p1', source_card=None, source_oid=None, seq=(1,), label='Creator')
    groups = grouped.creator_groups(plan, 'test', [change], grouped.initial_groups(plan, original), {})
    assert len(groups) == 2 and all(g.player == 'p1' for g in groups)
    assert [g.parts[0]['creation_atom'] for g in groups] == ['one', 'two']


@pytest.mark.parametrize('first', ['Jinnie', 'Peregrin'])
def test_actual_jinnie_and_fixed_addition_order_survives_cold(cards, tmp_path, first):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    put(s, 'Peregrin Took', 'battlefield')
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    until(s, lambda x: x.state.rules.decision is not None)
    d = s.state.rules.decision
    word = 'create Dogs' if first == 'Jinnie' else 'Apply Peregrin'
    option = next(o for o in d.options if word in o.label)
    s = cold_choose(s, cards, tmp_path, [option.id])
    if first == 'Peregrin':
        choose_label(s, 'Dogs')
    settle(s)
    made = tokens(s)
    assert len(made) == 3
    assert sum(ch(s, c).name == 'Food' for c in made) == int(first == 'Jinnie')
    assert sum(ch(s, c).name == 'Dog' for c in made) == (2 if first == 'Jinnie' else 3)
    roundtrip(s)


def test_actual_jinnie_whole_mixed_instruction_discards_original_keywords(cards, tmp_path):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    wurm = put(s, 'Wurmcoil Engine', 'battlefield')
    act(s, 'p1', type='set_damage', card_ids=[wurm.id], delta=20)
    act(s, s.state.rules.priority or 'p1', type='pass_priority')
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and any('create Cats' in o.label for o in d.options):
            break
        if d is not None:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    cat = next(o for o in d.options if 'create Cats' in o.label)
    s = cold_choose(s, cards, tmp_path, [cat.id])
    settle(s)
    assert len(tokens(s)) == 2
    assert all(ch(s, c).name == 'Cat' and ch(s, c).keywords == frozenset({'haste'}) for c in tokens(s))
    roundtrip(s)


def test_actual_jinnie_missing_source_and_other_creator_stay_unchanged(cards):
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    put(s, NAMES[0], 'battlefield', pid='p2')
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).name == 'Soldier' for c in tokens(s))
    s = setup(cards)
    source = put(s, NAMES[0], 'battlefield')
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).name == 'Soldier' for c in tokens(s))


@pytest.mark.parametrize('level,expected', [(1, 'Fish'), (2, 'Shark'), (3, 'Octopus')])
def test_actual_fisher_upkeep_native_levels_and_same_top_draw(cards, level, expected):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_wave16a_class import bar
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, "Fisher's Talent", 'battlefield')
    mana(s, 'p1', G=4, U=4, C=4)
    for n in range(2, level + 1):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=bar(s, source, n))
        settle(s)
    top = put(s, 'Hallowed Fountain', 'library')
    act(s, 'p1', type='move', card_ids=[top.id], to={'zone': 'library'}, position='top')
    to_phase(s, 'upkeep', turn=4)
    until(s, lambda x: x.state.rules.decision is not None)
    d = s.state.rules.decision
    assert top.id in {o.id for o in d.options}, (d.prompt, d.options)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[top.id])
    settle(s)
    assert s.state.cards[top.id].zone == 'p1:hand'
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == expected
    roundtrip(s)


def test_actual_foreach_quina_addition_and_jinnie_declines_keep_each_defender(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Ainok Strike Leader', 'battlefield')
    put(s, 'Quina, Qu Gourmet', 'battlefield')
    put(s, NAMES[0], 'battlefield')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    # Each foreach action spends its own optional opportunity. Applying Quina
    # first must not cause its added Frog to inherit the other action's defender.
    for _ in range(50):
        d = s.state.rules.decision
        if d is not None:
            wanted = next((o for o in d.options if 'Apply Quina' in o.label), None)
            wanted = wanted or next((o for o in d.options if 'Decline Jinnie' in o.label), None)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[(wanted or d.options[0]).id])
        elif not s.state.rules.stack:
            break
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    made = tokens(s)
    assert len(made) == 4
    for defender in ('p2', 'p3'):
        assigned = [c for c in made if c.attacking is not None and c.attacking.id == defender]
        assert len(assigned) == 2 and {ch(s, c).name for c in assigned} == {'Goblin', 'Frog'}
        assert all(c.tapped for c in assigned)
    roundtrip(s)


def wait_token_question(s):
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get('fp', '').startswith('token_group:'):
            return d
        if d is not None:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('No grouped token question')


def esix_original(s, original):
    d = wait_token_question(s)
    option = next(o for o in d.options if 'Apply Esix' in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    d = wait_token_question(s)
    assert original.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[original.id])


@pytest.mark.parametrize('first', ['decline', 'before_source', 'copy'])
def test_actual_esix_first_history_sequential_instructions(cards, first):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    if first != 'before_source':
        put(s, 'Esix, Fractal Bloom', 'battlefield')
    spell = put(s, 'Raise the Alarm', 'hand')
    cast(s, spell)
    if first == 'decline':
        choose_label(s, 'Decline Esix')
    elif first == 'copy':
        esix_original(s, bear)
    settle(s)
    if first == 'before_source':
        put(s, 'Esix, Fractal Bloom', 'battlefield')
    act(s, 'p1', type='move', card_ids=[spell.id], to={'zone': 'hand'})
    cast(s, s.state.cards[spell.id])
    settle(s)
    assert s.state.rules.decision is None
    names = [ch(s, c).name for c in tokens(s)]
    assert names.count('Soldier') == (2 if first == 'copy' else 4)
    assert names.count('Grizzly Bears') == (2 if first == 'copy' else 0)
    roundtrip(s)


def test_actual_esix_simultaneous_atoms_have_independent_cold_original_choices(cards, tmp_path):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Ainok Strike Leader', 'battlefield')
    put(s, 'Esix, Fractal Bloom', 'battlefield')
    put(s, 'Quina, Qu Gourmet', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    ghoul = put(s, 'Diregraf Ghoul', 'battlefield', pid='p2')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    # Fixed addition first participates in Esix; second atom gets a different
    # original, proving a first atom's recipe receipt cannot leak to the second.
    for original in (bear, ghoul):
        d = wait_token_question(s)
        extra = next(o for o in d.options if 'Apply Quina' in o.label)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[extra.id])
        d = wait_token_question(s)
        apply = next(o for o in d.options if 'Apply Esix' in o.label)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[apply.id])
        d = wait_token_question(s)
        s = cold_choose(s, cards, tmp_path, [original.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 4
    for defender, name in [('p2', 'Grizzly Bears'), ('p3', 'Diregraf Ghoul')]:
        assigned = [c for c in made if c.attacking is not None and c.attacking.id == defender]
        assert len(assigned) == 2 and all(ch(s, c).name == name and c.tapped for c in assigned)
    roundtrip(s)


@pytest.mark.parametrize('name,host_name', [('Moonlit Meditation', 'Grizzly Bears'), ('Moonlit Meditation', 'Bonesplitter'), ('Mirrormind Crown', 'Grizzly Bears')])
def test_actual_attached_replacements_cast_equip_and_cold_copy(cards, tmp_path, name, host_name):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import activate, ch
    from tests.test_rules_linked_return_family import cold_choose

    s = setup(cards)
    host = put(s, host_name, 'battlefield')
    source = put(s, name, 'hand')
    cast(s, source, **({'targets': [host.id]} if name == 'Moonlit Meditation' else {}))
    settle(s)
    if name == 'Mirrormind Crown':
        activate(s, source, ability=1, targets=[host.id])
        settle(s)
    assert s.state.cards[source.id].attached_to == host.id
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    d = wait_token_question(s)
    option = next(o for o in d.options if o.label.startswith('Apply '))
    s = cold_choose(s, cards, tmp_path, [option.id])
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).name == host_name for c in tokens(s))
    roundtrip(s)


@pytest.mark.parametrize('name', ['Moonlit Meditation', 'Mirrormind Crown'])
@pytest.mark.parametrize('first', ['decline', 'before_attached'])
def test_actual_attached_first_history_survives_decline_and_late_attachment(cards, name, first):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import activate, ch

    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, name, 'hand')
    if first == 'decline':
        cast(s, source, **({'targets': [host.id]} if name == 'Moonlit Meditation' else {}))
        settle(s)
        if name == 'Mirrormind Crown':
            activate(s, source, ability=1, targets=[host.id])
            settle(s)
    elif name == 'Mirrormind Crown':
        cast(s, source)
        settle(s)
    spell = put(s, 'Raise the Alarm', 'hand')
    cast(s, spell)
    if first == 'decline':
        choose_label(s, 'Decline')
    settle(s)
    if first == 'before_attached':
        if name == 'Moonlit Meditation':
            cast(s, source, targets=[host.id])
        else:
            activate(s, source, ability=1, targets=[host.id])
        settle(s)
    act(s, 'p1', type='move', card_ids=[spell.id], to={'zone': 'hand'})
    cast(s, s.state.cards[spell.id])
    settle(s)
    assert s.state.rules.decision is None
    assert len(tokens(s)) == 4 and all(ch(s, c).name == 'Soldier' for c in tokens(s))
    roundtrip(s)


@pytest.mark.parametrize('topname,accept', [('Hallowed Fountain', False), ('Grizzly Bears', False)])
def test_actual_fisher_optional_land_reveal_negatives_and_cold_draw(cards, tmp_path, topname, accept):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, "Fisher's Talent", 'battlefield')
    top = put(s, topname, 'library')
    act(s, 'p1', type='move', card_ids=[top.id], to={'zone': 'library'}, position='top')
    to_phase(s, 'upkeep', turn=4)
    if topname == 'Hallowed Fountain':
        until(s, lambda x: x.state.rules.decision is not None)
        d = s.state.rules.decision
        assert d.min_choices == 0 and top.id in {o.id for o in d.options}
        s = cold_choose(s, cards, tmp_path, [])
    settle(s)
    assert s.state.cards[top.id].zone == 'p1:hand' and not tokens(s)
    assert '*' not in s.state.cards[top.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('name', ['Esix, Fractal Bloom', 'Moonlit Meditation', 'Mirrormind Crown'])
def test_actual_first_replacement_own_turn_scope_and_other_turn_scope(cards, name):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import activate, ch
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, name, 'hand')
    cast(s, source, **({'targets': [host.id]} if name == 'Moonlit Meditation' else {}))
    settle(s)
    if name == 'Mirrormind Crown':
        activate(s, source, ability=1, targets=[host.id])
        settle(s)
    to_phase(s, 'upkeep', turn=2)
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    if name != 'Esix, Fractal Bloom':
        choose_label(s, 'Apply')
    settle(s)
    assert len(tokens(s)) == 2
    assert all(ch(s, c).name == ('Soldier' if name == 'Esix, Fractal Bloom' else 'Grizzly Bears') for c in tokens(s))
    roundtrip(s)


def test_cold_receipt_identity_is_independent_after_creator_convergence(cards):
    s = setup(cards)
    source = put(s, NAMES[0], 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    d = grouped.definition(cards.resolve(NAMES[0])['oracle_text'])
    optional = candidate(plan, source, d)
    original = parts()
    original[1] = {**original[0], 'player': 'p2'}
    groups = grouped.initial_groups(plan, original)
    change = Candidate(id='creator', event='tokens', match={}, op={'do': 'set_creator'},
                       controller='p1', source_card=None, source_oid=None, seq=(1,), label='Creator')
    groups = grouped.creator_groups(plan, 'one', [change], groups, {})
    receipt = grouped.snapshot(plan, optional, groups[0], 'cat')
    restored = grouped.TokenReplacementChoice.model_validate_json(receipt.model_dump_json())
    groups[1].choices.append(restored)
    assert grouped.receipt_for(optional, groups[1]) is None
    assert grouped.fingerprint('one', groups[0], [optional]) != grouped.fingerprint('one', groups[1], [optional])


def test_actual_esix_clone_recipe_then_each_token_independent_entry_choices_cold(cards, tmp_path):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose

    s = setup(cards)
    put(s, 'Glorious Anthem', 'battlefield')
    original = put(s, 'Clone', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[original.id], kind='+1/+1', delta=1)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    ghoul = put(s, 'Diregraf Ghoul', 'battlefield', pid='p2')
    put(s, 'Esix, Fractal Bloom', 'battlefield')
    assert ch(s, original).name == 'Clone'
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    esix_original(s, original)
    for chosen in (bear, ghoul):
        until(s, lambda x: x.state.rules.decision is not None)
        d = s.state.rules.decision
        assert d.resume['fp'].startswith('enter:') and chosen.id in {o.id for o in d.options}
        s = cold_choose(s, cards, tmp_path, [chosen.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 2 and {ch(s, c).name for c in made} == {'Grizzly Bears', 'Diregraf Ghoul'}
    assert all(not c.counters for c in made)
    roundtrip(s)


def test_actual_cutpurse_final_creator_chooses_esix_and_consumes_only_final_history(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    put(s, 'Esix, Fractal Bloom', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, put(s, 'Crafty Cutpurse', 'hand'))
    settle(s)
    spell = put(s, 'Raise the Alarm', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', W=1, C=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    d = wait_token_question(s)
    assert d.player == 'p1'
    esix_original(s, bear)
    settle(s)
    assert len(tokens(s)) == 2 and all(c.owner == c.controller == 'p1' and ch(s, c).name == 'Grizzly Bears' for c in tokens(s))
    plan = Plan(s.state, 'p1', cards, None)
    assert grouped.prior_creators(plan) == frozenset({'p1'})
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    settle(s)
    assert s.state.rules.decision is None
    assert sum(ch(s, c).name == 'Soldier' for c in tokens(s)) == 2
    roundtrip(s)


@pytest.mark.parametrize('first', ['jinnie', 'esix'])
def test_actual_two_optional_sources_can_override_in_either_legal_order(cards, first):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    put(s, 'Esix, Fractal Bloom', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    if first == 'jinnie':
        choose_label(s, 'Dogs')
        esix_original(s, bear)
    else:
        esix_original(s, bear)
        choose_label(s, 'Dogs')
    settle(s)
    expected = 'Grizzly Bears' if first == 'jinnie' else 'Dog'
    assert len(tokens(s)) == 2 and all(ch(s, c).name == expected for c in tokens(s))
    roundtrip(s)


def test_actual_fisher_empty_library_creates_nothing_and_still_attempts_draw(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, "Fisher's Talent", 'battlefield')
    library = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=library, to={'zone': 'graveyard'})
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert not tokens(s)
    assert 'p1' in s.state.rules.drew_from_empty or s.state.players['p1'].left


def test_grouped_xorn_adds_one_normal_treasure_across_matching_parts(cards):
    s = setup(cards)
    plan = Plan(s.state, 'p1', cards, None)
    a = parts()[1]
    a.pop('recipient_ref')
    b = {**a, 'count': 1, 'token': {**a['token'], 'text': 'Flying'}}
    group = grouped.TokenCreationGroup(player='p1', parts=[a, b])
    xorn = Candidate(id='xorn', event='tokens', match={'who': 'you', 'subtypes': ['Treasure']},
                     op={'do': 'add', 'n': 1}, controller='p1', source_card=None, source_oid=None,
                     seq=(1,), label='Xorn')
    result = grouped.apply(plan, xorn, group)
    assert sum(p['count'] for p in result.parts) == 4
    assert result.parts[-1]['token']['name'] == 'Treasure'
    assert 'Flying' not in result.parts[-1]['token']['text']


@pytest.mark.parametrize('name', NAMES)
def test_canonical_full_card_admission_after_actual_native_proofs(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_actual_doppelgang_foreach_original_has_independent_optional_choices(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Diregraf Ghoul', 'battlefield', pid='p2')
    cast(s, put(s, 'Doppelgang', 'hand'), x_value=2, targets=[a.id, b.id], target_counts=[2])
    choose_label(s, 'Cats')
    choose_label(s, 'Dogs')
    settle(s)
    assert len(tokens(s)) == 4
    assert sorted(ch(s, c).name for c in tokens(s)) == ['Cat', 'Cat', 'Dog', 'Dog']
    roundtrip(s)


def test_actual_zero_doppelgang_does_not_consume_first_creation(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    put(s, 'Esix, Fractal Bloom', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, put(s, 'Doppelgang', 'hand'), x_value=0, targets=[], target_counts=[0])
    settle(s)
    assert not tokens(s) and not grouped.prior_creators(Plan(s.state, 'p1', cards, None))
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    esix_original(s, bear)
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).name == 'Grizzly Bears' for c in tokens(s))
    roundtrip(s)


def test_actual_foreach_attachment_atoms_preserve_distinct_fixed_hosts_after_swap(cards, tmp_path):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch, choose
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    dog = put(s, 'Three Dog, Galaxy News DJ', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    ghoul = put(s, 'Diregraf Ghoul', 'battlefield')
    original = put(s, 'Bonesplitter', 'battlefield')
    cast(s, put(s, 'Moonlit Meditation', 'hand'), targets=[original.id])
    settle(s)
    cast(s, put(s, 'Holy Strength', 'hand'), targets=[dog.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=4)
    mana(s, C=2)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in (dog, bear, ghoul)])
    choose(s, ['pay'])
    for _ in range(2):
        d = wait_token_question(s)
        apply = next(o for o in d.options if o.label.startswith('Apply Moonlit'))
        s = cold_choose(s, cards, tmp_path, [apply.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 2 and all(ch(s, c).name == 'Bonesplitter' for c in made)
    assert {c.attached_to for c in made} == {bear.id, ghoul.id}
    roundtrip(s)


def test_actual_destroy_all_per_controller_foreach_actions_choose_independently(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    a = put(s, 'Bonesplitter', 'battlefield')
    b = put(s, 'Mirrormind Crown', 'battlefield')
    cast(s, put(s, 'Rampage of the Clans', 'hand'))
    choose_label(s, 'Cats')
    choose_label(s, 'Dogs')
    settle(s)
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == 'p1:graveyard'
    assert sorted(ch(s, c).name for c in tokens(s)) == ['Cat', 'Dog']
    roundtrip(s)


def test_actual_adeline_replacements_then_each_created_creature_chooses_defender_cold(cards, tmp_path):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Adeline, Resplendent Cathar', 'battlefield')
    put(s, NAMES[0], 'battlefield')
    put(s, 'Parallel Lives', 'battlefield')
    walker = put(s, 'Jace Beleren', 'hand')
    cast(s, walker)
    settle(s)
    act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p2')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    for _ in range(2):
        d = wait_token_question(s)
        # Multiplication commutes with Jinnie's swap, but explicit decline of
        # one source must not suppress a different opponent's atom.
        choice = next(o for o in d.options if 'create Cats' in o.label)
        s = cold_choose(s, cards, tmp_path, [choice.id])
    assert s.state.rules.decision is not None, (s.state.turn, [(c.name, c.controller, c.attacking) for c in tokens(s)], s.state.cards[walker.id].zone)
    for destination in ('p2', walker.id):
        until(s, lambda x: x.state.rules.decision is not None)
        d = s.state.rules.decision
        assert d.resume['step'] == 'token_attack_created'
        assert {'p2', walker.id} == {o.id for o in d.options}
        s = cold_choose(s, cards, tmp_path, [destination])
    settle(s)
    made = tokens(s)
    assert len(made) == 4 and all(ch(s, c).name == 'Cat' and c.tapped for c in made)
    assert sorted(c.attacking.id for c in made) == sorted(['p2', walker.id, 'p3', 'p3'])
    roundtrip(s)


def test_actual_myriad_outer_resume_replacements_defenders_and_cleanup_cold(cards, tmp_path):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Scion of Calamity', 'battlefield')
    put(s, NAMES[0], 'battlefield')
    put(s, 'Parallel Lives', 'battlefield')
    walker = put(s, 'Jace Beleren', 'hand')
    cast(s, walker)
    settle(s)
    act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p3')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    until(s, lambda x: x.state.rules.decision is not None and x.state.rules.decision.resume['step'] == 'myriad_pick')
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p3'])
    d = wait_token_question(s)
    choice = next(o for o in d.options if 'create Cats' in o.label)
    s = cold_choose(s, cards, tmp_path, [choice.id])
    for destination in ('p3', walker.id):
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'token_attack_created'
        s = cold_choose(s, cards, tmp_path, [destination])
    settle(s)
    made = tokens(s)
    assert len(made) == 2 and all(ch(s, c).name == 'Cat' and c.tapped for c in made)
    assert {c.attacking.id for c in made} == {'p3', walker.id}
    roundtrip(s)
    to_phase(s, 'main2', turn=4)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_actual_encore_replacement_outputs_keep_each_forced_opponent_and_cleanup(cards, tmp_path):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import activate, ch
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave5c_combat import to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    put(s, 'Parallel Lives', 'battlefield')
    source = put(s, 'Exquisite Huntmaster', 'graveyard')
    to_phase(s, 'main1', turn=4)
    activate(s, source, ability=1)
    for mode in ('Dogs', 'Cats'):
        d = wait_token_question(s)
        option = next(o for o in d.options if 'create ' + mode in o.label)
        s = cold_choose(s, cards, tmp_path, [option.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 4
    assert all('haste' in ch(s, c).keywords for c in made)
    to_attack(s, 4)
    declarations = [{'card_id': c.id, 'target': 'p2' if ch(s, c).name == 'Dog' else 'p3'} for c in made]
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=declarations[:3])
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{**entry, 'target': 'p3'} for entry in declarations])
    act(s, 'p1', type='declare_attackers', attackers=declarations)
    settle(s)
    roundtrip(s)
    to_phase(s, 'end', turn=4)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


@pytest.mark.parametrize('change', ['controller', 'leave'])
def test_actual_saved_defender_choice_does_not_rebind_changed_planeswalker(cards, tmp_path, change):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Adeline, Resplendent Cathar', 'battlefield')
    walker = put(s, 'Jace Beleren', 'hand')
    cast(s, walker)
    settle(s)
    act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p2')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    until(s, lambda x: x.state.rules.decision is not None and x.state.rules.decision.resume['step'] == 'token_attack_created')
    d = s.state.rules.decision
    first = d.resume['item']['token']['card']
    if change == 'controller':
        act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p3')
    else:
        act(s, 'p1', type='move', card_ids=[walker.id], to={'zone': 'graveyard'})
    s = cold_choose(s, cards, tmp_path, [walker.id])
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.resume['step'] == 'token_attack_created'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert s.state.cards[first].attacking is None
    other = next(c for c in tokens(s) if c.id != first)
    assert other.attacking.id == 'p3'
    roundtrip(s)


def test_actual_redirected_noncreation_does_not_consume_first_creation(cards, tmp_path):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose

    s = setup(cards)
    host = put(s, 'Bonesplitter', 'battlefield')
    cast(s, put(s, 'Moonlit Meditation', 'hand'), targets=[host.id])
    settle(s)
    cast(s, put(s, 'Hallowed Moonlight', 'hand'))
    settle(s)
    spell = put(s, 'Raise the Alarm', 'hand')
    cast(s, spell)
    d = wait_token_question(s)
    option = next(o for o in d.options if o.label.startswith('Decline Moonlit'))
    s = cold_choose(s, cards, tmp_path, [option.id])
    settle(s)
    assert not tokens(s) and not grouped.prior_creators(Plan(s.state, 'p1', cards, None))
    act(s, 'p1', type='move', card_ids=[spell.id], to={'zone': 'hand'})
    cast(s, s.state.cards[spell.id])
    choose_label(s, 'Apply Moonlit')
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).name == 'Bonesplitter' for c in tokens(s))
    assert grouped.prior_creators(Plan(s.state, 'p1', cards, None)) == frozenset({'p1'})
    roundtrip(s)


def test_actual_esix_copy_recipe_retains_legendary_and_native_legend_choice_cold(cards, tmp_path):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose

    s = setup(cards)
    put(s, 'Esix, Fractal Bloom', 'battlefield')
    original = put(s, NAMES[0], 'battlefield', pid='p2')
    cast(s, put(s, 'Raise the Alarm', 'hand'))
    esix_original(s, original)
    until(s, lambda x: x.state.rules.decision is not None)
    d = s.state.rules.decision
    copies = tokens(s)
    assert len(copies) == 2 and all('Legendary' in ch(s, c).supertypes for c in copies)
    assert {o.id for o in d.options} == {c.id for c in copies}
    assert original.id not in {o.id for o in d.options}
    s = cold_choose(s, cards, tmp_path, [copies[0].id])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == NAMES[0]
    assert grouped.prior_creators(Plan(s.state, 'p1', cards, None)) == frozenset({'p1'})
    roundtrip(s)
