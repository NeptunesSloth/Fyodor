"""Wave MBC-D: the last two Commander-legal Mystery Booster Commander cards (app/rules/mbc_d.py), real Oracle text (data/cards.sqlite), and the
machinery they need: a player leaving the game as an event with what they controlled as it last existed (app/rules/left_game.py, 800.4a),
and every random choice of the rules engine recorded as one event (app/rules/randomness.py). Every scenario checks the replay and a save and
a load."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_planechase_events import EXTRA as PLANAR
from tests.test_rules_planechase_events import PLANES, _InOrder
from tests.test_rules_planechase_events import roll as roll_planar
from tests.test_rules_wave12a_counters_keywords import real, rolls
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave47b_kit import EXTRA as W47B
from tests.wave47b_kit import build3, cast, life, pin_random

HIGHWATER = ("Menace\nWhenever Miss Highwater deals combat damage to a player who doesn't have a contract counter, they may discard their hand. "
             "If they do, they draw seven cards and get a contract counter. For as long as they have a contract counter, when they lose the game, "
             "for each artifact and creature they controlled, create a token that's a copy of it.")
CHIRA = ("Whenever you discard one or more cards at random, select one or more targets at random, choose one or more modes at random, flip one or "
         "more coins, or roll one or more dice, put a +1/+1 counter on Chira and create a tapped Treasure token.")
EXTRA = [
    real("Miss Highwater", "{2}{B}{B}", 4, "Legendary Creature — Demon Advisor", HIGHWATER, ("5", "3"), "B"),
    real("Chira, All In", "{3}{R}", 4, "Legendary Creature — Human Rogue", CHIRA, ("3", "3"), "R"),
    real("Pardic Swordsmith", "{2}{R}", 3, "Creature — Dwarf", "{R}, Discard a card at random: This creature gets +2/+0 until end of turn.",
         ("1", "1"), "R"),
    real("Sorcerer's Strongbox", "{4}", 4, "Artifact", "{2}, {T}: Flip a coin. If you win the flip, sacrifice this artifact and draw three cards."),
    real("Circuits Act", "{2}{R}", 3, "Sorcery", "Roll three six-sided dice. For each different result, create a 1/1 white Clown Robot artifact "
         "creature token.", None, "R"),
    real("Goblin Lore", "{1}{R}", 2, "Sorcery", "Draw four cards, then discard three cards at random.", None, "R"),
    real("Ornithopter", "{0}", 0, "Artifact Creature — Thopter", "Flying", ("0", "2")),
]
INSECT = {"name": "Insect", "type_line": "Token Creature — Insect", "power": "1", "toughness": "1", "colors": ["G"]}


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    known = {*have, *(c["name"] for c in W47B)}
    planar = [c for c in PLANAR if c["name"] not in known]
    known |= {c["name"] for c in planar}
    build_database([*fixture_cards(), *W47B, *planar, *(c for c in EXTRA if c["name"] not in known)], settings.cards_db_path,
                   meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Miss Highwater", "Chira, All In"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Miss Highwater ------------------------------------------------------------------------------------------------------------------------
def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == f"{pid}:battlefield"]


def highwater_table(cards):
    """Alice (Miss Highwater, Blaze, Lightning Bolt), Bob (Sol Ring, Grizzly Bears, Ornithopter and an Insect token on the battlefield, an Island)
    and Carol (Hill Giant, which Bob controls); Alice's second turn, main phase, Highwater ready to attack."""
    s = build3(cards, ["Miss Highwater", "Blaze", "Lightning Bolt"], bobs=["Sol Ring", "Grizzly Bears", "Ornithopter"], carols=["Hill Giant"])
    hw = put(s, "Miss Highwater")
    for name in ("Sol Ring", "Grizzly Bears", "Ornithopter", "Island"):
        put(s, name, "p2")
    act(s, "p2", type="create_token", player="p2", token=INSECT)
    giant = card_named(s, "Hill Giant", "p3")
    act(s, "p3", type="move", card_ids=[giant.id], to={"player": "p2", "zone": "battlefield"})  # (Carol's card, Bob controls it)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    return s, hw


def hit(s, hw, accept=True):
    """Highwater attacks Bob unblocked; Bob answers "discard your hand"."""
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hw.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p2" and s.state.rules.decision.kind != "declare_blockers")
    d = s.state.rules.decision
    ids = [o.id for o in d.options]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes" if accept else "no"] if "yes" in ids else [ids[0 if accept else -1]])
    settle(s)


def kill_bob(s):
    to_hand(s, "Blaze")
    mana(s, R=1, C=40)
    cast(s, "Blaze", targets=["p2"], x_value=40)
    settle(s)


