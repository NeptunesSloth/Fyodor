"""Wave 100C: instant and sorcery sentences the grammar didn't read (app/rules/static_spell100c.py), real Oracle text
(tests/fixtures/wave100c_static_spells_cards.json, from data/cards.sqlite; CR 2026-09-25). Every scenario checks the replay and a
save and a load (wave9c_kit.check).

* One instruction naming several groups ("all blocking creatures and all blocked creatures", "target creature and all Auras attached to
  it") is carried out at once: one destroy / move of every object (608.2c, 701.8a, 610.3).
* "Owns" is the owner (108.3), whoever controls it; "you own or control" either.
* "Loses all counters": every kind of counter the player has (122.1, 122.8), never speed (a value, 702.179).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, life, mana
from tests.wave100c_kit import cast, move, named, one, open_repo, put_on, settle, to_phase, zone

PROMOTED = ["Early Harvest", "Invincible Hymn", "Fight to the Death", "End Hostilities", "Soulquake", "Ultimate Nullification",
            "Shadows' Verdict", "Iridian Maelstrom", "Hurkyl's Recall", "Hubris", "Word of Undoing", "Silence the Believers",
            "Telim'Tor's Edict", "Thraben Exorcism", "Blazing Hope", "Final Act"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- sweepers naming several groups: one instruction (608.2c) -----------------------------------------------------------------------
def test_fight_to_the_death_destroys_blockers_and_blocked_attackers_but_not_the_unblocked_one(cards):
    """Fight to the Death: "Destroy all blocking creatures and all blocked creatures." An unblocked attacker and a creature out of combat stay."""
    s = build(cards, ["Fight to the Death", "Grizzly Bears", "Llanowar Elves", "Benalish Hero"], ["Grizzly Bears"])
    blocked, unblocked, home = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves"), put_on(s, "Benalish Hero")
    blocker = put_on(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_stops", own=["declare_blockers"], others=[], smart_pass=False)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": blocked.id, "target": "p2"}, {"card_id": unblocked.id, "target": "p2"}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": blocked.id}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(10):
        if s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1" and s.state.rules.decision is None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    cast(s, "Fight to the Death", R=1, W=1)
    assert zone(s, blocked) == "p1:graveyard" and zone(s, blocker) == "p2:graveyard"
    assert zone(s, unblocked) == "p1:battlefield" and zone(s, home) == "p1:battlefield"
    check(s)


def test_end_hostilities_destroys_creatures_and_what_is_attached_to_creatures_only(cards):
    """End Hostilities: "Destroy all creatures and all permanents attached to creatures." An Aura on a creature goes with it; an unattached
    Equipment and a noncreature permanent stay."""
    s = build(cards, ["End Hostilities", "Grizzly Bears", "Holy Strength", "Bonesplitter", "Sol Ring"], ["Grizzly Bears"])
    bear, other = put_on(s, "Grizzly Bears"), put_on(s, "Grizzly Bears", "p2")
    aura = put_on(s, "Holy Strength")
    act(s, "p1", type="attach", card_ids=[aura.id], to=bear.id)
    sword, ring = put_on(s, "Bonesplitter"), put_on(s, "Sol Ring")
    assert s.state.cards[aura.id].attached_to == bear.id
    cast(s, "End Hostilities", W=5)
    assert zone(s, bear) == "p1:graveyard" and zone(s, other) == "p2:graveyard" and zone(s, aura) == "p1:graveyard"
    assert zone(s, sword) == "p1:battlefield" and zone(s, ring) == "p1:battlefield"
    check(s)


def test_soulquake_returns_creatures_and_creature_cards_in_graveyards_to_their_owners(cards):
    """Soulquake: "Return all creatures on the battlefield and all creature cards in graveyards to their owners' hands." A noncreature card
    in a graveyard and a noncreature permanent stay; Bob's creature goes to Bob's hand."""
    s = build(cards, ["Soulquake", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Sol Ring"], ["Grizzly Bears", "Benalish Hero"])
    bear, theirs = put_on(s, "Grizzly Bears"), put_on(s, "Grizzly Bears", "p2")
    elves, bolt = move(s, one(s, "Llanowar Elves"), "graveyard"), move(s, one(s, "Lightning Bolt"), "graveyard")
    hero, ring = move(s, one(s, "Benalish Hero", "p2"), "graveyard"), put_on(s, "Sol Ring")
    cast(s, "Soulquake", U=2, B=2, C=3)
    assert zone(s, bear) == "p1:hand" and zone(s, elves) == "p1:hand"
    assert zone(s, theirs) == "p2:hand" and zone(s, hero) == "p2:hand"
    assert zone(s, bolt) == "p1:graveyard" and zone(s, ring) == "p1:battlefield"
    check(s)


def test_ultimate_nullification_exiles_creatures_and_graveyards_and_goes_to_the_bottom(cards):
    """Ultimate Nullification (additional cost: sacrifice a legendary creature): "Exile all creatures and graveyards. Put Ultimate
    Nullification on the bottom of its owner's library." The sacrificed creature is in the graveyard by then (601.2h) and is exiled too."""
    s = build(cards, ["Ultimate Nullification", "Sliver Queen", "Grizzly Bears", "Lightning Bolt", "Sol Ring"], ["Grizzly Bears", "Opt"])
    queen, bear, theirs = put_on(s, "Sliver Queen"), put_on(s, "Grizzly Bears"), put_on(s, "Grizzly Bears", "p2")
    bolt, opt, ring = move(s, one(s, "Lightning Bolt"), "graveyard"), move(s, one(s, "Opt", "p2"), "graveyard"), put_on(s, "Sol Ring")
    spell = cast(s, "Ultimate Nullification", prefer=["Sliver Queen"], W=1, C=4)
    assert zone(s, queen) == "p1:exile" and zone(s, bear) == "p1:exile" and zone(s, bolt) == "p1:exile"
    assert zone(s, theirs) == "p2:exile" and zone(s, opt) == "p2:exile" and zone(s, ring) == "p1:battlefield"
    assert s.state.zones["p1:library"][-1] == spell.id
    check(s)


