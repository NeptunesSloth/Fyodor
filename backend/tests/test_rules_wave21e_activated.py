"""Wave 21E: activated-ability long tail, researched against CR 2026-09-25.

* 601.2c / 602.2b: "Choose target opponent who has more life than you do as you activate this ability" (the Keepers): the
  condition is judged only as the target is chosen; 608.2b on resolution asks only that it is still an opponent.
* 105.3, 613.1e: "becomes the color or colors of your choice until end of turn" (one or more colors, chosen as it resolves) and
  "becomes blue in addition to its other colors" (the color is added); no duration: the rest of the game (611.2a).
* 508.1d: "Target creature an opponent controls attacks you this turn if able" is a requirement to attack that player.
* 510.1a: "assigns combat damage equal to its toughness rather than its power this turn".
* "Activate only if you own a card in exile" (108.3: owner, whichever exile zone it is in).

Every scenario uses the cards' current Oracle text (tests/fixtures/wave21e_cards.json, from data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import combat_rules, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import ch, drive, game, mana, put, roundtrip

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave21e_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t21e", number=f"E{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": []}).level == "FULL", name


def unready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0  # (there since before the turn: no summoning sickness)


def activate(s, c, **kw):
    i = next(a.index for a in ch(s, c).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=i, **kw)


def test_keeper_of_the_flame_needs_an_opponent_with_more_life_as_it_is_activated(cards):
    s = game(cards, ["Keeper of the Flame"])
    keeper = put(s, "Keeper of the Flame")
    unready(s, keeper)
    mana(s, R=2)
    with pytest.raises(ActionError):  # (equal life: there is no legal target)
        activate(s, keeper, targets=["p2"])
    act(s, "p1", type="set_life", player="p1", value=30)
    activate(s, keeper, targets=["p2"])
    drive(s)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_scuttlemutt_chooses_one_or_more_colors(cards):
    s = game(cards, ["Scuttlemutt"], bob=["Scuttlemutt"])
    mutt = put(s, "Scuttlemutt")
    victim = put(s, "Scuttlemutt", pid="p2")
    unready(s, mutt)
    activate(s, mutt, targets=[victim.id])
    drive(s, lambda d: ["Blue", "Red"] if d.kind == "choose_cards" else None)
    assert ch(s, victim).colors == {"U", "R"}
    roundtrip(s)


def test_alchors_tomb_color_lasts_and_indigo_faerie_adds_a_color(cards):
    s = game(cards, ["Alchor's Tomb", "Indigo Faerie"])
    tomb = put(s, "Alchor's Tomb")
    faerie = put(s, "Indigo Faerie")
    unready(s, tomb, faerie)
    mana(s, C=2)
    activate(s, tomb, targets=[faerie.id])
    drive(s, lambda d: ["Green"])
    assert ch(s, faerie).colors == {"G"}
    mana(s, U=1)
    activate(s, faerie, targets=[faerie.id])
    drive(s)
    assert ch(s, faerie).colors == {"G", "U"}
    roundtrip(s)


def test_alluring_siren_makes_the_creature_attack_its_controllers_opponent(cards):
    s = game(cards, ["Alluring Siren"], bob=["Scuttlemutt"])
    siren = put(s, "Alluring Siren")
    victim = put(s, "Scuttlemutt", pid="p2")
    unready(s, siren)
    activate(s, siren, targets=[victim.id])
    drive(s)
    assert combat_rules.attack_players(ch(s, victim)) == {"p1"}
    roundtrip(s)


def test_plagon_assigns_toughness_and_dreadlight_needs_an_exiled_card(cards):
    s = game(cards, ["Plagon, Lord of the Beach", "Dreadlight Monstrosity"])
    plagon = put(s, "Plagon, Lord of the Beach")
    dread = put(s, "Dreadlight Monstrosity")
    unready(s, plagon, dread)
    mana(s, W=1)
    activate(s, plagon, targets=[plagon.id])
    drive(s)
    assert "assign_toughness" in ch(s, plagon).imposed
    mana(s, U=2, C=3)
    with pytest.raises(ActionError):  # (no card of Alice's in exile)
        activate(s, dread)
    put(s, "Forest", "exile")
    activate(s, dread)
    drive(s)
    assert "cant_be_blocked" in ch(s, dread).imposed
    roundtrip(s)
