"""Wave 29B: the "cast it?" choice of an engine-granted cast is face-aware (CR 2026-09-25). Real Oracle text (tests/fixtures/wave29b_cards.json,
from data/cards.sqlite and the Gatherer rulings); every scenario checks the replay and a save and a load, the pauses mid-choice too.

* 709.3, 709.3a: a split card is cast as one half and only that half is evaluated. 715.3, 715.3a: an adventurer card is cast as the creature or as
  its Adventure. 712.11b-c: a modal double-faced card is cast as either face. A land face is not cast (712.12).
* 702.85a cascade: stop at a nonland card whose mana value (the card's: a split card's halves combined 709.4b, an adventurer's creature
  715.4, a double-faced card's front face 712.8a) is less than the spell's; "you may cast that card without paying its mana cost if the resulting
  spell's mana value is less than this spell's mana value", so every half / face is checked on its own.
* 701.57a discover N: the same with "N or less". 702.62a suspend and 702.88a rebound: no limit, any half / face. 702.60a ripple: "the same name"
  (201.2a: one name in common, 709.4a: a split card has two).
* 708.4, 702.85a: a face-down spell given cascade by another effect has it; its mana value is 0 (708.2a), so it finds nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.wave9c_kit import build, card_named, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave29b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t29b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def decision(s):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    return d


def asked(s):
    """Is the "cast it?" choice of an engine-granted cast the pending decision?"""
    d = s.state.rules.decision
    return d is not None and (d.resume or {}).get("step") == "suspend_cast"


def to_question(s, limit=40):
    """Pass priority until the engine asks whether to cast the card it found."""
    for _ in range(limit):
        if asked(s):
            return decision(s)
        d = s.state.rules.decision
        if d is not None:
            raise AssertionError(f"another choice first: {d.prompt}")
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def options(s):
    return [(o.id, o.label) for o in decision(s).options]


def answer(s, prefer=None, limit=8):
    """Answer the choices of a spell being cast (its targets) until none is pending."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None or asked(s):
            return
        ids = [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[prefer] if prefer in ids else ids[: max(1, d.min_choices)])


