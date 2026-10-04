from tests.test_rules_wave15a_keyword_grants import *  # noqa: F403,F401
from tests.test_rules_wave15a_keyword_grants import card_db  # noqa: F401
from app.rules import scripts
from app.rules.plan import Plan


def test_dbg(cards):
    s = build(cards, "Pontiff of Blight", "Opt")
    put(s, "Pontiff of Blight")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    plan = Plan(s.state, "p1", s.cards, None)
    for c in s.state.cards.values():
        if c.zone == "p1:battlefield":
            ch = plan.ch(c)
            print(c.name, [(a.index, a.kind, a.text) for a in ch.abilities], ch.keywords)
            print({k: v.get("trigger") for k, v in scripts.definitions(ch).items()})
    opt = to_hand(s, "Opt")
    mana(s, U=1, W=2)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    print(s.state.rules.decision, [ (x) for x in s.state.zones.get("stack", [])])
    assert 0
