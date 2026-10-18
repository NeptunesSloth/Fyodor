"""Wave 41D: optional additional costs on a free cast (CR 2026-09-25), real Oracle text (tests/fixtures/wave41d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load (also in the middle of the question).

* 118.9d: "If an alternative cost … is being paid … any additional costs … are paid in addition" — a spell cast without paying its mana cost may still be
  kicked, bargained, promised a gift or cast with casualty (601.2b: announced with the other costs, before the targets); the kicker cost's mana is still
  paid (601.2f-h), through the normal payment. Before wave 41D the caster of a cascaded, discovered or Gandalf'd spell was never asked.
* 702.33a / 702.33c: kicker / multikicker (the times it is paid); 702.166a-b: bargain (sacrifice an artifact, enchantment or token); 702.174a: gift (an
  opponent is promised it); 702.153a: casualty (sacrifice a creature with power N or greater; when you do, copy the spell).
* Only the caster is asked; what decides whether an option is offered is public (mana, permanents), so no answer or omission tells the table what is in a hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import settle, stack_top
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of
from tests.wave9c_kit import reloaded as reloaded_session

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave41d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t41d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
GANDALF = "Gandalf, Party Guest"
FULL = [GANDALF, "Burst Lightning", "Candy Grapple", "Light 'Em Up", "Wear Down", "Gnarlid Pack", "Bloodbraid Elf", "Prosperous Bandit"]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def lands(s, n):
    """``n`` untapped Forests on the battlefield (mana that is still there when the beginning of combat asks)."""
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:n]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})


def gandalf(cards, spell, *, forests=0, theirs=()):
    """Alice has Gandalf (X = 2: he is a legendary Wizard) and ``spell`` in hand, ``forests`` Forests in play; the free-cast question waits at the
    beginning of combat and is answered with the spell."""
    s = build(cards, [GANDALF, spell, "Grizzly Bears"], list(theirs))
    put(s, GANDALF)
    to_hand(s, spell)
    lands(s, forests)
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        if s.state.rules.decision is not None:
            break
    pick(s, card_named(s, spell).id)
    return s


def pick(s, *option_ids):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(option_ids))


def question(s):
    """The optional-cost question, or None."""
    d = s.state.rules.decision
    return d if d is not None and (d.resume or {}).get("step") == "free_optional" else None


# ---- kicker: Burst Lightning ----------------------------------------------------------------------------------------------------------------
def test_burst_lightning_cast_free_with_gandalf_can_be_kicked_and_its_mana_is_paid(cards):
    """"Kicker {4} … Burst Lightning deals 2 damage to any target. If this spell was kicked, it deals 4 damage instead." Cast through Gandalf with four
    Forests: the caster is asked (only they see it); kicker:1 is the one option; the {4} is paid from the Forests (118.9d, 601.2f) and 4 damage is dealt."""
    s = gandalf(cards, "Burst Lightning", forests=4)
    d = question(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards" and d.min_choices == 0
    assert [o.id for o in d.options] == ["kicker:1"] and d.options[0].label == "Kicker {4}"
    other = s.view("p2")["rules"]["decision"]  # (the other player only sees that Alice is choosing)
    assert other["kind"] == "waiting" and "options" not in other and "Kicker" not in json.dumps(other)
    s = reloaded_session(s)  # a save and a load in the middle of the question
    pick(s, "kicker:1")
    pick(s, "p2")
    settle(s)
    assert life(s, "p2") == 36 and zone_of(s, "Burst Lightning") == "p1:graveyard"
    assert all(c.tapped for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield")
    check(s)


def test_burst_lightning_cast_free_and_declined_is_the_unkicked_one_and_pays_nothing(cards):
    """Nothing chosen: 2 damage, no mana spent (the Forests stay untapped), and the question is not asked again."""
    s = gandalf(cards, "Burst Lightning", forests=4)
    assert question(s) is not None
    pick(s)
    assert question(s) is None
    pick(s, "p2")
    settle(s)
    assert life(s, "p2") == 38 and not any(c.tapped for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield")
    check(s)


def test_a_kicker_the_caster_cant_pay_is_not_offered(cards):
    """Three Forests are not {4}: no question at all (the first thing asked is the target), and the spell is the unkicked one."""
    s = gandalf(cards, "Burst Lightning", forests=3)
    assert question(s) is None
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one" and "target" in d.prompt.lower()
    pick(s, "p2")
    settle(s)
    assert life(s, "p2") == 38
    check(s)


# ---- multikicker through cascade ------------------------------------------------------------------------------------------------------------
def cascade_gnarlid(cards, forests, found="Gnarlid Pack"):
    """Bloodbraid Elf (paid from the pool) cascades into ``found``; the "cast it?" question is answered "yes"."""
    s = build(cards, ["Bloodbraid Elf", found])
    stack_top(s, [found])
    to_hand(s, "Bloodbraid Elf")
    lands(s, forests)
    mana(s, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bloodbraid Elf").id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "suspend_cast":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pick(s, "yes")
    return s


def test_multikicker_on_a_cascaded_spell_offers_only_the_counts_the_caster_can_pay(cards):
    """"Multikicker {1}{G} … This creature enters with a +1/+1 counter on it for each time it was kicked." (Gnarlid Pack, found by cascade): four Forests
    pay it twice and not three times, so ×1 and ×2 are offered; ×2 is paid in full and the creature enters with two counters (702.33c)."""
    s = cascade_gnarlid(cards, 4)
    d = question(s)
    assert d is not None and [o.id for o in d.options] == ["kicker:1", "kicker:2"]
    assert d.options[1].label == "Multikicker {1}{G}, paid 2 times"
    s = reloaded_session(s)
    pick(s, "kicker:2")
    settle(s)
    assert zone_of(s, "Gnarlid Pack") == "p1:battlefield" and pt(s, "Gnarlid Pack") == (4, 4)
    assert all(c.tapped for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield")
    check(s)


def test_multikicker_with_one_forest_short_is_not_offered_and_two_counts_are_refused(cards):
    s = cascade_gnarlid(cards, 1)
    assert question(s) is None  # ({1}{G} needs two mana: one Forest is not enough)
    s = cascade_gnarlid(cards, 2)
    d = question(s)
    assert d is not None and [o.id for o in d.options] == ["kicker:1"]
    pick(s)
    settle(s)
    assert pt(s, "Gnarlid Pack") == (2, 2)
    check(s)


def test_offspring_on_a_cascaded_creature_is_offered_and_creates_the_token_copy(cards):
    """"Offspring {1} (You may pay an additional {1} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)"
    (Prosperous Bandit, found by cascade): one Forest pays it, and the token copy comes with the creature; with no mana nothing is offered."""
    s = cascade_gnarlid(cards, 1, "Prosperous Bandit")
    d = question(s)
    assert d is not None and [(o.id, o.label) for o in d.options] == [("kicker:1", "Offspring {1}")]
    pick(s, "kicker:1")
    settle(s)
    bandits = [c for c in s.state.cards.values() if c.name == "Prosperous Bandit" and c.zone == "p1:battlefield"]
    assert len(bandits) == 2 and sorted(c.is_token for c in bandits) == [False, True]
    check(s)
    assert question(cascade_gnarlid(cards, 0, "Prosperous Bandit")) is None


# ---- bargain: Candy Grapple -------------------------------------------------------------------------------------------------------------------
def grapple_game(cards, *, artifact):
    """Gandalf casts Candy Grapple; Bob's Courser of Kruphix is 2/4 (-3/-3 leaves it a 1-toughness creature, -5/-5 kills it)."""
    s = build(cards, [GANDALF, "Candy Grapple", "Sol Ring"], ["Courser of Kruphix"])
    put(s, GANDALF)
    ring = put(s, "Sol Ring") if artifact else None
    courser = put(s, "Courser of Kruphix", "p2")
    to_hand(s, "Candy Grapple")
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        if s.state.rules.decision is not None:
            break
    pick(s, card_named(s, "Candy Grapple").id)
    return s, ring, courser


