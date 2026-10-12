"""Wave 38C: cast permissions with an "exile it instead" rider, and spells exiled instead of going to the graveyard as they resolve (CR 2026-09-25),
real Oracle text (tests/fixtures/wave38c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 614.1a / 601.2 / 608.2g: "you may cast target instant or sorcery card from your graveyard. If that spell would be put into your graveyard, exile it instead.
  If you cast a spell this way, …" (Helmut Zemo): the spell is cast as the ability resolves; it is exiled whether it resolves or is countered; the rider after it
  reads whether a spell was cast. "… and mana of any type can be spent to cast that spell" (Quistis Trepe, 118.14).
* 400.7 / 707.10 / 704.5e: the replacement is of that spell as that object; a copy of it is another object, never exiled (it ceases to exist).
* 614.1a / 608.2n: "exile that card instead of putting it into your graveyard as it resolves" (Feather, Lilah, Gandalf of the Secret Fire, Goliath Daydreamer) applies
  to the spell that resolves, not to one that is countered; "If you do" (return it to your hand at the beginning of the next end step; it becomes plotted, 702.170c;
  it gains suspend, 702.62) follows only the exile that happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave38c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w38c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Helmut Zemo, Mastermind", "Quistis Trepe", "Feather, the Redeemed", "Lilah, Undefeated Slickshot", "Gandalf of the Secret Fire",
        "Goliath Daydreamer", "Aven Interrupter", "Make Your Own Luck", "Tinybones, the Pickpocket", "Halo Forager", "Isareth the Awakener"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_these_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_kellan_joins_up_stays_manual_since_its_it_is_a_card_paid_for_a_cost(cards):
    """"… you may exile a nonland card … from your hand. If you do, it becomes plotted.": the exiled card is the cost's object, which the grammar doesn't bind
    (it would read "it" as Kellan itself): not automated."""
    assert coverage.of_card_data(cards.resolve("Kellan Joins Up")).level != "FULL"


def grave(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def ready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0  # (no longer summoning sick)


def play_out(s, prefer=(), respond=None, topup=None, limit=60):
    """Answer whatever is asked (the first of ``prefer`` on offer, else the first option) and let the stack resolve. ``respond``: (a spell, a player, the card
    that player casts, its mana): that player casts the card at the spell once it is the top of the stack. ``topup``: (a part of a prompt, mana): Alice has that mana from
    the moment she is asked that (mana empties between steps)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            if topup is not None and topup[0] in d.prompt:
                mana(s, "p1", **topup[1])
                topup = None
            ids = [o.id for o in d.options]
            chosen = next((p for p in prefer if p in ids), None)
            if d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            elif d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blocks=[])
            else:  # ("none": a choice that may be no card is answered with no card)
                act(s, d.player, type="choose", decision_id=d.id,
                    option_ids=[] if "none" in prefer and d.min_choices == 0 else [chosen] if chosen else ids[: max(1, d.min_choices)])
        elif respond is not None and (s.state.zones.get("stack") or [None])[-1] == respond[0].id and zone(s, respond[2]) == f"{respond[1]}:hand":
            act(s, respond[1], type="cast_spell", card_id=respond[2].id, targets=[respond[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def attack(s, c, prefer=(), respond=None, topup=None, **pool):
    act(s, "p1", type="pass_priority")  # → declare attackers
    if pool:
        mana(s, "p1", **pool)  # (mana empties between steps, and an X is offered up to the mana there is when the attack trigger resolves)
    if respond is not None:
        mana(s, respond[1], **respond[3])  # (a player with no mana is passed over: who answers has it by the time a spell is cast)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"}])
    play_out(s, prefer, respond, topup)


def zone(s, c):
    return s.state.cards[c.id].zone


def named(s, name):
    return [c for c in s.state.cards.values() if c.name == name]


def counters(s, c, kind):
    return s.state.cards[c.id].counters.get(kind, 0)


# -- Helmut Zemo, Mastermind: a cast permission with the exile rider and "If you cast a spell this way" --------------------------------------
def helmut(cards, theirs=(), mine=()):
    s = build(cards, ["Helmut Zemo, Mastermind", "Lightning Bolt", *mine], theirs)
    h = put(s, "Helmut Zemo, Mastermind")
    ready(s, h)
    return s, h, grave(s, "Lightning Bolt")


def test_helmut_zemo_casts_the_instant_from_the_graveyard_exiles_it_and_grows(cards):
    s, h, bolt = helmut(cards)
    attack(s, h, prefer=(bolt.id, "p2"), R=1)
    assert life(s, "p2") == 34  # the Bolt (3) and then Helmut, who has grown to 3 power, in combat (3)
    assert zone(s, bolt) == "p1:exile"  # 614.1a: exiled instead of going to your graveyard
    assert counters(s, h, "+1/+1") == 1  # "If you cast a spell this way"
    check(s)


def test_helmut_zemo_gets_no_counter_when_no_spell_is_cast(cards):
    s, h, bolt = helmut(cards)
    attack(s, h, prefer=("none",), R=1)  # (the choice is "no card")
    assert life(s, "p2") == 38 and zone(s, bolt) == "p1:graveyard" and counters(s, h, "+1/+1") == 0  # (Helmut hits for 2)
    check(s)


def test_a_countered_helmut_spell_is_still_exiled_and_still_counts_as_cast(cards):
    s, h, bolt = helmut(cards, ["Counterspell"])
    counter = to_hand(s, "Counterspell", "p2")
    attack(s, h, prefer=(bolt.id, "p2"), respond=(bolt, "p2", counter, {"U": 2}), R=1)
    assert life(s, "p2") == 37  # the Bolt was countered: only Helmut (3) hit
    assert zone(s, bolt) == "p1:exile" and zone(s, counter) == "p2:graveyard"  # 701.6a: it would be put into your graveyard: exiled instead
    assert counters(s, h, "+1/+1") == 1
    check(s)


def test_a_copy_of_a_helmut_spell_is_not_exiled_it_ceases_to_exist(cards):
    """400.7 / 707.10: the replacement is of the spell that was cast; Twincast's copy of it is another object, and a copy that leaves the stack ceases to exist
    (704.5e), so it is in no graveyard and no exile."""
    s, h, bolt = helmut(cards, mine=["Twincast"])
    twincast = to_hand(s, "Twincast")
    attack(s, h, prefer=(bolt.id, "p2", "keep"), respond=(bolt, "p1", twincast, {"U": 2}), R=1)
    assert life(s, "p2") == 31  # the copy (3), the Bolt (3), Helmut (3)
    assert zone(s, bolt) == "p1:exile" and zone(s, twincast) == "p1:graveyard"
    copies = [c for c in named(s, "Lightning Bolt") if c.id != bolt.id]
    assert all(c.zone not in ("p1:graveyard", "p1:exile", "p2:graveyard", "p2:exile") for c in copies)
    assert [c.name for c in s.state.cards.values() if c.zone in ("p1:exile", "p2:exile")] == ["Lightning Bolt"]
    check(s)


# -- Quistis Trepe: "and mana of any type can be spent to cast that spell" (118.14) on the cast the trigger makes -----------------------------------
def test_quistis_casts_a_sorcery_from_a_graveyard_with_any_mana_and_it_is_exiled_instead(cards):
    s = build(cards, ["Quistis Trepe"], ["Divination"])
    divination = grave(s, "Divination", "p2")
    quistis = to_hand(s, "Quistis Trepe")
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", U=1, G=5)  # (the {U} of Quistis; a Divination's {2}{U} is paid with green mana alone)
    act(s, "p1", type="cast_spell", card_id=quistis.id)
    play_out(s, prefer=(divination.id,))
    assert zone(s, quistis) == "p1:battlefield"
    assert zone(s, divination) == "p2:exile"  # "If that spell would be put into a graveyard, exile it instead": its owner's exile, not Bob's graveyard
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2  # (Quistis left it; Divination drew two cards for Alice)
    assert s.state.players["p1"].mana.get("G", 0) == 0
    check(s)


def test_quistis_may_cast_nothing(cards):
    s = build(cards, ["Quistis Trepe"], ["Divination"])
    divination = grave(s, "Divination", "p2")
    quistis = to_hand(s, "Quistis Trepe")
    mana(s, "p1", U=1, G=5)
    act(s, "p1", type="cast_spell", card_id=quistis.id)
    play_out(s, prefer=(divination.id, "none"))
    assert zone(s, divination) == "p2:graveyard" and zone(s, quistis) == "p1:battlefield"
    check(s)


# -- Feather, the Redeemed: "exile that card instead of putting it into your graveyard as it resolves. If you do, return it to your hand …" ---------
def feather(cards, theirs=(), mine=()):
    s = build(cards, ["Feather, the Redeemed", "Giant Growth", *mine], theirs)
    f = put(s, "Feather, the Redeemed")
    return s, f, to_hand(s, "Giant Growth")


def cast_growth(s, f, gg, respond=None, prefer=("keep",)):
    mana(s, "p1", G=1)
    if respond is not None:
        mana(s, respond[1], **respond[3])
    act(s, "p1", type="cast_spell", card_id=gg.id, targets=[f.id])
    play_out(s, prefer, respond)


def end_step(s):
    """Play on through this turn's end step (its delayed triggers resolve on the way)."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn)
    play_out(s)


def test_feather_exiles_the_spell_as_it_resolves_and_returns_it_to_hand_at_the_end_step(cards):
    s, f, gg = feather(cards)
    cast_growth(s, f, gg)
    assert zone(s, gg) == "p1:exile"  # 614.1a, 608.2n: exiled instead of put into your graveyard as it resolved
    assert pt(s, "Feather, the Redeemed") == (6, 7)  # (it resolved: +3/+3)
    check(s)
    end_step(s)
    assert zone(s, gg) == "p1:hand"  # "If you do, return it to your hand at the beginning of the next end step"
    check(s)


def test_a_countered_spell_does_not_resolve_so_feather_does_not_exile_it(cards):
    s, f, gg = feather(cards, ["Counterspell"])
    counter = to_hand(s, "Counterspell", "p2")
    cast_growth(s, f, gg, respond=(gg, "p2", counter, {"U": 2}))
    assert zone(s, gg) == "p1:graveyard" and zone(s, counter) == "p2:graveyard"  # (608.2n is about resolving; a countered spell goes there, 701.6a)
    end_step(s)
    assert zone(s, gg) == "p1:graveyard"  # nothing to return: "If you do" did not happen
    check(s)


def test_a_copy_of_a_feather_spell_is_not_exiled_and_the_card_returns_once(cards):
    s, f, gg = feather(cards, mine=["Twincast"])
    twincast = to_hand(s, "Twincast")
    cast_growth(s, f, gg, respond=(gg, "p1", twincast, {"U": 2}))
    assert zone(s, gg) == "p1:exile" and zone(s, twincast) == "p1:graveyard"
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:exile"] == ["Giant Growth"]  # (the copy ceased to exist, 704.5e)
    assert not [c for c in named(s, "Giant Growth") if c.id != gg.id and c.zone in ("p1:graveyard", "p1:hand", "p1:exile")]
    end_step(s)
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:hand"].count("Giant Growth") == 1 and zone(s, gg) == "p1:hand"
    check(s)


# -- Lilah, Undefeated Slickshot: "… exile that spell instead of putting it into your graveyard as it resolves. If you do, it becomes plotted." ------
def plotted(s, c):
    return [p for p in s.state.rules.permissions if p.card == c.id and p.free and p.sorcery]


def next_main(s, turns=2):
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number == turn + turns and s.state.turn.phase == "main1")


def test_lilah_exiles_a_multicolored_spell_cast_from_hand_as_it_resolves_and_it_becomes_plotted(cards):
    s = build(cards, ["Lilah, Undefeated Slickshot", "Lightning Helix"])
    put(s, "Lilah, Undefeated Slickshot")
    helix = to_hand(s, "Lightning Helix")
    mana(s, "p1", R=1, W=1)
    act(s, "p1", type="cast_spell", card_id=helix.id, targets=["p2"])
    play_out(s)
    assert life(s, "p2") == 37 and life(s) == 43  # it resolved
    assert zone(s, helix) == "p1:exile"  # 614.1a, 608.2n
    (permission,) = plotted(s, helix)  # 702.170c-d: its owner may cast it for free, on a later turn, as a sorcery
    assert permission.player == "p1" and permission.after_turn == s.state.turn.number
    with pytest.raises(ActionError):  # (not on the turn it became plotted)
        act(s, "p1", type="cast_spell", card_id=helix.id, free=True, targets=["p2"])
    check(s)
    next_main(s)
    act(s, "p1", type="cast_spell", card_id=helix.id, free=True, targets=["p2"])
    play_out(s)
    assert life(s, "p2") == 34 and zone(s, helix) == "p1:graveyard"  # (cast from exile, not from hand: Lilah doesn't exile it again)
    assert life(s) == 46 and not plotted(s, helix)
    check(s)


def test_lilah_ignores_a_spell_of_one_color(cards):
    s = build(cards, ["Lilah, Undefeated Slickshot", "Lightning Bolt"])
    put(s, "Lilah, Undefeated Slickshot")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    play_out(s)
    assert zone(s, bolt) == "p1:graveyard" and not plotted(s, bolt)
    check(s)


# -- Gandalf of the Secret Fire: "… exile that card with three time counters on it instead of …. Then if the exiled card doesn't have suspend, it gains suspend." --
def test_gandalf_suspends_an_instant_cast_from_hand_during_an_opponents_turn(cards):
    s = build(cards, ["Gandalf of the Secret Fire", "Lightning Bolt"])
    put(s, "Gandalf of the Secret Fire")
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="set_prefs", full_control=True)  # (Alice gets priority in every step, her opponent's too)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    play_out(s)
    assert life(s, "p2") == 37  # it resolved
    assert zone(s, bolt) == "p1:exile" and counters(s, bolt, "time") == 3  # 702.62b: a suspended card
    assert bolt.id in s.state.rules.suspended
    check(s)
    until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")
    play_out(s)  # (the upkeep trigger removes a time counter)
    assert counters(s, bolt, "time") == 2
    check(s)


def test_gandalf_ignores_a_spell_cast_during_your_own_turn(cards):
    s = build(cards, ["Gandalf of the Secret Fire", "Lightning Bolt"])
    put(s, "Gandalf of the Secret Fire")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    play_out(s)
    assert zone(s, bolt) == "p1:graveyard" and counters(s, bolt, "time") == 0 and bolt.id not in s.state.rules.suspended
    check(s)


# -- Goliath Daydreamer: a dream counter on the exiled spell; "cast a spell from among cards you own in exile with dream counters on them" ----------
def test_goliath_daydreamer_exiles_a_spell_with_a_dream_counter_and_casts_it_when_it_attacks(cards):
    s = build(cards, ["Goliath Daydreamer", "Lightning Bolt"])
    g = put(s, "Goliath Daydreamer")
    ready(s, g)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    play_out(s)
    assert life(s, "p2") == 37 and zone(s, bolt) == "p1:exile" and counters(s, bolt, "dream") == 1
    check(s)
    attack(s, g, prefer=(bolt.id, "p2"))  # "you may cast a spell from among cards you own in exile with dream counters on them without paying its mana cost"
    assert life(s, "p2") == 30  # the Bolt again (3) and Goliath (4)
    assert zone(s, bolt) == "p1:graveyard"  # (cast from exile: not exiled again)
    check(s)


def test_goliath_daydreamer_casts_only_cards_with_dream_counters(cards):
    s = build(cards, ["Goliath Daydreamer", "Lightning Bolt"])
    g = put(s, "Goliath Daydreamer")
    ready(s, g)
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "exile"})  # (an exiled card with no counter)
    attack(s, g)
    assert zone(s, bolt) == "p1:exile" and life(s, "p2") == 36  # nothing to cast
    check(s)


# -- "It becomes plotted." after another exile (702.170c): Aven Interrupter and Make Your Own Luck ---------------------------------------------------
def test_aven_interrupter_exiles_a_spell_that_becomes_plotted(cards):
    s = build(cards, ["Aven Interrupter", "Divination"])
    divination, aven = to_hand(s, "Divination"), to_hand(s, "Aven Interrupter")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="set_prefs", hold_priority=True)  # (to answer her own Divination)
    mana(s, "p1", U=1, G=2, W=3)
    act(s, "p1", type="cast_spell", card_id=divination.id)
    act(s, "p1", type="cast_spell", card_id=aven.id)  # (flash, in response)
    play_out(s, prefer=(divination.id,))
    assert zone(s, divination) == "p1:exile" and len(s.state.zones["p1:hand"]) == hand - 2  # exiled, not resolved: no cards drawn
    assert len(plotted(s, divination)) == 1
    check(s)
    next_main(s)
    act(s, "p1", type="cast_spell", card_id=divination.id, free=True)
    play_out(s)
    assert len(s.state.zones["p1:hand"]) == hand - 2 + 1 + 2  # (a draw step, and the two Divination draws)
    check(s)


def test_make_your_own_luck_plots_the_card_it_exiles_from_the_top_three(cards):
    s = build(cards, ["Make Your Own Luck", "Giant Growth", "Lightning Bolt", "Opt"])
    for name in ("Opt", "Lightning Bolt", "Giant Growth"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "library"}, position="top")
    luck = to_hand(s, "Make Your Own Luck")
    growth = card_named(s, "Giant Growth")
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", G=4, U=1)
    act(s, "p1", type="cast_spell", card_id=luck.id)
    play_out(s, prefer=(growth.id,))
    assert zone(s, growth) == "p1:exile" and len(plotted(s, growth)) == 1
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2  # (the other two went to the hand)
    check(s)


# -- "you may pay {X}. When you do, … target … card with mana value X …" (603.12): the reflexive ability's target is chosen knowing the X paid ------
def forager_table(cards, x):
    s = build(cards, ["Halo Forager"], ["Lightning Bolt"])
    bolt = grave(s, "Lightning Bolt", "p2")
    forager = to_hand(s, "Halo Forager")
    mana(s, "p1", U=1, B=1, G=1 + x)  # {1}{U}{B}, and {X}
    act(s, "p1", type="cast_spell", card_id=forager.id)
    return s, bolt


def test_halo_forager_pays_x_and_casts_a_card_of_that_mana_value_from_a_graveyard_exiling_it(cards):
    s, bolt = forager_table(cards, 1)
    play_out(s, prefer=("x:1", bolt.id, "p2"))
    assert life(s, "p2") == 37  # (cast free, as the reflexive ability resolves)
    assert zone(s, bolt) == "p2:exile"  # "If that spell would be put into a graveyard, exile it instead": its owner's
    assert s.state.players["p1"].mana == {}  # {X} was paid
    check(s)


def test_halo_forager_with_another_x_has_no_card_to_cast(cards):
    s, bolt = forager_table(cards, 2)  # (the Bolt has mana value 1)
    play_out(s, prefer=("x:2", bolt.id, "p2"))
    assert life(s, "p2") == 40 and zone(s, bolt) == "p2:graveyard"
    assert s.state.players["p1"].mana == {}  # (the {X} was paid all the same)
    check(s)


def test_isareth_returns_the_creature_card_of_the_mana_value_paid_with_a_corpse_counter(cards):
    s = build(cards, ["Isareth the Awakener", "Grizzly Bears"])
    isareth = put(s, "Isareth the Awakener")
    ready(s, isareth)
    bears = grave(s, "Grizzly Bears")
    attack(s, isareth, prefer=("x:2", bears.id), B=2)
    assert zone(s, bears) == "p1:battlefield" and counters(s, bears, "corpse") == 1
    assert s.state.rules.object_id(bears.id) in s.state.rules.exile_if_leaves  # "If that creature would leave the battlefield, exile it instead"
    check(s)


def test_isareth_with_the_wrong_x_returns_nothing(cards):
    s = build(cards, ["Isareth the Awakener", "Grizzly Bears"])
    isareth = put(s, "Isareth the Awakener")
    ready(s, isareth)
    bears = grave(s, "Grizzly Bears")
    attack(s, isareth, prefer=("x:3", bears.id), B=3)
    assert zone(s, bears) == "p1:graveyard"
    check(s)


# -- Tinybones, the Pickpocket: the same cast ("and mana of any type can be spent") of a permanent card from the damaged player's graveyard ---------
def test_tinybones_casts_a_permanent_card_from_the_damaged_players_graveyard_with_any_mana(cards):
    s = build(cards, ["Tinybones, the Pickpocket"], ["Grizzly Bears"])
    tinybones = put(s, "Tinybones, the Pickpocket")
    ready(s, tinybones)
    bears = grave(s, "Grizzly Bears", "p2")
    attack(s, tinybones, prefer=(bears.id,), topup=("Choose a spell to cast", {"B": 2}))  # (Grizzly Bears' {1}{G}, paid with black mana)
    assert zone(s, bears) == "p1:battlefield" and s.state.cards[bears.id].controller == "p1" and life(s, "p2") == 39
    assert s.state.players["p1"].mana == {}
    check(s)


# -- Rod of Absorption: the unconditional wording ("a player", "a graveyard") of the same replacement ---------------------------------------------
def test_rod_of_absorption_exiles_any_players_spell_as_it_resolves(cards):
    s = build(cards, ["Rod of Absorption"], ["Lightning Bolt"])
    put(s, "Rod of Absorption")
    bolt = to_hand(s, "Lightning Bolt", "p2")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.priority == "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    play_out(s)
    assert life(s) == 37 and zone(s, bolt) == "p2:exile"  # (Bob's spell: his exile)
    check(s)
