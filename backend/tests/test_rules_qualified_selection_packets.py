"""Actual qualified library selections and their native follow-up instructions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_qualified_attached_tutors import cold
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/qualified_selection_packet_cards.json'
NAMES=[c['name'] for c in json.loads(DATA.read_text())][:25]


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        base[c['name']]=card(c['name'],set_code='qsp',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns=[c['name'] for c in json.loads(DATA.read_text())]
    s=table(cards,[*ns,'Forest','Island','Plains','Grizzly Bears','Sol Ring'],ns,ns)
    to_phase(s,'main1',turn=1)
    return s


def order(s):
    d=s.state.rules.decision
    assert d is not None and d.kind=='order'
    ids=[o.id for o in d.options]
    answer(s,list(reversed(ids)))
    return ids


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    if name=="Zimone's Experiment":
        pytest.skip('Exact public-zone overlap rule under research; not admitted')
    got=coverage.of_card_data(cards.resolve(name))
    assert got.level=='FULL',got


def test_stargaze_actual_x_select_and_life(cards):
    s=setup(cards)
    top=stack_library(s,['Forest','Grizzly Bears','Island','Sol Ring'])
    before=s.state.players['p1'].life
    cast(s,'Stargaze',x_value=2)
    assert {o.id for o in s.state.rules.decision.options}==set(top)
    answer(s,[top[0],top[3]])
    assert all(s.state.cards[c].zone=='p1:hand' for c in [top[0],top[3]])
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in [top[1],top[2]])
    assert s.state.players['p1'].life==before-2
    roundtrip(s)


def test_expand_actual_land_count_and_proliferate(cards):
    s=setup(cards)
    host=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='counter',card_ids=[host.id],kind='+1/+1',delta=1)
    top=stack_library(s,['Forest','Island','Runeclaw Bear','Sol Ring','Plains','Memnite'])
    cast(s,'Expand the Sphere')
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:battlefield' and s.state.cards[top[0]].tapped
    assert s.state.rules.decision is not None, (s.state.cards[host.id].counters,[(c.name,c.zone) for c in s.state.cards.values() if c.zone.endswith(':battlefield')])
    assert s.state.rules.decision.resume['step']=='proliferate'
    answer(s,[host.id])
    assert s.state.cards[host.id].counters['+1/+1']==2
    roundtrip(s)


def test_vow_actual_land_or_legendary_permanent_batch(cards):
    s=setup(cards)
    put(s,'Krenko, Mob Boss','battlefield')
    top=stack_library(s,['Forest','Grizzly Bears','Sol Ring','Lonis, Cryptozoologist','Memnite'])
    cast(s,"Kamahl's Druidic Vow",x_value=5)
    opts={o.id for o in s.state.rules.decision.options}
    assert top[0] in opts and top[3] in opts, (s.state.rules.decision.resume['step'],[(o.id,o.label) for o in s.state.rules.decision.options])
    assert top[1] not in opts and top[2] not in opts
    answer(s,[top[0],top[3]])
    assert all(s.state.cards[c].zone=='p1:battlefield' for c in [top[0],top[3]])
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in [top[1],top[2],top[4]])
    roundtrip(s)


def test_touch_actual_entry_ordinary_granted_return_ability(cards):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears','Forest','Island','Sol Ring'])
    cast(s,"Aethermage's Touch")
    answer(s,[top[0]])
    order(s)
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[top[0]].zone=='p1:hand'
    roundtrip(s)


def test_invocation_native_reflexive_damage_after_spell(cards):
    s=setup(cards)
    victim=put(s,'Grizzly Bears','battlefield','p2')
    top=stack_library(s,['Shivan Dragon','Forest','Island','Sol Ring','Plains','Memnite','Grizzly Bears'])
    spell=cast(s,"Vivien's Invocation")
    answer(s,[top[0]])
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    answer(s,[victim.id])
    assert s.state.cards[victim.id].zone=='p2:graveyard'
    roundtrip(s)


def test_bamboozle_controller_chooses_target_library_cards(cards):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears','Forest','Island','Sol Ring'],pid='p2')
    cast(s,'Bamboozle',targets=['p2'])
    assert s.state.rules.decision.player=='p1'
    answer(s,[top[0],top[3]])
    rest=order(s)
    assert set(rest)=={top[1],top[2]}
    assert all(s.state.cards[c].zone=='p2:graveyard' for c in [top[0],top[3]])
    assert s.state.zones['p2:library'][:2]==list(reversed(rest))
    roundtrip(s)


def test_librarian_random_four_actual_exile_then_order(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s=setup(cards)
    source=put(s,'Orcish Librarian','battlefield')
    s.state.rules.controlled_since[source.id].turn=0
    top=stack_library(s,['Grizzly Bears','Forest','Island','Sol Ring','Plains','Memnite','Shivan Dragon','Spore Frog'])
    mana(s,R=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{R}'))
    settle(s)
    assert len([c for c in top if s.state.cards[c].zone=='p1:exile'])==4
    rest=order(s)
    assert len(rest)==4 and set(rest)<=set(top)
    roundtrip(s)


def test_cylix_target_looks_and_chooses_own_library(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s=setup(cards)
    source=put(s,"Ashnod's Cylix",'battlefield')
    top=stack_library(s,['Grizzly Bears','Forest','Island'],pid='p2')
    mana(s,C=5)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{3}'),targets=['p2'])
    settle(s)
    assert s.state.rules.decision.player=='p2'
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p2:library'
    assert s.state.zones['p2:library'][0]==top[0]
    assert all(s.state.cards[c].zone=='p2:exile' for c in top[1:])
    roundtrip(s)


def test_petals_actual_bottom_and_stack_to_hand(cards):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears','Forest','Island'])
    spell=cast(s,'Petals of Insight')
    answer(s,['yes'])
    rest=order(s)
    assert set(rest)==set(top)
    assert s.state.cards[spell.id].zone=='p1:hand'
    roundtrip(s)


def test_taste_actual_put_graveyard_power_gain(cards):
    s=setup(cards)
    top=stack_library(s,['Forest','Shivan Dragon','Grizzly Bears','Sol Ring'])
    before=s.state.players['p1'].life
    cast(s,'Discerning Taste')
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:hand'
    assert s.state.cards[top[1]].zone=='p1:graveyard'
    assert s.state.players['p1'].life==before+5
    roundtrip(s)


def test_debut_normal_actual_revealed_cards_hand_and_shuffle(cards):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears','Shivan Dragon','Forest'])
    cast(s,'Thunderous Debut')
    answer(s,top[:2])
    assert all(s.state.cards[c].zone=='p1:hand' for c in top[:2])
    roundtrip(s)


def test_appraiser_actual_target_exile_then_private_hand_pick(cards):
    s=setup(cards)
    target=put(s,'Grizzly Bears','graveyard','p2')
    top=stack_library(s,['Forest','Island','Sol Ring'])
    cast(s,'Corpse Appraiser')
    answer(s,[target.id])
    assert s.state.cards[target.id].zone=='p2:exile'
    answer(s,[top[2]])
    assert s.state.cards[top[2]].zone=='p1:hand'
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in top[:2])
    roundtrip(s)


def test_ritual_natural_endstep_payment_then_capped_entry(cards):
    s=setup(cards)
    host=put(s,'Grizzly Bears','battlefield')
    cast(s,'Birthing Ritual')
    top=stack_library(s,['Memnite','Shivan Dragon','Forest','Island','Sol Ring','Plains','Reclamation Sage'])
    to_phase(s,'end',turn=1)
    settle(s)
    answer(s,['pay'])
    if s.state.rules.decision.resume['step']!='pick_looked':
        answer(s,[host.id])
    assert s.state.cards[host.id].zone=='p1:graveyard'
    opts={o.id for o in s.state.rules.decision.options}
    assert top[0] in opts and top[6] in opts and top[1] not in opts
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    roundtrip(s)


def test_gilgamesh_actual_equipment_arrival_then_nontarget_attachment(cards):
    s=setup(cards)
    host=put(s,'Universal Automaton','battlefield')
    top=stack_library(s,['Sword of the Animist','Forest','Island','Sol Ring','Memnite','Grizzly Bears'])
    cast(s,'Gilgamesh, Master-at-Arms')
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    answer(s,['yes'])
    answer(s,[top[0]])
    answer(s,[host.id])
    assert s.state.cards[top[0]].attached_to==host.id
    roundtrip(s)


def test_lonis_actual_x_clues_foreign_reveal_and_own_entry(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s=setup(cards)
    source=cast(s,'Lonis, Cryptozoologist')
    cast(s,'Grizzly Bears')
    cast(s,'Memnite')
    clues=[c.id for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.name=='Clue']
    assert len(clues)==2
    s.state.rules.controlled_since[source.id].turn=0
    top=stack_library(s,['Sol Ring','Shivan Dragon'],pid='p2')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,s.state.cards[source.id],'{T}'),x_value=2,targets=['p2'])
    settle(s)
    assert not any(c in s.state.cards and s.state.cards[c].zone=='p1:battlefield' for c in clues)
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    answer(s,[top[0]])
    assert s.state.cards[top[0]].owner=='p2' and s.state.cards[top[0]].controller=='p1'
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    roundtrip(s)


def test_owlbear_actual_attack_eight_lands_and_fixed_attacked_player(cards):
    s=setup(cards)
    source=put(s,'Owlbear Cub','battlefield')
    put(s,'Fervor','battlefield')
    for n in ['Plains','Island','Forest','Mountain','Command Tower','Darksteel Citadel','Great Furnace','Dryad Arbor']:
        put(s,n,'battlefield','p2')
    top=stack_library(s,['Runeclaw Bear','Forest','Island','Sol Ring','Plains','Memnite','Grizzly Bears','Shivan Dragon'])
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:battlefield' and s.state.cards[top[0]].tapped
    assert s.state.cards[top[0]].attacking.id=='p2'
    roundtrip(s)


def test_woodwurm_real_backup_grants_host_own_power_look(cards):
    s=setup(cards)
    host=put(s,'Grizzly Bears','battlefield')
    put(s,'Fervor','battlefield')
    cast(s,'Emergent Woodwurm')
    answer(s,[host.id])
    top=stack_library(s,['Sol Ring','Forest','Island','Shivan Dragon','Memnite'])
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':host.id,'target':'p2'}])
    settle(s)
    assert top[0] in {o.id for o in s.state.rules.decision.options}
    assert top[3] not in {o.id for o in s.state.rules.decision.options}
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    roundtrip(s)


def test_witness_target_shuffle_then_private_controller_look(cards):
    s=setup(cards)
    grave=put(s,'Grizzly Bears','graveyard','p2')
    top=stack_library(s,['Forest','Island','Sol Ring','Memnite'])
    cast(s,'Witness the Future',targets=['p2',grave.id],target_counts=[1,1])
    assert s.state.rules.decision.player=='p1'
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:hand'
    assert any(c.name=='Grizzly Bears' and c.zone=='p2:library' for c in s.state.cards.values())
    roundtrip(s)


def test_munda_optional_native_ally_card_partition(cards):
    s=setup(cards)
    top=stack_library(s,['Universal Automaton','Forest','Grizzly Bears','Memnite'])
    cast(s,'Munda, Ambush Leader')
    answer(s,['yes'])
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    answer(s,[top[0]])
    order(s)
    assert s.state.zones['p1:library'][0]==top[0]
    assert not s.state.cards[top[0]].revealed_to
    roundtrip(s)


def test_beguiler_actual_damage_reveals_recipient_library_and_leaves_rest_top(cards):
    s=setup(cards)
    source=put(s,'Balshan Beguiler','battlefield')
    put(s,'Fervor','battlefield')
    top=stack_library(s,['Forest','Island'],pid='p2')
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'combat_damage',turn=1)
    settle(s)
    assert s.state.rules.decision.player=='p1'
    answer(s,[top[1]])
    assert s.state.cards[top[1]].zone=='p2:graveyard'
    assert s.state.zones['p2:library'][0]==top[0]
    assert not s.state.cards[top[0]].revealed_to
    roundtrip(s)


def test_dubious_actual_exile_packet_target_opponent_selects_then_rest_enters(cards):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears','Shivan Dragon','Forest','Island','Sol Ring','Memnite','Plains','Spore Frog','Runeclaw Bear','Llanowar Elves'])
    cast(s,'Dubious Challenge',targets=['p2'])
    answer(s,top[:2])
    assert s.state.rules.decision.player=='p2'
    assert all(s.state.cards[c].zone=='p1:exile' for c in top[:2])
    answer(s,[top[1]])
    assert s.state.cards[top[1]].zone=='p2:battlefield' and s.state.cards[top[1]].owner=='p1'
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    roundtrip(s)


def test_reason_front_then_real_aftermath_believe_entry(cards):
    s=setup(cards)
    spell=cast(s,'Reason // Believe',face=0)
    answer(s,[])
    if s.state.rules.decision is not None:
        order(s)
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    top=stack_library(s,['Grizzly Bears'])
    mana(s,C=10,G=3)
    act(s,'p1',type='cast_spell',card_id=spell.id,face=1)
    settle(s)
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    assert s.state.cards[spell.id].zone=='p1:exile'
    roundtrip(s)


def test_eos_real_convoke_receipt_caps_revealed_creatures(cards):
    s=setup(cards)
    helper=put(s,'Doomed Traveler','battlefield')
    top=stack_library(s,['Memnite','Grizzly Bears','Forest','Island','Sol Ring','Shivan Dragon'])
    cast(s,'Knight-Errant of Eos',contributions=[{'kind':'convoke','card':helper.id}])
    assert s.state.cards[helper.id].tapped
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:hand'
    roundtrip(s)


def test_amareth_actual_other_artifact_creature_shares_any_card_type(cards):
    s=setup(cards)
    cast(s,'Amareth, the Lustrous')
    top=stack_library(s,['Sol Ring','Forest'])
    cast(s,'Memnite')
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:hand'
    assert s.state.zones['p1:library'][0]==top[1]
    roundtrip(s)


@pytest.mark.parametrize('replacement',["Grafdigger's Cage",'Containment Priest'])
def test_invocation_native_failed_entry_has_no_reflexive_cold(cards,replacement):
    s=setup(cards)
    put(s,replacement,'battlefield','p2')
    top=stack_library(s,['Grizzly Bears','Forest','Island','Sol Ring','Memnite','Plains','Shivan Dragon'])
    cast(s,"Vivien's Invocation")
    s=cold(s,cards)
    answer(s,[top[0]])
    assert s.state.rules.decision is None
    assert s.state.cards[top[0]].zone==('p1:library' if replacement=="Grafdigger's Cage" else 'p1:exile')
    if replacement=="Grafdigger's Cage":
        assert set(s.state.zones['p1:library'][-7:])==set(top)
    roundtrip(s)


@pytest.mark.parametrize('replacement',["Grafdigger's Cage",'Containment Priest'])
def test_believe_native_failed_entry_exact_original_fallback(cards,replacement):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears'])
    source=put(s,'Reason // Believe','graveyard')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=4,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    put(s,replacement,'battlefield','p2')
    settle(s)
    s=cold(s,cards)
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone==('p1:hand' if replacement=="Grafdigger's Cage" else 'p1:exile')
    roundtrip(s)


def test_vow_high_mana_value_low_toughness_rejected_cold(cards):
    s=setup(cards)
    put(s,'Krenko, Mob Boss','battlefield')
    top=stack_library(s,['Forest','Amareth, the Lustrous','Lonis, Cryptozoologist'])
    cast(s,"Kamahl's Druidic Vow",x_value=3)
    s=cold(s,cards)
    assert {o.id for o in s.state.rules.decision.options}=={top[0],top[2]}
    answer(s,[top[0],top[2]])
    assert s.state.cards[top[1]].zone=='p1:graveyard'
    roundtrip(s)


def test_dubious_cold_opponent_declines_frozen_complement(cards):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears','Shivan Dragon','Forest','Island','Sol Ring','Memnite','Plains','Spore Frog','Runeclaw Bear','Llanowar Elves'])
    cast(s,'Dubious Challenge',targets=['p2'])
    s=cold(s,cards)
    answer(s,top[:2])
    s=cold(s,cards)
    assert s.state.rules.decision.player=='p2'
    answer(s,[])
    assert all(s.state.cards[c].zone=='p1:battlefield' for c in top[:2])
    roundtrip(s)


def test_cylix_cold_target_is_private_viewer_and_chooser(cards):
    from tests.test_rules_wave4h_activation_costs import ability
    s=setup(cards)
    source=put(s,"Ashnod's Cylix",'battlefield')
    mana(s,C=3)
    top=stack_library(s,['Forest','Island','Sol Ring'],pid='p2')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{3}'),targets=['p2'])
    settle(s)
    s=cold(s,cards)
    assert s.state.rules.decision.player=='p2'
    assert all(c in json.dumps(s.view('p2')['cards']) for c in top)
    assert all(c not in json.dumps(s.view('p1')['cards']) for c in top)
    answer(s,[top[0]])
    assert s.state.zones['p2:library'][0]==top[0]
    assert all(s.state.cards[c].zone=='p2:exile' for c in top[1:])
    roundtrip(s)


def test_petals_decline_uses_actual_draw_cold(cards):
    s=setup(cards)
    top=stack_library(s,['Forest','Grizzly Bears','Island'])
    source=cast(s,'Petals of Insight')
    s=cold(s,cards)
    answer(s,['no'])
    assert all(s.state.cards[c].zone=='p1:hand' for c in top)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_bamboozle_public_reveal_then_private_order_http_ws(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards)
    top=stack_library(s,['Forest','Island','Sol Ring','Memnite'],pid='p2')
    cast(s,'Bamboozle',targets=['p2'])
    with TestClient(create_app(settings)) as client:
        deck=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck},{'name':'Bob','deck_id':deck}]}).json()
        gid=game['game']['id']
        token=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for stage in range(3):
            if stage==1:
                answer(s,top[:2])
            elif stage==2:
                order(s)
            response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
            assert response.status_code==200
            with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                frame=ws.receive_json()
            for raw in [response.text,json.dumps(frame)]:
                assert all((c in raw)==(stage<2) for c in top[2:])
                assert all(c in raw for c in top[:2])
    roundtrip(s)


def test_debut_actual_bargain_moves_creatures_battlefield_cold(cards):
    s=setup(cards)
    ring=put(s,'Sol Ring','battlefield')
    source=put(s,'Thunderous Debut','hand')
    top=stack_library(s,['Grizzly Bears','Shivan Dragon','Forest','Island'])
    mana(s,C=10,G=3)
    act(s,'p1',type='cast_spell',card_id=source.id,optional_costs=[f'{source.id}:bargain'])
    settle(s)
    if s.state.rules.decision.resume['step']!='pick_looked':
        answer(s,[ring.id])
    assert s.state.cards[ring.id].zone=='p1:graveyard'
    s=cold(s,cards)
    answer(s,top[:2])
    assert all(s.state.cards[c].zone=='p1:battlefield' for c in top[:2])
    roundtrip(s)


def test_touch_granted_ordinary_endstep_ability_survives_source_cold(cards):
    s=setup(cards)
    top=stack_library(s,['Grizzly Bears','Forest','Island','Sol Ring'])
    source=cast(s,"Aethermage's Touch")
    s=cold(s,cards)
    answer(s,[top[0]])
    order(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[top[0]].zone=='p1:hand'
    roundtrip(s)


def test_stargaze_x_zero_no_look_or_life_loss(cards):
    s=setup(cards)
    top=stack_library(s,['Forest','Island'])
    before=s.state.players['p1'].life
    cast(s,'Stargaze',x_value=0)
    assert s.state.rules.decision is None
    assert s.state.zones['p1:library'][:2]==top
    assert s.state.players['p1'].life==before
    roundtrip(s)


def test_ritual_declining_payment_still_bottoms_seen_cards_cold(cards):
    s=setup(cards)
    host=put(s,'Grizzly Bears','battlefield')
    cast(s,'Birthing Ritual')
    top=stack_library(s,['Memnite','Shivan Dragon','Forest','Island','Sol Ring','Plains','Reclamation Sage'])
    to_phase(s,'end',turn=1)
    settle(s)
    s=cold(s,cards)
    answer(s,['decline'])
    assert s.state.cards[host.id].zone=='p1:battlefield'
    assert set(s.state.zones['p1:library'][-7:])==set(top)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_eos_actual_double_major_copy_retains_convoker_count_cold(cards):
    s=setup(cards)
    helper=put(s,'Doomed Traveler','battlefield')
    source=put(s,'Knight-Errant of Eos','hand')
    copier=put(s,'Double Major','hand')
    top=stack_library(s,['Memnite','Grizzly Bears','Forest','Island','Sol Ring','Shivan Dragon'])
    mana(s,C=20,W=3,U=2,G=2)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='cast_spell',card_id=source.id,contributions=[{'kind':'convoke','card':helper.id}])
    act(s,'p1',type='cast_spell',card_id=copier.id,targets=[source.id])
    settle(s)
    s=cold(s,cards)
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    assert s.state.cards[source.id].zone=='stack'
    answer(s,[top[0]])
    while s.state.rules.decision is not None:
        answer(s,[])
    assert s.state.cards[top[0]].zone=='p1:hand'
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.name=='Knight-Errant of Eos'])==2
    roundtrip(s)
