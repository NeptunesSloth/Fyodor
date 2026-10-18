"""Wave 32D: the player announces which limited permission a cast or play uses (CR 2026-09-25), real Oracle text (tests/fixtures/wave30q_cast_permissions_cards.json
and tests/fixtures/cards.py, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 601.2: the player announces the permission a spell is cast with; 305.1 likewise a land played from the graveyard.
* Muldrotha rulings (2020-11-10): an artifact creature spell may be the artifact or the creature; the player chooses which permission is used — so two
  limited ones that use up different things (Lurrus's once, Karador's once, Serra Paragon's once, Muldrotha's type) are asked, an unlimited one is not.
* The answer is the action's ``via`` (a Grant's ``use``): asked as a decision when absent and more than one fits, validated when given.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.rules import permissions
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import put_in, settle  # noqa: F401
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30q_cast_permissions_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t32d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
MULDROTHA, LURRUS, PARAGON, KARADOR = "Muldrotha, the Gravetide", "Lurrus of the Dream-Den", "Serra Paragon", "Karador, Ghost Chieftain"


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def cast(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id, **kw)


def asked(s):
    d = s.state.rules.decision
    return None if d is None else sorted(o.label for o in d.options)


def answer(s, label):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])
    settle(s)


def cast_as(s, name, label):
    """Cast it, answering the question (there must be one) with the option of that label."""
    cast(s, name)
    answer(s, label)


def where(s, name):
    return card_named(s, name).zone


def table(cards, *names, extra=()):
    s = build(cards, [*names, *extra])
    for n in names:
        if n in (MULDROTHA, LURRUS, PARAGON, KARADOR, "Chainer, Nightmare Adept"):
            put(s, n)
    return s


def uses(s, cards, name):
    """The ``use`` of every permission that covers casting this card now."""
    c = card_named(s, name)
    return {g.label: g.use for g in permissions.grants(s.state, "p1", c, Plan(s.state, "p1", s.cards, None).ch(c), cards, verb="cast")}


# ---- Muldrotha: an artifact creature card is the artifact use or the creature use, the player's choice ---------------------------------------
def test_muldrotha_artifact_creature_played_as_the_artifact_leaves_the_creature_use(cards):
    s = table(cards, MULDROTHA, "Perilous Myr", "Grizzly Bears", "Shimmer Myr", "Bonesplitter")
    for n in ("Perilous Myr", "Grizzly Bears", "Shimmer Myr", "Bonesplitter"):
        put_in(s, n, "graveyard")
    mana(s, G=14)
    cast(s, "Perilous Myr")
    assert asked(s) == ["Artifact", "Creature"]
    check(s)  # (the question is part of the saved game)
    answer(s, "Artifact")
    assert where(s, "Perilous Myr") == "p1:battlefield"
    cast(s, "Grizzly Bears")  # the creature use is still there, and it is the only one that fits: no question
    assert asked(s) is None
    settle(s)
    assert where(s, "Grizzly Bears") == "p1:battlefield"
    for n in ("Shimmer Myr", "Bonesplitter"):  # both of the uses are spent
        with pytest.raises(ActionError):
            cast(s, n)
    check(s)


def test_the_type_can_be_named_with_the_action_and_an_answer_saved_before_wave_32d_still_works(cards):
    """``slot`` (wave 30Q) still names the type; a decision saved with its option ids the types and no ``field`` sets it."""
    s = table(cards, MULDROTHA, "Perilous Myr", "Shimmer Myr")
    put_in(s, "Perilous Myr", "graveyard")
    put_in(s, "Shimmer Myr", "graveyard")
    mana(s, G=14)
    cast(s, "Perilous Myr", slot="Artifact")
    assert asked(s) is None
    settle(s)
    cast(s, "Shimmer Myr")  # only the creature use is left
    assert asked(s) is None
    settle(s)
    assert where(s, "Shimmer Myr") == "p1:battlefield"
    s2 = table(cards, MULDROTHA, "Perilous Myr")
    put_in(s2, "Perilous Myr", "graveyard")
    mana(s2, G=4)
    cast(s2, "Perilous Myr")
    d = s2.state.rules.decision
    for o in d.options:
        o.id = o.label  # (as wave 30Q saved it: the option ids are the types)
    d.resume.pop("field")
    answer(s2, "Creature")
    used = [k for k in s2.state.rules.once_per_turn if ":permission:" in k]
    assert where(s2, "Perilous Myr") == "p1:battlefield" and any(k.endswith(":Creature") for k in used) and not any(k.endswith(":Artifact") for k in used)
    check(s2)
    check(s)


# ---- Lurrus and Muldrotha both cover the same spell: the player picks what to spend -------------------------------------------------------
@pytest.mark.parametrize("for_the_myr", [LURRUS, "Muldrotha, the Gravetide (Artifact)"])
def test_lurrus_or_muldrotha_for_the_same_permanent_spell_is_the_players_choice(cards, for_the_myr):
    """Grizzly Bears (mana value 2) and Perilous Myr (2) are covered by Lurrus's once and by Muldrotha's types; Shimmer Myr (3) only by Muldrotha's. The
    Bears take Muldrotha's creature use, so spending Lurrus's on the Myr leaves the artifact use for Shimmer Myr; spending Muldrotha's artifact use on the Myr
    leaves nothing for it — a choice the engine's own order could have got wrong."""
    s = table(cards, LURRUS, MULDROTHA, "Grizzly Bears", "Perilous Myr", "Shimmer Myr")
    for n in ("Grizzly Bears", "Perilous Myr", "Shimmer Myr"):
        put_in(s, n, "graveyard")
    mana(s, G=14)
    cast(s, "Grizzly Bears")
    assert asked(s) == [LURRUS, "Muldrotha, the Gravetide (Creature)"]
    check(s)
    answer(s, "Muldrotha, the Gravetide (Creature)")
    cast(s, "Perilous Myr")
    assert asked(s) == [LURRUS, "Muldrotha, the Gravetide (Artifact)"]  # (Lurrus's once, or the artifact use: the creature use is spent)
    answer(s, for_the_myr)
    assert where(s, "Perilous Myr") == "p1:battlefield"
    if for_the_myr == LURRUS:
        cast(s, "Shimmer Myr")  # only the artifact use covers a mana value of 3, and it is left
        assert asked(s) is None
        settle(s)
        assert where(s, "Shimmer Myr") == "p1:battlefield"
    else:
        with pytest.raises(ActionError):
            cast(s, "Shimmer Myr")
    check(s)


