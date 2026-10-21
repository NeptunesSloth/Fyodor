"""Review of wave 18B (mana provenance and spending restrictions), CR 2026-09-25.

* 107.4f / 119.4: each Phyrexian symbol is paid on its own — the payer pays life for only the symbols mana can't pay.
* 202.3e / 601.2h: "When you spend this mana to cast a spell with mana value 6 or greater" sees the X the spell was cast with.
* K'rrik, Son of Yawgmoth in the tap-your-own-mana mode (the pool plus 2 life per {B}), and not once it has lost its abilities (613.1f).
* 116.2b / 116.2f / 116.2k: turning a permanent face up, suspending and plotting are special actions, not casting a spell or activating an
  ability: mana that may only be spent on those doesn't pay for them.
* Hidden information: whether a source's mana is remembered depends on every card of the game (mana_units.tracking), so the views show
  unrestricted remembered mana as plain mana.

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import mana as M
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, creature, on_field, to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave18b_mana import EXTRA, real, roundtrip, settle, treasure, units

MORE = [
    real("Gilanra, Caller of Wirewood", "{2}{G}", 3, "Legendary Creature — Elf Druid",
         "{T}: Add {G}. When you spend this mana to cast a spell with mana value 6 or greater, draw a card.\n"
         "Partner (You can have two commanders if both have partner.)", ("2", "3"), "G"),
    real("Boommobile", "{2}{R}", 3, "Artifact — Vehicle",
         "When this Vehicle enters, add four mana of any one color. Spend this mana only to activate abilities.\n"
         "Exhaust — {X}{2}{R}: This Vehicle deals X damage to any target. Put a +1/+1 counter on this Vehicle. (Activate each exhaust "
         "ability only once.)\nCrew 2", ("4", "3"), "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *MORE], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_each_phyrexian_symbol_is_paid_on_its_own():
    cost = M.parse_cost("{W/P}{U/P}")
    assert M.solve(cost, {"W": 1}, [], life=40).life == 2  # (the {W} pays {W/P}; 2 life for {U/P}, not 4)
    assert M.solve(cost, {"W": 1}, [], life=3).life == 2  # (and with 3 life it can still be paid)
    assert M.solve(cost, {"U": 1}, [], life=40).life == 2
    assert M.solve(cost, {}, [], life=40).life == 4


def test_gilanras_mana_sees_the_x_of_the_spell(cards):
    s = build(cards, "Gilanra, Caller of Wirewood", "Blaze")
    gilanra = on_field(s, "Gilanra, Caller of Wirewood")
    s.state.rules.controlled_since[gilanra.id].turn = 0
    blaze = to_hand(s, "Blaze")
    mana(s, "p1", R=1, C=4)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=blaze.id, x_value=5, targets=["p2"])  # {X}{R}, X = 5: mana value 6 on the stack
    assert s.state.cards[gilanra.id].tapped
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand  # (Blaze left the hand, the trigger drew a card)
    assert s.state.players["p2"].life == 35
    roundtrip(s)


def test_krrik_in_the_tap_your_own_mana_mode(cards):
    s = build(cards, "K'rrik, Son of Yawgmoth", "Murder")
    on_field(s, "K'rrik, Son of Yawgmoth")
    murder = to_hand(s, "Murder")
    victim = creature(s, "p2", "Bob Bear", "2/2")
    s.state.rules.prefs["p1"].payment = "self"
    mana(s, "p1", C=1, B=1)  # {1}{B}{B}: the pool and 2 life
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[victim.id])
    settle(s)
    assert victim.id not in s.state.cards and s.state.players["p1"].life == 38 and s.state.players["p1"].mana == {}
    roundtrip(s)


def test_krrik_without_its_abilities_gives_no_life_payment(cards):
    s = build(cards, "K'rrik, Son of Yawgmoth", "Murder", "Turn to Frog")
    krrik = on_field(s, "K'rrik, Son of Yawgmoth")
    frog = to_hand(s, "Turn to Frog")
    murder = to_hand(s, "Murder")
    victim = creature(s, "p2", "Bob Bear", "2/2")
    mana(s, "p1", C=1, U=1)
    act(s, "p1", type="cast_spell", card_id=frog.id, targets=[krrik.id])
    settle(s)
    mana(s, "p1", C=1, B=1)
    with pytest.raises(ActionError):  # (613.1f: it lost "For each {B} in a cost, you may pay 2 life …")
        act(s, "p1", type="cast_spell", card_id=murder.id, targets=[victim.id])


def test_mana_only_for_abilities_does_not_turn_a_permanent_face_up(cards):
    s = build(cards, "Boommobile", "Grizzly Bears")
    boom = to_hand(s, "Boommobile")
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=boom.id)
    settle(s)  # (its enters trigger: four mana of one color, only to activate abilities)
    assert len(units(s)) == 4 and s.state.players["p1"].mana == {}
    bears = on_field(s, "Grizzly Bears")
    act(s, "p1", type="face_down", card_ids=[bears.id], face_down=True, kind="manifest")
    with pytest.raises(ActionError):  # (116.2b: a special action, not an activated ability)
        act(s, "p1", type="turn_face_up", card_id=bears.id, method="mana_cost")
    assert s.state.cards[bears.id].face_down and len(units(s)) == 4
    roundtrip(s)


def test_views_show_remembered_mana_as_plain_mana(cards):
    from app.game.views import OMNISCIENT, SPECTATOR, build_view

    def pools(s):
        out = {}
        for v in ("p1", "p2", SPECTATOR):
            p1 = next(p for p in build_view(s.state, v)["players"] if p["id"] == "p1")
            out[v] = (p1["mana"], p1["mana_units"], "mana_seq" in p1)
        return out

    seen = []
    for p2 in ((), ("Smaug, Wicked Worm",)):  # (Smaug, in Bob's library, asks for "mana from a Treasure")
        s = build(cards, "Lightning Bolt", p2=p2)
        t = treasure(s)
        act(s, "p1", type="activate_ability", card_id=t.id, ability=0, mana_choice="R")
        assert units(s) == [("R", None)]  # every known source is retained, independent of hidden cards
        seen.append(pools(s))
        assert next(p for p in build_view(s.state, OMNISCIENT)["players"] if p["id"] == "p1")["mana_units"] == \
            [u.model_dump() for u in s.state.players["p1"].mana_units]
        act(s, "p1", type="add_mana", player="p1", mana={"R": -1})  # (the table tool takes the mana the view shows)
        assert s.state.players["p1"].mana == {} and units(s) == []
    assert seen[0] == seen[1] and seen[0]["p2"] == ({"R": 1}, [], False)




def test_restricted_mana_in_the_pool_pays_before_a_source_is_tapped(cards):
    from tests.test_rules_wave18b_mana import geosurged

    s = geosurged(cards, "Grizzly Bears", "Sol Ring")
    ring = on_field(s, "Sol Ring")
    forest = on_field(s, "Forest")
    s.state.rules.controlled_since[ring.id].turn = 0
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p1", type="cast_spell", card_id=bears.id)  # {1}{G}: the Forest and one restricted {R} (not Sol Ring's {C}{C})
    settle(s)
    assert not s.state.cards[ring.id].tapped and s.state.cards[forest.id].tapped and len(units(s)) == 6
    assert s.state.players["p1"].mana == {}
    roundtrip(s)
