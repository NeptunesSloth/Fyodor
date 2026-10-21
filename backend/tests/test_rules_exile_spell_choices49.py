"""Spark exercised through production casting and permissions."""
import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_ordered_tutor_continuations import cast

cards=gameplay.cards


@pytest.mark.parametrize('damage',[False,True])
def test_spark_actual_exile_creature_damage_or_exact_normal_paid_cast(cards,damage):
    s=gameplay.setup(cards,'Spark of Creativity')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    top=put(s,'Divination','library')
    cast(s,'Spark of Creativity',targets=[target.id])
    assert s.state.cards[top.id].zone=='p1:exile'
    answer(s,['damage' if damage else 'play'])
    if damage:
        assert s.state.cards[target.id].zone=='p2:graveyard'
        assert not s.state.rules.permissions
    else:
        assert s.state.cards[target.id].zone=='p2:battlefield'
        act(s,'p1',type='clear_mana',player='p1')
        mana(s,U=1,C=2)
        act(s,'p1',type='cast_spell',card_id=top.id)
        from tests.test_rules_library_look import settle
        settle(s)
        assert s.state.cards[top.id].zone=='p1:graveyard'
        assert not s.state.players['p1'].mana
    roundtrip(s)


@pytest.mark.parametrize('damage',[False,True])
def test_spark_land_zero_damage_is_elected_action_or_real_normal_land_play(cards,damage):
    s=gameplay.setup(cards,'Spark of Creativity','Forest')
    target=put(s,'Grizzly Bears','battlefield')
    top=put(s,'Forest','library')
    cast(s,'Spark of Creativity',targets=[target.id])
    answer(s,['damage' if damage else 'play'])
    assert s.state.cards[target.id].damage==0
    if damage:
        assert not s.state.rules.permissions
        assert s.state.cards[top.id].zone=='p1:exile'
    else:
        act(s,'p1',type='play_land',card_id=top.id)
        assert s.state.cards[top.id].zone=='p1:battlefield'
        assert s.state.rules.lands_this_turn('p1',s.state.turn.number)==1
    roundtrip(s)


def test_spark_all_targets_illegal_does_not_exile_library_top(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Spark of Creativity','Murder')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    top=put(s,'Divination','library')
    spell=put(s,'Spark of Creativity','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id])
    cast(s,'Murder',targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.cards[top.id].zone=='p1:library'
    assert not s.state.rules.permissions
    assert s.state.rules.decision is None
    roundtrip(s)


def test_spark_prevented_elected_damage_does_not_fall_back_to_play(cards):
    s=gameplay.setup(cards,'Spark of Creativity','Hallow')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    top=put(s,'Divination','library')
    spell=put(s,'Spark of Creativity','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id])
    cast(s,'Hallow',targets=[spell.id])
    answer(s,['damage'])
    assert s.state.cards[target.id].zone=='p2:battlefield'
    assert s.state.cards[target.id].damage==0
    assert s.state.players['p1'].life==43
    assert s.state.cards[top.id].zone=='p1:exile'
    assert not s.state.rules.permissions
    roundtrip(s)


def test_spark_unused_play_permission_expires_at_end_of_actual_turn(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase

    s=gameplay.setup(cards,'Spark of Creativity')
    target=put(s,'Grizzly Bears','battlefield')
    top=put(s,'Divination','library')
    cast(s,'Spark of Creativity',targets=[target.id])
    answer(s,['play'])
    assert s.state.rules.permissions
    to_phase(s,'main1',turn=4)
    mana(s,U=1,C=2)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top.id)
    assert s.state.model_dump_json()==before
    roundtrip(s)


def test_spark_reads_exiled_x_mana_value_with_zero_x(cards):
    s=gameplay.setup(cards,'Spark of Creativity','Earthquake')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    top=put(s,'Earthquake','library')
    cast(s,'Spark of Creativity',targets=[target.id])
    answer(s,['damage'])
    assert s.state.cards[target.id].zone=='p2:battlefield'
    assert s.state.cards[target.id].damage==1
    assert s.state.cards[top.id].zone=='p1:exile'
    assert not s.state.rules.permissions
    roundtrip(s)


def test_spark_permission_preserves_ordinary_timing_and_colored_mana_requirements(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase

    s=gameplay.setup(cards,'Spark of Creativity')
    target=put(s,'Grizzly Bears','battlefield')
    top=put(s,'Divination','library')
    cast(s,'Spark of Creativity',targets=[target.id])
    answer(s,['play'])
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,R=3)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top.id)
    assert s.state.model_dump_json()==before
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,U=1,C=2)
    to_phase(s,'begin_combat',turn=1)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top.id)
    assert s.state.model_dump_json()==before
    assert s.state.cards[top.id].zone=='p1:exile'
    roundtrip(s)