def choose(s, option):
    d = decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def top_of_library(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def settle_all(s, limit=60):
    """Resolve everything: pass priority, answer every choice with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def cascade_from(s, source, **pool):
    """Cast ``source`` (a cascade creature) and pass priority until the engine asks about the card cascade found."""
    mana(s, **pool)
    act(s, "p1", type="cast_spell", card_id=card_named(s, source).id)
    return to_question(s)


# -- cascade ---------------------------------------------------------------------------------------------------------------------
def test_cascade_into_a_split_card_offers_each_half(cards):
    """Wear // Tear (mana value 1 + 2 = 3, 709.4b) under Bloodbraid Elf (4): either half is a spell with a lesser mana value, and the Ruling of
    2021-06-18: "you may cast either half but not both halves"."""
    s = build(cards, ["Bloodbraid Elf", "Wear // Tear"], theirs=["Maelstrom Nexus"])
    nexus = put(s, "Maelstrom Nexus", "p2")
    wear = top_of_library(s, "Wear // Tear")
    to_hand(s, "Bloodbraid Elf")
    d = cascade_from(s, "Bloodbraid Elf", R=2, G=2)
    assert d.prompt.startswith("Cascade")
    assert options(s) == [("yes", "Cast Wear"), ("yes@1", "Cast Tear"), ("no", "Put it on the bottom")]
    s = reloaded(s)  # a save and a load in the middle of the choice
    assert options(s)[1] == ("yes@1", "Cast Tear")
    with pytest.raises(ActionError):
        choose(s, "yes")  # Wear needs an artifact to destroy: that half is evaluated on its own (709.3a), and can't be cast
    assert asked(s)
    choose(s, "yes@1")
    answer(s, nexus.id)
    check(s)
    pass_until_stack_empty(s)
    assert s.state.cards[nexus.id].zone == "p2:graveyard"  # Tear: "Destroy target enchantment."
    assert s.state.cards[wear.id].zone == "p1:graveyard"
    assert s.state.rules.decision is None and not s.state.rules.free_casts and not s.state.rules.free_cast_faces
    check(s)


def test_cascade_checks_the_mana_value_of_the_half_it_casts(cards):
    """Giant Killer // Chop Down: the creature has mana value 1, the Adventure 3. Shardless Agent (3) finds it (1 is less than 3), but "the resulting
    spell must also have lesser mana value" (the 2021 rule change in the rulings): Chop Down (3) can't be cast, only the creature."""
    s = build(cards, ["Shardless Agent", "Giant Killer // Chop Down"])
    killer = top_of_library(s, "Giant Killer // Chop Down")
    to_hand(s, "Shardless Agent")
    cascade_from(s, "Shardless Agent", G=1, U=1, C=1)
    assert options(s) == [("yes", "Cast Giant Killer"), ("no", "Put it on the bottom")]
    s = reloaded(s)
    choose(s, "yes")
    pass_until_stack_empty(s)
    assert s.state.cards[killer.id].zone == "p1:battlefield" and s.state.cards[killer.id].face == 0
    check(s)


def test_cascade_offers_the_adventure_when_its_value_is_lesser(cards):
    """Bonecrusher Giant // Stomp (3 and 2) under Bloodbraid Elf (4): both; Stomp (the Adventure) is cast, and the card goes on an adventure (715.3d)."""
    s = build(cards, ["Bloodbraid Elf", "Bonecrusher Giant // Stomp"])
    giant = top_of_library(s, "Bonecrusher Giant // Stomp")
    to_hand(s, "Bloodbraid Elf")
    cascade_from(s, "Bloodbraid Elf", R=2, G=2)
    assert options(s) == [("yes", "Cast Bonecrusher Giant"), ("yes@1", "Cast Stomp"), ("no", "Put it on the bottom")]
    choose(s, "yes@1")
    answer(s, "p2")
    check(s)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38  # Stomp: 2 damage to any target
    assert s.state.cards[giant.id].zone == "p1:exile"  # (715.3d: exiled, and its controller may cast the creature from there)
    check(s)


def test_cascade_into_a_double_faced_card_casts_either_face(cards):
    """Flamescroll Celebrant // Revel in Silence (2 and 2) under Bloodbraid Elf (4): either face (712.11b), the back face being an instant."""
    s = build(cards, ["Bloodbraid Elf", "Flamescroll Celebrant // Revel in Silence"])
    celebrant = top_of_library(s, "Flamescroll Celebrant // Revel in Silence")
    to_hand(s, "Bloodbraid Elf")
    cascade_from(s, "Bloodbraid Elf", R=2, G=2)
    assert options(s) == [("yes", "Cast Flamescroll Celebrant"), ("yes@1", "Cast Revel in Silence"), ("no", "Put it on the bottom")]
    s = reloaded(s)
    choose(s, "yes@1")
    pass_until_stack_empty(s)
    assert "Revel in Silence" in json.dumps(s.view("p2")["log"])  # (the instant was cast: "Exile Revel in Silence." as it resolved)
    assert s.state.cards[celebrant.id].zone == "p1:exile" and not s.state.zones["stack"]
    assert not s.state.rules.free_casts and not s.state.rules.free_cast_faces
    check(s)


def test_cascade_into_a_double_faced_card_checks_the_back_face_value(cards):
    """Valki, God of Lies // Tibalt, Cosmic Impostor (2 and 7) under Shardless Agent (3): Tibalt (7) is not a lesser mana value, only Valki can be cast."""
    s = build(cards, ["Shardless Agent", "Valki, God of Lies // Tibalt, Cosmic Impostor"])
    valki = top_of_library(s, "Valki, God of Lies // Tibalt, Cosmic Impostor")
    to_hand(s, "Shardless Agent")
    cascade_from(s, "Shardless Agent", G=1, U=1, C=1)
    assert options(s) == [("yes", "Cast Valki, God of Lies"), ("no", "Put it on the bottom")]
    choose(s, "yes")
    pass_until_stack_empty(s)
    answer(s)
    pass_until_stack_empty(s)
    assert s.state.cards[valki.id].zone == "p1:battlefield" and s.state.cards[valki.id].face == 0
    check(s)


def test_cascade_never_offers_a_land_face(cards):
    """Valakut Awakening // Valakut Stoneforge: the front face (3) is the nonland card found; the land face is not cast (712.12), so one spell."""
    s = build(cards, ["Bloodbraid Elf", "Valakut Awakening // Valakut Stoneforge"])
    top_of_library(s, "Valakut Awakening // Valakut Stoneforge")
    to_hand(s, "Bloodbraid Elf")
    cascade_from(s, "Bloodbraid Elf", R=2, G=2)
    assert options(s) == [("yes", "Cast Valakut Awakening"), ("no", "Put it on the bottom")]
    check(s)


def test_cascade_stops_at_the_card_not_at_a_cheaper_face(cards):
    """709.4b, 712.8a: the card in exile has its halves' mana costs combined / only its front face. Imoti (5) goes past Hit // Run (3 + 5 = 8, though Hit
    alone is 3) and Jadzi // Journey to the Oracle (front 8, though the back is 4) and stops at Lightning Bolt."""
    s = build(cards, ["Imoti, Celebrant of Bounty", "Hit // Run", "Jadzi, Oracle of Arcavios // Journey to the Oracle", "Lightning Bolt"])
    bolt = top_of_library(s, "Lightning Bolt")
    top_of_library(s, "Jadzi, Oracle of Arcavios // Journey to the Oracle")
    top_of_library(s, "Hit // Run")
    to_hand(s, "Imoti, Celebrant of Bounty")
    d = cascade_from(s, "Imoti, Celebrant of Bounty", G=1, U=1, C=3)
    assert d.resume["card"] == bolt.id and options(s) == [("yes", "Cast it"), ("no", "Put it on the bottom")]
    check(s)


def test_a_declined_cascade_card_joins_the_others_in_a_random_order(cards):
    """702.85a: "put all cards exiled this way that weren't cast on the bottom of your library in a random order": the card that is not cast is
    among them, not always last (the cards it went past were put there before the question)."""
    seen = set()
    for _ in range(16):
        s = build(cards, ["Imoti, Celebrant of Bounty", "Craterhoof Behemoth", "Hit // Run", "Lightning Bolt"])
        bolt = top_of_library(s, "Lightning Bolt")
        passed = [top_of_library(s, "Craterhoof Behemoth").id, top_of_library(s, "Hit // Run").id]
        to_hand(s, "Imoti, Celebrant of Bounty")
        cascade_from(s, "Imoti, Celebrant of Bounty", G=1, U=1, C=3)
        s = reloaded(s)
        choose(s, "no")
        library = s.state.zones["p1:library"]
        assert set(library[-3:]) == {bolt.id, *passed} and not s.state.zones.get("p1:exile")
        seen.add(library[-3:].index(bolt.id))
        check(s)  # (every time: the replay and the save and load give the same order, though it was random)
    assert len(seen) > 1


def test_a_half_that_a_prohibition_stops_is_not_offered(cards):
    """601.3: Gaddock Teeg ("Noncreature spells with mana value 4 or greater can't be cast."). Discover 8 (Monstrous Vortex, for Craterhoof Behemoth)
    finds Hit // Run (3 + 5 = 8): Hit (3) can be cast, Run (5) can't, so only Hit is offered."""
    s = build(cards, ["Monstrous Vortex", "Craterhoof Behemoth", "Hit // Run", "Gaddock Teeg"])
    put(s, "Monstrous Vortex")
    put(s, "Gaddock Teeg")
    split = top_of_library(s, "Hit // Run")
    to_hand(s, "Craterhoof Behemoth")
    mana(s, G=8)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Craterhoof Behemoth").id)
    to_question(s)
    assert options(s) == [("yes", "Cast Hit"), ("no", "Put it into your hand")]
    s = reloaded(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=split.id, free=True, face=1)  # (nor can Run be sent with the cast)
    assert asked(s)
    check(s)


def test_a_card_nothing_lets_you_cast_goes_to_the_bottom_without_asking(cards):
    """Gaddock Teeg again: the Monstrous Vortex cascade found (4, an enchantment) can't be cast, so it joins the others on the bottom and nothing is
    asked (the card is public, so skipping the question tells nobody anything)."""
    s = build(cards, ["Imoti, Celebrant of Bounty", "Monstrous Vortex", "Gaddock Teeg"])
    put(s, "Gaddock Teeg")
    vortex = top_of_library(s, "Monstrous Vortex")
    to_hand(s, "Imoti, Celebrant of Bounty")
    mana(s, G=1, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Imoti, Celebrant of Bounty").id)
    s = reloaded(s)
    settle_all(s)
    assert s.state.cards[vortex.id].zone == "p1:library" and s.state.zones["p1:library"][-1] == vortex.id and not s.state.zones.get("p1:exile")
    assert "can't be cast" in json.dumps(s.view("p2")["log"]) and not s.state.rules.free_casts
    check(s)


def test_a_face_the_card_wasnt_offered_cant_be_cast_by_hand(cards):
    """cast_free takes only the face the choice named (28A review): "yes" can't be turned into the Adventure by sending face 1 with the cast."""
    s = build(cards, ["Shardless Agent", "Giant Killer // Chop Down"])
    killer = top_of_library(s, "Giant Killer // Chop Down")
    to_hand(s, "Shardless Agent")
    cascade_from(s, "Shardless Agent", G=1, U=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=killer.id, free=True, face=1)
    assert asked(s)
    check(s)


# -- discover --------------------------------------------------------------------------------------------------------------------
def discover_from(s, pool=None):
    mana(s, **(pool or {"R": 6}))
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Trumpeting Carnosaur").id)
    return to_question(s)


def test_discover_offers_the_adventure_when_it_is_five_or_less(cards):
    """Discover 5 (Trumpeting Carnosaur) finds Bonecrusher Giant // Stomp (3; Stomp 2): both, and a decline puts the card into the hand (701.57a)."""
    s = build(cards, ["Trumpeting Carnosaur", "Bonecrusher Giant // Stomp"])
    giant = top_of_library(s, "Bonecrusher Giant // Stomp")
    to_hand(s, "Trumpeting Carnosaur")
    d = discover_from(s)
    assert d.prompt.startswith("Discover 5")
    assert options(s) == [("yes", "Cast Bonecrusher Giant"), ("yes@1", "Cast Stomp"), ("no", "Put it into your hand")]
    s = reloaded(s)
    choose(s, "no")
    assert s.state.cards[giant.id].zone == "p1:hand" and not s.state.rules.free_casts and not s.state.rules.free_cast_faces
    check(s)


def test_discover_checks_the_adventure_against_the_value(cards):
    """The Gatherer ruling: discover 4 finds Galvanic Giant (4) but not Storm Reading (7); here discover 5 doesn't reach it either. The creature is cast."""
    s = build(cards, ["Trumpeting Carnosaur", "Galvanic Giant // Storm Reading"])
    giant = top_of_library(s, "Galvanic Giant // Storm Reading")
    to_hand(s, "Trumpeting Carnosaur")
    discover_from(s)
    assert options(s) == [("yes", "Cast Galvanic Giant"), ("no", "Put it into your hand")]
    choose(s, "yes")
    pass_until_stack_empty(s)
    assert s.state.cards[giant.id].zone == "p1:battlefield"
    check(s)


def test_discover_x_reaches_the_higher_face(cards):
    """Monstrous Vortex: casting Craterhoof Behemoth (8) discovers 8, which reaches Storm Reading (7) as well as Galvanic Giant (4)."""
    s = build(cards, ["Monstrous Vortex", "Craterhoof Behemoth", "Galvanic Giant // Storm Reading"])
    put(s, "Monstrous Vortex")
    giant = top_of_library(s, "Galvanic Giant // Storm Reading")
    to_hand(s, "Craterhoof Behemoth")
    mana(s, G=8)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Craterhoof Behemoth").id)
    d = to_question(s)
    assert d.prompt.startswith("Discover 8")
    assert options(s) == [("yes", "Cast Galvanic Giant"), ("yes@1", "Cast Storm Reading"), ("no", "Put it into your hand")]
    hand = len(s.state.zones["p1:hand"])
    s = reloaded(s)
    choose(s, "yes@1")
    pass_until_stack_empty(s)
    answer(s)  # Storm Reading: draw four, then discard two
    check(s)
    pass_until_stack_empty(s)
    answer(s)
    pass_until_stack_empty(s)
    assert s.state.cards[giant.id].zone == "p1:exile"  # (it went on an adventure, 715.3d)
    assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)


def test_discover_casts_either_door_of_a_room(cards):
    """709.5, 709.3: a Room is a split card with one type line, cast as one door; it enters with that door unlocked (709.5d). Underwater Tunnel //
    Slimy Aquarium (1 and 4, 5 combined) is found by discover 8; the right door is cast."""
    s = build(cards, ["Monstrous Vortex", "Craterhoof Behemoth", "Underwater Tunnel // Slimy Aquarium"])
    put(s, "Monstrous Vortex")
    room = top_of_library(s, "Underwater Tunnel // Slimy Aquarium")
    to_hand(s, "Craterhoof Behemoth")
    mana(s, G=8)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Craterhoof Behemoth").id)
    to_question(s)
    assert options(s) == [("yes", "Cast Underwater Tunnel"), ("yes@1", "Cast Slimy Aquarium"), ("no", "Put it into your hand")]
    s = reloaded(s)
    choose(s, "yes@1")
    settle_all(s)
    assert s.state.cards[room.id].zone == "p1:battlefield"
    assert s.state.rules.unlocked.get(s.state.rules.object_id(room.id)) == [2]
    check(s)


# -- suspend ---------------------------------------------------------------------------------------------------------------------
def test_suspend_lets_its_owner_cast_either_half(cards):
    """702.62a: when the last time counter is removed the owner may cast the card without paying its mana cost: Suspend exiled Bonecrusher Giant //
    Stomp with two time counters, a card with two ways to be cast (715.3), so both are offered, with no mana value limit."""
    from tests.test_rules_suspend import until

    s = build(cards, ["Suspend", "Bonecrusher Giant // Stomp"])
    giant = put(s, "Bonecrusher Giant // Stomp")
    spell = to_hand(s, "Suspend")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[giant.id])
    pass_until_stack_empty(s)
    assert s.state.cards[giant.id].zone == "p1:exile" and giant.id in s.state.rules.suspended
    act(s, "p1", type="counter", card_ids=[giant.id], kind="time", delta=-1)
    until(s, asked, limit=3000)
    assert options(s) == [("yes", "Cast Bonecrusher Giant"), ("yes@1", "Cast Stomp"), ("no", "Leave it exiled")]
    s = reloaded(s)
    choose(s, "yes@1")
    answer(s, "p2")
    check(s)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38
    assert s.state.cards[giant.id].zone == "p1:exile" and giant.id not in s.state.rules.suspended  # (715.3d: on an adventure, no longer suspended)
    check(s)


