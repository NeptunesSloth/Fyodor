"""Naya's cast-trigger information belongs to the exact original spell object."""
from __future__ import annotations

# ruff: noqa: F811 -- pytest fixture imported for these test functions.
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana as fund
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_reveal_snapshots import cards, mana  # noqa: F401
from tests.test_rules_shared_damage_choices import table


def start(cards,extra=()):
    s=table(cards,['Naya Soulbeast','Grizzly Bears',*extra],['Sol Ring','Counterspell'],['Counterspell'])
    put(s,'Grizzly Bears','library')
    put(s,'Sol Ring','library','p2')
    put(s,'Counterspell','library','p3')
    source=put(s,'Naya Soulbeast','hand')
    mana(s)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    return s,source


def test_cast_trigger_resolves_after_original_spell_countered(cards):
    s,source=start(cards)
    counter=put(s,'Counterspell','hand','p2')
    fund(s,pid='p2',U=2)
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[source.id],sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.cards[source.id].counters
    assert any('reveal' in str(entry).lower() for entry in s.state.log)
    assert all(not s.state.cards[c].revealed_to for p in ['p1','p2','p3'] for c in s.state.zones[f'{p}:library'])
    roundtrip(s)


def test_old_cast_trigger_does_not_give_counters_to_new_incarnation(cards):
    s,source=start(cards)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'hand'})
    settle(s)
    for p in ['p1','p2','p3']:
        ids=list(s.state.zones[f'{p}:library'])
        if ids:
            act(s,p,type='move',card_ids=ids,to={'player':p,'zone':'graveyard'})
    mana(s)
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_native_counter_replacement_modifies_original_entry_only(cards):
    s=table(cards,['Naya Soulbeast','Grizzly Bears','Hardened Scales'],['Sol Ring'],['Counterspell'])
    put(s,'Hardened Scales','battlefield')
    put(s,'Grizzly Bears','library')
    put(s,'Sol Ring','library','p2')
    put(s,'Counterspell','library','p3')
    source=put(s,'Naya Soulbeast','hand')
    mana(s)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    assert s.state.cards[source.id].counters['+1/+1']==6
    roundtrip(s)


def test_spell_copy_does_not_inherit_original_cast_trigger_entry_count(cards):
    s,source=start(cards,['Double Major'])
    copy=put(s,'Double Major','hand')
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[source.id],sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].counters['+1/+1']==5
    assert not [c for c in s.state.cards.values() if c.name=='Naya Soulbeast' and c.is_token and c.zone.endswith(':battlefield')]
    assert len([e for e in s.state.rules.turn_log.entered if e.card!=source.id])==1
    roundtrip(s)
