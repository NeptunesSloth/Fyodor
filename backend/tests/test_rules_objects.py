"""Game-object identity, last known information, simultaneous event batches, damage vs life
loss, player counters, and a player leaving a multiplayer game."""

from __future__ import annotations

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, enable, find, turn_on
from tests.test_rules_combat import creature, table


def rules(s):
    return s.state.rules


def test_a_card_that_changes_zones_is_a_new_object_and_its_last_known_information_is_kept(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    first = rules(s).object_id(krenko.id)
    act(s, "p1", type="counter", card_ids=[krenko.id], kind="+1/+1", delta=2)
    act(s, "p1", type="set_damage", card_ids=[krenko.id], delta=1)
    act(s, "p1", type="tap", card_ids=[krenko.id], tapped=True)
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "exile"})  # flicker…
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})  # …and back
    r = rules(s)
    second = r.object_id(krenko.id)
    assert first != second and second.startswith(krenko.id)  # same physical card, new rules object
    lki = r.lki[first]
    assert (lki.counters, lki.damage, lki.tapped, lki.zone) == ({"+1/+1": 2}, 1, True, "p1:battlefield")
    back = s.state.cards[krenko.id]
    assert back.counters == {} and back.damage == 0 and not back.tapped  # nothing carried over
    assert r.controlled_since[krenko.id].turn == s.state.turn.number  # summoning sick again


def test_simultaneous_deaths_are_one_event_batch_with_last_known_information(cards):
    s = table(cards)
    a = creature(s, "p1", "Ant", "2/2")
    b = creature(s, "p2", "Bee", "1/1")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=1)
    act(s, "p1", type="set_damage", card_ids=[a.id], delta=3)
    act(s, "p2", type="set_damage", card_ids=[b.id], delta=1)
    oid_a, oid_b = rules(s).object_id(a.id), rules(s).object_id(b.id)
    act(s, "p1", type="pass_priority")  # state-based actions: both die at once
    deaths = [e for e in rules(s).events if e.kind == "zone_change" and e.to_zone and e.to_zone.endswith(":graveyard")]
    assert {e.object_id for e in deaths} == {oid_a, oid_b}
    assert len({e.batch for e in deaths}) == 1  # simultaneous, not one after the other
    assert rules(s).lki[oid_a].counters == {"+1/+1": 1} and rules(s).lki[oid_a].damage == 3  # (a "dies" trigger reads this)
    assert a.id not in s.state.cards and b.id not in s.state.cards  # tokens: then they cease to exist


def test_combat_damage_is_damage_not_just_life_change(cards):
    s = table(cards)
    leech = creature(s, "p1", "Leech", "3/3", "Lifelink")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": leech.id, "target": "p2"}])
    while s.state.players["p2"].life == 40:
        d = rules(s).decision
        if d is not None and d.kind == "declare_blockers":
            act(s, "p2", type="declare_blockers", blocks=[])
        else:
            act(s, rules(s).priority, type="pass_priority")
    events = rules(s).events
    damage = next(e for e in events if e.kind == "damage")
    loss = next(e for e in events if e.kind == "life_loss")
    gain = next(e for e in events if e.kind == "life_gain")
    assert (damage.player, damage.amount, damage.combat, damage.source) == ("p2", 3, True, rules(s).object_id(leech.id))
    assert (loss.player, loss.amount, gain.player, gain.amount) == ("p2", 3, "p1", 3)
    assert damage.batch == loss.batch == gain.batch  # dealt simultaneously


def test_a_control_change_is_the_same_object(cards):
    s = table(cards)
    ox = creature(s, "p1", "Ox", "2/4")
    turn_on(s)
    act(s, "p1", type="counter", card_ids=[ox.id], kind="+1/+1", delta=1)
    act(s, "p1", type="set_damage", card_ids=[ox.id], delta=2)
    act(s, "p1", type="tap", card_ids=[ox.id], tapped=True)
    before = rules(s).object_id(ox.id)
    act(s, "p1", type="move", card_ids=[ox.id], to={"player": "p2", "zone": "battlefield"})  # Bob gains control
    moved = s.state.cards[ox.id]
    assert (moved.controller, moved.counters, moved.damage, moved.tapped) == ("p2", {"+1/+1": 1}, 2, True)
    assert rules(s).object_id(ox.id) == before
    assert rules(s).controlled_since[ox.id].controller == "p2"  # but it's new under Bob's control


def test_player_counters_are_generic(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="resource", player="p2", key="rad", delta=3)
    act(s, "p1", type="resource", player="p2", key="poison", delta=2)
    kinds = [(e.player, e.counter, e.amount) for e in rules(s).events if e.kind == "player_counters"]
    assert ("p2", "rad", 3) in kinds and ("p2", "poison", 2) in kinds


def test_a_player_leaving_takes_their_things_and_returns_what_they_controlled(cards):
    def deck(name):
        cmd = cards.resolve(name)
        return [DeckCard("commander", 1, cmd["name"], cmd["id"]), DeckCard("main", 5, "Forest", cards.resolve("Forest")["id"])]

    state = new_game([PlayerSetup("Alice", cards=deck("Krenko, Mob Boss")), PlayerSetup("Bob", cards=deck("Atraxa, Praetors' Voice")),
                      PlayerSetup("Carol", cards=deck("Krenko, Mob Boss"))], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    stolen = creature(s, "p1", "Stolen Bear")
    act(s, "p1", type="move", card_ids=[stolen.id], to={"player": "p2", "zone": "battlefield"})  # Bob controls it
    lent = find(s.state, "Forest", "p2")
    act(s, "p2", type="move", card_ids=[lent.id], to={"player": "p3", "zone": "battlefield"})  # Bob's card, Carol's side
    goblin = creature(s, "p2", "Bob's Goblin", "1/1")
    act(s, "p2", type="set_monarch", player="p2")
    act(s, "p2", type="concede")
    st = s.state
    assert st.cards[stolen.id].zone == "p1:battlefield"  # the control-changing effect ended
    assert st.cards[lent.id].zone == "p2:battlefield"  # Bob's own card left the shared game
    assert goblin.id not in st.cards  # Bob's token ceased to exist
    assert st.table.monarch == "p1"  # the active player becomes the monarch
    assert "p2" in rules(s).conceded and rules(s).priority in ("p1", "p3")
    assert rules(s).winner is None  # Alice and Carol play on
