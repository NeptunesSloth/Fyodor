"""Wave 51F: the reanimation Auras (CR 2026-09-25), real Oracle text (tests/fixtures/wave51f_reanimation_auras_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* Animate Dead, Dance of the Dead: "Enchant creature card in a graveyard" - the Aura spell targets a creature card in any graveyard (303.4a, 115.1b) and enters enchanting it
  (608.3c). Its enters trigger ("if it's on the battlefield", 603.4) swaps the enchant ability, puts the card onto the battlefield under the Aura controller's control and attaches
  the Aura to it; it creates a delayed trigger: when the Aura leaves the battlefield that creature's controller sacrifices it (603.7).
* Necromancy: an enchantment (flash if the controller wishes: sacrificed at cleanup when cast at instant speed) whose enters trigger targets a creature card in a graveyard and
  makes it an Aura with the same restricted enchant ability.
* An Aura attached to an illegal object goes to the graveyard (704.5m, 303.4c): protection from black on the returned creature, or the creature card gone from the graveyard.
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
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51f_reanimation_auras_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51f", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def bury(s, name, pid):
    """The card (in the player's deck) goes to that player's graveyard."""
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def game(cards, aura, mine=(), theirs=()):
    """Alice has the Aura in hand and plenty of Forests; every named card is a deck card of Alice / Bob. Alice has priority in her main phase."""
    s = build(cards, [aura, *mine], theirs)
    stops(s)
    mana(s, B=4, G=4, U=4)
    return s, to_hand(s, aura)


def cast_on(s, aura, target):
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[target.id])


def resolve_spell(s):
    """Bob (priority after the cast) passes: the Aura spell resolves; its enters trigger goes on the stack and Alice has priority."""
    act(s, "p2", type="pass_priority")


def test_the_three_are_full(cards):
    for name in ("Animate Dead", "Dance of the Dead", "Necromancy"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_animate_dead_returns_an_opponents_creature_under_your_control(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Grizzly Bears"])
    bears = bury(s, "Grizzly Bears", "p2")
    cast_on(s, ad, bears)
    settle(s)
    now = s.state.cards[bears.id]
    assert (now.zone, now.controller, now.owner) == ("p1:battlefield", "p1", "p2")  # returned under Alice's control
    assert s.state.cards[ad.id].attached_to == bears.id and zone_of(s, "Animate Dead") == "p1:battlefield"
    assert pt(s, "Grizzly Bears", "p2") == (1, 2)  # Enchanted creature gets -1/-0
    texts = {a.text.lower().rstrip(".") for a in ch(s, ad).abilities}
    assert "enchant creature put onto the battlefield with animate dead" in texts and "enchant creature card in a graveyard" not in texts
    check(s)


def to_stack_trigger(s, aura, target):
    """Cast the Aura on the target and let the spell resolve: its enters trigger is on the stack, Alice has priority."""
    cast_on(s, aura, target)
    resolve_spell(s)
    assert [e.name for e in s.state.rules.stack.values()] == [aura.name]


def test_animate_dead_removed_in_response_to_its_trigger_returns_nothing(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Grizzly Bears", "Disenchant"])
    bears, dis = bury(s, "Grizzly Bears", "p2"), to_hand(s, "Disenchant", "p2")
    to_stack_trigger(s, ad, bears)
    assert s.state.cards[ad.id].zone == "p1:battlefield" and s.state.cards[ad.id].attached_to is None  # it enchants the card in the graveyard, not a permanent
    act(s, "p1", type="pass_priority")
    mana(s, "p2", W=2)
    act(s, "p2", type="cast_spell", card_id=dis.id, targets=[ad.id])
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard"  # 603.4: "if it's on the battlefield" fails as the trigger resolves
    assert s.state.cards[bears.id].zone == "p2:graveyard" and not s.state.rules.delayed
    check(s)


def test_the_card_leaving_the_graveyard_in_response_sends_the_aura_to_the_graveyard(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Grizzly Bears", "Tormod's Crypt"])
    bears, crypt = bury(s, "Grizzly Bears", "p2"), put(s, "Tormod's Crypt", "p2")
    to_stack_trigger(s, ad, bears)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=crypt.id, ability=0, targets=["p2"])
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:exile"  # 303.4c, 704.5m: enchanting a card that isn't in a graveyard
    check(s)


def test_the_target_exiled_in_response_to_the_spell_and_it_does_not_resolve(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Grizzly Bears", "Tormod's Crypt"])
    bears, crypt = bury(s, "Grizzly Bears", "p2"), put(s, "Tormod's Crypt", "p2")
    cast_on(s, ad, bears)
    act(s, "p2", type="activate_ability", card_id=crypt.id, ability=0, targets=["p2"])
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:exile"  # 608.2b: illegal target, 608.3b
    check(s)


def test_destroying_animate_dead_makes_the_creatures_controller_sacrifice_it(cards):
    s, ad = game(cards, "Animate Dead", mine=["Disenchant"], theirs=["Grizzly Bears"])
    bears, dis = bury(s, "Grizzly Bears", "p2"), to_hand(s, "Disenchant")
    cast_on(s, ad, bears)
    settle(s)
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=dis.id, targets=[ad.id])
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard"
    assert s.state.cards[bears.id].zone == "p2:graveyard"  # sacrificed: it goes to its OWNER's graveyard (701.21a)
    assert not s.state.rules.delayed  # (it triggered once, 603.7b)
    check(s)


def test_the_creature_dying_first_sends_the_aura_to_the_graveyard_and_nothing_is_sacrificed(cards):
    s, ad = game(cards, "Animate Dead", mine=["Lightning Bolt"], theirs=["Grizzly Bears"])
    bears, bolt = bury(s, "Grizzly Bears", "p2"), to_hand(s, "Lightning Bolt")
    cast_on(s, ad, bears)
    settle(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bears.id])
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:graveyard"  # 704.5m
    assert not s.state.rules.delayed and not s.state.rules.stack
    check(s)


def test_protection_from_black_on_the_returned_creature_ends_the_aura_and_the_creature_is_sacrificed(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Paladin en-Vec"])
    paladin = bury(s, "Paladin en-Vec", "p2")
    cast_on(s, ad, paladin)  # (protection doesn't function in a graveyard: it is a legal target)
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard"  # 702.16c: it can't be attached to the creature (Animate Dead is black), 704.5m
    assert s.state.cards[paladin.id].zone == "p2:graveyard"  # its leaves trigger: the creature is sacrificed
    check(s)


def test_it_can_target_only_a_creature_card_in_a_graveyard(cards):
    s, ad = game(cards, "Animate Dead", mine=["Lightning Bolt"], theirs=["Grizzly Bears"])
    with pytest.raises(ActionError):  # no creature card in any graveyard
        cast_on(s, ad, card_named(s, "Grizzly Bears", "p2"))
    bolt = bury(s, "Lightning Bolt", "p1")
    with pytest.raises(ActionError):  # an instant card is not a creature card
        cast_on(s, ad, bolt)
    mine = bury(s, "Grizzly Bears", "p2")
    cast_on(s, ad, mine)
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield"
    check(s)


def test_the_target_is_chosen_among_the_creature_cards_of_every_graveyard(cards):
    s, ad = game(cards, "Animate Dead", mine=["Grizzly Bears", "Lightning Bolt"], theirs=["Kitchen Finks"])
    mine, finks, bolt = bury(s, "Grizzly Bears", "p1"), bury(s, "Kitchen Finks", "p2"), bury(s, "Lightning Bolt", "p1")
    act(s, "p1", type="cast_spell", card_id=ad.id)
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {mine.id, finks.id} and bolt.id not in {o.id for o in d.options}  # 303.4a: creature cards, both graveyards
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[finks.id])
    settle(s)
    assert (s.state.cards[finks.id].zone, s.state.cards[finks.id].controller) == ("p1:battlefield", "p1")
    check(s)


def test_a_log_and_view_never_name_the_cards_in_a_hand(cards):
    s, ad = game(cards, "Animate Dead", mine=["Lightning Bolt"], theirs=["Grizzly Bears"])
    bears, _ = bury(s, "Grizzly Bears", "p2"), to_hand(s, "Lightning Bolt")
    cast_on(s, ad, bears)
    settle(s)
    for viewer in ("p2", SPECTATOR):
        assert "Lightning Bolt" not in json.dumps(s.view(viewer))  # (graveyards are public, a hand is not)
    check(s)


def test_the_creatures_new_controller_sacrifices_it_when_the_aura_leaves(cards):
    s, ad = game(cards, "Animate Dead", mine=["Disenchant", "Grizzly Bears"])
    bears, dis = bury(s, "Grizzly Bears", "p1"), to_hand(s, "Disenchant")
    cast_on(s, ad, bears)
    settle(s)
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p2")  # (as Control Magic would)
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=dis.id, targets=[ad.id])
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:graveyard"  # 603.7c, 701.21a: Bob sacrificed it; it goes to its owner's
    check(s)


def test_it_cannot_be_attached_to_any_other_creature(cards):
    from app.rules import attachments

    s, ad = game(cards, "Animate Dead", theirs=["Grizzly Bears", "Grizzly Bears"])
    other = put(s, "Grizzly Bears", "p2")
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2" and c.id != other.id)
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "graveyard"})
    cast_on(s, ad, bears)
    settle(s)
    plan = Plan(s.state, "p1", s.cards, None)
    assert attachments.host_problem(plan, s.state.cards[ad.id], other.id) is not None  # its enchant ability allows only what it put onto the battlefield
    assert not attachments.attach(plan, ad.id, other.id, "p1") and s.state.cards[ad.id].attached_to == bears.id  # 303.4j / 701.3b: it doesn't move
    check(s)


def test_a_creature_that_asks_a_question_as_it_enters_is_still_enchanted(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Metallic Mimic"])
    mimic = bury(s, "Metallic Mimic", "p2")
    cast_on(s, ad, mimic)
    settle(s, answer="Goblin")  # "As this creature enters, choose a creature type" (614.12a): before it enters
    assert s.state.cards[mimic.id].zone == "p1:battlefield" and s.state.cards[ad.id].attached_to == mimic.id
    check(s)


def test_a_clone_returned_as_a_copy_is_still_enchanted(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Clone", "Grizzly Bears"])
    clone, _ = bury(s, "Clone", "p2"), put(s, "Grizzly Bears", "p2")
    cast_on(s, ad, clone)
    settle(s)  # "You may have Clone enter as a copy of any creature on the battlefield" (614.12a): answered with its first option
    assert s.state.cards[clone.id].zone == "p1:battlefield" and s.state.cards[ad.id].attached_to == clone.id and zone_of(s, "Animate Dead") == "p1:battlefield"
    check(s)


def test_wrath_of_god_destroys_the_creature_and_the_aura_in_one_go(cards):
    s, ad = game(cards, "Animate Dead", mine=["Wrath of God"], theirs=["Grizzly Bears"])
    bears, wrath = bury(s, "Grizzly Bears", "p2"), to_hand(s, "Wrath of God")
    cast_on(s, ad, bears)
    settle(s)
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    settle(s)
    assert zone_of(s, "Animate Dead") == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:graveyard" and not s.state.rules.delayed
    check(s)


def test_dance_of_the_dead_returns_the_creature_tapped_with_plus_one(cards):
    s, dance = game(cards, "Dance of the Dead", theirs=["Grizzly Bears"])
    bears = bury(s, "Grizzly Bears", "p2")
    cast_on(s, dance, bears)
    settle(s)
    now = s.state.cards[bears.id]
    assert (now.zone, now.controller, now.tapped) == ("p1:battlefield", "p1", True)
    assert s.state.cards[dance.id].attached_to == bears.id and pt(s, "Grizzly Bears", "p2") == (3, 3)
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_dance_of_the_dead_stays_tapped_unless_its_controller_pays_in_the_upkeep(cards, pay):
    s, dance = game(cards, "Dance of the Dead", theirs=["Grizzly Bears"])
    bears = bury(s, "Grizzly Bears", "p2")
    cast_on(s, dance, bears)
    settle(s)
    to_phase(s, "upkeep", turn=s.state.turn.number + 2)  # Alice's next turn: it didn't untap in the untap step ("doesn't untap during its controller's untap step")
    assert s.state.cards[bears.id].tapped and s.state.zones["stack"]  # "At the beginning of the upkeep of enchanted creature's controller"
    if pay:
        mana(s, B=1, G=1)
    settle(s, answer="yes" if pay else "no")
    assert s.state.cards[bears.id].tapped is not pay and s.state.cards[dance.id].attached_to == bears.id
    check(s)


def test_necromancy_cast_in_the_main_phase_becomes_an_aura_on_the_creature(cards):
    s, nec = game(cards, "Necromancy", theirs=["Grizzly Bears"])
    bears = bury(s, "Grizzly Bears", "p2")
    act(s, "p1", type="cast_spell", card_id=nec.id)
    settle(s)
    now = ch(s, nec)
    assert "Aura" in now.subtypes and s.state.cards[nec.id].attached_to == bears.id  # 205.1a: it became an Aura
    assert (s.state.cards[bears.id].zone, s.state.cards[bears.id].controller) == ("p1:battlefield", "p1")
    check(s)


def test_necromancy_cast_at_instant_speed_is_sacrificed_at_cleanup_and_so_is_the_creature(cards):
    s, nec = game(cards, "Necromancy", theirs=["Grizzly Bears"])
    bears = bury(s, "Grizzly Bears", "p2")
    to_phase(s, "end")
    mana(s, B=1, U=2)
    act(s, "p1", type="cast_spell", card_id=nec.id)  # a sorcery couldn't have been cast: flash
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[nec.id].zone == "p1:battlefield"
    to_phase(s, "main1", turn=s.state.turn.number + 1)
    assert zone_of(s, "Necromancy") == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_necromancy_with_no_creature_card_in_a_graveyard_stays_an_enchantment(cards):
    s, nec = game(cards, "Necromancy")
    act(s, "p1", type="cast_spell", card_id=nec.id)
    settle(s)
    assert zone_of(s, "Necromancy") == "p1:battlefield" and "Aura" not in ch(s, nec).subtypes  # 603.3d: the trigger had no target
    assert not s.state.rules.delayed
    check(s)


def test_necromancy_whose_target_is_exiled_in_response_does_nothing(cards):
    s, nec = game(cards, "Necromancy", theirs=["Grizzly Bears", "Tormod's Crypt"])
    bears, crypt = bury(s, "Grizzly Bears", "p2"), put(s, "Tormod's Crypt", "p2")
    act(s, "p1", type="cast_spell", card_id=nec.id)
    act(s, "p2", type="pass_priority")
    d = s.state.rules.decision  # the enters trigger's target
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=crypt.id, ability=0, targets=["p2"])
    settle(s)
    assert "Aura" not in ch(s, nec).subtypes and zone_of(s, "Necromancy") == "p1:battlefield"  # 608.2b: the whole ability does nothing
    check(s)