def test_candy_grapple_cast_free_can_be_bargained_by_sacrificing_an_artifact(cards):
    """"Bargain … Target creature gets -3/-3 until end of turn. If this spell was bargained, that creature gets -5/-5 until end of turn instead." Gandalf
    casts it; Sol Ring is sacrificed (702.166a) and the 2/4 Courser dies."""
    s, ring, courser = grapple_game(cards, artifact=True)
    d = question(s)
    grapple = card_named(s, "Candy Grapple")
    assert d is not None and [(o.id, o.label) for o in d.options] == [(f"{grapple.id}:bargain", "Bargain: sacrifice an artifact, enchantment, or token")]
    other = s.view("p2")["rules"]["decision"]
    assert other["kind"] == "waiting" and "Bargain" not in json.dumps(other)
    pick(s, d.options[0].id)
    s = reloaded_session(s)
    pick(s, courser.id)
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard" and s.state.cards[courser.id].zone == "p2:graveyard"
    check(s)


def test_candy_grapple_cast_free_declined_is_the_unbargained_one(cards):
    s, ring, courser = grapple_game(cards, artifact=True)
    assert question(s) is not None
    pick(s)
    pick(s, courser.id)
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield" and s.state.cards[courser.id].zone == "p2:battlefield"
    assert pt(s, "Courser of Kruphix", "p2") == (-1, 1)
    check(s)


