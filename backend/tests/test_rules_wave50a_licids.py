"""Wave 50A: the Licids (CR 2026-09-25), real Oracle text (tests/fixtures/wave50a_licids_cards.json, from data/cards.sqlite). Every scenario checks the replay and a
save and a load.

* "{W}, {T}: This creature loses this ability and becomes an Aura enchantment with enchant creature. Attach it to target creature. You may pay {W} to end this
  effect." - one continuous effect without a duration (611.2a): the Licid is an Aura enchantment, not a creature (613.1d, 205.1a; its creature type goes with it),
  loses that activated ability only (613.1f) and has enchant creature (702.5); it is attached to the target (701.3, 303.4).
* 116.2c: paying to end the effect is a special action any time its controller has priority; it doesn't use the stack. The Licid is a creature again and, as a
  creature, becomes unattached (704.5p); an Aura whose creature is gone goes to the graveyard (704.5m).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ability, ask, attack, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, check, life, mana, pt, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50a_licids_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50a", number=f"L{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
LICIDS = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def game(cards, name, extra=(), theirs=()):
    """Alice has the Licid and a Grizzly Bears, Bob a Grizzly Bears; all have been on the table since the turn began. Alice has priority in her main phase."""
    s = build(cards, [name, "Grizzly Bears", *extra], ["Grizzly Bears", *theirs])
    licid, mine, theirs = put(s, name), put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    next_turn(s)
    return s, licid, mine, theirs


def attach(s, licid, host, **pool):
    """Activate the Licid's ability targeting ``host`` and let it resolve."""
    mana(s, **pool)
    act(s, "p1", type="activate_ability", card_id=licid.id, ability=ability(s, licid.name), targets=[host.id])
    settle(s)


def test_the_twelve_are_full(cards):
    assert len(LICIDS) == 12
    for name in LICIDS:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_calming_licid_becomes_an_aura_on_the_creature_and_it_cannot_attack(cards):
    s, licid, mine, theirs = game(cards, "Calming Licid")
    attach(s, licid, mine, W=1)
    now = ch(s, licid)
    assert (now.types, now.subtypes) == (frozenset({"Enchantment"}), frozenset({"Aura"}))  # 613.1d: not a creature, and Licid went with the creature type
    assert s.state.cards[licid.id].attached_to == mine.id and s.state.cards[licid.id].zone == "p1:battlefield"
    assert not any(a.kind == "activated" for a in now.abilities)  # 613.1f: it lost that ability
    assert "enchant creature." in {a.text.lower() for a in now.abilities}
    with pytest.raises(ActionError):  # (the ability is gone: no second activation)
        act(s, "p1", type="activate_ability", card_id=licid.id, ability=0, targets=[theirs.id])
    stops(s)
    with pytest.raises(ActionError):  # Enchanted creature can't attack
        attack(s, mine)
    check(s)
    assert ch(s, mine).imposed and "cant_attack" in ch(s, mine).imposed


def test_paying_to_end_the_effect_is_a_special_action_and_the_licid_is_a_creature_again(cards):
    s, licid, mine, theirs = game(cards, "Calming Licid", theirs=["Lightning Bolt"])
    attach(s, licid, mine, W=1)
    assert [m.text for m in s.state.cards[licid.id].effects] == ["until its controller pays {W} to end this effect"]  # (the table marker)
    stops(s)
    act(s, "p1", type="pass_priority")  # Bob gets priority and casts Lightning Bolt at Alice's Grizzly Bears: Alice has priority with it on the stack
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[mine.id])
    assert s.state.zones["stack"] and s.state.rules.priority == "p1"  # a special action doesn't use the stack and works any time its player has priority (116.2c)
    with pytest.raises(ActionError):  # {W} is the cost
        act(s, "p1", type="end_effect", card_id=licid.id)
    mana(s, W=1)
    with pytest.raises(ActionError):  # only the effect's player
        act(s, "p2", type="end_effect", card_id=licid.id)
    act(s, "p1", type="end_effect", card_id=licid.id)
    assert len(s.state.zones["stack"]) == 1  # (it did not go on the stack)
    now = ch(s, licid)
    assert now.is_creature and "Licid" in now.subtypes and "Aura" not in now.subtypes
    assert s.state.cards[licid.id].attached_to is None and s.state.cards[licid.id].zone == "p1:battlefield"  # 704.5p: unattached, still here
    assert any(a.kind == "activated" and "loses this ability" in a.text for a in now.abilities)
    assert not ch(s, mine).imposed and not s.state.cards[licid.id].effects and s.state.cards[licid.id].tapped
    settle(s)
    check(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="end_effect", card_id=licid.id)  # nothing left to end


