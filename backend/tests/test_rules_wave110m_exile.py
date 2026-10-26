"""Wave 110M: cards in exile that carry a counter-driven trigger. 702.62c-style "when the last time counter is removed from this card, if it's exiled, you may cast it without paying its
mana cost": granted by Alaundo the Seer to the card it exiles from its controller's hand (no suspend: nothing comes off at upkeep). Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave36a_kit import ready
from tests.wave110m_kit import *

ALAUNDO = "Alaundo the Seer"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([ALAUNDO])


def table(cards, hand=("Lightning Bolt",)):
    s = build(cards, [ALAUNDO, *hand], ["Elite Vanguard"], forests=20)
    ship = put(s, ALAUNDO)
    ready(s, ALAUNDO)
    for n in hand:
        to_hand(s, n)
    return s, ship


def activate(s, ship, pick):
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind == "choose_cards" and d.min_choices == 1
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, pick).id])
    answer(s)


def test_the_exiled_card_gets_time_counters_equal_to_its_mana_value(cards):
    s, ship = table(cards, ["Grizzly Bears"])
    activate(s, ship, "Grizzly Bears")
    bears = card_named(s, "Grizzly Bears")
    assert bears.zone == "p1:exile" and bears.counters.get("time") == 2
    check(s)


def test_a_mana_value_zero_card_gets_no_counters_and_never_triggers(cards):
    s, ship = table(cards, [])
    # (the drawn card is the one exiled: a Forest, mana value 0)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    assert len(exiled) == 1 and not exiled[0].counters.get("time")
    check(s)


def test_the_next_activation_takes_a_counter_off_the_other_card_and_casts_it_when_it_was_the_last(cards):
    s, ship = table(cards, ["Lightning Bolt", "Grizzly Bears"])
    activate(s, ship, "Lightning Bolt")  # (1 counter)
    stops(s)
    next_turn(s)
    ready(s, ALAUNDO)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and d.min_choices == 1:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, "Grizzly Bears").id])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(30):  # the Bolt's last counter came off: its owner may cast it for free
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_one" and "yes" in [o.id for o in d.options]:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2" if "p2" in [o.id for o in d.options] else d.options[0].id])
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and life(s, "p2") == 37
    assert card_named(s, "Grizzly Bears").counters.get("time") == 2  # (the card just exiled keeps all its counters)
    check(s)


def test_a_creature_cast_this_way_has_haste_until_end_of_turn(cards):
    s, ship = table(cards, ["Llanowar Elves", "Grizzly Bears"])
    activate(s, ship, "Llanowar Elves")
    stops(s)
    next_turn(s)
    ready(s, ALAUNDO)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and d.min_choices == 1:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, "Grizzly Bears").id])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if "yes" in [o.id for o in d.options] else d.options[0].id])
    elves = card_named(s, "Llanowar Elves")
    assert elves.zone == "p1:battlefield" and "haste" in ch(s, elves).keywords
    next_turn(s)
    assert "haste" not in ch(s, s.state.cards[elves.id]).keywords
    check(s)


# -- Tawnos's Coffin ---------------------------------------------------------------------------------------------------------------------------
COFFIN = "Tawnos's Coffin"
test_coffin_full = full_test([COFFIN])


def coffin_table(cards):
    s = build(cards, [COFFIN, "Pacifism", "Disenchant"], ["Grizzly Bears"], forests=20)
    coffin = put(s, COFFIN)
    ready(s, COFFIN)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="counter", card_ids=[bears.id], kind="+1/+1", delta=2)
    act(s, "p2", type="counter", card_ids=[bears.id], kind="stun", delta=1)
    cast(s, "Pacifism", [bears.id])
    answer(s)
    pacifism = card_named(s, "Pacifism")
    assert pacifism.attached_to == bears.id
    fund(s, "{3}")
    act(s, "p1", type="activate_ability", card_id=coffin.id, ability=1, targets=[bears.id])
    answer(s)
    return s, coffin, bears, pacifism


def test_the_coffin_exiles_the_creature_and_its_auras_together(cards):
    s, coffin, bears, pacifism = coffin_table(cards)
    assert s.state.cards[bears.id].zone == "p2:exile" and s.state.cards[pacifism.id].zone == "p1:exile"
    assert s.state.cards[coffin.id].tapped
    check(s)


def test_the_creature_comes_back_tapped_with_its_counters_and_its_auras_attached_when_the_coffin_leaves(cards):
    s, coffin, bears, pacifism = coffin_table(cards)
    cast(s, "Disenchant", [coffin.id])
    answer(s)
    back = s.state.cards[bears.id]
    assert back.zone == "p2:battlefield" and back.tapped
    assert back.counters.get("+1/+1") == 2 and back.counters.get("stun") == 1
    assert s.state.cards[pacifism.id].zone == "p1:battlefield" and s.state.cards[pacifism.id].attached_to == bears.id
    check(s)


def untap_step(s, keep):
    """Pass until the untap step asks which permanents to keep tapped, and answer."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None:
            assert "keep tapped" in d.prompt
            act(s, d.player, type="choose", decision_id=d.id, option_ids=keep)
            answer(s)
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no untap question")


