"""Actual negative and independent-line gates for staged exile authorities."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import combat
from tests import test_rules_exile_authority_continuations_staged as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_exile_authority_continuations_staged import setup
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ch
from tests.test_rules_wave30m_durations import to_phase

cards = gameplay.cards
staged = gameplay.staged


def test_flameskull_actual_cannot_block_and_flying(cards):
    s = setup(cards, 'Flameskull')
    skull = put(s, 'Flameskull', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    assert 'flying' in ch(s, skull).keywords
    assert combat.block_problem(s.state, skull, ch(s, skull), bear, ch(s, bear), s.cards)


@pytest.mark.parametrize('name', ['Bismuth Mindrender', 'The Infamous Cruelclaw'])
def test_required_immediate_alternative_cannot_be_offered_without_native_resources(cards, name):
    s = setup(cards, name)
    source = put(s, name, 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    cid = stack_library(s, ['Grizzly Bears'], pid='p2' if name.startswith('Bismuth') else 'p1')[0]
    if name.startswith('Bismuth'):
        act(s, 'p1', type='set_life', player='p1', value=1)
    else:
        held = list(s.state.zones.get('p1:hand', []))
        if held:
            act(s, 'p1', type='move', card_ids=held, to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    to_phase(s, 'combat_damage', turn=4)
    settle(s)
    assert s.state.cards[cid].zone.endswith(':exile')
    d = s.state.rules.decision
    assert d is None or not any(o.card_id == cid for o in d.options)
    assert not any(p.card == cid for p in s.state.rules.permissions)
    roundtrip(s)


def test_abstruse_target_land_is_refused_and_permission_dies_on_new_object(cards):
    s = setup(cards, 'Abstruse Appropriation')
    land = put(s, 'Forest', 'battlefield', 'p2')
    source = put(s, 'Abstruse Appropriation', 'hand')
    mana(s, C=2, W=1, B=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[land.id])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Abstruse Appropriation', targets=[bear.id])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player':'p2','zone':'graveyard'})
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player':'p2','zone':'exile'})
    mana(s, C=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id)
    roundtrip(s)


def test_cannonade_attacking_creature_death_actual_each_opponent_damage(cards):
    s = setup(cards, 'Brazen Cannonade', 'Murder')
    put(s, 'Brazen Cannonade', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id':bear.id,'target':'p2'}])
    cast(s, 'Murder', targets=[bear.id])
    assert s.state.players['p2'].life == 38 and s.state.players['p3'].life == 38
    roundtrip(s)


def test_chiss_printed_affinity_actual_cast_haste_flying_and_artifact_spell_filter(cards):
    s = setup(cards, 'Chiss-Goria, Forge Tyrant', 'Myr Enforcer', 'Sol Ring')
    for name in ('Memnite','Myr Enforcer','Sol Ring'):
        put(s,name,'battlefield')
    source = put(s,'Chiss-Goria, Forge Tyrant','hand')
    mana(s,C=3,R=3)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert {'haste','flying'} <= ch(s,s.state.cards[source.id]).keywords
    blocker=put(s,'Grizzly Bears','battlefield','p2')
    assert combat.block_problem(s.state,blocker,ch(s,blocker),s.state.cards[source.id],ch(s,source),cards)
    cid=stack_library(s,['Grizzly Bears'])[0]
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    assert s.state.cards[cid].zone=='p1:exile'
    to_phase(s,'main2',turn=1)
    mana(s,C=20,G=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=cid)
    roundtrip(s)


def test_xander_casualty_actual_sacrifice_copies_separate_packets_without_casting_copy(cards):
    from app.rules import history
    from app.rules.plan import Plan
    s=setup(cards,"Xander's Pact")
    sacrifice=put(s,'Grizzly Bears','battlefield')
    source=put(s,"Xander's Pact",'hand')
    ids=[]
    for pid in ('p2','p3'):
        ids += stack_library(s,['Grizzly Bears','Lightning Bolt'],pid=pid)
    mana(s,C=4,B=2)
    act(s,'p1',type='cast_spell',card_id=source.id,optional_costs=[f'{source.id}:casualty'],
        cost_choices=[{'component':0,'cards':[sacrifice.id]}])
    settle(s)
    assert s.state.cards[sacrifice.id].zone=='p1:graveyard'
    assert all(s.state.cards[c].zone.endswith(':exile') for c in ids)
    permissions = [p for p in s.state.rules.permissions if p.card in ids]
    assert len(permissions) == 4 and len({p.id for p in permissions}) == 4
    assert {p.card for p in permissions} == set(ids)
    assert sum(c.player=='p1' for c in history.log_for(Plan(s.state,'p1',cards,None)).casts)==1
    roundtrip(s)


def test_chiss_shared_one_spell_limit_excludes_second_artifact_even_after_source_leaves(cards):
    s=setup(cards,'Chiss-Goria, Forge Tyrant','Memnite')
    source=put(s,'Chiss-Goria, Forge Tyrant','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    ids=stack_library(s,['Memnite','Memnite'])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    to_phase(s,'main2',turn=4)
    act(s,'p1',type='cast_spell',card_id=ids[0])
    settle(s)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=ids[1])
    roundtrip(s)


def test_mnemonic_excludes_own_graveyard_and_blinked_exile_does_not_return(cards):
    s=setup(cards,'Mnemonic Betrayal')
    own=put(s,'Grizzly Bears','graveyard')
    foreign=put(s,'Grizzly Bears','graveyard','p2')
    cast(s,'Mnemonic Betrayal')
    assert s.state.cards[own.id].zone=='p1:graveyard'
    act(s,'p1',type='move',card_ids=[foreign.id],to={'player':'p2','zone':'hand'})
    act(s,'p1',type='move',card_ids=[foreign.id],to={'player':'p2','zone':'exile'})
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[foreign.id].zone=='p2:exile'
    roundtrip(s)


def test_allure_all_lands_have_no_forced_nonland_exile_or_cast(cards):
    s=setup(cards,'Allure of the Unknown')
    ids=stack_library(s,['Forest','Island'])
    rest=[c for c in s.state.zones.get('p1:library',[]) if c not in ids]
    if rest:
        act(s,'p1',type='move',card_ids=rest,to={'player':'p1','zone':'graveyard'})
    cast(s,'Allure of the Unknown')
    from tests.test_rules_controller_tutors import answer
    answer(s,['p2'])
    settle(s)
    assert all(s.state.cards[c].zone=='p1:hand' for c in ids)
    assert s.state.rules.decision is None
    assert not s.state.rules.free_casts
    roundtrip(s)


@pytest.mark.parametrize('name',['Bismuth Mindrender','The Infamous Cruelclaw','Breeches, Brazen Plunderer'])
def test_printed_menace_native_combat_rejects_one_blocker(cards,name):
    s=setup(cards,name)
    source=put(s,name,'battlefield')
    blocker=put(s,'Grizzly Bears','battlefield','p2')
    if name=='Bismuth Mindrender':
        assert ch(s,source).colors==frozenset()
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    to_phase(s,'declare_blockers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':source.id}])
    roundtrip(s)


def test_durnan_background_and_breeches_partner_real_deck_pairing_remain_native(cards):
    from app.rules import commander
    durnan=cards.resolve('Durnan of the Yawning Portal')
    background=cards.resolve('Raised by Giants')
    breeches=cards.resolve('Breeches, Brazen Plunderer')
    assert commander.pair_problem(durnan,background) is None
    assert commander.pair_problem(durnan,breeches) is not None
    assert any(p.kind=='partner' for p in commander.pairings(breeches))


@pytest.mark.parametrize('colorless,paidlife',[(4,0),(3,2)])
def test_abstruse_actual_phyrexian_choice_spends_real_colorless_or_actual_life(cards,colorless,paidlife):
    s=setup(cards,'Abstruse Appropriation','Birthing Pod')
    target=put(s,'Birthing Pod','battlefield','p2')
    cast(s,'Abstruse Appropriation',targets=[target.id])
    act(s,'p1',type='clear_mana',player='p1')
    before=s.state.players['p1'].life
    mana(s,C=colorless)
    act(s,'p1',type='cast_spell',card_id=target.id)
    settle(s)
    if s.state.rules.decision is not None:
        from tests.test_rules_controller_tutors import answer
        assert s.state.rules.decision.resume['step']=='phyrexian'
        answer(s,['0'])
    assert s.state.players['p1'].life==before-paidlife
    record=next(p for p in s.state.rules.payments.values() if p.card==target.id)
    assert record.mana_spent=={'C':colorless}
    assert s.state.cards[target.id].zone=='p1:battlefield'
    roundtrip(s)
