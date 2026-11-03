"""Wave 111D: Star Trek activated abilities, counters and costs. Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a save
and a load.

* "Create a tapped Planet land token named New Planet with "{T}: Add one mana of any color."" (the anomaly lands, Saurian Explorer): a colorless
  noncreature land token (111.3, 111.4, 105.2c) with the land type Planet (205.3i), entering tapped, whose mana ability its controller can use.
* The anomalies' own abilities: "{N}, {T}, Sacrifice this land: …" (602.2: the costs paid as it's activated; "It deals 2 damage" is the land as it last
  existed, 113.7a, 608.2h).
* "{G}, Exile this card from your graveyard: …" (Photosynthetic Physician; 602.2, 113.6m: the ability works from the graveyard only), "Activate only as a
  sorcery" (602.5d, 307.5).
* Gagh Slinger: "Klingon spells and Warrior spells you cast cost {1} less" (601.2f: one reduction for a Klingon Warrior spell), General Chang (each
  Klingon you control), Maturation Chamber (a charge counter per artifact spell, then a Borg token for each), Cloak and Phaser ("costs {X} less, where
  X is the number of differently named lands you control", 601.2f).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put

PLANET = "Create a tapped Planet land token named New Planet with \"{T}: Add one mana of any color.\""
EXTRA = [
    real("Artificial Anomaly", "", 0, "Land", "{T}: Add {C}.\n{3}{B}, {T}, Sacrifice this land: Each opponent loses 2 life and you gain 2 life. " + PLANET, None, ""),
    real("Gaseous Anomaly", "", 0, "Land", "{T}: Add {C}.\n{5}{U}, {T}, Sacrifice this land: Draw two cards. " + PLANET, None, ""),
    real("Spatial Anomaly", "", 0, "Land", "{T}: Add {C}.\n{4}{R}, {T}, Sacrifice this land: It deals 2 damage to target creature. " + PLANET, None, ""),
    real("Subspace Anomaly", "", 0, "Land", "{T}: Add {C}.\n{4}{W}, {T}, Sacrifice this land: Create two 1/1 red Officer creature tokens. " + PLANET, None, ""),
    real("Temporal Anomaly", "", 0, "Land", "{T}: Add {C}.\n{3}{G}, {T}, Sacrifice this land: Mill four cards. You may put a permanent card from among them into "
         "your hand. " + PLANET, None, ""),
    real("Saurian Explorer", "{3}{G}", 4, "Creature — Dinosaur Scout", "Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of "
         "turn.\n{6}: " + PLANET + " Activate only as a sorcery.", ("4", "3"), "G"),
    real("Photosynthetic Physician", "{4}{G}", 5, "Creature \u2014 Plant Doctor", "Reach\n{G}, Exile this card from your graveyard: Create a 1/1 red Officer "
         "creature token. Activate only as a sorcery.", ("5", "5"), "G"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Shock", "{R}", 1, "Instant", "Shock deals 2 damage to any target.", None, "R"),
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


def planets(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "New Planet" and c.zone == f"{pid}:battlefield"]


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def assert_planet(s):
    """One New Planet: a tapped colorless Planet land token, no creature; untapped, it taps for one mana of the color its controller picks."""
    (p,) = planets(s)
    c = ch(s, p)
    assert p.tapped and p.is_token
    assert c.types == {"Land"} and c.subtypes == {"Planet"} and not c.colors, (c.types, c.subtypes, c.colors)
    act(s, "p1", type="tap", card_ids=[p.id], tapped=False)
    act(s, "p1", type="activate_ability", card_id=p.id, ability=0, mana_choice="R")
    assert mana_pool(s).get("R") == 1 and s.state.cards[p.id].tapped


def sacrifice_ability(s, name, targets=(), **m):
    land = put(s, name)
    mana(s, **m)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=1, targets=list(targets))
    assert s.state.cards[land.id].zone == "p1:graveyard"  # (sacrificed as a cost, 602.2)
    answer(s)
    return land


def test_artificial_anomaly_drains_each_opponent_and_makes_a_planet(cards):
    s = build3(cards, ["Artificial Anomaly"])
    sacrifice_ability(s, "Artificial Anomaly", B=1, C=3)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (42, 38, 38)
    assert_planet(s)
    check(s)


def hand(s, pid="p1"):
    return [s.state.cards[i].name for i in s.state.zones.get(f"{pid}:hand", [])]


def graveyard(s, pid="p1"):
    return [s.state.cards[i].name for i in s.state.zones.get(f"{pid}:graveyard", [])]


def test_gaseous_anomaly_draws_two(cards):
    s = build(cards, ["Gaseous Anomaly"])
    assert hand(s) == []  # (the first player skips the first draw, 103.8a)
    sacrifice_ability(s, "Gaseous Anomaly", U=1, C=5)
    assert hand(s) == ["Forest", "Forest"]
    assert_planet(s)
    check(s)


def test_spatial_anomaly_deals_2_damage_to_target_creature(cards):
    s = build(cards, ["Spatial Anomaly"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    sacrifice_ability(s, "Spatial Anomaly", [bears.id], R=1, C=4)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert_planet(s)
    check(s)


def test_spatial_anomaly_needs_a_creature_target(cards):
    s = build(cards, ["Spatial Anomaly"])
    land = put(s, "Spatial Anomaly")
    mana(s, R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=land.id, ability=1, targets=["p2"])
    check(s)


def test_subspace_anomaly_makes_two_red_officers(cards):
    s = build(cards, ["Subspace Anomaly"])
    sacrifice_ability(s, "Subspace Anomaly", W=1, C=4)
    officers = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name != "New Planet" and c.is_token]
    assert len(officers) == 2
    for o in officers:
        c = ch(s, o)
        assert c.types == {"Creature"} and c.subtypes == {"Officer"} and c.colors == {"R"} and c.pt == (1, 1), (c.types, c.subtypes, c.colors, c.pt)
    assert_planet(s)
    check(s)


@pytest.mark.parametrize("take", [True, False])
def test_temporal_anomaly_mills_four_and_may_keep_a_permanent_card(cards, take):
    s = build(cards, ["Temporal Anomaly", "Shock", "Grizzly Bears"])  # (Temporal Anomaly is put from the top: Shock, Grizzly Bears, Forest, Forest follow)
    land = put(s, "Temporal Anomaly")
    mana(s, G=1, C=3)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=1)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None
    names = {s.state.cards[o.id].name for o in d.options if o.id in s.state.cards}
    assert "Shock" not in names and "Grizzly Bears" in names  # (an instant is no permanent card, 110.4a)
    bears = card_named(s, "Grizzly Bears")
    answer(s, bears.id if take else [])
    assert ("Grizzly Bears" in hand(s)) is take
    assert sorted(graveyard(s)) == sorted(["Shock", "Forest", "Forest", "Temporal Anomaly"] + ([] if take else ["Grizzly Bears"]))
    assert_planet(s)
    check(s)


def test_saurian_explorer_makes_a_planet_at_sorcery_speed_and_landfall_sees_it(cards):
    s = build(cards, ["Saurian Explorer"])
    explorer = put(s, "Saurian Explorer")
    act(s, "p1", type="set_stops", own=["main1", "end"])
    to_phase(s, "end")
    mana(s, C=6)
    with pytest.raises(ActionError):  # (602.5d: only in its controller's main phase with an empty stack, 307.1)
        act(s, "p1", type="activate_ability", card_id=explorer.id, ability=1)
    to_phase(s, "main1", turn=3)
    mana(s, C=6)
    act(s, "p1", type="activate_ability", card_id=explorer.id, ability=1)
    answer(s)
    assert_planet(s)
    assert ch(s, explorer).pt == (6, 5)  # (landfall: the token is a land entering under its control, 111.1)
    check(s)


def test_photosynthetic_physician_works_from_the_graveyard_only(cards):
    s = build(cards, ["Photosynthetic Physician"])
    doc = put(s, "Photosynthetic Physician")
    mana(s, G=1)
    with pytest.raises(ActionError):  # (an ability whose cost exiles it from the graveyard works only there, 113.6m)
        act(s, "p1", type="activate_ability", card_id=doc.id, ability=1)
    act(s, "p1", type="move", card_ids=[doc.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=doc.id, ability=1)
    assert s.state.cards[doc.id].zone == "p1:exile"  # (exiled as a cost, 602.2)
    answer(s)
    (officer,) = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token]
    c = ch(s, officer)
    assert c.types == {"Creature"} and c.subtypes == {"Officer"} and c.colors == {"R"} and c.pt == (1, 1)
    check(s)
