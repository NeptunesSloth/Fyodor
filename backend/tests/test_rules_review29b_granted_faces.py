"""Review of wave 29B (granted casts): the "cast it?" choice of cascade, discover, ripple, suspend and rebound offers only the ways the card can
really be cast now, and a cast that is begun and then abandoned ends like a declined one (CR 2026-09-25). Real Oracle text
(tests/fixtures/wave29b_cards.json, review29b_cards.json, from data/cards.sqlite); each scenario checks the replay and a save and a load.

* 601.2c / 601.5: a spell whose required target can't be chosen can't be cast (the proposal is illegal and rewound); 700.2a: nor a modal spell
  with no mode that can be chosen; 205.4e: a legendary instant or sorcery without a legendary creature or planeswalker; 601.2h / 118.9d: a
  mandatory additional cost ("sacrifice a creature") that can't be paid. Such a half / face is not offered: otherwise the answer was a dead end
  (the free cast's target choice couldn't be cancelled, and every target was refused). With none left nothing is asked and the card goes where
  the mechanic puts a card not cast (702.85a cascade: the bottom, in a random order with the others). Everything checked is public: a cost part
  read from the hand ("discard a land card") is not checked ahead, nor is mana (can_pay doesn't count mana abilities activated by hand).
* 601.2: a free cast begun as the ability resolves and then cancelled — at its target choice, which a cost that can't be paid makes the only
  way out, or at its payment — is a card not cast: 702.85a puts it on the bottom with the others; it is not left in exile with a grant to cast
  it later (``RulesState.free_cast_then`` records it: permissions.free_cast_abandoned).
* Saves from before wave 29B asked a plain yes / no (no ``group`` in the resume, no ``free_cast_faces``): they still resolve.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.wave9c_kit import build, card_named, mana, put, reloaded, to_hand

HERE = Path(__file__).parent / "fixtures"
DATA = [*json.loads((HERE / "wave29b_cards.json").read_text("utf-8")), *json.loads((HERE / "review29b_cards.json").read_text("utf-8"))]
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r29b", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def asked(s):
    d = s.state.rules.decision
    return d is not None and (d.resume or {}).get("step") == "suspend_cast"


def options(s):
    return [(o.id, o.label) for o in s.state.rules.decision.options]


def choose(s, option):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def top_of_library(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def cascade_into(cards, found, mine=(), theirs=(), *, passed=(), setup=None):
    """Bloodbraid Elf (4) cascades; ``found`` is the first nonland card it exiles (after the cards ``passed``, mana value 4 or more). Priority
    is passed until the question is asked or the cascade is over."""
    s = build(cards, ["Bloodbraid Elf", found, *passed, *mine], theirs=list(theirs))
    if setup is not None:
        setup(s)
    hit = top_of_library(s, found)
    went_past = [top_of_library(s, name).id for name in passed]
    to_hand(s, "Bloodbraid Elf")
    mana(s, R=2, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bloodbraid Elf").id)
    for _ in range(20):  # (until the cascade trigger has asked, or resolved without asking)
        if asked(s) or all(e.kind == "spell" for e in s.state.rules.stack.values()):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s, hit, went_past


def not_cast(s, hit, went_past=()):
    """Nothing was asked: the card went to the bottom with the others, and no grant to cast it is left."""
    library = s.state.zones["p1:library"]
    assert not asked(s) and s.state.cards[hit.id].zone == "p1:library"
    assert set(library[-1 - len(went_past):]) == {hit.id, *went_past}
    assert hit.id not in s.state.rules.free_casts and not s.state.rules.free_cast_faces and s.state.rules.free_cast_then is None
    assert "can't be cast without paying its mana cost now" in json.dumps(s.view("p2")["log"])


# -- a half / face that can't be cast is not offered (601.2c, 601.5) ----------------------------------------------------------------------
def test_a_spell_whose_additional_cost_cant_be_paid_is_not_offered(cards):
    """Fling ("As an additional cost to cast this spell, sacrifice a creature.") with no creature on the battlefield (Bloodbraid Elf is still a
    spell): it can't be cast (601.2h), so nothing is asked. Before the review the answer "yes" led to Fling's target choice, where every target
    was refused ("You can't pay 'Sacrifice a creature'") and the choice couldn't be cancelled: the game was stuck."""
    s, fling, went_past = cascade_into(cards, "Fling", passed=["Craterhoof Behemoth"])
    not_cast(s, fling, went_past)
    s = reloaded(s)
    pass_until_stack_empty(s)
    assert s.state.cards[card_named(s, "Bloodbraid Elf").id].zone == "p1:battlefield" and s.state.rules.decision is None
    check(s)


