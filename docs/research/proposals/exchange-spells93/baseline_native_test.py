from tests.test_rules_spell_control import cards
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_designations import put
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.game_helpers import act


def test_native_nonowner_controller_concedes_restores_original_caster93(cards):
    s = table(cards, ['Aethersnatch'], ['Grizzly Bears'], ['Sol Ring'])
    bear = put(s, 'Grizzly Bears', 'hand', pid='p2')
    steal = put(s, 'Aethersnatch', 'hand')
    start(s, turn=5)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    mana(s, pid='p2', C=1, G=1)
    act(s, 'p2', type='cast_spell', card_id=bear.id)
    wait_priority(s, 'p1')
    mana(s, C=4, U=2)
    act(s, 'p1', type='cast_spell', card_id=steal.id, targets=[bear.id])
    for _ in range(20):
        if steal.zone != 'stack':
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert bear.zone == 'stack' and bear.controller == 'p1'
    act(s, 'p1', type='concede')
    assert bear.zone == 'stack' and bear.controller == 'p2'
