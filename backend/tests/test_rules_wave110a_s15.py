"""Wave 110A session 15: layer-6 timestamp order for the Zinnia offspring grant against a real static "loses all abilities" (Sludge Monster)."""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

from app.rules import wave110a_grants  # isort: skip


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _bears(s):
    return next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield" and not c.token)


def _run(cards, wipe_first):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears", "Sludge Monster"])
    put(s, "Zinnia, Valley's Voice")
    if wipe_first:
        put(s, "Sludge Monster")
    c = to_hand(s, "Grizzly Bears")
    fund(s, "{1}{G}{2}")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    if not wipe_first:
        put(s, "Sludge Monster")
    check(s)
    bears = _bears(s)
    bears.counters["slime"] = 1  # Sludge Monster: "Non-Horror creatures with slime counters on them lose all abilities"
    s.state.seq += 1
    return s, bears


def test_wipe_earlier_than_the_grant_keeps_the_granted_offspring(cards):  # 613.7: the permanent's timestamp is later than Sludge Monster's, so the grant applies after the wipe
    s, bears = _run(cards, True)
    assert wave110a_grants.granted_offspring(ch(s, bears))


def test_wipe_later_than_the_grant_removes_the_granted_offspring(cards):  # 613.7: Sludge Monster entered after the creature, so its wipe applies after the grant
    s, bears = _run(cards, False)
    assert not wave110a_grants.granted_offspring(ch(s, bears))


def test_full(cards):
    from app.rules import coverage

    assert all(coverage.of_card_data(cards.resolve(n)).level == "FULL" for n in ("The Master, Multiplied", "Aboleth Spawn", "Metamorphic Alteration", "Scheming Fence", "Fblthp, Lost on the Range", "Berserker's Frenzy"))


def _unused_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("The Master, Multiplied")).level == "FULL"


def _myriad(cards):
    from tests.test_rules_conditionals import until as until_
    from tests.test_rules_wave6e_statics import attack_with
    from tests.test_rules_wave15e_keywords import build3, next_own_turn

    s = build3(cards, "The Master, Multiplied", "Grizzly Bears")
    master = put(s, "The Master, Multiplied")
    next_own_turn(s)
    attack_with(s, master)
    until_(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and "token copy" in s.state.rules.decision.prompt)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    until_(s, lambda s: s.state.turn.phase == "main2")
    return s


def test_master_multiplied_keeps_its_myriad_tokens_at_end_of_combat(cards):  # 614.17: the delayed exile trigger can't exile the controller's creature tokens
    s = _myriad(cards)
    toks = [c for c in s.state.cards.values() if c.token and c.name == "The Master, Multiplied" and c.zone == "p1:battlefield"]
    assert len(toks) == 1
    check(s)


SPAWN = "Aboleth Spawn"


def _spawn(cards, creature, yes, targets=None):
    s = build(cards, [creature, "Grizzly Bears"], [SPAWN])
    put(s, SPAWN, pid="p2")
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    cast(s, creature)
    answer(s, *([] if targets is None else [targets]), "yes" if yes else "no")
    return s, hand


@pytest.mark.parametrize("yes", [True, False])
def test_aboleth_spawn_copies_an_opponents_enters_trigger(cards, yes):  # 603.2d, 707.10: p1's Elvish Visionary draws for p1; the copy (p2 controls it) draws for p2
    s, hand = _spawn(cards, "Elvish Visionary", yes)
    assert (len(s.state.zones["p1:hand"]) - hand["p1"], len(s.state.zones["p2:hand"]) - hand["p2"]) == (1, 1 if yes else 0)  # p1: +1 (card to hand) -1 (cast) +1 (draw)
    check(s)


def test_aboleth_spawn_ignores_its_controllers_own_creatures(cards):
    s = build(cards, ["Elvish Visionary", SPAWN])
    put(s, SPAWN)
    n = len(s.state.zones["p1:hand"])
    cast(s, "Elvish Visionary")
    answer(s)
    assert len(s.state.zones["p1:hand"]) == n + 1  # card to hand +1, cast -1, draw +1, no copy
    check(s)