def test_bargain_without_a_permanent_to_sacrifice_is_not_offered(cards):
    s, _, courser = grapple_game(cards, artifact=False)
    assert question(s) is None  # (no artifact, enchantment or token of Alice's: bargain can't be paid, 118.3)
    pick(s, courser.id)
    settle(s)
    assert pt(s, "Courser of Kruphix", "p2") == (-1, 1)
    check(s)


# ---- gift: Wear Down ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("promised", [True, False])
def test_wear_down_cast_free_can_promise_a_gift(cards, promised):
    """"Gift a card … Destroy target artifact or enchantment. If the gift was promised, instead destroy two target artifacts and/or enchantments." A
    promised gift (702.174a) makes the opponent draw a card first and the spell destroys two permanents; declined, one and no card. With one opponent
    there is nobody to choose between."""
    s = build(cards, [GANDALF, "Wear Down"], ["Sol Ring", "Arcane Signet"])
    put(s, GANDALF)
    ring, signet = put(s, "Sol Ring", "p2"), put(s, "Arcane Signet", "p2")
    to_hand(s, "Wear Down")
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        if s.state.rules.decision is not None:
            break
    pick(s, card_named(s, "Wear Down").id)
    d = question(s)
    assert d is not None and [o.label for o in d.options] == ["Gift: promise an opponent a gift"]
    hand_before = len(s.state.zones["p2:hand"])
    pick(s, d.options[0].id) if promised else pick(s)
    s = reloaded_session(s)
    while s.state.rules.decision is not None or s.state.zones.get("stack"):
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            ids = [ring.id, signet.id] if all(o.id in (ring.id, signet.id) for o in d.options) else [d.options[0].id]
            pick(s, *ids[: d.max_choices])
    gone = [c for c in (ring, signet) if s.state.cards[c.id].zone == "p2:graveyard"]
    assert len(gone) == (2 if promised else 1)
    assert len(s.state.zones["p2:hand"]) == hand_before + (1 if promised else 0)
    check(s)


# ---- casualty: Light 'Em Up ---------------------------------------------------------------------------------------------------------------------
def test_light_em_up_cast_free_with_casualty_sacrifices_a_creature_and_copies_the_spell(cards):
    """"Casualty 2 … Light 'Em Up deals 2 damage to target creature or planeswalker." Sacrificing a creature with power 2 or greater (Grizzly Bears) as
    Gandalf casts it: the copy is made (702.153a) and each Grizzly Bears of Bob takes 2 damage; declined: one is hit and nothing is sacrificed."""
    s = build(cards, [GANDALF, "Light 'Em Up", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears"])
    put(s, GANDALF)
    bears = put(s, "Grizzly Bears")
    theirs = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"][:2]
    for c in theirs:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Light 'Em Up")
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        if s.state.rules.decision is not None:
            break
    pick(s, card_named(s, "Light 'Em Up").id)
    d = question(s)
    assert d is not None and d.options[0].id.endswith(":casualty") and d.options[0].label.startswith("Casualty 2")
    pick(s, d.options[0].id)
    pick(s, theirs[0].id)  # (the target)
    for _ in range(30):  # (the sacrifice, the copy's new target, resolution)
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [bears.id] if bears.id in ids else [theirs[1].id] if theirs[1].id in ids else ids[: max(1, d.min_choices)]
            pick(s, *want[: d.max_choices])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bears.id].zone == "p1:graveyard"  # (sacrificed)
    assert [s.state.cards[c.id].zone for c in theirs] == ["p2:graveyard", "p2:graveyard"]  # (the spell and its copy)
    check(s)


# ---- the old limit is gone for spells that have no optional cost ---------------------------------------------------------------------------------
def test_a_free_cast_of_a_spell_with_no_optional_cost_asks_nothing_new(cards):
    s = gandalf(cards, "Burst Lightning", forests=0)
    assert question(s) is None
    pick(s, "p2")
    settle(s)
    assert life(s, "p2") == 38
    check(s)
