"""Wave 110E session 10: Oracle-text scenarios for cards promoted this session (each docstring names the rule)."""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.test_rules_wave110e_cards import answer, card_db, cast  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

REPROACH = real("Teferi's Reproach", "{2}{W}{W}", 4, "Instant",
                "Choose target opponent. Until that player's next turn, they gain protection from everything and their life total can't change. "
                "All nonland permanents they control phase out. (While they're phased out, they're treated as though they don't exist. "
                "They phase in before that player untaps during their next untap step.)\nExile Teferi's Reproach.", None, "W")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
DRAIN = real("Test Drain", "{B}", 1, "Sorcery", "Each opponent loses 3 life.", None, "B")
BLADE = real("Sanctuary Blade", "{2}", 2, "Artifact — Equipment",
             "As this Equipment becomes attached to a creature, choose a color.\nEquipped creature gets +2/+0 and has protection from the last chosen color.\nEquip {3}", None, "")
MONITOR = real("Monitor Monitor", "{2}{U}", 3, "Creature — Human Wizard",
               "When this creature enters, open an Attraction. (Put the top card of your Attraction deck onto the battlefield.)\n"
               "Once each turn, you may pay {1} to reroll one or more dice you rolled.", ("1", "3"), "U")
ROLL = real("Test Roll", "{B}", 1, "Sorcery", "Roll a six-sided die. You gain life equal to the result.", None, "B")
IMP = real("Maddening Imp", "{4}{B}", 5, "Creature — Imp",
           "Flying\n{T}: Non-Wall creatures the active player controls attack this turn if able. At the beginning of the next end step, destroy each of those creatures "
           "that didn't attack this turn. Activate only during an opponent's turn and only before combat.", ("2", "2"), "B")
WALL = real("Test Wall", "{1}{W}", 2, "Creature — Wall", "", ("0", "4"), "W")
VEC = real("Oracle en-Vec", "{2}{W}", 3, "Creature — Human Wizard",
           "{T}: Target opponent chooses any number of creatures they control. During that player's next turn, the chosen creatures attack if able, and other creatures can't "
           "attack. At the beginning of that turn's end step, destroy each of the chosen creatures that didn't attack this turn. Activate only during your turn.", ("1", "1"), "W")
SLOTH = real("Test Sloth", "{1}{G}", 2, "Creature — Sloth", "Defender", ("0", "3"), "G")
MARVEL = real("Ms. Marvel, Kamala Khan", "{2}{U}", 3, "Legendary Creature — Mutant Inhuman Hero", "Reach, vigilance\nYou have no maximum hand size.\n"
              "Embiggen Fist — Whenever you cast a spell that targets a creature you control, draw a card. "
              "Until end of turn, Ms. Marvel gains \"Ms. Marvel's base power is equal to the number of cards in your hand.\"", ("1", "4"), "U")
PUMP = real("Test Pump", "{G}", 1, "Instant", "Target creature gets +1/+1 until end of turn.", None, "G")
base.EXTRA.extend([MARVEL, PUMP, REPROACH, BEAR, DRAIN, BLADE, MONITOR, ROLL, IMP, WALL, VEC, SLOTH])


@pytest.mark.parametrize("name", ["Teferi's Reproach", "Sanctuary Blade", "Monitor Monitor", "Maddening Imp", "Oracle en-Vec", "Ms. Marvel, Kamala Khan"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_teferis_reproach_shields_the_opponent_until_their_next_turn(cards):
    """702.16j, 119.7, 702.26: target opponent has protection from everything, life can't change, nonland permanents phase out; all end at their turn."""
    s = build(cards, ["Teferi's Reproach", "Test Drain"], ["Test Bear", "Test Bear"])
    bear = put(s, "Test Bear", "p2")
    mana(s, W=2, C=2, B=1)
    cast(s, "Teferi's Reproach", ["p2"])
    answer(s)
    assert s.state.cards[bear.id].zone.endswith(":phased")
    cast(s, "Test Drain")
    answer(s)
    assert life(s, "p2") == 40
    check(s)
    stops(s, "upkeep")
    to_phase(s, "upkeep", 2)
    assert not s.state.cards[bear.id].zone.endswith(":phased")
    assert not s.state.rules.life_locks and not s.state.rules.player_shields
    check(s)


def _keywords(s, card):
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])
    return {k.lower() for k in ch.keywords} | {a.text.lower() for a in ch.abilities}