@pytest.mark.parametrize(("name", "pay", "end", "keyword"), [("Corrupting Licid", {"B": 1}, {"B": 1}, "fear"), ("Gliding Licid", {"U": 1}, {"U": 1}, "flying"),
                                                             ("Enraging Licid", {"R": 1}, {"R": 1}, "haste"),
                                                             ("Quickening Licid", {"W": 1, "C": 1}, {"W": 1}, "first strike")])
def test_a_licid_that_grants_a_keyword_gives_it_to_the_enchanted_creature_only_while_attached(cards, name, pay, end, keyword):
    s, licid, mine, theirs = game(cards, name)
    assert keyword not in ch(s, mine).keywords
    attach(s, licid, mine, **pay)
    assert keyword in ch(s, mine).keywords and keyword not in ch(s, theirs).keywords
    mana(s, **end)
    act(s, "p1", type="end_effect", card_id=licid.id)
    assert keyword not in ch(s, mine).keywords and ch(s, licid).is_creature
    check(s)


def test_transmogrifying_licid_is_an_enchantment_only_and_gives_plus_one_and_the_artifact_type(cards):
    s, licid, mine, theirs = game(cards, "Transmogrifying Licid")
    assert ch(s, licid).types == {"Artifact", "Creature"}
    attach(s, licid, mine, C=1)
    assert ch(s, licid).types == {"Enchantment"}  # 613.1d, 205.1a: neither a creature nor an artifact (ruling 2013-09-20)
    assert pt(s, "Grizzly Bears") == (3, 3) and "Artifact" in ch(s, mine).types and "Creature" in ch(s, mine).types
    mana(s, C=1)
    act(s, "p1", type="end_effect", card_id=licid.id)
    assert ch(s, licid).types == {"Artifact", "Creature"} and "Licid" in ch(s, licid).subtypes
    assert pt(s, "Grizzly Bears") == (2, 2) and "Artifact" not in ch(s, mine).types
    check(s)


def test_the_enchanted_creature_dying_puts_the_aura_licid_into_the_graveyard(cards):
    s, licid, mine, theirs = game(cards, "Calming Licid", theirs=["Lightning Bolt"])
    attach(s, licid, mine, W=1)
    stops(s)
    act(s, "p1", type="pass_priority")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[mine.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Calming Licid") == "p1:graveyard"  # 704.5m: an Aura attached to nothing
    check(s)


def test_a_licid_on_a_permanent_that_was_only_a_creature_for_a_turn_goes_to_the_graveyard_when_that_ends(cards):
    s, licid, mine, theirs = game(cards, "Calming Licid", ["Mutavault"])
    vault = put(s, "Mutavault")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=ability(s, "Mutavault", contains="becomes"))
    settle(s)
    attach(s, licid, vault, W=1)
    assert s.state.cards[licid.id].attached_to == vault.id
    next_turn(s)  # the end of the turn: it is no creature, so the Aura is attached to an illegal object (ruling 2004-10-04, 704.5m)
    assert zone_of(s, "Mutavault") == "p1:battlefield" and zone_of(s, "Calming Licid") == "p1:graveyard"
    check(s)


