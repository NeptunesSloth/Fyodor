"""Wave 37A: "for as long as" durations on one-shot effects and play / cast permissions (CR 2026-09-25), real Oracle text
(tests/fixtures/wave37a_durations_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 611.2b: "For as long as ~ remains on the battlefield, gain control of that permanent, it loses all abilities, and it can't attack or block"
  (Opportunistic Dragon), "For as long as this artifact remains tapped, another target permanent loses all abilities and can't attack or block"
  (Immovable Rod): one duration over a list of effects; each ends the moment the condition stops being true, and a duration that is already over
  as the effects would begin means they do nothing at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave37a_durations_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w37a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Opportunistic Dragon", "Immovable Rod", "Cunning Rhetoric", "Masked Bandits", "Rakish Revelers", "Spara's Adjudicators", "Shattered Seraph",
        "Glamorous Outlaw", "Emrakul, the Exigent Doom"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def of(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def now(s, c):
    return s.state.cards[c.id]


def move(s, c, zone, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})


def kill(s, c):
    """Lethal damage: the creature dies (704.5g) as the engine next looks at the table."""
    act(s, "p1", type="set_damage", card_ids=[c.id], value=99)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)


# -- 611.2b: one duration over a list of effects ---------------------------------------------------------------------------------
def dragon_table(cards):
    s = build(cards, mine=("Opportunistic Dragon",), theirs=("Monastery Swiftspear",))
    swiftspear = put(s, "Monastery Swiftspear", "p2")
    dragon = to_hand(s, "Opportunistic Dragon")
    mana(s, R=2, C=2)
    return s, dragon, swiftspear


def test_opportunistic_dragon_takes_the_creature_and_all_its_abilities_only_while_it_stays(cards):
    s, dragon, swiftspear = dragon_table(cards)
    act(s, "p1", type="cast_spell", card_id=dragon.id)
    settle(s)
    got = now(s, swiftspear)
    assert got.controller == "p1" and not of(s, swiftspear).keywords and "cant_attack_or_block" in of(s, swiftspear).imposed
    check(s)
    kill(s, dragon)  # (611.2b: it ends the moment the Dragon is gone — control, lost abilities and the restriction together)
    back = now(s, swiftspear)
    assert back.controller == "p2" and "haste" in of(s, swiftspear).keywords and "cant_attack_or_block" not in of(s, swiftspear).imposed
    check(s)


def test_opportunistic_dragon_does_nothing_when_it_left_in_response_to_its_trigger(cards):
    """611.2b: "for as long as this creature remains on the battlefield" is already false as the trigger resolves: none of the three effects begins."""
    s, dragon, swiftspear = dragon_table(cards)
    act(s, "p1", type="cast_spell", card_id=dragon.id)
    d = s.state.rules.decision  # (the Dragon resolved; its enters trigger asks for its target before it goes on the stack)
    assert d is not None
    move(s, dragon, "hand")  # (it is gone before the trigger resolves)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == swiftspear.id])
    settle(s)
    assert now(s, swiftspear).controller == "p2" and "haste" in of(s, swiftspear).keywords
    check(s)


# -- 113.6m, 400.7j, 611.2a: "{2}, Exile this card from your hand: Target land gains "{T}: Add …" until this card is cast from exile. You may cast
# this card for as long as it remains exiled." ---------------------------------------------------------------------------------------
GAINED = "{T}: Add {R}, {G}, or {W}."


def revelers_table(cards, hold=False):
    s = build(cards, mine=("Rakish Revelers",))
    forest = put(s, "Forest")
    revelers = to_hand(s, "Rakish Revelers")
    mana(s, C=2)
    if hold:
        for pid in s.state.players:
            act(s, pid, type="set_prefs", response="on")
    ability = next(ab.index for ab in of(s, revelers).abilities if ab.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=revelers.id, ability=ability, targets=[forest.id])
    return s, revelers, forest


def has_gift(s, land):
    return any(ab.text == GAINED for ab in of(s, land).abilities)


def test_rakish_revelers_land_gets_the_mana_ability_until_the_card_is_cast_from_exile(cards):
    s, revelers, forest = revelers_table(cards)
    settle(s)
    assert now(s, revelers).zone == "p1:exile" and has_gift(s, forest)
    assert not can_cast(s, "p2", revelers)
    mana(s, C=2, G=1, W=1)  # (the red mana for the spell is the one the land makes: 601.2g, a mana ability while paying)
    assert can_cast(s, "p1", revelers)
    check(s)
    act(s, "p1", type="cast_spell", card_id=revelers.id)
    settle(s)
    assert now(s, revelers).zone == "p1:battlefield" and not has_gift(s, forest)  # (611.2a: it was cast from exile; the land's ability ended)
    check(s)


def test_rakish_revelers_land_keeps_the_ability_when_the_card_leaves_exile_uncast_and_the_permission_is_gone(cards):
    """The ruling: if Rakish Revelers is removed from exile without being cast, the land keeps the ability. A card that left is a new object (400.7):
    it can't be cast from exile again with the old permission."""
    s, revelers, forest = revelers_table(cards)
    settle(s)
    act(s, "p1", type="move", card_ids=[revelers.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[revelers.id], to={"player": "p1", "zone": "exile"})
    mana(s, C=2, R=1, G=1, W=1)
    assert has_gift(s, forest) and not can_cast(s, "p1", revelers)
    check(s)


def test_rakish_revelers_gone_in_response_gives_the_land_the_ability_for_good_and_no_permission(cards):
    s, revelers, forest = revelers_table(cards, hold=True)
    assert now(s, revelers).zone == "p1:exile" and not has_gift(s, forest)
    act(s, "p1", type="move", card_ids=[revelers.id], to={"player": "p1", "zone": "graveyard"})  # (in response: the card the cost exiled is gone)
    settle(s)
    assert has_gift(s, forest) and now(s, revelers).zone == "p1:graveyard"
    mana(s, C=2, R=1, G=1, W=1)
    assert not can_cast(s, "p1", revelers)  # (nothing to cast from exile: the permission is for the object the cost exiled, 400.7j)
    check(s)


# -- 508.3e, 611.2b, 400.7: "You may play that card for as long as it remains exiled" -------------------------------------------
def rhetoric_table(cards):
    """Bob's Grizzly Bears attacks Alice (Cunning Rhetoric): the Lightning Bolt on top of Bob's library is exiled."""
    s = build(cards, mine=("Cunning Rhetoric",), theirs=("Grizzly Bears", "Lightning Bolt"))
    put(s, "Cunning Rhetoric")
    bears = put(s, "Grizzly Bears", "p2")
    for _ in range(80):  # (Alice's turn passes with no attackers; Bob is asked whom he attacks with)
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers" and d.player == "p2":
            break
        elif d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    bolt = card_named(s, "Lightning Bolt", "p2")
    act(s, "p2", type="move", card_ids=[bolt.id], to={"player": "p2", "zone": "library"}, position="top")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    settle(s)
    return s, bolt


def can_cast(s, pid, c):
    from app.rules.casting import castable

    return castable(s.state, pid, s.state.cards[c.id], s.cards, check_priority=False)


def test_cunning_rhetoric_lets_alice_play_the_exiled_card_with_any_mana_until_it_leaves_exile(cards):
    s, bolt = rhetoric_table(cards)
    assert now(s, bolt).zone == "p2:exile"
    mana(s, C=1)  # (the Bolt costs {R}: "you may spend mana as though it were mana of any color", 609.4b)
    assert can_cast(s, "p1", bolt) and not can_cast(s, "p2", bolt)
    check(s)
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p2", "zone": "graveyard"})  # (400.7: it leaves exile ...)
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p2", "zone": "exile"})  # ... and comes back: a new object
    assert now(s, bolt).zone == "p2:exile" and not can_cast(s, "p1", bolt)
    check(s)


def rod_table(cards, hold=False):
    s = build(cards, mine=("Immovable Rod",), theirs=("Monastery Swiftspear",))
    swiftspear, rod = put(s, "Monastery Swiftspear", "p2"), put(s, "Immovable Rod")
    mana(s, W=1, C=3)
    if hold:  # (everyone stops at each object on the stack: a response can be made)
        for pid in s.state.players:
            act(s, pid, type="set_prefs", response="on")
    act(s, "p1", type="activate_ability", card_id=rod.id, ability=2, targets=[swiftspear.id])
    return s, rod, swiftspear


def test_immovable_rod_holds_the_permanent_down_for_as_long_as_it_remains_tapped(cards):
    """611.2b: the Rod is tapped to pay for the ability; the target loses all abilities and can't attack or block until the Rod untaps."""
    s, rod, swiftspear = rod_table(cards)
    settle(s)
    assert now(s, rod).tapped and not of(s, swiftspear).keywords and "cant_attack_or_block" in of(s, swiftspear).imposed
    check(s)
    act(s, "p1", type="tap", card_ids=[rod.id], tapped=False)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert "haste" in of(s, swiftspear).keywords and "cant_attack_or_block" not in of(s, swiftspear).imposed
    check(s)


def test_immovable_rod_does_nothing_when_it_untapped_in_response(cards):
    """611.2b: "for as long as this artifact remains tapped" is already false as the ability resolves: the target keeps everything."""
    s, rod, swiftspear = rod_table(cards, hold=True)
    act(s, "p1", type="tap", card_ids=[rod.id], tapped=False)  # (in response, the Rod is untapped)
    settle(s)
    assert "haste" in of(s, swiftspear).keywords and "cant_attack_or_block" not in of(s, swiftspear).imposed
    check(s)
