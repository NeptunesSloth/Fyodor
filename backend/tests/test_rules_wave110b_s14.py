"""Wave 110B session 14 (real Oracle text in tests/fixtures/wave110b_cards.json).

* Tranquil Frillback: 107.1b pay {G} up to three times, 603.12 the reflexive ability, 700.2b "choose up to that many" modes = the times paid.
"""
from __future__ import annotations

import pytest

from app.rules import coverage, sba
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import (
    build,
    card_named,
    ch,
    check,
    drive,
    life,
    mana,
    put,
    settle,
    to_hand,
)


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_wave12a_counters_keywords import real
    from tests.wave110b_kit import EXTRA

    settings.ensure_dirs()
    otters = [real(f"Test Otter{x}", "{1}{G}", 2, "Creature — Otter", "", ("1", "1"), "G") for x in ("", " B")]
    lands = [real("City of Brass", "", 0, "Land", "Whenever this land becomes tapped, it deals 1 damage to you.\n{T}: Add one mana of any color."),
             real("Reflecting Pool", "", 0, "Land", "{T}: Add one mana of any type that a land you control could produce.")]
    build_database([*fixture_cards(), *EXTRA, *otters, *lands], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Tranquil Frillback")).level == "FULL"


def frillback(cards, G, times, modes):
    """Cast it with {2}{G} + ``G`` more green; pay ``times``; choose the mode indexes ``modes`` (artifact and enchantment targets exist)."""
    s = build(cards, ["Tranquil Frillback", "Sol Ring"], ["Grizzly Bears"], forests=30)
    ring = put(s, "Sol Ring")
    to_hand(s, "Tranquil Frillback")
    mana(s, G=3 + G)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Tranquil Frillback").id)
    seen = []

    def answer(d):
        seen.append(d.prompt)
        if "how many times" in d.prompt:
            return [f"x:{times}"] if times else ["decline"]
        if d.kind == "choose_cards" and "mode" in d.prompt:
            return [f"{i}:0" for i in modes]
        return None
    drive(s, answer)
    return s, ring, seen


def test_pay_twice_two_modes(cards):
    s, ring, seen = frillback(cards, 2, 2, [0, 2])
    assert s.state.cards[ring.id].zone.endswith("graveyard") and life(s, "p1") == 44  # destroy artifact, gain 4 (40 + 4)
    assert any("up to two" in p for p in seen)
    check(s)


def test_pay_once_limits_to_one_mode(cards):
    s, ring, seen = frillback(cards, 3, 1, [2])
    assert s.state.cards[ring.id].zone.endswith("battlefield") and life(s, "p1") == 44
    assert any("up to one" in p for p in seen)
    check(s)


def test_pay_nothing_no_modes(cards):
    s, ring, _ = frillback(cards, 3, 0, [])
    assert s.state.cards[ring.id].zone.endswith("battlefield") and life(s, "p1") == 40
    check(s)


def test_hawkeye_attack_pays_once_for_one_mode(cards):
    """Hawkeye (same "pay {1} up to three times ... choose up to that many" with ability word and mode labels): attacking taps it (603.2)."""
    assert coverage.of_card_data(cards.resolve("Hawkeye, Master Marksman")).level == "FULL"
    from tests.wave110b_kit import attack

    s = build(cards, ["Hawkeye, Master Marksman"], ["Grizzly Bears"], forests=30)
    hawk = put(s, "Hawkeye, Master Marksman")
    mana(s, G=3)

    def answer(d):
        if "how many times" in d.prompt:
            return ["x:1"]
        if d.kind == "choose_cards" and "mode" in d.prompt:
            return ["1:0"]
        return None
    attack(s, hawk)
    drive(s, answer)
    assert life(s, "p2") == 38  # Explosive: 2 damage to target player (before combat damage)
    check(s)


@pytest.mark.parametrize("sacrifice", [True, False])
def test_dragon_broodmother_token_devours(cards, sacrifice):
    """702.82a: the Dragon token created at each upkeep has devour 2: sacrificing one creature gives it two +1/+1 counters (a 3/3 flier)."""
    assert coverage.of_card_data(cards.resolve("Dragon Broodmother")).level == "FULL"
    s = build(cards, ["Dragon Broodmother", *["Grizzly Bears"] * 20], ["Grizzly Bears"] * 20, forests=30)
    put(s, "Dragon Broodmother")
    bears = put(s, "Grizzly Bears")
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and d.kind == "choose_cards" and "Discard" in d.prompt:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif d is not None:
            assert "devour 2" in d.prompt and bears.id in [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id] if sacrifice else ["done"])
            d = s.state.rules.decision  # asked again until "done" (702.82a: any number)
            if sacrifice:
                assert d is not None and "devour 2" in d.prompt and bears.id not in [o.id for o in d.options]
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["done"])
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    else:
        raise AssertionError("no devour prompt")
    drive(s)
    dragons = [c for c in s.state.cards.values() if c.token and c.token.name == "Dragon"]
    assert len(dragons) == 1
    t = dragons[0]
    assert (sba.power(t, ch(s, t)), sba.toughness(t, ch(s, t))) == ((3, 3) if sacrifice else (1, 1))
    assert s.state.cards[bears.id].zone.endswith("graveyard") == sacrifice
    check(s)


