"""Wave 110E session 11: Oracle-text scenarios (each docstring names the rule)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db, cast  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

THROWDOWN = real("Lethal Throwdown", "{1}{B}", 2, "Instant",
                 "As an additional cost to cast this spell, sacrifice a creature or sacrifice a modified creature. (Equipment, Auras you control, and counters are modifications.)\n"
                 "Destroy target creature or planeswalker. If the modified creature was sacrificed, draw a card.", None, "B")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
BOON = real("Test Boon", "{1}{G}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2.", None, "G")
STORY = real("Storyweave", "{2}{G}", 3, "Instant", "Choose one \u2014\n\u2022 Put two +1/+1 counters on target creature you control.\n"
             "\u2022 Put two lore counters on target Saga you control. The next time one or more enchantment creatures you control enter this turn, "
             "each enters with two additional +1/+1 counters on it.", None, "G")
SAGA = real("Test Saga", "{1}{G}", 2, "Enchantment \u2014 Saga", "I \u2014 You gain 1 life.\nII \u2014 You gain 1 life.\nIII \u2014 You gain 1 life.", None, "G")
RALLY = real("Test Rally", "{W}", 1, "Sorcery", "Return all creature cards from your graveyard to the battlefield.", None, "W")
RADIATE = real("Radiate", "{3}{R}{R}", 5, "Instant", "Choose target instant or sorcery spell that targets only a single permanent or player. Copy that spell for each other permanent "
               "or player the spell could target. Each copy targets a different one of those permanents and players.", None, "R")
CHILL = real("Winter's Chill", "{X}{U}", 1, "Instant", "Cast this spell only during combat before blockers are declared.\nX can't be greater than the number of snow lands you control.\n"
             "Choose X target attacking creatures. For each of those creatures, its controller may pay {1} or {2}. If that player doesn't, destroy that creature at end of combat. "
             "If that player pays only {1}, prevent all combat damage that would be dealt to and dealt by that creature this combat.", None, "U")
SNOW = real("Test Snow Island", "", 0, "Basic Snow Land \u2014 Island", "({T}: Add {U}.)")
SPIRIT = real("Test Spirit", "{1}{W}", 2, "Enchantment Creature \u2014 Spirit", "", ("1", "1"), "W")
GIANT = real("Test Giant", "{4}{G}", 5, "Creature — Giant", "", ("0", "9"), "G")
RAPTOR = real("Test Raptor", "{2}{R}", 3, "Creature — Dinosaur", "", ("3", "2"), "R")
_REAL = json.loads((Path(__file__).parent / "fixtures" / "wave110e_cards.json").read_text("utf-8"))  # real Oracle text, from data/cards.sqlite
FEUD = real("Bitter Feud", "{4}{R}", 5, "Enchantment", "As this enchantment enters, choose two players.\nIf a source controlled by one of the chosen players would deal "
            "damage to the other chosen player or a permanent that player controls, that source deals double that damage to that player or permanent instead.", None, "R")
BOLT = real("Test Bolt", "{R}", 1, "Instant", "Test Bolt deals 3 damage to any target.", None, "R")
base.EXTRA.extend([THROWDOWN, BEAR, BOON, RAPTOR, GIANT, STORY, SAGA, SPIRIT, RALLY, RADIATE, CHILL, SNOW, FEUD, BOLT, *(card(c["name"], set_code="w110e", number=f"E{i:03d}", **{k: v for k, v in c.items() if k != "name"})
                                                    for i, c in enumerate(_REAL))])


@pytest.mark.parametrize("name", ["Lethal Throwdown", "Bitter Feud", "Radiate", "Winter's Chill", "Storyweave", "Saheeli's Lattice // Mastercraft Raptor"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(("mod", "draws"), [(None, 0), ("counter", 1), ("aura", 1)])
def test_lethal_throwdown_draws_only_for_a_modified_sacrifice(cards, mod, draws):
    """700.9, 608.2h: the sacrificed creature is read as it last existed: a counter or an Aura on it makes it modified."""
    s = build(cards, ["Lethal Throwdown", "Test Bear", "Test Boon"], ["Test Bear"])
    mine = put(s, "Test Bear")
    victim = put(s, "Test Bear", "p2")
    if mod == "counter":
        s.state.cards[mine.id].counters["+1/+1"] = 1
    if mod == "aura":
        s.state.cards[put(s, "Test Boon").id].attached_to = mine.id
    hand = len(s.state.zones["p1:hand"])
    mana(s, B=1, C=1)
    cast(s, "Lethal Throwdown", [victim.id])
    answer(s, mine.id)
    assert s.state.cards[mine.id].zone == "p1:graveyard" and s.state.cards[victim.id].zone == "p2:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + draws
    check(s)


def test_mastercraft_raptor_power_is_the_total_power_of_the_crafted_cards(cards):
    """702.167a: the exiled Dinosaurs (power 3 + 3) are the craft materials; the back face's power is their total (toughness stays 4)."""
    s = build(cards, ["Saheeli's Lattice // Mastercraft Raptor", "Test Raptor", "Test Raptor"])
    lattice = put(s, "Saheeli's Lattice // Mastercraft Raptor")
    raptors = [c for c in s.state.cards.values() if c.name == "Test Raptor" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[c.id for c in raptors], to={"player": "p1", "zone": "graveyard"})
    mana(s, R=1, C=4)
    act(s, "p1", type="activate_ability", card_id=lattice.id, ability=1, cost_choices=[{"component": 2, "cards": [c.id for c in raptors]}])
    answer(s)
    assert s.state.cards[lattice.id].face == 1 and all(s.state.cards[c.id].zone == "p1:exile" for c in raptors)
    assert pt(s, "Saheeli's Lattice // Mastercraft Raptor") == (6, 4)
    check(s)


