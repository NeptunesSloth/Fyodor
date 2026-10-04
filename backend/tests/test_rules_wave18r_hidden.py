"""Review of system 18A (hidden exile and face-down objects), real Oracle text (CR 2026-09-25).

* 708.2a / 305.6: a permanent face down as a "Forest land" (Yedora) has the Forest's intrinsic mana ability: it taps for {G}.
* 708.5: a face-down commander isn't located for players who can't look at it (the commander list would name its zone).
* 708.5 / 108.4: a face-down permanent that changes control is looked at by its new controller, not by its owner.
* 708.9 / 702.143f: a player who leaves the game reveals their face-down permanents and foretold cards; at the end of the game
  everyone's are revealed.
"""

from __future__ import annotations

import pytest

from app.game.visibility import SPECTATOR
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip
from tests.test_rules_wave18a_down import EXTRA, chars_of, mana, unseen_by


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_a_face_down_forest_land_taps_for_green(cards):
    s = build(cards, p1=("Yedora, Grave Gardener", "Ambush Viper", "Lightning Bolt"))
    put(s, "Yedora, Grave Gardener", "battlefield")
    viper = put(s, "Ambush Viper", "battlefield")
    vid = viper.id
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[vid])
    answer(s)
    land = s.state.cards[vid]
    assert land.face_down and land.face_down_as == "Forest land"
    tap = next(a for a in chars_of(s, land).abilities if a.text.startswith("{T}: Add {G}"))
    act(s, "p1", type="activate_ability", card_id=vid, ability=tap.index)
    assert s.state.cards[vid].tapped and s.state.cards[vid].face_down  # a mana ability: it stays face down (no reveal)
    assert s.state.players["p1"].mana.get("G") == 1
    assert s.view("p2")["cards"][vid].get("face_down_as") == "Forest land"  # 708.2a: public
    assert unseen_by(s, land, "p2", SPECTATOR)
    roundtrip(s)


def test_a_face_down_commander_is_not_located_for_others(cards):
    s = build(cards)
    krenko = find(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="manifest")

    def zone(viewer):
        return next(c for p in s.view(viewer)["players"] if p["id"] == "p1" for c in p["commanders"])["zone"]

    assert zone("p1") == "p1:battlefield"
    assert zone("p2") is None and zone(SPECTATOR) is None
    act(s, "p1", type="face_down", card_ids=[krenko.id], face_down=False)
    assert zone("p2") == "p1:battlefield"
    replay_matches(s)


def test_a_face_down_permanent_that_changes_control_is_seen_by_its_new_controller(cards):
    s = build(cards, p1=("Ambush Viper",))
    viper = put(s, "Ambush Viper", "hand")
    act(s, "p1", type="move", card_ids=[viper.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="manifest")
    act(s, "p1", type="move", card_ids=[viper.id], to={"player": "p2", "zone": "battlefield"})  # a control change (same object)
    c = s.state.cards[viper.id]
    assert c.face_down and c.controller == "p2" and c.face_down_kind == "manifest"
    assert not unseen_by(s, c, "p2") and unseen_by(s, c, "p1", SPECTATOR)  # 708.5: its controller looks, not its owner
    roundtrip(s)


def test_leaving_the_game_reveals_face_down_permanents_and_foretold_cards(cards):
    s = build(cards, p1=("Ambush Viper",), p2=("Grizzly Bears", "Giant Growth"))
    viper = put(s, "Ambush Viper", "hand")
    act(s, "p1", type="move", card_ids=[viper.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="manifest")
    bears = put(s, "Grizzly Bears", "hand", pid="p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"}, face_down=True, face_down_kind="manifest")
    saw = put(s, "Giant Growth", "foretell", pid="p2")
    assert unseen_by(s, bears, "p1", SPECTATOR) and unseen_by(s, saw, "p1", SPECTATOR) and unseen_by(s, viper, "p2", SPECTATOR)
    act(s, "p2", type="concede")  # 708.9 / 702.143f: Bob leaves; then Alice is the last player and the game ends
    assert s.state.rules.winner == "p1"
    for c in (bears, saw, viper):
        assert not unseen_by(s, c, "p1") and not unseen_by(s, c, "p2") and not unseen_by(s, c, SPECTATOR)
    roundtrip(s)