def _equip(s, blade, bear, color):
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=2, targets=[bear.id])
    answer(s, *([color] if color else []))


def test_sanctuary_blade_chooses_a_color_each_time_it_becomes_attached(cards):
    """701.3a: the controller chooses as it becomes attached (equip); the grant uses the last chosen color: +2/+0 and protection from it."""
    s = build(cards, ["Sanctuary Blade", "Test Bear", "Test Bear"])
    blade, bear = put(s, "Sanctuary Blade"), put(s, "Test Bear")
    _equip(s, blade, bear, "Red")
    assert s.state.cards[bear.id].attached_to is None and s.state.cards[blade.id].attached_to == bear.id
    assert pt(s, "Test Bear") == (4, 2) and "protection from red" in _keywords(s, bear)
    check(s)
    bear2 = card_named(s, "Test Bear")
    other = next(c for c in s.state.cards.values() if c.name == "Test Bear" and c.id != bear.id and c.owner == "p1")
    put_bear = act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "battlefield"})  # noqa: F841
    _equip(s, blade, other, "Green")
    assert s.state.cards[blade.id].attached_to == other.id
    assert "protection from green" in _keywords(s, other) and "protection from red" not in _keywords(s, other)
    assert "protection from red" not in _keywords(s, bear2) or bear2.id == other.id
    check(s)


@pytest.mark.parametrize(("reroll", "second", "life"), [(True, 6, 46), (True, 1, 41), (False, 6, 42)])
def test_monitor_monitor_rerolls_before_the_result_counts(cards, monkeypatch, reroll, second, life):
    """706.2a-b: paying {1} rerolls the chosen dice and the new natural result is final; declining keeps the first roll; once each turn."""
    from tests.test_rules_random_consequences import faces

    s = build(cards, ["Monitor Monitor", "Test Roll", "Test Roll"])
    put(s, "Monitor Monitor")
    faces(monkeypatch, [2, second, 4])
    mana(s, B=1, C=1)
    cast(s, "Test Roll")
    d = s.state.rules.decision
    assert d is not None and d.options[0].id.startswith("roll_adjust42:")
    if not reroll:
        pick(s, ["done"])
    else:
        pick(s, [d.options[0].id])
        assert [o.id for o in s.state.rules.decision.options][0] == "pay"
        pick(s, ["pay"])
        assert s.state.rules.decision.kind == "choose_cards"
        pick(s, ["0"])
    answer(s)
    assert life_of(s) == life
    check(s)
    if reroll:  # once each turn: the second roll is not offered another reroll
        mana(s, B=1, C=1)
        cast(s, "Test Roll")
        answer(s)
        assert life_of(s) == life + 4


def pick(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def life_of(s):
    return s.state.players["p1"].life


def test_maddening_imp_forces_non_wall_attackers_and_destroys_the_ones_that_did_not(cards):
    """508.1d + 603.7: the active player's non-Wall creatures must attack; at the next end step those that didn't (a summoning-sick one) are destroyed,
    the Wall and the attacker survive."""
    from tests.test_rules_player_protection import priority

    s = build(cards, ["Maddening Imp"], ["Test Bear", "Test Bear", "Test Wall"])
    imp, wall, bear = put(s, "Maddening Imp"), put(s, "Test Wall", "p2"), put(s, "Test Bear", "p2")
    stops(s, "main1")
    to_phase(s, "main1", 4)
    sick = next(c for c in s.state.cards.values() if c.name == "Test Bear" and c.id != bear.id)
    act(s, "p2", type="move", card_ids=[sick.id], to={"player": "p2", "zone": "battlefield"})
    priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=imp.id, ability=1)
    answer(s)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p1"}])
    check(s)
    stops(s, "end")
    to_phase(s, "end", 4)
    answer(s)
    zone = {n: s.state.cards[i].zone for n, i in (("bear", bear.id), ("wall", wall.id), ("sick", sick.id))}
    assert zone == {"bear": "p2:battlefield", "wall": "p2:battlefield", "sick": "p2:graveyard"}
    check(s)