def test_suspend_offers_only_the_face_a_prohibition_leaves(cards):
    """Suspend exiled Valki, God of Lies // Tibalt, Cosmic Impostor (a creature, a planeswalker). Steel Golem ("You can't cast creature spells."):
    Valki can't be cast, Tibalt can, so the choice is Tibalt or nothing (712.11b-c: only the face that would be up is evaluated)."""
    from tests.test_rules_suspend import until

    s = build(cards, ["Suspend", "Valki, God of Lies // Tibalt, Cosmic Impostor", "Steel Golem"])
    put(s, "Steel Golem")
    valki = put(s, "Valki, God of Lies // Tibalt, Cosmic Impostor")
    spell = to_hand(s, "Suspend")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[valki.id])
    pass_until_stack_empty(s)
    act(s, "p1", type="counter", card_ids=[valki.id], kind="time", delta=-1)
    until(s, asked, limit=3000)
    assert options(s) == [("yes@1", "Cast Tibalt, Cosmic Impostor"), ("no", "Leave it exiled")]
    s = reloaded(s)
    choose(s, "yes@1")
    settle_all(s)
    assert s.state.cards[valki.id].zone == "p1:battlefield" and s.state.cards[valki.id].face == 1
    check(s)


def suspended_florahedron(cards, counters=1, extra=()):
    """Suspend (the instant) on Tangled Florahedron // Tangled Vale (a creature // a land): exiled with two time counters, ``counters`` left."""
    s = build(cards, ["Suspend", "Tangled Florahedron // Tangled Vale", *extra])
    both = put(s, "Tangled Florahedron // Tangled Vale")
    spell = to_hand(s, "Suspend")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[both.id])
    pass_until_stack_empty(s)
    assert s.state.cards[both.id].zone == "p1:exile" and both.id in s.state.rules.suspended
    act(s, "p1", type="counter", card_ids=[both.id], kind="time", delta=counters - 2)
    return s, both