def test_shadows_verdict_exiles_small_creatures_and_planeswalkers_on_the_battlefield_and_in_graveyards(cards):
    """Shadows' Verdict: mana value 3 or less, creatures and planeswalkers on the battlefield and creature / planeswalker cards in graveyards.
    A bigger creature and a small noncreature card stay."""
    s = build(cards, ["Shadows' Verdict", "Grizzly Bears", "Sliver Queen", "Liliana of the Veil", "Lightning Bolt"], ["Llanowar Elves"])
    bear, queen = put_on(s, "Grizzly Bears"), put_on(s, "Sliver Queen")
    lili, bolt = move(s, one(s, "Liliana of the Veil"), "graveyard"), move(s, one(s, "Lightning Bolt"), "graveyard")
    elves = move(s, one(s, "Llanowar Elves", "p2"), "graveyard")
    cast(s, "Shadows' Verdict", B=2, C=3)
    assert zone(s, bear) == "p1:exile" and zone(s, lili) == "p1:exile" and zone(s, elves) == "p2:exile"
    assert zone(s, queen) == "p1:battlefield" and zone(s, bolt) == "p1:graveyard"
    check(s)


def test_iridian_maelstrom_spares_only_a_creature_of_all_five_colors(cards):
    """Iridian Maelstrom: "Destroy each creature that isn't all colors." (105.1) Sliver Queen (WUBRG) stays."""
    s = build(cards, ["Iridian Maelstrom", "Sliver Queen", "Grizzly Bears"], ["Benalish Hero"])
    queen, bear, hero = put_on(s, "Sliver Queen"), put_on(s, "Grizzly Bears"), put_on(s, "Benalish Hero", "p2")
    cast(s, "Iridian Maelstrom", W=1, U=1, B=1, R=1, G=1)
    assert zone(s, queen) == "p1:battlefield" and zone(s, bear) == "p1:graveyard" and zone(s, hero) == "p2:graveyard"
    check(s)


def test_hurkyls_recall_returns_the_artifacts_the_target_player_owns_even_under_another_controller(cards):
    """Hurkyl's Recall: "Return all artifacts target player owns to their hand." (108.3) Bob's Sol Ring returns even while Alice controls it;
    Alice's own artifact stays."""
    s = build(cards, ["Hurkyl's Recall", "Sol Ring"], ["Sol Ring", "Arcane Signet"])
    mine, signet = put_on(s, "Sol Ring"), put_on(s, "Arcane Signet", "p2")
    stolen = one(s, "Sol Ring", "p2")
    act(s, "p2", type="move", card_ids=[stolen.id], to={"player": "p1", "zone": "battlefield"})
    assert s.state.cards[stolen.id].controller == "p1"
    cast(s, "Hurkyl's Recall", targets=["p2"], U=1, C=1)
    assert zone(s, stolen) == "p2:hand" and zone(s, signet) == "p2:hand" and zone(s, mine) == "p1:battlefield"
    check(s)