def test_a_contract_then_a_loss_copies_each_artifact_and_creature_bob_controlled(cards):
    s, hw = highwater_table(cards)
    hit(s, hw)
    assert s.state.players["p2"].resources.get("contract") == 1
    assert len(s.state.zones["p2:hand"]) == 7  # (the hand discarded, seven drawn)
    assert life(s, "p2") == 35
    check(s)
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None)
    kill_bob(s)
    assert "p2" in s.state.rules.lost
    # Sol Ring, Grizzly Bears, Ornithopter, the Insect token and Carol's Hill Giant (Bob controlled it): copies under Alice's control; not the Island
    assert {n: len(tokens(s, n)) for n in ("Sol Ring", "Grizzly Bears", "Ornithopter", "Insect", "Hill Giant", "Island")} == {
        "Sol Ring": 1, "Grizzly Bears": 1, "Ornithopter": 1, "Insect": 1, "Hill Giant": 1, "Island": 0}
    assert not tokens(s, "Sol Ring", "p3") and not tokens(s, "Grizzly Bears", "p3")
    bears = tokens(s, "Grizzly Bears")[0]
    assert (s.state.cards[bears.id].controller, s.state.cards[bears.id].owner) == ("p1", "p1")
    check(s)


def test_a_concession_is_a_loss_and_highwater_need_not_be_there_any_more(cards):
    s, hw = highwater_table(cards)
    hit(s, hw)
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[hw.id])  # (5/3: she dies; the delayed ability outlives her, 603.7)
    assert s.state.cards[hw.id].zone == "p1:graveyard"
    act(s, "p2", type="concede")
    settle(s)
    assert "p2" in s.state.rules.conceded
    assert len(tokens(s, "Grizzly Bears")) == 1 and len(tokens(s, "Sol Ring")) == 1 and len(tokens(s, "Insect")) == 1
    assert not any(c.is_token and c.zone.startswith("p3:") for c in s.state.cards.values())  # (Carol is untouched, and still in the game)
    assert "p3" not in s.state.rules.lost and "p3" not in s.state.rules.conceded
    check(s)


def test_declining_makes_no_contract_and_no_copies(cards):
    s, hw = highwater_table(cards)
    hit(s, hw, accept=False)
    assert not s.state.players["p2"].resources.get("contract")
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None)
    kill_bob(s)
    assert "p2" in s.state.rules.lost and not tokens(s, "Grizzly Bears") and not tokens(s, "Sol Ring")
    check(s)


def test_losing_the_contract_counter_ends_it(cards):
    s, hw = highwater_table(cards)
    hit(s, hw)
    act(s, "p2", type="set_resource", player="p2", key="contract", value=0)  # (611.2b: no longer "as long as they have a contract counter")
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None)
    kill_bob(s)
    assert "p2" in s.state.rules.lost and not tokens(s, "Grizzly Bears") and not tokens(s, "Sol Ring")
    assert not any(t.when.get("kind") == "player_left" for t in s.state.rules.delayed)
    check(s)


def test_another_players_loss_does_not_trigger_it(cards):
    s, hw = highwater_table(cards)
    hit(s, hw)
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None)
    to_hand(s, "Blaze")
    mana(s, R=1, C=40)
    cast(s, "Blaze", targets=["p3"], x_value=40)
    settle(s)
    assert "p3" in s.state.rules.lost and not tokens(s, "Hill Giant") and not tokens(s, "Grizzly Bears")
    assert any(t.when.get("kind") == "player_left" and t.when.get("player") == "p2" for t in s.state.rules.delayed)
    check(s)


# -- Chira, All In ---------------------------------------------------------------------------------------------------------------------------
def chira_state(s, pid="p1"):
    chira = card_named(s, "Chira, All In", pid)
    return s.state.cards[chira.id].counters.get("+1/+1", 0), len([c for c in tokens(s, "Treasure", pid) if c.tapped])


def test_a_random_discard_effect_triggers_it_once(cards, monkeypatch):
    pin_random(monkeypatch, 0)
    s = build(cards, ["Chira, All In", "Goblin Lore"])
    put(s, "Chira, All In")
    to_hand(s, "Goblin Lore")
    mana(s, R=2)
    cast(s, "Goblin Lore")  # three cards discarded at random at once: one event (603.2c)
    settle(s)
    assert chira_state(s) == (1, 1)
    check(s)


def test_a_random_discard_cost_triggers_it(cards, monkeypatch):
    pin_random(monkeypatch, 0)
    s = build(cards, ["Chira, All In", "Pardic Swordsmith", "Goblin Lore"])
    put(s, "Chira, All In")
    smith = put(s, "Pardic Swordsmith")
    to_hand(s, "Goblin Lore")
    mana(s, R=1)
    activate(s, "p1", smith)
    settle(s)
    assert s.state.cards[card_named(s, "Goblin Lore").id].zone == "p1:graveyard"  # (the only card in hand: discarded at random)
    assert chira_state(s) == (1, 1)
    check(s)