def test_a_suspended_modal_card_may_be_played_as_its_land_face(cards):
    """702.62a: when the last time counter is removed the owner "may play it without paying its mana cost": a land face is played (712.12), on the
    owner's own turn with a land play left (305.2a-b, 305.3), and enters with that face up, tapped as the card says."""
    from tests.test_rules_suspend import until

    s, both = suspended_florahedron(cards)
    until(s, asked, limit=3000)
    assert options(s) == [("yes", "Cast Tangled Florahedron"), ("yes@1", "Play Tangled Vale"), ("no", "Leave it exiled")]
    s = reloaded(s)
    choose(s, "yes@1")
    settle_all(s)
    card = s.state.cards[both.id]
    assert card.zone == "p1:battlefield" and card.face == 1 and card.tapped
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 1 and both.id not in s.state.rules.suspended
    assert not s.state.rules.free_casts and s.state.rules.decision is None
    check(s)


def test_a_suspended_land_face_asks_for_its_entering_choice(cards):
    """Kang Prime suspends the card at the top of the library: Agadeem's Awakening // Agadeem, the Undercrypt. Playing the land face asks the usual
    "As this land enters, you may pay 3 life" first (614.12a), the ability going on once it is answered; the choice survives a save and a load."""
    from tests.test_rules_suspend import until

    s = build(cards, ["Kang Prime", "Agadeem's Awakening // Agadeem, the Undercrypt"])
    both = top_of_library(s, "Agadeem's Awakening // Agadeem, the Undercrypt")
    to_hand(s, "Kang Prime")
    mana(s, U=1, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kang Prime").id)
    settle_all(s)
    assert s.state.cards[both.id].zone == "p1:exile" and s.state.cards[both.id].counters == {"time": 2} and both.id in s.state.rules.suspended
    act(s, "p1", type="counter", card_ids=[both.id], kind="time", delta=-1)
    until(s, asked, limit=3000)
    assert options(s) == [("yes", "Cast Agadeem's Awakening"), ("yes@1", "Play Agadeem, the Undercrypt"), ("no", "Leave it exiled")]
    life = s.state.players["p1"].life
    choose(s, "yes@1")
    d = decision(s)
    assert "life" in d.prompt and s.state.cards[both.id].zone == "p1:exile"  # 614.12a: asked before it enters
    s = reloaded(s)
    choose(s, [o.id for o in decision(s).options if o.id == "pay"][0])
    settle_all(s)
    card = s.state.cards[both.id]
    assert card.zone == "p1:battlefield" and card.face == 1 and not card.tapped and s.state.players["p1"].life == life - 3
    assert s.state.rules.decision is None and both.id not in s.state.rules.suspended and not s.state.rules.free_casts
    check(s)


def test_a_suspended_land_face_is_not_offered_without_a_land_play(cards):
    """305.2b: time travel (Wibbly-wobbly, Timey-wimey) takes the last counter off in the owner's main phase after a land was played: no land play is
    left, so the land face can't be played, only the creature face cast."""
    s, both = suspended_florahedron(cards, counters=1, extra=["Wibbly-wobbly, Timey-wimey"])
    forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    to_hand(s, "Wibbly-wobbly, Timey-wimey")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Wibbly-wobbly, Timey-wimey").id)
    for _ in range(12):
        if asked(s):
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == both.id])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["remove"])
    assert options(s) == [("yes", "Cast Tangled Florahedron"), ("no", "Leave it exiled")]
    check(s)


