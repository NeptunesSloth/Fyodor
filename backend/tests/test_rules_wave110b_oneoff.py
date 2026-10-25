"""Wave 110B: single cards read from an exact wording (real Oracle text, tests/fixtures/wave110b_cards.json); each scenario checks replay and save/load.

* Prince of Thralls: 118.12 "unless that opponent pays 3 life": the opponent whose permanent went to the graveyard chooses.
* Oath of Lim-Dul: 120.3/603.2 one "sacrifice a permanent … unless you discard a card" for each 1 life lost, each with its own choice (608.2c).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, ch, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Prince of Thralls", "Oath of Lim-Dûl", "Chaos Lord", "Divine Intervention", "Herald of Anafenza", "Guardian of New Benalia", "Aloe Alchemist", "Parapet Thrasher", "Bane of the Living", "Warbreak Trumpeter", "Kadena's Silencer", "Longhorn Sharpshooter", "Plague Reaver", "Quakebringer", "Suppressor Skyguard"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("pays", [False, True])
def test_prince_takes_the_permanent_unless_its_controller_pays_3_life(cards, pays):
    s = build(cards, ["Prince of Thralls", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Prince of Thralls")
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])
    drive(s, lambda d: [next((o.id for o in d.options if o.label.startswith("Pay") == pays), d.options[0].id)])
    assert s.state.players["p2"].life == (37 if pays else 40)
    assert s.state.cards[bears.id].zone == ("p2:graveyard" if pays else "p1:battlefield")
    check(s)


@pytest.mark.parametrize("discards", [0, 1, 3])
def test_oath_asks_once_per_life_lost(cards, discards):
    """Lightning Bolt: 3 damage is 3 life lost, so three separate sacrifice-unless-discard choices; each discard saves one permanent."""
    s = build(cards, ["Oath of Lim-Dûl", "Forest", "Forest", "Forest", "Lightning Bolt"], [])
    put(s, "Oath of Lim-Dûl")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"]
    act(s, "p1", type="move", card_ids=forests[:3], to={"player": "p1", "zone": "battlefield"})
    hand = forests[3:3 + discards]
    for f in hand:
        act(s, "p1", type="move", card_ids=[f], to={"player": "p1", "zone": "hand"})
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p1"])
    def answer(d):
        return [next((o.id for o in d.options if o.id in hand), d.options[0].id)]

    drive(s, answer)
    lands = [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]
    assert len(lands) == discards
    check(s)


@pytest.mark.parametrize("extra, passes", [(0, False), (1, True)])
def test_chaos_lord_goes_to_the_opponent_only_when_the_permanent_count_is_even(cards, extra, passes):
    """Chaos Lord: a trailing "if" is checked as the ability resolves (608.2c, 603.4 is only for intervening ifs); every permanent counts, zero is even."""
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Chaos Lord", "Forest"], [])
    lord = put(s, "Chaos Lord")
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:extra]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    to_turn(s, 3, "upkeep")
    drive(s, lambda d: ["p2"] if any(o.id == "p2" for o in d.options) else None)
    assert (s.state.cards[lord.id].controller == "p2") == passes
    check(s)


def test_divine_intervention_is_a_draw_when_the_last_counter_goes(cards):
    """Divine Intervention: removing the second of two counters (one per upkeep of its controller) makes the game a draw (104.4c)."""
    from tests.test_rules_conditionals import to_turn, until

    s = build(cards, ["Divine Intervention"], [])
    mana(s, "p1", W=2, C=6)
    di = to_hand(s, "Divine Intervention")
    act(s, "p1", type="cast_spell", card_id=di.id)
    drive(s)
    assert s.state.cards[di.id].counters.get("intervention") == 2
    to_turn(s, 3)
    drive(s)
    assert s.state.cards[di.id].counters.get("intervention") == 1 and s.state.rules.draw_reason is None
    until(s, lambda s: s.state.rules.draw_reason is not None)
    assert s.state.turn.number == 5
    assert s.state.rules.draw_reason is not None
    check(s)


def test_herald_of_anafenza_makes_a_warrior_for_its_own_outlast_only(cards):
    """Herald of Anafenza: 702.107a outlast is an activated ability; only the Herald whose outlast was activated makes the token (two Heralds)."""
    s = build(cards, ["Herald of Anafenza", "Herald of Anafenza"], [])
    heralds = [c.id for c in s.state.cards.values() if c.name == "Herald of Anafenza" and c.zone == "p1:library"][:2]
    act(s, "p1", type="move", card_ids=heralds, to={"player": "p1", "zone": "battlefield"})
    for h in heralds:
        s.state.rules.controlled_since[h].turn = 0
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=heralds[0], ability=0)
    drive(s)
    warriors = [c for c in s.state.cards.values() if c.name == "Warrior" and c.zone == "p1:battlefield"]
    assert len(warriors) == 1 and s.state.cards[heralds[0]].counters.get("+1/+1") == 1
    check(s)


@pytest.mark.parametrize("enlists", [True, False])
def test_guardian_of_new_benalia_scries_only_when_it_enlists(cards, enlists):
    """Guardian of New Benalia: 702.154a "Whenever this creature enlists a creature, scry 2." (not when the enlist is declined)."""
    from tests.wave110b_kit import attack

    s = build(cards, ["Guardian of New Benalia", "Grizzly Bears"], [])
    guardian = put(s, "Guardian of New Benalia")
    bears = put(s, "Grizzly Bears")
    s.state.rules.controlled_since[bears.id].turn = 0
    attack(s, guardian)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id] if enlists else [])
    kinds = []
    drive(s, lambda d: kinds.append(d.kind) or None)
    assert ("choose_cards" in kinds) == enlists, kinds  # the scry's choice of cards for the top or bottom (701.22a)
    check(s)


def _plot(s, name, **paid):
    c = to_hand(s, name)
    mana(s, "p1", **paid)
    from tests.wave110b_kit import ch

    plot = next(a.index for a in ch(s, c).abilities if a.text.startswith("Plot"))
    act(s, "p1", type="activate_ability", card_id=c.id, ability=plot)  # the plot special action (702.170a-b)
    return c


def test_longhorn_sharpshooter_deals_2_damage_when_it_becomes_plotted(cards):
    """Longhorn Sharpshooter: 702.170d "When this card becomes plotted" triggers from exile; the card is the source of the damage (120.1)."""
    s = build(cards, ["Longhorn Sharpshooter"], [])
    c = _plot(s, "Longhorn Sharpshooter", R=1, C=3)
    drive(s, lambda d: ["p2"] if any(o.id == "p2" for o in d.options) else None)
    assert s.state.cards[c.id].zone == "p1:exile" and s.state.players["p2"].life == 38
    check(s)


def test_aloe_alchemist_pumps_a_creature_when_it_becomes_plotted(cards):
    """Aloe Alchemist: 702.170d "When this card becomes plotted, target creature gets +3/+2 and gains trample until end of turn." (613.4c)"""
    from tests.wave110b_kit import pt

    s = build(cards, ["Aloe Alchemist", "Grizzly Bears"], [])
    put(s, "Grizzly Bears")
    _plot(s, "Aloe Alchemist", G=1, C=1)
    drive(s)
    assert pt(s, "Grizzly Bears") == (5, 4)
    check(s)


def test_faux_herald_non_outlast_ability_with_the_same_text_is_not_an_outlast_activation(cards):
    """702.107a: only a keyword outlast ability (printed "Outlast {2}{W}") is "this creature's outlast ability"; the same words printed in full are not."""
    s = build(cards, ["Faux Herald"], [])
    faux = put(s, "Faux Herald")
    s.state.rules.controlled_since[faux.id].turn = 0
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=faux.id, ability=0)
    drive(s)
    assert s.state.cards[faux.id].counters.get("+1/+1") == 1
    assert not [c for c in s.state.cards.values() if c.name == "Warrior"]
    check(s)


def test_parapet_thrasher_dragon_damage_modes(cards):
    """603.2c: "Whenever one or more Dragons you control deal combat damage to an opponent": "that opponent" is the player dealt damage."""
    from tests.wave110b_kit import attack

    s = build(cards, ["Parapet Thrasher"], ["Sol Ring"])
    thrasher = put(s, "Parapet Thrasher")
    ring = put(s, "Sol Ring", "p2")
    attack(s, thrasher)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind != "declare_blockers"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["0:0"])
    drive(s)
    assert s.state.cards[ring.id].zone == "p2:graveyard"
    check(s)


def _face_down(s, name, x_cost_mana):
    """Cast ``name`` face down (morph, {3}) and return it."""
    card = to_hand(s, name)
    mana(s, "p1", **x_cost_mana)
    act(s, "p1", type="cast_spell", card_id=card.id, face_down=True)
    drive(s)
    assert s.state.cards[card.id].face_down
    return card


@pytest.mark.parametrize("x", [0, 2])
def test_bane_of_the_living_shrinks_all_creatures_by_the_x_paid(cards, x):
    """107.3a, 702.37e: "Morph {X}{B}{B}": X is announced as it is turned face up; "-X/-X" in the turned-face-up trigger reads it."""
    s = build(cards, ["Bane of the Living", "Grizzly Bears"], [])
    bane = _face_down(s, "Bane of the Living", {"C": 3})
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", B=2, C=x)
    act(s, "p1", type="turn_face_up", card_id=bane.id, x_value=x)
    drive(s)
    assert not s.state.cards[bane.id].face_down
    assert (s.state.cards[bears.id].zone == "p1:battlefield") == (x < 2)
    check(s)


@pytest.mark.parametrize("x", [0, 3])
def test_warbreak_trumpeter_makes_x_goblins(cards, x):
    """107.3a: "Morph {X}{X}{R}" pays X twice; "create X 1/1 red Goblin creature tokens" reads the X announced."""
    s = build(cards, ["Warbreak Trumpeter"], [])
    trumpeter = _face_down(s, "Warbreak Trumpeter", {"C": 3})
    mana(s, "p1", R=1, C=2 * x)
    act(s, "p1", type="turn_face_up", card_id=trumpeter.id, x_value=x)
    drive(s)
    assert len([c for c in s.state.cards.values() if c.name == "Goblin" and c.zone == "p1:battlefield"]) == x
    check(s)


def test_turning_up_an_x_morph_needs_x(cards):
    """107.3a: the X of a morph cost is announced; leaving it out is refused."""
    from app.game.errors import ActionError

    s = build(cards, ["Warbreak Trumpeter"], [])
    trumpeter = _face_down(s, "Warbreak Trumpeter", {"C": 3})
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="turn_face_up", card_id=trumpeter.id)


def test_kadenas_silencer_counters_only_opponents_abilities(cards):
    """701.6a: "counter all abilities your opponents control" leaves the abilities its own controller controls on the stack."""
    s = build(cards, ["Kadena's Silencer", "Herald of Anafenza"], [])
    silencer = _face_down(s, "Kadena's Silencer", {"C": 3})
    herald = put(s, "Herald of Anafenza")
    s.state.rules.controlled_since[herald.id].turn = 0
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=herald.id, ability=0)
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=silencer.id)
    drive(s)
    assert not s.state.cards[silencer.id].face_down
    assert s.state.cards[herald.id].counters.get("+1/+1") == 1  # its own ability still resolved
    check(s)


def test_kadenas_silencer_counters_an_opponents_ability_on_the_stack(cards):
    """701.6a: the turn-face-up trigger counters Bob's activated ability on the stack and not Alice's own, which resolves."""
    s = build(cards, ["Kadena's Silencer", "Herald of Anafenza"], ["Shivan Dragon"])
    silencer = _face_down(s, "Kadena's Silencer", {"C": 3})
    herald = put(s, "Herald of Anafenza")
    sorcerer = put(s, "Shivan Dragon", pid="p2")
    s.state.rules.controlled_since[herald.id].turn = 0
    act(s, "p2", type="set_prefs", response="on")  # both players stop at every priority
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=herald.id, ability=0)
    mana(s, "p2", R=1)
    act(s, "p2", type="activate_ability", card_id=sorcerer.id, ability=1)
    assert len(s.state.zones["stack"]) == 3  # Alice outlast + its Warrior trigger, Bob pump
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=silencer.id)
    drive(s)
    assert ch(s, sorcerer).power == "5"  # Bob's {R}: +1/+0 was countered (a Shivan Dragon is 5/5)
    assert s.state.cards[herald.id].counters.get("+1/+1") == 1
    check(s)



def test_plague_reaver_returns_under_the_chosen_opponent(cards):
    """Plague Reaver: 701.21a end-step sacrifice of the other creatures; 603.7 delayed return at that player's next upkeep under their control (110.2a)."""
    s = build(cards, ["Plague Reaver", "Grizzly Bears", "Forest", "Forest"], [])
    reaver = put(s, "Plague Reaver")
    bears = put(s, "Grizzly Bears")
    for f in [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"]:
        act(s, "p1", type="move", card_ids=[f], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="activate_ability", card_id=reaver.id, ability=1, targets=["p2"])
    drive(s, lambda d: [o.id for o in d.options][:2])
    assert s.state.cards[reaver.id].zone == "p1:graveyard"
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.cards[reaver.id].zone.endswith(":battlefield"))
    assert s.state.cards[reaver.id].zone == "p2:battlefield"
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_plague_reaver_end_step_sacrifices_each_other_creature(cards):
    """701.21a: at its controller's end step every other creature that player controls is sacrificed, the Reaver stays."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Plague Reaver", "Grizzly Bears"], [])
    reaver, bears = put(s, "Plague Reaver"), put(s, "Grizzly Bears")
    until(s, lambda s: s.state.cards[bears.id].zone == "p1:graveyard")
    assert s.state.cards[reaver.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("zone, giant, dmg", [("battlefield", False, 2), ("graveyard", True, 2), ("graveyard", False, 0), ("hand", True, 0)])
def test_quakebringer_triggers_on_the_battlefield_or_from_the_graveyard_with_a_giant(cards, zone, giant, dmg):
    """Quakebringer: the upkeep trigger functions on the battlefield, or in its controller's graveyard while they control a Giant; once only."""
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Quakebringer", "Hill Giant"], [])
    q = put(s, "Quakebringer")
    if giant:
        put(s, "Hill Giant")
    if zone != "battlefield":
        act(s, "p1", type="move", card_ids=[q.id], to={"player": "p1", "zone": zone})
    to_turn(s, 3, "main1")
    assert s.state.players["p2"].life == 40 - dmg
    check(s)


@pytest.mark.parametrize("also_carol, bob_life", [(False, 40), (True, 38)])
def test_suppressor_skyguard_prevents_combat_damage_only_when_another_opponent_is_not_attacked(cards, also_carol, bob_life):
    """Suppressor Skyguard: 508.3d the attacker has another opponent (Carol) who is not being attacked -> prevention this combat (615.1); not otherwise."""
    from tests.wave100c_kit import three

    s = three(cards, ["Grizzly Bears", "Hill Giant"], ["Suppressor Skyguard"], [])
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    put(s, "Suppressor Skyguard", "p2")
    for c in (bears, giant):
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"},
                                                      *([{"card_id": giant.id, "target": "p3"}] if also_carol else [])])
    for _ in range(40):
        if s.state.turn.phase == "main2":
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == bob_life  # (Grizzly Bears deals 2)
    assert s.state.players["p3"].life == (37 if also_carol else 40)
    check(s)