def _vec_turn(cards, chosen_names):
    """Alice (turn 3) taps Oracle en-Vec on Bob; Bob chooses ``chosen_names`` of his Bear, Bear, Sloth; returns the state at Bob's declare attackers (turn 4)."""
    from tests.test_rules_player_protection import priority

    s = build(cards, ["Oracle en-Vec"], ["Test Bear", "Test Bear", "Test Sloth"])
    vec = put(s, "Oracle en-Vec")
    bears = [c for c in s.state.cards.values() if c.name == "Test Bear" and c.owner == "p2"]
    for c in (*bears, card_named(s, "Test Sloth", "p2")):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    stops(s, "main1")
    to_phase(s, "main1", 3)
    priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=vec.id, ability=0, targets=["p2"], target_counts=[1])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.player == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    ids = {"bear0": bears[0].id, "bear1": bears[1].id, "sloth": card_named(s, "Test Sloth", "p2").id}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[ids[n] for n in chosen_names])
    answer(s)
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and s.state.turn.number == 4:
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, ids


def test_oracle_en_vec_chosen_attack_others_stay_home_and_unattackers_die(cards):
    """508.1d, 508.1c, 603.7: the chosen Bear must attack and the unchosen Bear can't; the chosen Defender can't, so it is destroyed at the end step."""
    s, ids = _vec_turn(cards, ["bear0", "sloth"])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": ids["bear0"], "target": "p1"}, {"card_id": ids["bear1"], "target": "p1"}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": ids["bear0"], "target": "p1"}])
    check(s)
    stops(s, "end")
    to_phase(s, "end", 4)
    answer(s)
    assert {n: s.state.cards[i].zone for n, i in ids.items()} == {"bear0": "p2:battlefield", "bear1": "p2:battlefield", "sloth": "p2:graveyard"}
    check(s)


def test_oracle_en_vec_choosing_nothing_still_stops_every_attack(cards):
    """508.1c: with no creature chosen, no creature can attack that turn."""
    s, ids = _vec_turn(cards, [])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": ids["bear0"], "target": "p1"}])
    act(s, "p2", type="declare_attackers", attackers=[])
    check(s)


@pytest.mark.parametrize("target", ["Test Bear", "Ms. Marvel, Kamala Khan"])
def test_ms_marvel_base_power_is_the_hand_size_all_turn_and_only_for_a_creature_you_target(cards, target):
    """613.4b, 611.3a: a spell targeting a creature you control draws a card and sets her base power to the cards in hand, counted continuously this turn
    (a +1/+1 pump on her is added on top, 613.4c); the next turn she is a 1/4 again."""
    s = build(cards, ["Ms. Marvel, Kamala Khan", "Test Bear", "Test Pump", "Test Pump"])
    marvel, bear = put(s, "Ms. Marvel, Kamala Khan"), put(s, "Test Bear")
    mana(s, G=1)
    assert pt(s, "Ms. Marvel, Kamala Khan") == (1, 4)
    cast(s, "Test Pump", [(marvel if target.startswith("Ms") else bear).id])
    answer(s)
    hand = len(s.state.zones["p1:hand"])
    bonus = 1 if target.startswith("Ms") else 0
    assert pt(s, "Ms. Marvel, Kamala Khan") == (hand + bonus, 4 + bonus)
    to_hand(s, "Test Pump")  # one more card in hand: her base power follows
    assert pt(s, "Ms. Marvel, Kamala Khan") == (hand + 1 + bonus, 4 + bonus)
    check(s)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main1", 3)
    assert pt(s, "Ms. Marvel, Kamala Khan") == (1, 4)