def test_a_suspended_modal_card_is_cast_as_its_creature_face(cards):
    from tests.test_rules_suspend import until

    s, both = suspended_florahedron(cards)
    until(s, asked, limit=3000)
    choose(s, "yes")
    settle_all(s)
    card = s.state.cards[both.id]
    assert card.zone == "p1:battlefield" and card.face == 0 and s.state.rules.lands_this_turn("p1", s.state.turn.number) == 0
    check(s)


# -- ripple ----------------------------------------------------------------------------------------------------------------------
def test_ripple_casts_either_half_of_a_revealed_split_card(cards):
    """Thrumming Stone gives Hit (half of Hit // Run) ripple 4. The revealed Hit // Run has the same name (201.2a, 709.4a: a split card has two
    names, and one in common is enough) and either half may be cast (Gatherer ruling 2006-07-15)."""
    s = build(cards, ["Thrumming Stone", "Hit // Run", "Hit // Run"])
    put(s, "Thrumming Stone")
    first, second = [c for c in s.state.cards.values() if c.name == "Hit // Run" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, B=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])
    for _ in range(40):
        if asked(s):
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:  # (reveal the top four: yes)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert asked(s)
    assert decision(s).prompt.startswith("Ripple")
    assert options(s) == [("yes", "Cast Hit"), ("yes@1", "Cast Run"), ("no", "Put it on the bottom")]
    s = reloaded(s)
    choose(s, "yes@1")
    check(s)
    settle_all(s)  # (Run has ripple too: it reveals the top four again and finds no other copy)
    assert s.state.cards[second.id].zone == "p1:graveyard" and s.state.cards[first.id].zone == "p1:graveyard"
    check(s)


