"""Wave 100J (3): counter lines with choices (app/rules/counters100j.py), on the real Oracle text of tests/fixtures/wave100j_cards.json."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave21r_review import three
from tests.test_rules_wave30m_durations import stops
from tests.test_rules_wave100j_counters import card_db, counters, murder  # noqa: F401 (card_db: the fixture)
from tests.test_rules_wave100j_counters2 import ability, cast_on, library_card, resolve
from tests.wave9c_kit import build, check, mana, put
from tests.wave100e_kit import answer, chars, to_phase, tokens


def test_book_of_exalted_deeds_angel_keeps_you_in_the_game(cards):
    s = build(cards, ["The Book of Exalted Deeds", "Probe Angel", "Murder"])
    book, angel = put(s, "The Book of Exalted Deeds"), put(s, "Probe Angel")
    mana(s, W=3)
    act(s, "p1", type="activate_ability", card_id=book.id, ability=ability(s, book, "enlightened"), targets=[angel.id])
    answer(s)
    assert s.state.cards[book.id].zone == "p1:exile" and counters(s, angel, "enlightened") == 1
    act(s, "p1", type="counter", card_ids=[angel.id], kind="enlightened", delta=-1)  # (the counter is only a reminder: the ruling)
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")
    assert "p1" not in s.state.rules.lost  # 104.3a: she doesn't lose for having 0 life
    murder(s, angel)
    assert "p1" in s.state.rules.lost and s.state.rules.winner == "p2"
    check(s)


def test_super_adaptoid_copies_each_keyword_it_lacks_as_a_counter(cards):
    s = build(cards, ["Super-Adaptoid"], ["Probe Drake"])
    drake = put(s, "Probe Drake", "p2")
    sa = cast_on(s, "Super-Adaptoid", [], C=2)
    answer(s, drake.id)
    assert {k: v for k, v in s.state.cards[sa.id].counters.items() if v} == {"flying": 1, "trample": 1}
    assert {"flying", "trample"} <= chars(s, sa).keywords
    check(s)


@pytest.mark.parametrize("payers", [(), ("p2",), ("p2", "p3")])
def test_desecration_demon_each_opponent_may_sacrifice_in_turn_order(cards, payers):
    s = three(cards, ["Desecration Demon"], ["Grizzly Bears"], ["Grizzly Bears"])
    demon = put(s, "Desecration Demon")
    bears = {pid: put(s, "Grizzly Bears", pid) for pid in ("p2", "p3")}
    to_phase(s, "begin_combat")
    asked = []

    def choose(d):
        ids = [o.id for o in d.options]
        if "decline" in ids:
            asked.append(d.player)
            return ["pay"] if d.player in payers else ["decline"]
        return [bears[d.player].id] if bears.get(d.player) and bears[d.player].id in ids else ids[:1]

    resolve(s, choose)
    assert asked == ["p2", "p3"]  # 101.4: in turn order
    assert all((s.state.cards[bears[p].id].zone == f"{p}:graveyard") == (p in payers) for p in ("p2", "p3"))
    assert s.state.cards[demon.id].tapped == bool(payers) and counters(s, demon) == (1 if payers else 0)  # one counter at most (the ruling)
    check(s)


@pytest.mark.parametrize("choice", ["put", "remove", "neither"])
def test_lavabrink_floodgates_the_upkeep_player_chooses_then_three_doom_counters_blow(cards, choice):
    s = build(cards, ["Lavabrink Floodgates", "Grizzly Bears"], ["Probe Ogre"])
    gates, bear, ogre = put(s, "Lavabrink Floodgates"), put(s, "Grizzly Bears"), put(s, "Probe Ogre", "p2")
    act(s, "p1", type="counter", card_ids=[gates.id], kind="doom", delta=2)
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=1)  # Bob's upkeep: he chooses
    d = s.state.rules.decision
    while d is None or d.kind != "choose_one":
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[choice])
    answer(s)
    blown = choice == "put"
    assert (s.state.cards[gates.id].zone == "p1:graveyard") == blown
    assert all((s.state.cards[c.id].zone.endswith("graveyard")) == blown for c in (bear, ogre))  # 6 damage to each creature
    if not blown:
        assert counters(s, gates, "doom") == {"remove": 1, "neither": 2}[choice]
    check(s)


@pytest.mark.parametrize("lands", [True, False])
def test_terrapact_intimidator_the_opponent_picks_landers_or_counters(cards, lands):
    s = build(cards, ["Terrapact Intimidator"])
    kav = cast_on(s, "Terrapact Intimidator", [], R=1, C=1)
    resolve(s, lambda d: ["p2"] if "p2" in [o.id for o in d.options] else (["pay"] if lands else ["decline"]) if d.player == "p2" else [d.options[0].id])
    assert len(tokens(s, "Lander", "p1")) == (2 if lands else 0) and counters(s, kav) == (0 if lands else 2)
    check(s)


def test_dimension_x_pizzasaur_counts_every_counter_among_your_permanents(cards):
    s = build(cards, ["Dimension X Pizzasaur", "Grizzly Bears", "Sol Ring"], ["Grizzly Bears", "Probe Ogre"])
    mine, ring = put(s, "Grizzly Bears"), put(s, "Sol Ring")
    act(s, "p1", type="counter", card_ids=[ring.id], kind="charge", delta=1)
    bear, ogre = put(s, "Grizzly Bears", "p2"), put(s, "Probe Ogre", "p2")
    offered = []

    def choose(d):
        ids = [o.id for o in d.options]
        if mine.id in ids and d.min_choices >= 1 and not offered:
            return [mine.id]  # the two +1/+1 counters: then 3 counters among her permanents
        offered.append(set(ids))
        return [ogre.id] if ogre.id in ids else ids[: max(1, d.min_choices)]

    cast_on(s, "Dimension X Pizzasaur", [], B=1, C=3)
    resolve(s, choose)
    assert counters(s, mine) == 2 and s.state.cards[ogre.id].zone == "p2:graveyard"  # mana value 3 <= 2 + 1
    assert any(bear.id in o for o in offered)
    check(s)


def test_dismantle_moves_the_count_of_any_counters_as_the_kind_you_choose(cards):
    s = build(cards, ["Dismantle", "Sol Ring"], ["Sol Ring"])
    mine, theirs = put(s, "Sol Ring"), put(s, "Sol Ring", "p2")
    act(s, "p2", type="counter", card_ids=[theirs.id], kind="charge", delta=2)
    act(s, "p2", type="counter", card_ids=[theirs.id], kind="fuse", delta=1)
    cast_on(s, "Dismantle", [theirs.id], R=1, C=2)
    resolve(s, lambda d: [f"{mine.id}|+1/+1"])
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and counters(s, mine) == 3  # how many, of any kind (the ruling)
    check(s)


def test_valors_reach_warriors_grow_only_when_another_token_attacks_too(cards):
    from tests.test_rules_wave100j_counters import combat

    s = build(cards, ["Probe Tag", "Grizzly Bears", "Raise the Alarm"])
    tag, bear = put(s, "Probe Tag"), put(s, "Grizzly Bears")
    cast_on(s, "Raise the Alarm", [], W=1, C=1)
    answer(s)
    soldier = tokens(s, "Soldier", "p1")[0]
    combat(s, [tag, bear])
    assert counters(s, tag) == 0  # the other attacker isn't a token
    combat(s, [tag, soldier])
    assert counters(s, tag) == 1
    check(s)


def test_quarantine_field_targets_one_for_each_isolation_counter_not_for_x(cards):
    s = build(cards, ["Quarantine Field", "Doubling Season"], ["Sol Ring", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Doubling Season")
    ring, bear, elves = (put(s, n, "p2") for n in ("Sol Ring", "Grizzly Bears", "Llanowar Elves"))
    seen = []

    def choose(d):
        seen.append(d.max_choices)
        return [ring.id, bear.id]

    field = library_card(s, "Quarantine Field")
    act(s, "p1", type="move", card_ids=[field.id], to={"zone": "hand"})
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=field.id, x_value=1)
    resolve(s, choose)
    assert counters(s, field, "isolation") == 2 and seen == [2]  # X 1, doubled entering: two counters, two targets (the ruling)
    assert s.state.cards[ring.id].zone == "p2:exile" and s.state.cards[bear.id].zone == "p2:exile" and s.state.cards[elves.id].zone == "p2:battlefield"
    check(s)


def test_xathrid_gorgon_petrifies_for_good(cards):
    s = build(cards, ["Xathrid Gorgon"], ["Llanowar Elves"])
    gorgon, elves = put(s, "Xathrid Gorgon"), put(s, "Llanowar Elves", "p2")
    to_phase(s, "main1", turn=2)
    mana(s, B=1, C=2)
    act(s, "p1", type="activate_ability", card_id=gorgon.id, ability=ability(s, gorgon, "petrification"), targets=[elves.id])
    answer(s)
    act(s, "p2", type="counter", card_ids=[elves.id], kind="petrification", delta=-1)  # (it doesn't depend on the counter: the ruling)
    to_phase(s, "main1", turn=1)
    ch = chars(s, elves)
    assert {"Artifact", "Creature"} <= set(ch.types) and not ch.colors and "defender" in ch.keywords and "cant_activate" in ch.imposed
    check(s)
