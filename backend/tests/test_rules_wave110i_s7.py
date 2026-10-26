"""Wave 110I (session 7): real Oracle text; scenarios check replay and save/load.

* Fasting: the draw step is skipped only when its controller says so (614.10a, 614.1); skipping gains 2 life; drawing destroys it (121.1).
* Smelting Vat: the up-to-two noncreature artifacts put onto the battlefield have total mana value at most the sacrificed artifact's (608.2d).
* Lodestone Bauble: targets are basic lands of one player's graveyard (115.1), put on top of that library; that player draws at the next upkeep.
* Noctis: Warp-Strike returns it at the beginning of its owner's next declare attackers step (507.1, 603.7), tapped and attacking (508.4), unblockable that combat; 508.8.
* Balduvian Fallen / Heart of Bogardan: the "is paid" / "doesn't pay" cumulative upkeep triggers (702.24a, 603.2), sized by the mana spent / the age counters.
* Sheltered Valley: entering sacrifices each other permanent named Sheltered Valley you control first (614.1a), none of other names.
* Hipparion: blocking a creature with power 3 or greater costs {1} (509.1d); power 2 costs nothing.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate
from tests.wave9c_kit import build, card_named, life, mana, pt, put
from tests.wave110a_kit import answer
from tests.wave110c_kit import check, make_db

HIPPARION = "This creature can't block creatures with power 3 or greater unless you pay {1}."
FASTING = ("At the beginning of your upkeep, put a hunger counter on this enchantment. Then destroy this enchantment if it has five or more hunger counters on it.\n"
           "If you would begin your draw step, you may skip that step instead. If you do, you gain 2 life.\nWhen you draw a card, destroy this enchantment.")
VAT = ("{1}, {T}, Sacrifice another artifact: Reveal the top eight cards of your library. Put up to two noncreature artifact cards with total mana value "
       "less than or equal to the sacrificed artifact's mana value from among them onto the battlefield and the rest on the bottom of your library in a random order.")
BAUBLE = ("{1}, {T}, Sacrifice this artifact: Put up to four target basic land cards from a player's graveyard on top of their library in any order. "
          "That player draws a card at the beginning of the next turn's upkeep.")
NOCTIS = ("Whenever a creature you control enters during combat, you may attach target Equipment you control to target creature you control.\n"
          "Warp-Strike \u2014 {3}: Exile Noctis. Return it to the battlefield under its owner's control tapped and attacking at the beginning of that player's next declare attackers step. "
          "It can't be blocked that combat.")
FALLEN = ("Cumulative upkeep {1} (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its upkeep cost for each age counter on it.)\n"
          "Whenever this creature's cumulative upkeep is paid, it gets +1/+0 until end of turn for each {B} or {R} spent this way.")
HEART = ("Cumulative upkeep {2} (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its upkeep cost for each age counter on it.)\n"
         "When a player doesn't pay this enchantment's cumulative upkeep, this enchantment deals X damage to target player or planeswalker and each creature that player or "
         "that planeswalker's controller controls, where X is twice the number of age counters on this enchantment minus 2.")
VALLEY = ("If this land would enter, instead sacrifice each other permanent named Sheltered Valley you control, then put this land onto the battlefield.\n"
          "At the beginning of your upkeep, if you control three or fewer lands, you gain 1 life.\n{T}: Add {C}.")
EXTRA = [real("Sheltered Valley", "", 0, "Land", VALLEY, None, ""),
         real("Balduvian Fallen", "{3}{B}", 4, "Creature \u2014 Zombie", FALLEN, ("3", "5"), "B"),
         real("Heart of Bogardan", "{2}{R}{R}", 4, "Enchantment", HEART, None, "R"),
         real("Noctis, Heir Apparent", "{W}{U}{B}", 3, "Legendary Creature \u2014 Human Noble", NOCTIS, ("2", "3"), "WUB"),
         real("Probe Bears", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
         real("Probe Wall", "{1}", 1, "Creature \u2014 Wall", "", ("0", "9"), ""),
         real("Lodestone Bauble", "{2}", 2, "Artifact", BAUBLE, None, ""),
         real("Smelting Vat", "{2}", 2, "Artifact", VAT, None, ""),
         real("Probe Gem1", "{1}", 1, "Artifact", "", None, ""), real("Probe Gem2", "{2}", 2, "Artifact", "", None, ""),
         real("Probe Gem3", "{3}", 3, "Artifact", "", None, ""), real("Probe Golem", "{1}", 1, "Artifact Creature — Golem", "", ("1", "1"), ""),
         real("Fasting", "{W}", 1, "Enchantment", FASTING, None, "W"),
         real("Hipparion", "{1}{G}", 2, "Creature — Horse", HIPPARION, ("1", "3"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(("power", "paid"), [("3", True), ("4", True), ("2", False)])
def test_hipparion_block_tax(cards, power, paid):
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import combat_step, pool

    s = sandbox(cards)
    a = creature(s, "p1", "Atk", f"{power}/4")
    h = creature(s, "p2", "Hip", "1/3", text=HIPPARION)
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    if paid:
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": h.id, "attacker_id": a.id}])
        pool(s, "p2", G=1)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": h.id, "attacker_id": a.id}])
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.cards[h.id].is_blocking
    assert not s.state.players["p2"].mana.get("G")
    check(s)


@pytest.mark.parametrize("skip", [True, False])
def test_fasting_optional_skip(cards, skip):
    s = build(cards, ["Fasting"])
    put(s, "Fasting")
    hand = len(s.state.zones["p1:hand"])
    asked = 0
    for _ in range(200):
        d = s.state.rules.decision
        if s.state.turn.number >= 3 and s.state.turn.phase == "main1":
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif (d.resume or {}).get("step") == "skip_may110i":
            asked += 1
            assert d.player == "p1"
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes" if skip else "no"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert asked == 1
    fasting = card_named(s, "Fasting")
    assert (life(s) == 42 and len(s.state.zones["p1:hand"]) == hand and fasting.zone == "p1:battlefield") if skip \
        else (life(s) == 40 and len(s.state.zones["p1:hand"]) == hand + 1 and s.state.cards[fasting.id].zone == "p1:graveyard")
    check(s)


def _vat(cards, sac):
    s = build(cards, ["Smelting Vat", "Probe Gem1", "Probe Gem2", "Probe Gem3", "Probe Golem"])
    vat = put(s, "Smelting Vat")
    rock = put(s, sac)  # the only other artifact: sacrificed as the cost
    for n in ("Probe Golem", "Probe Gem3", "Probe Gem2", "Probe Gem1"):
        if n != sac:
            act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "library"}, position="top")
    mana(s, C=1)
    activate(s, "p1", vat)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            return s, d, rock
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no pick")


def test_smelting_vat_total_mana_value(cards):
    s, d, rock = _vat(cards, "Probe Gem3")
    g1, g2, golem = (card_named(s, n) for n in ("Probe Gem1", "Probe Gem2", "Probe Golem"))
    assert golem.id not in [o.id for o in d.options] and g1.id in [o.id for o in d.options]  # noncreature only
    answer(s, [g1.id, g2.id])  # 1 + 2 <= 3
    assert {s.state.cards[g1.id].zone, s.state.cards[g2.id].zone} == {"p1:battlefield"}
    assert s.state.cards[golem.id].zone == "p1:library" and s.state.cards[rock.id].zone == "p1:graveyard"
    check(s)


def test_smelting_vat_refuses_too_much_mana_value(cards):
    s, d, rock = _vat(cards, "Probe Gem1")  # mana value 1
    g2, g3 = card_named(s, "Probe Gem2"), card_named(s, "Probe Gem3")
    with pytest.raises(ActionError):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[g2.id])  # 2 > 1
    answer(s, [])
    assert s.state.cards[g2.id].zone == "p1:library" and s.state.cards[g3.id].zone == "p1:library"
    check(s)


def _bauble(cards, targets):
    s = build(cards, ["Lodestone Bauble"])
    bauble = put(s, "Lodestone Bauble")
    islands = [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:3]
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:1]
    act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "graveyard"})
    mana(s, C=1)
    return s, bauble, islands, forests


def test_bauble_returns_lands_and_that_player_draws(cards):
    s, bauble, islands, forests = _bauble(cards, None)
    hand = len(s.state.zones["p2:hand"])
    activate(s, "p1", bauble, targets=islands[:2], target_counts=[2])
    answer(s)
    assert [s.state.cards[c].zone for c in islands[:2]] == ["p2:library"] * 2 and s.state.cards[islands[2]].zone == "p2:graveyard"
    assert s.state.cards[forests[0]].zone == "p1:graveyard"
    assert len(s.state.zones["p2:hand"]) == hand
    from tests.wave100c_kit import to_phase

    to_phase(s, "main1", turn=2)
    assert len(s.state.zones["p2:hand"]) == hand + 2  # upkeep draw (Bauble) and draw step
    check(s)


def test_bauble_refuses_lands_from_two_graveyards(cards):
    s, bauble, islands, forests = _bauble(cards, None)
    with pytest.raises(ActionError):
        activate(s, "p1", bauble, targets=[islands[0], forests[0]], target_counts=[2])


def test_bauble_with_no_target_refused(cards):
    """Zero targets leave "that player" undefined (no CR rule or ruling): the activation is not offered."""
    s, bauble, islands, forests = _bauble(cards, None)
    with pytest.raises(ActionError):
        activate(s, "p1", bauble, targets=[], target_counts=[0])
    check(s)


@pytest.mark.parametrize("attack", [True, False, None])  # None: nobody else can attack (508.8: Noctis alone still gets blockers and damage)
def test_noctis_returns_attacking_at_declare_attackers_and_cannot_be_blocked(cards, attack):
    from tests.wave100c_kit import to_phase

    s = build(cards, ["Noctis, Heir Apparent", "Probe Bears"], ["Probe Wall"])
    noctis = put(s, "Noctis, Heir Apparent")
    bears = put(s, "Probe Bears") if attack is not None else None
    wall = put(s, "Probe Wall", "p2")
    to_phase(s, "main1", turn=3)  # (the next turn: nothing is summoning sick)
    mana(s, C=3)
    activate(s, "p1", noctis, "Warp-Strike")
    answer(s)
    assert s.state.cards[noctis.id].zone == "p1:exile"
    blocked_tried = False
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.turn.phase in ("combat_damage", "end_combat", "main2"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            assert s.state.cards[noctis.id].zone == "p1:exile"  # it returns after the declaration
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}] if attack else [])
        elif d.kind == "declare_blockers":
            assert s.state.cards[noctis.id].is_attacking and s.state.cards[noctis.id].tapped
            with pytest.raises(ActionError):
                act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": noctis.id}])
            blocked_tried = True
            act(s, "p2", type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert blocked_tried and life(s, "p2") == 40 - 2 - (2 if attack else 0)
    check(s)


def _upkeep(s, name, counters, turn=3):
    from tests.wave100c_kit import to_phase

    card = put(s, name)
    if counters:
        act(s, "p1", type="counter", card_ids=[card.id], kind="age", delta=counters)
    to_phase(s, "upkeep", turn=turn)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "pay_or_sacrifice":
            return card, d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no cumulative upkeep question")


@pytest.mark.parametrize(("mana_paid", "bonus"), [({"B": 1}, 1), ({"R": 1}, 1), ({"G": 1}, 0), ({"C": 1}, 0)])
def test_balduvian_fallen_pumps_for_each_b_or_r_spent(cards, mana_paid, bonus):
    s = build(cards, ["Balduvian Fallen"])
    fallen, d = _upkeep(s, "Balduvian Fallen", 0)
    mana(s, **mana_paid)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    answer(s)
    assert s.state.cards[fallen.id].zone == "p1:battlefield" and s.state.cards[fallen.id].counters.get("age") == 1
    assert pt(s, "Balduvian Fallen") == (3 + bonus, 5)
    check(s)


def test_balduvian_fallen_two_age_counters_two_mana(cards):
    s = build(cards, ["Balduvian Fallen"])
    fallen, d = _upkeep(s, "Balduvian Fallen", 1)  # second upkeep: {1} twice
    mana(s, B=1, G=1)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    answer(s)
    assert pt(s, "Balduvian Fallen") == (4, 5)  # only the {B} counts
    check(s)


def test_balduvian_fallen_unpaid_is_sacrificed_without_pump(cards):
    s = build(cards, ["Balduvian Fallen"])
    fallen, d = _upkeep(s, "Balduvian Fallen", 0)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["sacrifice"])
    answer(s)
    assert s.state.cards[fallen.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_heart_of_bogardan_damages_only_when_unpaid(cards, pay):
    s = build(cards, ["Heart of Bogardan", "Probe Wall"], ["Probe Bears"])
    bears = put(s, "Probe Bears", "p2")
    mine = put(s, "Probe Wall")
    heart, d = _upkeep(s, "Heart of Bogardan", 1)  # two age counters: X = 2 * 2 - 2 = 2
    if pay:
        mana(s, C=4)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    else:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["sacrifice"])
    answer(s, "p2")
    assert s.state.cards[heart.id].zone == ("p1:battlefield" if pay else "p1:graveyard")
    assert life(s, "p2") == (40 if pay else 38)
    assert s.state.cards[bears.id].zone == ("p2:battlefield" if pay else "p2:graveyard")
    assert s.state.cards[mine.id].zone == "p1:battlefield" and life(s) == 40
    check(s)


def test_sheltered_valley_sacrifices_the_older_copy_only(cards):
    s = build(cards, ["Sheltered Valley", "Sheltered Valley", "Forest"])
    first, second = [c for c in s.state.cards.values() if c.name == "Sheltered Valley" and c.owner == "p1"][:2]
    forest = put(s, "Forest")
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=first.id)
    answer(s)
    assert s.state.cards[first.id].zone == "p1:battlefield"
    from tests.wave100c_kit import to_phase

    to_phase(s, "main1", turn=3)  # (the next land drop)
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=second.id)
    answer(s)
    assert s.state.cards[first.id].zone == "p1:graveyard" and s.state.cards[second.id].zone == "p1:battlefield"
    assert s.state.cards[forest.id].zone == "p1:battlefield"
    check(s)


def test_sheltered_valley_alone_just_enters(cards):
    s = build(cards, ["Sheltered Valley", "Forest"])
    forest = put(s, "Forest")
    valley = card_named(s, "Sheltered Valley")
    act(s, "p1", type="move", card_ids=[valley.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=valley.id)
    answer(s)
    assert s.state.cards[valley.id].zone == "p1:battlefield" and s.state.cards[forest.id].zone == "p1:battlefield"
    check(s)
