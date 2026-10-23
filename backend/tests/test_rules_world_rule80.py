"""Staged native World-rule duration evidence, no card promotion."""
import json
from pathlib import Path

import pytest
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=json.loads((Path(__file__).parent/'fixtures/world_rule80_cards.json').read_text())
@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(DATA):
        base[c['name']]=card(c['name'],number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in DATA]+['Forest','Grizzly Bears','Cytoshape']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    return s


def cast(s,name,pid='p1',targets=()):
    from app.rules.optional_payment import STEP

    c=put(s,name,'hand',pid)
    wait_priority(s,pid)
    mana(s,pid=pid,C=20,U=10,G=10,W=10)
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),sources=[])
    settle(s)
    # Once the separate Chaos recipe is admitted, its genuine instant tax must
    # be paid before this World-duration fixture can exercise its copy spell.
    while (decision := s.state.rules.decision) is not None and \
            (decision.resume or {}).get('ctx', {}).get('name') == 'In the Eye of Chaos' and \
            (decision.resume or {}).get('step') == STEP:
        assert 'pay' in [o.id for o in decision.options]
        act(s, decision.player, type='choose', decision_id=decision.id, option_ids=['pay'])
        settle(s)
    return c


def test_actual_cast_new_world_replaces_old_and_retains_native_batch(cards):
    s=game(cards)
    first=cast(s,'In the Eye of Chaos')
    old=s.state.rules.world_intervals80[Plan(s.state,'p1',s.cards,None).oid(first)].model_copy(deep=True)
    second=cast(s,'Concordant Crossroads')
    assert s.state.cards[first.id].zone=='p1:graveyard'
    assert s.state.cards[second.id].zone=='p1:battlefield'
    receipt=s.state.rules.world_intervals80[Plan(s.state,'p1',s.cards,None).oid(second)]
    assert receipt.since>old.since and receipt.event_batch is not None
    restored=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=cards)
    assert restored.state.rules.world_intervals80==s.state.rules.world_intervals80


def test_actual_simultaneous_newest_world_tie_kills_older_world_too(cards):
    s=game(cards)
    old=cast(s,'In the Eye of Chaos')
    left=put(s,'Concordant Crossroads','graveyard','p1')
    right=put(s,'Concordant Crossroads','graveyard','p2')
    cast(s,'Open the Vaults')
    assert s.state.cards[old.id].zone=='p1:graveyard'
    assert s.state.cards[left.id].zone=='p1:graveyard'
    assert s.state.cards[right.id].zone=='p2:graveyard'
    entries=[e for e in s.state.rules.events if e.kind=='zone_change' and e.card in (left.id,right.id)
             and e.to_zone is not None and e.to_zone.endswith(':battlefield')]
    assert len(entries)==2 and entries[0].batch==entries[1].batch
    assert entries[0].new_object_id!=entries[1].new_object_id


def test_actual_entering_world_copy_receives_new_interval(cards):
    s=game(cards)
    old=cast(s,'Concordant Crossroads')
    copied=cast(s,'Copy Enchantment')
    decision=s.state.rules.decision
    assert decision and old.id in [o.id for o in decision.options]
    act(s,decision.player,type='choose',decision_id=decision.id,option_ids=[old.id])
    settle(s)
    assert s.state.cards[old.id].zone=='p1:graveyard'
    assert s.state.cards[copied.id].zone=='p1:battlefield'
    assert 'World' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[copied.id]).supertypes
    assert s.state.rules.world_intervals80[s.state.rules.object_id(copied.id)].since is not None


def test_legacy_unknown_world_proven_older_than_later_native_entry(cards):
    s=game(cards)
    old=cast(s,'In the Eye of Chaos')
    saved=s.state.model_dump(mode='json')
    saved['rules'].pop('world_epoch80')
    saved['rules'].pop('world_intervals80')
    s=GameSession(GameState.model_validate(saved),cards=cards)
    fresh=cast(s,'Concordant Crossroads')
    assert s.state.cards[old.id].zone=='p1:graveyard'
    assert s.state.cards[fresh.id].zone=='p1:battlefield'


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in [o.id for o in d.options], d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def test_native_copy_loss_and_cleanup_regain_start_new_world_interval(cards):
    s=game(cards)
    cast(s,'Opalescence')
    world=cast(s,'Concordant Crossroads')
    oid=s.state.rules.object_id(world.id)
    first=s.state.rules.world_intervals80[oid].since
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Cytoshape',targets=[world.id])
    choose(s,bear.id)
    assert oid not in s.state.rules.world_intervals80
    other=cast(s,'In the Eye of Chaos')
    to_phase(s,'upkeep',2)
    settle(s)
    assert s.state.cards[world.id].zone=='p1:battlefield'
    assert s.state.cards[other.id].zone=='p1:graveyard'
    assert s.state.rules.world_intervals80[oid].since>first


def test_native_extra_world_copy_effect_does_not_restart_uninterrupted_interval(cards):
    s=game(cards)
    cast(s,'Opalescence')
    world=cast(s,'Concordant Crossroads')
    oid=s.state.rules.object_id(world.id)
    first=s.state.rules.world_intervals80[oid].since
    cast(s,'Cytoshape',targets=[world.id])
    if s.state.rules.decision is not None:
        choose(s,world.id)
    assert s.state.rules.world_intervals80[oid].since==first
    to_phase(s,'upkeep',2)
    settle(s)
    assert s.state.rules.world_intervals80[oid].since==first


def test_native_group_world_copy_acquisition_ties_and_kills_old_source(cards):
    s=game(cards)
    cast(s,'Opalescence')
    world=cast(s,'Concordant Crossroads')
    a=put(s,'Grizzly Bears','battlefield','p1')
    b=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Nanogene Conversion',targets=[world.id])
    assert s.state.cards[world.id].zone=='p1:graveyard'
    assert s.state.cards[a.id].zone=='p1:graveyard'
    assert s.state.cards[b.id].zone=='p2:graveyard'


