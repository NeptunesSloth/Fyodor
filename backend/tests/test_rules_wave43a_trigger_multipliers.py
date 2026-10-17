"""Wave 43A: trigger multipliers, one reusable system (CR 2026-09-25), real Oracle text (tests/fixtures/wave43a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 603.2d: "If [event] causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time." Each such effect adds one
  (two of them: three times, not four); it doesn't copy the ability (each instance is put on the stack with its own targets, 603.3d), applies only to the
  triggered abilities the permanent has (not delayed or reflexive ones, not replacement effects or "as ~ enters").
* 603.6a: the entering cause - Panharmonicon, Yarok, Ancient Greenwarden, Elesh Norn, Naban, Starfield Vocalist, Traveling Chocobo, Virtue of Knowledge. The
  event an ability triggers on is the one it names: "whenever you play a land" (Ancient Greenwarden's ruling), "whenever you sacrifice" (Teysa's) and
  "whenever you create a token" (701.7a, the same kind of action) are not "entering".
* 508.1m, 508.3: the attacking cause (Isshin, Windcrag Siege's Mardu word, Wulfgar); 120.2: dealing combat damage to a player (Felix Five-Boots).
* 603.2d, 301.5, 309.4c, 114.4: the sources "equipped creature" (Wizard's Staff), "Cloud or an Equipment attached to it" (as long as Cloud is equipped), a granted
  "this creature or an emblem you own" (The Masamune), a colorless spell (Echoes of Eternity), "another Shrine … while you control six or more" (Sanctum of All),
  the chosen type (Roaming Throne) and the room abilities of a dungeon (Hama Pashar, Dungeon Delver).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave5d_triggers import confirm_triggers, triggered
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave43a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w43a", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
MULTIPLIERS = ["Panharmonicon", "Yarok, the Desecrated", "Ancient Greenwarden", "Elesh Norn, Mother of Machines", "Isshin, Two Heavens as One",
               "Windcrag Siege", "Wulfgar of Icewind Dale", "Felix Five-Boots", "Roaming Throne", "Echoes of Eternity", "Cloud, Midgar Mercenary",
               "Wizard's Staff", "The Masamune", "Sanctum of All", "Naban, Dean of Iteration", "Starfield Vocalist", "Traveling Chocobo",
               "Virtue of Knowledge // Vantress Visions", "Hama Pashar, Ruin Seeker", "Dungeon Delver"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", MULTIPLIERS)
def test_every_multiplier_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, prefer=("yes",), limit=80):
    """Resolve everything; a decision is answered with the first of ``prefer`` it offers (card names or option ids), else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, s.state.cards[o.card_id].name if o.card_id in s.state.cards else None)]
            pick = want[: max(1, d.min_choices)] if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, pid="p1", prefer=("yes",), **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s, prefer)


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn} (at {s.state.turn.phase} of turn {s.state.turn.number})")


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def lands(s, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.controller == pid and c.zone == f"{pid}:battlefield" and c.name in ("Forest", "Island"))


# --- 603.6a: entering ------------------------------------------------------------------------------------------------------------------------
def test_panharmonicon_and_yarok_stack_to_three(cards):
    """Panharmonicon (an artifact or creature entering) and Yarok (a permanent entering) each add one: Elvish Visionary's "When this creature enters, draw a
    card" triggers three times, not four (Panharmonicon's rulings of 2021-03-19: two of them, three times)."""
    s = build(cards, ["Panharmonicon", "Yarok, the Desecrated", "Elvish Visionary"])
    put(s, "Panharmonicon")
    put(s, "Yarok, the Desecrated")
    to_hand(s, "Elvish Visionary")
    before = hand(s)
    mana(s, G=2)
    cast(s, "Elvish Visionary")
    assert hand(s) == before - 1 + 3
    check(s)