def test_the_creature_comes_back_when_the_coffin_untaps(cards):
    s, coffin, bears, pacifism = coffin_table(cards)
    untap_step(s, [])
    assert not s.state.cards[coffin.id].tapped
    back = s.state.cards[bears.id]
    assert back.zone == "p2:battlefield" and back.tapped and back.counters.get("+1/+1") == 2
    assert s.state.cards[pacifism.id].attached_to == bears.id
    check(s)


def test_keeping_the_coffin_tapped_keeps_the_creature_exiled(cards):
    s, coffin, bears, pacifism = coffin_table(cards)
    untap_step(s, [coffin.id])
    assert s.state.cards[coffin.id].tapped and s.state.cards[bears.id].zone == "p2:exile"
    check(s)


# -- Zygon Infiltrator -------------------------------------------------------------------------------------------------------------------------
ZYGON = "Zygon Infiltrator"
test_zygon_full = full_test([ZYGON])


def zygon_table(cards):
    s = build(cards, [ZYGON, "Lightning Bolt"], ["Hill Giant"], forests=20)
    zygon = put(s, ZYGON)
    giant = put(s, "Hill Giant", "p2")
    ready(s, ZYGON)
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=zygon.id, ability=0, targets=[giant.id])
    answer(s)
    return s, zygon, giant


def test_zygon_taps_the_creature_stuns_it_and_becomes_a_copy_while_it_stays_tapped(cards):
    s, zygon, giant = zygon_table(cards)
    assert s.state.cards[giant.id].tapped and s.state.cards[giant.id].counters.get("stun") == 1
    assert ch(s, zygon).name == "Hill Giant" and ch(s, zygon).pt == (3, 3)
    check(s)


def test_the_copy_lasts_through_the_stun_counters_untap_and_ends_when_the_creature_finally_untaps(cards):
    s, zygon, giant = zygon_table(cards)
    stops(s)
    to_phase(s, "main1", turn=2)  # Bob's untap step: the stun counter comes off instead of the Giant untapping
    assert s.state.cards[giant.id].tapped and not s.state.cards[giant.id].counters.get("stun")
    assert ch(s, zygon).name == "Hill Giant"
    to_phase(s, "main1", turn=4)  # Bob's next untap step: it untaps
    assert not s.state.cards[giant.id].tapped and ch(s, s.state.cards[zygon.id]).name == ZYGON
    check(s)


def test_the_copy_ends_when_the_creature_leaves_the_battlefield(cards):
    s, zygon, giant = zygon_table(cards)
    cast(s, "Lightning Bolt", [giant.id])
    answer(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and ch(s, s.state.cards[zygon.id]).name == ZYGON
    check(s)


# -- Old-Growth Troll --------------------------------------------------------------------------------------------------------------------------
TROLL = "Old-Growth Troll"
test_troll_full = full_test([TROLL])


def troll_dies(cards, forests_in_play=1):
    s = build(cards, [TROLL, "Murder"], ["Elite Vanguard"], forests=20)
    troll = put(s, TROLL)
    lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:forests_in_play]
    for c in lands:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Murder", [troll.id])
    answer(s)
    return s, troll, lands