def test_a_spell_whose_additional_cost_can_be_paid_is_offered(cards):
    s, fling, _ = cascade_into(cards, "Fling", mine=["Grizzly Bears"], setup=lambda s: put(s, "Grizzly Bears"))
    assert options(s) == [("yes", "Cast it"), ("no", "Put it on the bottom")]
    check(s)


def test_an_additional_cost_read_from_the_hand_is_still_asked(cards):
    """Magmatic Insight ("As an additional cost to cast this spell, discard a land card.") with no land card in hand: whether the hand holds
    one is hidden, so skipping the question would tell the other players; it is asked, and "yes" is refused (601.2h) in the cast itself, by
    a message only its caster sees. "no" puts it on the bottom."""
    from app.game.errors import ActionError

    s, insight, _ = cascade_into(cards, "Magmatic Insight")
    assert not [c for c in s.state.zones["p1:hand"] if s.state.cards[c].name == "Forest"]
    assert options(s) == [("yes", "Cast it"), ("no", "Put it on the bottom")]
    with pytest.raises(ActionError):
        choose(s, "yes")
    choose(s, "no")
    assert s.state.zones["p1:library"][-1] == insight.id and not s.state.rules.free_casts
    check(s)


def test_a_spell_with_no_legal_target_is_not_offered(cards):
    """Shatter ("Destroy target artifact.") with no artifact anywhere: no legal target (601.2c), nothing asked."""
    s, shatter, _ = cascade_into(cards, "Shatter")
    not_cast(s, shatter)
    check(s)


def test_a_split_half_with_no_legal_target_is_not_offered(cards):
    """Wear // Tear with an enchantment and no artifact: only Tear ("Destroy target enchantment.") is offered (709.3a: each half is
    evaluated on its own)."""
    s, wear, _ = cascade_into(cards, "Wear // Tear", theirs=["Maelstrom Nexus"], setup=lambda s: put(s, "Maelstrom Nexus", "p2"))
    assert options(s) == [("yes@1", "Cast Tear"), ("no", "Put it on the bottom")]
    s = reloaded(s)
    choose(s, "yes@1")
    d = s.state.rules.decision
    if d is not None:  # (Tear's one legal target)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, "Maelstrom Nexus", "p2").id])
    pass_until_stack_empty(s)
    assert s.state.cards[card_named(s, "Maelstrom Nexus", "p2").id].zone == "p2:graveyard"
    check(s)


def test_a_legendary_sorcery_needs_a_legendary_creature(cards):
    """205.4e: Kamahl's Druidic Vow (a legendary sorcery, mana value 2) can be cast only while its caster controls a legendary creature or
    planeswalker: not offered without one, offered with Imoti, Celebrant of Bounty."""
    s, vow, _ = cascade_into(cards, "Kamahl's Druidic Vow")
    not_cast(s, vow)
    check(s)
    s, vow, _ = cascade_into(cards, "Kamahl's Druidic Vow", mine=["Imoti, Celebrant of Bounty"],
                             setup=lambda s: put(s, "Imoti, Celebrant of Bounty"))
    assert options(s) == [("yes", "Cast it"), ("no", "Put it on the bottom")]
    check(s)