@pytest.mark.parametrize(("multiplier", "land", "creature"), [
    ("Panharmonicon", 1, 2),  # an artifact or creature: not a land
    ("Ancient Greenwarden", 2, 1),  # a land: not a creature
    ("Yarok, the Desecrated", 2, 2),  # a permanent
    ("Starfield Vocalist", 2, 2),
    ("Virtue of Knowledge // Vantress Visions", 2, 2),
    ("Elesh Norn, Mother of Machines", 2, 2),
    ("Traveling Chocobo", 2, 1),  # a land or Bird you control: Elvish Visionary is an Elf Shaman
    ("Naban, Dean of Iteration", 1, 1),  # a Wizard you control
])
def test_which_permanent_entering_is_the_cause(cards, multiplier, land, creature):
    """Evolution Sage's landfall and Elvish Visionary's "enters" each trigger once, plus once for every multiplier whose event is the entering land or creature
    (the rulings: the trigger event needn't name the type - landfall is caused by "a land entering")."""
    s = build(cards, [multiplier, "Evolution Sage", "Elvish Visionary"])
    put(s, multiplier)
    put(s, "Evolution Sage")
    confirm_triggers(s)
    act(s, "p1", type="play_land", card_id=to_hand(s, "Forest").id)
    assert triggered(s) == ["Evolution Sage"] * land
    settle(s)
    to_hand(s, "Elvish Visionary")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Elvish Visionary").id)
    assert triggered(s) == ["Elvish Visionary"] * creature
    settle(s)
    check(s)


def test_an_opponents_multiplier_does_not_count_but_the_entering_permanent_may_be_theirs(cards):
    """Rulings: "You don't need to control the permanent entering the battlefield, only the permanent that has the triggered ability." An opponent's
    Panharmonicon is not a multiplier of mine (603.2d: "a permanent you control")."""
    s = build(cards, ["Panharmonicon", "Soul Warden"], ["Panharmonicon", "Grizzly Bears", "Elvish Visionary"])
    put(s, "Panharmonicon", "p2")
    put(s, "Soul Warden")
    to_phase(s, "main1", turn=2)
    gained = life(s)
    to_hand(s, "Grizzly Bears", "p2")
    mana(s, "p2", G=2)
    cast(s, "Grizzly Bears", "p2")
    assert life(s) == gained + 1  # (Soul Warden: "another creature enters", once - the Panharmonicon isn't mine)
    put(s, "Panharmonicon")  # mine too: a creature of theirs entering now causes my Soul Warden to trigger twice
    to_hand(s, "Elvish Visionary", "p2")
    mana(s, "p2", G=2)
    cast(s, "Elvish Visionary", "p2")
    assert life(s) == gained + 1 + 2
    check(s)


def test_creating_a_token_is_not_the_token_entering(cards):
    """Staff of the Storyteller: "When this artifact enters, create a 1/1 white Spirit creature token with flying." (an artifact entering: twice, so two
    tokens) and "Whenever you create one or more creature tokens, put a story counter on this artifact." Creating tokens is an action of its own
    (701.7a), the event that second ability names, as "you play a land" or "you sacrifice a creature" are not the entering or the dying (rulings of
    Ancient Greenwarden, 2020-09-25, and Teysa Karlov, 2019-01-25): one story counter for each creation, not two."""
    s = build(cards, ["Panharmonicon", "Staff of the Storyteller"])
    put(s, "Panharmonicon")
    to_hand(s, "Staff of the Storyteller")
    mana(s, W=1, G=1)
    cast(s, "Staff of the Storyteller")
    spirits = [c for c in s.state.cards.values() if c.controller == "p1" and c.zone == "p1:battlefield" and c.is_token]
    assert len(spirits) == 2
    assert s.state.cards[card_named(s, "Staff of the Storyteller").id].counters.get("story") == 2
    check(s)


def test_elesh_norn_doubles_my_abilities_and_stops_theirs(cards):
    """Elesh Norn, Mother of Machines: a permanent entering causes my abilities to trigger an additional time and doesn't cause abilities of permanents my
    opponents control to trigger (rulings: whoever controls the permanent entering, only who controls the one with the ability)."""
    s = build(cards, ["Elesh Norn, Mother of Machines", "Soul Warden"], ["Soul Warden", "Elvish Visionary"])
    put(s, "Elesh Norn, Mother of Machines")
    put(s, "Soul Warden")
    put(s, "Soul Warden", "p2")
    to_phase(s, "main1", turn=2)
    to_hand(s, "Elvish Visionary", "p2")
    mine, theirs, cards_in_hand = life(s), life(s, "p2"), hand(s, "p2")
    mana(s, "p2", G=2)
    cast(s, "Elvish Visionary", "p2")
    assert life(s) == mine + 2  # my Soul Warden: twice
    assert life(s, "p2") == theirs and hand(s, "p2") == cards_in_hand - 1  # their Soul Warden and their Visionary's own draw: nothing
    check(s)


