"""Common Commander patterns through the rules engine, with real Oracle cards: token makers and
"whenever another creature enters", cast triggers, board wipes with dies triggers, blink, tutors
(private search), the monarch, looting, Treasure, and proliferate."""

from __future__ import annotations

import json

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import (
    mana,
    pass_until_stack_empty,
    replay_matches,
    rules,
    run_until,
    token,
)

ALICE = [(1, "Raise the Alarm"), (1, "Soul Warden"), (1, "Day of Judgment"), (1, "Cloudshift"), (1, "Rampant Growth"),
         (1, "Thorn of the Black Rose"), (1, "Young Pyromancer"), (1, "Merfolk Looter"), (1, "Prosperous Innkeeper"),
         (1, "Wrath of God"), (1, "Elvish Visionary"), (1, "Perilous Myr"), (6, "Forest"), (4, "Island")]


def resolve_all(s):
    """Pass until the stack is empty, putting simultaneous triggers in the offered order."""
    for _ in range(30):
        d = rules(s).decision
        if d is not None and d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is not None or not s.state.zones.get("stack"):
            return
        else:
            act(s, rules(s).priority, type="pass_priority")


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", ALICE)
    bob = deck(cards, "Atraxa, Praetors' Voice", [(12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def fetch(s, name, pid="p1"):
    """Put a named card from the library into the hand (test setup, by hand)."""
    card = next(s.state.cards[c] for c in zone(s.state, pid, "library") if s.state.cards[c].name == name)
    act(s, pid, type="move", card_ids=[card.id], to={"zone": "hand"})
    return card


def onto_battlefield(s, name, pid="p1"):
    card = fetch(s, name, pid)
    act(s, pid, type="move", card_ids=[card.id], to={"zone": "battlefield"})
    return card


def test_tokens_and_whenever_another_creature_enters(cards):
    s = build(cards)
    onto_battlefield(s, "Soul Warden")
    onto_battlefield(s, "Young Pyromancer")
    alarm = fetch(s, "Raise the Alarm")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=alarm.id)
    resolve_all(s)
    names = sorted(c.name for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")
    assert names == ["Elemental", "Soldier", "Soldier"]  # cast trigger + the spell
    assert s.state.players["p1"].life == 43  # Soul Warden: three creatures entered
    replay_matches(s)


def test_board_wipe_is_simultaneous_and_dies_triggers_look_back(cards):
    s = build(cards)
    warden = onto_battlefield(s, "Soul Warden")
    myr = onto_battlefield(s, "Perilous Myr")
    ox = token(s, "p2", "Ox", "2/4")
    wrath = fetch(s, "Wrath of God")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    deaths = [e for e in rules(s).events if e.kind == "zone_change" and (e.to_zone or "").endswith("graveyard")
              and e.from_zone and e.from_zone.endswith("battlefield")]
    assert len(deaths) == 3 and len({e.batch for e in deaths}) == 1  # one simultaneous event (the Ox token died too)
    d = rules(s).decision
    assert d.kind == "choose_one" and "Perilous Myr" in d.prompt  # the Myr died with everything else
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    pass_until_stack_empty(s)
    st = s.state
    assert st.cards[warden.id].zone == "p1:graveyard" and st.cards[myr.id].zone == "p1:graveyard" and ox.id not in st.cards
    assert st.players["p2"].life == 38
    replay_matches(s)


def test_cloudshift_makes_a_new_object_that_enters_again(cards):
    s = build(cards)
    visionary = onto_battlefield(s, "Elvish Visionary")
    act(s, "p1", type="counter", card_ids=[visionary.id], kind="+1/+1", delta=2)
    before_obj = rules(s).object_id(visionary.id)
    before_hand = len(zone(s.state, "p1", "hand"))
    shift = fetch(s, "Cloudshift")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=shift.id, targets=[visionary.id])
    pass_until_stack_empty(s)
    v = s.state.cards[visionary.id]
    assert v.zone == "p1:battlefield" and v.counters == {} and rules(s).object_id(v.id) != before_obj
    assert len(zone(s.state, "p1", "hand")) == before_hand + 1  # (+Cloudshift, −Cloudshift) and the enters trigger drew one
    replay_matches(s)


def test_rampant_growth_searches_privately(cards):
    s = build(cards)
    growth = fetch(s, "Rampant Growth")
    mana(s, G=2)
    library_before = set(zone(s.state, "p1", "library"))
    act(s, "p1", type="cast_spell", card_id=growth.id)
    d = rules(s).decision
    assert d.kind == "choose_cards" and d.player == "p1"
    assert {s.state.cards[o.id].name for o in d.options} <= {"Forest", "Island"}  # the server filtered: basic lands only
    bob = json.dumps(s.view("p2"))
    assert not any(o.id in bob for o in d.options) and "options" not in s.view("p2")["rules"]["decision"]
    forest = next(o.id for o in d.options if s.state.cards[o.id].name == "Forest")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[forest])
    assert s.state.cards[forest].zone == "p1:battlefield" and s.state.cards[forest].tapped
    assert not (set(zone(s.state, "p1", "library")) & library_before)  # shuffled: fresh ids


def test_the_monarch(cards):
    s = build(cards)
    thorn = fetch(s, "Thorn of the Black Rose")
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=thorn.id)
    pass_until_stack_empty(s)
    assert s.state.table.monarch == "p1"
    brute = token(s, "p2", "Brute", "3/3")  # (Bob's, since before his turn: not summoning sick then)
    hand_before = len(zone(s.state, "p1", "hand"))
    run_until(s, lambda s: s.state.turn.active_player == "p2")
    assert len(zone(s.state, "p1", "hand")) == hand_before + 1  # drew at the beginning of the monarch's end step
    run_until(s, lambda s: rules(s).decision is not None and rules(s).decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": brute.id, "target": "p1"}])
    run_until(s, lambda s: s.state.table.monarch == "p2" or s.state.turn.phase == "main2")
    assert s.state.table.monarch == "p2"  # combat damage to the monarch steals it


def test_looting_and_treasure(cards):
    s = build(cards)
    looter = onto_battlefield(s, "Merfolk Looter")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=0)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert d.kind == "choose_cards" and d.prompt == "Discard 1 card"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.cards[d.options[0].id].zone == "p1:graveyard"
    innkeeper = fetch(s, "Prosperous Innkeeper")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=innkeeper.id)
    resolve_all(s)
    treasure = next(c for c in s.state.cards.values() if c.name == "Treasure")
    assert treasure.zone == "p1:battlefield"
    visionary = fetch(s, "Elvish Visionary")
    act(s, "p1", type="clear_mana", player="p1")
    forest = fetch(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    act(s, "p1", type="cast_spell", card_id=visionary.id)  # {1}{G}: the Forest and the Treasure (sacrificed)
    resolve_all(s)
    assert treasure.id not in s.state.cards and s.state.cards[visionary.id].zone == "p1:battlefield"
    assert s.state.players["p1"].life == 41  # Innkeeper: another creature I control entered
    replay_matches(s)


def test_atraxa_proliferates_at_the_end_step(cards):
    s = build(cards)
    atraxa = next(c for c in s.state.cards.values() if c.name == "Atraxa, Praetors' Voice")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"zone": "battlefield"})
    act(s, "p2", type="counter", card_ids=[atraxa.id], kind="+1/+1", delta=1)
    act(s, "p2", type="resource", player="p1", key="poison", delta=2)
    run_until(s, lambda s: rules(s).decision is not None and rules(s).decision.prompt.startswith("Proliferate"))
    d = rules(s).decision
    assert d.player == "p2" and {o.id for o in d.options} == {atraxa.id, "p1"}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[atraxa.id, "p1"])
    assert s.state.cards[atraxa.id].counters["+1/+1"] == 2 and s.state.players["p1"].resources["poison"] == 3