def test_the_troll_returns_as_an_aura_enchanting_a_forest_and_is_no_longer_a_creature(cards):
    s, troll, lands = troll_dies(cards)
    back = s.state.cards[troll.id]
    assert back.zone == "p1:battlefield" and back.attached_to == lands[0].id
    c = ch(s, back)
    assert "Creature" not in c.types and "Enchantment" in c.types and "Aura" in c.subtypes
    check(s)


def test_the_enchanted_forest_taps_for_two_green_and_can_be_sacrificed_for_a_troll_warrior(cards):
    s, troll, lands = troll_dies(cards)
    texts = [a.text for a in ch(s, s.state.cards[lands[0].id]).abilities]
    assert any(t.startswith("{T}: Add {G}{G}") for t in texts) and any("Sacrifice" in t and "Troll Warrior" in t for t in texts)
    index = next(a.index for a in ch(s, s.state.cards[lands[0].id]).abilities if "Sacrifice" in a.text)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=lands[0].id, ability=index)
    answer(s)
    warriors = [c for c in s.state.cards.values() if c.is_token and c.name == "Troll Warrior" and c.zone == "p1:battlefield"]
    assert len(warriors) == 1 and warriors[0].tapped and ch(s, warriors[0]).pt == (4, 4)
    check(s)


def test_with_no_forest_to_enchant_the_aura_stays_in_the_graveyard(cards):
    s, troll, lands = troll_dies(cards, forests_in_play=0)
    assert s.state.cards[troll.id].zone == "p1:graveyard"
    check(s)


# -- Baron Helmut Zemo -------------------------------------------------------------------------------------------------------------------------
ZEMO = "Baron Helmut Zemo"
test_zemo_full = full_test([ZEMO])


def zemo_table(cards, murders=8):
    s = build(cards, [ZEMO, *(["Murder"] * murders)], ["Elite Vanguard", "Hill Giant", "Grizzly Bears", "Llanowar Elves"], forests=20)
    zemo = put(s, ZEMO)
    ready(s, ZEMO)
    victims = [put(s, n, "p2") for n in ("Elite Vanguard", "Hill Giant", "Grizzly Bears", "Llanowar Elves")]
    for c in [c for c in s.state.cards.values() if c.name == "Murder" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    return s, zemo, victims


def boast(s, zemo):
    return next(a.index for a in ch(s, zemo).abilities if a.text.startswith("Boast"))


def attack_with(s, zemo):
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": zemo.id, "target": "p2"}])


def test_the_boast_needs_fifteen_black_symbols_exiled_and_an_attack_this_turn(cards):
    s, zemo, victims = zemo_table(cards, murders=7)  # (14 symbols in all: not enough)
    attack_with(s, zemo)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=zemo.id, ability=boast(s, zemo))
    check(s)


def test_zemo_copies_the_exiled_cards_and_casts_up_to_three_of_them_free(cards):
    s, zemo, victims = zemo_table(cards)
    attack_with(s, zemo)
    gy = [c.id for c in s.state.cards.values() if c.name == "Murder" and c.zone == "p1:graveyard"]
    act(s, "p1", type="activate_ability", card_id=zemo.id, ability=boast(s, zemo), cost_choices=[{"component": 0, "cards": gy}])
    aimed: list[str] = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            ids = [o.id for o in d.options]
            pick = next((v.id for v in victims if v.id in ids and v.id not in aimed), ids[0])
            if d.kind == "choose_one" and pick in ids and any(v.id == pick for v in victims):
                aimed.append(pick)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if "yes" in ids else pick])
    dead = [v for v in victims if s.state.cards[v.id].zone == "p2:graveyard"]
    assert len(dead) == 3 and all(s.state.cards[c].zone == "p1:exile" for c in gy)
    check(s)


def test_the_boast_cannot_be_activated_before_zemo_attacks(cards):
    s, zemo, victims = zemo_table(cards)
    gy = [c.id for c in s.state.cards.values() if c.name == "Murder" and c.zone == "p1:graveyard"]
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=zemo.id, ability=boast(s, zemo), cost_choices=[{"component": 0, "cards": gy}])
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in gy)  # (nothing was paid; no replay check: ``ready`` writes the creature's age directly)


