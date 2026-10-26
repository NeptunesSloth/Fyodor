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