ALTER = "Metamorphic Alteration"


def ch_pt(s, c):
    from app.rules import sba

    card = s.state.cards[c.id]
    return sba.power(card, ch(s, c)), sba.toughness(card, ch(s, c))


def _alter(cards):
    s = build(cards, [ALTER, "Grizzly Bears", "Llanowar Elves", "Naturalize"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    cast(s, ALTER, [bears.id])
    answer(s, elves.id)
    return s, bears, elves


def test_metamorphic_alteration_enchanted_creature_becomes_a_copy_of_the_chosen_one(cards):  # 707.2c, 613.2a: layer-1 copy while the Aura stays attached (611.2b)
    s, bears, elves = _alter(cards)
    assert (ch(s, bears).name, ch_pt(s, bears)) == ("Llanowar Elves", (1, 1)) and ch(s, elves).name == "Llanowar Elves"
    cast(s, "Naturalize", [card_named(s, ALTER).id])  # the Aura leaves: the copy effect ends
    answer(s)
    assert (ch(s, bears).name, ch_pt(s, bears)) == ("Grizzly Bears", (2, 2))
    check(s)


def test_metamorphic_alteration_copy_is_fixed_when_it_starts(cards):  # 707.2c: later changes to the chosen creature's copiable values are not followed
    s, bears, elves = _alter(cards)
    act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "graveyard"})
    assert ch(s, bears).name == "Llanowar Elves"  # the copy needs no more than the values taken when it started
    check(s)


FENCE = "Scheming Fence"


def _fence(cards, chosen):
    s = build(cards, [FENCE, "Shivan Dragon", "Jace Beleren"])
    dragon, jace = put(s, "Shivan Dragon"), put(s, "Jace Beleren")
    act(s, "p1", type="set_counter", card_id=jace.id, kind="loyalty", value=3)
    cast(s, FENCE)
    answer(s, {"dragon": dragon.id, "jace": jace.id, "none": "none"}[chosen])
    return s, dragon, jace, card_named(s, FENCE)


def test_scheming_fence_stops_the_chosen_permanents_abilities_and_borrows_them(cards):  # 602.5, 113.10, 609.4b: Fence has Shivan Dragon's {R}: +1/+0, payable with any color
    s, dragon, jace, fence = _fence(cards, "dragon")
    fund(s, "{G}")
    with pytest.raises(Exception, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=dragon.id, ability=1)
    mana(s, G=1)
    base = ch_pt(s, fence)
    act(s, "p1", type="activate_ability", card_id=fence.id, ability=next(a.index for a in ch(s, fence).abilities if a.kind == "activated"))
    answer(s)
    assert ch_pt(s, fence)[0] == base[0] + 1  # the Fence's copy of the pump, paid with green mana
    check(s)


def test_scheming_fence_chosen_planeswalker_loses_loyalty_abilities_but_none_are_lent(cards):  # "except for loyalty abilities"
    s, dragon, jace, fence = _fence(cards, "jace")
    assert not [a for a in ch(s, fence).abilities if a.kind in ("activated", "loyalty")]
    with pytest.raises(Exception, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=jace.id, ability=0)
    check(s)


def test_scheming_fence_may_choose_nothing(cards):
    s, dragon, jace, fence = _fence(cards, "none")
    assert not [a for a in ch(s, fence).abilities if a.kind == "activated"]
    fund(s, "{R}")
    act(s, "p1", type="activate_ability", card_id=dragon.id, ability=1)
    check(s)


FBLTHP = "Fblthp, Lost on the Range"