# -- Balduvian Shaman --------------------------------------------------------------------------------------------------------------------------
SHAMAN = "Balduvian Shaman"
test_shaman_full = full_test([SHAMAN])


def shaman_table(cards):
    s = build(cards, [SHAMAN, "Crusade", "Elite Vanguard", "Lim-Dûl the Necromancer"], ["Elite Vanguard"], forests=20)
    shaman = put(s, SHAMAN)
    crusade = put(s, "Crusade")
    ready(s, SHAMAN)
    return s, shaman, crusade


def test_the_color_word_is_changed_and_the_enchantment_gains_cumulative_upkeep(cards):
    s, shaman, crusade = shaman_table(cards)
    vanguard = put(s, "Elite Vanguard")  # a white 2/1
    limdul = put(s, "Lim-Dûl the Necromancer")  # a black 4/4
    assert ch(s, vanguard).pt == (3, 2) and ch(s, limdul).pt == (4, 4)
    act(s, "p1", type="activate_ability", card_id=shaman.id, ability=0, targets=[crusade.id])
    for word in ("white", "black"):  # white → black
        d = s.state.rules.decision
        assert d is not None and word in [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[word])
    answer(s)
    assert ch(s, vanguard).pt == (2, 1) and ch(s, limdul).pt == (5, 5)  # "Black creatures get +1/+1"
    assert "cumulative upkeep" in {k.lower() for k in ch(s, s.state.cards[crusade.id]).keywords}
    check(s)


def test_an_enchantment_that_already_has_cumulative_upkeep_cannot_be_targeted(cards):
    s, shaman, crusade = shaman_table(cards)
    act(s, "p1", type="activate_ability", card_id=shaman.id, ability=0, targets=[crusade.id])
    for word in ("white", "black"):
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[word])
    answer(s)
    s.state.cards[shaman.id].tapped = False
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=shaman.id, ability=0, targets=[crusade.id])


# -- Ludevic, Necrogenius // Olag, Ludevic's Hubris -------------------------------------------------------------------------------------------
LUDEVIC = "Ludevic, Necrogenius // Olag, Ludevic's Hubris"
test_ludevic_full = full_test([LUDEVIC])


def ludevic_table(cards, x=2, extra=()):
    s = build(cards, [LUDEVIC, "Grizzly Bears", "Hill Giant", *extra], ["Elite Vanguard"], forests=20)
    ludevic = put(s, LUDEVIC)
    ready(s, LUDEVIC)
    gy = []
    for n in ("Grizzly Bears", "Hill Giant"):
        c = card_named(s, n)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
        gy.append(c)
    return s, ludevic, gy


def olag_activate(s, ludevic, exiled, x):
    mana(s, U=2, B=2, C=x)
    act(s, "p1", type="activate_ability", card_id=ludevic.id, ability=1, x_value=x, cost_choices=[{"component": 1, "cards": [c.id for c in exiled]}])


def test_ludevic_becomes_olag_a_copy_of_the_chosen_exiled_creature_with_counters(cards):
    s, ludevic, gy = ludevic_table(cards)
    olag_activate(s, ludevic, gy, 2)
    d = s.state.rules.decision
    assert d is not None and set(o.id for o in d.options) == {c.id for c in gy}  # (a choice of the creature cards exiled with it)
    giant = next(c for c in gy if c.name == "Hill Giant")
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[giant.id])
    answer(s)
    olag = ch(s, s.state.cards[ludevic.id])
    assert olag.name == "Olag, Ludevic's Hubris" and olag.pt == (6, 6)  # (4/4 and two +1/+1 counters)
    assert "Legendary" in olag.supertypes and "Zombie" in olag.subtypes and "Giant" in olag.subtypes and {"U", "B", "R"} <= set(olag.colors)
    check(s)


def test_x_cannot_be_zero(cards):
    s, ludevic, gy = ludevic_table(cards)
    with pytest.raises(ActionError):
        olag_activate(s, ludevic, [], 0)
