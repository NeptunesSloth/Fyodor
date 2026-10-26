from tests.test_rules_wave110j_s15 import *  # noqa
def test_dbg(cards):
    s = build(cards, [YURLOK], [], forests=30, islands=30)
    y = put_new(s, YURLOK)
    to_phase(s, "main1", turn=3)
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=y.id, ability=ability(s, y, "{1}, {T}"))
    print("STACK", s.state.zones.get("stack"), s.state.rules.decision, [ (p, s.state.players[p].mana) for p in ("p1","p2")], now(s,y).tapped)
    assert 0
