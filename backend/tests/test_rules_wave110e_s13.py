"""Wave 110E session 13: Paleontologist's Pick-Axe // Dinosaur Headdress (701.3a attach-time choice of a crafted exiled card; 707.2 copy while attached, 611.2b)."""
from __future__ import annotations

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, mana, put

_FRONT = ("Whenever equipped creature attacks, draw a card, then discard a card.\nEquip {1}\nCraft with one or more creatures {5} ({5}, Exile this artifact, Exile one or more "
          "creatures you control and/or creature cards from your graveyard: Return this card transformed under its owner's control. Craft only as a sorcery.)")
_BACK = ("When this Equipment enters, attach it to target creature you control.\nAs this Equipment becomes attached to a creature, choose an exiled creature card used to craft this "
         "Equipment.\nEquipped creature is a copy of the last chosen card.\nEquip {2}")
AXE = card("Paleontologist's Pick-Axe // Dinosaur Headdress", set_code="tst", number="13-axe", layout="transform", mana_cost="{2} // ", cmc=2.0,
           type_line="Artifact — Equipment // Artifact — Equipment", oracle_text=f"{_FRONT}\n//\n{_BACK}", colors=[], color_identity=[], keywords=["Craft", "Transform", "Equip"],
           card_faces=[{"name": "Paleontologist's Pick-Axe", "mana_cost": "{2}", "type_line": "Artifact — Equipment", "oracle_text": _FRONT, "colors": []},
                       {"name": "Dinosaur Headdress", "mana_cost": "", "type_line": "Artifact — Equipment", "oracle_text": _BACK, "colors": []}])
HAWK = real("Zed Hawk", "{1}{U}", 2, "Creature — Bird", "Flying", ("2", "1"), "U")
BEAR = real("Zed Bear", "{1}{G}", 2, "Creature — Bear", "", ("3", "3"), "G")
HOST = real("Zed Host", "{W}", 1, "Creature — Human", "", ("1", "1"), "W")
base.EXTRA.extend([AXE, HAWK, BEAR, HOST])
NAME = "Paleontologist's Pick-Axe // Dinosaur Headdress"


def _until_question(s):
    """Resolve the stack (other decisions: first option) until the craft-card question or nothing is left."""
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and "exiled creature card" in d.prompt:
            return d
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return None
    raise AssertionError("never settled")


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def _ch(s, card_id):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_id])


def _crafted(cards, materials):
    """Alice crafts the Pick-Axe from ``materials`` (creature cards from her graveyard); its enters trigger attaches it to Zed Host."""
    s = build(cards, [NAME, "Zed Hawk", "Zed Bear", "Zed Host", "Zed Host"])
    axe, host = put(s, NAME), put(s, "Zed Host")
    mats = [card_named(s, n) for n in materials]
    act(s, "p1", type="move", card_ids=[c.id for c in mats], to={"player": "p1", "zone": "graveyard"})
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=axe.id, ability=2, cost_choices=[{"component": 2, "cards": [c.id for c in mats]}])
    return s, axe, host, mats


def test_pick_axe_copies_the_chosen_exiled_card_while_attached(cards):
    s, axe, host, (hawk, bear) = _crafted(cards, ["Zed Hawk", "Zed Bear"])
    d = _until_question(s)
    assert d is not None and {o.label for o in d.options} == {"Zed Hawk", "Zed Bear"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear.id])
    assert s.state.cards[axe.id].attached_to == host.id and s.state.cards[axe.id].face == 1
    ch = _ch(s, host.id)
    assert ch.name == "Zed Bear" and ch.pt == (3, 3)
    check(s)


def test_pick_axe_with_one_material_asks_nothing(cards):
    s, axe, host, (hawk,) = _crafted(cards, ["Zed Hawk"])
    assert _until_question(s) is None
    assert _ch(s, host.id).name == "Zed Hawk" and "flying" in {k.lower() for k in _ch(s, host.id).keywords}
    check(s)


