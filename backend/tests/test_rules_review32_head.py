"""Review 32 (head): falsifying the cards waves 30-31 made FULL (CR 2026-09-25). Real Oracle text (tests/fixtures/review32_cards.json, from
data/cards.sqlite); every scenario checks the replay and a save and a load.

* 400.7 / 118.12: "Whenever you discard a card, [you may] exile that card from your graveyard." read "exile it", any zone: a discard a
  replacement sent to exile (madness 702.35a, Rest in Peace 614.1a) was "exiled" where it already was, so Containment Construct granted
  "you may play that card this turn" and Bag of Holding linked it for its return. The card was never in the graveyard: nothing is done.
* 608.2h / 707.2: "Exile target creature or enchantment. If it wasn't an Aura, create a token that's a copy of it" (Kaya, Intangible
  Slayer) copied the card as it is in exile (a Clone that was a Serra Angel came back a Clone; an exiled token, gone, made nothing at
  all). Her rulings: a permanent copying something else gives a copy of what it copied; a token gives a copy of what made it. Identity
  Thief ("you may exile another target nontoken creature. If you do, this creature becomes a copy of that creature") read the trigger's
  event instead of the exiled creature for its last known information, so a copied creature left it unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.plan import Plan
from app.rules.scripts import definitions
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of
from tests.test_rules_copy import characteristics
from tests.test_rules_wave30o_layers import attack, to_phase
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review32_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r32", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, prefer=(), limit=40):
    """Resolve everything; a choice is answered with ``prefer`` (option ids, in that order) or its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=(want or ids)[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def chars(s, card_id):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_id])


def discard_one(s, name):
    """Alice discards ``name`` through a test token's "{1}: Discard a card."."""
    driver = token_of(s, "p1", "Discarder", "Token Creature — Test", pt="1/1", text="{1}: Discard a card.")
    target = to_hand(s, name)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=driver.id, ability=0)
    return target


# -- "exile that card from your graveyard": only from the graveyard ----------------------------------------------------------------------------
def test_containment_construct_cant_exile_a_madness_card_that_never_reached_the_graveyard(cards):
    s = build(cards, ["Containment Construct", "Fiery Temper"])
    put(s, "Containment Construct")
    temper = discard_one(s, "Fiery Temper")  # madness: discarded into exile (702.35a); both triggers wait
    for _ in range(20):  # Construct: "yes" (exile it — it isn't in the graveyard); madness: "no" (it goes to the graveyard)
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else ["no"] if "no" in ids else ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[temper.id].zone == "p1:graveyard"
    assert not any("may play" in "".join(p.t or "" for p in e.parts) for e in s.state.log)  # 118.12: nothing exiled, no permission
    check(s)


def test_bag_of_holding_links_nothing_rest_in_peace_exiled_instead(cards):
    s = build(cards, ["Bag of Holding", "Grizzly Bears"], ["Rest in Peace"])
    put(s, "Rest in Peace", "p2")
    bag = put(s, "Bag of Holding")
    bears = discard_one(s, "Grizzly Bears")
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:exile"  # Rest in Peace's exile (614.1a), not the Bag's
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=bag.id, ability=2)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:exile"  # "all cards exiled with this artifact": none (607.2a)
    check(s)


# -- a copy of what an earlier instruction exiled: as it last existed on the battlefield (608.2h) -------------------------------------------
def clone_of_angel(s):
    angel = put(s, "Serra Angel")
    clone = to_hand(s, "Clone")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=clone.id)
    settle(s, prefer=(angel.id,))
    assert chars(s, clone.id).name == "Serra Angel"
    return clone


def kaya_minus_three(s, target_id):
    kaya = put(s, "Kaya, Intangible Slayer")
    act(s, "p1", type="counter", card_ids=[kaya.id], kind="loyalty", delta=3)
    act(s, "p1", type="activate_ability", card_id=kaya.id, ability=3, targets=[target_id])
    settle(s)
    return [c for c in s.state.cards.values() if c.is_token and c.controller == "p1" and c.zone.endswith(":battlefield")]


