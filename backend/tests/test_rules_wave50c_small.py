"""Wave 50C: small pieces of commanders' text (CR 2026-09-25), real Oracle text (tests/fixtures/wave50c_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load.

* 119.3 / 608.2h: Astarion's "Feed - Target opponent loses life equal to the amount of life they lost this turn." (that player's own total).
* 614.17 / 122.1 / 702.164: Melira, Sylvok Outcast - "You can't get poison counters." (toxic gives none), "Creatures your opponents control lose infect." (their
  infect creatures deal ordinary damage, 702.90b).
* 701.28 / 700.2: Henrika Domnathi's "Transform Henrika." mode and "each creature you control with flying, deathtouch, and/or lifelink".
* 701.27a / 701.53: Glissa, Herald of Predation - "Transform all Incubator tokens you control."
* 611.2a: Sauron, Dino Devotee - "for as long as it has a saurian counter on it".
* 118.12 / 608.2c: Bill Ferny, Bree Swindler - "Target opponent gains control of target Horse you control. If they do, …".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ability, ask, attack, next_turn, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50c", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
TOXIC = card("Venomous Hound", set_code="w50c", number="P03", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Dog", oracle_text="Toxic 2", power="2",
             toughness="2", colors=["B"], color_identity=["B"], keywords=["Toxic"])
INFECT = card("Blight Imp", set_code="w50c", number="P04", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Phyrexian Imp", oracle_text="Infect", power="2",
              toughness="2", colors=["B"], color_identity=["B"], keywords=["Infect"])
HORSE = card("Wild Stallion", set_code="w50c", number="P05", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Horse", oracle_text="", power="2",
             toughness="2", colors=["G"], color_identity=["G"])


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, TOXIC, INFECT, HORSE], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


HENRIKA = "Henrika Domnathi // Henrika, Infernal Seer"


def settle_combat(s, limit=60):
    """Resolve everything; no attackers are declared."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def choose(s, *ids):
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards", d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def kws(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords


def poison(s, pid):
    return int(s.state.players[pid].resources.get("poison", 0))


# --- Astarion, the Decadent ---------------------------------------------------------------------------------------------------------------


def test_astarion_feed_drains_the_life_the_opponent_lost_this_turn(cards):
    s = build(cards, ["Astarion, the Decadent", "Lightning Bolt"], forests=30)
    put(s, "Astarion, the Decadent")
    stops(s)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    settle_combat(s)
    assert life(s, "p2") == 37
    to_phase(s, "end", turn=1)
    d = ask(s)
    assert [o.label[:4] for o in d.options] == ["Feed", "Frie"]
    choose(s, "0:0")
    settle_combat(s)
    d = s.state.rules.decision
    if d is not None:  # (the target: the one opponent)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
        settle_combat(s)
    assert life(s, "p2") == 34  # the 3 it lost to the Bolt, once more
    check(s)
    s = reloaded(s)
    assert life(s, "p2") == 34


def test_astarion_feed_with_no_life_lost_does_nothing(cards):
    s = build(cards, ["Astarion, the Decadent"], forests=30)
    put(s, "Astarion, the Decadent")
    to_phase(s, "end", turn=1)
    ask(s)
    choose(s, "0:0")
    settle_combat(s)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
        settle_combat(s)
    assert life(s, "p2") == 40
    check(s)


# --- Melira, Sylvok Outcast --------------------------------------------------------------------------------------------------------------


def hit_alice(cards, melira, attacker):
    """Bob's ``attacker`` hits Alice on Bob's turn 2, with Melira in play for Alice or not."""
    s = build(cards, ["Melira, Sylvok Outcast"] if melira else [], [attacker], forests=30)
    if melira:
        put(s, "Melira, Sylvok Outcast")
    put(s, attacker, "p2")
    stops(s)
    to_phase(s, "main1", turn=3)  # (what Bob put onto the table before has been there since the turn began)
    to_phase(s, "main1", turn=4)
    act(s, "p2", type="pass_priority") if False else None
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": card_named(s, attacker, "p2").id, "target": "p1"}])
    settle_combat(s)
    to_phase(s, "end", turn=4)
    return s


def test_melira_toxic_gives_no_poison_but_the_damage_is_dealt(cards):
    s = hit_alice(cards, True, "Venomous Hound")
    assert life(s) == 38 and poison(s, "p1") == 0
    check(s)
    s = hit_alice(cards, False, "Venomous Hound")  # (without Melira Alice is poisoned)
    assert life(s) == 38 and poison(s, "p1") == 2


def test_melira_makes_an_infect_attacker_deal_ordinary_damage(cards):
    s = hit_alice(cards, True, "Blight Imp")
    assert "infect" not in kws(s, "Blight Imp", "p2")
    assert life(s) == 38 and poison(s, "p1") == 0
    check(s)
    s = hit_alice(cards, False, "Blight Imp")
    assert life(s) == 40 and poison(s, "p1") == 2


# --- Henrika Domnathi ---------------------------------------------------------------------------------------------------------------------


