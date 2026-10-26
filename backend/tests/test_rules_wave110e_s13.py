"""Wave 110E session 13: Paleontologist's Pick-Axe // Dinosaur Headdress (701.3a attach-time choice of a crafted exiled card; 707.2 copy while attached, 611.2b)."""
from __future__ import annotations

import pytest

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
SPLIT = real("Zed Split", "{2}{W}", 3, "Instant", "Exile target creature. Exile target creature card in a graveyard.", None, "W")
base.EXTRA.extend([KAYA, BANISH, SCOUR, PURGE, SPLIT])
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
    s = _three(cards, ["Kaya, Spirits' Justice", "Zed Banish", "Zed Scour", "Zed Purge", "Zed Split", "Zed Hawk", "Zed Bear", *deck_extra], carols=(GIANT,))
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


def _both(cards, name):
    s, kaya = _kaya(cards)
    spirit = _spirit(s, kaya)
    hawk = put(s, "Zed Hawk")
    bear = card_named(s, "Zed Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, C=2)
    cast(s, name, [hawk.id, bear.id], target_counts=[1, 1])
    return s, spirit


def test_kaya_one_instruction_exiling_both_is_one_trigger(cards):
    """603.2c / 608.2c: one instruction exiles a creature of yours and a creature card of your graveyard together: ONE trigger offering both cards."""
    s, spirit = _both(cards, "Zed Purge")
    assert _drive(s, "Zed Bear") == [["Zed Bear", "Zed Hawk"]]
    assert _ch(s, spirit.id).name == "Zed Bear"
    check(s)


def test_kaya_two_instructions_are_two_triggers(cards):
    """603.2: two separate instructions are two events: two triggers, each offering its own exiled card; the later copy replaces the earlier (613.7)."""
    s, spirit = _both(cards, "Zed Split")
    assert sorted(_drive(s, "Zed Bear")) == [["Zed Bear"], ["Zed Hawk"]]
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


# -- Blaster, Combat DJ // Blaster, Morale Booster -------------------------------------------------------------------------------------------------------
from app.rules import alt_costs  # noqa: E402

_BLASTER_FRONT = ("More Than Meets the Eye {1}{R}{G} (You may cast this card converted for {1}{R}{G}.)\nOther nontoken artifact creatures and Vehicles you control have modular 1. "
                  "(They enter with an additional +1/+1 counter on them. When they die, you may put their +1/+1 counters on target artifact creature.)\n"
                  "Whenever you put one or more +1/+1 counters on Blaster, convert it.")
_BLASTER_BACK = ("Modular 3\n{X}, {T}: Move X +1/+1 counters from Blaster onto another target artifact. That artifact gains haste until end of turn. "
                 "If Blaster has no +1/+1 counters on it, convert it. Activate only as a sorcery.")
BLASTER = card("Blaster, Combat DJ // Blaster, Morale Booster", set_code="tst", number="13-blaster", layout="transform", mana_cost="{3}{R}{G} // ", cmc=5.0,
               type_line="Legendary Artifact Creature — Robot // Legendary Artifact", oracle_text=f"{_BLASTER_FRONT}\n//\n{_BLASTER_BACK}", power="3", toughness="3",
               colors=["G", "R"], color_identity=["G", "R"], keywords=["Modular", "Convert", "More Than Meets the Eye"],
               card_faces=[{"name": "Blaster, Combat DJ", "mana_cost": "{3}{R}{G}", "type_line": "Legendary Artifact Creature — Robot", "oracle_text": _BLASTER_FRONT,
                            "power": "3", "toughness": "3", "colors": ["G", "R"]},
                           {"name": "Blaster, Morale Booster", "mana_cost": "", "type_line": "Legendary Artifact", "oracle_text": _BLASTER_BACK, "colors": ["G", "R"]}])
GOLEM = real("Zed Golem", "{2}", 2, "Artifact Creature — Golem", "", ("2", "2"))
DRONE = real("Zed Drone", "{2}", 2, "Artifact Creature — Construct", "", ("1", "1"))
CRUISER = real("Zed Cruiser", "{2}", 2, "Artifact — Vehicle", "Crew 1", ("3", "3"))
ELF = real("Zed Elf", "{G}", 1, "Creature — Elf", "", ("1", "1"), "G")
ROCK = real("Zed Rock", "{1}", 1, "Artifact", "", None)
MAKER = real("Zed Maker", "{1}", 1, "Sorcery", "Create a 1/1 colorless Construct artifact creature token.", None)
SMITE = real("Zed Smite", "{B}", 1, "Instant", "Destroy target creature.", None, "B")
base.EXTRA.extend([BLASTER, GOLEM, DRONE, CRUISER, ELF, ROCK, SMITE, MAKER])
BNAME = "Blaster, Combat DJ // Blaster, Morale Booster"


def _plus(s, name, pid="p1"):
    return card_named(s, name, pid).counters.get("+1/+1", 0)


def _blaster_table(cards, extra=()):
    s = build(cards, [BNAME, "Zed Golem", "Zed Drone", "Zed Cruiser", "Zed Elf", "Zed Rock", "Zed Smite", "Zed Maker", *extra], forests=30, islands=30)
    return s, put(s, BNAME)


def test_blaster_full(cards):
    assert coverage.of_card_data(cards.resolve(BNAME)).level == "FULL"


@pytest.mark.parametrize(("name", "cost", "counters"), [("Zed Golem", {"C": 2}, 1), ("Zed Cruiser", {"C": 2}, 1), ("Zed Elf", {"G": 1}, 0), ("Zed Rock", {"C": 1}, 0)])
def test_blaster_gives_modular_one_to_artifact_creatures_and_vehicles_entering(cards, name, cost, counters):
    """702.43a: the granted modular is an "enters with" replacement of the entering permanent: artifact creatures and Vehicles get a counter, others don't."""
    s, blaster = _blaster_table(cards)
    mana(s, **cost)
    cast(s, name)
    answer_all(s)
    assert _plus(s, name) == counters
    check(s)


def answer_all(s, prefer=None, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label == prefer][:1] or [i for i in ids if i in ("yes", "pay")][:1] or ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_blaster_granted_modular_moves_counters_when_it_dies(cards):
    """702.43a: when the permanent with modular is put into a graveyard, its +1/+1 counters go on target artifact creature (last known information)."""
    s, blaster = _blaster_table(cards)
    mana(s, C=4)
    cast(s, "Zed Golem")
    answer_all(s)
    cast(s, "Zed Drone")
    answer_all(s)
    assert (_plus(s, "Zed Golem"), _plus(s, "Zed Drone")) == (1, 1)
    mana(s, B=1)
    cast(s, "Zed Smite", [card_named(s, "Zed Golem").id])
    answer_all(s, prefer="Zed Drone")
    assert card_named(s, "Zed Golem").zone == "p1:graveyard" and _plus(s, "Zed Drone") == 2
    check(s)


def _converted(cards):
    s, blaster = _blaster_table(cards)
    act(s, "p1", type="move", card_ids=[blaster.id], to={"zone": "hand"})
    hand = s.state.cards[blaster.id]
    offers = alt_costs.converted_offers(s.state, "p1", hand, s.cards)
    mana(s, R=1, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=hand.id, alt_cost=offers[0].key)
    answer_all(s)
    assert s.state.cards[blaster.id].face == 1 and s.state.cards[blaster.id].counters.get("+1/+1") == 3  # modular 3
    rock = put(s, "Zed Rock")
    return s, blaster, rock


@pytest.mark.parametrize(("x", "moved", "left", "face"), [(2, 2, 1, 1), (3, 3, 0, 0), (5, 3, 0, 0)])
def test_blaster_back_moves_x_counters_and_converts_when_none_are_left(cards, x, moved, left, face):
    """122.5: as many as X (fewer there: those); 701.28a: with none left it converts back to the front face; the target artifact gains haste."""
    s, blaster, rock = _converted(cards)
    mana(s, C=x)
    act(s, "p1", type="activate_ability", card_id=blaster.id, ability=1, targets=[rock.id], x_value=x)
    answer_all(s)
    assert s.state.cards[rock.id].counters.get("+1/+1", 0) == moved and s.state.cards[blaster.id].counters.get("+1/+1", 0) == left
    assert s.state.cards[blaster.id].face == face
    assert "haste" in {k.lower() for k in _ch(s, rock.id).keywords}
    check(s)


def test_blaster_modular_is_for_nontoken_permanents_only(cards):
    """"nontoken": an artifact creature token enters without the counter."""
    s, blaster = _blaster_table(cards)
    mana(s, C=1)
    cast(s, "Zed Maker")
    answer_all(s)
    token = next(c for c in s.state.cards.values() if c.is_token and c.controller == "p1" and c.zone == "p1:battlefield")
    assert token.counters.get("+1/+1", 0) == 0
    check(s)


# -- Vedalken Squirrel-Whacker ---------------------------------------------------------------------------------------------------------------------------
SQUIRREL = real("Vedalken Squirrel-Whacker", "{3}{U}", 4, "Creature — Vedalken Guest",
                "As this creature enters, roll a six-sided die twice. Its base power becomes the first result and its base toughness becomes the second result.\n"
                "If you would roll one or more six-sided dice, instead roll them and you may exchange one result with this creature's base power or base toughness.",
                ("*", "*"), "U")
ROLL6 = real("Zed Roll", "{B}", 1, "Sorcery", "Roll a six-sided die. You gain life equal to the result.", None, "B")
ROLL20 = real("Zed Roll Big", "{B}", 1, "Sorcery", "Roll a d20. You gain life equal to the result.", None, "B")
base.EXTRA.extend([SQUIRREL, ROLL6, ROLL20])
SQ = "Vedalken Squirrel-Whacker"


def _cast_squirrel(cards, monkeypatch, dice, copies=1):
    from tests.test_rules_random_consequences import faces

    s = build(cards, [SQ] * copies + ["Zed Roll", "Zed Roll Big"])
    faces(monkeypatch, dice)
    mana(s, U=1, C=3)
    cast(s, SQ)
    answer_all(s)
    return s


def test_squirrel_whacker_full(cards):
    assert coverage.of_card_data(cards.resolve(SQ)).level == "FULL"


@pytest.mark.parametrize(("dice", "stats"), [([4, 2], (4, 2)), ([6, 6], (6, 6))])
def test_squirrel_whacker_dice_are_its_base_power_and_toughness(cards, monkeypatch, dice, stats):
    """614.12a / 208.4b: rolled as it enters; first result its base power, second its base toughness (it is on the battlefield, not dead as a 0/0)."""
    s = _cast_squirrel(cards, monkeypatch, dice)
    card = card_named(s, SQ)
    assert card.zone == "p1:battlefield" and _ch(s, card.id).pt == stats and _ch(s, card.id).base_pt == stats
    check(s)


def _roll_and_exchange(s, monkeypatch, die, pick_stat):
    from tests.test_rules_random_consequences import faces

    faces(monkeypatch, [die])
    mana(s, B=1)
    before = s.state.players["p1"].life
    cast(s, "Zed Roll")
    d = s.state.rules.decision
    assert d is not None and d.options[0].id.startswith("roll_adjust42:")
    if pick_stat is None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["done"])
    else:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["0"])
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[pick_stat])
    answer_all(s)
    return s.state.players["p1"].life - before