def senu_game(cards, zone, legend="Krenko, Mob Boss", blocker=False):
    from tests.wave110b_kit import attack, through_combat

    s = build(cards, ["Senu, Keen-Eyed Protector", legend, "Grizzly Bears"], ["Grizzly Bears"], forests=30)
    senu = card_named(s, "Senu, Keen-Eyed Protector")
    act(s, "p1", type="move", card_ids=[senu.id], to={"player": "p1", "zone": zone})
    lord = put(s, legend)
    bears = put(s, "Grizzly Bears", "p2") if blocker else None
    attack(s, lord)
    through_combat(s, blocks=[(bears, lord)] if blocker else None)
    return s, senu


def test_senu_enters_attacking_from_exile_when_unblocked(cards):
    """603.2 / 509.3g / 508.4: Krenko attacks unblocked; Senu (exiled) joins the attack, so both connect: 3 + 2 damage."""
    assert coverage.of_card_data(cards.resolve("Senu, Keen-Eyed Protector")).level == "FULL"
    s, senu = senu_game(cards, "exile")
    assert s.state.cards[senu.id].zone.endswith("battlefield") and life(s, "p2") == 35
    check(s)


@pytest.mark.parametrize("zone,blocker", [("hand", False), ("graveyard", False), ("exile", True)])
def test_senu_stays_put_elsewhere_or_when_blocked(cards, zone, blocker):
    """113.6k: the ability works only from exile; a blocked legendary creature doesn't trigger it (509.3g)."""
    s, senu = senu_game(cards, zone, blocker=blocker)
    assert not s.state.cards[senu.id].zone.endswith("battlefield")
    check(s)


def web_game(cards, tap, lands=("Forest", "Forest", "Mountain", "Island", "Swamp"), ability=0, **kw):
    """Alice has Mana Web; Bob (opponent) has the ``lands`` and taps the first one named ``tap`` for mana."""
    s = build(cards, ["Mana Web"], list(lands), forests=30)
    put(s, "Mana Web")
    ids = {}
    for name in lands:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p2" and c.id not in ids.values())
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
        ids.setdefault(name, c.id)
    to_phase(s, "main1", turn=2)  # Bob's turn: he has priority in his main phase
    act(s, "p2", type="activate_ability", card_id=ids[tap], ability=ability, **kw)
    settle(s)
    return s, {n: s.state.cards[i].tapped for n, i in ids.items()}


def test_mana_web_taps_lands_that_could_produce_the_same_type(cards):
    """Both Forests are tapped (G); the Mountain, Island and Swamp could not produce G. The untouched same-name Forest is the first one found, so check by type."""
    assert coverage.of_card_data(cards.resolve("Mana Web")).level == "FULL"
    s, tapped = web_game(cards, "Forest")
    assert tapped == {"Forest": True, "Mountain": False, "Island": False, "Swamp": False}
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p2" and c.zone.endswith("battlefield")]
    assert len(forests) == 2 and all(c.tapped for c in forests)
    check(s)


def test_mana_web_does_not_touch_its_own_controllers_lands(cards):
    """Only the opponent's tapping triggers it; Alice's own Forests stay untapped when she taps one."""
    s = build(cards, ["Mana Web"], ["Forest"], forests=30)
    put(s, "Mana Web")
    a = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    for c in a:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=a[0].id, ability=0)
    settle(s)
    assert s.state.cards[a[0].id].tapped and not s.state.cards[a[1].id].tapped
    check(s)