def test_pick_axe_equip_chooses_again(cards):
    s, axe, host, (hawk, bear) = _crafted(cards, ["Zed Hawk", "Zed Bear"])
    act(s, "p1", type="choose", decision_id=_until_question(s).id, option_ids=[hawk.id])
    assert _ch(s, host.id).name == "Zed Hawk"
    other = next(c for c in s.state.cards.values() if c.name == "Zed Host" and c.owner == "p1" and c.id != host.id)
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=axe.id, ability=3, targets=[other.id])
    d = _until_question(s)
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear.id])
    assert _ch(s, other.id).name == "Zed Bear" and _ch(s, host.id).name == "Zed Host"
    check(s)


# -- Kaya, Spirits' Justice ------------------------------------------------------------------------------------------------------------------------------
from tests.test_rules_wave110e_cards import cast  # noqa: E402
from tests.test_rules_wave110e_s11 import _three  # noqa: E402

KAYA = card("Kaya, Spirits' Justice", set_code="tst", number="13-kaya", mana_cost="{2}{W}{B}", cmc=4.0, type_line="Legendary Planeswalker — Kaya", loyalty="3",
            colors=["W", "B"], color_identity=["W", "B"], keywords=[],
            oracle_text="Whenever one or more creatures you control and/or creature cards in your graveyard are put into exile, you may choose a creature card from among them. "
                        "Until end of turn, target token you control becomes a copy of it, except it has flying.\n+2: Surveil 2, then exile a card from a graveyard.\n"
                        "+1: Create a 1/1 white and black Spirit creature token with flying.\n−2: Exile target creature you control. For each other player, exile up to one target creature that player controls.")
BANISH = real("Zed Banish", "{1}{W}", 2, "Instant", "Exile target creature.", None, "W")
SCOUR = real("Zed Scour", "{W}", 1, "Instant", "Exile target card from a graveyard.", None, "W")
PURGE = real("Zed Purge", "{2}{W}", 3, "Instant", "Exile target creature and target creature card in a graveyard.", None, "W")
base.EXTRA.extend([KAYA, BANISH, SCOUR, PURGE])
GIANT = "Test Giant"


