"""-- round 5 audit: replicate and additional costs -- scenarios through the real action API with real Oracle text pulled from the card
database: replicate (702.56: the count, the total cost 601.2f, one copy per payment, new targets for the copies, copies aren't cast 707.10,
magecraft sees them, a copy of a replicated spell isn't replicated, Djinn Illuminatus's grant), kicker / multikicker (702.33), buyback,
entwine, escalate, splice, conspire, bargain, casualty, squad, mandatory additional costs ("sacrifice a creature", "discard a card",
"pay X life"), cost changes on additional costs (Thalia, a reducer), free casts that still pay kicker (118.9d), flashback + kicker, commander
tax with kicker (903.8), and copies of a kicked spell being kicked (707.10). Every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_review_core import REAL_DB, real_cards
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

NAMES = ["Train of Thought", "Gigadrowse", "Shattering Spree", "Djinn Illuminatus", "Archmage Emeritus", "Grapeshot", "Twincast",
         "Burst Lightning", "Everflowing Chalice", "Thalia, Guardian of Thraben", "Omniscience", "Goblin Electromancer", "Snapcaster Mage",
         "Capsize", "Collective Brutality", "Glacial Ray", "Lava Spike", "Burn Trail", "Torch the Tower", "Cut Your Losses", "Fling",
         "Thrill of Possibility", "Toxic Deluge", "Josu Vess, Lich Knight", "Bone Splinters", "Arco-Flagellant", "Lightning Bolt",
         "Grizzly Bears", "Sol Ring", "Mind Stone", "Hill Giant", "Craw Wurm", "Raging Goblin", "Goblin Piker"]

pytestmark = pytest.mark.skipif(not REAL_DB.is_file(), reason="the real card database is needed")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *real_cards([n for n in NAMES if n not in have])], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


FULL = [n for n in NAMES if n not in ("Grizzly Bears", "Sol Ring", "Mind Stone", "Hill Giant", "Craw Wurm", "Raging Goblin", "Goblin Piker")]


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=120):
    """Resolve the stack; decisions answered from ``picks`` in turn (an option id / label / card id, or a list), else their first options."""
    picks = list(picks)

    def find(d, token):
        return next((o.id for o in d.options if token in (o.id, o.label, o.card_id)), token)

    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [find(d, t) for t in pick] if isinstance(pick, list) else [find(d, pick)] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def stack(s):
    return [s.state.cards[i].name for i in s.state.zones.get("stack", [])]


# -- replicate (702.56) --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("paid", [0, 1, 3])
def test_train_of_thought_one_copy_per_payment(cards, paid):
    s = build(cards, ["Train of Thought"])
    c = to_hand(s, "Train of Thought")
    mana(s, U=1 + paid, C=1 + paid)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=paid)
    answer(s)
    assert hand(s) == before - 1 + 1 + paid  # the spell and one copy per payment each draw a card
    assert zone_of(s, "Train of Thought") == "p1:graveyard"
    assert not s.state.cards[c.id].zone.startswith("stack")
    check(s)


def test_replicate_count_needs_the_mana(cards):
    s = build(cards, ["Train of Thought"])
    c = to_hand(s, "Train of Thought")
    mana(s, U=2, C=2)  # {1}{U} + {1}{U}: one payment, not two
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)


def test_gigadrowse_copies_choose_new_targets(cards):
    s = build(cards, ["Gigadrowse"], ["Grizzly Bears", "Hill Giant", "Craw Wurm"])
    bears, giant, wurm = (put(s, n, "p2") for n in ("Grizzly Bears", "Hill Giant", "Craw Wurm"))
    c = to_hand(s, "Gigadrowse")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2, targets=[bears.id])
    d = s.state.rules.decision
    assert d is not None and "Replicate" in d.prompt, d.prompt  # the copies are replicate's, not storm's
    answer(s, "Choose new targets for each copy", "Hill Giant", "Craw Wurm")
    tapped = {x.name for x in (s.state.cards[bears.id], s.state.cards[giant.id], s.state.cards[wurm.id]) if x.tapped}
    assert tapped == {"Grizzly Bears", "Hill Giant", "Craw Wurm"}
    check(s)


def test_replicate_copies_are_not_cast_storm_counts_one(cards):
    s = build(cards, ["Train of Thought", "Grapeshot"])
    c = to_hand(s, "Train of Thought")
    mana(s, U=3, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    answer(s)
    g = to_hand(s, "Grapeshot")
    mana(s, R=1, C=1)
    before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=g.id, targets=["p2"])
    answer(s)  # storm: one spell (Train of Thought) cast before it this turn; its two copies weren't cast
    assert before - life(s, "p2") == 2
    check(s)


def test_magecraft_sees_each_replicate_copy(cards):
    s = build(cards, ["Train of Thought", "Archmage Emeritus"])
    put(s, "Archmage Emeritus")
    c = to_hand(s, "Train of Thought")
    mana(s, U=3, C=3)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    answer(s)
    assert hand(s) == before - 1 + 3 + 3  # three draws from the spell and its copies, three from magecraft (cast + two copies)
    check(s)


def test_a_copy_of_a_replicated_spell_isnt_replicated(cards):
    s = build(cards, ["Train of Thought", "Twincast"])
    c = to_hand(s, "Train of Thought")
    t = to_hand(s, "Twincast")
    mana(s, U=4, C=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    act(s, "p1", type="cast_spell", card_id=t.id, targets=[c.id])
    answer(s)
    # 1 cast + 1 replicate copy + 1 Twincast copy (the copy of a spell whose replicate was paid isn't cast: no trigger, 707.10)
    assert hand(s) == before - 2 + 3
    check(s)


def test_djinn_illuminatus_grants_replicate_equal_to_mana_cost(cards):
    s = build(cards, ["Djinn Illuminatus", "Lightning Bolt"])
    put(s, "Djinn Illuminatus")
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=3)
    before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"], replicate=[2])
    answer(s)
    assert before - life(s, "p2") == 9
    check(s)


def test_djinn_offers_its_grant_in_the_hints(cards):
    s = build(cards, ["Djinn Illuminatus", "Lightning Bolt"])
    put(s, "Djinn Illuminatus")
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    hints = s.view("p1")["rules"]["hints"]
    assert b.id in (hints.get("replicate111r3") or {}), hints.get("replicate111r3")


def test_replicate_with_thalia_tax_paid_once(cards):
    s = build(cards, ["Train of Thought"], ["Thalia, Guardian of Thraben"])
    put(s, "Thalia, Guardian of Thraben", "p2")
    c = to_hand(s, "Train of Thought")
    mana(s, U=3, C=4)  # {1}{U} + 2 × {1}{U} + Thalia's {1}: the increase applies once to the total cost (601.2f)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    answer(s)
    assert hand(s) == before - 1 + 3
    assert not s.state.players["p1"].mana
    check(s)


def test_shattering_spree_free_cast_still_pays_replicate(cards):
    s = build(cards, ["Shattering Spree", "Omniscience"], ["Sol Ring", "Mind Stone"])
    put(s, "Omniscience")
    a1, a2 = put(s, "Sol Ring", "p2"), put(s, "Mind Stone", "p2")
    c = to_hand(s, "Shattering Spree")
    mana(s, R=1)
    # 118.9d: cast without paying its mana cost from the table (the card menu's "Cast without paying its mana cost"), replicate may be paid
    act(s, "p1", type="cast_spell", card_id=c.id, free=True, ask_optional=True, targets=[a1.id])
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options][:1] == ["Replicate {R}"], d and [o.label for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["kicker:1"])
    assert not s.state.players["p1"].mana  # the {R} paid once (the mana cost not at all)
    answer(s, "Mind Stone")
    assert zone_of(s, "Sol Ring", "p2").endswith("graveyard") and zone_of(s, "Mind Stone", "p2").endswith("graveyard")
    check(s)


def test_omniscience_kicker_is_offered_and_only_the_kicker_is_paid(cards):
    s = build(cards, ["Burst Lightning", "Omniscience"])
    put(s, "Omniscience")
    c = to_hand(s, "Burst Lightning")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, free=True, ask_optional=True, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and "kicker:1" in [o.id for o in d.options], d and [o.label for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["kicker:1"])
    answer(s)
    assert life(s, "p2") == 36 and not s.state.players["p1"].mana  # kicked: 4 damage, {4} paid (118.9d, 601.2f)
    check(s)


def test_omniscience_without_asking_stays_unkicked(cards):  # (an intent without ask_optional: as before, nothing asked)
    s = build(cards, ["Burst Lightning", "Omniscience"])
    put(s, "Omniscience")
    c = to_hand(s, "Burst Lightning")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, free=True, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 38
    check(s)


# -- additional costs in general (601.2b, 601.2f) -------------------------------------------------------------------------------------
def bf(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def offers(s, cid):
    return s.view("p1")["rules"]["hints"].get("optional_costs", {}).get(cid, [])


def test_burst_lightning_kicked(cards):
    s = build(cards, ["Burst Lightning"])
    c = to_hand(s, "Burst Lightning")
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 36 and not s.state.players["p1"].mana
    check(s)


def test_kicker_with_a_granted_replicate_copies_a_kicked_spell(cards):  # 601.2b both announced; 707.10: the copy is kicked too
    s = build(cards, ["Burst Lightning", "Djinn Illuminatus"])
    put(s, "Djinn Illuminatus")
    c = to_hand(s, "Burst Lightning")
    mana(s, R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, replicate=[1], targets=["p2"])
    answer(s)
    assert life(s, "p2") == 32 and not s.state.players["p1"].mana
    check(s)


def test_josu_vess_kicked_makes_eight_knights(cards):
    s = build(cards, ["Josu Vess, Lich Knight"])
    c = to_hand(s, "Josu Vess, Lich Knight")
    mana(s, B=3, C=7)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    knights = [x for x in s.state.cards.values() if x.is_token and x.zone == "p1:battlefield"]
    assert sum(getattr(x, "quantity", 1) or 1 for x in knights) == 8
    check(s)


def test_thalia_taxes_a_kicked_spell_once(cards):  # 601.2f: {R} + {4} kicker + Thalia's {1}
    s = build(cards, ["Burst Lightning"], ["Thalia, Guardian of Thraben"])
    put(s, "Thalia, Guardian of Thraben", "p2")
    c = to_hand(s, "Burst Lightning")
    mana(s, R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, targets=["p2"])
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 36 and not s.state.players["p1"].mana
    check(s)


def test_a_reducer_applies_to_the_kicked_total_once(cards):  # 601.2f: {R}{4} - {1} = {R}{3}
    s = build(cards, ["Burst Lightning", "Goblin Electromancer"])
    put(s, "Goblin Electromancer")
    c = to_hand(s, "Burst Lightning")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 36 and not s.state.players["p1"].mana
    check(s)


def test_a_copy_of_a_kicked_spell_is_kicked(cards):  # 707.10
    s = build(cards, ["Burst Lightning", "Twincast"])
    c = to_hand(s, "Burst Lightning")
    t = to_hand(s, "Twincast")
    mana(s, R=1, C=4, U=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=t.id, targets=[c.id])
    answer(s)
    assert life(s, "p2") == 32 and not s.state.players["p1"].mana
    check(s)


def test_flashback_plus_kicker(cards):  # an alternative cost with an additional cost (601.2b, 601.2f)
    s = build(cards, ["Burst Lightning", "Snapcaster Mage"])
    b = card_named(s, "Burst Lightning")
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "graveyard"})
    sc = to_hand(s, "Snapcaster Mage")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=sc.id)
    answer(s, b.id)
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=b.id, kicker=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 36 and s.state.cards[b.id].zone == "p1:exile" and not s.state.players["p1"].mana
    check(s)


@pytest.mark.parametrize("buyback", [False, True])
def test_capsize_buyback(cards, buyback):
    s = build(cards, ["Capsize"], ["Hill Giant"])
    g = put(s, "Hill Giant", "p2")
    c = to_hand(s, "Capsize")
    mana(s, U=2, C=1 + 3 * buyback)
    act(s, "p1", type="cast_spell", card_id=c.id, buyback=buyback, targets=[g.id])
    answer(s)
    assert s.state.cards[c.id].zone == ("p1:hand" if buyback else "p1:graveyard") and s.state.cards[g.id].zone == "p2:hand"
    check(s)


def test_splice_glacial_ray_onto_lava_spike(cards):
    s = build(cards, ["Lava Spike", "Glacial Ray"])
    spike, ray = to_hand(s, "Lava Spike"), to_hand(s, "Glacial Ray")
    mana(s, R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spike.id, splice=[ray.id], targets=["p2", "p2"], target_counts=[1, 1])  # (Lava Spike's target, then Glacial Ray's)
    answer(s)
    assert life(s, "p2") == 35 and s.state.cards[ray.id].zone == "p1:hand"
    check(s)


def test_conspire_copies_burn_trail_and_the_copy_isnt_cast(cards):
    s = build(cards, ["Burn Trail", "Raging Goblin", "Goblin Piker", "Grapeshot"])
    put(s, "Raging Goblin")
    put(s, "Goblin Piker")
    c = to_hand(s, "Burn Trail")
    mana(s, R=1, C=3)
    found = offers(s, c.id)
    assert found
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[found[0]["id"]], targets=["p2"])
    answer(s)
    assert life(s, "p2") == 34 and all(x.tapped for x in bf(s, "Raging Goblin") + bf(s, "Goblin Piker"))
    g = to_hand(s, "Grapeshot")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=g.id, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 32  # storm 1: the conspire copy wasn't cast
    check(s)


def test_bargain_torch_the_tower(cards):
    s = build(cards, ["Torch the Tower"], ["Hill Giant"])
    g = put(s, "Hill Giant", "p2")
    act(s, "p1", type="create_token", player="p1", token={"name": "Clue", "type_line": "Token Artifact — Clue"})
    c = to_hand(s, "Torch the Tower")
    mana(s, R=1)
    found = offers(s, c.id)
    assert found
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[found[0]["id"]], targets=[g.id])
    answer(s)
    # bargained: 3 damage (the 3/3 dies), and a permanent it damaged that would die is exiled instead
    assert s.state.cards[g.id].zone == "p2:exile" and not [x for x in s.state.cards.values() if x.is_token and x.zone == "p1:battlefield"]
    check(s)


def test_squad_makes_a_copy_per_payment(cards):
    s = build(cards, ["Arco-Flagellant"])
    c = to_hand(s, "Arco-Flagellant")
    mana(s, B=1, C=6)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    answer(s)
    assert sum(getattr(x, "quantity", 1) or 1 for x in bf(s, "Arco-Flagellant")) == 3
    check(s)


def test_fling_uses_the_sacrificed_creatures_power(cards):
    s = build(cards, ["Fling", "Craw Wurm"])
    w = put(s, "Craw Wurm")
    c = to_hand(s, "Fling")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    answer(s, w.id)
    assert life(s, "p2") == 34 and s.state.cards[w.id].zone == "p1:graveyard"
    check(s)


def test_mandatory_costs_that_cant_be_paid_refuse_the_cast(cards):
    s = build(cards, ["Bone Splinters", "Thrill of Possibility"], ["Hill Giant"])
    g = put(s, "Hill Giant", "p2")
    bone = to_hand(s, "Bone Splinters")
    for cid in list(s.state.zones.get("p1:hand", [])):
        if cid != bone.id:
            act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"})
    mana(s, B=1, R=1, C=1)
    assert bone.id not in s.view("p1")["rules"]["hints"].get("castable", [])
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bone.id, targets=[g.id])  # no creature to sacrifice (601.2c, 601.2h)
    act(s, "p1", type="move", card_ids=[bone.id], to={"player": "p1", "zone": "library"})
    thrill = to_hand(s, "Thrill of Possibility")  # the only card in hand: nothing to discard
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=thrill.id)


def test_toxic_deluge_pays_x_life(cards):
    s = build(cards, ["Toxic Deluge"], ["Hill Giant"])
    g = put(s, "Hill Giant", "p2")
    c = to_hand(s, "Toxic Deluge")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=3)
    answer(s)
    assert life(s) == 37 and s.state.cards[g.id].zone == "p2:graveyard"
    check(s)


def test_commander_tax_adds_to_a_kicked_commander(cards):  # 903.8: the tax is an additional cost, added to the kicked total (601.2f)
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Josu Vess, Lich Knight", [(9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    josu = card_named(s, "Josu Vess, Lich Knight")
    assert josu.zone == "p1:command"
    mana(s, B=3, C=7)
    act(s, "p1", type="cast_spell", card_id=josu.id, kicker=1)
    answer(s)
    assert s.state.cards[josu.id].zone == "p1:battlefield"
    act(s, "p1", type="move", card_ids=[josu.id], to={"player": "p1", "zone": "command"})
    mana(s, B=3, C=8)  # {2}{B}{B} + {5}{B} + tax {2} = 12: 11 isn't enough
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=josu.id, kicker=1)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=josu.id, kicker=1)
    answer(s)
    assert s.state.cards[josu.id].zone == "p1:battlefield" and not s.state.players["p1"].mana
    check(s)


def test_escalate_needs_a_discard_per_extra_mode(cards):  # 702.120a: Collective Brutality's escalate cost, paid for each mode beyond the first
    s = build(cards, ["Collective Brutality", "Lightning Bolt", "Grizzly Bears"], ["Hill Giant"])
    c = to_hand(s, "Collective Brutality")
    for cid in list(s.state.zones.get("p1:hand", [])):
        if cid != c.id:
            act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"})
    to_hand(s, "Lightning Bolt")  # one card to discard: two modes, not three
    giant = put(s, "Hill Giant", "p2")
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):  # three modes: two discards, one card to discard
        act(s, "p1", type="cast_spell", card_id=c.id, modes=[0, 1, 2], targets=["p2", giant.id, "p2"])
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[0, 2], targets=["p2", "p2"])
    answer(s)
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and life(s, "p2") == 38 and life(s) == 42
    check(s)