def _top(s, name):
    c = to_hand(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    return c


def _plot_index(s, c):
    return next(a.index for a in ch(s, c).abilities if "plot" in a.keywords)


def test_fblthp_plots_the_top_card_for_its_mana_cost(cards):  # 702.170b, 116.2k: exile it and pay the plot cost (its mana cost); 702.170d: castable free on a later turn
    s = build(cards, [FBLTHP, "Lightning Bolt"])
    put(s, FBLTHP)
    bolt = _top(s, "Lightning Bolt")
    fund(s, "{R}")
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=_plot_index(s, bolt))
    answer(s)
    assert s.state.cards[bolt.id].zone == "p1:exile"
    assert any(p.card == bolt.id and p.free for p in s.state.rules.permissions)  # plotted: cast without paying its mana cost on a later turn
    check(s)


@pytest.mark.parametrize("what", ["land", "second", "nofblthp"])
def test_fblthp_plots_only_the_top_nonland_card_while_it_is_there(cards, what):
    s = build(cards, [FBLTHP, "Lightning Bolt", "Grizzly Bears"])
    if what != "nofblthp":
        put(s, FBLTHP)
    if what == "land":
        top = next(c for c in s.state.cards.values() if c.zone == "p1:library" and c.name == "Forest")
        act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
        assert not [a for a in ch(s, top).abilities if "plot" in a.keywords]
        return
    if what == "second":
        bolt = _top(s, "Lightning Bolt")
        bears = _top(s, "Grizzly Bears")
        assert not [a for a in ch(s, bolt).abilities if "plot" in a.keywords] and [a for a in ch(s, bears).abilities if "plot" in a.keywords]
        return
    bolt = _top(s, "Lightning Bolt")
    assert not [a for a in ch(s, bolt).abilities if "plot" in a.keywords]


def test_without_fblthp_the_top_card_cannot_be_plotted(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Lightning Bolt"])
    bolt = _top(s, "Lightning Bolt")
    fund(s, "{R}")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=bolt.id, ability=100)
    assert s.state.cards[bolt.id].zone == "p1:library"


FRENZY = "Berserker's Frenzy"


def _frenzy(cards, monkeypatch, *dice, pick=None):
    from tests.test_rules_wave12a_counters_keywords import rolls
    from tests.test_rules_wave34b_activated import stops, to_phase

    s = build(cards, [FRENZY, "Grizzly Bears"], ["Hill Giant"])
    bears, wall = put(s, "Grizzly Bears"), put(s, "Hill Giant", "p2")
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    rolls(monkeypatch, *dice)
    cast(s, FRENZY)
    answer(s, *([[wall.id]] if pick else [[]]))
    return s, bears, wall


@pytest.mark.parametrize("dice", [(3, 10), (14, 2)])
def test_berserkers_frenzy_low_result_makes_the_chosen_creatures_block_if_able(cards, monkeypatch, dice):  # 706.2: the higher die is the result (<= 14); 509.1c requirement
    from tests.test_rules_wave34b_activated import to_phase

    s, bears, wall = _frenzy(cards, monkeypatch, *dice, pick=True)
    assert not s.state.rules.declare_choosers
    to_phase(s, "declare_blockers")
    with pytest.raises(Exception):  # it must block if able
        act(s, "p2", type="declare_blockers", blocks=[])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": bears.id}])
    assert s.state.cards[wall.id].is_blocking
    check(s)


def test_berserkers_frenzy_ignores_the_lower_roll(cards, monkeypatch):  # 15-20 from the higher die although the lower (2) would be the low row
    s, bears, wall = _frenzy(cards, monkeypatch, 2, 16)
    assert "block" in s.state.rules.declare_choosers  # the caster chooses blocks
    check(s)


def test_berserkers_frenzy_cannot_be_cast_after_blockers_are_declared(cards):  # the spell's own timing line (601.3)
    from app.game.errors import ActionError
    from tests.test_rules_wave34b_activated import stops, to_phase

    s = build(cards, [FRENZY, "Grizzly Bears"], ["Hill Giant"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    to_phase(s, "declare_blockers")
    with pytest.raises(ActionError):
        cast(s, FRENZY)