def test_an_ability_that_triggers_only_once_each_turn_is_not_multiplied(cards):
    """Welcoming Vampire: "Whenever one or more other creatures you control with power 2 or less enter, draw a card. This ability triggers only once each
    turn." With Panharmonicon it still draws one card, and none for the next creature that turn (ruling of Elvish Warmaster, 2021-02-05: "Once the
    triggered ability has triggered once during a turn, it can't trigger again"); the creature's own enters ability is not so limited."""
    s = build(cards, ["Panharmonicon", "Welcoming Vampire", "Elvish Visionary", "Dwynen's Elite"])
    put(s, "Panharmonicon")
    put(s, "Welcoming Vampire")
    to_hand(s, "Elvish Visionary")
    to_hand(s, "Dwynen's Elite")
    before = hand(s)
    mana(s, G=2)
    cast(s, "Elvish Visionary")
    assert hand(s) == before - 1 + 1 + 2  # the Vampire once; the Visionary's own "enters" twice
    mana(s, G=2)
    cast(s, "Dwynen's Elite")
    assert hand(s) == before - 2 + 1 + 2  # no card from the Vampire again this turn
    check(s)


def test_an_intervening_if_is_checked_for_every_instance_and_when_it_triggers(cards):
    """Dwynen's Elite: "When this creature enters, if you control another Elf, create a 1/1 green Elf Warrior creature token." (603.4: the condition is checked as
    it would trigger, so with no other Elf there is nothing to multiply, and again as each instance resolves). With Panharmonicon and an Elf: two tokens."""
    s = build(cards, ["Panharmonicon", "Dwynen's Elite", "Elvish Visionary"])
    put(s, "Panharmonicon")
    to_hand(s, "Dwynen's Elite")
    mana(s, G=2)
    cast(s, "Dwynen's Elite")
    assert not [c for c in s.state.cards.values() if c.is_token]  # (no other Elf: no trigger at all)
    put(s, "Elvish Visionary")  # an Elf is there now
    act(s, "p1", type="move", card_ids=[card_named(s, "Dwynen's Elite").id], to={"zone": "hand"})
    mana(s, G=2)
    cast(s, "Dwynen's Elite")
    assert len([c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]) == 2
    check(s)


def test_naban_doubles_a_wizards_conditional_enters_ability(cards):
    """Naban, Dean of Iteration (commander): "If a Wizard you control entering causes a triggered ability of a permanent you control to trigger, that ability
    triggers an additional time." Ghitu Journeymage (a Wizard): "When this creature enters, if you control another Wizard, this creature deals 2 damage to each
    opponent." - 4 damage; a Wizard entering counts for abilities of other permanents as well (Soul Warden), a non-Wizard doesn't."""
    s = build(cards, ["Naban, Dean of Iteration", "Ghitu Journeymage", "Soul Warden", "Elvish Visionary"])
    put(s, "Naban, Dean of Iteration")
    put(s, "Soul Warden")
    to_hand(s, "Ghitu Journeymage")
    theirs, mine = life(s, "p2"), life(s)
    mana(s, R=3)
    cast(s, "Ghitu Journeymage")
    assert life(s, "p2") == theirs - 4 and life(s) == mine + 2  # (Soul Warden twice: the Journeymage is a Wizard)
    to_hand(s, "Elvish Visionary")
    mana(s, G=2)
    cast(s, "Elvish Visionary")
    assert life(s) == mine + 2 + 1  # (an Elf Shaman: once)
    check(s)


# --- 508.1m, 508.3: attacking -------------------------------------------------------------------------------------------------------------
def attack(s, *attackers, turn=None):
    """Alice attacks Bob with these creatures (on her turn ``turn``) and everything that triggered resolves; the combat is left at the declare attackers step."""
    to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    settle(s)


