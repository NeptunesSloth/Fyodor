"""Wave 23A: more per-player group wordings (CR 608.2c, 101.4, 800.4a), each checked against real Oracle text.

"Each player who didn't discard a creature card this way loses 4 life" (Strongarm Tactics), "Each player who controls a permanent
named Bonder's Ornament draws a card", "Corrupted — Each opponent who has three or more poison counters loses 3 life" (Feed the
Infection), "each player who controls the most lands sacrifices two lands of their choice" (Tectonic Hellion: a tie qualifies all),
"Each opponent who lost life this turn sacrifices a creature with the greatest power among creatures they control" (Papalymo
Totolymo: each player's own creatures)."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, life, on_field, settle, to_hand
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"23A-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Strongarm Tactics", "{1}{B}", 2, "Sorcery", "Each player discards a card. Then each player who didn't discard a creature card this way loses 4 life.", colors="B"),
    real("Bonder's Ornament", "{3}", 3, "Artifact", "{T}: Add one mana of any color.\n{4}, {T}: Each player who controls a permanent named Bonder's Ornament draws a card."),
    real("Feed the Infection", "{2}{B}", 3, "Sorcery", "You draw three cards and you lose 3 life.\nCorrupted — Each opponent who has three or more poison counters loses 3 life.", colors="B"),
    real("Tectonic Hellion", "{2}{R}{R}", 4, "Creature — Hellion", "Haste\nWhenever this creature attacks, each player who controls the most lands sacrifices two lands of their choice.", ("4", "4"), "R"),
    real("Papalymo Totolymo", "{1}{B}", 2, "Legendary Creature — Moogle Wizard",
         "Whenever you cast a noncreature spell, Papalymo Totolymo deals 1 damage to each opponent and you gain 1 life.\n{4}, {T}, Sacrifice Papalymo Totolymo: Each opponent who lost life this turn sacrifices a creature with the greatest power among creatures they control.",
         ("1", "3"), "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build3(cards, mine=(), bob=(), carol=()):
    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (12, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (12, "Island")])
    c = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (12, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b), PlayerSetup("Carol", cards=c)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def hand(s, pid):
    return zone(s.state, pid, "hand")


def set_hand(s, pid, *names):
    for c in list(hand(s, pid)):
        act(s, pid, type="move", card_ids=[c], to={"zone": "library"})
    for n in names:
        c = next(c for c in s.state.cards.values() if c.name == n and c.owner == pid and c.zone == f"{pid}:library")
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})


def cast(s, name, **pool):
    c = to_hand(s, name)
    mana(s, "p1", **pool)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def names(s, pid, key="battlefield"):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, key))


@pytest.mark.parametrize("name", [e["name"] for e in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_strongarm_tactics_only_a_creature_card_saves_you(cards):
    s = build3(cards, mine=["Strongarm Tactics"], bob=["Tectonic Hellion"])
    set_hand(s, "p1", "Forest")  # (Alice's Tactics leaves her hand as she casts it)
    set_hand(s, "p2", "Tectonic Hellion")
    set_hand(s, "p3", "Mountain")
    cast(s, "Strongarm Tactics", B=1, C=1)
    settle(s)
    assert life(s, "p1") == 36 and life(s, "p2") == 40 and life(s, "p3") == 36  # only Bob discarded a creature card
    roundtrip(s)


def test_strongarm_tactics_an_empty_hand_discards_nothing_and_loses_life(cards):
    s = build3(cards, mine=["Strongarm Tactics"])
    set_hand(s, "p2")
    set_hand(s, "p3", "Mountain")
    cast(s, "Strongarm Tactics", B=1, C=1)
    settle(s)
    assert life(s, "p2") == 36 and life(s, "p3") == 36
    roundtrip(s)


def test_bonders_ornament_draws_for_each_player_who_controls_one(cards):
    s = build3(cards, mine=["Bonder's Ornament"], bob=["Bonder's Ornament"])
    mine = on_field(s, "Bonder's Ornament")
    on_field(s, "Bonder's Ornament", "p2")
    before = {p: len(hand(s, p)) for p in ("p1", "p2", "p3")}
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=1)
    settle(s)
    assert len(hand(s, "p1")) == before["p1"] + 1 and len(hand(s, "p2")) == before["p2"] + 1 and len(hand(s, "p3")) == before["p3"]
    roundtrip(s)


def test_feed_the_infection_only_opponents_with_three_poison_counters(cards):
    s = build3(cards, mine=["Feed the Infection"])
    act(s, "p1", type="resource", player="p2", key="poison", delta=3)
    act(s, "p1", type="resource", player="p3", key="poison", delta=2)
    cast(s, "Feed the Infection", B=1, C=2)
    settle(s)
    assert life(s, "p2") == 37 and life(s, "p3") == 40 and life(s, "p1") == 37
    roundtrip(s)


def test_tectonic_hellion_every_player_tied_for_the_most_lands(cards):
    s = build3(cards, mine=["Tectonic Hellion"])
    hellion = on_field(s, "Tectonic Hellion")
    for pid, n in (("p1", 3), ("p2", 3), ("p3", 2)):
        for _ in range(n):
            land = next(c for c in s.state.cards.values() if c.owner == pid and c.name in ("Forest", "Island", "Mountain")
                        and c.zone == f"{pid}:library")
            act(s, pid, type="move", card_ids=[land.id], to={"player": pid, "zone": "battlefield"})
    s.state.rules.controlled_since[hellion.id].turn = 0
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hellion.id, "target": "p2"}])
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    lands = {p: sum(1 for c in names(s, p) if c in ("Forest", "Island", "Mountain")) for p in ("p1", "p2", "p3")}
    assert lands == {"p1": 1, "p2": 1, "p3": 2}  # Alice and Bob tied for the most: two each; Carol has fewer and keeps hers
    roundtrip(s)


def test_papalymo_each_opponent_who_lost_life_sacrifices_their_own_greatest(cards):
    s = build3(cards, mine=["Papalymo Totolymo"])
    pap = on_field(s, "Papalymo Totolymo")
    big = creature(s, "p1", "Mine Big", "9/9")  # (Alice's own huge creature must not be chosen for Bob)
    small = creature(s, "p2", "Small", "1/1")
    large = creature(s, "p2", "Large", "3/3")
    other = creature(s, "p3", "Carols", "5/5")
    act(s, "p1", type="life", player="p2", delta=-1)  # Bob lost life this turn; Carol did not
    s.state.rules.controlled_since[pap.id].turn = 0
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=pap.id, ability=1)
    settle(s)
    assert large.id not in s.state.cards  # (a token: it ceased to exist)
    assert s.state.cards[small.id].zone == "p2:battlefield"
    assert s.state.cards[other.id].zone == "p3:battlefield" and s.state.cards[big.id].zone == "p1:battlefield"
    roundtrip(s)