def test_hubris_returns_the_target_and_its_auras_to_their_owners(cards):
    """Hubris: "Return target creature and all Auras attached to it to their owners' hands." Alice's Aura on Bob's creature goes to Alice's
    hand, the creature to Bob's; an Aura on another creature stays."""
    s = build(cards, ["Hubris", "Holy Strength", "Pacifism", "Grizzly Bears"], ["Grizzly Bears"])
    target, other = put_on(s, "Grizzly Bears", "p2"), put_on(s, "Grizzly Bears")
    strength, pacifism = put_on(s, "Holy Strength"), put_on(s, "Pacifism")
    act(s, "p1", type="attach", card_ids=[strength.id], to=target.id)
    act(s, "p1", type="attach", card_ids=[pacifism.id], to=other.id)
    cast(s, "Hubris", targets=[target.id], U=2)
    assert zone(s, target) == "p2:hand" and zone(s, strength) == "p1:hand"
    assert zone(s, other) == "p1:battlefield" and zone(s, pacifism) == "p1:battlefield"
    check(s)


def test_word_of_undoing_returns_only_the_white_auras_you_own_with_it(cards):
    """Word of Undoing: "Return target creature and all white Auras you own attached to it to their owners' hands." Bob's own white Aura
    on it stays (it goes to the graveyard as a state-based action, 704.5m)."""
    s = build(cards, ["Word of Undoing", "Holy Strength"], ["Grizzly Bears", "Holy Strength"])
    target = put_on(s, "Grizzly Bears", "p2")
    mine, theirs = put_on(s, "Holy Strength"), put_on(s, "Holy Strength", "p2")
    act(s, "p1", type="attach", card_ids=[mine.id], to=target.id)
    act(s, "p2", type="attach", card_ids=[theirs.id], to=target.id)
    cast(s, "Word of Undoing", targets=[target.id], U=1)
    assert zone(s, target) == "p2:hand" and zone(s, mine) == "p1:hand" and zone(s, theirs) == "p2:graveyard"
    check(s)


def test_silence_the_believers_exiles_each_target_and_its_auras_paying_strive(cards):
    """Silence the Believers: "Exile any number of target creatures and all Auras attached to them." Two targets: the strive cost once more."""
    s = build(cards, ["Silence the Believers", "Holy Strength", "Grizzly Bears"], ["Grizzly Bears", "Benalish Hero"])
    a, b, safe = put_on(s, "Grizzly Bears", "p2"), put_on(s, "Benalish Hero", "p2"), put_on(s, "Grizzly Bears")
    strength = put_on(s, "Holy Strength")
    act(s, "p1", type="attach", card_ids=[strength.id], to=a.id)
    cast(s, "Silence the Believers", targets=[a.id, b.id], target_counts=[2], B=3, C=4)
    assert zone(s, a) == "p2:exile" and zone(s, b) == "p2:exile" and zone(s, strength) == "p1:exile"
    assert zone(s, safe) == "p1:battlefield"
    assert s.state.players["p1"].mana == {} or not any(s.state.players["p1"].mana.values())  # ({2}{B}{B} + one strive {2}{B}: all of it)
    check(s)