def test_an_opponents_random_discard_does_not_trigger_yours(cards, monkeypatch):
    pin_random(monkeypatch, 0)
    s = build(cards, ["Goblin Lore"], ["Chira, All In"])
    put(s, "Chira, All In", "p2")
    to_hand(s, "Goblin Lore")
    mana(s, R=2)
    cast(s, "Goblin Lore")
    settle(s)
    assert chira_state(s, "p2") == (0, 0)
    check(s)


@pytest.mark.parametrize("index", [0, 1])
def test_a_target_selected_at_random_triggers_it(cards, monkeypatch, index):
    pin_random(monkeypatch, index)
    s = build3(cards, ["Chira, All In", "Scab-Clan Giant"], bobs=["Grizzly Bears"], carols=["Hill Giant"])
    put(s, "Chira, All In")
    put(s, "Grizzly Bears", "p2")
    put(s, "Hill Giant", "p3")
    to_hand(s, "Scab-Clan Giant")
    mana(s, R=1, G=1, C=4)
    cast(s, "Scab-Clan Giant")
    settle(s)
    assert chira_state(s) == (1, 1)
    check(s)


def test_a_mode_chosen_at_random_triggers_it(cards, monkeypatch):
    pin_random(monkeypatch, 0)
    s = build3(cards, ["Chira, All In", "Typhoid Mary, Fractured"])
    put(s, "Chira, All In")
    mary = put(s, "Typhoid Mary, Fractured")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mary.id, "target": "p2"}])
    settle(s)
    assert chira_state(s) == (1, 1)
    check(s)


def test_a_coin_flip_triggers_it(cards):
    s = build(cards, ["Chira, All In", "Sorcerer's Strongbox"])
    put(s, "Chira, All In")
    box = put(s, "Sorcerer's Strongbox")
    mana(s, C=2)
    activate(s, "p1", box)
    settle(s)
    assert chira_state(s) == (1, 1)
    check(s)


def test_rolling_three_dice_triggers_it_once(cards, monkeypatch):
    rolls(monkeypatch, 1, 2, 2)
    s = build(cards, ["Chira, All In", "Circuits Act"])
    put(s, "Chira, All In")
    to_hand(s, "Circuits Act")
    mana(s, R=1, C=2)
    cast(s, "Circuits Act")
    settle(s)
    assert chira_state(s) == (1, 1)
    assert len(tokens(s, "Clown Robot")) == 2
    check(s)


def test_a_death_triggers_target_chosen_at_random_triggers_it(cards, monkeypatch):
    """Knight Rampager: "When this creature dies, it deals 4 damage to target opponent chosen at random." — its controller selects it."""
    pin_random(monkeypatch)
    s = build3(cards, ["Chira, All In", "Knight Rampager", "Blaze"])
    put(s, "Chira, All In")
    knight = put(s, "Knight Rampager")
    to_hand(s, "Blaze")
    mana(s, R=6)
    cast(s, "Blaze", targets=[knight.id], x_value=5)
    settle(s)
    assert (life(s, "p2"), life(s, "p3")) == (40, 36)
    assert chira_state(s) == (1, 1)
    check(s)


def test_a_random_choice_of_another_kind_does_not_trigger_it(cards, monkeypatch):
    """Indoraptor's enrage: "choose an opponent at random" — a random choice (of a player), but none of Chira's five kinds."""
    pin_random(monkeypatch, 0)
    s = build3(cards, ["Chira, All In", "Indoraptor, the Perfect Hybrid", "Lightning Bolt"])
    put(s, "Chira, All In")
    indo = put(s, "Indoraptor, the Perfect Hybrid")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[indo.id])
    settle(s, answer="no")
    assert "chosen at random" in str(s.view("p1")["log"])
    assert chira_state(s) == (0, 0)
    check(s)


def test_rolling_the_planar_die_triggers_it(cards, monkeypatch):
    """706.7, 901.9d: rolling the planar die triggers "whenever a player rolls one or more dice" abilities."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from app.game.state import GameSettings, PlanarCard
    from tests.game_helpers import deck, enable

    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=PLANES[n][0] == "Phenomenon") for n in ("Krosa", "Goldmeadow")]
    state = new_game([PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, "Chira, All In"), (9, "Forest")])),
                      PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]))], shuffle=False, first_player=0,
                     settings=GameSettings(planechase=True, planar_deck_size=2), planar_pool=lambda: pool, rng=_InOrder())
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    put(s, "Chira, All In")
    roll_planar(s, monkeypatch, 4)  # a blank
    settle(s)
    assert chira_state(s) == (1, 1)
    check(s)