def _drive(s, pick=None, limit=40):
    """Resolve everything; the Kaya question is answered with the card named ``pick`` (None: decline), other decisions with their first option."""
    asked = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            if "from among the exiled cards" in d.prompt:
                asked.append(sorted(o.label for o in d.options))
                ids = [o.id for o in d.options if o.label == pick][:1]
            else:
                ids = [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def _kaya(cards, deck_extra=()):
    s = _three(cards, ["Kaya, Spirits' Justice", "Zed Banish", "Zed Scour", "Zed Purge", "Zed Hawk", "Zed Bear", *deck_extra], carols=(GIANT,))
    kaya = put(s, "Kaya, Spirits' Justice")
    act(s, "p1", type="set_counter", card_id=kaya.id, kind="loyalty", value=5)
    return s, kaya


def _spirit(s, kaya):
    act(s, "p1", type="activate_ability", card_id=kaya.id, ability=2)  # +1
    _drive(s)
    return next(c for c in s.state.cards.values() if c.is_token and c.controller == "p1" and c.zone == "p1:battlefield")


def test_kaya_full(cards):
    assert coverage.of_card_data(cards.resolve("Kaya, Spirits' Justice")).level == "FULL"


def test_kaya_token_copies_an_exiled_creature_of_yours(cards):
    """603.2 / 707.4: the creature you control put into exile; the token you target becomes a copy of that card, with flying, until end of turn."""
    s, kaya = _kaya(cards)
    spirit = _spirit(s, kaya)
    hawk = put(s, "Zed Hawk")
    mana(s, W=1, C=1)
    cast(s, "Zed Banish", [hawk.id])
    assert _drive(s, "Zed Hawk") == [["Zed Hawk"]]
    ch = _ch(s, spirit.id)
    assert ch.name == "Zed Hawk" and ch.pt == (2, 1) and "flying" in {k.lower() for k in ch.keywords}
    check(s)


def test_kaya_graveyard_half_and_decline(cards):
    """The creature card of your graveyard put into exile also triggers it; "you may" choose: declining leaves the token as it is."""
    s, kaya = _kaya(cards)
    spirit = _spirit(s, kaya)
    bear = card_named(s, "Zed Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1)
    cast(s, "Zed Scour", [bear.id])
    assert _drive(s, None) == [["Zed Bear"]]
    assert _ch(s, spirit.id).name == "Spirit"
    mana(s, W=1)
    other = card_named(s, "Zed Hawk")
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Zed Scour", [other.id])
    assert _drive(s, "Zed Hawk") == [["Zed Hawk"]] and _ch(s, spirit.id).name == "Zed Hawk"
    check(s)


def test_kaya_an_opponents_card_in_their_graveyard_does_not_trigger(cards):
    """Only creature cards in YOUR graveyard (and your creatures): an opponent's creature or graveyard exiled does nothing."""
    s, kaya = _kaya(cards)
    _spirit(s, kaya)
    giant = put(s, GIANT, "p3")
    mana(s, W=1, C=1)
    cast(s, "Zed Banish", [giant.id])
    assert _drive(s, "Test Giant") == []
    check(s)


def test_kaya_each_exile_event_is_its_own_trigger(cards):
    """603.2: two instructions exile one object each (two events): two triggers, each offering its own exiled cards; the later copy replaces the earlier (613.7)."""
    s, kaya = _kaya(cards)
    spirit = _spirit(s, kaya)
    hawk = put(s, "Zed Hawk")
    bear = card_named(s, "Zed Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, C=2)
    cast(s, "Zed Purge", [hawk.id, bear.id], target_counts=[1, 1])
    asked = _drive(s, "Zed Bear")
    assert sorted(a for q in asked for a in q) == ["Zed Bear", "Zed Hawk"]
    assert _ch(s, spirit.id).name in ("Zed Bear", "Zed Hawk")
    check(s)


def test_kaya_minus_two_exiles_yours_and_up_to_one_per_other_player(cards):
    """-2: your creature, then for each other player up to one of that player's creatures (their own target group each)."""
    s, kaya = _kaya(cards)
    mine, bobs, carols = put(s, "Zed Hawk"), put(s, GIANT, "p2"), put(s, GIANT, "p3")
    act(s, "p1", type="activate_ability", card_id=kaya.id, ability=3, targets=[mine.id, bobs.id, carols.id], target_counts=[1, 1, 1])
    _drive(s)
    assert [s.state.cards[c.id].zone for c in (mine, bobs, carols)] == ["p1:exile", "p2:exile", "p3:exile"]
    assert s.state.cards[kaya.id].counters["loyalty"] == 3
    check(s)


def test_kaya_minus_two_up_to_one_may_skip_an_opponent(cards):
    s, kaya = _kaya(cards)
    mine, carols = put(s, "Zed Hawk"), put(s, GIANT, "p3")
    bobs = put(s, GIANT, "p2")
    act(s, "p1", type="activate_ability", card_id=kaya.id, ability=3, targets=[mine.id, carols.id], target_counts=[1, 0, 1])
    _drive(s)
    assert s.state.cards[bobs.id].zone == "p2:battlefield" and s.state.cards[carols.id].zone == "p3:exile"
    check(s)


def test_kaya_plus_two_surveils_then_exiles_a_card_from_any_graveyard(cards):
    s, kaya = _kaya(cards)
    bear = card_named(s, "Zed Bear", "p1")
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=kaya.id, ability=1)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            break
        pick = [o.id for o in d.options if o.label == "Zed Bear"] or [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    assert s.state.cards[bear.id].zone == "p1:exile" and s.state.cards[kaya.id].counters["loyalty"] == 7
    check(s)
