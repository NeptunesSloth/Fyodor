"""Subtype applicability in native layer-four dependency signatures."""
from dataclasses import replace

import pytest

from app.rules import layer_dependency_graph as graph
from app.rules.characteristics import Characteristics


def solver(types):
    s = object.__new__(graph.Solver)
    s.begun, s.removed = {}, set()
    s.position = graph.Position({'c': Characteristics(name='Object', types=frozenset(types))}, {})
    s.orders = {'c': []}
    return s


def node(seq, **op):
    return graph.Node((seq, 0, 0), definition={'layer4': op}, fixed=frozenset({'c'}))


def test_later_animation_is_dependency_for_earlier_creature_subtype():
    s = solver({'Artifact'})
    subtype, animate = node(1, add_subtypes=['Vampire']), node(2, add_types=['Creature'])
    s.schedule([subtype, animate])
    assert [n.key for n in s.orders['c']] == [(2, 0, 0), (1, 0, 0)]
    assert s.position.chars['c'].subtypes == {'Vampire'}
    assert (subtype.key, animate.key) == ((1, 0, 0), (2, 0, 0))


def test_self_setting_creature_does_not_depend_on_external_animation():
    s = solver({'Artifact'})
    form = node(1, set_types=['Creature'], set_creature_types=['Vampire'])
    animate = node(2, add_types=['Creature'])
    before = s.position
    after = s.apply4(animate, before, s.signature(animate, before))
    assert s.signature(form, before) == s.signature(form, after)
    s.schedule([form, animate])
    assert [n.key for n in s.orders['c']] == [(1, 0, 0), (2, 0, 0)]
    assert s.position.chars['c'].types == {'Creature'} and s.position.chars['c'].subtypes == {'Vampire'}


@pytest.mark.parametrize('kind', ['Kindred', 'Tribal'])
def test_kindred_creature_subtype_is_already_compatible_without_creature(kind):
    s = solver({kind, 'Artifact'})
    subtype, animate = node(1, add_subtypes=['Vampire']), node(2, add_types=['Creature'])
    before = s.position
    after = s.apply4(animate, before, s.signature(animate, before))
    assert s.signature(subtype, before) == s.signature(subtype, after)
    s.schedule([subtype, animate])
    assert s.orders['c'][0] is subtype and 'Vampire' in s.position.chars['c'].subtypes


@pytest.mark.parametrize('initial,new,expected', [
    ({'Land'}, 'Artifact', {'Island', 'Equipment'}),
    ({'Artifact'}, 'Land', {'Island', 'Equipment'}),
    ({'Creature'}, 'Artifact', {'Vampire', 'Equipment'}),
])
def test_basic_land_artifact_and_creature_subtypes_follow_their_own_type(initial, new, expected):
    s = solver(initial)
    subtype = node(1, add_subtypes=['Vampire', 'Island', 'Equipment'])
    add = node(2, add_types=[new])
    untouched = s.position
    snapshot = replace(untouched.chars['c'])
    s.schedule([subtype, add])
    assert s.position.chars['c'].subtypes == expected
    assert untouched.chars['c'] == snapshot
    assert s.orders['c'][-1] is subtype
