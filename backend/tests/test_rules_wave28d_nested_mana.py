"""Wave 28D: mana abilities whose cost chooses objects, activated while paying (CR 2026-09-25). Real Oracle text; every scenario checks the
replay and a save and a load.

* 605.3a: a player may activate a mana ability whenever they have priority, or whenever they're told to pay a cost or an effect asks for a
  mana payment, so Ashnod's Altar and Phyrexian Altar can be used in the middle of a "tap your mana" prompt. 601.2g-h: the costs of the
  mana ability (the creature sacrificed) are chosen as they're paid, in a prompt nested in the payment prompt; the mana joins the pool,
  and the payment prompt carries on (or finishes at once when the pool now covers it).
* 304.5 / 602.5d-e: "Activate only as an instant" (Lion's Eye Diamond) needs priority, which a player paying a cost doesn't have.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, pick, until_asked
from tests.wave9c_kit import build, card_named, check, put, reloaded, to_hand, zone_of

REAL = [
    ("Ashnod's Altar", "{3}", "Artifact", "Sacrifice a creature: Add {C}{C}."),
    ("Phyrexian Altar", "{3}", "Artifact", "Sacrifice a creature: Add one mana of any color."),
    ("Lion's Eye Diamond", "{0}", "Artifact", "Discard your hand, Sacrifice this artifact: Add three mana of any one color. Activate only as an instant."),
    ("Giant Opportunity", "{2}{G}", "Sorcery",
     "You may sacrifice two Foods. If you do, create a 7/7 green Giant creature token. Otherwise, create three Food tokens. "
     "(They're artifacts with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")"),
    ("Doom Blade", "{1}{B}", "Instant", "Destroy target nonblack creature."),
]
EXTRA = [card(n, set_code="t28d", number=f"T{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1), type_line=tl,
              colors=["B"] if n == "Doom Blade" else [], color_identity=[], oracle_text=text)
         for i, (n, mc, tl, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def self_payment(s):
    for prefs in s.state.rules.prefs.values():
        prefs.payment = "self"  # (players tap their own mana: the "tap your mana" prompt)


def alive(s, c):
    return c.id in s.state.cards and s.state.cards[c.id].zone == "p1:battlefield"


def gone(s, c):
    return not alive(s, c)


def start(cards, *permanents):
    s = build(cards, ["Giant Opportunity", *permanents])
    self_payment(s)
    return s


def cast_giant(s):
    spell = to_hand(s, "Giant Opportunity")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "pay_mana"
    return spell


def use(s, name, **kw):
    act(s, "p1", type="activate_ability", card_id=card_named(s, name).id, ability=0, **kw)


def test_ashnods_altar_pays_part_of_a_spell_while_paying(cards):
    s = start(cards, "Ashnod's Altar")
    put(s, "Ashnod's Altar")
    bear = creature(s, "p1", "Bear")
    creature(s, "p1", "Cub")
    cast_giant(s)
    use(s, "Ashnod's Altar")
    d = s.state.rules.decision  # (the creature to sacrifice, nested in the payment)
    assert d.kind == "choose_cards" and {o.id for o in d.options} >= {bear.id}
    assert s.state.rules.payment_outer is not None and s.state.rules.payment_outer.resume["step"] == "pay_mana"
    check(s)
    pick(s, bear.id)
    assert gone(s, bear)  # (601.2h: sacrificed as it's paid)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "pay_mana" and s.state.rules.payment_outer is None  # (back in the payment)
    assert s.state.players["p1"].mana.get("C") == 2
    check(s)


def test_the_payment_finishes_when_the_altar_covers_it(cards):
    s = start(cards, "Phyrexian Altar")
    put(s, "Phyrexian Altar")
    mana_forest = creature(s, "p1", "Elf")
    other = creature(s, "p1", "Cub")
    other2 = creature(s, "p1", "Bear")
    cast_giant(s)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    use(s, "Phyrexian Altar", mana_choice="G")
    pick(s, mana_forest.id)
    assert s.state.rules.decision is None or s.state.rules.decision.resume.get("step") != "pay_mana"  # (2 + G paid it: it was cast)
    assert gone(s, mana_forest) and other.id in s.state.cards and other2.id in s.state.cards
    assert zone_of(s, "Giant Opportunity") == "p1:graveyard"  # (it was cast and has resolved)
    check(s)


def test_the_color_is_chosen_after_the_sacrifice_and_survives_a_load(cards):
    s = start(cards, "Phyrexian Altar")
    put(s, "Phyrexian Altar")
    elf = creature(s, "p1", "Elf")
    creature(s, "p1", "Cub")
    cast_giant(s)
    use(s, "Phyrexian Altar")
    pick(s, elf.id)
    d = s.state.rules.decision  # (nested: which mana)
    assert d.resume["step"] == "mana_ability" and s.state.rules.payment_outer is not None
    check(s)
    t = reloaded(s)  # (a save and a load in the middle of the nest)
    assert t.state.rules.payment_outer is not None and t.state.rules.decision.resume["step"] == "mana_ability"
    for sess in (s, t):
        d = sess.state.rules.decision
        act(sess, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "{G}")])
        assert sess.state.players["p1"].mana.get("G") == 1 and sess.state.rules.payment_outer is None
        assert sess.state.rules.decision.resume["step"] == "pay_mana"
    check(t)


def test_cancelling_the_choice_returns_to_the_payment(cards):
    s = start(cards, "Ashnod's Altar")
    put(s, "Ashnod's Altar")
    bear = creature(s, "p1", "Bear")
    creature(s, "p1", "Cub")
    cast_giant(s)
    use(s, "Ashnod's Altar")
    pick(s)  # (none: the altar isn't activated)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "pay_mana" and s.state.rules.payment_outer is None
    assert alive(s, bear) and s.state.players["p1"].mana.get("C", 0) == 0
    check(s)


def test_a_lone_creature_is_sacrificed_without_asking(cards):
    s = start(cards, "Ashnod's Altar")
    put(s, "Ashnod's Altar")
    bear = creature(s, "p1", "Bear")
    cast_giant(s)
    use(s, "Ashnod's Altar")
    assert gone(s, bear) and s.state.players["p1"].mana.get("C") == 2
    assert s.state.rules.payment_outer is None and s.state.rules.decision.resume["step"] == "pay_mana"
    check(s)


def test_with_no_creature_the_altar_cant_be_used(cards):
    s = start(cards, "Ashnod's Altar")
    put(s, "Ashnod's Altar")
    cast_giant(s)
    with pytest.raises(ActionError):
        use(s, "Ashnod's Altar")  # 118.3
    assert s.state.rules.decision.resume["step"] == "pay_mana" and s.state.rules.payment_outer is None
    check(s)


def test_lions_eye_diamond_still_needs_priority(cards):
    s = start(cards, "Lion's Eye Diamond", "Doom Blade")
    put(s, "Lion's Eye Diamond")
    to_hand(s, "Doom Blade")
    cast_giant(s)
    with pytest.raises(ActionError):
        use(s, "Lion's Eye Diamond", mana_choice="G")  # 304.5
    assert zone_of(s, "Lion's Eye Diamond") == "p1:battlefield" and zone_of(s, "Doom Blade") == "p1:hand"
    assert s.state.rules.payment_outer is None
    check(s)


def test_cancelling_the_spell_after_a_nested_activation(cards):
    s = start(cards, "Ashnod's Altar")
    put(s, "Ashnod's Altar")
    bear = creature(s, "p1", "Bear")
    creature(s, "p1", "Cub")
    spell = cast_giant(s)
    use(s, "Ashnod's Altar")
    pick(s, bear.id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    assert s.state.rules.decision is None and s.state.cards[spell.id].zone == "p1:hand"  # (the spell isn't cast; the mana stays: 106.4)
    assert s.state.players["p1"].mana.get("C") == 2
    check(s)


def test_the_spells_own_target_isnt_offered_for_the_sacrifice(cards):
    """The payment is carried out again from its announcement, which needs its target where it was: the other creature is offered."""
    s = build(cards, ["Doom Blade", "Ashnod's Altar"])
    self_payment(s)
    put(s, "Ashnod's Altar")
    bear = creature(s, "p1", "Bear")
    spell = to_hand(s, "Doom Blade")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1})
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    with pytest.raises(ActionError):
        use(s, "Ashnod's Altar")  # (the only creature is the target)
    cub = creature(s, "p1", "Cub")
    elf = creature(s, "p1", "Elf")
    use(s, "Ashnod's Altar")
    assert {o.id for o in s.state.rules.decision.options} == {cub.id, elf.id}
    check(s)
    pick(s, cub.id)
    assert gone(s, cub) and alive(s, elf)  # (and the spell resolved: the bear was its target, destroyed)
    assert gone(s, bear)
    assert s.state.cards[spell.id].zone != "p1:hand"  # (B + CC paid {1}{B}: it was cast)
    check(s)