def test_mana_web_counts_every_type_a_dual_land_could_produce(cards):
    """Shivan Reef ({C}, or {U} / {R}): tapped for {U}, the Island and the Mountain (and not the Forest or Swamp) are tapped too."""
    s, tapped = web_game(cards, "Shivan Reef", ("Shivan Reef", "Island", "Mountain", "Forest", "Swamp"), ability=1, mana_choice="U")
    assert tapped == {"Shivan Reef": True, "Island": True, "Mountain": True, "Forest": False, "Swamp": False}
    check(s)


def alania(cards, spells, yes=True):
    """Alania in play, Bob with ``Grizzly Bears`` in hand to draw; Alice casts each of ``spells`` ((name, targets)) in order and every decision is answered
    yes / no (the copy keeps its targets). Returns the table and how many cards Bob drew."""
    s = build(cards, ["Alania, Divergent Storm", *[n for n, _ in spells]], ["Grizzly Bears"] * 5, forests=30)
    put(s, "Alania, Divergent Storm")
    hand = len([c for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:hand"])

    def go(d):
        if d.kind == "confirm":
            return ["yes" if yes else "no"]
        return ["keep"] if "keep" in [o.id for o in d.options] else None
    for name, targets in spells:
        mana(s, R=6, G=2, U=2, W=2)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id, targets=list(targets))
        drive(s, go)
    return s, len([c for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:hand"]) - hand


def test_alania_first_instant_copies_and_opponent_draws(cards):
    """603.4: the first instant spell cast this turn triggers it; the opponent draws, the copy (707.10) is a second Lightning Bolt: 3 + 3 damage."""
    assert coverage.of_card_data(cards.resolve("Alania, Divergent Storm")).level == "FULL"
    s, drawn = alania(cards, [("Lightning Bolt", ["p2"])])
    assert life(s, "p2") == 34 and drawn == 1
    check(s)


def test_alania_declined_does_nothing(cards):
    s, drawn = alania(cards, [("Lightning Bolt", ["p2"])], yes=False)
    assert life(s, "p2") == 37 and drawn == 0
    check(s)


def test_alania_second_instant_does_not_trigger(cards):
    """Only the first instant spell: the second Bolt is a single Bolt (3), and Bob draws only for the first."""
    s, drawn = alania(cards, [("Lightning Bolt", ["p2"]), ("Lightning Bolt", ["p2"])])
    assert life(s, "p2") == 31 and drawn == 1
    check(s)


def test_alania_first_sorcery_after_an_instant_triggers(cards):
    """The first sorcery spell counts on its own, whatever instant came before: Bob draws for both."""
    s, drawn = alania(cards, [("Lightning Bolt", ["p2"]), ("Pyroclasm", [])])
    assert drawn == 2
    check(s)


def test_alania_first_otter_other_than_itself(cards):
    """The first Otter spell (not Alania) triggers: the copy of the creature spell makes a second Otter; a second Otter spell doesn't."""
    s, drawn = alania(cards, [("Test Otter", [])])
    assert drawn == 1 and len([c for c in s.state.cards.values() if c.name == "Test Otter" and c.zone.endswith("battlefield")]) == 2
    s, drawn = alania(cards, [("Test Otter", []), ("Test Otter B", [])])
    assert drawn == 1 and len([c for c in s.state.cards.values() if c.name.startswith("Test Otter") and c.zone.endswith("battlefield")]) == 3
    check(s)


def test_alania_other_creature_spells_do_not_trigger(cards):
    s, drawn = alania(cards, [("Grizzly Bears", [])])
    assert drawn == 0
    check(s)


def test_mana_web_reads_commander_identity_land(cards):
    """106.7: Command Tower (Bob's identity W U B G) tapped for G also taps Forest, Island, Swamp but not Mountain (R is outside it)."""
    s, tapped = web_game(cards, "Command Tower", ("Command Tower", "Forest", "Island", "Swamp", "Mountain"), mana_choice="G")
    assert tapped == {"Command Tower": True, "Forest": True, "Island": True, "Swamp": True, "Mountain": False}
    check(s)


def test_mana_web_reads_any_color_and_borrowed_types(cards):
    """City of Brass could produce every color: tapping it for R taps all colored lands; Reflecting Pool (types other lands could produce) is tapped by a Forest."""
    s, tapped = web_game(cards, "City of Brass", ("City of Brass", "Forest", "Mountain", "Island"), ability=1, mana_choice="R")
    assert all(tapped.values())
    s, tapped = web_game(cards, "Forest", ("Forest", "Reflecting Pool", "Mountain"))
    assert tapped["Forest"] and tapped["Reflecting Pool"]
    check(s)