def test_a_cast_whose_cost_cant_be_paid_can_be_cancelled_at_its_target(cards):
    """Thalia, Guardian of Thraben (an opponent's): "Noncreature spells cost {1} more to cast." A Lightning Bolt cast without paying its mana
    cost costs {1} (118.9d, 601.2f). Mana isn't checked before the question (mana abilities activated by hand aren't counted), so "yes" is
    offered; with no mana the answer to Bolt's target is refused (601.2h), and the target choice of this free cast can now be cancelled
    (601.2: rewound, the card not cast goes to the bottom, 702.85a). Before the review it couldn't: the game was stuck."""
    from app.game.errors import ActionError

    s, bolt, went_past = cascade_into(cards, "Lightning Bolt", theirs=["Thalia, Guardian of Thraben"], passed=["Craterhoof Behemoth"],
                                      setup=lambda s: put(s, "Thalia, Guardian of Thraben", "p2"))
    assert options(s) == [("yes", "Cast it"), ("no", "Put it on the bottom")]
    choose(s, "yes")
    with pytest.raises(ActionError):
        choose(s, "p2")
    d = s.state.rules.decision
    assert d.resume["step"] == "cast_target" and s.view("p1")["rules"]["decision"]["cancelable"]
    s = reloaded(s)
    choose(s, "cancel")
    library = s.state.zones["p1:library"]
    assert s.state.cards[bolt.id].zone == "p1:library" and set(library[-2:]) == {bolt.id, *went_past}
    assert bolt.id not in s.state.rules.free_casts and s.state.rules.free_cast_then is None and s.state.rules.decision is None
    pass_until_stack_empty(s)
    assert s.state.cards[card_named(s, "Bloodbraid Elf").id].zone == "p1:battlefield" and s.state.players["p2"].life == 40
    check(s)


def test_a_normal_free_cast_target_choice_without_a_record_is_not_cancelable(cards):
    """Only a free cast whose end is recorded may be cancelled: the wave 24D rule stands for any other (an old save's)."""
    from app.game.rules_state import cancelable

    s, bolt, _ = cascade_into(cards, "Lightning Bolt")
    choose(s, "yes")
    d = s.state.rules.decision
    assert d.resume["step"] == "cast_target" and d.resume.get("abandon") and cancelable(d)
    old = d.model_copy(update={"resume": {k: v for k, v in d.resume.items() if k != "abandon"}})
    assert not cancelable(old)