def test_the_permission_can_be_named_with_the_action_and_a_wrong_one_is_refused(cards):
    s = table(cards, LURRUS, MULDROTHA, "Grizzly Bears", "Shimmer Myr", "Bonesplitter", extra=["Command Tower"])
    for n in ("Grizzly Bears", "Shimmer Myr", "Bonesplitter"):
        put_in(s, n, "graveyard")
    to_hand(s, "Command Tower")
    mana(s, G=14)
    bears = uses(s, cards, "Grizzly Bears")
    assert set(bears) == {LURRUS, MULDROTHA} and len(set(bears.values())) == 2
    lurrus, muldrotha = bears[LURRUS], bears[MULDROTHA]
    for n, via in (("Grizzly Bears", "nonsense"), ("Shimmer Myr", lurrus),  # (mana value 3: Lurrus doesn't cover it)
                   ("Bonesplitter", muldrotha.replace("Creature", "Artifact") + "x"), ("Bonesplitter", muldrotha)):  # (not a creature: that use isn't its)
        with pytest.raises(ActionError):
            cast(s, n, via=via)
    cast(s, "Grizzly Bears", via=lurrus)  # named: no question
    assert asked(s) is None
    settle(s)
    assert where(s, "Grizzly Bears") == "p1:battlefield" and LURRUS not in uses(s, cards, "Shimmer Myr")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id, via=lurrus)  # (a land from the hand uses no permission)
    check(s)
    # the creature use is still there for the next creature card (the default way, with nothing else to choose between)
    s2 = table(cards, LURRUS, MULDROTHA, "Grizzly Bears", "Ambush Viper")
    put_in(s2, "Grizzly Bears", "graveyard")
    put_in(s2, "Ambush Viper", "graveyard")
    mana(s2, G=8)
    cast(s2, "Grizzly Bears", via=uses(s2, cards, "Grizzly Bears")[MULDROTHA])
    settle(s2)
    cast(s2, "Ambush Viper")  # Lurrus's once is the only one left
    assert asked(s2) is None
    settle(s2)
    assert where(s2, "Ambush Viper") == "p1:battlefield"
    check(s2)