def test_a_target_that_is_gone_means_the_ability_does_nothing_and_the_licid_stays_a_creature(cards):
    s, licid, mine, theirs = game(cards, "Calming Licid", theirs=["Lightning Bolt"])
    stops(s)
    mana(s, W=1)
    act(s, "p1", type="activate_ability", card_id=licid.id, ability=0, targets=[mine.id])
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[mine.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Calming Licid") == "p1:battlefield"  # 608.2b
    assert ch(s, licid).is_creature and any(a.kind == "activated" for a in ch(s, licid).abilities) and s.state.cards[licid.id].attached_to is None
    check(s)


def test_a_licid_that_targets_itself_cannot_enchant_itself(cards):
    s, licid, mine, theirs = game(cards, "Calming Licid")
    attach(s, licid, licid, W=1)
    assert zone_of(s, "Calming Licid") == "p1:graveyard"  # 303.4d, 701.3b, 704.5m
    check(s)


def test_the_effects_of_a_licid_come_back_after_a_save_and_a_load_and_it_can_be_ended_there(cards):
    s, licid, mine, theirs = game(cards, "Calming Licid")
    attach(s, licid, theirs, W=1)
    s2 = reloaded(s)
    assert s2.state.cards[licid.id].attached_to == theirs.id and "Aura" in ch(s2, licid).subtypes and "cant_attack" in ch(s2, theirs).imposed
    assert s2.view("p1")["rules"]["stats"][licid.id]["end_cost"] == "{W}"
    assert "end_cost" not in s2.view("p2")["rules"]["stats"].get(licid.id, {}) and "end_cost" not in s2.view(SPECTATOR)["rules"]["stats"].get(licid.id, {})
    mana(s2, W=1)
    act(s2, "p1", type="end_effect", card_id=licid.id)
    assert ch(s2, licid).is_creature and s2.state.cards[licid.id].attached_to is None and "end_cost" not in s2.view("p1")["rules"]["stats"].get(licid.id, {})
    check(s2)


def test_the_cost_waits_for_the_players_own_mana_taps_and_nothing_is_paid_before(cards):
    s, licid, mine, theirs = game(cards, "Nurturing Licid")
    attach(s, licid, mine, G=1)
    forest = put(s, "Forest")
    act(s, "p1", type="set_prefs", payment="self")
    act(s, "p1", type="end_effect", card_id=licid.id)
    assert s.state.rules.decision is not None and "Aura" in ch(s, licid).subtypes and not s.state.cards[forest.id].tapped  # (asked to tap: nothing is paid yet)
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    assert s.state.rules.decision is None and ch(s, licid).is_creature and s.state.cards[forest.id].tapped
    check(s)


def test_after_the_effect_ends_the_licid_can_do_it_again_and_without_a_host_its_other_lines_do_nothing(cards):
    s, licid, mine, theirs = game(cards, "Nurturing Licid")
    regenerate = ability(s, "Nurturing Licid", contains="Regenerate")
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=licid.id, ability=regenerate)  # "Regenerate enchanted creature": it enchants nothing
    settle(s)
    assert not s.state.rules.regen_shields
    attach(s, licid, mine, G=1)
    mana(s, G=1)
    act(s, "p1", type="end_effect", card_id=licid.id)
    assert not [e for e in s.state.rules.effects if e.end_cost]
    next_turn(s)
    attach(s, licid, theirs, G=1)  # untapped again: the ability is back and starts a new effect
    assert s.state.cards[licid.id].attached_to == theirs.id and len([e for e in s.state.rules.effects if e.end_cost]) == 2  # (a new effect: the first one is gone)
    check(s)


def test_dominating_licid_controls_the_enchanted_creature_until_the_effect_ends(cards):
    s, licid, mine, theirs = game(cards, "Dominating Licid")
    attach(s, licid, theirs, U=3)
    assert s.state.cards[theirs.id].controller == "p1"
    mana(s, U=1)
    act(s, "p1", type="end_effect", card_id=licid.id)
    assert s.state.cards[theirs.id].controller == "p2" and ch(s, licid).is_creature
    check(s)


def test_convulsing_licid_stops_the_enchanted_creature_from_blocking(cards):
    s, licid, mine, theirs = game(cards, "Convulsing Licid")
    attach(s, licid, theirs, R=1)
    stops(s)
    attack(s, mine)
    assert ask(s).kind == "declare_blockers"
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": mine.id}])
    check(s)


def test_tempting_licid_makes_every_creature_able_to_block_the_enchanted_creature_do_so(cards):
    s, licid, mine, theirs = game(cards, "Tempting Licid")
    attach(s, licid, mine, G=1)
    stops(s)
    attack(s, mine)
    assert ask(s).kind == "declare_blockers"
    with pytest.raises(ActionError):  # Bob's Grizzly Bears must block
        act(s, "p2", type="declare_blockers", blocks=[])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": mine.id}])
    check(s)


def test_stinging_licid_deals_two_damage_to_the_controller_of_the_enchanted_creature_when_it_becomes_tapped(cards):
    s, licid, mine, theirs = game(cards, "Stinging Licid")
    attach(s, licid, mine, U=1, C=1)
    stops(s)
    before = life(s)
    attack(s, mine)  # tapped by attacking (508.1f)
    settle(s)
    assert life(s) == before - 2
    check(s)


def test_leeching_licid_deals_one_damage_in_the_upkeep_of_the_enchanted_creatures_controller(cards):
    s, licid, mine, theirs = game(cards, "Leeching Licid")
    attach(s, licid, theirs, B=1)
    before = life(s, "p2")
    stops(s)
    to_phase(s, "upkeep", turn=s.state.turn.number + 1)
    settle(s)
    assert life(s, "p2") == before - 1 and life(s) == 40
    check(s)


def test_nurturing_licid_regenerates_the_enchanted_creature(cards):
    s, licid, mine, theirs = game(cards, "Nurturing Licid", theirs=["Lightning Bolt"])
    attach(s, licid, mine, G=1)
    stops(s)
    act(s, "p1", type="pass_priority")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[mine.id])
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=licid.id, ability=ability(s, "Nurturing Licid", contains="Regenerate"))
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and s.state.cards[mine.id].tapped and zone_of(s, "Nurturing Licid") == "p1:battlefield"
    check(s)