@pytest.mark.parametrize(("stat", "gain", "stats"), [("power", 4, (5, 2)), ("toughness", 2, (4, 5)), (None, 5, (4, 2))])
def test_squirrel_whacker_exchanges_a_result_with_its_base_power_or_toughness(cards, monkeypatch, stat, gain, stats):
    """614.1a / 706.2: the roll's result is exchanged with the base value (a 5 against base power 4 or toughness 2); declining changes nothing."""
    s = _cast_squirrel(cards, monkeypatch, [4, 2])
    assert _roll_and_exchange(s, monkeypatch, 5, stat) == gain
    assert _ch(s, card_named(s, SQ).id).pt == stats
    check(s)


def test_squirrel_whacker_is_not_offered_for_other_dice(cards, monkeypatch):
    """"six-sided dice" only: a d20 roll is not adjusted."""
    from tests.test_rules_random_consequences import faces

    s = _cast_squirrel(cards, monkeypatch, [4, 2])
    faces(monkeypatch, [17])
    mana(s, B=1)
    cast(s, "Zed Roll Big")
    assert s.state.rules.decision is None and s.state.players["p1"].life == 40 + 17
    check(s)


def test_squirrel_whacker_does_not_adjust_its_own_entering_roll(cards, monkeypatch):
    """It is not on the battlefield while it rolls (614.12a): no exchange is offered for its own two dice."""
    from tests.test_rules_random_consequences import faces

    s = build(cards, [SQ, "Zed Roll"])
    faces(monkeypatch, [3, 5])
    mana(s, U=1, C=3)
    cast(s, SQ)
    d = s.state.rules.decision
    assert d is None or not d.options[0].id.startswith("roll_adjust42:")
    answer_all(s)
    assert _ch(s, card_named(s, SQ).id).pt == (3, 5)


def test_squirrel_whacker_on_the_battlefield_adjusts_the_roll_of_a_second_one_entering(cards, monkeypatch):
    """The first one is on the battlefield while the second rolls: its exchange applies to the second's dice (614.1a) before they become the second's base values."""
    from tests.test_rules_random_consequences import faces

    s = _cast_squirrel(cards, monkeypatch, [4, 2], copies=2)
    first = card_named(s, SQ)
    faces(monkeypatch, [6, 1])
    mana(s, U=1, C=3)
    second = next(c for c in s.state.cards.values() if c.name == SQ and c.owner == "p1" and c.id != first.id)
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=second.id)
    d = s.state.rules.decision
    for _ in range(6):
        if d is not None and d.options[0].id.startswith("roll_adjust42:"):
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        d = s.state.rules.decision
    assert d is not None and d.options[0].id.startswith("roll_adjust42:")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["0"])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["power"])
    answer_all(s)
    assert _ch(s, first.id).pt == (6, 2) and _ch(s, second.id).pt == (4, 1)
    check(s)
