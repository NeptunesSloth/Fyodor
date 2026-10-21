"""Canonical exact-target delayed watches, event batching and source/controller identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sba import power
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/bound_delayed35_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="bd35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/bound_delayed35_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


NAMES = ['Niko Aris','Long River Lurker','Jaya, Fiery Negotiator','Arcbond','Glyph of Life','Reincarnation','Time to Feed','Goblin Sappers','Dwarven Sea Clan','Phantasmal Mount']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def priority(s,pid='p1'):
    for _ in range(10):
        if s.state.rules.priority==pid:
            return
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('no priority')


def test_niko_actual_loyalty_unblockable_then_damage_bounce(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    niko=cast(s,'Niko Aris',x_value=0)
    act(s,'p1',type='activate_ability',card_id=niko.id,ability=1,targets=[bear.id],target_counts=[1])
    settle(s)
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(bear,'p2'))
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:hand'
    assert s.state.players['p2'].life==38
    roundtrip(s)


def test_lurker_real_etb_optional_blink_returns_new_object(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    start(s)
    cast(s,'Long River Lurker')
    pick(s,[bear.id])
    settle(s)
    old=s.state.rules.object_id(bear.id)
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(bear,'p2'))
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    pick(s,['yes'])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.rules.object_id(bear.id)!=old
    roundtrip(s)


def test_jaya_damage_counts_current_attackers_when_watch_resolves(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    fodder=put(s,'Memnite','battlefield')
    enemy=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    jaya=cast(s,'Jaya, Fiery Negotiator')
    act(s,'p1',type='activate_ability',card_id=jaya.id,ability=2,targets=[enemy.id],target_counts=[1])
    settle(s)
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(bear,'p2'),(fodder,'p2'))
    # Shock resolves before the already-created attack trigger.
    priority(s)
    shock=put(s,'Shock','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=shock.id,targets=[fodder.id])
    settle(s)
    assert s.state.cards[enemy.id].zone=='p2:battlefield'
    assert s.state.cards[enemy.id].damage==1
    roundtrip(s)


def test_arcbond_lethal_damage_uses_creature_lki_and_hits_all_once(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    fodder=put(s,'Memnite','battlefield')
    start(s)
    cast(s,'Arcbond',[bear.id],target_counts=[1])
    cast(s,'Shock',[bear.id])
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    assert s.state.cards[fodder.id].zone=='p1:graveyard'
    assert [s.state.players[p].life for p in ('p1','p2','p3')]==[38,38,38]
    roundtrip(s)


def test_glyph_opponents_wall_gains_original_caster_life(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    wall=put(s,'Wall of Wood','battlefield',pid='p2')
    bear=put(s,'Grizzly Bears','battlefield',pid='p3')
    start(s,turn=3)
    cast(s,'Glyph of Life',[wall.id],target_counts=[1])
    to_phase(s,'declare_attackers',turn=3)
    attack(s,(bear,'p2'),pid='p3')
    to_phase(s,'declare_blockers',turn=3)
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':wall.id,'attacker_id':bear.id}])
    to_phase(s,'combat_damage',turn=3)
    settle(s)
    assert s.state.players['p1'].life==42
    assert s.state.cards[wall.id].damage==2
    roundtrip(s)


def test_reincarnation_chooser_is_caster_recipient_is_dead_creatures_owner(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    other=put(s,'Memnite','graveyard',pid='p2')
    start(s)
    act(s,'p2',type='set_controller',card_ids=[bear.id],player='p3')
    cast(s,'Reincarnation',[bear.id],target_counts=[1])
    cast(s,'Shock',[bear.id])
    assert s.state.rules.decision.player=='p1'
    pick(s,[other.id])
    settle(s)
    assert s.state.cards[other.id].zone=='p2:battlefield'
    assert s.state.cards[other.id].controller=='p2'
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    roundtrip(s)


def test_time_to_feed_watch_created_before_actual_fight(cards):
    s=setup(cards)
    own=put(s,'Grizzly Bears','battlefield')
    enemy=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    cast(s,'Time to Feed',[enemy.id,own.id],target_counts=[1,1])
    assert s.state.cards[own.id].zone=='p1:graveyard'
    assert s.state.cards[enemy.id].zone=='p2:graveyard'
    assert s.state.players['p1'].life==43
    roundtrip(s)


def test_sappers_end_combat_destroys_both_named_objects(cards):
    s=setup(cards)
    source=put(s,'Goblin Sappers','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    start(s)
    mana(s,R=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[bear.id],target_counts=[1])
    settle(s)
    to_phase(s,'main2',turn=4)
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_sea_clan_real_attacker_qualifier_and_delayed_damage(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=put(s,'Dwarven Sea Clan','battlefield')
    put(s,'Fervor','battlefield')
    put(s,'Island','battlefield',pid='p2')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=2)
    to_phase(s,'declare_attackers',turn=2)
    attack(s,(bear,'p1'),pid='p2')
    priority(s)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[bear.id],target_counts=[1])
    settle(s)
    assert s.state.cards[bear.id].damage==0
    to_phase(s,'main2',turn=2)
    assert s.state.players['p1'].life==38
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    roundtrip(s)


def test_mount_real_blink_does_not_sacrifice_new_target(cards):
    s=setup(cards)
    mount=put(s,'Phantasmal Mount','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    start(s)
    mana(s)
    act(s,'p1',type='activate_ability',card_id=mount.id,ability=1,targets=[bear.id],target_counts=[1])
    settle(s)
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[bear.id])
    assert power(s.state.cards[bear.id],ch)==3 and 'flying' in ch.keywords
    old=s.state.rules.object_id(bear.id)
    cast(s,'Cloudshift',[bear.id])
    assert s.state.cards[mount.id].zone=='p1:graveyard'
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.rules.object_id(bear.id)!=old
    roundtrip(s)


def test_niko_zero_optional_target_creates_no_watch(cards):
    s=setup(cards)
    start(s)
    niko=cast(s,'Niko Aris',x_value=0)
    act(s,'p1',type='activate_ability',card_id=niko.id,ability=1,targets=[],target_counts=[0])
    settle(s)
    assert not s.state.rules.delayed
    assert s.state.cards[niko.id].counters['loyalty']==4
    roundtrip(s)


def test_niko_simultaneous_noncombat_damage_is_one_watch_trigger(cards):
    s=setup(cards)
    creature=put(s,'Guttersnipe','battlefield')
    start(s)
    niko=cast(s,'Niko Aris',x_value=0)
    act(s,'p1',type='activate_ability',card_id=niko.id,ability=1,targets=[creature.id],target_counts=[1])
    settle(s)
    shock=put(s,'Shock','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=shock.id,targets=['p3'])
    found=[]
    for _ in range(16):
        found=[e for e in s.state.rules.stack.values() if e.event is not None and e.event.kind=='deal_damage']
        if found:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert len(found)==1 and found[0].event.amount==4 and found[0].event.count==2
    settle(s)
    assert s.state.cards[creature.id].zone=='p1:hand'
    assert s.state.players['p2'].life==38 and s.state.players['p3'].life==36
    roundtrip(s)


@pytest.mark.parametrize('accept',[False,True])
def test_lurker_optional_choice_is_by_original_controller(cards,accept):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    start(s)
    source=cast(s,'Long River Lurker')
    pick(s,[bear.id])
    settle(s)
    # The delayed ability survives its source leaving.
    cast(s,'Cloudshift',[source.id])
    # The new Lurker ETB is independent; choose itself for its new watch.
    pick(s,[source.id])
    settle(s)
    old=s.state.rules.object_id(bear.id)
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(bear,'p2'))
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    assert s.state.rules.decision.player=='p1'
    pick(s,['yes' if accept else 'no'])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert (s.state.rules.object_id(bear.id)!=old)==accept
    roundtrip(s)


def test_arcbond_simultaneous_incoming_sources_are_one_summed_trigger(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    wall=put(s,'Wall of Wood','battlefield')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    memnite=put(s,'Memnite','battlefield',pid='p2')
    start(s,turn=1)
    cast(s,'Entangler',[wall.id])
    to_phase(s,'main1',turn=2)
    cast(s,'Arcbond',[wall.id],target_counts=[1])
    to_phase(s,'declare_attackers',turn=2)
    attack(s,(bear,'p1'),(memnite,'p1'),pid='p2')
    to_phase(s,'declare_blockers',turn=2)
    act(s,'p1',type='declare_blockers',blocks=[{'blocker_id':wall.id,'attacker_id':bear.id},{'blocker_id':wall.id,'attacker_id':memnite.id}])
    to_phase(s,'combat_damage',turn=2)
    found=[e for e in s.state.rules.stack.values() if e.event is not None and e.event.kind=='dealt_damage']
    assert len(found)==1 and found[0].event.amount==3 and found[0].event.count==2
    settle(s)
    assert [s.state.players[p].life for p in ('p1','p2','p3')]==[37,37,37]
    roundtrip(s)


def test_glyph_rejects_damage_from_nonattacking_spell(cards):
    s=setup(cards)
    wall=put(s,'Wall of Wood','battlefield',pid='p2')
    start(s)
    cast(s,'Glyph of Life',[wall.id],target_counts=[1])
    cast(s,'Shock',[wall.id])
    assert s.state.players['p1'].life==40
    assert s.state.cards[wall.id].damage==2
    roundtrip(s)


def test_glyph_accepts_noncombat_damage_from_attacking_creature(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    tim=put(s,'Prodigal Pyromancer','battlefield',pid='p2')
    wall=put(s,'Wall of Wood','battlefield',pid='p3')
    start(s,turn=2)
    cast(s,'Glyph of Life',[wall.id],target_counts=[1])
    to_phase(s,'declare_attackers',turn=2)
    attack(s,(tim,'p3'),pid='p2')
    cast(s,'Vitalize',pid='p2')
    priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=tim.id,ability=0,targets=[wall.id])
    settle(s)
    assert s.state.cards[tim.id].attacking is not None
    assert s.state.cards[wall.id].damage==1
    assert s.state.players['p1'].life==41
    roundtrip(s)


def test_reincarnation_no_dies_when_replaced_by_exile(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s)
    cast(s,'Reincarnation',[bear.id],target_counts=[1])
    cast(s,'Rest in Peace')
    cast(s,'Shock',[bear.id])
    assert s.state.cards[bear.id].zone=='p2:exile'
    assert len(s.state.rules.delayed)==1
    roundtrip(s)


def test_time_to_feed_one_illegal_target_still_creates_opponents_death_watch(cards):
    s=setup(cards)
    own=put(s,'Grizzly Bears','battlefield')
    enemy=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    act(s,'p1',type='set_prefs',hold_priority=True)
    spell=put(s,'Time to Feed','hand')
    blink=put(s,'Cloudshift','hand')
    mana(s,G=1,C=2,W=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[enemy.id,own.id],target_counts=[1,1])
    priority(s)
    act(s,'p1',type='cast_spell',card_id=blink.id,targets=[own.id])
    settle(s)
    assert s.state.cards[enemy.id].damage==0
    cast(s,'Shock',[enemy.id])
    assert s.state.players['p1'].life==43
    roundtrip(s)


@pytest.mark.parametrize('blink',['source','target'])
def test_sappers_preserves_both_old_object_identities(cards,blink):
    s=setup(cards)
    source=put(s,'Goblin Sappers','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    start(s)
    mana(s,R=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[bear.id],target_counts=[1])
    settle(s)
    changed=source if blink=='source' else bear
    cast(s,'Cloudshift',[changed.id])
    to_phase(s,'main2',turn=4)
    assert s.state.cards[changed.id].zone=='p1:battlefield'
    other=bear if blink=='source' else source
    assert s.state.cards[other.id].zone=='p1:graveyard'
    roundtrip(s)


def test_mount_cannot_sacrifice_creature_now_controlled_by_opponent(cards):
    s=setup(cards)
    source=put(s,'Phantasmal Mount','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    start(s)
    for pid in ('p1','p3'):
        act(s,pid,type='set_prefs',hold_priority=True,response='on')
    aggression=put(s,'Act of Aggression','hand',pid='p3')
    blink=put(s,'Cloudshift','hand')
    mana(s,pid='p3',R=5,C=3)
    mana(s,W=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,targets=[bear.id],target_counts=[1])
    settle(s)
    priority(s,'p3')
    act(s,'p3',type='cast_spell',card_id=aggression.id,targets=[bear.id],life_symbols=[])
    settle(s)
    priority(s)
    act(s,'p1',type='cast_spell',card_id=blink.id,targets=[source.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p3:battlefield'
    assert s.state.cards[bear.id].controller=='p3'
    roundtrip(s)


def test_sea_clan_rejects_controller_without_island_before_tapping(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=put(s,'Dwarven Sea Clan','battlefield')
    put(s,'Fervor','battlefield')
    put(s,'Island','battlefield',pid='p3')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=2)
    to_phase(s,'declare_attackers',turn=2)
    attack(s,(bear,'p1'),pid='p2')
    priority(s)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[bear.id],target_counts=[1])
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_niko_watched_creature_can_become_a_noncreature_before_damage(cards):
    s=setup(cards)
    tim=put(s,'Prodigal Pyromancer','battlefield')
    put(s,'Vedalken Orrery','battlefield')
    start(s)
    niko=cast(s,'Niko Aris',x_value=0)
    act(s,'p1',type='activate_ability',card_id=niko.id,ability=1,targets=[tim.id],target_counts=[1])
    settle(s)
    act(s,'p1',type='set_prefs',hold_priority=True)
    song=put(s,'Song of the Dryads','hand')
    mana(s,G=1,C=2)
    act(s,'p1',type='activate_ability',card_id=tim.id,ability=0,targets=['p3'])
    priority(s)
    act(s,'p1',type='cast_spell',card_id=song.id,targets=[tim.id])
    for _ in range(12):
        if s.state.cards[song.id].zone=='p1:battlefield':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[tim.id])
    assert 'Land' in ch.types and 'Creature' not in ch.types
    assert any(e.kind=='activated' for e in s.state.rules.stack.values())
    settle(s)
    assert s.state.players['p3'].life==39
    assert s.state.cards[tim.id].zone=='p1:hand'
    roundtrip(s)


def test_niko_bound_watch_does_not_transfer_to_blinked_object(cards):
    s=setup(cards)
    tim=put(s,'Prodigal Pyromancer','battlefield')
    put(s,'Fervor','battlefield')
    start(s)
    niko=cast(s,'Niko Aris',x_value=0)
    act(s,'p1',type='activate_ability',card_id=niko.id,ability=1,targets=[tim.id],target_counts=[1])
    settle(s)
    act(s,'p1',type='set_prefs',hold_priority=True)
    blink=put(s,'Cloudshift','hand')
    mana(s,W=1)
    old=s.state.rules.object_id(tim.id)
    act(s,'p1',type='activate_ability',card_id=tim.id,ability=0,targets=['p3'])
    act(s,'p1',type='cast_spell',card_id=blink.id,targets=[tim.id])
    settle(s)
    assert s.state.players['p3'].life==39
    assert s.state.rules.object_id(tim.id)!=old
    assert s.state.cards[tim.id].zone=='p1:battlefield'
    priority(s)
    act(s,'p1',type='activate_ability',card_id=tim.id,ability=0,targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life==39
    assert s.state.cards[tim.id].zone=='p1:battlefield'
    roundtrip(s)


def test_saved_reincarnation_choice_resumes_cold_with_original_owner(cards,tmp_path):
    import subprocess
    import sys
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    other=put(s,'Memnite','graveyard',pid='p2')
    start(s)
    act(s,'p2',type='set_controller',card_ids=[bear.id],player='p3')
    cast(s,'Reincarnation',[bear.id],target_counts=[1])
    cast(s,'Shock',[bear.id])
    assert s.state.rules.decision is not None and s.state.rules.decision.player=='p1'
    saved=tmp_path/'reincarnation.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.rules.decision.player=='p1'
pick(s,[sys.argv[3]])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p2:battlefield'
assert s.state.cards[sys.argv[3]].controller=='p2'
roundtrip(s)
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),other.id],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
