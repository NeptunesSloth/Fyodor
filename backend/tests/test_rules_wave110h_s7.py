"""Wave 110H session 7: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* Unleash the Inferno: the excess damage (120.10) triggers a destroy whose target (chosen when the trigger goes on the stack, 603.3d) has mana value at most that excess.
* Revival Experiment: up to one graveyard card per permanent type, a matching of cards to types (205.2a); 3 life each; the spell is exiled.
* Memory Vessel: both players exile seven; until the activator's next turn each may play their own exiled cards and none may play cards from hand (305.1, 601.3).
* Sword of the Ages: the sacrificed artifact and creatures pay the cost (601.2h), X is their total power, and what is still in the graveyard afterwards is exiled.
* Shifting Shadow: the granted upkeep trigger attaches the granting Aura to the creature it put onto the battlefield (607.1a, 303.4f).
* Stitcher Geralf: each player mills three (701.17); up to two creature cards among those milled are exiled; the Zombie is as big as their total power (608.2c, 107.1b).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave110h_s5 import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

EXTRA = [
    real("Stitcher Geralf", "{2}{U}", 3, "Legendary Creature — Human Wizard",
         "{2}{U}, {T}: Each player mills three cards. Exile up to two creature cards put into graveyards this way. Create an X/X blue Zombie creature token, "
         "where X is the total power of the cards exiled this way.", ("3", "4"), "U"),
    real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Unleash the Inferno", "{3}{R}", 4, "Instant",
         "Unleash the Inferno deals 7 damage to target creature or planeswalker. When it deals excess damage this way, destroy target artifact or enchantment an opponent "
         "controls with mana value less than or equal to that amount of excess damage.", None, "R"),
    real("Gilded Lotus", "{5}", 5, "Artifact", "{T}: Add three mana of any one color.", None, ""),
    real("Colossus", "{7}", 7, "Artifact Creature \u2014 Golem", "", ("7", "7"), ""),
    real("Revival Experiment", "{3}{B}{B}", 5, "Sorcery",
         "For each permanent type, return up to one card of that type from your graveyard to the battlefield. You lose 3 life for each card returned this way. "
         "Exile Revival Experiment.", None, "B"),
    real("Wayfarer's Bauble", "{1}", 1, "Artifact Creature \u2014 Golem", "", ("1", "1"), ""),
    real("Memory Vessel", "{4}", 4, "Artifact",
         "{T}, Exile this artifact: Each player exiles the top seven cards of their library. Until your next turn, players may play cards they exiled this way, and they can't "
         "play cards from their hand. Activate only as a sorcery.", None, ""),
    real("Sword of the Ages", "{4}", 4, "Artifact",
         "This artifact enters tapped.\n{T}, Sacrifice this artifact and any number of creatures you control: This artifact deals X damage to any target, where X is "
         "the total power of the creatures sacrificed this way, then exile this artifact and those creature cards.", None, ""),
    real("Shifting Shadow", "{1}{B}{B}", 3, "Enchantment \u2014 Aura",
         "Enchant creature\nEnchanted creature has haste and \"At the beginning of your upkeep, destroy this creature. Reveal cards from the top of your library until you "
         "reveal a creature card. Put that card onto the battlefield and attach Shifting Shadow to it, then put all other cards revealed this way on the bottom of your "
         "library in a random order.\"", None, "B"),
    real("Sol Ring", "{1}", 1, "Artifact", "{T}: Add {C}{C}.", None, ""),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def top(s, name, pid):
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "library"}, position="top")


def geralf(cards, mine, theirs):
    s = build(cards, ["Stitcher Geralf", "Hill Giant", "Grizzly Bears", "Runeclaw Bear", "Sol Ring"], ["Hill Giant", "Grizzly Bears"])
    g = put(s, "Stitcher Geralf")
    to_phase(s, "main1", 3)  # (summoning sickness is over on the controller's next turn)
    for n in reversed(mine):
        top(s, n, "p1")
    for n in reversed(theirs):
        top(s, n, "p2")
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=g.id, ability=0)
    return s


def zombies(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Zombie"]


def test_geralf_exiles_two_milled_creatures_total_power(cards):
    """Pick one of each side: 3 + 2 power, a 5/5 Zombie; the other milled creature stays in its graveyard, the noncreature is not offered."""
    s = geralf(cards, ["Hill Giant", "Sol Ring", "Runeclaw Bear"], ["Grizzly Bears", "Hill Giant", "Island"])
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 4 and d.max_choices == 2 and d.min_choices == 0
    mine = card_named(s, "Hill Giant", "p1")
    theirs = card_named(s, "Grizzly Bears", "p2")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[mine.id, theirs.id])
    answer(s)
    assert s.state.cards[mine.id].zone == "p1:exile" and s.state.cards[theirs.id].zone == "p2:exile"
    (z,) = zombies(s)
    assert s.state.cards[z.id].zone == "p1:battlefield"
    from app.rules.plan import Plan
    assert Plan(s.state, "p1", s.cards, None).ch(z).pt == (5, 5)
    assert card_named(s, "Runeclaw Bear", "p1").zone == "p1:graveyard"
    check(s)


def test_geralf_none_exiled_makes_a_dying_zombie(cards):
    """Choosing none: X is 0 (107.1b), the 0/0 Zombie is created and put into the graveyard by state-based actions; the milled cards stay."""
    s = geralf(cards, ["Hill Giant", "Grizzly Bears", "Sol Ring"], ["Island", "Island", "Island"])
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert not zombies(s) or all(s.state.cards[z.id].zone != "p1:battlefield" for z in zombies(s))
    assert card_named(s, "Hill Giant", "p1").zone == "p1:graveyard"
    check(s)


def unleash(cards, victim):
    s = build(cards, ["Unleash the Inferno"], ["Sol Ring", "Gilded Lotus", victim])
    for n in ("Sol Ring", "Gilded Lotus", victim):
        put(s, n, "p2")
    mana(s, R=1, C=3)
    c = to_hand(s, "Unleash the Inferno")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[card_named(s, victim, "p2").id])
    return s


def test_unleash_excess_bounds_the_destroy_target(cards):
    """Hill Giant (toughness 3): 4 excess. Only Sol Ring (1) is a legal target of the trigger, Gilded Lotus (5) is not, so Sol Ring is destroyed (701.8) and the Lotus stays."""
    s = unleash(cards, "Hill Giant")
    answer(s)
    assert card_named(s, "Hill Giant", "p2").zone == "p2:graveyard" and card_named(s, "Sol Ring", "p2").zone == "p2:graveyard"
    assert card_named(s, "Gilded Lotus", "p2").zone == "p2:battlefield"
    check(s)


def test_unleash_no_excess_no_trigger(cards):
    """A 7/7 takes exactly lethal: no excess damage (120.10), nothing triggers, the artifacts stay."""
    s = unleash(cards, "Colossus")
    answer(s)
    assert card_named(s, "Colossus", "p2").zone == "p2:graveyard"
    assert card_named(s, "Sol Ring", "p2").zone == "p2:battlefield" and card_named(s, "Gilded Lotus", "p2").zone == "p2:battlefield"
    check(s)


def revival(cards):
    s = build(cards, ["Revival Experiment", "Grizzly Bears", "Runeclaw Bear", "Sol Ring", "Wayfarer's Bauble"])
    for n in ("Grizzly Bears", "Runeclaw Bear", "Sol Ring", "Wayfarer's Bauble"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})
    mana(s, B=2, C=3)
    c = to_hand(s, "Revival Experiment")
    act(s, "p1", type="cast_spell", card_id=c.id)
    return s, c


def test_revival_experiment_one_card_per_type(cards):
    """Bears (creature) + Sol Ring (artifact): both return, 6 life lost, the spell is exiled; the second Bear and the Bauble stay."""
    s, c = revival(cards)
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 4
    bears, ring = card_named(s, "Grizzly Bears"), card_named(s, "Sol Ring")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id, ring.id])
    answer(s)
    assert s.state.cards[bears.id].zone == s.state.cards[ring.id].zone == "p1:battlefield"
    assert card_named(s, "Runeclaw Bear").zone == "p1:graveyard" and s.state.cards[c.id].zone == "p1:exile"
    assert life(s) == 34
    check(s)


def test_revival_experiment_two_creatures_refused(cards):
    """Two creature cards are one type twice: the answer is refused (608.2d)."""
    from app.game.errors import ActionError

    s, c = revival(cards)
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[card_named(s, "Grizzly Bears").id, card_named(s, "Runeclaw Bear").id])


def test_revival_experiment_artifact_creature_is_one_type(cards):
    """An artifact creature stands for one type only: Bauble + Bears + Sol Ring has no matching (the Bauble would need the creature or artifact slot Bears or
    Sol Ring already fills) and is refused; Bauble + Sol Ring is fine."""
    from app.game.errors import ActionError

    s, c = revival(cards)
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[card_named(s, n).id for n in ("Wayfarer's Bauble", "Grizzly Bears", "Sol Ring")])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[card_named(s, n).id for n in ("Wayfarer's Bauble", "Sol Ring")])
    answer(s)
    assert life(s) == 34 and card_named(s, "Wayfarer's Bauble").zone == "p1:battlefield"
    check(s)


def test_memory_vessel_hand_locked_exile_playable_until_your_next_turn(cards):
    """Until Alice's next turn: Bob plays his own exiled Island but not an Island from hand, Alice can't cast from hand; once her turn begins both are normal again."""
    from app.game.errors import ActionError

    s = build(cards, ["Memory Vessel", "Grizzly Bears", "Sol Ring"], ["Hill Giant"])
    vessel = put(s, "Memory Vessel")
    to_phase(s, "main1", 3)
    bears = to_hand(s, "Grizzly Bears")
    top(s, "Sol Ring", "p1")
    isl_hand = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[isl_hand.id], to={"zone": "hand"})
    act(s, "p1", type="activate_ability", card_id=vessel.id, ability=0)
    answer(s)
    assert len([c for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:exile"]) == 7
    ring = card_named(s, "Sol Ring")
    assert ring.zone == "p1:exile"
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)
    act(s, "p1", type="cast_spell", card_id=ring.id)  # her own exiled card
    answer(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    to_phase(s, "main1", 4)
    exiled = next(c for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:exile" and c.name == "Island")
    with pytest.raises(ActionError):
        act(s, "p2", type="play_land", card_id=isl_hand.id)
    act(s, "p2", type="play_land", card_id=exiled.id)
    assert s.state.cards[exiled.id].zone == "p2:battlefield"
    check(s)
    to_phase(s, "main1", 5)
    rest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:exile" and c.name == "Forest")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=rest.id)  # the permission ended as her turn began
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)  # the hand lock ended too
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"


@pytest.mark.parametrize("chosen,damage", [(("Hill Giant", "Grizzly Bears"), 5), ((), 0), (("Hill Giant",), 3)])
def test_sword_of_the_ages_exiles_what_it_sacrificed(cards, chosen, damage):
    """X is the total power of the creatures sacrificed (0 for none); the Sword and those creature cards end in exile, an unsacrificed creature stays."""
    s = build(cards, ["Sword of the Ages", "Hill Giant", "Grizzly Bears"])
    sword = put(s, "Sword of the Ages")
    for n in ("Hill Giant", "Grizzly Bears"):
        put(s, n)
    to_phase(s, "main1", 3)
    act(s, "p1", type="activate_ability", card_id=sword.id, ability=1, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[card_named(s, n).id for n in chosen])
    answer(s)
    assert life(s, "p2") == 40 - damage
    assert s.state.cards[sword.id].zone == "p1:exile"
    for n in ("Hill Giant", "Grizzly Bears"):
        assert card_named(s, n).zone == ("p1:exile" if n in chosen else "p1:battlefield")
    check(s)


def test_sword_of_the_ages_leaves_a_same_name_card_already_in_the_graveyard(cards):
    """608.2h, 400.7: only the objects the sacrifice made are exiled; a same-name card that was already in the graveyard stays."""
    s = build(cards, ["Sword of the Ages", "Hill Giant", "Hill Giant"])
    sword = put(s, "Sword of the Ages")
    giants = [c for c in s.state.cards.values() if c.name == "Hill Giant" and c.owner == "p1"][:2]
    act(s, "p1", type="move", card_ids=[giants[0].id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[giants[1].id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "main1", 3)
    act(s, "p1", type="activate_ability", card_id=sword.id, ability=1, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giants[0].id])
    answer(s)
    assert life(s, "p2") == 37
    assert s.state.cards[giants[0].id].zone == "p1:exile" and s.state.cards[sword.id].zone == "p1:exile"
    assert s.state.cards[giants[1].id].zone == "p1:graveyard"
    check(s)


def test_shifting_shadow_moves_to_the_next_creature(cards):
    """Upkeep: the host dies, the first creature card revealed (the Giant, under a Forest) enters and the Aura is attached to it (not in the graveyard); the Forest goes under."""
    s = build(cards, ["Shifting Shadow", "Grizzly Bears", "Hill Giant"], forests=30, islands=30)
    bears = put(s, "Grizzly Bears")
    mana(s, B=3)
    shadow = to_hand(s, "Shifting Shadow")
    act(s, "p1", type="cast_spell", card_id=shadow.id, targets=[bears.id])
    answer(s)
    assert s.state.cards[shadow.id].attached_to == bears.id
    giant = card_named(s, "Hill Giant")
    top(s, "Hill Giant", "p1")
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "library"}, position="top")
    to_phase(s, "main1", 3)
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert s.state.cards[giant.id].zone == "p1:battlefield"
    assert s.state.cards[shadow.id].zone == "p1:battlefield" and s.state.cards[shadow.id].attached_to == giant.id
    assert s.state.cards[forest.id].zone == "p1:library" and forest.id not in s.state.zones["p1:library"][:1]  # (under the rest: 701.20e, bottom)
    check(s)