def test_telimtors_edict_targets_only_what_you_own_or_control(cards):
    """Telim'Tor's Edict: "Exile target permanent you own or control." / "Draw a card at the beginning of the next turn's upkeep." Bob's
    own permanent can't be targeted; Bob's Sol Ring under Alice's control can."""
    s = build(cards, ["Telim'Tor's Edict"], ["Sol Ring", "Arcane Signet"])
    stolen, signet = one(s, "Sol Ring", "p2"), put_on(s, "Arcane Signet", "p2")
    act(s, "p2", type="move", card_ids=[stolen.id], to={"player": "p1", "zone": "battlefield"})
    edict = one(s, "Telim'Tor's Edict")
    move(s, edict, "hand")
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=edict.id, targets=[signet.id])
    act(s, "p1", type="cast_spell", card_id=edict.id, targets=[stolen.id])
    settle(s)
    assert zone(s, stolen) == "p2:exile" and zone(s, signet) == "p2:battlefield"
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="set_stops", own=["draw"], others=["draw"], smart_pass=False)
    to_phase(s, "draw", turn=2)  # (the next turn is Bob's: in its upkeep, Alice draws; none of her own draw steps came)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_thraben_exorcism_targets_a_spirit_a_disturb_creature_or_an_enchantment(cards):
    """Thraben Exorcism: "Exile target Spirit, creature with disturb, or enchantment." A creature without disturb can't be targeted."""
    s = build(cards, ["Thraben Exorcism"], ["Baithook Angler // Hook-Haunt Drifter", "Grizzly Bears"])
    angler, bear = put_on(s, "Baithook Angler // Hook-Haunt Drifter", "p2"), put_on(s, "Grizzly Bears", "p2")
    spell = one(s, "Thraben Exorcism")
    move(s, spell, "hand")
    mana(s, W=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[angler.id])
    settle(s)
    assert zone(s, angler) == "p2:exile" and zone(s, bear) == "p2:battlefield"
    check(s)


def test_blazing_hope_needs_power_at_least_your_life_total(cards):
    """Blazing Hope: "Exile target creature with power greater than or equal to your life total." At 2 life, a 2-power creature, not a 1-power one."""
    s = build(cards, ["Blazing Hope"], ["Grizzly Bears", "Llanowar Elves"])
    bear, elves = put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p2")
    act(s, "p1", type="set_life", player="p1", value=2)
    spell = one(s, "Blazing Hope")
    move(s, spell, "hand")
    mana(s, W=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[elves.id])
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    settle(s)
    assert zone(s, bear) == "p2:exile" and zone(s, elves) == "p2:battlefield"
    check(s)


def test_final_act_destroys_creatures_and_each_opponent_loses_every_counter_but_keeps_speed(cards):
    """Final Act, modes 1 and 5: "Destroy all creatures." and "Each opponent loses all counters." (122.1) Bob's poison and energy go;
    his speed (a value, 702.179) and Alice's own counters stay."""
    s = build(cards, ["Final Act", "Grizzly Bears"], ["Grizzly Bears"])
    bear, theirs = put_on(s, "Grizzly Bears"), put_on(s, "Grizzly Bears", "p2")
    for pid, key, n in (("p2", "poison", 3), ("p2", "energy", 2), ("p1", "energy", 4)):
        act(s, pid, type="resource", player=pid, key=key, delta=n)
    act(s, "p2", type="set_resource", player="p2", key="speed", value=2)
    c = one(s, "Final Act")
    move(s, c, "hand")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[0, 4])
    settle(s)
    assert zone(s, bear) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard"
    bob = s.state.players["p2"].resources
    assert bob.get("poison") == 0 and bob.get("energy") == 0 and bob.get("speed") == 2
    assert s.state.players["p1"].resources.get("energy") == 4
    check(s)


def test_early_harvest_untaps_only_the_basic_lands_of_the_target_player(cards):
    """Early Harvest: "Target player untaps all basic lands they control." A nonbasic land stays tapped; Bob's lands too."""
    s = build(cards, ["Early Harvest", "Command Tower"], [])
    forests = [move(s, c, "battlefield") for c in named(s, "Forest")[:3]]
    tower, island = put_on(s, "Command Tower"), move(s, named(s, "Island", "p2")[0], "battlefield")
    act(s, "p1", type="tap", card_ids=[c.id for c in (*forests, tower)], tapped=True)
    act(s, "p2", type="tap", card_ids=[island.id], tapped=True)
    cast(s, "Early Harvest", targets=["p1"], G=3)
    assert not any(s.state.cards[c.id].tapped for c in forests)
    assert s.state.cards[tower.id].tapped and s.state.cards[island.id].tapped
    check(s)


def test_invincible_hymn_sets_life_to_the_number_of_cards_in_your_library(cards):
    """Invincible Hymn: "Count the number of cards in your library. Your life total becomes that number." (608.2h)"""
    s = build(cards, ["Invincible Hymn"], [])
    cast(s, "Invincible Hymn", W=2, C=6)
    assert life(s) == len(s.state.zones["p1:library"])
    check(s)
