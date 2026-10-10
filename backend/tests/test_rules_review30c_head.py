"""Review 30c (Opus head review, round 3) of waves 30Q-30S (CR 2026-09-25), real Oracle text (tests/fixtures/wave30q_cast_permissions_cards.json,
wave30s_cards.json and review30c_head_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 400.7 / Muldrotha ruling 2020-11-10: "If you play a card from your graveyard and then have a new Muldrotha come under your control in the same turn,
  you may play another land or spell of that type" (Lurrus, Arcade Gannon: the same) — a "once" use belongs to the object, not to the physical card.
* 601.3 / Chainer ruling 2019-08-23: "if another effect allows you to cast a creature card from your graveyard, you may use that permission and later
  use Chainer's permission" — the engine, picking the permission for the caster, must not spend a one-spell permission an unlimited one covers.
* 202.3e / 601.2e / Lurrus ruling 2020-04-17: "For spells with {X} in their mana costs, use the value chosen for X to determine the spell's mana value"
  — a permission for a spell "with mana value 3 or less" doesn't cover one cast with a bigger X.
* Brood Keeper ruling 2014-07-18: it triggers "whenever an Aura enters the battlefield attached to Brood Keeper" — a Role token created attached and
  an Aura card returned to the battlefield attached too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.casting import castable
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import put_in, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

_DIR = Path(__file__).parent / "fixtures"
_KNOWN = {c["name"] for c in fixture_cards()}
_SEEN: set[str] = set()
EXTRA = []
for _file, _set in (("wave30q_cast_permissions_cards.json", "q"), ("wave30s_cards.json", "s"), ("wave30s_effects_cards.json", "e"),
                      ("review30c_head_cards.json", "h")):
    for _i, _c in enumerate(json.loads((_DIR / _file).read_text("utf-8"))):
        if _c["name"] not in _KNOWN and _c["name"] not in _SEEN:
            _SEEN.add(_c["name"])
            EXTRA.append(card(_c["name"], set_code="r30c", number=f"{_set}{_i:02d}", **({"image_uris": None} if _c.get("card_faces") else {}),
                              **{k: v for k, v in _c.items() if k != "name"}))


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def castable_now(s, cards, name, pid="p1"):
    return castable(s.state, pid, card_named(s, name, pid), cards, check_priority=False)


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s)


def grave(s, *names, pid="p1"):
    for n in names:
        put_in(s, n, "graveyard", pid)


def on_table(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield")]


# ---- 400.7: a new Muldrotha is a new object with new uses ---------------------------------------------------------------------------------------
def test_a_new_muldrotha_lets_you_cast_another_creature_spell_that_turn(cards):
    s = build(cards, ["Muldrotha, the Gravetide", "Grizzly Bears", "Ambush Viper"])
    muldrotha = put(s, "Muldrotha, the Gravetide")
    grave(s, "Grizzly Bears", "Ambush Viper")
    mana(s, G=4)
    cast(s, "Grizzly Bears")
    assert card_named(s, "Grizzly Bears").zone == "p1:battlefield" and not castable_now(s, cards, "Ambush Viper")  # (the creature use is spent)
    put_in(s, "Muldrotha, the Gravetide", "graveyard")
    put(s, "Muldrotha, the Gravetide")  # a new object (400.7): "a new Muldrotha come under your control in the same turn"
    assert s.state.cards[muldrotha.id].zone == "p1:battlefield" and castable_now(s, cards, "Ambush Viper")
    cast(s, "Ambush Viper")
    assert card_named(s, "Ambush Viper").zone == "p1:battlefield"
    check(s)


# ---- 601.3: the one-spell permission is kept when an unlimited one covers the cast --------------------------------------------------------------
def test_chainers_one_creature_spell_is_kept_when_lilianas_zombie_permission_covers_the_cast(cards):
    s = build(cards, ["Chainer, Nightmare Adept", "Liliana, Untouched by Death", "Dregscape Zombie", "Twisted Abomination", "Grizzly Bears",
                      "Lightning Bolt"])
    chainer, lili = put(s, "Chainer, Nightmare Adept"), put(s, "Liliana, Untouched by Death")
    act(s, "p1", type="set_counter", card_id=lili.id, kind="loyalty", value=4)
    grave(s, "Dregscape Zombie", "Twisted Abomination", "Grizzly Bears")
    to_hand(s, "Lightning Bolt")
    act(s, "p1", type="activate_ability", card_id=chainer.id, ability=0)  # Chainer's permission first: one creature spell this turn
    settle(s, prefer=[card_named(s, "Lightning Bolt").id])
    act(s, "p1", type="activate_ability", card_id=lili.id, ability=2)  # then Liliana's: any number of Zombie spells this turn
    settle(s)
    mana(s, B=8, G=2)
    cast(s, "Dregscape Zombie")
    cast(s, "Twisted Abomination")
    assert castable_now(s, cards, "Grizzly Bears")  # (Chainer's one creature spell is still there)
    cast(s, "Grizzly Bears")
    assert {"Dregscape Zombie", "Twisted Abomination", "Grizzly Bears"} <= {c.name for c in s.state.cards.values() if c.zone == "p1:battlefield"}
    check(s)


@pytest.mark.parametrize("first", ["Serra Paragon", "Karador, Ghost Chieftain"])
def test_the_permission_picked_for_the_caster_is_not_one_with_a_rider_when_a_plain_one_covers_the_cast(cards, first):
    """Muldrotha ruling 2020-11-10: the caster announces the permission used. The engine picks it: never Serra Paragon's (the permanent gains
    "… exile it …") when Karador's covers the same cast, whichever came first; Paragon's use is left for a land."""
    s = build(cards, ["Serra Paragon", "Karador, Ghost Chieftain", "Grizzly Bears"])
    put(s, first)
    put(s, "Karador, Ghost Chieftain" if first == "Serra Paragon" else "Serra Paragon")
    grave(s, "Grizzly Bears")
    put_in(s, "Forest", "graveyard")
    mana(s, G=2)
    cast(s, "Grizzly Bears")
    bear = card_named(s, "Grizzly Bears")
    assert bear.zone == "p1:battlefield" and not any("exile it" in a.text for a in Plan(s.state, "p1", s.cards, None).ch(bear).abilities)
    act(s, "p1", type="play_land", card_id=next(c.id for c in s.state.cards.values() if c.zone == "p1:graveyard" and c.name == "Forest"))
    check(s)


# ---- 202.3e: the X chosen counts toward "with mana value 3 or less"-----------------------------------------------------------------------------
def test_serra_paragon_does_not_cover_a_spell_whose_x_makes_it_too_big(cards):
    s = build(cards, ["Serra Paragon", "Hangarback Walker"])
    put(s, "Serra Paragon")
    grave(s, "Hangarback Walker")
    mana(s, G=6)
    assert castable_now(s, cards, "Hangarback Walker")  # (X 0 or 1 fits)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Hangarback Walker").id, x_value=2)  # mana value 4
    assert card_named(s, "Hangarback Walker").zone == "p1:graveyard"
    cast(s, "Hangarback Walker", x_value=1)  # mana value 2
    assert card_named(s, "Hangarback Walker").zone == "p1:battlefield" and card_named(s, "Hangarback Walker").counters.get("+1/+1") == 1
    check(s)


# ---- Brood Keeper: an Aura entering attached ---------------------------------------------------------------------------------------------------
def test_brood_keeper_triggers_on_a_role_token_created_attached_to_it(cards):
    s = build(cards, ["Brood Keeper", "Royal Treatment"])
    keeper = put(s, "Brood Keeper")
    to_hand(s, "Royal Treatment")
    mana(s, G=1)
    cast(s, "Royal Treatment", targets=[keeper.id])
    assert any(c.attached_to == keeper.id for c in s.state.cards.values())  # (the Royal Role)
    assert len(on_table(s, "Dragon")) == 1
    check(s)


def test_brood_keeper_triggers_on_an_aura_card_returned_attached_to_it(cards):
    s = build(cards, ["Brood Keeper", "Gryff's Boon"])
    keeper = put(s, "Brood Keeper")
    boon = put_in(s, "Gryff's Boon", "graveyard")
    mana(s, W=4)
    act(s, "p1", type="activate_ability", card_id=boon.id, ability=2, targets=[keeper.id])
    settle(s)
    assert s.state.cards[boon.id].attached_to == keeper.id
    assert len(on_table(s, "Dragon")) == 1
    check(s)


# ---- Valduk: what was last attached, a token Aura that ceased to exist included ----------------------------------------------------------------
def test_valduk_that_left_counts_a_role_token_that_ceased_to_exist(cards):
    """608.2h, Valduk ruling 2022-12-08: "use the number of Auras and Equipment that were last attached to it before it left the battlefield" — the
    Royal Role went to the graveyard with it and ceased to exist (704.5d, 111.7), but it was attached."""
    s = build(cards, ["Valduk, Keeper of the Flame", "Bonesplitter", "Royal Treatment"])
    valduk = put(s, "Valduk, Keeper of the Flame")
    act(s, "p1", type="attach", card_ids=[put(s, "Bonesplitter").id], to=valduk.id)
    to_hand(s, "Royal Treatment")
    mana(s, G=1)
    cast(s, "Royal Treatment", targets=[valduk.id])
    assert sum(1 for c in s.state.cards.values() if c.attached_to == valduk.id) == 2
    act(s, "p1", type="set_stops", own=["begin_combat"], smart_pass=False)
    for _ in range(6):  # → the trigger waits on the stack for priority
        if s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.zones.get("stack")
    act(s, "p1", type="move", card_ids=[valduk.id], to={"zone": "graveyard"})
    settle(s)
    assert not any(c.name == "Royal Role" for c in s.state.cards.values())  # (the token is gone)
    assert len(on_table(s, "Elemental")) == 2
    check(s)
