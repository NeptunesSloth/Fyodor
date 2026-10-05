from tests.game_helpers import act
from tests.test_rules_wave22e_history import card_db as card_db  # noqa: F401
from tests.test_rules_wave22e_history import settle_for, to_turn, front, put as put5, game
from tests.test_rules_wave5j_token_copies import drive, mana
from tests.wave9c_kit import build, card_named, check, to_hand, zone_of
from tests.wave9c_kit import put as kit_put


def test_prossh(cards):
    s = build(cards, ["Prossh, Skyraider of Kher"], [])
    p = to_hand(s, "Prossh, Skyraider of Kher")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1, "R": 1, "G": 1, "C": 4})
    act(s, "p1", type="cast_spell", card_id=p.id)
    settle_for(s)
    kob = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    print("kobolds", len(kob), s.state.rules.mana_pool if hasattr(s.state.rules, "mana_pool") else "")
    assert len(kob) == 6
    check(s)


def test_pit_dweller_undying(cards):
    s = build(cards, ["Treacherous Pit-Dweller"], [])
    d = kit_put(s, "Treacherous Pit-Dweller")
    act(s, "p1", type="move", card_ids=[d.id], to={"player": "p1", "zone": "graveyard"})  # (a manual move: not "dies")
    settle_for(s, "yes")
    print("zone", s.state.cards[d.id].zone)


def test_werewolf_extra_save(cards):
    s = game(cards, ["Mayor of Avabruck // Howlpack Alpha"], ["Probe Cantrip"])
    mayor = put5(s, "Mayor of Avabruck // Howlpack Alpha")
    to_turn(s, 2, "upkeep")
    from tests.test_rules_wave5j_token_copies import roundtrip
    roundtrip(s)
    drive(s)
    print(front(s, mayor), s.state.turn.phase)


from tests.fixtures.cards import card
from tests.test_rules_wave22e_history import EXTRA
EXTRA.append(card("Bothersome Quasit", set_code="t22e", number="E81", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Demon",
                  colors=["R"], color_identity=["R"], keywords=["Goad", "Menace"], power="3", toughness="2",
                  oracle_text="Menace\nGoaded creatures your opponents control can't block.\nWhenever you cast a noncreature spell, goad target creature an opponent controls. (Until your next turn, that creature attacks each combat if able and attacks a player other than you if able.)"))


def test_quasit(cards):
    from tests.test_rules_conditionals import until
    s = build(cards, ["Bothersome Quasit", "Probe Cantrip", "Probe Soldier"], ["Probe Soldier"])
    kit_put(s, "Bothersome Quasit")
    mine = kit_put(s, "Probe Soldier")
    s.state.rules.controlled_since[mine.id].turn = 0
    theirs = kit_put(s, "Probe Soldier", "p2")
    c = to_hand(s, "Probe Cantrip")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1})
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle_for(s, theirs.id, "yes")
    from tests.test_rules_wave5j_token_copies import ch as ch5
    from app.rules.keyword_actions import goaded_by
    print("GOADED", goaded_by(ch5(s, theirs)), [e for e in s.state.rules.log[-6:]] if hasattr(s.state.rules, "log") else "")
    from app.rules import coverage
    from tests.test_rules_wave22e_history import level
    print("LEVEL", level("Bothersome Quasit"))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers", limit=60)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers", limit=40)
    try:
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": mine.id}])
        print("BLOCK ACCEPTED")
    except Exception as e:
        print("block refused:", e)