def test_native_simultaneous_cleanup_world_regains_tie_despite_copy_timestamps(cards):
    s=game(cards)
    cast(s,'Opalescence')
    bear=put(s,'Grizzly Bears','battlefield')
    left=cast(s,'Concordant Crossroads')
    cast(s,'Cytoshape',targets=[left.id])
    choose(s,bear.id)
    right=cast(s,'In the Eye of Chaos')
    cast(s,'Cytoshape',targets=[right.id])
    # Only the two Bears remain eligible; choose the actual non-World bear.
    if s.state.rules.decision is not None:
        choose(s,bear.id)
    third=cast(s,'Arboria')
    assert all(s.state.cards[c.id].zone=='p1:battlefield' for c in (left,right,third))
    to_phase(s,'upkeep',2)
    settle(s)
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in (left,right,third))


def test_ambiguous_legacy_world_durations_reject_atomically_without_guessed_sba(cards):
    from app.game.errors import ActionError
    s=game(cards)
    put(s,'Concordant Crossroads','battlefield')
    put(s,'In the Eye of Chaos','battlefield','p2')
    saved=s.state.model_dump(mode='json')
    saved['rules'].pop('world_epoch80')
    saved['rules'].pop('world_intervals80')
    s=GameSession(GameState.model_validate(saved),cards=cards)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='historical World durations'):
        act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.model_dump_json()==before


def test_native_phased_entering_copy_cold_restore_retains_interval_and_loses_to_newer(cards,tmp_path):
    from tests.test_rules_text_changes71 import cold_run
    s=game(cards)
    source=cast(s,'Concordant Crossroads')
    copied=cast(s,'Copy Enchantment')
    choose(s,source.id)
    oid=s.state.rules.object_id(copied.id)
    first=s.state.rules.world_intervals80[oid].since
    cast(s,"Teferi's Protection")
    assert s.state.cards[copied.id].zone=='p1:phased'
    assert s.state.rules.world_intervals80[oid].since==first
    cold_run(s,cards,tmp_path,r'''
from tests.test_rules_world_rule80 import cast
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_library_look import settle
copied=s.state.cards[sys.argv[3]]
oid=s.state.rules.object_id(copied.id)
first=s.state.rules.world_intervals80[oid].since
assert copied.zone=='p1:phased'
to_phase(s,'main1',2)
new=cast(s,'In the Eye of Chaos',pid='p2')
assert new.zone=='p2:battlefield' and copied.zone=='p1:phased'
assert s.state.rules.world_intervals80[oid].since==first
to_phase(s,'main1',4)
settle(s)
assert copied.zone=='p1:graveyard' and new.zone=='p2:battlefield'
''',copied.id)


def test_native_world_supertype_survives_type_change_and_indestructible_cannot_save_it(cards):
    s=game(cards)
    cast(s,'Opalescence')
    world=cast(s,'Concordant Crossroads')
    cast(s,'Darksteel Mutation',targets=[world.id])
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[world.id])
    assert 'World' in ch.supertypes and 'indestructible' in ch.keywords
    new=cast(s,'In the Eye of Chaos')
    assert s.state.cards[world.id].zone=='p1:graveyard'
    assert s.state.cards[new.id].zone=='p1:battlefield'


def test_native_world_graveyard_destination_uses_normal_replacement(cards):
    s=game(cards)
    cast(s,'Rest in Peace')
    old=cast(s,'Concordant Crossroads')
    new=cast(s,'In the Eye of Chaos')
    assert s.state.cards[old.id].zone=='p1:exile'
    assert s.state.cards[new.id].zone=='p1:battlefield'


def test_manual_face_loss_and_regain_cannot_reuse_old_world_interval(cards):
    s=game(cards)
    world=cast(s,'Concordant Crossroads')
    oid=s.state.rules.object_id(world.id)
    assert s.state.rules.world_intervals80[oid].since is not None
    act(s,'p1',type='face_down',card_ids=[world.id],face_down=True)
    act(s,'p1',type='face_down',card_ids=[world.id],face_down=False)
    assert oid not in s.state.rules.world_intervals80
    act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.rules.world_intervals80[oid].since is None


def test_native_copy_expires_while_phased_and_regained_world_interval_survives_cold(cards,tmp_path):
    from tests.test_rules_text_changes71 import cold_run
    s=game(cards)
    cast(s,'Opalescence')
    world=cast(s,'Concordant Crossroads')
    oid=s.state.rules.object_id(world.id)
    first=s.state.rules.world_intervals80[oid].since
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Cytoshape',targets=[world.id])
    choose(s,bear.id)
    assert oid not in s.state.rules.world_intervals80
    cast(s,"Teferi's Protection")
    assert s.state.cards[world.id].zone=='p1:phased'
    to_phase(s,'main1',2)
    assert s.state.cards[world.id].zone=='p1:phased'
    receipt=s.state.rules.world_intervals80[oid]
    assert receipt.since>first
    cold_run(s,cards,tmp_path,r'''
from tests.test_rules_world_rule80 import cast
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_library_look import settle
world=s.state.cards[sys.argv[3]]
oid=s.state.rules.object_id(world.id)
regained=s.state.rules.world_intervals80[oid].since
new=cast(s,'In the Eye of Chaos',pid='p2')
assert s.state.rules.world_intervals80[s.state.rules.object_id(new.id)].since>regained
to_phase(s,'main1',4)
settle(s)
assert world.zone=='p1:graveyard' and new.zone=='p2:battlefield'
''',world.id)