# -- face-down spells ------------------------------------------------------------------------------------------------------------
def library_ids(s, pid="p1"):  # noqa: D103
    return list(s.state.zones[f"{pid}:library"])


def test_a_face_down_creature_spell_with_granted_cascade_cascades(cards):
    """Sloppity Bilepiper: "The next creature spell you cast this turn has cascade." A face-down spell has no abilities of its own (708.2), but an
    effect can give it one (613.1f), and it has it as it is cast (601.2a): cascade triggers (702.85a). Its mana value is 0 (708.2a), so no card
    has a lesser one: the whole library is exiled, nothing is cast, and it all goes back on the bottom in a random order."""
    s = build(cards, ["Sloppity Bilepiper", "Willbender", "Grizzly Bears"])
    bilepiper = put(s, "Sloppity Bilepiper")
    s.state.rules.controlled_since[bilepiper.id].turn = 0
    bears = put(s, "Grizzly Bears")
    willbender = to_hand(s, "Willbender")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bilepiper.id, ability=0)
    answer(s, bears.id)
    pass_until_stack_empty(s)
    assert len(s.state.rules.next_spell_grants) == 1
    s = reloaded(s)  # (a save and a load with the grant waiting for the next creature spell)
    willbender = card_named(s, "Willbender")
    before = library_ids(s)
    act(s, "p1", type="set_prefs", hold_priority=True)  # (so the trigger waits on the stack)
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=willbender.id, face_down=True)
    assert not s.state.rules.next_spell_grants  # (used up by the cast)
    assert len(s.state.rules.stack) == 1 and len(s.state.zones["stack"]) == 2  # the face-down spell, and the cascade ability it was given
    assert s.state.rules.stack[next(iter(s.state.rules.stack))].source_card == willbender.id
    seen = s.view("p2")
    assert "Willbender" not in json.dumps(seen) and "name" not in seen["cards"][willbender.id]  # 708.5: only its controller may look at it
    s = reloaded(s)
    settle_all(s)
    log = json.dumps(s.view("p1")["log"])
    assert "Cascade found nothing" in log  # 702.85a: the cascade ability triggered and resolved, finding no card with a mana value less than 0
    assert s.state.rules.decision is None
    assert sorted(library_ids(s)) == sorted(before) and not s.state.zones.get("p1:exile")  # (all of it came back, 702.85a)
    assert library_ids(s) != before  # (in a random order)
    assert s.state.cards[willbender.id].zone == "p1:battlefield" and s.state.cards[willbender.id].face_down
    assert "Willbender" not in json.dumps(s.view("p2"))  # 708.5: only its controller may look at it; neither the trigger nor the log name it
    check(s)


