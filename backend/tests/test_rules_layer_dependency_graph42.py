"""Native layer positions, exact fixed-effect identity, and real dependency SCCs."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.state import CardInstance
from app.rules import group_layers, layers, selectors
from app.rules.characteristics import Characteristics
from app.rules.layer_dependency_graph import next_index, solve_field
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_characteristic_recipes39 import activate, ch
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table

DATA = Path(__file__).parent / 'fixtures/layer_dependency_graph42_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((DATA.parent / 'characteristic_recipes39_cards.json').read_text()) + json.loads(DATA.read_text())
    for i, row in enumerate(rows):
        base[row['name']] = card(row['name'], set_code='ldg42', number=str(i),
                                 **{k: v for k, v in row.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def intercycle():
    bases = {str(i): Characteristics(name=t, types=frozenset({t}))
             for i, t in enumerate(['Creature', 'Artifact', 'Land', 'Enchantment'])}
    solver = object.__new__(group_layers._Solver)
    solver.cards = {cid: CardInstance(id=cid, name=c.name, owner='p1', controller='p1', zone='p1:battlefield')
                    for cid, c in bases.items()}
    solver.view = None
    solver.state = SimpleNamespace(cards={})
    solver.at = lambda cid, key: bases[cid]
    solver.waited = {}
    def node(name, seq, types, add):
        return layers.Static(name, 'p1', {'layered': True, 'who': selectors.Selector(types=tuple(types)).key(),
                                         'layer4': {'add_types': [add]}}, seq)
    return solver, [node('A', 1, ['Creature', 'Enchantment'], 'Artifact'), node('B', 2, ['Artifact'], 'Creature'),
                    node('C', 3, ['Enchantment'], 'Land'), node('D', 4, ['Land'], 'Enchantment')]


def test_native_intercycle_respects_external_edges_before_timestamp():
    native, nodes = intercycle()
    edges = {(x.source, y.source) for x in nodes for y in nodes if x is not y and native._depends(x, y)}
    assert edges == {('A', 'B'), ('A', 'D'), ('B', 'A'), ('C', 'D'), ('D', 'C')}
    i = next_index([st.key for st in nodes], lambda x, y: native._depends(nodes[x], nodes[y]))
    assert nodes[i].source == 'C'


@pytest.fixture()
def native_scripts():
    from app.rules import scripts

    scripts._cached.cache_clear()
    yield
    scripts._cached.cache_clear()


def test_native_resolved_and_static_nodes_share_exact_position(cards, native_scripts):
    names = ['Neurok Transmuter', 'Sol Ring', 'March of the Machines']
    s = table(cards, names, names, names)
    ring = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Neurok Transmuter', 'battlefield')
    start(s)
    cast(s, 'March of the Machines')
    assert ch(s, ring).types == {'Artifact', 'Creature'}
    activate(s, source, "isn't an artifact", targets=[ring.id], target_counts=[1])
    solved = solve_field(s.state, s.cards, layers.statics(s.state, s.cards))
    base = layers.copiable(s.state, s.state.cards[ring.id], s.cards)
    assert solved.table.layer4(ring.id, base).types == frozenset()
    assert solved.table.layer4_orders[ring.id][0].effect is not None
    assert ch(s, ring).types == frozenset()
    from tests.test_rules_designations import roundtrip

    roundtrip(s)


def test_sequential_land_type_operations_replace_intrinsic_mana():
    from app.rules.layer_dependency_graph import Node, apply_type_node
    from app.rules.oracle import parse_abilities

    base = Characteristics(name='Land', types=frozenset({'Land'}),
                           abilities=tuple(parse_abilities('{T}: Add {C}.')))
    island = Node((1, 0, 0), definition={'layer4': {'add_subtypes': ['Island']}})
    mountain = Node((2, 0, 0), definition={'layer4': {'set_land_types': ['Mountain']}})
    artifact = Node((3, 0, 0), definition={'layer4': {'set_types': ['Artifact']}})
    ch1, _ = apply_type_node(island, base)
    assert {a.text for a in ch1.abilities} == {'{T}: Add {C}.', '{T}: Add {U}.'}
    ch2, stripped = apply_type_node(mountain, ch1)
    assert stripped and ch2.subtypes == {'Mountain'} and [a.text for a in ch2.abilities] == ['{T}: Add {R}.']
    ch3, _ = apply_type_node(artifact, ch2)
    assert ch3.types == {'Artifact'} and not ch3.subtypes and not ch3.abilities


@pytest.mark.parametrize('source_name', ['Kaito, Bane of Nightmares', 'Warden of the Wall'])
@pytest.mark.parametrize('wipe', ['Lignify', 'Darksteel Mutation', 'Humble'])
def test_actual_earlier_layer_form_survives_later_ability_loss(cards, source_name, wipe, tmp_path):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Kaito, Bane of Nightmares', 'Warden of the Wall', 'Lignify', 'Darksteel Mutation', 'Humble']
    s = table(cards, names, names, names)
    start(s)
    source = cast(s, source_name)
    pid = 'p1'
    if source_name == 'Warden of the Wall':
        to_phase(s, 'main1', turn=5)
        pid = 'p2'
    assert 'Creature' in ch(s, source).types
    effect = cast(s, wipe, [source.id], pid=pid, target_counts=[1])
    current = ch(s, source)
    types = {'Creature'} if source_name.startswith('Kaito') else {'Artifact', 'Creature'}
    subtypes = {'Ninja'} if source_name.startswith('Kaito') else {'Gargoyle'}
    pt = (0, 1)
    if wipe == 'Lignify':
        subtypes, pt = {'Treefolk'}, (0, 4)
    if wipe == 'Darksteel Mutation':
        types, subtypes = {'Artifact', 'Creature'}, {'Insect'}
    assert current.types == types and current.subtypes == subtypes and current.pt == pt
    if wipe != 'Humble':
        assert s.state.cards[effect.id].attached_to == source.id and s.state.cards[effect.id].zone.endswith(':battlefield')
    assert not ({'flying', 'hexproof'} & current.keywords)
    if source_name.startswith('Kaito') and wipe == 'Lignify':
        import subprocess
        import sys

        saved = tmp_path / 'layered-self.json'
        saved.write_text(s.state.model_dump_json())
        worker = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
ch=Plan(s.state,'p1',repo,None).ch(s.state.cards[sys.argv[3]])
assert ch.types=={'Creature'} and ch.subtypes=={'Treefolk'} and ch.pt==(0,4)
assert 'hexproof' not in ch.keywords
roundtrip(s);repo.close()
"""
        result = subprocess.run([sys.executable, '-c', worker, str(saved), str(cards.db_path), source.id],
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
    roundtrip(s)


def test_actual_resolved_wipe_precedes_later_static_source_propagation(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    names = ['Opalescence', 'Fervor', 'Sludge Monster', 'Humble', 'Grizzly Bears']
    s = table(cards, names, names, names)
    fervor = put(s, 'Fervor', 'battlefield')
    put(s, 'Opalescence', 'battlefield')
    source = put(s, 'Sludge Monster', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[fervor.id], kind='slime', delta=1)
    start(s)
    assert 'haste' not in ch(s, bear).keywords
    cast(s, 'Humble', [source.id], target_counts=[1])
    assert ch(s, fervor).pt == (3, 3) and 'haste' in ch(s, bear).keywords
    roundtrip(s)


def test_plain_battlefield_skips_positions_but_preserves_static_effects(cards, monkeypatch):
    from app.rules import layer_dependency_graph as graph

    names = ['Fervor', 'Grizzly Bears']
    s = table(cards, names, names, names)
    put(s, 'Fervor', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    def forbidden(*args, **kwargs):
        raise AssertionError('unchanged battlefield constructed dependency positions')
    monkeypatch.setattr(graph.Solver, '__init__', forbidden)
    layers._STATIC_CACHE.clear()
    assert 'haste' in ch(s, bear).keywords
    assert ch(s, bear).types == {'Creature'}


def test_neurok_modes_order_and_cleanup_preserve_native_counters(cards, native_scripts):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Neurok Transmuter', 'Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, 'Neurok Transmuter', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    s.state.cards[bear.id].counters['+1/+1'] = 1
    start(s)
    activate(s, source, 'in addition', targets=[bear.id], target_counts=[1])
    assert ch(s, bear).types == {'Artifact', 'Creature'}
    assert ch(s, bear).colors == {'G'} and ch(s, bear).pt == (3, 3)
    activate(s, source, "isn't an artifact", targets=[bear.id], target_counts=[1])
    assert ch(s, bear).types == {'Creature'}
    assert ch(s, bear).colors == {'U'} and ch(s, bear).pt == (3, 3)
    activate(s, source, 'in addition', targets=[bear.id], target_counts=[1])
    assert ch(s, bear).types == {'Artifact', 'Creature'} and ch(s, bear).colors == {'U'}
    to_phase(s, 'main1', turn=5)
    assert ch(s, bear).types == {'Creature'}
    assert ch(s, bear).colors == {'G'} and ch(s, bear).pt == (3, 3)
    roundtrip(s)


@pytest.mark.parametrize('blink', ['source', 'target'])
def test_neurok_pending_effect_tracks_source_and_target_incarnations(cards, native_scripts, blink, tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    names = ['Neurok Transmuter', 'Sol Ring', 'March of the Machines', 'Cloudshift']
    s = table(cards, names, names, names)
    ring = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Neurok Transmuter', 'battlefield')
    start(s)
    cast(s, 'March of the Machines')
    ability = next(a for a in ch(s, source).abilities if "isn't an artifact" in a.text)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, U=10, W=10, C=10)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
        targets=[ring.id], target_counts=[1])
    import subprocess
    import sys

    saved = tmp_path / 'pending.json'
    saved.write_text(s.state.model_dump_json())
    worker = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_declaration_requirements33 import cast
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
ring,source,blink=sys.argv[3:]
target=source if blink=='source' else ring
old=s.state.rules.object_id(target)
cast(s,'Cloudshift',targets=[target])
assert s.state.rules.object_id(target)!=old
ch=Plan(s.state,'p1',repo,None).ch(s.state.cards[ring])
assert ch.types==(frozenset() if blink=='source' else {'Artifact','Creature'})
assert ch.colors==({'U'} if blink=='source' else frozenset())
roundtrip(s);repo.close()
"""
    result = subprocess.run([sys.executable, '-c', worker, str(saved), str(cards.db_path),
                             ring.id, source.id, blink], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    old = s.state.rules.object_id((source if blink == 'source' else ring).id)
    cast(s, 'Cloudshift', targets=[(source if blink == 'source' else ring).id])
    assert s.state.rules.object_id((source if blink == 'source' else ring).id) != old
    if blink == 'source':
        assert ch(s, ring).types == frozenset() and ch(s, ring).colors == {'U'}
        assert any('{C}' in a.text for a in ch(s, ring).abilities)
    else:
        assert ch(s, ring).types == {'Artifact', 'Creature'} and not ch(s, ring).colors
    roundtrip(s)


def test_neurok_independent_of_later_march_timestamp_and_cleanup(cards, native_scripts):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Neurok Transmuter', 'Sol Ring', 'March of the Machines', 'Flicker of Fate']
    s = table(cards, names, names, names)
    ring = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Neurok Transmuter', 'battlefield')
    start(s)
    march = cast(s, 'March of the Machines')
    activate(s, source, "isn't an artifact", targets=[ring.id], target_counts=[1])
    assert ch(s, ring).types == frozenset()
    old = s.state.rules.object_id(march.id)
    cast(s, 'Flicker of Fate', targets=[march.id])
    assert s.state.rules.object_id(march.id) != old
    assert ch(s, ring).types == frozenset() and ch(s, ring).colors == {'U'}
    to_phase(s, 'main1', turn=5)
    assert ch(s, ring).types == {'Artifact', 'Creature'} and not ch(s, ring).colors
    assert ch(s, ring).pt == (1, 1)
    roundtrip(s)


def test_neurok_resolved_membership_survives_actual_control_change(cards, native_scripts):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Neurok Transmuter', 'Sol Ring', 'March of the Machines', 'Confiscate']
    s = table(cards, names, names, names)
    ring = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Neurok Transmuter', 'battlefield')
    start(s)
    cast(s, 'March of the Machines')
    from tests.game_helpers import act

    to_phase(s, 'main1', turn=5)
    while s.state.rules.priority != 'p1':
        act(s, s.state.rules.priority, type='pass_priority')
    activate(s, source, "isn't an artifact", targets=[ring.id], target_counts=[1])
    old = s.state.rules.object_id(ring.id)
    cast(s, 'Confiscate', targets=[ring.id], pid='p2')
    assert s.state.cards[ring.id].controller == 'p2' and s.state.rules.object_id(ring.id) == old
    assert ch(s, ring).types == frozenset() and ch(s, ring).colors == {'U'}
    incoming = s.state.cards[ring.id].model_copy(update={'controller': 'p3'})
    base = layers.copiable(s.state, incoming, s.cards)
    assert layers.derive(s.state, incoming, base, s.cards).types == frozenset()
    assert ch(s, ring).types == frozenset()
    to_phase(s, 'main1', turn=6)
    assert ch(s, ring).types == {'Artifact', 'Creature'} and not ch(s, ring).colors
    roundtrip(s)


def test_neurok_countered_activation_creates_no_continuous_effect(cards, native_scripts):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    names = ['Neurok Transmuter', 'Sol Ring', 'March of the Machines', 'Stifle']
    s = table(cards, names, names, names)
    ring = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Neurok Transmuter', 'battlefield')
    start(s)
    cast(s, 'March of the Machines')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, U=10, C=10)
    ability = next(a for a in ch(s, source).abilities if "isn't an artifact" in a.text)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
        targets=[ring.id], target_counts=[1])
    pending = s.state.zones['stack'][-1]
    cast(s, 'Stifle', targets=[pending])
    assert not s.state.zones['stack']
    assert ch(s, ring).types == {'Artifact', 'Creature'} and not ch(s, ring).colors
    roundtrip(s)


def test_neurok_whole_canonical_card_supported(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve('Neurok Transmuter')).level == 'FULL'