@pytest.mark.parametrize(("multiplier", "word", "counters"), [
    (None, (), 1), ("Isshin, Two Heavens as One", (), 2), ("Wulfgar of Icewind Dale", (), 2),
    ("Windcrag Siege", ("Mardu",), 2), ("Windcrag Siege", ("Jeskai",), 1),  # the Siege's Mardu ability is there only for the word it chose as it entered
])
def test_a_creature_attacking_triggers_gleam_of_battles_ability_again(cards, multiplier, word, counters):
    """Gleam of Battle: "Whenever a creature you control attacks, put a +1/+1 counter on it." Isshin ("a creature attacking"), Wulfgar ("a creature you control
    attacking") and Windcrag Siege's Mardu word: each attack makes it trigger twice."""
    s = build(cards, ["Gleam of Battle", "Grizzly Bears", *([multiplier] if multiplier else [])], forests=30, islands=30)
    put(s, "Gleam of Battle")
    bears = put(s, "Grizzly Bears")
    if multiplier == "Windcrag Siege":
        to_hand(s, multiplier)
        mana(s, R=1, W=1, B=1, G=1)
        cast(s, multiplier, prefer=word)
    elif multiplier:
        put(s, multiplier)
    to_phase(s, "main1", turn=3)
    attack(s, bears, turn=3)
    assert pt(s, "Grizzly Bears") == (2 + counters, 2 + counters)
    check(s)
    s = reloaded(s)
    assert pt(s, "Grizzly Bears") == (2 + counters, 2 + counters)


def test_wulfgars_melee_triggers_twice(cards):
    """Wulfgar of Icewind Dale: "Melee (Whenever this creature attacks, it gets +1/+1 until end of turn for each opponent you attacked this combat.)" and its
    own multiplier (ruling of 2021-07-23: "Wulfgar's last ability will cause its melee ability to trigger an additional time")."""
    s = build(cards, ["Wulfgar of Icewind Dale"], forests=30, islands=30)
    wulfgar = put(s, "Wulfgar of Icewind Dale")
    base = s.state.cards[wulfgar.id]
    power, toughness = pt(s, "Wulfgar of Icewind Dale")
    to_phase(s, "main1", turn=3)
    attack(s, base, turn=3)
    assert pt(s, "Wulfgar of Icewind Dale") == (power + 2, toughness + 2)
    check(s)