def test_a_face_down_spell_given_ripple_reveals_but_matches_no_name(cards):
    """Thrumming Stone: "Spells you cast have ripple 4." A face-down spell has it as it is cast, but has no name (708.2a) and an object with no name
    has the same name as no other object (201.2a): the four cards revealed are put on the bottom and none is cast."""
    s = build(cards, ["Thrumming Stone", "Willbender", "Willbender"])
    put(s, "Thrumming Stone")
    first, second = [c for c in s.state.cards.values() if c.name == "Willbender" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "library"}, position="top")
    top4 = library_ids(s)[:4]
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=first.id, face_down=True)
    s = reloaded(s)
    settle_all(s)
    assert set(library_ids(s)[-4:]) == set(top4) and second.id in top4  # (the other Willbender was revealed, and is not "the same name")
    assert s.state.cards[second.id].zone == "p1:library" and s.state.cards[first.id].zone == "p1:battlefield"
    assert "Willbender" not in json.dumps(s.view("p2")["cards"][first.id])
    check(s)


def test_storm_given_to_a_face_down_spell_is_refused(cards):
    """No printed card gives a creature spell storm ("the next instant or sorcery spell", "instant and sorcery spells you cast"); one that did
    would copy a face-down spell, whose copies are face-up 2/2 creature spells (707.2), which isn't automated: the cast is refused, not read
    as if the grant weren't there. (The grant is put in the table directly: there is no card to give it.)"""
    from app.game.rules_state import NextSpellGrant

    s = build(cards, ["Willbender"])
    willbender = to_hand(s, "Willbender")
    s.state.rules.next_spell_grants.append(NextSpellGrant(id="g1", player="p1", keyword="storm", turn=s.state.turn.number, label="Test"))
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=willbender.id, face_down=True)
    assert s.state.cards[willbender.id].zone == "p1:hand" and len(s.state.rules.next_spell_grants) == 1


def test_a_static_cascade_works_on_a_face_down_spell_too(cards):
    """Maelstrom Nexus: "The first spell you cast each turn has cascade." A disguised creature cast face down is that spell."""
    s = build(cards, ["Maelstrom Nexus", "Pyrotechnic Performer"])
    put(s, "Maelstrom Nexus")
    performer = to_hand(s, "Pyrotechnic Performer")
    before = library_ids(s)
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=performer.id, face_down=True)
    settle_all(s)
    assert "Cascade found nothing" in json.dumps(s.view("p1")["log"])
    assert sorted(library_ids(s)) == sorted(before) and library_ids(s) != before
    assert s.state.cards[performer.id].zone == "p1:battlefield" and s.state.cards[performer.id].face_down
    assert "Pyrotechnic Performer" not in json.dumps(s.view("p2"))
    check(s)