def _three(cards, mine, carols=("Test Bolt",)):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (10, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Test Giant"), (1, "Test Bolt"), (10, "Mountain")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carols), (10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def _feud(cards):
    s = _three(cards, ["Bitter Feud", "Test Bolt", "Test Bear", "Test Giant"])
    mana(s, R=1, C=4)
    cast(s, "Bitter Feud")
    answer(s, "p1,p2")
    feud = next(c for c in s.state.cards.values() if c.name == "Bitter Feud")
    assert feud.zone == "p1:battlefield" and feud.choices.get("Chosen players") == "Alice and Bob"
    return s


@pytest.mark.parametrize(("hit", "doubled"), [("p2", True), ("p3", False), ("p1", False), ("bear", True), ("mybear", False)])
def test_bitter_feud_doubles_damage_between_the_two_chosen_players(cards, hit, doubled):
    """614.12a: p1 chooses two players (p1, p2) as it enters; 614.1: a source controlled by one chosen player deals double to the OTHER one or its permanents only."""
    s = _feud(cards)
    mybear = put(s, "Test Giant")
    big = put(s, "Test Giant", "p2") if hit == "bear" else mybear
    target = {"bear": big.id, "mybear": mybear.id}.get(hit, hit)
    before = {p: s.state.players[p].life for p in ("p1", "p2", "p3")}
    mana(s, R=1)
    cast(s, "Test Bolt", [target])
    answer(s)
    if hit.startswith("p"):
        assert before[hit] - s.state.players[hit].life == (6 if doubled else 3)
    else:
        assert s.state.cards[big.id].damage == (6 if doubled else 3)
    check(s)


def test_bitter_feud_the_other_chosen_player_and_an_unchosen_source(cards):
    """614.1: Bob's source hitting Alice is doubled (each chosen player's sources count); Carol's source (not chosen) hitting Alice is not."""
    s = _feud(cards)
    for pid, doubled in (("p2", True), ("p3", False)):
        before = s.state.players["p1"].life
        bolt = to_hand(s, "Test Bolt", pid)
        s.state.rules.priority = pid
        mana(s, pid, R=1)
        act(s, pid, type="cast_spell", card_id=bolt.id, targets=["p1"])
        answer(s)
        assert before - s.state.players["p1"].life == (6 if doubled else 3)
    check(s)


def _counters(s, card):
    return s.state.cards[card.id].counters.get("+1/+1", 0)


def test_storyweave_second_mode_arms_one_batch_of_enchantment_creatures(cards):
    """614.1c, 614.12: the first entry event with enchantment creatures gives each +2 counters (a plain creature entering first does not use it up); a later one gets none."""
    s = build(cards, ["Storyweave", "Test Saga", "Test Rally", "Test Spirit", "Test Spirit", "Test Spirit", "Test Bear"])
    saga = put(s, "Test Saga")
    spirits = [c for c in s.state.cards.values() if c.name == "Test Spirit" and c.owner == "p1"]
    bear = card_named(s, "Test Bear")
    mana(s, G=1, C=2)
    cast(s, "Storyweave", [saga.id], modes=[1])
    answer(s)
    assert s.state.cards[saga.id].counters.get("lore", 0) >= 2
    mana(s, G=1, C=1)
    cast(s, "Test Bear")  # a plain creature enters first: the shot stays armed
    answer(s)
    assert _counters(s, bear) == 0 and s.state.rules.effects
    act(s, "p1", type="move", card_ids=[c.id for c in spirits[:2]], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1)
    cast(s, "Test Rally")
    answer(s)
    assert [_counters(s, c) for c in spirits[:2]] == [2, 2]
    mana(s, W=1, C=1)
    cast(s, "Test Spirit")
    answer(s)
    assert _counters(s, spirits[2]) == 0
    check(s)


def test_radiate_copies_the_spell_for_each_other_permanent_or_player(cards):
    """707.10d: Bolt targets Bob; Radiate copies it for every other player and permanent it could target (Alice, Carol, both Giants): each copy hits a different one."""
    s = _three(cards, ["Test Bolt", "Radiate", "Test Giant", "Test Giant"])
    mine = put(s, "Test Giant")
    theirs = put(s, "Test Giant", "p2")
    before = {p: s.state.players[p].life for p in ("p1", "p2", "p3")}
    act(s, "p1", type="set_stops", own=["main1"], others=["main1"], smart_pass=False, hold_priority=True)  # (Alice keeps priority after casting, to respond)
    radiate = to_hand(s, "Radiate")
    mana(s, R=3, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bolt").id, targets=["p2"])
    bolt = s.state.cards[s.state.zones["stack"][-1]]
    act(s, "p1", type="cast_spell", card_id=radiate.id, targets=[bolt.id])
    answer(s)
    lost = {p: before[p] - s.state.players[p].life for p in before}
    assert lost == {"p1": 3, "p2": 3, "p3": 3}
    assert s.state.cards[mine.id].damage == 3 and s.state.cards[theirs.id].damage == 3
    check(s)


def _chill(cards, first, second, x=2, snow=2):
    """Alice attacks with two bears; Bob (holding Winter's Chill, X snow lands) targets both during declare attackers; Alice answers per bear: "pay2" / "pay1" / "no"."""
    from tests.wave110b_kit import attack

    s = build(cards, ["Test Bear", "Test Bear"], ["Winter's Chill", "Test Snow Island", "Test Snow Island"])
    bears = [c for c in s.state.cards.values() if c.name == "Test Bear" and c.owner == "p1"]
    for c in bears:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    islands = [c for c in s.state.cards.values() if c.name == "Test Snow Island" and c.owner == "p2"]
    act(s, "p2", type="move", card_ids=[c.id for c in islands[:snow]], to={"player": "p2", "zone": "battlefield"})
    chill = to_hand(s, "Winter's Chill", "p2")
    act(s, "p2", type="set_stops", own=[], others=["declare_attackers"], smart_pass=True)
    attack(s, *bears)
    mana(s, "p2", U=1, C=x)
    mana(s, "p1", C=6)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    assert s.state.turn.phase == "declare_attackers" and s.state.rules.priority == "p2"
    if first is None:
        with pytest.raises(ActionError, match="X can't be greater than 1"):
            act(s, "p2", type="cast_spell", card_id=chill.id, x_value=x, targets=[b.id for b in bears], target_counts=[x])
        return s, bears, 0
    act(s, "p2", type="cast_spell", card_id=chill.id, x_value=x, targets=[b.id for b in bears], target_counts=[x])
    life = s.state.players["p2"].life
    for want in ((first, second) if first else ()):
        d = s.state.rules.decision
        assert d is not None and d.player == "p1", d
        if want == "pay2" and "pay" in [o.id for o in d.options]:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
        else:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
            if want == "pay1":
                d = s.state.rules.decision
                act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
            elif want == "no":
                d = s.state.rules.decision
                act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    return s, bears, life


@pytest.mark.parametrize(("first", "second", "dead", "dmg"), [("pay2", "no", [False, True], 4), ("pay1", "no", [False, True], 2), ("no", "pay2", [True, False], 4)])
def test_winters_chill_each_controller_decides_creature_by_creature(cards, first, second, dead, dmg):
    """118.12, 614: pay {2}: nothing; pay only {1}: that creature's combat damage (dealt and received) is prevented; pay nothing: destroyed at end of combat."""
    from tests.wave110b_kit import through_combat

    s, bears, life = _chill(cards, first, second)
    through_combat(s)
    assert [s.state.cards[b.id].zone.endswith(":graveyard") for b in bears] == dead
    assert life - s.state.players["p2"].life == dmg
    check(s)


def test_winters_chill_x_is_capped_by_the_snow_lands(cards):
    """601.2b: X can't be greater than the number of snow lands you control (one snow land: X = 2 is refused)."""
    _chill(cards, None, None, snow=1)
