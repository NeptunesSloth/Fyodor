"""Wave 111D: Star Trek cost changes and counters. Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a save and a load.

* Gagh Slinger: "Klingon spells and Warrior spells you cast cost {1} less to cast." (601.2f: one effect, so a Klingon Warrior spell costs {1} less once;
  it reduces only generic mana, 118.7d) and "Whenever another Klingon or Warrior you control enters, …" (one trigger for a Klingon Warrior).
* Cloak and Phaser: "This spell costs {X} less to cast, where X is the number of differently named lands you control." (601.2f; a name counted once).
* General Chang: "{1}, Sacrifice a creature: Put a +1/+1 counter on each Klingon you control." (602.2: the creature is chosen and sacrificed as a cost).
* Maturation Chamber: a charge counter for each artifact spell its controller casts, then "{4}, {T}: Create a 1/1 colorless Borg artifact creature token
  for each charge counter on this artifact. Activate only as a sorcery."
* The Star Trek creature types (Klingon, Romulan, Borg, Officer) are the subtypes printed on those sets' type lines (205.3a; CR 205.3m predates them).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, check, life, mana, put, to_hand

EXTRA = [
    real("Gagh Slinger", "{2}{R}", 3, "Creature — Klingon Warrior", "Klingon spells and Warrior spells you cast cost {1} less to cast.\nWhenever another "
         "Klingon or Warrior you control enters, this creature deals 1 damage to each opponent.", ("3", "2"), "R"),
    real("Cloak and Phaser", "{8}{U}", 9, "Sorcery", "Strange new worlds — This spell costs {X} less to cast, where X is the number of differently named lands "
         "you control.\nCreate two 2/2 black Romulan creature tokens. Draw two cards, then discard a card.", None, "U"),
    real("General Chang, Cold Warrior", "{B}", 1, "Legendary Creature — Klingon Warrior Officer", "{1}, Sacrifice a creature: Put a +1/+1 counter on each "
         "Klingon you control.", ("1", "2"), "B"),
    real("The Beacon of Kahless", "{2}{R}", 3, "Legendary Artifact", "{T}: Add one mana of any color.\nBattlefront — {T}: Choose a color. Add an amount of "
         "mana of that color equal to the number of opponents you attacked this turn.", None, "R"),
    real("Starfleet Academy", "", 0, "Legendary Land", "{T}: Add {C}.\nFederation — {5}, {T}: Choose a color. Add an amount of mana of that color equal to "
         "the number of creature types among non-Borg creatures you control.", None, ""),
    real("Maturation Chamber", "{1}{W}", 2, "Artifact", "Whenever you cast an artifact spell, put a charge counter on this artifact.\n{4}, {T}: Create a 1/1 "
         "colorless Borg artifact creature token for each charge counter on this artifact. Activate only as a sorcery.", None, "W"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Warship Flight Crew", "{1}{R}", 2, "Creature — Klingon Pilot", "", ("2", "2"), "R"),
    real("Defense Force Aggressor", "{R}", 1, "Creature — Klingon Warrior", "", ("2", "1"), "R"),
    real("Goblin Piker", "{1}{R}", 2, "Creature — Goblin Warrior", "", ("2", "1"), "R"),
    real("Worf, Chief Tactical Officer", "{2}{W}", 3, "Legendary Creature — Klingon Warrior Officer", "Vigilance (Attacking doesn't cause this creature "
         "to tap.)", ("2", "3"), "W"),
    real("Centaur Courser", "{2}{G}", 3, "Creature — Centaur Warrior", "", ("3", "3"), "G"),
    real("Assault Drone", "{3}{B}", 4, "Artifact Creature — Borg", "Artifact creatures you control get +1/+0.", ("2", "4"), "B"),
    real("Universal Automaton", "{1}", 1, "Artifact Creature — Shapeshifter", "Changeling (This card is every creature type.)", ("1", "1"), ""),
    real("Mox Jet", "{0}", 0, "Artifact", "{T}: Add {B}.", None, ""),
    real("Ur-Golem's Eye", "{4}", 4, "Artifact", "{T}: Add {C}{C}.", None, ""),
]


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


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def build3(cards, p1=(), p2=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Mountain")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def counters(s, c, kind="+1/+1"):
    return s.state.cards[c.id].counters.get(kind, 0)


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


# -- Gagh Slinger ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "paid", "short", "trigger"), [
    ("Warship Flight Crew", {"R": 1}, None, True),                     # Klingon: {1}{R} → {R}
    ("Goblin Piker", {"R": 1}, None, True),                            # Warrior: {1}{R} → {R}
    ("Worf, Chief Tactical Officer", {"W": 1, "C": 1}, {"W": 1}, True),  # Klingon Warrior: {2}{W} → {1}{W}, once
    ("Grizzly Bears", {"G": 1, "C": 1}, {"G": 1}, False),              # neither: full price, no trigger
])
def test_gagh_slinger_discounts_klingons_and_warriors_and_pings_each_opponent(cards, name, paid, short, trigger):
    s = build3(cards, ["Gagh Slinger", name])
    put(s, "Gagh Slinger")
    if short is not None:  # (one generic mana short of the reduced cost)
        mana(s, **short)
        with pytest.raises(ActionError):
            cast(s, name)
        act(s, "p1", type="clear_mana", player="p1")
    mana(s, **paid)
    c = cast(s, name)
    answer(s)
    assert s.state.cards[c.id].zone == "p1:battlefield"
    hit = 39 if trigger else 40  # (one trigger for a Klingon Warrior)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, hit, hit)
    check(s)


def test_gagh_slinger_ignores_an_opponents_klingon(cards):
    s = build(cards, ["Gagh Slinger"], ["Warship Flight Crew"])
    put(s, "Gagh Slinger")
    to_phase(s, "main1", turn=2)
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):  # ("Klingon spells … you cast": not Bob's)
        cast(s, "Warship Flight Crew", pid="p2")
    mana(s, "p2", C=1)
    crew = cast(s, "Warship Flight Crew", pid="p2")  # (an opponent's Klingon entering: "you control")
    answer(s)
    assert s.state.cards[crew.id].zone == "p2:battlefield"
    assert (life(s, "p1"), life(s, "p2")) == (40, 40)
    check(s)


# -- Cloak and Phaser --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("lands", "generic"), [((), 8), (("Forest", "Island", "Mountain"), 5)])
def test_cloak_and_phaser_costs_less_per_differently_named_land(cards, lands, generic):
    s = build(cards, ["Cloak and Phaser", "Island", "Mountain", "Grizzly Bears", "Goblin Piker"])
    put_lands = [put(s, land) for land in lands]
    if lands:
        second = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "battlefield"})  # (a second Forest: one name, counted once)
        put_lands.append(second)
        assert len(on_battlefield(s, "Forest")) == 2
        act(s, "p1", type="tap", card_ids=[c.id for c in put_lands], tapped=True)  # (tapped lands still count; none pays)
    mana(s, U=1, C=generic - 1)
    with pytest.raises(ActionError):
        cast(s, "Cloak and Phaser")
    act(s, "p1", type="clear_mana", player="p1")
    mana(s, U=1, C=generic)
    spell = cast(s, "Cloak and Phaser")
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    romulans = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token]
    assert len(romulans) == 2
    for r in romulans:
        c = ch(s, r)
        assert c.types == {"Creature"} and c.subtypes == {"Romulan"} and c.colors == {"B"} and c.pt == (2, 2)
    assert len(s.state.zones["p1:hand"]) == 1 and len(s.state.zones["p1:graveyard"]) == 2  # (drew two, discarded one)
    check(s)


# -- General Chang -----------------------------------------------------------------------------------------------------------------------
def test_general_chang_sacrifices_a_creature_to_grow_each_klingon_you_control(cards):
    s = build(cards, ["General Chang, Cold Warrior", "Warship Flight Crew", "Grizzly Bears"], ["Defense Force Aggressor"])
    chang = put(s, "General Chang, Cold Warrior")
    crew = put(s, "Warship Flight Crew")
    bears = put(s, "Grizzly Bears")
    theirs = put(s, "Defense Force Aggressor", "p2")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=chang.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {chang.id, crew.id, bears.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    answer(s)
    assert (counters(s, chang), counters(s, crew), counters(s, theirs)) == (1, 1, 0)
    check(s)


def test_general_chang_can_sacrifice_himself_and_still_grows_the_other_klingons(cards):
    s = build(cards, ["General Chang, Cold Warrior", "Warship Flight Crew"])
    chang = put(s, "General Chang, Cold Warrior")
    crew = put(s, "Warship Flight Crew")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=chang.id, ability=0)
    answer(s, chang.id)
    assert s.state.cards[chang.id].zone == "p1:graveyard" and counters(s, crew) == 1  # (113.7a: the ability resolves without its source)
    check(s)


# -- Maturation Chamber ------------------------------------------------------------------------------------------------------------------
def test_maturation_chamber_counts_artifact_spells_then_makes_that_many_borg(cards):
    s = build(cards, ["Maturation Chamber", "Mox Jet", "Ur-Golem's Eye", "Grizzly Bears"])
    chamber = put(s, "Maturation Chamber")
    cast(s, "Mox Jet")
    answer(s)
    mana(s, C=4)
    cast(s, "Ur-Golem's Eye")
    answer(s)
    mana(s, G=1, C=1)
    cast(s, "Grizzly Bears")  # (no artifact: no counter)
    answer(s)
    assert counters(s, chamber, "charge") == 2
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=chamber.id, ability=1)
    answer(s)
    borg = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token]
    assert len(borg) == 2 and s.state.cards[chamber.id].tapped
    for b in borg:
        c = ch(s, b)
        assert c.types == {"Artifact", "Creature"} and c.subtypes == {"Borg"} and not c.colors and c.pt == (1, 1)
    check(s)


def test_maturation_chamber_ignores_an_opponents_artifact_spell_and_activates_only_as_a_sorcery(cards):
    s = build(cards, ["Maturation Chamber"], ["Mox Jet"])
    chamber = put(s, "Maturation Chamber")
    act(s, "p1", type="set_stops", own=["main1", "end"])
    to_phase(s, "end")
    mana(s, C=4)
    with pytest.raises(ActionError):  # (602.5d)
        act(s, "p1", type="activate_ability", card_id=chamber.id, ability=1)
    to_phase(s, "main1", turn=2)
    mana(s, "p2")
    cast(s, "Mox Jet", pid="p2")
    answer(s)
    assert counters(s, chamber, "charge") == 0
    check(s)


# -- chosen-color mana amounts -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("targets", "attacked"), [((), 0), (("p2", "p2"), 1), (("p2", "p3"), 2)])
def test_beacon_of_kahless_adds_one_of_a_color_per_opponent_you_attacked(cards, targets, attacked):
    s = build3(cards, ["The Beacon of Kahless", "Grizzly Bears", "Centaur Courser"])
    beacon = put(s, "The Beacon of Kahless")
    attackers = [put(s, "Grizzly Bears"), put(s, "Centaur Courser")]
    act(s, "p1", type="set_stops", own=["main1", "main2"])
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": t} for a, t in zip(attackers, targets, strict=False)])
    to_phase(s, "main2", turn=4)
    if attacked:
        act(s, "p1", type="activate_ability", card_id=beacon.id, ability=1, mana_choice="R")
    else:  # (no mana to add: the engine doesn't offer the empty activation, as for any counted mana ability)
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=beacon.id, ability=1, mana_choice="R")
    assert mana_pool(s) == ({"R": attacked} if attacked else {})  # (two attackers at one opponent: one opponent, 508.6)
    check(s)


@pytest.mark.parametrize("theirs", [False, True])
def test_starfleet_academy_counts_creature_types_among_your_non_borg_creatures(cards, theirs):
    s = build(cards, ["Starfleet Academy", "Grizzly Bears", "Centaur Courser", "Warship Flight Crew", "Assault Drone", "Universal Automaton"], ["Goblin Piker"])
    academy = put(s, "Starfleet Academy")
    for name in ("Grizzly Bears", "Centaur Courser", "Warship Flight Crew", "Assault Drone", "Universal Automaton"):
        put(s, name)  # (the Borg and the changeling, which is every creature type and so a Borg too (702.73a), aren't counted)
    if theirs:
        put(s, "Goblin Piker", "p2")  # (an opponent's Goblin Warrior: not yours)
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=academy.id, ability=1, mana_choice="G")
    assert mana_pool(s) == {"G": 5}  # Bear, Centaur, Warrior, Klingon, Pilot
    check(s)
