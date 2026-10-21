"""Fresh-process Ur-Sphinx through production registrations."""
from tests import test_rules_exile_sphinx49 as gameplay
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_exile_outcomes42_cold import fresh

cards=gameplay.cards



def test_ur_sphinx_cold_mill_packet_then_each_original_player_cast_choice(cards,tmp_path):
    from tests.game_helpers import act
    from tests.test_rules_library_look import settle
    from tests.test_rules_wave30m_durations import to_phase

    s=gameplay.gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx')
    put(s,'The Ur-Sphinx','battlefield')
    attacker=put(s,'Serra Sphinx','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    milled={p:put(s,'Divination','library',pid=p) for p in ('p1','p2','p3')}
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    settle(s)
    for player in ('p1','p2','p3'):
        d=s.state.rules.decision
        s=fresh(s,cards,tmp_path/(player+'.json'),d.player,{'type':'choose','decision_id':d.id,'option_ids':[milled[player].id]})
    assert all(s.state.cards[c.id].zone==p+':graveyard' for p,c in milled.items())
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    roundtrip(s)