@pytest.mark.parametrize(("multiplier", "drained"), [("Isshin, Two Heavens as One", 2), ("Wulfgar of Icewind Dale", 1)])
def test_isshin_counts_any_creature_attacking_wulfgar_only_mine(cards, multiplier, drained):
    """Revenge of Ravens: "Whenever a creature attacks you or a planeswalker you control, that creature's controller loses 1 life and you gain 1 life." Bob's
    Grizzly Bears attacking me is "a creature attacking" for Isshin, but not "a creature you control attacking" for Wulfgar."""
    s = build(cards, ["Revenge of Ravens", multiplier], ["Grizzly Bears"], forests=30, islands=30)
    put(s, "Revenge of Ravens")
    put(s, multiplier)
    bears = put(s, "Grizzly Bears", "p2")
    to_phase(s, "declare_attackers", turn=2)
    mine, theirs = life(s), life(s, "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    settle(s)
    assert (life(s), life(s, "p2")) == (mine + drained - 2, theirs - drained)  # (the Bears' own 2 combat damage to me comes too)
    check(s)


def test_isshin_doubles_exalted(cards):
    """702.83a: exalted - "Whenever a creature you control attacks alone, that creature gets +1/+1 until end of turn" - is an ability directly related to
    attacking: Akrasan Squire alone, with Isshin, gets +2/+2."""
    s = build(cards, ["Isshin, Two Heavens as One", "Akrasan Squire"], forests=30, islands=30)
    put(s, "Isshin, Two Heavens as One")
    squire = put(s, "Akrasan Squire")
    to_phase(s, "main1", turn=3)
    attack(s, squire, turn=3)
    assert pt(s, "Akrasan Squire") == (3, 3)
    check(s)


def test_attacks_and_isnt_blocked_is_not_the_creature_attacking(cards):
    """508.3f, 509.3g: "Whenever this creature attacks and isn't blocked, draw a card." (Eternal of Harsh Truths) triggers at the declare blockers step, even
    for a creature that was never declared as an attacker - it isn't caused by the creature attacking, so Isshin doesn't add to it."""
    s = build(cards, ["Eternal of Harsh Truths", "Isshin, Two Heavens as One"], forests=30, islands=30)
    put(s, "Isshin, Two Heavens as One")
    eternal = put(s, "Eternal of Harsh Truths")
    to_phase(s, "main1", turn=3)
    before = hand(s)
    attack(s, eternal, turn=3)
    assert hand(s) == before + 1  # (one card: the declare blockers step has passed with nothing blocking it)
    check(s)


def test_felix_five_boots_combat_damage_to_a_player(cards):
    """Felix Five-Boots (commander): "If a creature you control dealing combat damage to a player causes a triggered ability of a permanent you control to
    trigger, that ability triggers an additional time." Thieving Magpie: "Whenever this creature deals damage to an opponent, draw a card." - two cards."""
    s = build(cards, ["Felix Five-Boots", "Thieving Magpie"], forests=30, islands=30)
    put(s, "Felix Five-Boots")
    magpie = put(s, "Thieving Magpie")
    to_phase(s, "main1", turn=3)
    before = hand(s)
    attack(s, magpie, turn=3)
    to_phase(s, "main2")
    settle(s)
    assert hand(s) == before + 2
    check(s)


# --- the chosen type, colorless spells, equipment, the Shrines, the rooms ----------------------------------------------------------------------
@pytest.mark.parametrize(("types", "draws"), [(("Elf",), 2), (("Elf", "Elf"), 3), (("Goblin",), 1), (("Elf", "Goblin"), 2)])
def test_roaming_throne_the_chosen_type(cards, types, draws):
    """Roaming Throne: "As this creature enters, choose a creature type. … If a triggered ability of another creature you control of the chosen type triggers,
    it triggers an additional time." Elvish Visionary is an Elf; two Thrones that chose Elf make it trigger three times (rulings of 2023-11-10); a Throne that
    chose another type doesn't count (and "another": a Throne is not its own multiplier)."""
    s = build(cards, ["Roaming Throne", "Roaming Throne", "Elvish Visionary"], forests=30, islands=30)
    thrones = [c for c in s.state.cards.values() if c.name == "Roaming Throne" and c.owner == "p1"]
    for throne, chosen in zip(thrones, types, strict=False):
        act(s, "p1", type="move", card_ids=[throne.id], to={"zone": "hand"})
        mana(s, C=4)
        act(s, "p1", type="cast_spell", card_id=throne.id)
        settle(s, prefer=(chosen, "yes"))
        assert s.state.cards[throne.id].choices  # (the type it chose is kept with it)
    to_hand(s, "Elvish Visionary")
    before = hand(s)
    mana(s, G=2)
    cast(s, "Elvish Visionary")
    assert hand(s) == before - 1 + draws
    check(s)


def test_echoes_of_eternity_colorless_spells(cards):
    """Echoes of Eternity: "If a triggered ability of a colorless spell you control or another colorless permanent you control triggers, that ability triggers an
    additional time." Kozilek, Butcher of Truth is colorless: "When you cast this spell, draw four cards." draws eight; Prossh, Skyraider of Kher (red, black and
    green): "When you cast this spell, create X 0/1 red Kobold creature tokens …" once."""
    s = build(cards, ["Echoes of Eternity", "Kozilek, Butcher of Truth", "Prossh, Skyraider of Kher"], forests=40, islands=40)
    put(s, "Echoes of Eternity")
    to_hand(s, "Prossh, Skyraider of Kher")
    to_hand(s, "Kozilek, Butcher of Truth")
    mana(s, B=1, R=1, G=1, C=3)
    cast(s, "Prossh, Skyraider of Kher")
    kobolds = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield" and "Kobold" in (c.name or "")]
    assert len(kobolds) == 6  # X is the six mana spent, once
    before = hand(s)
    mana(s, C=10)
    cast(s, "Kozilek, Butcher of Truth")
    assert hand(s) == before - 1 + 8
    check(s)


def attach(s, equipment, host):
    act(s, "p1", type="attach", card_ids=[equipment.id], to=host.id)


def test_cloud_is_multiplied_only_while_equipped(cards):
    """Cloud, Midgar Mercenary (commander): "As long as Cloud is equipped, if a triggered ability of Cloud or an Equipment attached to it triggers, that
    ability triggers an additional time." Sword of the Animist: "Whenever equipped creature attacks, you may search your library for a basic land card …":
    attached to Cloud, twice; attached to another creature (Cloud not equipped), once."""
    s = build(cards, ["Cloud, Midgar Mercenary", "Sword of the Animist", "Grizzly Bears"], forests=40, islands=40)
    cloud, sword, bears = put(s, "Cloud, Midgar Mercenary"), put(s, "Sword of the Animist"), put(s, "Grizzly Bears")
    attach(s, sword, bears)
    to_phase(s, "main1", turn=3)
    before = lands(s)
    attack(s, bears, turn=3)
    assert lands(s) == before + 1
    to_phase(s, "main1", turn=5)
    attach(s, sword, cloud)
    before = lands(s)
    attack(s, cloud, turn=5)
    assert lands(s) == before + 2
    check(s)


def test_wizards_staff_equipped_creature(cards):
    """Wizard's Staff: "If a triggered ability of equipped creature triggers, that ability triggers an additional time." Eternal of Harsh Truths: "Whenever this
    creature attacks and isn't blocked, draw a card."; Solemn Simulacrum "When Solemn Simulacrum dies, you may draw a card." (its abilities as it last existed:
    603.10a - the Staff was attached to it right before)."""
    s = build(cards, ["Wizard's Staff", "Eternal of Harsh Truths", "Solemn Simulacrum", "Murder"], forests=40, islands=40)
    staff, eternal, solemn = put(s, "Wizard's Staff"), put(s, "Eternal of Harsh Truths"), put(s, "Solemn Simulacrum")
    attach(s, staff, eternal)
    to_phase(s, "main1", turn=3)
    before = hand(s)
    attack(s, eternal, turn=3)
    assert hand(s) == before + 2
    attach(s, staff, solemn)
    to_hand(s, "Murder")
    before = hand(s)
    mana(s, B=3)
    cast(s, "Murder", targets=[solemn.id])
    assert s.state.cards[solemn.id].zone == "p1:graveyard" and hand(s) == before - 1 + 2
    check(s)


def test_cloud_equipped_with_skullclamp_dies_and_the_clamp_triggers_twice(cards):
    """Cloud, Midgar Mercenary dies while equipped with Skullclamp ("Whenever equipped creature dies, draw two cards."): both look back in time to what was
    attached right before (603.10a) - Cloud was equipped and the Equipment was attached to it - so the Equipment's ability triggers an additional time."""
    s = build(cards, ["Cloud, Midgar Mercenary", "Skullclamp", "Murder"], forests=40, islands=40)
    cloud, clamp = put(s, "Cloud, Midgar Mercenary"), put(s, "Skullclamp")
    attach(s, clamp, cloud)
    to_hand(s, "Murder")
    before = hand(s)
    mana(s, B=3)
    cast(s, "Murder", targets=[cloud.id])
    assert s.state.cards[cloud.id].zone == "p1:graveyard" and hand(s) == before - 1 + 4
    check(s)


def test_the_masamune_grants_the_multiplier_to_its_creature(cards):
    """The Masamune: "Equipped creature has 'If a creature dying causes a triggered ability of this creature or an emblem you own to trigger, that ability
    triggers an additional time.'" Blood Artist wearing it triggers twice for another creature dying (and one without it once); Solemn Simulacrum dying
    while wearing it triggers its own "dies" ability twice (the grant is among the abilities it last had, 603.10a)."""
    s = build(cards, ["The Masamune", "Blood Artist", "Solemn Simulacrum", "Grizzly Bears", "Murder"], forests=40, islands=40)
    masamune, artist, solemn, bears = (put(s, n) for n in ("The Masamune", "Blood Artist", "Solemn Simulacrum", "Grizzly Bears"))
    attach(s, masamune, artist)
    confirm_triggers(s)
    to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[bears.id])
    assert triggered(s) == ["Blood Artist"] * 2
    settle(s)
    attach(s, masamune, solemn)
    to_hand(s, "Murder")
    before = hand(s)
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[solemn.id])
    assert triggered(s) == ["Blood Artist", "Solemn Simulacrum", "Solemn Simulacrum"]  # (the Artist, no longer wearing it: once)
    settle(s)
    assert hand(s) == before - 1 + 2
    check(s)