def test_a_single_limited_permission_is_not_asked_about(cards):
    s = table(cards, LURRUS, "Grizzly Bears")
    put_in(s, "Grizzly Bears", "graveyard")
    mana(s, G=2)
    cast(s, "Grizzly Bears")
    assert asked(s) is None
    settle(s)
    assert where(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


# ---- Karador / Serra Paragon: a land played from the graveyard uses one of the limited permissions -------------------------------------------
def test_a_land_from_the_graveyard_is_played_with_muldrotha_or_serra_paragon_as_the_player_chooses(cards):
    s = table(cards, MULDROTHA, PARAGON, "Grizzly Bears")
    put_in(s, "Forest", "graveyard")
    put_in(s, "Grizzly Bears", "graveyard")
    mana(s, G=4)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:graveyard")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=forest.id, via="nonsense")
    act(s, "p1", type="play_land", card_id=forest.id)
    assert asked(s) == ["Muldrotha, the Gravetide (Land)", PARAGON]
    check(s)
    answer(s, "Muldrotha, the Gravetide (Land)")
    assert forest.id in {c.id for c in s.state.cards.values() if c.zone == "p1:battlefield"}
    cast(s, "Grizzly Bears")  # Paragon's use is still there, and Muldrotha's creature one: asked again
    assert asked(s) == ["Muldrotha, the Gravetide (Creature)", PARAGON]
    answer(s, PARAGON)
    bear = card_named(s, "Grizzly Bears")
    assert bear.zone == "p1:battlefield" and any("exile it" in a.text for a in Plan(s.state, "p1", s.cards, None).ch(bear).abilities)
    check(s)


def test_muldrotha_land_use_named_with_the_action_leaves_serra_paragons(cards):
    s = table(cards, MULDROTHA, PARAGON, "Command Tower")
    put_in(s, "Command Tower", "graveyard")
    tower = card_named(s, "Command Tower")
    muldrotha = next(g.use for g in permissions.grants(s.state, "p1", tower, Plan(s.state, "p1", s.cards, None).ch(tower), cards, verb="play")
                     if g.label == MULDROTHA)
    act(s, "p1", type="play_land", card_id=tower.id, via=muldrotha)
    assert asked(s) is None and card_named(s, "Command Tower").zone == "p1:battlefield"
    assert not [g for g in permissions.grants(s.state, "p1", tower, Plan(s.state, "p1", s.cards, None).ch(tower), cards, verb="play")
                if g.label == MULDROTHA]
    check(s)


# ---- a stored one-spell permission (Chainer's) is a use too ---------------------------------------------------------------------------------
def test_chainers_one_creature_spell_and_muldrothas_creature_use_are_the_players_choice(cards):
    s = table(cards, MULDROTHA, "Chainer, Nightmare Adept", "Grizzly Bears", "Ambush Viper", extra=["Lightning Bolt"])
    chainer = card_named(s, "Chainer, Nightmare Adept")
    put_in(s, "Grizzly Bears", "graveyard")
    put_in(s, "Ambush Viper", "graveyard")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, G=8)
    act(s, "p1", type="activate_ability", card_id=chainer.id, ability=0)  # "Discard a card: You may cast a creature spell from your graveyard this turn."
    settle(s, prefer=[bolt.id])
    cast(s, "Grizzly Bears")
    labels = asked(s)
    assert len(labels) == 2 and "Muldrotha, the Gravetide (Creature)" in labels
    check(s)
    answer(s, next(label for label in labels if label != "Muldrotha, the Gravetide (Creature)"))  # Chainer's
    cast(s, "Ambush Viper")  # the creature use is the only one left
    assert asked(s) is None
    settle(s)
    assert {"Grizzly Bears", "Ambush Viper"} <= {c.name for c in s.state.cards.values() if c.zone == "p1:battlefield"}
    check(s)