def test_discover_puts_a_card_it_cant_cast_into_the_hand(cards):
    """701.57a: "If you don't cast it, put that card into your hand": discover 5 finds Shatter with no artifact to destroy."""
    s = build(cards, ["Trumpeting Carnosaur", "Shatter"])
    shatter = top_of_library(s, "Shatter")
    to_hand(s, "Trumpeting Carnosaur")
    mana(s, R=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Trumpeting Carnosaur").id)
    for _ in range(6):
        pass_until_stack_empty(s)
    assert not asked(s) and s.state.cards[shatter.id].zone == "p1:hand" and not s.state.rules.free_casts
    assert "can't be cast without paying its mana cost now" in json.dumps(s.view("p2")["log"])
    check(s)


# -- a cast abandoned on the way (601.2) ---------------------------------------------------------------------------------------------------
def test_a_cascade_cast_whose_payment_is_cancelled_goes_to_the_bottom(cards):
    """Under Thalia the cascaded Lightning Bolt costs {1}. Its caster taps their own mana (payment preference "self") and cancels the payment:
    nothing was paid, the spell wasn't cast (601.2), so it joins the cards cascade went past on the bottom (702.85a). Before the review it stayed
    in exile with its grant, castable for free at any later time."""
    def setup(s):
        put(s, "Thalia, Guardian of Thraben", "p2")
        put(s, "Forest")
        act(s, "p1", type="set_prefs", payment="self")

    s, bolt, went_past = cascade_into(cards, "Lightning Bolt", theirs=["Thalia, Guardian of Thraben"], passed=["Craterhoof Behemoth"],
                                      setup=setup)
    choose(s, "yes")
    choose(s, "p2")  # (Bolt's target)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "pay_mana"
    s = reloaded(s)  # (a save and a load in the middle of the payment)
    choose(s, "cancel")
    library = s.state.zones["p1:library"]
    assert s.state.cards[bolt.id].zone == "p1:library" and set(library[-2:]) == {bolt.id, *went_past}
    assert bolt.id not in s.state.rules.free_casts and s.state.rules.free_cast_then is None and not s.state.zones.get("p1:exile")
    assert "doesn't cast it" in json.dumps(s.view("p2")["log"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 40 and s.state.cards[card_named(s, "Bloodbraid Elf").id].zone == "p1:battlefield"
    check(s)


def test_a_cascade_cast_that_is_paid_clears_its_record(cards):
    def setup(s):
        put(s, "Thalia, Guardian of Thraben", "p2")
        put(s, "Forest")

    s, bolt, _ = cascade_into(cards, "Lightning Bolt", theirs=["Thalia, Guardian of Thraben"], setup=setup)
    choose(s, "yes")
    assert s.state.rules.free_cast_then is not None  # (while its target is chosen)
    s = reloaded(s)
    choose(s, "p2")  # (the Forest pays the {1})
    assert s.state.rules.free_cast_then is None and s.state.cards[bolt.id].zone in ("stack", "p1:graveyard")
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37 and s.state.cards[bolt.id].zone == "p1:graveyard"
    assert s.state.rules.free_cast_then is None and not s.state.rules.free_casts
    check(s)


# -- the random order stays hidden (401.4) -----------------------------------------------------------------------------------------------
def bottom_lines(s, viewer="p2"):
    """The names each "put on the bottom of" log line lists, as ``viewer`` reads them."""
    out = []
    for entry in s.view(viewer)["log"]:
        parts = entry.get("parts") or []
        if any("put on the bottom of" in (p.get("t") or "") for p in parts):
            out.append([g["card"]["name"] for p in parts for g in p.get("group") or [] if g.get("card")])
    return out


def test_the_cards_cascade_went_past_are_logged_in_no_particular_order(cards):
    """702.85a "in a random order": the cards go to the bottom in one move, whose log line lists them by name; before the review each went in
    its own move, so the lines told everyone the order (a face-down spell's cascade put the whole library back that way). The declined card's
    own line says nothing of where among them it landed."""
    passed = ["Craterhoof Behemoth", "Hit // Run", "Jadzi, Oracle of Arcavios // Journey to the Oracle", "Storm, Force of Nature"]
    orders = set()
    for _ in range(6):
        s, bolt, went_past = cascade_into(cards, "Lightning Bolt", passed=passed)
        choose(s, "no")
        lines = bottom_lines(s)
        assert lines[-2:] == [sorted(passed), ["Lightning Bolt"]]
        orders.add(tuple(c for c in s.state.zones["p1:library"] if c in {bolt.id, *went_past}))
        check(s)
    assert len(orders) > 1  # (the order itself is random)


# -- saves from before wave 29B ----------------------------------------------------------------------------------------------------------
def old_save(s):
    """The table as a save from before wave 29B: the pending "cast it?" offers a plain yes / no, its resume has no ``group``, and the rules
    state has no ``free_cast_faces``."""
    dump = s.state.model_dump(mode="json")
    d = dump["rules"]["decision"]
    d["options"] = [o for o in d["options"] if o["id"] in ("yes", "no")]
    d["options"][0]["label"] = "Cast it"
    d["resume"].pop("group", None)
    dump["rules"].pop("free_cast_faces", None)
    return GameSession(GameState.model_validate(dump), cards=s.cards)


def test_an_old_save_yes_casts_the_first_half(cards):
    """The old "yes" for Bonecrusher Giant // Stomp casts the card as it is: the creature (its first half, 715.4)."""
    s, giant, went_past = cascade_into(cards, "Bonecrusher Giant // Stomp", passed=["Craterhoof Behemoth"])
    assert [o[0] for o in options(s)] == ["yes", "yes@1", "no"]
    s = old_save(s)
    assert options(s) == [("yes", "Cast it"), ("no", "Put it on the bottom")] and s.state.rules.free_cast_faces == {}
    choose(s, "yes")
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.cards[giant.id].zone == "p1:battlefield" and s.state.cards[giant.id].face == 0
    assert s.state.zones["p1:library"][-1] == went_past[0] and not s.state.rules.free_casts


def test_an_old_save_no_puts_it_on_the_bottom(cards):
    s, giant, went_past = cascade_into(cards, "Bonecrusher Giant // Stomp", passed=["Craterhoof Behemoth"])
    s = old_save(s)
    choose(s, "no")
    assert set(s.state.zones["p1:library"][-2:]) == {giant.id, *went_past} and not s.state.rules.free_casts