@pytest.mark.parametrize(("equipped", "gained"), [(True, 2), (False, 1)])
def test_the_masamune_and_an_emblem_you_own(cards, equipped, gained):
    """"… a triggered ability of this creature or an emblem you own": my emblem "Whenever a creature dies, you gain 1 life." (114.4: it works from the command
    zone, I own it) triggers an additional time for a creature dying while one of my creatures wears The Masamune."""
    from tests.test_rules_wave13a_emblems import get_emblem

    s = build(cards, ["The Masamune", "Grizzly Bears", "Murder", "Elvish Visionary"], forests=40, islands=40)
    masamune, bears, visionary = put(s, "The Masamune"), put(s, "Grizzly Bears"), put(s, "Elvish Visionary")
    if equipped:
        attach(s, masamune, visionary)
    get_emblem(s, 'You get an emblem with "Whenever a creature dies, you gain 1 life."')
    to_hand(s, "Murder")
    mana(s, B=3)
    mine = life(s)
    cast(s, "Murder", targets=[bears.id])
    assert life(s) == mine + gained
    check(s)


SHRINES = ["Honden of Cleansing Fire", "Sanctum of Tranquil Light", "Go-Shintai of Shared Purpose", "Go-Shintai of Lost Wisdom", "Go-Shintai of Hidden Cruelty"]


