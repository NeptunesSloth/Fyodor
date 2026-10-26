"""Wave 110A: 601.2f/602.2b first activated ability of an artifact you activate each turn costs {2} less (Tezzeret, Betrayer of Flesh)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import answer, card_db  # noqa: F401
from tests.wave9c_kit import build, card_named, check, life, mana, put

EXTRA = [
    real("Tezzeret, Betrayer of Flesh", "{3}{U}{B}", 5, "Legendary Planeswalker — Tezzeret",
         "The first activated ability of an artifact you activate each turn costs {2} less to activate.\n+1: Draw two cards. Then discard two cards unless you "
         "discard an artifact card.\n−2: Target artifact becomes an artifact creature. If it isn't a Vehicle, it has base power and toughness 4/4.\n−6: You get an "
         "emblem with \"Whenever an artifact you control becomes tapped, draw a card.\"", None, "UB"),
    real("Tectonic Split", "{4}{G}{U}", 6, "Enchantment",
         "As an additional cost to cast this spell, sacrifice half the lands you control, rounded up.\nHexproof\nLands you control have \"{T}: Add three mana of "
         "any one color.\"", None, "GU"),
    real("Estrid, the Masked", "{2}{W}{W}", 4, "Legendary Planeswalker — Estrid",
         "+2: Untap each enchanted permanent you control.\n\u22121: Create a white Aura enchantment token named Mask attached to another target permanent. The token has "
         "enchant permanent and umbra armor.\n\u22127: Mill seven cards. Return all non-Aura enchantment cards from your graveyard to the battlefield, then do the same "
         "for Aura cards.\nEstrid, the Masked can be your commander.", None, "W"),
    real("Aura110", "{W}", 1, "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.", None, "W"),
    real("Ench110", "{W}", 1, "Enchantment", "", None, "W"),
    real("Bear110", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Thran Portal", "", 0, "Land", "This land enters tapped unless you control two or fewer other lands.\nAs this land enters, choose a basic land type.\n"
         "This land is the chosen type in addition to its other types.\nMana abilities of this land cost an additional 1 life to activate.", None, ""),
    real("New Blood", "{2}{B}", 3, "Sorcery", "As an additional cost to cast this spell, tap an untapped Vampire you control.\nGain control of target creature. Change the text of "
         "that creature by replacing all instances of one creature type with Vampire.", None, "B"),
    real("Vamp110", "{B}", 1, "Creature — Vampire", "", ("1", "1"), "B"),
    real("Goblin110", "{R}", 1, "Creature — Goblin", "Other Goblin creatures you control get +1/+1.", ("1", "1"), "R"),
    real("Karn, Living Legacy", "{4}", 4, "Legendary Planeswalker — Karn",
         "+1: Create a tapped Powerstone token. (It's an artifact with \"{T}: Add {C}. This mana can't be spent to cast a nonartifact spell.\")\n\u22121: Pay any amount of mana. "
         "Look at that many cards from the top of your library, then put one of those cards into your hand and the rest on the bottom of your library in a random order."
         "\n\u22127: You get an emblem with \"Tap an untapped artifact you control: This emblem deals 1 damage to any target.\"", None, ""),
    real("Gizmo A110", "{1}", 1, "Artifact", "{2}, {T}: You gain 1 life.", None, ""),
    real("Gizmo B110", "{1}", 1, "Artifact", "{2}, {T}: You gain 1 life.", None, ""),
    real("Rock110", "{1}", 1, "Artifact", "{T}: Add {C}.", None, ""),
]
_BASE.extend(EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Tezzeret, Betrayer of Flesh")).level == "FULL"


def _go(s, name):
    act(s, "p1", type="activate_ability", card_id=put_cards[name].id, ability=0, sources=[])
    act(s, "p1", type="pass_priority")


put_cards: dict = {}


def _setup(cards, *names):
    s = build(cards, ["Tezzeret, Betrayer of Flesh", *names])
    put(s, "Tezzeret, Betrayer of Flesh")
    for n in names:
        put_cards[n] = put(s, n)
    return s


def test_first_free_second_pays(cards):
    s = _setup(cards, "Gizmo A110", "Gizmo B110")
    _go(s, "Gizmo A110")
    assert life(s) == 41
    with pytest.raises(ActionError):
        _go(s, "Gizmo B110")
    mana(s, C=2)
    _go(s, "Gizmo B110")
    assert life(s) == 42
    check(s)


def test_mana_ability_of_artifact_uses_the_first(cards):
    from app.rules import mana_units

    s = _setup(cards, "Gizmo A110", "Rock110")
    act(s, "p1", type="activate_ability", card_id=put_cards["Rock110"].id, ability=0)
    mana(s, C=1)
    _go(s, "Gizmo A110")  # paid {2} in full: the Rock activation was the first
    assert life(s) == 41 and not mana_units.visible_pool(s.state, "p1")
    check(s)


def _split(cards, lands, picked):
    s = build(cards, ["Tectonic Split"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:lands]  # (put() returns the same Forest each call)
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    mana(s, G=1, U=1, C=4)
    spell = card_named(s, "Tectonic Split")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=spell.id, cost_choices=[{"component": 0, "cards": [f.id for f in forests[:picked]]}])
    return s, forests


def test_tectonic_split_full(cards):
    assert coverage.of_card_data(cards.resolve("Tectonic Split")).level == "FULL"


@pytest.mark.parametrize(("lands", "half"), [(5, 3), (4, 2), (1, 1)])
def test_tectonic_split_sacrifices_half_rounded_up(cards, lands, half):
    s, forests = _split(cards, lands, half)
    assert sum(f.zone == "p1:graveyard" for f in forests) == half
    check(s)


@pytest.mark.parametrize(("lands", "wrong"), [(5, 2), (4, 3)])
def test_tectonic_split_wrong_count_refused(cards, lands, wrong):
    with pytest.raises(ActionError):
        _split(cards, lands, wrong)


def test_tectonic_split_lands_make_three_mana(cards):
    from app.rules import mana_units

    s, forests = _split(cards, 4, 2)
    answer(s)
    keep = forests[2]
    act(s, "p1", type="activate_ability", card_id=keep.id, ability=100)
    answer(s)
    assert sum(mana_units.visible_pool(s.state, "p1").values()) == 3
    check(s)


def _estrid(cards, ability, loyalty):
    s = build(cards, ["Estrid, the Masked", "Bear110", "Aura110", "Ench110"])
    est = put(s, "Estrid, the Masked")
    act(s, "p1", type="counter", card_ids=[est.id], kind="loyalty", delta=loyalty)
    return s, est


def test_estrid_full(cards):
    assert coverage.of_card_data(cards.resolve("Estrid, the Masked")).level == "FULL"


def test_estrid_mask_attaches_to_another_permanent_with_umbra_armor(cards):
    from app.rules.plan import Plan

    s, est = _estrid(cards, 1, 3)
    bear = put(s, "Bear110")
    act(s, "p1", type="activate_ability", card_id=est.id, ability=1, targets=[bear.id])
    answer(s)
    mask = next(c for c in s.state.cards.values() if c.name == "Mask")
    assert mask.attached_to == bear.id and "umbra armor" in Plan.view(s.state, "p1", s.cards).ch(mask).keywords
    check(s)


def test_estrid_mask_cannot_target_estrid_herself(cards):
    s, est = _estrid(cards, 1, 3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=est.id, ability=1, targets=[est.id])


def test_estrid_ultimate_returns_enchantments_then_auras(cards):
    s, est = _estrid(cards, 2, 3)
    bear = put(s, "Bear110")
    aura, ench = card_named(s, "Aura110"), card_named(s, "Ench110")
    act(s, "p1", type="move", card_ids=[aura.id, ench.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="counter", card_ids=[est.id], kind="loyalty", delta=4)
    act(s, "p1", type="activate_ability", card_id=est.id, ability=2)
    answer(s)
    assert ench.zone == "p1:battlefield" and aura.zone == "p1:battlefield"
    assert aura.attached_to in (bear.id, ench.id, est.id)
    check(s)


def test_thran_portal_full(cards):
    assert coverage.of_card_data(cards.resolve("Thran Portal")).level == "FULL"


def test_thran_portal_chosen_type_and_life_for_mana(cards):
    from app.rules import mana_units
    from app.rules.plan import Plan

    s = build(cards, ["Thran Portal"])
    portal = card_named(s, "Thran Portal")
    act(s, "p1", type="move", card_ids=[portal.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=portal.id)
    answer(s)
    chosen = portal.choices.get("Chosen basic land type")
    assert chosen and chosen in Plan.view(s.state, "p1", s.cards).ch(portal).subtypes
    assert not portal.tapped  # two or fewer other lands: enters untapped
    idx = [a.index for a in Plan.view(s.state, "p1", s.cards).ch(portal).abilities if a.text.startswith("{T}, Pay 1 life: Add")]
    assert idx, [(a.index, a.kind, a.text) for a in Plan.view(s.state, "p1", s.cards).ch(portal).abilities]
    act(s, "p1", type="activate_ability", card_id=portal.id, ability=idx[0])
    answer(s)
    assert life(s) == 39 and sum(mana_units.visible_pool(s.state, "p1").values()) == 1
    check(s)


def test_thran_portal_enters_tapped_with_three_other_lands(cards):
    s = build(cards, ["Thran Portal"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    portal = card_named(s, "Thran Portal")
    act(s, "p1", type="move", card_ids=[portal.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=portal.id)
    answer(s)
    assert portal.tapped


def test_new_blood_full(cards):
    assert coverage.of_card_data(cards.resolve("New Blood")).level == "FULL"


@pytest.mark.parametrize("word", ["Goblin", "Vampire"])
def test_new_blood_steals_and_rewrites_type(cards, word):
    from app.rules.plan import Plan
    from tests.test_rules_wave100n_multi import cast

    s = build(cards, ["New Blood", "Vamp110"], ["Goblin110"])
    vamp, gob = put(s, "Vamp110"), put(s, "Goblin110", "p2")
    mana(s, B=1, C=2)
    cast(s, "New Blood", [gob.id], cost_choices=[{"component": 0, "cards": [vamp.id]}])
    answer(s, word)
    assert s.state.cards[vamp.id].tapped and s.state.cards[gob.id].controller == "p1"
    subs = Plan.view(s.state, "p1", s.cards).ch(s.state.cards[gob.id]).subtypes
    assert ("Vampire" in subs and "Goblin" not in subs) if word == "Goblin" else ("Goblin" in subs and "Vampire" not in subs)
    check(s)


def test_karn_living_legacy_full(cards):
    assert coverage.of_card_data(cards.resolve("Karn, Living Legacy")).level == "FULL"


@pytest.mark.parametrize("paid", [0, 2])
def test_karn_pay_any_amount_look_that_many_take_one(cards, paid):
    s = build(cards, ["Karn, Living Legacy"])
    karn = put(s, "Karn, Living Legacy")
    act(s, "p1", type="counter", card_ids=[karn.id], kind="loyalty", delta=4)
    hand, lib = len(s.state.zones["p1:hand"]), len(s.state.zones["p1:library"])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=karn.id, ability=1)
    answer(s, f"x:{paid}")
    assert len(s.state.zones["p1:hand"]) == hand + (1 if paid else 0) and len(s.state.zones["p1:library"]) == lib - (1 if paid else 0)
    check(s)


def test_karn_emblem_taps_artifact_for_one_damage(cards):
    s = build(cards, ["Karn, Living Legacy", "Rock110"])
    karn, rock = put(s, "Karn, Living Legacy"), put(s, "Rock110")
    act(s, "p1", type="counter", card_ids=[karn.id], kind="loyalty", delta=7)
    act(s, "p1", type="activate_ability", card_id=karn.id, ability=2)
    answer(s)
    emblem = next(c for c in s.state.cards.values() if c.zone == "p1:command" and c.token is not None and c.token.type_line == "Emblem")
    act(s, "p1", type="activate_ability", card_id=emblem.id, ability=0, targets=["p2"], cost_choices=[{"component": 0, "cards": [rock.id]}])
    answer(s)
    assert life(s, "p2") == 39 and s.state.cards[rock.id].tapped
    check(s)
