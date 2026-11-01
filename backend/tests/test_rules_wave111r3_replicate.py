"""Wave 111R3: granted replicate as its own instances (rules/wave111r3_replicate.py). Hugh, First of Many: "Artifact spells you cast have replicate
{2}{U}." (702.56a); each grant is an instance paid separately, with its own cast trigger (702.56b); apart from the spell's own multikicker
(Everflowing Chalice: 601.2b, both announced, one total cost 601.2f) and with {X} in its mana cost (Hangarback Walker: the copies copy X,
707.10). Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import pt
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real, to_hand

HUGH = real("Hugh, First of Many", "{1}{W}{U}{B}", 4, "Legendary Artifact Creature — Borg",
            "Artifact spells you cast have replicate {2}{U}. (Whenever you cast an artifact spell, copy it for each time you paid its replicate cost. "
            "Each copy becomes a token.)", ("3", "4"), "BUW")
EXTRA = [
    HUGH,
    real("Mind Stone", "{2}", 2, "Artifact", "{T}: Add {C}.\n{1}, {T}, Sacrifice this artifact: Draw a card.", None, ""),
    real("Everflowing Chalice", "{0}", 0, "Artifact", "Multikicker {2} (You may pay an additional {2} any number of times as you cast this spell.)\n"
         "This artifact enters with a charge counter on it for each time it was kicked.\n{T}: Add {C} for each charge counter on this artifact.", None, ""),
    real("Hangarback Walker", "{X}{X}", 0, "Artifact Creature — Construct",
         "This creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a 1/1 colorless Thopter artifact creature token with flying "
         "for each +1/+1 counter on this creature.\n{1}, {T}: Put a +1/+1 counter on this creature.", ("0", "0"), ""),
    real("Hatchery Sliver", "{1}{G}", 2, "Creature — Sliver",
         "Replicate {1}{G} (When you cast this spell, copy it for each time you paid its replicate cost.)\nEach Sliver spell you cast has replicate. "
         "The replicate cost is equal to its mana cost. (A copy of a permanent spell becomes a token.)", ("2", "2"), "G"),
    real("Sliver Construct", "{3}", 3, "Artifact Creature — Sliver Construct", "", ("2", "2"), ""),
    real("Ashnod's Altar", "{3}", 3, "Artifact", "Sacrifice a creature: Add {C}{C}.", None, ""),
    real("Test Bear 111R3", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
NAMES = ["Hugh, First of Many"]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def mine(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def hugh_copy(s, pid="p1"):
    """A nonlegendary copy of Hugh (a token with its text: the legend rule leaves both, 704.5j)."""
    act(s, pid, type="create_token", player=pid, token={"name": "Hugh Copy", "type_line": "Artifact Creature — Borg", "power": "3",
                                                        "toughness": "4", "text": "Artifact spells you cast have replicate {2}{U}."})


def test_the_grant_reads_as_a_static():
    from app.rules import permissions

    assert permissions.define_static("Artifact spells you cast have replicate {2}{U}.", "static")["kw"] == "Replicate {2}{U}"
    assert permissions.define_static("Artifact spells you cast have replicate {X}.", "static") is None  # (a cost with X: not read)


@pytest.mark.parametrize("paid", [0, 1, 2])
def test_artifact_spell_copied_for_each_payment(cards, paid):  # 702.56a: copies of a permanent spell become tokens (707.10f)
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    mana(s, C=2 + 2 * paid, U=paid)
    c = to_hand(s, "Mind Stone")
    act(s, "p1", type="cast_spell", card_id=c.id, replicate=[paid] if paid else [])
    answer(s)
    stones = mine(s, "Mind Stone")
    assert len(stones) == 1 + paid and sum(x.is_token for x in stones) == paid
    check(s)


def test_the_payment_is_mana(cards):  # 601.2f: {2}{U} for each time, with the spell's {2}: not enough mana, no cast
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    mana(s, C=4)
    c = to_hand(s, "Mind Stone")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, replicate=[1])


def test_a_kicker_count_still_pays_the_one_grant(cards):  # (the way wave 110A's grants were paid: kicker, for a spell without a kicker of its own)
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    mana(s, C=4, U=1)
    c = to_hand(s, "Mind Stone")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    assert len(mine(s, "Mind Stone")) == 2
    check(s)


def test_a_payment_saved_before_wave_111r_still_pays_the_grant(cards):  # (an intent saved mid-payment by wave 110A's engine: the count in kicker)
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    act(s, "p1", type="set_prefs", payment="self")
    mana(s, U=1)
    c = to_hand(s, "Mind Stone")
    act(s, "p1", type="cast_spell", card_id=c.id, replicate=[1])
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "pay_mana"
    intent = d.resume["intent"]
    intent["kicker"] = intent.pop("replicate")[0]  # (no replicate fields then)
    intent.pop("replicate_from")
    mana(s, C=4)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"] if any(o.id == "pay" for o in d.options) else [d.options[0].id])
    answer(s)
    assert len(mine(s, "Mind Stone")) == 2
    check(s)


def test_not_for_other_spells(cards):
    s = build(cards, ["Hugh, First of Many", "Test Bear 111R3"])
    put(s, "Hugh, First of Many")
    mana(s, G=2, C=2, U=1)
    c = to_hand(s, "Test Bear 111R3")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, replicate=[1])


def test_not_for_an_opponents_spells(cards):  # "you cast": Bob's Hugh gives Alice's artifact spells nothing
    s = build(cards, ["Mind Stone"], ["Hugh, First of Many"])
    put(s, "Hugh, First of Many", "p2")
    mana(s, C=4, U=1)
    c = to_hand(s, "Mind Stone")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, replicate=[1])


def test_own_multikicker_and_replicate_both_paid(cards):  # 601.2b: two optional costs, two counts; the copy copies the kicks (707.10)
    s = build(cards, ["Hugh, First of Many", "Everflowing Chalice"])
    put(s, "Hugh, First of Many")
    mana(s, C=2 * 2 + 2, U=1)
    c = to_hand(s, "Everflowing Chalice")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2, replicate=[1])
    answer(s)
    chalices = mine(s, "Everflowing Chalice")
    assert len(chalices) == 2 and sorted(x.counters.get("charge", 0) for x in chalices) == [2, 2]
    check(s)


def test_own_multikicker_alone_is_not_replicated(cards):
    s = build(cards, ["Hugh, First of Many", "Everflowing Chalice"])
    put(s, "Hugh, First of Many")
    mana(s, C=2)
    c = to_hand(s, "Everflowing Chalice")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    chalices = mine(s, "Everflowing Chalice")
    assert len(chalices) == 1 and chalices[0].counters.get("charge") == 1
    check(s)


def test_an_x_spell_has_it_and_its_copies_copy_x(cards):  # 601.2b: X and the replicate count are separate announcements; 707.10: X copied
    s = build(cards, ["Hugh, First of Many", "Hangarback Walker"])
    put(s, "Hugh, First of Many")
    mana(s, C=2 + 2, U=1)
    c = to_hand(s, "Hangarback Walker")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=1, replicate=[1])
    answer(s)
    walkers = mine(s, "Hangarback Walker")
    assert len(walkers) == 2 and all(pt(s, w.name) == (1, 1) for w in walkers[:1])
    assert sorted(x.counters.get("+1/+1", 0) for x in walkers) == [1, 1]
    check(s)


def test_two_grants_are_paid_separately_and_trigger_separately(cards):  # 702.56b
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    hugh_copy(s)
    c = to_hand(s, "Mind Stone")
    hints = s.view("p1")["rules"]["hints"]
    assert hints.get("replicate111r3", {}).get(c.id) is None  # (no mana: not castable, no hint)
    mana(s, C=2 + 2 * 3, U=3)
    hints = s.view("p1")["rules"]["hints"]
    assert len(hints["replicate111r3"][c.id]) == 2
    act(s, "p1", type="cast_spell", card_id=c.id, replicate=[1, 2])
    d = s.state.rules.decision  # one "when you cast" trigger per instance, each with its own count: their controller orders them
    assert d is not None and len(d.options) == 2
    answer(s)
    assert len(mine(s, "Mind Stone")) == 4
    check(s)


def test_a_count_for_a_grant_the_spell_lacks_is_refused(cards):
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    mana(s, C=8, U=3)
    c = to_hand(s, "Mind Stone")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, replicate=[0, 1])


def test_hatchery_sliver_and_hugh_on_an_artifact_sliver(cards):  # 702.56b: two instances, two costs ({3} and {2}{U})
    s = build(cards, ["Hugh, First of Many", "Hatchery Sliver", "Sliver Construct"])
    put(s, "Hugh, First of Many")
    put(s, "Hatchery Sliver")
    mana(s, C=3 + 3 + 2, U=1)
    c = to_hand(s, "Sliver Construct")
    labels = s.view("p1")["rules"]["hints"]["replicate111r3"][c.id]
    order = [0, 0]
    order[next(i for i, label in enumerate(labels) if label.startswith("Replicate {3}"))] = 1
    order[next(i for i, label in enumerate(labels) if label.startswith("Replicate {2}{U}"))] = 1
    act(s, "p1", type="cast_spell", card_id=c.id, replicate=order)
    answer(s)
    assert len(mine(s, "Sliver Construct")) == 3
    check(s)


def test_hatchery_slivers_own_replicate_and_a_granted_one(cards):  # its printed replicate (kicker's count) and another Hatchery's grant
    s = build(cards, ["Hatchery Sliver"], ["Hatchery Sliver"])
    other = put(s, "Hatchery Sliver", "p2")
    act(s, "p2", type="set_controller", card_ids=[other.id], player="p1")
    mana(s, G=3, C=3)
    c = to_hand(s, "Hatchery Sliver")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, replicate=[1])
    answer(s)
    assert len(mine(s, "Hatchery Sliver")) == 4  # the other Hatchery, the spell, one copy for each instance
    check(s)


def test_hugh_is_held_while_its_payment_is_made(cards):  # the cast names Hugh (CastSpell.replicate_from): not sacrificed for mana mid-payment
    s = build(cards, ["Hugh, First of Many", "Mind Stone", "Ashnod's Altar", "Test Bear 111R3"])
    hugh = put(s, "Hugh, First of Many")
    bear = put(s, "Test Bear 111R3")
    altar = put(s, "Ashnod's Altar")
    act(s, "p1", type="set_prefs", payment="self")
    mana(s, U=1)
    c = to_hand(s, "Mind Stone")
    act(s, "p1", type="cast_spell", card_id=c.id, replicate=[1])
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    with pytest.raises(ActionError):  # (not offered: the cast names it)
        act(s, "p1", type="activate_ability", card_id=altar.id, ability=0, cost_choices=[{"component": 0, "cards": [hugh.id]}])
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0, cost_choices=[{"component": 0, "cards": [bear.id]}])
    mana(s, C=2)
    d = s.state.rules.decision
    if d is not None and d.resume.get("step") == "pay_mana":
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"] if any(o.id == "pay" for o in d.options) else [d.options[0].id])
    answer(s)
    assert s.state.cards[hugh.id].zone == "p1:battlefield" and len(mine(s, "Mind Stone")) == 2
    check(s)


def test_sacrificed_before_the_cast_gives_nothing(cards):  # 113.6: the static works only on the battlefield
    s = build(cards, ["Hugh, First of Many", "Mind Stone", "Ashnod's Altar"])
    hugh = put(s, "Hugh, First of Many")
    altar = put(s, "Ashnod's Altar")
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0, cost_choices=[{"component": 0, "cards": [hugh.id]}])
    mana(s, C=2, U=1)
    c = to_hand(s, "Mind Stone")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, replicate=[1])
    assert "replicate111r3" not in s.view("p1")["rules"]["hints"]
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert len(mine(s, "Mind Stone")) == 1
    check(s)


# -- a cast without paying its mana cost (118.9d) ------------------------------------------------------------------------------------------------
def free_cast(s, name):
    c = to_hand(s, name)
    s.state.rules.free_casts.append(c.id)
    act(s, "p1", type="cast_spell", card_id=c.id, free=True)
    return c


def test_free_cast_offers_each_count(cards):
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    mana(s, C=4, U=2)
    free_cast(s, "Mind Stone")
    ids = {o.id for o in s.state.rules.decision.options}
    assert {"replicate111r3:0:1", "replicate111r3:0:2", "replicate111r3:0:other"} <= ids and "replicate111r3:0:3" not in ids
    answer(s, ["replicate111r3:0:2"])
    answer(s)
    assert len(mine(s, "Mind Stone")) == 3
    check(s)


def test_free_cast_typed_count(cards):
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    mana(s, C=2 * 7, U=7)
    free_cast(s, "Mind Stone")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["replicate111r3:0:other"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, name="7")
    answer(s)
    assert len(mine(s, "Mind Stone")) == 8
    check(s)


def test_free_cast_paying_nothing(cards):
    s = build(cards, ["Hugh, First of Many", "Mind Stone"])
    put(s, "Hugh, First of Many")
    free_cast(s, "Mind Stone")
    answer(s, [])
    answer(s)
    assert len(mine(s, "Mind Stone")) == 1
    check(s)