@pytest.mark.parametrize(("others", "gained"), [(5, 2 * 6 * 2), (4, 2 * 5)])
def test_sanctum_of_all_needs_six_shrines(cards, others, gained):
    """Sanctum of All: "If a triggered ability of another Shrine you control triggers while you control six or more Shrines, that ability triggers an
    additional time." Honden of Cleansing Fire: "At the beginning of your upkeep, you gain 2 life for each Shrine you control." - six Shrines (Sanctum and five
    more): twice; five: once."""
    s = build(cards, ["Sanctum of All", *SHRINES[:others]], forests=40, islands=40)
    put(s, "Sanctum of All")
    for name in SHRINES[:others]:
        put(s, name)
    mine = life(s)
    to_phase(s, "upkeep", turn=3)
    settle(s, prefer=("no",))
    assert life(s) == mine + gained
    check(s)


@pytest.mark.parametrize(("permanents", "extra"), [(("Hama Pashar, Ruin Seeker",), 1), (("Hama Pashar, Ruin Seeker", "Dungeon Delver", "Krenko, Mob Boss"), 2),
                                                   (("Dungeon Delver", "Krenko, Mob Boss"), 1), (("Dungeon Delver",), 0), ((), 0)])
def test_room_abilities_trigger_an_additional_time(cards, permanents, extra):
    """Hama Pashar, Ruin Seeker and Dungeon Delver ("Commander creatures you own have 'Room abilities of dungeons you own trigger an additional time.'") (309.4c):
    Nadaar, Selfless Paladin "Whenever Nadaar enters or attacks, venture into the dungeon." - the first room of Dungeon of the Mad Mage, Yawning Portal: "You
    gain 1 life.", triggers once more for each (rulings of 2021-07-23 and 2022-06-10: it doesn't move the marker; Hama, Delver and a commander: two more)."""
    s = build(cards, ["Nadaar, Selfless Paladin", *(p for p in permanents if p != "Krenko, Mob Boss")], forests=40, islands=40)
    for name in permanents:
        put(s, name)
    to_hand(s, "Nadaar, Selfless Paladin")
    mine = life(s)
    mana(s, W=1, G=2)
    cast(s, "Nadaar, Selfless Paladin", prefer=("Dungeon of the Mad Mage", "yes"))
    assert life(s) == mine + 1 + extra
    check(s)


def test_gandalf_the_white_entering_or_leaving(cards):
    """Gandalf the White: "If a legendary permanent or an artifact entering or leaving the battlefield causes a triggered ability of a permanent you control to
    trigger, that ability triggers an additional time." Perilous Myr (an artifact creature) dying: its ability twice; Elvish Visionary (neither) entering: once."""
    s = build(cards, ["Gandalf the White", "Perilous Myr", "Elvish Visionary", "Murder"], forests=40, islands=40)
    put(s, "Gandalf the White")
    myr = put(s, "Perilous Myr")
    confirm_triggers(s)
    to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[myr.id])
    assert triggered(s) == ["Perilous Myr"] * 2
    settle(s)
    to_hand(s, "Elvish Visionary")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Elvish Visionary").id)
    assert triggered(s) == ["Elvish Visionary"]
    settle(s)
    check(s)