def test_kaya_copies_what_the_exiled_creature_was_copying(cards):
    s = build(cards, ["Kaya, Intangible Slayer", "Clone", "Serra Angel"])
    clone = clone_of_angel(s)
    [token] = kaya_minus_three(s, clone.id)
    ch = chars(s, token.id)
    assert s.state.cards[clone.id].zone == "p1:exile"
    assert ch.name == "Serra Angel" and ch.pt == (1, 1) and "Spirit" in ch.subtypes and ch.colors == frozenset({"W"})
    check(s)


def test_kaya_copies_an_exiled_token_as_its_creating_effect_made_it(cards):
    s = build(cards, ["Kaya, Intangible Slayer"])
    beast = token_of(s, "p2", "Beast", "Token Creature — Beast", pt="3/3", colors=("G",))
    [token] = kaya_minus_three(s, beast.id)
    ch = chars(s, token.id)
    assert beast.id not in s.state.cards or not s.state.cards[beast.id].zone.endswith(":battlefield")
    assert ch.name == "Beast" and ch.pt == (1, 1) and {"Beast", "Spirit"} <= ch.subtypes and ch.colors == frozenset({"W"})
    check(s)


def test_identity_thief_becomes_what_the_exiled_creature_was_copying(cards):
    s = build(cards, ["Identity Thief", "Clone", "Serra Angel"])
    clone = clone_of_angel(s)
    thief = put(s, "Identity Thief")
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="set_prefs", hold_priority=True)
    attack(s, thief)
    settle(s, prefer=(clone.id, "yes"))
    ch = chars(s, thief.id)
    assert s.state.cards[clone.id].zone == "p1:exile" and ch.name == "Serra Angel" and ch.pt == (4, 4)
    check(s)


# -- "When you next cast …, copy that spell an additional time / for each …. You may choose new targets for the copy." ------------------------
def test_howl_of_the_horde_raid_copy_may_choose_a_new_target_too(cards):
    """707.10c: each copy's controller may choose new targets; the raid line's "an additional time" left its "You may choose new targets"
    outside the delayed trigger, so it ran as Howl resolved (no copy yet) and the raid copy kept its target with no question."""
    s = build(cards, ["Howl of the Horde", "Lightning Bolt", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    attack(s, bears)
    to_phase(s, "main2")  # raid: Alice attacked this turn (Bob took 2)
    howl, bolt = to_hand(s, "Howl of the Horde"), to_hand(s, "Lightning Bolt")
    mana(s, R=4)
    act(s, "p1", type="cast_spell", card_id=howl.id)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    asked = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.prompt)
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["p1"] if "new one" in d.prompt else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert sum("choose a new one" in p for p in asked) == 2  # both copies were asked: both went to Alice, the Bolt to Bob
    assert s.state.players["p1"].life == 40 - 6 and s.state.players["p2"].life == 40 - 2 - 3
    check(s)


@pytest.mark.parametrize("name", ["Howl of the Horde", "Thunderclap Drake"])
def test_the_new_targets_sentence_is_the_delayed_copys(name):
    data = next(c for c in DATA if c["name"] == name)
    defs = definitions(characteristics(name, data["type_line"], data["oracle_text"], spell="Sorcery" in data["type_line"]))
    effects = [e["do"] for d in defs.values() for e in d.get("effects") or []]
    assert "copy_new_targets" not in effects and "deferred:copy_new_targets" in effects


def test_the_madness_card_is_not_castable_through_the_construct(cards):
    """The permission the Construct would have granted is the one a cast from exile would use: none is there (the madness card is cast for
    its madness cost only, by its own trigger)."""
    s = build(cards, ["Containment Construct", "Fiery Temper"])
    put(s, "Containment Construct")
    for prefs in s.state.rules.prefs.values():  # (both players stop at every object on the stack)
        prefs.response = "on"
    temper = discard_one(s, "Fiery Temper")
    for _ in range(6):  # resolve only the Construct's trigger (it is on top: ordered last), saying yes
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "order":
            ids = [o.id for o in d.options]
            act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)
        elif d.kind == "confirm" and "Containment" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
            break
    assert s.state.cards[temper.id].zone == "p1:exile"
    mana(s, R=2, C=1)
    with pytest.raises(ActionError, match="from your hand"):
        act(s, "p1", type="cast_spell", card_id=temper.id, targets=["p2"])
    check(s)
