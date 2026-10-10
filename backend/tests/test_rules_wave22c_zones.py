"""Wave 22C: "reveal ~ and shuffle it into its owner's library instead" vs "exile instead" (CR 614.1a, 614.6, 616.1).

Real Oracle text (tests/fixtures/wave22c_cards.json, from data/cards.sqlite). The 616.1 choice is tried both ways: a wrong
order would be silent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.state import zone_key
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_replacements2 import permanent, reload
from tests.test_rules_wave5j_token_copies import drive, game, mana, put, roundtrip

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave22c_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t22c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def zone_of(s, c):
    """Where the card is now (by name: a card entering a library gets a new opaque id)."""
    return next(x.zone for x in s.state.cards.values() if x.name == c.name and not x.is_token and x.owner == c.owner)


def graveyard(s, pid="p1"):
    return s.state.zones.get(zone_key(pid, "graveyard"), [])


def sacrifice(s):
    """A permanent whose ability makes its controller sacrifice a creature (Blightsteel is the only one)."""
    t = permanent(s, "p1", "Sacrificer", "Enchantment", "{1}: Sacrifice a creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0)


def order_question(pick):
    return lambda d: [pick] if d.resume.get("step") == "zone_replace_order" else None


def test_blightsteel_is_shuffled_into_its_owners_library_not_put_into_the_graveyard(cards):
    s = game(cards, ["Blightsteel Colossus"])
    blight = put(s, "Blightsteel Colossus")
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature dies, you gain 1 life.")
    before = len(s.state.zones[zone_key("p1", "library")])
    sacrifice(s)
    drive(s)
    assert zone_of(s, blight) == "p1:library" and len(s.state.zones[zone_key("p1", "library")]) == before + 1
    assert not graveyard(s) and s.state.players["p1"].life == 40  # (614.6: it never died)
    roundtrip(s)


@pytest.mark.parametrize("pick, where", [("exile", "p1:exile"), ("library:shuffle", "p1:library")])
def test_blightsteel_with_rest_in_peace_the_controller_chooses_616_1_both_orders(cards, pick, where):
    s = game(cards, ["Blightsteel Colossus"], bob=["Rest in Peace"])
    blight = put(s, "Blightsteel Colossus")
    put(s, "Rest in Peace", pid="p2")
    sacrifice(s)
    drive(s, order_question(pick))
    assert zone_of(s, blight) == where and not graveyard(s)
    roundtrip(s)


def test_the_616_1_question_is_the_controllers_survives_reload_and_changes_nothing_until_answered(cards):
    s = game(cards, ["Blightsteel Colossus"], bob=["Rest in Peace"])
    blight = put(s, "Blightsteel Colossus")
    put(s, "Rest in Peace", pid="p2")
    sacrifice(s)
    d = s.state.rules.decision
    for _ in range(5):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.resume["step"] == "zone_replace_order"
    assert {o.id for o in d.options} == {"exile", "library:shuffle"} and zone_of(s, blight) == "p1:battlefield"
    other = s.view("p2")["rules"]["decision"]
    assert not other or not other.get("options")
    s2 = reload(s, cards)
    act(s2, "p1", type="choose", decision_id=d.id, option_ids=["library:shuffle"])
    assert zone_of(s2, blight) == "p1:library"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["exile"])
    assert zone_of(s, blight) == "p1:exile" and s.state.rules.decision is None
    replay_matches(s)


@pytest.mark.parametrize("pick, where", [("library:shuffle", "p1:library"), ("exile", "p1:exile")])
def test_nexus_of_fate_resolves_and_is_shuffled_in_or_exiled_by_choice(cards, pick, where):
    s = game(cards, ["Nexus of Fate"], bob=["Rest in Peace"])
    put(s, "Rest in Peace", pid="p2")
    nexus = put(s, "Nexus of Fate", "hand")
    mana(s, U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=nexus.id)
    drive(s, order_question(pick))
    assert zone_of(s, nexus) == where
    replay_matches(s)


def test_nexus_of_fate_alone_is_shuffled_in_without_a_question(cards):
    s = game(cards, ["Nexus of Fate"])
    nexus = put(s, "Nexus of Fate", "hand")
    mana(s, U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=nexus.id)
    drive(s)
    assert zone_of(s, nexus) == "p1:library" and s.state.rules.decision is None
    roundtrip(s)


def test_a_milled_blightsteel_is_shuffled_back_instead(cards):
    s = game(cards, ["Blightsteel Colossus"])
    blight = put(s, "Blightsteel Colossus", "library")
    act(s, "p1", type="move", card_ids=[blight.id], to={"player": "p1", "zone": "library"}, position="top")
    miller = permanent(s, "p1", "Miller", "Enchantment", "{1}: Target player mills a card.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=miller.id, ability=0, targets=["p1"])
    drive(s)
    assert zone_of(s, blight) == "p1:library" and not graveyard(s)
    roundtrip(s)


# == "If it would leave the battlefield, exile it instead of putting it anywhere else." (Whip of Erebos, Geth, 614.1a) ==
WHIP = ("{1}: Return target creature card from your graveyard to the battlefield. It gains haste. Exile it at the beginning of the "
        "next end step. If it would leave the battlefield, exile it instead of putting it anywhere else.")
GETH = ("{1}: Return target creature card from your graveyard to the battlefield. It gains \"If this creature would leave the "
        "battlefield, exile it instead of putting it anywhere else.\"")


def reanimate(s, text):
    bear = put(s, "Grizzly Bears", "graveyard")
    t = permanent(s, "p1", "Reanimator", "Enchantment", text)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0, targets=[bear.id])
    drive(s)
    return next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield")


@pytest.mark.parametrize("text", [WHIP, GETH])
@pytest.mark.parametrize("how, mover", [("sacrificed", "{1}: Sacrifice a creature."), ("bounced", "{1}: Return target creature to its owner's hand.")])
def test_a_reanimated_creature_that_would_leave_is_exiled_instead(cards, text, how, mover):
    s = game(cards, ["Grizzly Bears"])
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature dies, you gain 1 life.")
    bear = reanimate(s, text)
    mover_card = permanent(s, "p1", "Mover", "Enchantment", mover)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=mover_card.id, ability=0, **({"targets": [bear.id]} if "target" in mover else {}))
    drive(s)
    assert zone_of(s, bear) == "p1:exile" and not graveyard(s) and s.state.players["p1"].life == 40  # (never died)
    roundtrip(s)


# == exile instead, plus a token (Kalitas, 614.1a, 614.6) or a reflexive trigger (Head of the Hunt, 603.12) ==
KILL = "{1}: Destroy target creature."


def zombies(s, name="Zombie"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == "p1:battlefield"]


def kill(s, victim):
    t = permanent(s, "p1", "Killer", "Enchantment", KILL)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0, targets=[victim.id])


def test_kalitas_exiles_an_opponents_nontoken_creature_and_creates_a_zombie(cards):
    s = game(cards, ["Kalitas, Traitor of Ghet"], bob=["Grizzly Bears"])
    put(s, "Kalitas, Traitor of Ghet")
    victim = put(s, "Grizzly Bears", pid="p2")
    kill(s, victim)
    drive(s)
    assert zone_of(s, victim) == "p2:exile" and len(zombies(s)) == 1 and not graveyard(s, "p2")
    roundtrip(s)


def test_kalitas_does_not_apply_to_tokens_or_your_own_creatures(cards):
    s = game(cards, ["Kalitas, Traitor of Ghet", "Grizzly Bears"])
    put(s, "Kalitas, Traitor of Ghet")
    own = put(s, "Grizzly Bears")
    kill(s, own)
    drive(s)
    assert zone_of(s, own) == "p1:graveyard" and not zombies(s)


def test_kalitas_with_parallel_lives_makes_two_zombies(cards):
    s = game(cards, ["Kalitas, Traitor of Ghet", "Parallel Lives"], bob=["Grizzly Bears"])
    put(s, "Kalitas, Traitor of Ghet")
    put(s, "Parallel Lives")
    victim = put(s, "Grizzly Bears", pid="p2")
    kill(s, victim)
    drive(s)
    assert zone_of(s, victim) == "p2:exile" and len(zombies(s)) == 2
    roundtrip(s)


@pytest.mark.parametrize("tokens", [0, 1])
def test_kalitas_with_rest_in_peace_asks_the_victims_controller_both_orders(cards, tokens):
    s = game(cards, ["Kalitas, Traitor of Ghet"], bob=["Grizzly Bears", "Rest in Peace"])
    put(s, "Kalitas, Traitor of Ghet")
    put(s, "Rest in Peace", pid="p2")
    victim = put(s, "Grizzly Bears", pid="p2")
    kill(s, victim)
    d = s.state.rules.decision
    for _ in range(5):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.resume["step"] == "zone_replace_order"  # the affected object's controller (616.1)
    labels = {o.id: o.label for o in d.options}
    plain = next(k for k, v in labels.items() if v.startswith("Rest in Peace"))
    rider = next(k for k in labels if k != plain)
    assert "create" in labels[rider].lower() or "token" in labels[rider].lower(), labels
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[plain if tokens == 0 else rider])
    drive(s)
    assert zone_of(s, victim) == "p2:exile" and len(zombies(s)) == tokens
    replay_matches(s)


def test_head_of_the_hunt_is_a_reflexive_trigger_that_makes_the_wolf_afterwards(cards):
    s = game(cards, ["Head of the Hunt"], bob=["Grizzly Bears"])
    put(s, "Head of the Hunt")
    victim = put(s, "Grizzly Bears", pid="p2")
    kill(s, victim)
    drive(s)
    assert zone_of(s, victim) == "p2:exile" and len(zombies(s, "Wolf")) == 1
    roundtrip(s)


# == a Class's level 3 line (716.2a): Innkeeper's Talent doubles the counters you put only once it is level 3 ==
@pytest.mark.parametrize("level, counters", [(1, 1), (2, 1), (3, 2)])
def test_innkeepers_talent_doubles_counters_from_level_3(cards, level, counters):
    s = game(cards, ["Innkeeper's Talent", "Grizzly Bears"])
    talent = put(s, "Innkeeper's Talent")
    s.state.rules.levels[s.state.rules.object_id(talent.id)] = level
    bear = put(s, "Grizzly Bears")
    feeder = permanent(s, "p1", "Feeder", "Enchantment", "{1}: Put a +1/+1 counter on target creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=feeder.id, ability=0, targets=[bear.id])
    drive(s)
    assert s.state.cards[bear.id].counters == {"+1/+1": counters}
    roundtrip(s)


def test_the_replacement_belongs_to_that_object_only(cards):
    s = game(cards, ["Grizzly Bears"])
    bear = reanimate(s, WHIP)
    assert zone_of(s, bear) == "p1:battlefield" and s.state.rules.exile_if_leaves
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "exile"})  # (exiled by hand: it is a new object if it ever returns)
    again = put(s, "Grizzly Bears", "battlefield")  # (a different object entirely: not replaced when it dies)
    assert zone_of(s, again) == "p1:battlefield"
    act(s, "p1", type="move", card_ids=[again.id], to={"player": "p1", "zone": "graveyard"})
    assert zone_of(s, again) == "p1:graveyard"


def test_a_reanimated_blightsteel_is_exiled_without_a_question(cards):
    """Review 22C, 616.1e: shuffling it in still has it leave the battlefield, so the Whip's "exile it if it would leave"
    applies after Blightsteel's replacement anyway; either order ends in exile, and nobody is asked."""
    s = game(cards, ["Blightsteel Colossus"])
    blight = put(s, "Blightsteel Colossus", "graveyard")
    t = permanent(s, "p1", "Reanimator", "Enchantment", WHIP)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0, targets=[blight.id])
    drive(s)
    assert zone_of(s, blight) == "p1:battlefield"
    library = len(s.state.zones[zone_key("p1", "library")])
    sacrifice(s)
    drive(s, lambda d: pytest.fail(f"asked: {d.prompt}") if d.resume.get("step") == "zone_replace_order" else None)
    assert zone_of(s, blight) == "p1:exile" and len(s.state.zones[zone_key("p1", "library")]) == library
    assert not any("shuffled into" in str(e) for e in s.state.log)
    roundtrip(s)


@pytest.mark.parametrize("pick, where", [("exile", "p1:exile"), ("library:shuffle", "p1:library")])
def test_rest_in_peace_destroyed_alongside_progenitus_still_offers_exile(cards, pick, where):
    """Review 22C: Rest in Peace leaving at the same time still applies to that event (614.1a, 616.1); the answer, given after
    it is gone, must still carry the card somewhere instead of leaving it on the battlefield."""
    s = game(cards, ["Progenitus"], bob=["Rest in Peace"])
    prog = put(s, "Progenitus")
    rip = put(s, "Rest in Peace", pid="p2")
    t = permanent(s, "p1", "Wrath", "Enchantment", "{1}: Destroy all nonland permanents.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0)
    drive(s, order_question(pick))
    assert zone_of(s, rip) == "p2:exile" and zone_of(s, prog) == where and not graveyard(s)
    roundtrip(s)