def test_henrika_transform_mode_and_the_keyword_list_pump(cards):
    s = build(cards, [HENRIKA, "Grizzly Bears"], forests=30, islands=30)
    put(s, HENRIKA)
    put(s, "Grizzly Bears")
    stops(s)
    to_phase(s, "begin_combat", turn=1)
    d = ask(s)
    assert [o.label[:9] for o in d.options] == ["Each play", "You draw ", "Transform"]
    choose(s, "2:0")
    settle_combat(s)
    henrika = card_named(s, HENRIKA)
    assert henrika.face == 1  # Henrika, Infernal Seer
    assert pt(s, HENRIKA) == (3, 4)
    mana(s, B=3)
    act(s, "p1", type="activate_ability", card_id=henrika.id, ability=ability(s, HENRIKA, contains="Each creature you control with flying"))
    settle_combat(s)
    assert pt(s, HENRIKA) == (4, 4) and pt(s, "Grizzly Bears") == (2, 2)  # (Bears has none of the three keywords)
    check(s)
    s = reloaded(s)
    assert pt(s, HENRIKA) == (4, 4)
    to_phase(s, "begin_combat", turn=3)  # the back face has no trigger: nothing is asked
    assert s.state.rules.decision is None


# --- Glissa, Herald of Predation -------------------------------------------------------------------------------------------------------


def test_glissa_transforms_all_your_incubator_tokens(cards):
    s = build(cards, ["Glissa, Herald of Predation"], forests=30)
    put(s, "Glissa, Herald of Predation")
    to_phase(s, "begin_combat", turn=1)
    ask(s)
    choose(s, "0:0")  # Incubate 2 twice
    settle_combat(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.name == "Incubator" and c.zone == "p1:battlefield"]
    assert len(tokens) == 2 and all(c.face == 0 and c.counters.get("+1/+1") == 2 for c in tokens)
    check(s)
    s = reloaded(s)
    to_phase(s, "begin_combat", turn=3)
    ask(s)
    choose(s, "1:0")  # Transform all Incubator tokens you control
    settle_combat(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield" and c.name != "Glissa, Herald of Predation"]
    assert len(tokens) == 2 and all(c.face == 1 for c in tokens)
    assert [pt(s, "Phyrexian Token") for _ in tokens][0] == (2, 2)  # the 0/0 Phyrexian with two +1/+1 counters
    check(s)


# --- Sauron, Dino Devotee --------------------------------------------------------------------------------------------------------------


def test_sauron_dinosaur_lasts_only_as_long_as_the_counter(cards):
    s = build(cards, ["Sauron, Dino Devotee", "Grizzly Bears"], forests=30)
    bears = put(s, "Grizzly Bears")
    to_hand(s, "Sauron, Dino Devotee")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sauron, Dino Devotee").id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    choose(s, "1:0")  # Turn People into Dinosaurs
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle_combat(s)
    assert s.state.cards[bears.id].counters.get("saurian") == 1
    assert pt(s, "Grizzly Bears") == (5, 5)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id])
    assert "Dinosaur" in ch.subtypes and "Bear" not in ch.subtypes and ch.colors == frozenset({"G"})
    check(s)
    s = reloaded(s)
    assert pt(s, "Grizzly Bears") == (5, 5)
    act(s, "p1", type="counter", card_ids=[bears.id], kind="saurian", delta=-1)
    act(s, s.state.rules.priority, type="pass_priority")  # (the table is read again: 611.2b)
    assert pt(s, "Grizzly Bears") == (2, 2)  # the counter is gone: it is a Bear again


# --- Bill Ferny, Bree Swindler ----------------------------------------------------------------------------------------------------------


def blocked_bill(cards, mode):
    s = build(cards, ["Bill Ferny, Bree Swindler", "Wild Stallion"], ["Grizzly Bears"], forests=30)
    bill = put(s, "Bill Ferny, Bree Swindler")
    horse = put(s, "Wild Stallion")
    blocker = put(s, "Grizzly Bears", "p2")
    stops(s)
    next_turn(s)
    attack(s, bill)
    d = ask(s)
    assert d.kind == "declare_blockers"
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": bill.id}])
    d = ask(s)
    assert d.kind == "choose_cards"
    choose(s, mode)
    return s, bill, horse


def treasures(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Treasure" and c.zone == "p1:battlefield"]


def test_bill_ferny_gives_the_horse_away_and_leaves_combat_for_three_treasures(cards):
    s, bill, horse = blocked_bill(cards, "1:0")
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    settle_combat(s)
    assert s.state.cards[horse.id].controller == "p2" and s.state.cards[horse.id].owner == "p1"
    assert len(treasures(s)) == 3
    assert s.state.cards[bill.id].attacking is None  # removed from combat (506.4)
    check(s)
    s = reloaded(s)
    assert s.state.cards[horse.id].controller == "p2" and len(treasures(s)) == 3


def test_bill_ferny_first_mode_makes_one_treasure_and_keeps_the_horse(cards):
    s, bill, horse = blocked_bill(cards, "0:0")
    settle_combat(s)
    assert s.state.cards[horse.id].controller == "p1" and len(treasures(s)) == 1
    assert s.state.cards[bill.id].attacking is not None
    check(s)
